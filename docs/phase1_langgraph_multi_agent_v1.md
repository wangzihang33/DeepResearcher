# Phase 1：LangGraph 多 Agent 编排与协作通信 V1

本阶段实现了一个基于 LangGraph 的 Supervisor-Worker 多 Agent 研究图，并为 Agent 之间设计了结构化通信协议。

核心目标：让深度研究流程从“手写线程并发”变成“显式状态图 + 结构化任务交接 + 并行研究产物合并”。

## LangGraph 在本项目中的作用

LangChain / HelloAgents 更偏向解决“单个 Agent 如何调用模型和工具”；LangGraph 负责解决“多个 Agent / 多个步骤如何按照状态图协作”。

本项目中：

- HelloAgents 继续负责 LLM 调用、工具调用和任务总结。
- LangGraph 负责 Planner、Researcher、Compressor、CitationVerifier、ReportWriter 之间的流程编排。
- `StateGraph` 定义工作流节点和流转关系。
- `Send` 根据 Planner 生成的任务数量动态分发多个 Researcher worker。
- Reducer 将多个 Researcher 的 `ResearchArtifact` 合并为统一列表。

## 当前流程

```text
用户研究主题
    ↓
Supervisor / Planner
    ↓
生成 TodoItem
生成 TaskBoardItem
生成 HandoffMessage
    ↓
LangGraph Send 并行分发
    ↓
Researcher-1 / Researcher-2 / Researcher-N
    ↓
读取 task_id / title / intent / query
执行搜索与总结
生成 ResearchArtifact
生成 HandoffMessage
    ↓
Reducer 合并多个 Artifact
    ↓
Compressor
    ↓
读取所有 Artifact
合并 summary / sources / evidence
更新 TaskBoard
生成 HandoffMessage
    ↓
CitationVerifier
    ↓
抽取 Claim、整理 SourceCard、建立 EvidenceLink
生成 EvidenceGraph 和引用校验结果
生成 HandoffMessage
    ↓
ReportWriter
    ↓
读取任务总结、来源和引用校验结果
生成最终 Markdown 报告
```

当前图节点在 `backend/src/services/research_graph.py` 中：

- `planner`：生成任务、共享任务板和任务交接消息。
- `researcher`：并行执行子任务，输出结构化研究产物。
- `compressor`：合并多个 Researcher 的产物和来源证据。
- `citation_verifier`：建立结论与来源之间的证据关系并输出引用校验结果。
- `report_writer`：消费压缩后的上下文和引用校验结果并生成最终报告。

主链路已接入 `DeepResearchAgent.run()` 和 `DeepResearchAgent.run_stream()`。

## 多 Agent 通信协议

本项目没有让 Agent 自由聊天，而是通过四个结构完成通信：

```text
TaskBoardItem    = 任务板 / 项目管理系统
ResearchArtifact = 研究成果 / 工作产物
SourceCard       = 来源证据 / 引用卡片
HandoffMessage   = 交接单 / Agent 交接记录
```

### 1. TaskBoardItem：任务板

用于记录任务状态，让所有 Agent 围绕同一份任务状态协作。

关键字段：

```text
task_id       任务编号
title         任务标题
intent        任务目标
query         检索 query
owner         负责人，例如 researcher_1
status        pending / in_progress / completed / failed
dependencies  任务依赖
retry_count   重试次数
artifact_id   对应 ResearchArtifact
note_id       对应笔记
error         失败原因
```

Supervisor 创建它；Researcher 执行任务；Compressor 根据 Artifact 更新它。

### 2. ResearchArtifact：研究成果

Researcher 完成任务后提交的结构化产物。下游 Agent 不读取完整聊天历史，只读取 Artifact 字段。

关键字段：

```text
artifact_id      成果 ID
task_id          对应任务
producer         由哪个 Researcher 生成
status           执行状态
summary          任务总结
sources_summary  来源摘要
findings         关键发现
evidence         SourceCard 列表
confidence       置信度
open_questions   待验证问题
notices          搜索或执行提示
error            错误信息
```

这个结构解决的是：Agent 之间传递“可解析成果”，而不是不可控自由文本。

### 3. SourceCard：来源证据

用于沉淀来源信息，Phase 2 的 Evidence Graph 和引用校验直接复用这部分数据。

关键字段：

```text
source_id 来源 ID
title    来源标题
url      来源链接
snippet  来源摘要
raw      原始片段
```

当前 V1 会从 `sources_summary` 中解析来源，并写入 `ResearchArtifact.evidence`。

### 4. HandoffMessage：交接单

用于记录 Agent 之间发生了什么交接。

关键字段：

```text
message_id    交接 ID
from_agent    来源 Agent
to_agent      目标 Agent
message_type  交接类型
task_id       关联任务
content       交接说明
payload       结构化补充数据
```

当前 V1 已覆盖四类交接：

```text
Supervisor  -> Researcher     任务分发
Researcher  -> Compressor     提交 ResearchArtifact
Compressor  -> CitationVerifier  提交合并后的研究上下文
CitationVerifier -> ReportWriter 提交引用校验结果
```

