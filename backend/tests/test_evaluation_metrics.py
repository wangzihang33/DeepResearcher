"""Tests for rule-based deep research evaluation metrics."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from evaluation.metrics import EvalCase, evaluate_report


class EvaluationMetricsTests(unittest.TestCase):
    def test_evaluates_task_coverage_citation_and_source_quality(self) -> None:
        case = EvalCase.from_dict(
            {
                "id": "case-1",
                "category": "技术选型",
                "query": "对比 Agent 框架",
                "expected_topics": [
                    {"name": "状态管理", "aliases": ["状态管理", "checkpoint"]},
                    {"name": "并行任务", "aliases": ["并行任务", "parallel"]},
                    {"name": "生产部署", "aliases": ["生产部署"]},
                ],
                "preferred_source_keywords": ["docs", "github"],
            }
        )
        report = """
## 核心洞见
系统需要状态管理和 checkpoint，也要支持并行任务。

## 引用校验摘要
| 指标 | 数值 |
| --- | ---: |
| 引用覆盖率 | 80.00% |
| 无支撑结论率 | 20.00% |

### 去重后的来源
- **[S1]** [LangGraph docs](https://docs.langchain.com/langgraph)
- **[S2]** [Random blog](https://example.com/post)
"""

        result = evaluate_report(case, report)

        self.assertEqual(0.6667, result.task_coverage)
        self.assertEqual(0.8, result.citation_coverage)
        self.assertEqual(0.2, result.unsupported_claim_rate)
        self.assertEqual(0.5, result.source_quality)
        self.assertEqual(["生产部署"], result.missing_topics)

    def test_task_coverage_ignores_frontmatter_and_report_title(self) -> None:
        case = EvalCase.from_dict(
            {
                "id": "case-2",
                "category": "技术选型",
                "query": "对比 Agent 框架",
                "expected_topics": [
                    {"name": "状态恢复机制", "aliases": ["状态恢复机制", "检查点持久化"]},
                ],
            }
        )
        report = """---
title: 状态恢复机制调研
---

# 状态恢复机制调研

## 背景
这里只讨论基本架构，没有覆盖目标检查点。
"""

        result = evaluate_report(case, report)

        self.assertEqual(0.0, result.task_coverage)
        self.assertEqual(["状态恢复机制"], result.missing_topics)

    def test_dataset_expected_topics_match_planner_range(self) -> None:
        dataset_path = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "evaluation"
            / "data"
            / "research_eval_dataset.jsonl"
        )
        for line in dataset_path.read_text(encoding="utf-8").splitlines():
            payload = json.loads(line)
            expected_topics = payload["expected_topics"]
            self.assertGreaterEqual(len(expected_topics), 3, payload["id"])
            self.assertLessEqual(len(expected_topics), 5, payload["id"])


if __name__ == "__main__":
    unittest.main()
