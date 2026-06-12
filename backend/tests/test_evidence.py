"""Tests for deterministic evidence graph rendering."""

from __future__ import annotations

import unittest

from models import ResearchArtifact, SourceCard
from services.evidence import EvidenceGraphBuilder


class EvidenceGraphBuilderTests(unittest.TestCase):
    def test_audit_markdown_contains_claim_source_mapping_and_metrics(self) -> None:
        artifact = ResearchArtifact(
            artifact_id="a1",
            task_id=1,
            producer="Researcher-1",
            status="completed",
            findings=["LangGraph 使用显式状态图管理多 Agent 工作流"],
            evidence=[
                SourceCard(
                    title="LangGraph 官方文档",
                    url="https://docs.langchain.com/oss/python/langgraph/overview",
                    snippet="LangGraph 使用状态图构建长期运行的 Agent 工作流",
                )
            ],
        )
        builder = EvidenceGraphBuilder()
        graph = builder.build([artifact])

        markdown = builder.format_audit_markdown(graph)

        self.assertIn("引用覆盖率", markdown)
        self.assertIn("[C1-1]", markdown)
        self.assertIn("[S1]", markdown)
        self.assertIn("https://docs.langchain.com", markdown)

    def test_same_task_sources_are_partial_fallback_when_snippets_are_thin(self) -> None:
        artifact = ResearchArtifact(
            artifact_id="a1",
            task_id=2,
            producer="Researcher-2",
            status="completed",
            findings=["LangGraph 适合需要可审计状态流转的企业级多 Agent 工作流"],
            evidence=[
                SourceCard(
                    title="Official product overview",
                    url="https://docs.langchain.com/oss/python/langgraph/overview",
                )
            ],
        )
        builder = EvidenceGraphBuilder()
        graph = builder.build([artifact])

        self.assertEqual("partial", graph.claims[0].support_status)
        self.assertEqual(["S1"], graph.claims[0].source_ids)
        self.assertEqual(1.0, graph.metrics["citation_coverage"])


if __name__ == "__main__":
    unittest.main()
