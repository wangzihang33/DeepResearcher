# Deep Research Assistant 优化规划

目录名称：`deep-research-assistant`

本文档是项目竞争力优化规划，不代表当前所有能力均已完成。当前阶段先明确项目定位、现有架构、外部参考、差异化改造路线和后续可写入简历的方向。

## 项目定位

面向技术调研、行业分析、产品选型和资料综述场景的多 Agent 深度研究助手。系统接收一个复杂研究主题后，自动拆解研究任务，执行联网检索，汇总子任务发现，并生成结构化研究报告。

后续优化目标不是再做一个客服 RAG，而是把项目升级为一个可恢复、可追踪、可校验、可评测的长任务多 Agent 研究系统。

## 当前已有能力

- FastAPI 后端，提供 `/research` 和 `/research/stream` 接口。
- 前端通过 SSE 接收研究进度、任务列表、来源、任务总结和最终报告。
- `DeepResearchAgent` 作为核心编排类，负责规划、检索、总结和报告生成。
- 多 Agent 角色已初步存在：研究规划专家、任务总结专家、报告撰写专家。
- `PlanningService` 将复杂主题拆成 3-5 个研究子任务。
- `dispatch_search` 统一调用 HelloAgents `SearchTool`，支持不同搜索后端。
- `SummarizationService` 对每个子任务生成研究总结。
- `ReportingService` 汇总所有子任务输出最终 Markdown 报告。
- `NoteTool` 用于记录任务笔记，支持一定程度的跨 Agent 信息共享。
- 当前多任务执行使用多线程并发，能够同时推进多个研究子任务。

## 当前主要短板

- 工作流状态没有完整持久化，服务重启或单个任务失败后无法稳定断点恢复。
- 多 Agent 协作主要靠手写线程和服务调用串联，缺少显式的状态图、任务图和可恢复执行语义。
- 搜索结果复用、来源归档和研究证据沉淀还不完整。
- 报告生成后缺少引用校验和事实核查，无法证明关键结论均有来源支撑。
- 流式事件已经存在，但缺少完整 research trace，例如 task span、source span、agent handoff、耗时、失败重试和成本统计。
- 缺少研究质量评测集，无法量化报告覆盖率、引用完整性、事实一致性和任务完成质量。

## 外部参考结论

本轮规划只参考官方公开资料和开源项目，不参考任何未经授权的泄露源码。

### Claude Code 官方公开设计

- Claude Code 官方仓库展示了命令、插件和可组合配置的工程组织方式，适合参考其“可扩展 Agent 工作台”的项目结构。
- Subagents 文档强调专用 Agent 拥有独立上下文、专用系统提示词和受控工具权限，适合映射到本项目的 Planner、Researcher、Citation Verifier、Report Writer、Reviewer。
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
- 长任务断点恢复。
- 研究证据图谱。
- 引用校验和事实核查。
- 报告质量评测。

一句话概括：智扫通解决“客服 Agent 如何稳定回答业务问题”，Deep Research Assistant 解决“多 Agent 如何完成可追溯、可恢复、可验证的长任务研究”。

## 推荐改造路线

### Phase 1：LangGraph 多 Agent 编排与协作通信

目标：构建显式的多 Agent 研究状态图和结构化通信协议，实现任务并行分发、上下文隔离、研究成果共享与跨 Agent 反馈协作。

当前 V1 文档：`docs/phase1_langgraph_multi_agent_v1.md`

设计方向：

- 引入 LangGraph `StateGraph`，定义统一 `ResearchState`。
- 采用 Supervisor-Worker 架构，将 Planner、Researcher、Compressor、Citation Verifier、Report Writer 和 Reviewer 建模为独立节点或子图。
- 建立共享任务板，记录任务负责人、依赖关系、执行状态、重试次数和产出位置。
- 使用 LangGraph `Send` 动态分发并行研究任务，使用 Reducer 汇总多个 Researcher 的执行结果。
- 为不同 Agent 保留独立上下文，只通过共享状态传递必要信息，避免完整对话历史持续膨胀。
- 定义结构化 `ResearchArtifact`，统一传递 `task_id`、核心发现、来源证据、置信度和待验证问题。
- 定义 `HandoffMessage`，记录 Supervisor 任务委派、Researcher 产物提交以及 Writer 上下文交接。
- 使用图状态更新和条件路由管理 Agent 交接，限制无效循环并为后续补研反馈预留扩展点。
- 对并行 Agent 返回的重复或冲突结论进行来源去重、证据合并和冲突标记。
- 保留当前 FastAPI SSE，但事件来自图执行过程，而不是手写线程状态。

