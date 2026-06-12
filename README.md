# Deep Research Assistant 优化规划

目录名称：`deep-research-assistant`

本文档记录项目竞争力优化路线与当前阶段进度。Phase 1 的 LangGraph 多 Agent 编排、Phase 2 的 Evidence Graph 引用校验和 Phase 3 的深度研究质量评测均已完成 V1。

## 项目定位

面向技术调研、行业分析、产品选型和资料综述场景的多 Agent 深度研究助手。系统接收一个复杂研究主题后，自动拆解研究任务，执行联网检索，汇总子任务发现，并生成结构化研究报告。

项目目标不是再做一个客服 RAG，而是构建一个可协作、可追踪、可校验、可评测的长任务多 Agent 研究系统。

## 当前已有能力

- FastAPI 后端，提供 `/research` 和 `/research/stream` 接口。
- 前端通过 SSE 接收研究进度、任务列表、来源、任务总结和最终报告。
- 基于 LangGraph `StateGraph` 构建 Planner、Researcher、Compressor、Citation Verifier 和 Report Writer 显式研究图。
- 采用 Supervisor-Worker 架构，通过 `Send` 动态分发并行研究任务，并使用 reducer 合并多个 Researcher 的产物。
- 使用共享任务板记录任务状态，以 `ResearchArtifact`、`SourceCard` 和 `HandoffMessage` 作为结构化协作协议。
- `PlanningService` 将复杂主题拆成 3-5 个研究子任务。
- `dispatch_search` 统一调用 HelloAgents `SearchTool`，支持不同搜索后端。
- `SummarizationService` 对每个子任务生成研究总结。
- Citation Verifier 将关键结论抽取为 Claim，将来源整理为 SourceCard，并建立 Claim 到 Source 的 EvidenceLink。
- Evidence Graph 输出引用覆盖率、无支撑结论率及 supported、partial、unsupported 结论统计。
- `ReportingService` 同时读取任务总结和引用校验结果，生成带来源约束的最终 Markdown 报告。
- 新增深度研究质量评测模块，基于固定评测集输出 Task Coverage、Citation Coverage 和 Source Quality。

## 当前下一步重点

- 当前三个核心竞争点已经形成 V1 闭环：多 Agent 编排、引用校验、质量评测。
- 后续可以继续积累更多评测样本，形成 baseline 与不同版本的长期对比。
- Citation Verifier 和质量评测目前采用确定性规则，后续可在 V2 中选择性引入语义匹配或 LLM Judge。

## 外部参考结论

本轮规划只参考官方公开资料和开源项目，不参考任何未经授权的泄露源码。

### Claude Code 官方公开设计

- Claude Code 官方仓库展示了命令、插件和可组合配置的工程组织方式，适合参考其“可扩展 Agent 工作台”的项目结构。
- Subagents 文档强调专用 Agent 拥有独立上下文、专用系统提示词和受控工具权限，适合映射到本项目的 Planner、Researcher、Citation Verifier 和 Report Writer。
- Hooks 文档强调在工具调用前后插入确定性控制逻辑，适合本项目后续做搜索预算、任务状态、来源记录和错误兜底。
- Memory 文档强调把项目规范、工作流偏好和长期上下文沉淀为可审计文件，适合本项目沉淀研究模板、可信来源规则和报告格式规范。
- Plugins/Skills 文档强调把可复用能力按技能组织。对本项目来说，短期不需要做插件化，但可以借鉴其“研究计划、来源审计、引用校验、报告复审”等技能边界。

### 主流 Deep Research / 多 Agent 项目

