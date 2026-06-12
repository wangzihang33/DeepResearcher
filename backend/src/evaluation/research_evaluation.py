"""Command-line runner for deep research quality evaluation."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Iterable

from agent import DeepResearchAgent
from config import Configuration, SearchAPI
from evaluation.metrics import EvalCase, EvalResult, evaluate_report


DEFAULT_DATASET = Path(__file__).parent / "data" / "research_eval_dataset.jsonl"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "evaluations"


def main() -> None:
    """Run the evaluation CLI."""

    parser = argparse.ArgumentParser(
        description="Evaluate Deep Research Assistant reports with rule-based metrics.",
    )
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET), help="JSONL dataset path.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Output directory.")
    parser.add_argument("--max-cases", type=int, default=None, help="Maximum cases to run.")
    parser.add_argument("--run-label", default="phase3_v1", help="Label written into reports.")
    parser.add_argument(
        "--search-api",
        choices=[item.value for item in SearchAPI],
        default=None,
        help="Optional search backend override.",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Only score existing report_path values in the dataset; do not call the agent.",
    )
    args = parser.parse_args()

    cases = load_cases(Path(args.dataset))
    if args.max_cases is not None:
        cases = cases[: max(0, args.max_cases)]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(args.output_dir)
    reports_dir = output_dir / "reports" / f"{timestamp}_{args.run_label}"
    output_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    results: list[EvalResult] = []
    for index, case in enumerate(cases, start=1):
        print(f"[{index}/{len(cases)}] evaluating {case.case_id}: {case.query}")
        report_markdown = ""
        report_path = reports_dir / f"{case.case_id}.md"
        error = ""

        try:
            report_markdown = load_or_generate_report(
                case,
                report_only=args.report_only,
                search_api=args.search_api,
            )
            report_path.write_text(report_markdown, encoding="utf-8")
        except Exception as exc:  # pragma: no cover - runtime integration guard
            error = str(exc)

        results.append(
            evaluate_report(
                case,
                report_markdown,
                report_path=str(report_path) if report_markdown else "",
                error=error,
            )
        )

    csv_path = output_dir / f"research_eval_{timestamp}_{args.run_label}.csv"
    md_path = output_dir / f"research_eval_{timestamp}_{args.run_label}.md"
    write_csv(results, csv_path)
    write_markdown(results, md_path, run_label=args.run_label)

    print(f"Evaluation complete: {len(results)} cases")
    print(f"CSV: {csv_path}")
    print(f"Markdown: {md_path}")
    for name, value in aggregate_metrics(results).items():
        print(f"- {name}={value:.4f}")


def load_or_generate_report(
    case: EvalCase,
    *,
    report_only: bool,
    search_api: str | None,
) -> str:
    """Load a pre-existing report or run the real research workflow."""

    if report_only:
        if not case.report_path:
            raise ValueError(f"case {case.case_id} has no report_path")
        return Path(case.report_path).read_text(encoding="utf-8")

    overrides = {}
    if search_api:
        overrides["search_api"] = SearchAPI(search_api)
    config = Configuration.from_env(overrides=overrides)
    agent = DeepResearchAgent(config=config)
    output = agent.run(case.query)
    return output.report_markdown or output.running_summary or ""


def load_cases(path: Path) -> list[EvalCase]:
    """Load evaluation cases from JSONL."""

    cases: list[EvalCase] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        payload = json.loads(line)
        case = EvalCase.from_dict(payload)
        if not case.case_id or not case.query:
            raise ValueError(f"Invalid eval case at line {line_number}: missing id/query")
        cases.append(case)
    return cases


def write_csv(results: Iterable[EvalResult], path: Path) -> None:
    """Write per-case evaluation details."""

    rows = [asdict(result) for result in results]
    fieldnames = [
        "case_id",
        "category",
        "query",
        "task_coverage",
        "citation_coverage",
        "source_quality",
        "unsupported_claim_rate",
        "covered_topics",
        "missing_topics",
        "source_count",
        "trusted_source_count",
        "report_path",
        "error",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            row["covered_topics"] = "；".join(row["covered_topics"])
            row["missing_topics"] = "；".join(row["missing_topics"])
            writer.writerow(row)


def write_markdown(results: list[EvalResult], path: Path, *, run_label: str) -> None:
    """Write a human-readable evaluation summary."""

    averages = aggregate_metrics(results)
    lines = [
        f"# Deep Research Quality Evaluation - {run_label}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Cases | {len(results)} |",
        f"| Avg Task Coverage | {averages['task_coverage']:.2%} |",
        f"| Avg Citation Coverage | {averages['citation_coverage']:.2%} |",
        f"| Avg Source Quality | {averages['source_quality']:.2%} |",
        f"| Avg Unsupported Claim Rate | {averages['unsupported_claim_rate']:.2%} |",
        "",
        "## Case Details",
        "",
        "| Case | Category | Task Coverage | Citation Coverage | Source Quality | Unsupported Rate | Missing Topics |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]

    for result in results:
        missing = "、".join(result.missing_topics) if result.missing_topics else "-"
        lines.append(
            f"| {result.case_id} | {result.category} | "
            f"{result.task_coverage:.2%} | {result.citation_coverage:.2%} | "
            f"{result.source_quality:.2%} | {result.unsupported_claim_rate:.2%} | "
            f"{missing} |"
        )

    errors = [result for result in results if result.error]
    if errors:
        lines.extend(["", "## Errors", ""])
        for result in errors:
            lines.append(f"- `{result.case_id}`: {result.error}")

    lines.extend(
        [
            "",
            "## Metric Definitions",
            "",
            "- Task Coverage: manually labeled expected topics matched in the final report.",
            "- Citation Coverage: citation audit coverage from the Evidence Graph appendix.",
            "- Source Quality: ratio of parsed report sources that match trusted or preferred source keywords.",
            "- Unsupported Claim Rate: unsupported claim ratio from the Evidence Graph appendix.",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def aggregate_metrics(results: list[EvalResult]) -> dict[str, float]:
    """Aggregate average metrics across cases."""

    if not results:
        return {
            "task_coverage": 0.0,
            "citation_coverage": 0.0,
            "source_quality": 0.0,
            "unsupported_claim_rate": 0.0,
        }

    return {
        "task_coverage": sum(item.task_coverage for item in results) / len(results),
        "citation_coverage": sum(item.citation_coverage for item in results) / len(results),
        "source_quality": sum(item.source_quality for item in results) / len(results),
        "unsupported_claim_rate": sum(item.unsupported_claim_rate for item in results) / len(results),
    }


if __name__ == "__main__":
    main()
