"""State models used by the deep research workflow."""

import operator
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from typing_extensions import Annotated


@dataclass(kw_only=True)
class TodoItem:
    """单个待办任务项。"""

    id: int
    title: str
    intent: str
    query: str
    status: str = field(default="pending")
    summary: Optional[str] = field(default=None)
    sources_summary: Optional[str] = field(default=None)
    notices: list[str] = field(default_factory=list)
    note_id: Optional[str] = field(default=None)
    note_path: Optional[str] = field(default=None)
    stream_token: Optional[str] = field(default=None)


@dataclass(kw_only=True)
class SummaryState:
    research_topic: str = field(default=None)  # Report topic
    search_query: str = field(default=None)  # Deprecated placeholder
    web_research_results: Annotated[list, operator.add] = field(default_factory=list)
    sources_gathered: Annotated[list, operator.add] = field(default_factory=list)
    research_loop_count: int = field(default=0)  # Research loop count
    running_summary: str = field(default=None)  # Legacy summary field
    todo_items: Annotated[list, operator.add] = field(default_factory=list)
    structured_report: Optional[str] = field(default=None)
    report_note_id: Optional[str] = field(default=None)
    report_note_path: Optional[str] = field(default=None)


@dataclass(kw_only=True)
class SummaryStateInput:
    research_topic: str = field(default=None)  # Report topic


@dataclass(kw_only=True)
class SummaryStateOutput:
    running_summary: str = field(default=None)  # Backward-compatible文本
    report_markdown: Optional[str] = field(default=None)
    todo_items: List[TodoItem] = field(default_factory=list)


@dataclass(kw_only=True)
class TaskBoardItem:
    """Shared task-board record used by the multi-agent research graph."""

    task_id: int
    title: str
    intent: str
    query: str
    owner: str = "researcher"
    status: str = "pending"
    dependencies: List[int] = field(default_factory=list)
    retry_count: int = 0
    artifact_id: Optional[str] = None
    note_id: Optional[str] = None
    error: Optional[str] = None


@dataclass(kw_only=True)
class SourceCard:
    """Normalized source evidence passed between research agents."""

    title: str = ""
    url: str = ""
    snippet: str = ""
    raw: str = ""


@dataclass(kw_only=True)
class ResearchArtifact:
    """Structured output produced by a Researcher worker."""

    artifact_id: str
    task_id: int
    producer: str
    status: str
    summary: str = ""
    sources_summary: str = ""
    findings: List[str] = field(default_factory=list)
    evidence: List[SourceCard] = field(default_factory=list)
    confidence: float = 0.0
    open_questions: List[str] = field(default_factory=list)
    notices: List[str] = field(default_factory=list)
    note_id: Optional[str] = None
    note_path: Optional[str] = None
    backend: Optional[str] = None
    error: Optional[str] = None


@dataclass(kw_only=True)
class HandoffMessage:
    """Structured communication record between graph agents."""

    message_id: str
    from_agent: str
    to_agent: str
    message_type: str
    task_id: Optional[int] = None
    content: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
