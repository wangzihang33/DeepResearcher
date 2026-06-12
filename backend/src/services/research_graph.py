"""LangGraph workflow for multi-agent research orchestration."""

from __future__ import annotations

import operator
import re
from collections.abc import Callable, Iterator
from typing import Any, Optional

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from typing_extensions import Annotated, TypedDict

from models import (
    HandoffMessage,
    ResearchArtifact,
    SourceCard,
    SummaryState,
    SummaryStateOutput,
    TaskBoardItem,
    TodoItem,
)
from services.planner import PlanningService
from services.reporter import ReportingService


class ResearchGraphState(TypedDict, total=False):
    """Shared state exchanged by graph-level research agents."""

    research_topic: str
    summary_state: SummaryState
    todo_items: list[TodoItem]
    task_board: list[TaskBoardItem]
    artifacts: Annotated[list[ResearchArtifact], operator.add]
    handoff_messages: Annotated[list[HandoffMessage], operator.add]
    events: Annotated[list[dict[str, Any]], operator.add]
    report_markdown: str
    report_note_id: Optional[str]
    report_note_path: Optional[str]


class ResearchWorkerState(TypedDict, total=False):
    """State sent to one Researcher worker through LangGraph Send."""

    research_topic: str
    task: TodoItem
    board_item: TaskBoardItem
    artifacts: Annotated[list[ResearchArtifact], operator.add]
    handoff_messages: Annotated[list[HandoffMessage], operator.add]
    events: Annotated[list[dict[str, Any]], operator.add]


ExecuteTask = Callable[[SummaryState, TodoItem], None]
DrainToolEvents = Callable[[SummaryState, Optional[int]], list[dict[str, Any]]]
PersistReport = Callable[[SummaryState, str], dict[str, Any] | None]
SerializeTask = Callable[[TodoItem], dict[str, Any]]


