"""Service responsible for converting the research topic into actionable tasks."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, List, Optional

from hello_agents import ToolAwareSimpleAgent

from models import SummaryState, TodoItem
from config import Configuration
from prompts import get_current_date, todo_planner_instructions
from utils import strip_thinking_tokens

logger = logging.getLogger(__name__)

TOOL_CALL_PATTERN = re.compile(
    r"\[TOOL_CALL:(?P<tool>[^:]+):(?P<body>[^\]]+)\]",
    re.IGNORECASE,
)

class PlanningService:
    """Wraps the planner agent to produce structured TODO items."""

    def __init__(self, planner_agent: ToolAwareSimpleAgent, config: Configuration) -> None:
        self._agent = planner_agent
        self._config = config

    def plan_todo_list(self, state: SummaryState) -> List[TodoItem]:
        """Ask the planner agent to break the topic into actionable tasks."""

        prompt = todo_planner_instructions.format(
            current_date=get_current_date(),
            research_topic=state.research_topic,
        )

        try:
            response = self._agent.run(prompt)
            logger.info("Planner raw output (truncated): %s", response[:500])
            tasks_payload = self._extract_tasks(response)

            if len(tasks_payload) < 3:
                logger.warning(
                    "Planner output yielded %d task(s); requesting JSON repair",
                    len(tasks_payload),
                )
                repaired_response = self._agent.run(
                    self._build_repair_prompt(response, state.research_topic)
                )
                logger.info(
                    "Planner repaired output (truncated): %s",
                    repaired_response[:500],
                )
                repaired_tasks = self._extract_tasks(repaired_response)
                if len(repaired_tasks) > len(tasks_payload):
                    tasks_payload = repaired_tasks
        finally:
            self._agent.clear_history()

        tasks_payload = self._normalize_tasks(tasks_payload)[:5]
        todo_items: List[TodoItem] = []

        for idx, item in enumerate(tasks_payload, start=1):
            title = str(item.get("title") or f"任务{idx}").strip()
            intent = str(item.get("intent") or "聚焦主题的关键问题").strip()
            query = str(item.get("query") or state.research_topic).strip()

            if not query:
                query = state.research_topic

            task = TodoItem(
                id=idx,
                title=title,
                intent=intent,
                query=query,
            )
            todo_items.append(task)

        state.todo_items = todo_items

        titles = [task.title for task in todo_items]
        logger.info("Planner produced %d tasks: %s", len(todo_items), titles)
        return todo_items

    @staticmethod
    def create_fallback_task(state: SummaryState) -> TodoItem:
        """Create a minimal fallback task when planning failed."""

        return TodoItem(
            id=1,
            title="基础背景梳理",
            intent="收集主题的核心背景与最新动态",
            query=f"{state.research_topic} 最新进展" if state.research_topic else "基础背景梳理",
        )

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------
    def _extract_tasks(self, raw_response: str) -> List[dict[str, Any]]:
        """Parse planner output into a list of task dictionaries."""

        text = raw_response.strip()
        if self._config.strip_thinking_tokens:
            text = strip_thinking_tokens(text)

        json_payload = self._extract_json_payload(text)
        tasks: List[dict[str, Any]] = []

        if isinstance(json_payload, dict):
            candidate = json_payload.get("tasks")
            if isinstance(candidate, list):
                for item in candidate:
                    if isinstance(item, dict):
                        tasks.append(item)
        elif isinstance(json_payload, list):
            for item in json_payload:
                if isinstance(item, dict):
                    tasks.append(item)

        if not tasks:
            tool_payload = self._extract_tool_payload(text)
            if tool_payload and isinstance(tool_payload.get("tasks"), list):
                for item in tool_payload["tasks"]:
                    if isinstance(item, dict):
                        tasks.append(item)

        if not tasks:
            tasks = self._extract_markdown_table(text)

        return tasks

    @staticmethod
    def _normalize_tasks(tasks: List[dict[str, Any]]) -> List[dict[str, str]]:
        """Clean task fields, remove duplicates, and discard unusable rows."""

        normalized: List[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()

        for item in tasks:
            title = PlanningService._clean_markdown(str(item.get("title") or ""))
            intent = PlanningService._clean_markdown(str(item.get("intent") or ""))
            query = PlanningService._clean_markdown(str(item.get("query") or ""))
            if not title or not query:
                continue

            key = (title.casefold(), query.casefold())
            if key in seen:
                continue
            seen.add(key)
            normalized.append(
                {
                    "title": title,
                    "intent": intent or "聚焦主题的关键问题",
                    "query": query,
                }
            )

        return normalized

    @staticmethod
    def _build_repair_prompt(raw_response: str, research_topic: str) -> str:
        """Ask the planner to convert a malformed plan into the required schema."""

        return f"""
你刚才已经完成任务规划，但最终输出未满足结构化协议。请将全部规划结果重新整理为 3~5 个互补任务。

研究主题：{research_topic}

原始规划：
{raw_response}

只输出合法 JSON，不要调用工具，不要输出解释、Markdown 或代码围栏：
{{
  "tasks": [
    {{
      "title": "任务名称",
      "intent": "任务要解决的核心问题",
      "query": "可直接执行的网络检索关键词"
    }}
  ]
}}
""".strip()

    @staticmethod
    def _extract_markdown_table(text: str) -> List[dict[str, Any]]:
        """Recover task rows when the model returns a Markdown table."""

        tasks: List[dict[str, Any]] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line.startswith("|") or line.count("|") < 4:
                continue

            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) < 4:
                continue

            first_cell = PlanningService._clean_markdown(cells[0])
            if not re.fullmatch(r"\d+[.、]?", first_cell):
                continue

            title = PlanningService._clean_markdown(cells[1])
            intent = PlanningService._clean_markdown(cells[2])
            query = PlanningService._clean_markdown(" | ".join(cells[3:]))
            if title and query:
                tasks.append({"title": title, "intent": intent, "query": query})

        return tasks

    @staticmethod
    def _clean_markdown(value: str) -> str:
        """Remove common Markdown decoration from a task field."""

        value = value.strip()
        value = re.sub(r"^`+|`+$", "", value)
        value = re.sub(r"^(?:\*\*|__)(.*?)(?:\*\*|__)$", r"\1", value)
        value = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", value)
        return re.sub(r"\s+", " ", value).strip()

    def _extract_json_payload(self, text: str) -> Optional[dict[str, Any] | list]:
        """Try to locate and parse a JSON object or array from the text."""

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = text[start : end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            candidate = text[start : end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                return None

        return None

    def _extract_tool_payload(self, text: str) -> Optional[dict[str, Any]]:
        """Parse the first TOOL_CALL expression in the output."""

        match = TOOL_CALL_PATTERN.search(text)
        if not match:
            return None

        body = match.group("body")

        try:
            payload = json.loads(body)
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            pass

        parts = [segment.strip() for segment in body.split(",") if segment.strip()]
        payload: dict[str, Any] = {}
        for part in parts:
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            payload[key.strip()] = value.strip().strip('"').strip("'")

        return payload or None