需要注意：当前 V1 中 `HandoffMessage` 主要用于流程追踪、审计和后续调试，不是下游 Agent 生成内容时的主要 prompt 输入。

真正被下游消费的主要是：

```text
Researcher      读取 TodoItem + TaskBoardItem
Compressor      读取 TaskBoardItem + ResearchArtifact
CitationVerifier 读取 ResearchArtifact 中的 findings 和 evidence
ReportWriter    读取 SummaryState + verified_claims_summary
```

也就是说，`HandoffMessage` 更像“交接日志 / 审计记录”；`TaskBoardItem` 和 `ResearchArtifact` 才是当前 Agent 协作中的主要业务输入。

## 为什么这样能解决 Agent 通信问题

多 Agent 通信最容易出问题的地方是：上下文越来越长、Agent 输出格式不稳定、任务状态混乱、下游不知道哪些结论有来源。

本项目的处理方式是：

- 用 `TaskBoardItem` 管任务状态。
- 用 `HandoffMessage` 管 Agent 交接。
- 用 `ResearchArtifact` 管研究成果。
- 用 `SourceCard` 管证据来源。
- 用 LangGraph `Send` 做并行任务分发。
- 用 reducer 合并多个 Researcher 的产物。

一句话：**TaskBoard 管状态，HandoffMessage 管交接，ResearchArtifact 管成果，SourceCard 管证据。**

## 面试官可能提问

### 1. LangChain 和 LangGraph 的区别是什么？

LangChain 更像 Agent 能力工具箱，主要解决模型调用、Prompt、工具注册、工具调用和普通 Agent loop。

LangGraph 更像状态化工作流编排引擎，主要解决多步骤、多 Agent、长任务场景下的状态流转、并行分发、结果合并、流式输出和后续持久化。

在本项目中，HelloAgents / LangChain 风格组件负责单个 Agent 的模型与工具能力，LangGraph 负责把 Planner、Researcher、Compressor、CitationVerifier 和 ReportWriter 编排成一个可控的多 Agent 研究图。

### 2. 你是如何解决 Agent 和 Agent 之间通信的？

我没有让 Agent 之间自由对话，而是设计了一套结构化通信协议。Supervisor 先生成共享任务板 `TaskBoardItem`，并通过 `HandoffMessage` 将任务分发给 Researcher；Researcher 执行检索和总结后输出 `ResearchArtifact`，其中包含任务总结、关键发现、来源证据和置信度；Compressor 通过 reducer 读取并合并所有 Artifact，CitationVerifier 建立结论与来源之间的证据关系，最后由 ReportWriter 读取压缩结果和引用校验上下文生成报告。

这样可以避免多 Agent 自由聊天导致的上下文膨胀、状态混乱和结果不可追踪。

### 3. 你是如何实现 Agent 间上下文隔离的？

我没有把上游 Agent 的完整对话历史直接传给下游 Agent，而是在代码节点中把关键结果封装成结构化 schema。Researcher 只接收自己的任务包，执行后只输出 `ResearchArtifact`；Compressor 读取多个 Artifact 并整理成 `SummaryState`；CitationVerifier 只读取结论和证据字段；ReportWriter 只读取压缩后的任务总结、来源摘要和引用校验结果。这样下游只看到必要字段，而不是所有 Agent 的完整上下文。

### 4. LangGraph 在项目中具体发挥了什么作用？

LangGraph 在项目中主要负责多 Agent 工作流编排：把 Planner、Researcher、Compressor、CitationVerifier 和 ReportWriter 串成显式状态图，并通过 `Send` 动态分发多个 Researcher，通过 reducer 合并并行研究结果。

它解决的是“流程如何流转、worker 如何分发、并行结果如何合并”；本项目自己的 schema 解决的是“Agent 之间传什么、怎么封装、下游消费哪些字段”。

## 可写入简历的一句话

基于 LangGraph 构建 Supervisor-Worker 多 Agent 研究图，设计共享任务板、结构化 Research Artifact 与 Handoff 通信协议，实现研究任务并行分发、上下文隔离和跨 Agent 证据协作。

## 面试摘要

我在项目中实现了一个 LangGraph 多 Agent 研究编排层。Supervisor 先把复杂研究主题拆成多个子任务，并写入共享任务板；随后通过 LangGraph `Send` 动态分发给多个 Researcher worker 并行执行。每个 Researcher 不直接向下游传递完整对话，而是输出结构化 `ResearchArtifact`，其中包含任务总结、来源证据、置信度和待验证问题。Compressor 会合并多个 artifact，CitationVerifier 对关键结论和来源关系进行校验，最后由 ReportWriter 生成最终报告。

这一版的重点不是简单“用了 LangGraph”，而是把多 Agent 协作中的任务分发、状态共享、成果交接和上下文隔离都结构化下来。Phase 2 的 Evidence Graph 已经基于这套状态图与通信协议接入，下一步可继续构建质量评测闭环。

## 验证命令

```bash
python -m compileall -q backend/src demo.py
uv run python -c "from agent import DeepResearchAgent; agent=DeepResearchAgent(); print(type(agent.research_graph).__name__)"
```