class ResearchGraphWorkflow:
    """Supervisor-worker research workflow backed by LangGraph."""

    def __init__(
        self,
        *,
        planner: PlanningService,
        reporting: ReportingService,
        execute_task: ExecuteTask,
        drain_tool_events: DrainToolEvents,
        persist_report: PersistReport,
        serialize_task: SerializeTask,
    ) -> None:
        self._planner = planner
        self._reporting = reporting
        self._execute_task = execute_task
        self._drain_tool_events = drain_tool_events
        self._persist_report = persist_report
        self._serialize_task = serialize_task
        self._graph = self._build_graph()

    def run(self, topic: str) -> SummaryStateOutput:
        """Run the LangGraph workflow and return the final report."""

        final_state = self._graph.invoke({"research_topic": topic})
        return SummaryStateOutput(
            running_summary=final_state.get("report_markdown") or "",
            report_markdown=final_state.get("report_markdown") or "",
            todo_items=final_state.get("todo_items") or [],
        )

    def stream(self, topic: str) -> Iterator[dict[str, Any]]:
        """Stream graph node updates using the existing frontend event protocol."""

        yield {
            "type": "status",
            "message": "初始化 LangGraph 多 Agent 研究图",
        }

        for update in self._graph.stream(
            {"research_topic": topic},
            stream_mode="updates",
        ):
            for node_update in update.values():
                if not isinstance(node_update, dict):
                    continue
                for event in node_update.get("events") or []:
                    yield event

        yield {"type": "done"}

    def _build_graph(self):
        graph = StateGraph(ResearchGraphState)
        graph.add_node("planner", self._planner_node)
        graph.add_node("researcher", self._researcher_node)
        graph.add_node("compressor", self._compressor_node)
        graph.add_node("report_writer", self._report_writer_node)

        graph.add_edge(START, "planner")
        graph.add_conditional_edges("planner", self._assign_researchers, ["researcher"])
        graph.add_edge("researcher", "compressor")
        graph.add_edge("compressor", "report_writer")
        graph.add_edge("report_writer", END)
        return graph.compile()

    def _planner_node(self, state: ResearchGraphState) -> ResearchGraphState:
        topic = state.get("research_topic") or ""
        summary_state = SummaryState(research_topic=topic)
        todo_items = self._planner.plan_todo_list(summary_state)
        self._drain_tool_events(summary_state, 0)

        if not todo_items:
            todo_items = [self._planner.create_fallback_task(summary_state)]
            summary_state.todo_items = todo_items

        task_board = [
            TaskBoardItem(
                task_id=task.id,
                title=task.title,
                intent=task.intent,
                query=task.query,
                owner=f"researcher_{task.id}",
                status="pending",
            )
            for task in todo_items
        ]

        handoffs = [
            HandoffMessage(
                message_id=f"handoff-supervisor-researcher-{task.id}",
                from_agent="Supervisor",
                to_agent=f"Researcher-{task.id}",
                message_type="task_assignment",
                task_id=task.id,
                content=f"执行研究任务：{task.title}",
                payload={
                    "query": task.query,
                    "intent": task.intent,
                    "dependencies": [],
                },
            )
            for task in todo_items
        ]

        events: list[dict[str, Any]] = [
            {
                "type": "status",
                "message": f"Supervisor 已生成共享任务板：{len(todo_items)} 个研究任务",
            },
            {
                "type": "todo_list",
                "tasks": [self._serialize_task(task) for task in todo_items],
                "step": 0,
            },
            {
                "type": "status",
                "message": "已创建 ResearchArtifact 与 Handoff 通信协议",
            },
        ]

        return {
            "summary_state": summary_state,
            "todo_items": todo_items,
            "task_board": task_board,
            "handoff_messages": handoffs,
            "events": events,
        }

    def _assign_researchers(self, state: ResearchGraphState) -> list[Send]:
        board_by_task_id = {
            item.task_id: item for item in state.get("task_board", [])
        }
        sends: list[Send] = []
        for task in state.get("todo_items", []):
            board_item = board_by_task_id.get(task.id)
            if board_item is None:
                board_item = TaskBoardItem(
                    task_id=task.id,
                    title=task.title,
                    intent=task.intent,
                    query=task.query,
                )
            sends.append(
                Send(
                    "researcher",
                    {
                        "research_topic": state.get("research_topic") or "",
                        "task": task,
                        "board_item": board_item,
                    },
                )
            )
        return sends

    def _researcher_node(self, state: ResearchWorkerState) -> ResearchGraphState:
        task = state["task"]
        local_state = SummaryState(
            research_topic=state.get("research_topic") or "",
            todo_items=[task],
        )
        task.status = "in_progress"

        events: list[dict[str, Any]] = [
            {
                "type": "task_status",
                "task_id": task.id,
                "status": "in_progress",
                "title": task.title,
                "intent": task.intent,
                "note_id": task.note_id,
                "note_path": task.note_path,
            },
            {
                "type": "status",
                "task_id": task.id,
                "message": f"Researcher-{task.id} 接收任务并开始检索：{task.query}",
            },
        ]

        artifact: ResearchArtifact
        error_message: str | None = None
        try:
            self._execute_task(local_state, task)
            status = task.status
        except Exception as exc:  # pragma: no cover - defensive runtime guard
            status = "failed"
            error_message = str(exc)
            task.status = status
            task.summary = ""
            task.sources_summary = ""
            task.notices.append(error_message)

        artifact = self._artifact_from_task(task, status, error_message)

        if task.sources_summary:
            events.append(
                {
                    "type": "sources",
                    "task_id": task.id,
                    "latest_sources": task.sources_summary,
                    "sources_summary": task.sources_summary,
                    "note_id": task.note_id,
                    "note_path": task.note_path,
                }
            )

        if task.summary:
            events.append(
                {
                    "type": "task_summary_chunk",
                    "task_id": task.id,
                    "content": task.summary,
                    "note_id": task.note_id,
                    "note_path": task.note_path,
                }
            )

        events.append(
            {
                "type": "task_status",
                "task_id": task.id,
                "status": task.status,
                "summary": task.summary,
                "sources_summary": task.sources_summary,
                "note_id": task.note_id,
                "note_path": task.note_path,
            }
        )
        events.append(
            {
                "type": "status",
                "task_id": task.id,
                "message": f"Researcher-{task.id} 已发布 ResearchArtifact：{artifact.artifact_id}",
            }
        )

        return {
            "artifacts": [artifact],
            "handoff_messages": [
                HandoffMessage(
                    message_id=f"handoff-researcher-compressor-{task.id}",
                    from_agent=f"Researcher-{task.id}",
                    to_agent="Compressor",
                    message_type="research_artifact",
                    task_id=task.id,
                    content=f"提交任务 {task.id} 的结构化研究产物",
                    payload={
                        "artifact_id": artifact.artifact_id,
                        "status": artifact.status,
                        "evidence_count": len(artifact.evidence),
                        "confidence": artifact.confidence,
                    },
                )
            ],
            "events": events,
        }

    def _compressor_node(self, state: ResearchGraphState) -> ResearchGraphState:
        artifacts = sorted(
            state.get("artifacts", []),
            key=lambda artifact: artifact.task_id,
        )
        tasks_by_id = {task.id: task for task in state.get("todo_items", [])}

        for artifact in artifacts:
            task = tasks_by_id.get(artifact.task_id)
            if task is None:
                continue
            task.status = artifact.status
            task.summary = artifact.summary
            task.sources_summary = artifact.sources_summary
            task.notices = artifact.notices
            task.note_id = artifact.note_id
            task.note_path = artifact.note_path

        todo_items = [tasks_by_id[key] for key in sorted(tasks_by_id)]
        summary_state = state.get("summary_state") or SummaryState(
            research_topic=state.get("research_topic") or ""
        )
        summary_state.todo_items = todo_items
        summary_state.sources_gathered = [
            artifact.sources_summary for artifact in artifacts if artifact.sources_summary
        ]
        summary_state.web_research_results = [
            artifact.summary for artifact in artifacts if artifact.summary
        ]
        summary_state.research_loop_count = len(artifacts)

        board = self._merge_task_board(state.get("task_board", []), artifacts)
        evidence_count = sum(len(artifact.evidence) for artifact in artifacts)
        message = (
            f"Compressor 已合并 {len(artifacts)} 个 ResearchArtifact，"
            f"沉淀 {evidence_count} 条来源证据"
        )

        return {
            "summary_state": summary_state,
            "todo_items": todo_items,
            "task_board": board,
            "handoff_messages": [
                HandoffMessage(
                    message_id="handoff-compressor-writer",
                    from_agent="Compressor",
                    to_agent="ReportWriter",
                    message_type="compressed_context",
                    content="提交已合并的任务总结和来源证据",
                    payload={
                        "artifact_count": len(artifacts),
                        "evidence_count": evidence_count,
                    },
                )
            ],
            "events": [{"type": "status", "message": message}],
        }

    def _report_writer_node(self, state: ResearchGraphState) -> ResearchGraphState:
        summary_state = state.get("summary_state") or SummaryState(
            research_topic=state.get("research_topic") or ""
        )
        report = self._reporting.generate_report(summary_state)
        tool_events = self._drain_tool_events(summary_state, None)
        summary_state.structured_report = report
        summary_state.running_summary = report

        note_event = self._persist_report(summary_state, report)

        events: list[dict[str, Any]] = [
            {
                "type": "status",
                "message": "ReportWriter 已消费结构化研究产物并生成最终报告",
            }
        ]
        events.extend(tool_events)
        if note_event:
            events.append(note_event)
        events.append(
            {
                "type": "final_report",
                "report": report,
                "note_id": summary_state.report_note_id,
                "note_path": summary_state.report_note_path,
            }
        )

        return {
            "summary_state": summary_state,
            "report_markdown": report,
            "report_note_id": summary_state.report_note_id,
            "report_note_path": summary_state.report_note_path,
            "events": events,
        }

    def _artifact_from_task(
        self,
        task: TodoItem,
        status: str,
        error_message: str | None,
    ) -> ResearchArtifact:
        evidence = self._parse_source_cards(task.sources_summary or "")
        return ResearchArtifact(
            artifact_id=f"artifact-task-{task.id}",
            task_id=task.id,
            producer=f"Researcher-{task.id}",
            status=status,
            summary=task.summary or "",
            sources_summary=task.sources_summary or "",
            findings=self._extract_findings(task.summary or ""),
            evidence=evidence,
            confidence=self._estimate_confidence(status, task.summary, evidence),
            open_questions=[] if status == "completed" else ["需要补充检索或人工复核"],
            notices=list(task.notices or []),
            note_id=task.note_id,
            note_path=task.note_path,
            error=error_message,
        )

    @staticmethod
    def _parse_source_cards(sources_summary: str) -> list[SourceCard]:
        cards: list[SourceCard] = []
        for raw_line in sources_summary.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("*") and " : " in line:
                title, url = line.lstrip("* ").split(" : ", 1)
                cards.append(SourceCard(title=title.strip(), url=url.strip()))
                continue
            if line.lower().startswith("url:") and cards:
                cards[-1].url = line.split(":", 1)[1].strip()
                continue
            if line.lower().startswith("source:") or line.startswith("信息来源:"):
                title = line.split(":", 1)[1].strip() if ":" in line else line
                cards.append(SourceCard(title=title))
                continue
            if cards and not cards[-1].snippet:
                cards[-1].snippet = line
        return cards

    @staticmethod
    def _extract_findings(summary: str, limit: int = 5) -> list[str]:
        findings: list[str] = []
        for raw_line in summary.splitlines():
            line = raw_line.strip().lstrip("-*0123456789.、 ")
            if len(line) >= 12:
                findings.append(line)
            if len(findings) >= limit:
                break
        if findings:
            return findings
        sentence_parts = re.split(r"[。！？.!?]\s*", summary)
        return [part.strip() for part in sentence_parts if len(part.strip()) >= 12][:limit]

    @staticmethod
    def _estimate_confidence(
        status: str,
        summary: str | None,
        evidence: list[SourceCard],
    ) -> float:
        if status != "completed":
            return 0.0
        score = 0.45
        if summary and len(summary.strip()) >= 80:
            score += 0.25
        if evidence:
            score += min(0.25, len(evidence) * 0.05)
        return round(min(score, 0.95), 2)

    @staticmethod
    def _merge_task_board(
        board: list[TaskBoardItem],
        artifacts: list[ResearchArtifact],
    ) -> list[TaskBoardItem]:
        artifacts_by_task = {artifact.task_id: artifact for artifact in artifacts}
        merged: list[TaskBoardItem] = []
        for item in board:
            artifact = artifacts_by_task.get(item.task_id)
            if artifact:
                item.status = artifact.status
                item.artifact_id = artifact.artifact_id
                item.note_id = artifact.note_id
                item.error = artifact.error
            merged.append(item)
        return merged
