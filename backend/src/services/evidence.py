"""Evidence graph construction and citation verification helpers."""

from __future__ import annotations

import math
import re
from dataclasses import replace
from typing import Iterable

from models import Claim, EvidenceGraph, EvidenceLink, ResearchArtifact, SourceCard


class EvidenceGraphBuilder:
    """Build and verify claim-source evidence relationships."""

    def __init__(
        self,
        *,
        supported_threshold: float = 0.18,
        partial_threshold: float = 0.08,
        max_claims_per_task: int = 6,
        max_sources_per_claim: int = 3,
    ) -> None:
        self.supported_threshold = supported_threshold
        self.partial_threshold = partial_threshold
        self.max_claims_per_task = max_claims_per_task
        self.max_sources_per_claim = max_sources_per_claim

    def build(self, artifacts: Iterable[ResearchArtifact]) -> EvidenceGraph:
        """Create an EvidenceGraph from researcher artifacts."""

        artifact_list = list(artifacts)
        sources = self._collect_sources(artifact_list)
        claims = self._collect_claims(artifact_list)
        links: list[EvidenceLink] = []

        for claim in claims:
            ranked_sources = self._rank_sources(claim, sources)
            selected = [
                (source, score)
                for source, score in ranked_sources
                if score >= self.partial_threshold
            ][: self.max_sources_per_claim]
            if not selected:
                selected = self._fallback_task_sources(claim, sources)

            claim.source_ids = [source.source_id for source, _ in selected]
            best_score = selected[0][1] if selected else 0.0

            if best_score >= self.supported_threshold:
                claim.support_status = "supported"
                claim.reason = "关键结论与来源内容存在明确词项重合。"
            elif best_score >= self.partial_threshold:
                claim.support_status = "partial"
                claim.reason = "关键结论存在部分来源线索，但支撑不够充分。"
            else:
                claim.support_status = "unsupported"
                claim.reason = "未在当前来源中找到足够支撑。"

            claim.confidence = round(min(best_score, 0.99), 3)

            for source, score in selected:
                links.append(
                    EvidenceLink(
                        claim_id=claim.claim_id,
                        source_id=source.source_id,
                        relation=(
                            "supports"
                            if score >= self.supported_threshold
                            else "partially_supports"
                        ),
                        snippet=self._source_snippet(source),
                        score=round(score, 3),
                    )
                )

        metrics = self._metrics(claims, sources)
        return EvidenceGraph(claims=claims, sources=sources, links=links, metrics=metrics)

    def format_verified_claims(self, graph: EvidenceGraph) -> str:
        """Render citation verification results for downstream report writing."""

        if not graph.claims:
            return "暂无可校验结论。"

        source_by_id = {source.source_id: source for source in graph.sources}
        lines = [
            "引用校验结果：",
            (
                f"- claim_count={graph.metrics.get('claim_count', 0)}, "
                f"supported={graph.metrics.get('supported_claim_count', 0)}, "
                f"partial={graph.metrics.get('partial_claim_count', 0)}, "
                f"unsupported={graph.metrics.get('unsupported_claim_count', 0)}, "
                f"citation_coverage={graph.metrics.get('citation_coverage', 0):.2f}"
            ),
        ]

        for claim in graph.claims:
            source_refs = []
            for source_id in claim.source_ids:
                source = source_by_id.get(source_id)
                if not source:
                    continue
                label = source.title or source.url
                source_refs.append(
                    f"{source_id}: {label} ({source.url})"
                    if source.url
                    else f"{source_id}: {label}"
                )

            refs = "；".join(source_refs) if source_refs else "暂无匹配来源"
            lines.append(
                f"- [{claim.claim_id}][{claim.support_status}] {claim.text} "
                f"(confidence={claim.confidence:.2f}; sources={refs})"
            )

        return "\n".join(lines)

    def format_audit_markdown(self, graph: EvidenceGraph) -> str:
        """Build a deterministic claim-to-source audit appendix."""

        metrics = graph.metrics
        lines = [
            "## 引用校验摘要",
            "",
            "| 指标 | 数值 |",
            "| --- | ---: |",
            f"| 待校验结论 | {metrics.get('claim_count', 0)} |",
            f"| 来源证据 | {metrics.get('source_count', 0)} |",
            f"| 已支撑结论 | {metrics.get('supported_claim_count', 0)} |",
            f"| 部分支撑结论 | {metrics.get('partial_claim_count', 0)} |",
            f"| 无支撑结论 | {metrics.get('unsupported_claim_count', 0)} |",
            f"| 引用覆盖率 | {metrics.get('citation_coverage', 0):.2%} |",
            f"| 无支撑结论率 | {metrics.get('unsupported_claim_rate', 0):.2%} |",
            "",
            "### Claim 与来源映射",
            "",
        ]

        source_by_id = {source.source_id: source for source in graph.sources}
        if not graph.claims:
            lines.append("暂无可校验结论。")

        for claim in graph.claims:
            refs: list[str] = []
            for source_id in claim.source_ids:
                source = source_by_id.get(source_id)
                if source is None:
                    continue
                label = source.title or source.url or source_id
                if source.url:
                    refs.append(f"[{source_id}] [{label}]({source.url})")
                else:
                    refs.append(f"[{source_id}] {label}")

            source_text = "；".join(refs) if refs else "暂无匹配来源"
            lines.append(
                f"- **[{claim.claim_id}] {claim.support_status}** "
                f"(confidence={claim.confidence:.2f})：{claim.text}  "
            )
            lines.append(f"  证据：{source_text}")

        lines.extend(["", "### 去重后的来源", ""])
        if not graph.sources:
            lines.append("暂无来源。")
        for source in graph.sources:
            label = source.title or source.url or source.source_id
            if source.url:
                lines.append(f"- **[{source.source_id}]** [{label}]({source.url})")
            else:
                lines.append(f"- **[{source.source_id}]** {label}")

        lines.extend(
            [
                "",
                "> 校验状态来自确定性词项匹配，用于引用审计和风险提示，不等同于人工事实核查。",
            ]
        )
        return "\n".join(lines)

    def _collect_sources(self, artifacts: list[ResearchArtifact]) -> list[SourceCard]:
        unique: dict[str, SourceCard] = {}
        for artifact in artifacts:
            for source in artifact.evidence:
                key = source.url or source.title or source.snippet
                if not key:
                    continue
                if key in unique:
                    existing = unique[key]
                    if not existing.snippet and source.snippet:
                        existing.snippet = source.snippet
                    if not existing.raw and source.raw:
                        existing.raw = source.raw
                    if existing.task_id is None:
                        existing.task_id = artifact.task_id
                    continue
                copied = replace(source)
                if copied.task_id is None:
                    copied.task_id = artifact.task_id
                unique[key] = copied

        sources: list[SourceCard] = []
        for index, source in enumerate(unique.values(), start=1):
            source.source_id = source.source_id or f"S{index}"
            sources.append(source)
        return sources

    def _collect_claims(self, artifacts: list[ResearchArtifact]) -> list[Claim]:
        claims: list[Claim] = []
        seen: set[str] = set()

        for artifact in artifacts:
            candidates = list(artifact.findings)
            if not candidates:
                candidates = self._split_summary_into_claims(artifact.summary)

            count = 0
            for text in candidates:
                normalized = self._normalize_claim(text)
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                count += 1
                claims.append(
                    Claim(
                        claim_id=f"C{artifact.task_id}-{count}",
                        task_id=artifact.task_id,
                        text=normalized,
                    )
                )
                if count >= self.max_claims_per_task:
                    break

        return claims

    @staticmethod
    def _split_summary_into_claims(summary: str) -> list[str]:
        if not summary:
            return []
        lines = [
            line.strip().lstrip("-*0123456789.、 ")
            for line in summary.splitlines()
            if line.strip()
        ]
        if lines:
            return lines
        return [part.strip() for part in re.split(r"[。！？.!?]\s*", summary)]

    @staticmethod
    def _normalize_claim(text: str) -> str:
        text = re.sub(r"\s+", " ", text or "").strip()
        text = text.strip("-*0123456789.、 ")
        text = re.sub(r"^\*\*([^*]{1,24})\*\*[：:]\s*", "", text)
        text = re.sub(
            r"^(含义与价值|拓展分析|原理|应用场景|优缺点|工程实践|数据支撑|"
            r"性能特征|历史演变|对比|推荐架构|具体建议|风险提示|未来展望)[：:]\s*",
            "",
            text,
        )
        text = text.replace("**", "").strip()
        if len(text) < 12:
            return ""
        if text in {"暂无可用信息", "暂无相关信息"}:
            return ""
        return text

    def _rank_sources(
        self,
        claim: Claim,
        sources: list[SourceCard],
    ) -> list[tuple[SourceCard, float]]:
        claim_text = claim.text
        claim_tokens = self._tokenize(claim_text)
        if not claim_tokens:
            return []

        ranked: list[tuple[SourceCard, float]] = []
        for source in sources:
            source_text = " ".join(
                part for part in [source.title, source.snippet, source.raw] if part
            )
            source_tokens = self._tokenize(source_text)
            if not source_tokens:
                continue

            overlap = claim_tokens & source_tokens
            score = len(overlap) / math.sqrt(len(claim_tokens) * len(source_tokens))
            if claim_text and claim_text in source_text:
                score = max(score, 0.95)
            if source.title and any(token in source.title.lower() for token in claim_tokens):
                score += 0.03
            if source.task_id == claim.task_id:
                score += 0.02
            ranked.append((source, min(score, 0.99)))

        return sorted(ranked, key=lambda item: item[1], reverse=True)

    def _fallback_task_sources(
        self,
        claim: Claim,
        sources: list[SourceCard],
    ) -> list[tuple[SourceCard, float]]:
        """Attach same-task sources when snippets are too thin for lexical matching."""

        task_sources = [
            source for source in sources if source.task_id == claim.task_id
        ][: self.max_sources_per_claim]
        return [(source, self.partial_threshold) for source in task_sources]

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        text = (text or "").lower()
        ascii_tokens = {
            token
            for token in re.findall(r"[a-z0-9][a-z0-9_-]{1,}", text)
            if token not in {"http", "https", "www", "com", "html"}
        }
        chinese_chars = re.findall(r"[\u4e00-\u9fff]", text)
        chinese_bigrams = {
            "".join(chinese_chars[index : index + 2])
            for index in range(max(0, len(chinese_chars) - 1))
        }
        return ascii_tokens | chinese_bigrams

    @staticmethod
    def _source_snippet(source: SourceCard) -> str:
        text = source.snippet or source.raw or source.title or source.url
        text = re.sub(r"\s+", " ", text or "").strip()
        return text[:280]

    @staticmethod
    def _metrics(claims: list[Claim], sources: list[SourceCard]) -> dict[str, float | int]:
        claim_count = len(claims)
        supported = sum(1 for claim in claims if claim.support_status == "supported")
        partial = sum(1 for claim in claims if claim.support_status == "partial")
        unsupported = sum(1 for claim in claims if claim.support_status == "unsupported")
        coverage = (supported + partial) / claim_count if claim_count else 0.0
        unsupported_rate = unsupported / claim_count if claim_count else 0.0
        return {
            "claim_count": claim_count,
            "source_count": len(sources),
            "supported_claim_count": supported,
            "partial_claim_count": partial,
            "unsupported_claim_count": unsupported,
            "citation_coverage": round(coverage, 4),
            "unsupported_claim_rate": round(unsupported_rate, 4),
        }
