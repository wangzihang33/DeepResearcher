# DeepResearcher：多 Agent 研究系统

DeepResearcher 是一个面向技术调研、行业分析和产品选型场景的多 Agent 深度研究系统。用户输入一个复杂研究主题后，系统会自动拆解研究任务、执行联网检索、汇总证据来源、校验引用关系，并生成结构化 Markdown 研究报告。

项目基于 LangGraph 构建显式多 Agent 研究图，结合 FastAPI、Vue、SSE 流式事件、Evidence Graph 和规则评测脚本，让深度研究过程具备可协作、可追溯、可校验和可评测的工程闭环。

## 功能

| 功能 | 说明 |
|---|---|
| 多 Agent 研究编排 | 基于 LangGraph `StateGraph` 构建 Planner、Researcher、Compressor、Citation Verifier 和 Report Writer 流程。 |
| 任务拆解 | Planner 将复杂研究主题拆解为 3-5 个互补研究子任务。 |
| 并行研究 | 通过 LangGraph `Send` 动态分发多个 Researcher worker，并用 reducer 合并研究产物。 |
| 结构化通信 | 使用任务板、研究产物、来源卡片和交接消息约束 Agent 间协作，减少上下文膨胀和状态混乱。 |
| Evidence Graph | 将研究结论、来源证据和支撑关系组织为 Claim-Evidence Graph。 |
| 引用校验 | 在报告生成前校验关键结论与来源证据的支撑关系，并在最终报告中追加引用审计附录。 |
| 流式前端 | 前端通过 SSE 实时展示任务状态、阶段记录、来源列表和最终报告。 |
| 质量评测 | 提供 Task Coverage、Citation Coverage、Source Quality 三个规则指标，输出 CSV 和 Markdown 评测报告。 |

## 使用示例

可以尝试以下研究主题：

```text
对比 LangGraph、AutoGen 和 CrewAI 在多 Agent 编排、状态管理、并行任务、上下文隔离及生产部署方面的差异，并给出企业级深度研究系统的技术选型建议。

调研 2026 年企业级 RAG 系统在引用追踪、事实一致性和证据校验方面的主流工程实践。

设计一套用于评估 Deep Research 报告质量的规则指标体系，覆盖任务覆盖率、引用覆盖率和来源质量。
```

更多人工测试问题见 [manual_test_questions.txt](manual_test_questions.txt)。

## 项目结构

```text
.
├── backend/
│   ├── src/
│   │   ├── main.py                    # FastAPI 入口
│   │   ├── agent.py                   # DeepResearchAgent 编排入口
│   │   ├── models.py                  # 任务、Artifact、Source、Evidence Graph 数据结构
│   │   ├── services/
│   │   │   ├── research_graph.py      # LangGraph 多 Agent 研究图
│   │   │   ├── planner.py             # 研究任务拆解
│   │   │   ├── search.py              # 联网检索调度
│   │   │   ├── summarizer.py          # 子任务总结
│   │   │   ├── evidence.py            # Evidence Graph 与引用校验
│   │   │   └── reporter.py            # 最终报告生成
│   │   └── evaluation/
│   │       ├── metrics.py             # 规则评测指标
│   │       ├── research_evaluation.py # 评测命令行入口
│   │       └── data/                  # Deep Research hard set
│   ├── tests/                         # 单元测试
│   └── .env.example                   # 后端配置模板
├── frontend/
│   ├── src/                           # Vue 前端
│   └── package.json
├── docs/                              # 阶段说明文档
├── outputs/                           # 评测输出和报告快照
├── requirements.txt                   # 后端依赖
└── manual_test_questions.txt          # 人工验收问题
```

## 安装

建议使用 Python 3.10 或以上版本。

### 后端

```bash
cd backend
pip install -e .
```

也可以在项目根目录使用：

```bash
pip install -r requirements.txt
```

### 前端

```bash
cd frontend
npm install
```

## 配置

复制后端配置模板：

```bash
cd backend
cp .env.example .env
```

Windows PowerShell 可以使用：

```powershell
cd backend
Copy-Item .env.example .env
```

常用配置项：

| 配置项 | 用途 |
|---|---|
| `LLM_PROVIDER` | 模型提供方，DashScope/OpenAI 兼容接口可使用 `custom`。 |
| `DASHSCOPE_API_KEY` | DashScope API Key。 |
| `DASHSCOPE_MODEL` | 生成模型名称，例如 `qwen3.6-plus`。 |
| `DASHSCOPE_BASE_URL` | DashScope OpenAI 兼容接口地址。 |
| `SEARCH_API` | 搜索后端，支持 `duckduckgo`、`tavily`、`perplexity`、`searxng`、`advanced`。 |
| `TAVILY_API_KEY` | Tavily 搜索 API Key，使用 Tavily 时填写。 |
| `PERPLEXITY_API_KEY` | Perplexity API Key，使用 Perplexity 时填写。 |
| `LLM_TIMEOUT` | LLM 调用超时时间，深度研究任务建议适当放宽。 |
| `ENABLE_NOTES` | 是否启用任务笔记持久化。 |
| `NOTES_WORKSPACE` | 任务笔记保存目录。 |

`.env` 不会被提交到 Git。

## 启动

### 后端服务

进入 `backend/src` 后启动 FastAPI：

```bash
cd backend/src
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

健康检查：

```bash
curl http://127.0.0.1:8000/healthz
```

### 前端页面

```bash
cd frontend
npm run dev
```

默认访问地址：

```text
http://127.0.0.1:5174
```

## API

### 普通研究接口

```http
POST /research
Content-Type: application/json

{
  "topic": "对比 LangGraph、AutoGen 和 CrewAI 的企业级适用性"
}
```

### 流式研究接口

```http
POST /research/stream
Content-Type: application/json

{
  "topic": "调研多 Agent 深度研究系统的评测方案"
}
```

前端默认使用 `/research/stream`，并实时消费 SSE 事件。

## 评测

进入 `backend/src` 后运行：

```bash
python -m evaluation.research_evaluation --max-cases 3 --run-label phase3_v1
```

输出目录：

```text
outputs/evaluations/
```

评测会生成：

```text
research_eval_*.csv
research_eval_*.md
reports/<timestamp>_<run_label>/*.md
```

核心指标：

| 指标 | 说明 |
|---|---|
| Task Coverage | 报告是否覆盖人工标注的关键研究点。 |
| Citation Coverage | 关键结论是否能追溯到来源证据。 |
| Source Quality | 引用来源是否偏官方文档、论文、GitHub、benchmark 等高质量来源。 |

## 测试

进入 `backend` 后运行：

```bash
python -m unittest discover -s tests
```

## 文档

- [LangGraph 多 Agent 编排与协作通信](docs/phase1_langgraph_multi_agent_v1.md)
- [Evidence Graph 与引用校验 Agent](docs/phase2_evidence_graph_v1.md)
- [深度研究质量评测](docs/phase3_quality_evaluation_v1.md)

## 注意事项

- 深度研究会调用外部搜索和大模型 API，请提前配置 `.env`。
- DuckDuckGo 搜索无需 API Key，但稳定性和结果质量可能受网络环境影响。
- Tavily、Perplexity 等搜索后端需要对应 API Key。
- `backend/notes/`、`outputs/`、前端构建产物和本地环境文件不会提交到 Git。
