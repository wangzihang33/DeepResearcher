"""Tests for planner output parsing and repair."""

from __future__ import annotations

import unittest

from config import Configuration
from models import SummaryState
from services.planner import PlanningService


class FakePlannerAgent:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.prompts: list[str] = []
        self.history_cleared = False

    def run(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.responses.pop(0)

    def clear_history(self) -> None:
        self.history_cleared = True


class PlanningServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = Configuration(strip_thinking_tokens=True)

    def test_extracts_json_tasks(self) -> None:
        response = """{
          "tasks": [
            {"title": "架构对比", "intent": "比较编排模型", "query": "LangGraph AutoGen CrewAI architecture"},
            {"title": "状态管理", "intent": "比较状态机制", "query": "LangGraph AutoGen CrewAI state management"},
            {"title": "部署选型", "intent": "比较生产部署", "query": "LangGraph AutoGen CrewAI production deployment"}
          ]
        }"""
        service = PlanningService(FakePlannerAgent([response]), self.config)

        tasks = service.plan_todo_list(SummaryState(research_topic="框架对比"))

        self.assertEqual(3, len(tasks))
        self.assertEqual("状态管理", tasks[1].title)

    def test_extracts_markdown_table_tasks(self) -> None:
        response = """
| 序号 | 任务 | 意图 | 查询 |
| --- | --- | --- | --- |
| 1 | **架构对比** | 比较编排模型 | `LangGraph AutoGen CrewAI architecture` |
| 2 | **状态管理** | 比较状态机制 | `LangGraph AutoGen CrewAI state management` |
| 3 | **并行执行** | 比较并行能力 | `LangGraph AutoGen CrewAI parallel execution` |
| 4 | **部署选型** | 比较生产部署 | `LangGraph AutoGen CrewAI production deployment` |
"""
        service = PlanningService(FakePlannerAgent([response]), self.config)

        tasks = service.plan_todo_list(SummaryState(research_topic="框架对比"))

        self.assertEqual(4, len(tasks))
        self.assertEqual("架构对比", tasks[0].title)
        self.assertEqual(
            "LangGraph AutoGen CrewAI production deployment",
            tasks[3].query,
        )

    def test_repairs_output_when_too_few_tasks_are_parsed(self) -> None:
        malformed = "我已经完成规划，但没有按要求输出任务。"
        repaired = """{
          "tasks": [
            {"title": "任务一", "intent": "意图一", "query": "查询一"},
            {"title": "任务二", "intent": "意图二", "query": "查询二"},
            {"title": "任务三", "intent": "意图三", "query": "查询三"}
          ]
        }"""
        agent = FakePlannerAgent([malformed, repaired])
        service = PlanningService(agent, self.config)

        tasks = service.plan_todo_list(SummaryState(research_topic="复杂主题"))

        self.assertEqual(3, len(tasks))
        self.assertEqual(2, len(agent.prompts))
        self.assertTrue(agent.history_cleared)


if __name__ == "__main__":
    unittest.main()
