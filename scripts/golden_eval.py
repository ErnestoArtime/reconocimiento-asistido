from __future__ import annotations

import argparse
import datetime as dt
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.models.suggestion import AiSuggestion  # noqa: E402
from app.services.extraction_service import extract_from_text  # noqa: E402
from app.services.llm_provider import OllamaProvider  # noqa: E402
from app.services.questionnaire_engine import QuestionnaireEngine  # noqa: E402


GOLDEN_ROOT = ROOT / "tests" / "golden"
BASELINES_DIR = ROOT / "docs" / "baselines"


@dataclass
class CaseResult:
    case_id: str
    latency_ms: float
    expected_count: int
    predicted_count: int
    exact_matches: int
    false_positive: int
    false_negative: int
    forbidden_code: int
    invalid_code: int
    negation_error: int
    empty_generation: int


@dataclass
class ModelResult:
    name: str
    provider: str
    cases: list[CaseResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def precision(self) -> float:
        tp = sum(case.exact_matches for case in self.cases)
        fp = sum(case.false_positive for case in self.cases)
        return tp / (tp + fp) if tp + fp else 0.0

    @property
    def recall(self) -> float:
        tp = sum(case.exact_matches for case in self.cases)
        fn = sum(case.false_negative for case in self.cases)
        return tp / (tp + fn) if tp + fn else 0.0

    @property
    def avg_latency_ms(self) -> float:
        values = [case.latency_ms for case in self.cases]
        return statistics.mean(values) if values else 0.0


def load_cases(limit: int | None = None) -> list[dict[str, Any]]:
    cases = []
    for path in sorted(GOLDEN_ROOT.rglob("*.yaml")):
        case = yaml.safe_load(path.read_text(encoding="utf-8"))
        case["_path"] = path
        cases.append(case)
    return cases[:limit] if limit else cases


def expected_pairs(case: dict[str, Any]) -> set[tuple[str, tuple[str, ...]]]:
    return {
        (item["question_id"], tuple(sorted(item["selected_codes"])))
        for item in case.get("expected_suggestions", [])
    }


def predicted_pairs(suggestions: list[AiSuggestion]) -> set[tuple[str, tuple[str, ...]]]:
    return {
        (item.question_id, tuple(sorted(item.selected_codes)))
        for item in suggestions
        if item.selected_codes
    }


def valid_codes_by_question(questions: list[dict[str, Any]]) -> dict[str, set[str]]:
    return {
        question["id"]: set(question.get("codes", {}).keys())
        for question in questions
    }


def run_provider(
    model: str,
    case: dict[str, Any],
    questions: list[dict[str, Any]],
    ollama_base_url: str,
    ollama_num_ctx: int,
    timeout_s: float,
) -> tuple[list[AiSuggestion], float]:
    started = time.perf_counter()
    if model == "heuristic":
        suggestions = extract_from_text(
            text=case["transcript"],
            module=case["module"],
            section=case["section"],
            questions=questions,
        )
    else:
        provider = OllamaProvider(
            base_url=ollama_base_url,
            model=model,
            timeout=timeout_s,
            temperature=0.1,
            num_ctx=ollama_num_ctx,
        )
        suggestions = provider.extract(
            text=case["transcript"],
            module=case["module"],
            section=case["section"],
            questions=questions,
        )
    latency_ms = (time.perf_counter() - started) * 1000
    return suggestions, latency_ms


def evaluate_model(
    model: str,
    cases: list[dict[str, Any]],
    engine: QuestionnaireEngine,
    args: argparse.Namespace,
) -> ModelResult:
    result = ModelResult(
        name=model,
        provider="heuristic" if model == "heuristic" else "ollama",
    )

    for case in cases:
        try:
            questions = engine.get_questions_by_section(case["module"], case["section"])
            raw_suggestions, latency_ms = run_provider(
                model=model,
                case=case,
                questions=questions,
                ollama_base_url=args.ollama_base_url,
                ollama_num_ctx=args.ollama_num_ctx,
                timeout_s=args.timeout,
            )
        except Exception as exc:
            result.errors.append(f"{case['id']}: {exc}")
            continue

        valid_codes = valid_codes_by_question(questions)
        invalid_code = 0
        forbidden_code = 0
        forbidden_codes = set(case.get("forbidden_codes", []))

        for suggestion in raw_suggestions:
            allowed = valid_codes.get(suggestion.question_id, set())
            for code in suggestion.selected_codes:
                if code not in allowed:
                    invalid_code += 1
                if code in forbidden_codes:
                    forbidden_code += 1

        validated = engine.validate_suggestions(raw_suggestions)
        expected = expected_pairs(case)
        predicted = predicted_pairs(validated)
        exact = expected & predicted
        false_positive = predicted - expected
        false_negative = expected - predicted

        result.cases.append(
            CaseResult(
                case_id=case["id"],
                latency_ms=latency_ms,
                expected_count=len(expected),
                predicted_count=len(predicted),
                exact_matches=len(exact),
                false_positive=len(false_positive),
                false_negative=len(false_negative),
                forbidden_code=forbidden_code,
                invalid_code=invalid_code,
                negation_error=forbidden_code if case.get("labels") else 0,
                empty_generation=0 if raw_suggestions else 1,
            )
        )

    return result


def render_report(results: list[ModelResult], cases: list[dict[str, Any]]) -> str:
    now = dt.datetime.now().replace(microsecond=0)
    lines = [
        f"# Golden benchmark {now.date().isoformat()}",
        "",
        "## Scope",
        "",
        f"- Cases: `{len(cases)}`",
        f"- Generated: `{now.isoformat(sep=' ')}`",
        "",
        "## Summary",
        "",
        "| Model | Provider | Cases | Precision | Recall | Invalid codes | Forbidden codes | Negation errors | Empty | Avg latency ms | Errors |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    for result in results:
        lines.append(
            "| "
            + " | ".join(
                [
                    result.name,
                    result.provider,
                    str(len(result.cases)),
                    f"{result.precision:.3f}",
                    f"{result.recall:.3f}",
                    str(sum(case.invalid_code for case in result.cases)),
                    str(sum(case.forbidden_code for case in result.cases)),
                    str(sum(case.negation_error for case in result.cases)),
                    str(sum(case.empty_generation for case in result.cases)),
                    f"{result.avg_latency_ms:.1f}",
                    str(len(result.errors)),
                ]
            )
            + " |"
        )

    for result in results:
        lines.extend(
            [
                "",
                f"## Detail: {result.name}",
                "",
                "| Case | Expected | Predicted | Exact | FP | FN | Forbidden | Invalid | Empty | Latency ms |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for case in result.cases:
            lines.append(
                "| "
                + " | ".join(
                    [
                        case.case_id,
                        str(case.expected_count),
                        str(case.predicted_count),
                        str(case.exact_matches),
                        str(case.false_positive),
                        str(case.false_negative),
                        str(case.forbidden_code),
                        str(case.invalid_code),
                        str(case.empty_generation),
                        f"{case.latency_ms:.1f}",
                    ]
                )
                + " |"
            )
        if result.errors:
            lines.extend(["", "Errors:", ""])
            lines.extend(f"- {error}" for error in result.errors)

    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate providers against golden YAML cases.")
    parser.add_argument(
        "--models",
        default="heuristic",
        help="Comma-separated models. Use 'heuristic' or Ollama model names.",
    )
    parser.add_argument("--limit", type=int, default=0, help="Limit cases for quick checks.")
    parser.add_argument(
        "--ollama-base-url",
        default=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
    )
    parser.add_argument("--ollama-num-ctx", type=int, default=int(os.getenv("OLLAMA_NUM_CTX", "8192")))
    parser.add_argument("--timeout", type=float, default=float(os.getenv("OLLAMA_TIMEOUT", "180")))
    parser.add_argument("--output", default="", help="Optional report path.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cases = load_cases(args.limit or None)
    engine = QuestionnaireEngine(ROOT / "app" / "data" / "json_IA.json")
    models = [model.strip() for model in args.models.split(",") if model.strip()]

    results = [evaluate_model(model, cases, engine, args) for model in models]
    report = render_report(results, cases)

    BASELINES_DIR.mkdir(parents=True, exist_ok=True)
    output_path = (
        Path(args.output)
        if args.output
        else BASELINES_DIR / f"{dt.date.today().isoformat()}_bench.md"
    )
    output_path.write_text(report, encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    main()