可写入简历的方向：

> 基于 LangGraph 构建 Supervisor-Worker 多 Agent 研究图，设计共享任务板、结构化 Research Artifact 与 Handoff 通信协议，实现研究任务并行分发、上下文隔离和跨 Agent 证据协作。

### Phase 2：研究会话持久化与断点恢复

目标：让长任务研究可以恢复、重试和复盘。

设计方向：

- 引入 SQLite 保存 research session、task、source、note、claim、report。
- 每次研究生成 `session_id`。
- 每个子任务记录 `task_id`、状态、搜索查询、来源列表、总结结果和失败原因。
- 支持服务重启后通过 `session_id` 恢复未完成任务。
- 支持失败任务单独重试，保留已完成任务结果。
- 支持人工暂停、继续和终止研究。
- LangGraph checkpointer 与业务数据库结合：checkpointer 保存图状态，SQLite 保存可查询业务记录。

可写入简历的方向：

> 设计研究会话持久化机制，基于 session/task/source/report 状态表支持长任务断点恢复、失败重试和部分结果复用，提高多 Agent 研究流程的可靠性。

### Phase 3：Evidence Graph 与引用校验 Agent

目标：让最终报告的关键结论能够追溯到具体来源，减少无依据结论。

设计方向：

- 将搜索结果和网页内容整理为结构化 `SourceCard`。
- 从任务总结和最终报告中抽取关键 `Claim`。
- 建立 `Claim -> Evidence -> Source` 的证据映射。
- Citation Verifier 判断每条 claim 是否有来源支撑。
- 对 unsupported claim 执行补充检索，或在报告中标注不确定性。
- 生成 citation coverage、unsupported claim count、source diversity 等指标。
- 最终报告引用不让模型自由编造，而是从证据图中选择真实来源。

可写入简历的方向：

> 构建 Evidence Graph 与引用校验 Agent，将报告关键结论映射到来源片段，统计引用覆盖率与无支撑结论，提升深度研究报告的事实一致性和可追溯性。

### Phase 4：深度研究质量评测

目标：让项目优化从“看起来更好”变成“指标可证明”。

设计方向：

- 构建 20-30 条深度研究评测任务，覆盖技术选型、行业分析、论文综述、竞品调研。
- 每条任务标注期望覆盖点、推荐来源类型、报告结构要求和事实性要求。
- 指标包括 task coverage、citation coverage、unsupported claim rate、source diversity、report structure score。
- 支持 baseline 和改造后版本对比。
- 输出 CSV 和 Markdown 评测报告。
- 可使用 LLM-as-judge，但评分 rubric 要固定，避免每次标准漂移。

可写入简历的方向：

> 构建深度研究任务评测集，从任务覆盖率、引用覆盖率、无支撑结论率、来源多样性和报告结构完整性评估多 Agent 研究质量。

## 建议开发顺序

1. 先做 Phase 1：LangGraph 多 Agent 编排与协作通信。它决定整个项目的技术叙事，也是和智扫通差异最大的核心亮点。
2. 再做 Phase 2：研究会话持久化与断点恢复。它能把“多 Agent demo”变成真正长任务系统。
3. 接着做 Phase 3：Evidence Graph 与引用校验 Agent。它能显著提升报告可信度，也是面试中最好讲的点。
4. 最后做 Phase 4：深度研究质量评测，用量化结果验证前三个阶段的实际收益。

## 不建议作为主线的方向

- 不建议把 MCP 作为当前主线亮点。除非明确要让外部 Agent 或外部客户端复用本项目工具，否则 MCP 对这个项目的直接收益有限。
- 不建议重复智扫通的客服 RAG 评测、Web RAG 缓存和工具 Hook 治理叙事。
- 不建议一开始追求复杂 UI，先把后端多 Agent 状态图、证据链和评测闭环做扎实。

## 最终目标项目标题

深度研究助手：基于 LangGraph 的可恢复、可校验、可评测多 Agent 研究报告生成系统

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
