# Phase 2：Evidence Graph 与引用校验 Agent V1

一句话：在报告生成前，把 Researcher 的结论、证据和来源组装成可校验的 Evidence Graph，再用引用覆盖率和无支撑结论率控制最终报告的事实一致性。

## 当前流程

```text
Researcher 输出 ResearchArtifact
    ↓
Compressor 合并多个 Artifact
    ↓
CitationVerifier 抽取 Claim / 整理 SourceCard / 建立 EvidenceLink
    ↓
生成 EvidenceGraph 与 citation metrics
    ↓
ReportWriter 同时读取任务总结和校验后的结论上下文
    ↓
生成最终报告并追加 Claim → Source 引用审计附录
```

`citation_verifier` 是 LangGraph 中新增的中间节点，放在 `compressor` 和 `report_writer` 之间。

## 这层到底做了什么

ResearchArtifact 不是纯文本，而是结构化研究产物，里面包含：

```text
summary   任务总结
findings  关键结论
evidence  来源证据
```

Citation Verifier 会把这些内容进一步整理成三类结构：

```text
Claim         待校验结论
SourceCard    来源证据卡片
EvidenceLink  结论与来源之间的支撑关系
```

最后把它们组装成 `EvidenceGraph`，供后续报告生成和审计使用。

Citation Verifier 还会通过 SSE 输出 `citation_metrics` 事件；最终报告会由代码追加引用校验摘要，明确展示 Claim ID、校验状态、Source ID 和真实 URL，而不是只依赖模型自由生成参考文献。

## 核心结构

### Claim

表示一条需要被证据支撑的结论。

```text
claim_id
task_id
text
source_ids
support_status
confidence
reason
```

### SourceCard

表示一条来源证据，通常来自研究过程中收集到的网页、文档或抓取结果。

```text
source_id
task_id
title
url
snippet
raw
```

### EvidenceLink

表示某条结论和某条来源之间的支撑关系。

```text
claim_id
source_id
relation
snippet
score
```

### EvidenceGraph

整张证据图，包含：

```text
claims
sources
links
metrics
```

它不是图数据库，而是当前流程中的结构化内存对象。V1 的重点不是持久化，而是先把“结论-证据-来源”闭环跑通。

## 引用校验规则

V1 先用轻量、本地、确定性的方式做校验，成本低，也方便稳定复盘。

1. 从 `ResearchArtifact.findings` 读取候选结论。  
2. 如果 `findings` 不够，再从 `summary` 切分结论。  
3. 从 `ResearchArtifact.evidence` 收集来源证据。  
4. 对 Claim 和 SourceCard 做词项匹配。  
5. 如果来源正文或摘要过短，词项匹配没有命中，则把同一个研究任务下的来源作为 `partial` 兜底候选证据。  
6. 根据匹配分数判断结论状态：

```text
supported    来源明确支撑该结论
partial      来源有部分线索，但支撑不充分
unsupported  当前来源不足以支撑该结论
```

当前打分方式是：

```text
score = 词项重合度 / sqrt(Claim词项数 × Source词项数)
```

如果结论文本在来源中直接命中，还会额外提高分数。  
如果词项匹配没有命中，但 Claim 和 SourceCard 来自同一个 `task_id`，系统会把该来源挂到 Claim 下，并将其标记为 `partial`。这样做不是把它当成强事实支撑，而是保留“该结论来自哪个研究任务的候选来源”，避免报告审计里出现“明明有来源列表，却完全无法追溯”的断层。

当前阈值大致是：

- `>= 0.18`：supported
- `>= 0.08`：partial
- `< 0.08`：unsupported

## 当前指标

Citation Verifier 会输出：

```text
claim_count
source_count
supported_claim_count
partial_claim_count
unsupported_claim_count
citation_coverage
unsupported_claim_rate
```

其中：

```text
citation_coverage = (supported + partial) / claim_count
unsupported_claim_rate = unsupported / claim_count
```

这两个指标的意义很直接：报告里有多少结论是真的被证据托住了，有多少结论还只是“看起来像对的”。

## 为什么这一步有价值

ReportWriter 不再直接相信上游总结，而是先读取校验结果，再决定怎么写。

规则很简单：

```text
supported / partial 结论：可以进入报告
unsupported 结论：不作为确定事实输出
```

这样能把“会写”变成“写得有证据”，让深度研究报告更可追溯，也更适合面试时讲清楚工程价值。

需要注意，V1 的 supported / partial / unsupported 来自确定性词项匹配，用于自动审计和风险提示，不等同于人工事实核查。报告附录会保留这一限制说明，避免把自动分数包装成绝对真值。

同任务来源兜底只会产生 `partial`，不会直接判定为 `supported`。这能保证 V1 的 Evidence Graph 偏保守：它可以提供可追溯线索，但不会把弱证据包装成强证据。

## 可写入简历的一句话

构建 Evidence Graph 与引用校验 Agent，在报告生成前将研究结论、证据卡片与来源建立结构化映射，输出引用覆盖率和无支撑结论率，提升深度研究报告的事实一致性与可追溯性。

## 面试摘要

我在多 Agent 研究图中新增了 Citation Verifier 节点。Researcher 先输出结构化 `ResearchArtifact`，其中包含任务总结、关键发现和来源证据；Citation Verifier 再从 Artifact 中抽取 Claim，整理 SourceCard，并建立 Claim 到 Source 的 EvidenceLink，最终形成 EvidenceGraph。ReportWriter 在生成报告前会读取校验结果，优先使用 supported 或 partial 的结论，避免 unsupported 结论被当成确定事实输出。

这一步的重点不是把模型变得更“聪明”，而是把研究结果变得更“可验”。它把报告写作和事实校验拆开，最终产物不仅能生成内容，还能说明关键结论来自哪些来源，以及当前证据覆盖情况如何。

## 验证命令

```bash
python -m compileall -q backend/src demo.py
python -c "from models import ResearchArtifact, SourceCard; from services.evidence import EvidenceGraphBuilder; a=ResearchArtifact(artifact_id='a1', task_id=1, producer='r1', status='completed', findings=['LangGraph 支持多 Agent 状态化编排和并行任务分发'], evidence=[SourceCard(title='LangGraph 多 Agent 编排文档', snippet='LangGraph 支持状态化工作流、多 Agent 编排和并行任务分发')]); g=EvidenceGraphBuilder().build([a]); print(g.metrics)"
```