- LangGraph 的核心价值在于长期运行、状态化、多步骤 Agent 工作流，支持持久化、流式输出、人类介入和调试追踪；本项目天然适合用 LangGraph 改造。
- LangChain Open Deep Research 采用可配置搜索、模型分工、LangGraph 工作流和评测基准，说明深度研究项目的竞争点已经从“能联网总结”转向“可编排、可评测、可复现”。
- GPT Researcher 的亮点是基于问题生成研究子问题，再由爬取/总结/来源跟踪形成长报告；这与本项目已有规划-检索-总结-报告链路相近，但本项目需要补足证据链和状态化能力。
- OpenAI Deep Research 强调多步骤搜索、来源综合、引用和进度可见性，说明“带证据的长任务研究过程”比单次搜索总结更有竞争力。
- OpenAI Agents SDK 的 handoff 和 tracing 设计说明，多 Agent 系统需要显式记录 agent 交接、工具调用、guardrail、trace/span 和会话状态。

## 与智扫通项目的差异化

智扫通智能客服系统的核心竞争点是客服场景下的 Hybrid RAG、动态 Web RAG、工具生命周期治理和业务工具服务化。

Deep Research Assistant 不建议重复这些亮点。这个项目应重点讲：

- 多 Agent 任务图编排。
- 研究证据图谱。
- 引用校验和事实核查。
- 报告质量评测。

一句话概括：智扫通解决“客服 Agent 如何稳定回答业务问题”，Deep Research Assistant 解决“多 Agent 如何完成可协作、可追溯、可验证的长任务研究”。

## 推荐改造路线

### Phase 1：LangGraph 多 Agent 编排与协作通信（V1 已完成）

目标：构建显式的多 Agent 研究状态图和结构化通信协议，实现任务并行分发、上下文隔离、研究成果共享与跨 Agent 反馈协作。

当前 V1 文档：`docs/phase1_langgraph_multi_agent_v1.md`

已实现：

- 引入 LangGraph `StateGraph`，定义统一 `ResearchGraphState`。
- 采用 Supervisor-Worker 架构，将 Planner、Researcher、Compressor、Citation Verifier 和 Report Writer 建模为独立节点。
- 建立共享任务板，记录任务负责人、依赖关系、执行状态、重试次数和产出位置。
- 使用 LangGraph `Send` 动态分发并行研究任务，使用 Reducer 汇总多个 Researcher 的执行结果。
- 为不同 Agent 保留独立上下文，只通过共享状态传递必要信息，避免完整对话历史持续膨胀。
- 定义结构化 `ResearchArtifact`，统一传递 `task_id`、核心发现、来源证据、置信度和待验证问题。
- 定义 `HandoffMessage`，记录 Supervisor 任务委派、Researcher 产物提交以及 Writer 上下文交接。
- 保留当前 FastAPI SSE，但事件来自图执行过程，而不是手写线程状态。

可写入简历的方向：

> 基于 LangGraph 构建 Supervisor-Worker 多 Agent 研究图，设计共享任务板、结构化 Research Artifact 与 Handoff 通信协议，实现研究任务并行分发、上下文隔离和跨 Agent 证据协作。

### Phase 2：Evidence Graph 与引用校验 Agent（V1 已完成）

目标：让最终报告的关键结论能够追溯到具体来源，减少无依据结论。

当前 V1 文档：`docs/phase2_evidence_graph_v1.md`

已实现：

- 将研究过程中收集到的来源整理为结构化 `SourceCard`。
- 从 `ResearchArtifact.findings` 和 `summary` 中抽取关键 `Claim`。
- 建立 Claim、SourceCard 和 EvidenceLink 组成的 Evidence Graph。
- Citation Verifier 使用确定性词项匹配，将结论分为 supported、partial 和 unsupported。
- 当来源摘要较短导致词项匹配不足时，同一研究任务下的来源会作为 partial 兜底证据，保证结论仍可追溯到候选来源，但不会被误判为强支撑。
- 输出 citation coverage、unsupported claim rate 和各状态结论数量。
- 将校验结果写入 `SummaryState` 并通过 SSE 输出指标，供 Report Writer 优先使用有来源支撑的结论。
- 在最终报告中程序化追加 Claim、Source ID、来源 URL 和校验指标组成的引用审计附录。
- 任务完成后由代码回写任务总结与来源笔记，避免依赖模型是否主动调用更新工具。

可写入简历的方向：

