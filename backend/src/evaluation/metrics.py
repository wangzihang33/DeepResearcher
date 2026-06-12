"""Rule-based quality metrics for deep research reports."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse


DEFAULT_SOURCE_QUALITY_KEYWORDS = {
    "official",
    "docs",
    "documentation",
    "github",
    "gitlab",
    "arxiv",
    "paper",
    "research",
    "benchmark",
    "developer",
    "developers",
    "edu",
    "gov",
    "whitepaper",
    "standards",
}


@dataclass(kw_only=True)
class ExpectedTopic:
    """A manually labeled research point and its matching aliases."""

    name: str
    aliases: list[str] = field(default_factory=list)


@dataclass(kw_only=True)
class EvalCase:
    """One evaluation case from the JSONL dataset."""

    case_id: str
    category: str
    query: str
    expected_topics: list[ExpectedTopic]
    preferred_source_keywords: list[str] = field(default_factory=list)
    report_path: str = ""

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EvalCase":
        topics = []
        for item in payload.get("expected_topics") or []:
            if isinstance(item, str):
                topics.append(ExpectedTopic(name=item, aliases=[item]))
            elif isinstance(item, dict):
                name = str(item.get("name") or "").strip()
                aliases = [
                    str(alias).strip()
                    for alias in item.get("aliases", [])
                    if str(alias).strip()
                ]
                if name:
                    topics.append(ExpectedTopic(name=name, aliases=aliases or [name]))

        return cls(
            case_id=str(payload.get("id") or "").strip(),
            category=str(payload.get("category") or "").strip(),
            query=str(payload.get("query") or "").strip(),
            expected_topics=topics,
            preferred_source_keywords=[
                str(keyword).strip().lower()
                for keyword in payload.get("preferred_source_keywords", [])
                if str(keyword).strip()
            ],
            report_path=str(payload.get("report_path") or "").strip(),
        )


@dataclass(kw_only=True)
class SourceRef:
    """A source reference parsed from a generated report."""

    title: str
    url: str
    domain: str


@dataclass(kw_only=True)
class EvalResult:
    """Computed metrics for one evaluation case."""

    case_id: str
    category: str
    query: str
    task_coverage: float
    citation_coverage: float
    source_quality: float
    unsupported_claim_rate: float
    covered_topics: list[str]
    missing_topics: list[str]
    source_count: int
    trusted_source_count: int
    report_path: str = ""
    error: str = ""


def evaluate_report(
    case: EvalCase,
    report_markdown: str,
    *,
    report_path: str = "",
    error: str = "",
) -> EvalResult:
    """Compute all V1 rule-based quality metrics for a report."""

    topic_match_text = strip_report_boilerplate(report_markdown)
    covered_topics, missing_topics = match_expected_topics(
        topic_match_text,
        case.expected_topics,
    )
    task_coverage = safe_ratio(len(covered_topics), len(case.expected_topics))

    citation_coverage = parse_percent_metric(report_markdown, "引用覆盖率")
    unsupported_claim_rate = parse_percent_metric(report_markdown, "无支撑结论率")

    sources = extract_sources(report_markdown)
    trusted_sources = [
        source
        for source in sources
        if is_trusted_source(source, case.preferred_source_keywords)
    ]
    source_quality = safe_ratio(len(trusted_sources), len(sources))

    return EvalResult(
        case_id=case.case_id,
        category=case.category,
        query=case.query,
        task_coverage=round(task_coverage, 4),
        citation_coverage=round(citation_coverage, 4),
        source_quality=round(source_quality, 4),
        unsupported_claim_rate=round(unsupported_claim_rate, 4),
        covered_topics=covered_topics,
        missing_topics=missing_topics,
        source_count=len(sources),
        trusted_source_count=len(trusted_sources),
        report_path=report_path,
        error=error,
    )


def match_expected_topics(
    text: str,
    expected_topics: list[ExpectedTopic],
) -> tuple[list[str], list[str]]:
    """Match manually labeled research points against report text."""

    normalized_text = normalize_text(text)
    covered: list[str] = []
    missing: list[str] = []

    for topic in expected_topics:
        aliases = topic.aliases or [topic.name]
        matched = any(normalize_text(alias) in normalized_text for alias in aliases)
        if matched:
            covered.append(topic.name)
        else:
            missing.append(topic.name)

    return covered, missing


def parse_percent_metric(markdown: str, metric_name: str) -> float:
    """Parse a percentage metric from the report audit table."""

    patterns = [
        rf"\|\s*{re.escape(metric_name)}\s*\|\s*([0-9]+(?:\.[0-9]+)?)%\s*\|",
        rf"{re.escape(metric_name)}[：:\s]+([0-9]+(?:\.[0-9]+)?)%",
    ]
    for pattern in patterns:
        match = re.search(pattern, markdown)
        if match:
            return float(match.group(1)) / 100
    return 0.0


def extract_sources(markdown: str) -> list[SourceRef]:
    """Extract unique source links from a Markdown report."""

    found: dict[str, SourceRef] = {}
    for title, url in re.findall(r"\[([^\]]+)\]\((https?://[^)]+)\)", markdown):
        clean_url = url.strip()
        domain = urlparse(clean_url).netloc.lower()
        if not domain:
            continue
        found.setdefault(
            clean_url,
            SourceRef(
                title=re.sub(r"\s+", " ", title).strip(),
                url=clean_url,
                domain=domain,
            ),
        )
    return list(found.values())


def is_trusted_source(
    source: SourceRef,
    preferred_keywords: list[str] | None = None,
) -> bool:
    """Classify whether a source looks like a high-quality reference."""

    keywords = set(DEFAULT_SOURCE_QUALITY_KEYWORDS)
    keywords.update(keyword.lower() for keyword in preferred_keywords or [])

    haystack = f"{source.title} {source.url} {source.domain}".lower()
    if any(keyword and keyword in haystack for keyword in keywords):
        return True

    domain = source.domain.removeprefix("www.")
    return bool(
        domain.endswith(".edu")
        or domain.endswith(".gov")
        or domain.endswith(".org")
        or domain in {"github.com", "arxiv.org"}
    )


def safe_ratio(numerator: int, denominator: int) -> float:
    """Return a safe ratio with zero-denominator protection."""

    return numerator / denominator if denominator else 0.0


def normalize_text(text: str) -> str:
    """Normalize mixed Chinese/English text for deterministic matching."""

    text = (text or "").lower()
    text = re.sub(r"\s+", "", text)
    return text


def strip_report_boilerplate(markdown: str) -> str:
    """Remove generated report title/frontmatter before topic coverage matching."""

    lines = (markdown or "").splitlines()
    if lines and lines[0].strip() == "---":
        for index in range(1, len(lines)):
            if lines[index].strip() == "---":
                lines = lines[index + 1 :]
                break

    filtered: list[str] = []
    for index, line in enumerate(lines):
        stripped = line.strip()
        if index < 8 and stripped.startswith("# "):
            continue
        filtered.append(line)

    return "\n".join(filtered)
