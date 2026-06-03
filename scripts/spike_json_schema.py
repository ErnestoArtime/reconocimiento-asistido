from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.llm_provider import SYSTEM_PROMPT, build_extraction_schema  # noqa: E402
from app.services.questionnaire_engine import QuestionnaireEngine  # noqa: E402


def ollama_version() -> str:
    try:
        completed = subprocess.run(
            ["ollama", "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return str(exc)
    return ((completed.stdout or "") + (completed.stderr or "")).strip()


def run_generation(
    *,
    base_url: str,
    model: str,
    schema: dict[str, Any],
    payload: dict[str, Any],
    timeout_s: float,
) -> tuple[bool, bool, float, str]:
    started = time.perf_counter()
    body = {
        "model": model,
        "stream": False,
        "format": schema,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": "Devuelve solo JSON valido.\nDatos:\n"
                + json.dumps(payload, ensure_ascii=False),
            },
        ],
        "options": {"temperature": 0.1},
    }
    try:
        with httpx.Client(timeout=timeout_s) as client:
            response = client.post(f"{base_url.rstrip('/')}/api/chat", json=body)
            response.raise_for_status()
            data = response.json()
    except Exception as exc:  # noqa: BLE001
        return False, False, (time.perf_counter() - started) * 1000, str(exc)

    content = ((data.get("message") or {}).get("content") or "").strip()
    if not content:
        return True, False, (time.perf_counter() - started) * 1000, "<empty>"
    try:
        json.loads(content)
        parsed = True
    except json.JSONDecodeError:
        parsed = False
    return True, parsed, (time.perf_counter() - started) * 1000, content[:500]


def render_report(args: argparse.Namespace) -> str:
    engine = QuestionnaireEngine(ROOT / "app" / "data" / "json_IA.json")
    questions = engine.get_questions_by_section(args.module, args.section)[: args.questions]
    schema = build_extraction_schema(questions)
    payload = {
        "module": args.module,
        "section": args.section,
        "transcript": args.text,
        "questions": questions,
    }

    results = [
        run_generation(
            base_url=args.base_url,
            model=args.model,
            schema=schema,
            payload=payload,
            timeout_s=args.timeout,
        )
        for _ in range(args.iterations)
    ]
    http_ok = sum(1 for ok, _parsed, _ms, _sample in results if ok)
    parsed_ok = sum(1 for ok, parsed, _ms, _sample in results if ok and parsed)
    empty = sum(1 for ok, parsed, _ms, sample in results if ok and not parsed and sample == "<empty>")
    avg_ms = sum(ms for _ok, _parsed, ms, _sample in results) / len(results)

    return "\n".join(
        [
            f"# JSON Schema spike {args.model}",
            "",
            f"- Ollama: `{ollama_version()}`",
            f"- Model: `{args.model}`",
            f"- Iterations: `{args.iterations}`",
            f"- HTTP OK: `{http_ok}`",
            f"- JSON parse OK: `{parsed_ok}`",
            f"- Empty: `{empty}`",
            f"- Avg latency ms: `{avg_ms:.1f}`",
            "",
            "## Adoption check",
            "",
            f"- schema_pass >= 48/51: `{parsed_ok >= 48 if args.iterations >= 51 else 'not enough iterations'}`",
            "",
            "## First sample",
            "",
            "```text",
            results[0][3] if results else "<no result>",
            "```",
            "",
        ]
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Spike Ollama JSON Schema support.")
    parser.add_argument("--model", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--module", default="exam", choices=["history", "exam"])
    parser.add_argument("--section", default="CABEZA")
    parser.add_argument("--questions", type=int, default=3)
    parser.add_argument("--iterations", type=int, default=51)
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument(
        "--text",
        default="Cuero cabelludo normal. Cara normal. Boca normal.",
    )
    parser.add_argument("--output", default="")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = render_report(args)
    output = (
        Path(args.output)
        if args.output
        else ROOT / "docs" / "spikes" / f"json_schema_{args.model.replace(':', '_')}.md"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