> 构建 Evidence Graph 与引用校验 Agent，在报告生成前将研究结论、证据卡片与来源建立结构化映射，输出引用覆盖率和无支撑结论率，提升深度研究报告的事实一致性与可追溯性。

### Phase 3：深度研究质量评测（V1 已完成）

目标：让项目优化从“看起来更好”变成“指标可证明”。

当前 V1 文档：`docs/phase3_quality_evaluation_v1.md`

已实现：

- 构建 13 条 deep research hard set，覆盖技术选型、论文综述、行业分析、竞品调研、架构评审、开源调研、安全调研、评测设计、协议调研、可观测性、时效性、记忆机制和回归评测。
- 每条样本人工标注 3-5 个 `expected_topics` 和 `preferred_source_keywords`，与 Planner 的 3-5 个研究子任务约束保持同一尺度。
- 使用规则指标评估 Task Coverage、Citation Coverage 和 Source Quality，不依赖 LLM Judge，保证稳定、低成本、可复现。
- Task Coverage 会先去掉报告 frontmatter 和开头标题，再通过 expected topics 与 aliases 匹配正文内容，衡量研究完整性，避免 query 原文导致指标虚高。
- Citation Coverage 复用 Phase 2 的 Evidence Graph 引用审计结果，衡量结论可追溯性。
- Source Quality 基于来源标题、URL、domain 和任务偏好的关键词，衡量来源可靠性。
- 输出 CSV 明细、Markdown 汇总报告和每条样本的最终报告快照。

使用命令：

```bash
python -m evaluation.research_evaluation --max-cases 3 --run-label phase3_v1
```

可写入简历的方向：

> 构建 Deep Research hard set，基于任务覆盖率、引用覆盖率和来源质量评估多 Agent 报告质量，实现 Citation Coverage 1.00、Source Quality 1.00。

## 当前阶段进度

1. Phase 1 已完成：LangGraph 多 Agent 编排、并行任务分发、结构化通信和上下文隔离已经落地。
2. Phase 2 已完成：Evidence Graph、Citation Verifier、引用指标和报告生成约束已经形成 V1 闭环。
3. Phase 3 已完成：深度研究评测集、三项规则指标、CSV/Markdown 评测报告已经形成 V1 闭环。

## 不建议作为主线的方向

- 不建议把 MCP 作为当前主线亮点。除非明确要让外部 Agent 或外部客户端复用本项目工具，否则 MCP 对这个项目的直接收益有限。
- 不建议重复智扫通的客服 RAG 评测、Web RAG 缓存和工具 Hook 治理叙事。
- 不建议把研究会话持久化与断点恢复作为独立简历主线。它可以作为 LangGraph 工作流的后续工程增强，但不单独占用一个竞争点。
- 不建议一开始追求复杂 UI，先把后端多 Agent 状态图、证据链和评测闭环做扎实。

## 最终目标项目标题

深度研究助手：基于 LangGraph 的可协作、可校验、可评测多 Agent 研究报告生成系统

## 技术参考

- Claude Code 官方仓库：https://github.com/anthropics/claude-code
- Claude Code Subagents：https://code.claude.com/docs/en/sub-agents
- Claude Code Hooks：https://code.claude.com/docs/en/hooks
- Claude Code Memory：https://code.claude.com/docs/en/memory
- Claude Code Plugins：https://code.claude.com/docs/en/plugins
- LangGraph Overview：https://docs.langchain.com/oss/python/langgraph/overview
- LangChain Open Deep Research：https://github.com/langchain-ai/open_deep_research
- GPT Researcher：https://github.com/assafelovic/gpt-researcher
- OpenAI Deep Research：https://openai.com/index/introducing-deep-research/
- OpenAI Agents SDK Handoffs：https://openai.github.io/openai-agents-python/handoffs/
- OpenAI Agents SDK Tracing：https://openai.github.io/openai-agents-python/tracing/
- OpenResearcher：https://github.com/TIGER-AI-Lab/OpenResearcher
