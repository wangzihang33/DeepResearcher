# Phase 3：深度研究质量评测 V1

一句话：用固定评测集和三个规则指标，让多 Agent 深度研究报告从“看起来不错”变成“可以量化复盘”。

## 当前流程

```text
research_eval_dataset.jsonl
    ↓
逐条运行 DeepResearchAgent
    ↓
保存每条最终报告
    ↓
规则指标计算 Task Coverage / Citation Coverage / Source Quality
    ↓
输出 CSV 明细和 Markdown 汇总报告
```

这一步不改变主业务链路，而是在系统外侧增加一个评测闭环。

最新一次真实评测跑通 `tech_selection_001` hard case，结果如下：

```text
Task Coverage       0.50
Citation Coverage   1.00
Source Quality      1.00
Unsupported Rate    0.00
```

这说明当前报告的来源和引用链路质量较好，但研究点覆盖仍有提升空间，评测结果能够真实暴露优化方向。

## 评测数据集

数据集位于：

```text
backend/src/evaluation/data/research_eval_dataset.jsonl
```

当前 V1 包含 13 条 hard set，覆盖技术选型、论文综述、行业分析、竞品调研、架构评审、开源调研、安全调研、评测设计、协议调研、可观测性、时效性、记忆机制和回归评测等场景。

每条样本包含：

```text
id
category
query
expected_topics
preferred_source_keywords
```

其中 `expected_topics` 是人工标注的标准研究点。为了和 Planner 的 3-5 个子任务约束对齐，每条样本只标注 3-5 个关键检查点，默认控制在 4 个左右。V1 不再只标注 query 里直接出现的宽泛词，而是标注更细的检查点。例如技术选型任务会标注：

```text
状态恢复机制
动态并行分支
可观测性链路
选型决策矩阵
```

每个研究点还会配置 aliases，用来处理同义表达，例如：

```text
状态恢复机制：检查点持久化 / 状态快照 / 中断恢复 / checkpointing / PostgresSaver
```

所以 Task Coverage 不是让模型自己评分，而是“人工标注标准项 + 程序规则匹配报告内容”。

为了避免报告标题或 frontmatter 中的原始 query 直接命中 expected topics，评测脚本在计算 Task Coverage 前会去掉 YAML frontmatter 和报告开头的一级标题。这样指标更接近“正文是否真的展开分析”，而不是“题目里有没有这个词”。

## 三个核心指标

### 1. Task Coverage

评估报告是否覆盖预期研究点。

```text
task_coverage = covered_expected_topics / expected_topics
```

它回答的问题是：研究有没有漏掉用户真正关心的维度。

### 2. Citation Coverage

复用 Phase 2 的 Evidence Graph 审计结果。

```text
citation_coverage = (supported + partial) / claim_count
```

它回答的问题是：报告里的结论有多少能追溯到来源。

注意这里更准确地说是“引用覆盖率”或“可追溯率”，不是人工事实正确率。

### 3. Source Quality

基于来源标题、URL 和 domain 做规则判断。

```text
source_quality = trusted_sources / total_sources
```

高质量来源关键词包括：

```text
official
docs
github
arxiv
paper
research
benchmark
developer
gov / edu
```

每条样本还可以配置自己的 `preferred_source_keywords`，例如技术选型任务偏好 official docs、GitHub、benchmark，论文综述任务偏好 arxiv、paper、ACL、IEEE。

它回答的问题是：报告是否尽量使用官方文档、论文、代码仓库、benchmark 等更可靠的来源。

## 使用命令

进入 backend 目录后运行：

```bash
python -m evaluation.research_evaluation --max-cases 3 --run-label phase3_v1
```

输出目录：

```text
outputs/evaluations/
```

每次运行会生成：

```text
research_eval_*.csv
research_eval_*.md
reports/<timestamp>_<run_label>/*.md
```

CSV 用于记录每条样本的指标明细，Markdown 用于快速查看整体均值和低分原因。

## 可写入简历的一句话

构建 Deep Research hard set，基于任务覆盖率、引用覆盖率和来源质量评估多 Agent 报告质量，实现 Citation Coverage 1.00、Source Quality 1.00。

## 面试摘要

我为深度研究任务构建了一个可复现的规则评测闭环。每条评测样本会人工标注 3-5 个 expected topics 和偏好的来源类型，系统运行后自动保存报告，并计算 Task Coverage、Citation Coverage 和 Source Quality 三个指标。

Task Coverage 衡量报告是否覆盖关键研究维度，Citation Coverage 复用 Evidence Graph 的引用审计结果，Source Quality 通过 URL、domain 和标题判断来源是否偏官方、论文、GitHub 或 benchmark。这样评测结果稳定、成本低，也能清楚指导后续系统优化。

面试时可以强调：这一步不是为了追求单次高分，而是把深度研究系统变成可回归、可对比、可定位问题的工程系统。比如当前样本引用覆盖和来源质量满分，但 Task Coverage 只有 0.50，说明报告还缺少“动态并行分支”和“选型决策矩阵”等研究点，下一轮优化就有明确方向。
