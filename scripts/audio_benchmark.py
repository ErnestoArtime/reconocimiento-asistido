"""Benchmark de proveedores de transcripcion.

Estructura esperada del corpus:
    tests/audio_samples/
        consulta01.wav   (o .mp3, .m4a)
        consulta01.txt   (transcripcion gold en espanol)
        consulta02.wav
        consulta02.txt
        ...

Uso:
    python scripts/audio_benchmark.py
    python scripts/audio_benchmark.py --providers faster_whisper,openai
    python scripts/audio_benchmark.py --corpus tests/audio_samples --output results.md
"""
from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

# Permitir ejecutar como script sin instalar el paquete
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import get_settings  # noqa: E402
from app.services.audio import available_providers, get_provider  # noqa: E402
from app.services.audio.audio_preprocess import normalize_audio  # noqa: E402
from app.services.audio.clinical_prompt import build_clinical_prompt  # noqa: E402
from app.services.audio.metrics import score  # noqa: E402
from app.services.questionnaire_engine import QuestionnaireEngine  # noqa: E402


AUDIO_EXT = {".wav", ".mp3", ".m4a", ".webm", ".ogg", ".flac"}


def find_pairs(corpus: Path) -> list[tuple[Path, Path]]:
    pairs: list[tuple[Path, Path]] = []
    for audio in sorted(corpus.iterdir()):
        if audio.suffix.lower() not in AUDIO_EXT:
            continue
        gold = audio.with_suffix(".txt")
        if not gold.exists():
            print(f"[skip] {audio.name}: falta {gold.name}")
            continue
        pairs.append((audio, gold))
    return pairs


def run_provider(name: str, audio_path: Path, prompt: str | None) -> dict:
    provider = get_provider(name)
    started = time.perf_counter()
    result = provider.transcribe(
        audio_path=str(audio_path),
        language="es",
        initial_prompt=prompt,
        diarize=False,
    )
    elapsed = time.perf_counter() - started
    return {
        "text": result.text,
        "duration_s": result.duration_s or 0.0,
        "rtf": result.rtf or (elapsed / result.duration_s if result.duration_s else 0.0),
        "elapsed_s": elapsed,
        "model": result.model,
    }


def render_markdown(rows: list[dict], summaries: dict[str, dict]) -> str:
    lines = ["# Audio benchmark", "", "## Resultados por archivo", ""]
    lines.append("| sample | provider | WER | CER | RTF | dur(s) | proc(s) |")
    lines.append("|---|---|---|---|---|---|---|")
    for row in rows:
        lines.append(
            f"| {row['sample']} | {row['provider']} | "
            f"{row['wer']:.3f} | {row['cer']:.3f} | "
            f"{row['rtf']:.2f} | {row['duration_s']:.1f} | {row['elapsed_s']:.1f} |"
        )
    lines.append("")
    lines.append("## Resumen por provider")
    lines.append("")
    lines.append("| provider | WER medio | CER medio | RTF medio | n |")
    lines.append("|---|---|---|---|---|")
    for provider_name, s in summaries.items():
        lines.append(
            f"| {provider_name} | {s['wer']:.3f} | {s['cer']:.3f} | {s['rtf']:.2f} | {s['n']} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", default="tests/audio_samples")
    parser.add_argument("--providers", default="")
    parser.add_argument("--output", default="audio_benchmark_results.md")
    parser.add_argument("--no-clinical-prompt", action="store_true")
    args = parser.parse_args()

    corpus = Path(args.corpus)
    if not corpus.exists():
        print(f"Corpus no existe: {corpus}")
        return 1

    pairs = find_pairs(corpus)
    if not pairs:
        print("Sin pares audio/.txt en corpus.")
        return 1

    providers = (
        [p.strip() for p in args.providers.split(",") if p.strip()]
        if args.providers
        else available_providers()
    )
    print(f"Providers: {providers}")
    print(f"Samples: {len(pairs)}")

    settings = get_settings()
    prompt: str | None = None
    if not args.no_clinical_prompt:
        engine = QuestionnaireEngine(settings.questionnaire_path)
        prompt = build_clinical_prompt(engine.data, extra=settings.audio_initial_prompt)

    rows: list[dict] = []
    per_provider: dict[str, list[dict]] = {p: [] for p in providers}

    # pre-normaliza una vez por sample (mismo input a todos los providers)
    work_dir = Path(".cache/benchmark")
    work_dir.mkdir(parents=True, exist_ok=True)

    for audio, gold in pairs:
        wav = work_dir / f"{audio.stem}.wav"
        normalize_audio(audio, wav, apply_filters=settings.audio_apply_filters)
        reference = gold.read_text(encoding="utf-8")

        for provider_name in providers:
            try:
                outcome = run_provider(provider_name, wav, prompt)
            except Exception as exc:  # noqa: BLE001
                print(f"[fail] {audio.name} | {provider_name}: {exc}")
                continue
            quality = score(reference, outcome["text"])
            row = {
                "sample": audio.stem,
                "provider": provider_name,
                "wer": quality.wer,
                "cer": quality.cer,
                "rtf": outcome["rtf"],
                "duration_s": outcome["duration_s"],
                "elapsed_s": outcome["elapsed_s"],
            }
            rows.append(row)
            per_provider[provider_name].append(row)
            print(
                f"{audio.stem:<25} {provider_name:<18} "
                f"WER={quality.wer:.3f} CER={quality.cer:.3f} "
                f"RTF={outcome['rtf']:.2f}"
            )

    summaries: dict[str, dict] = {}
    for name, items in per_provider.items():
        if not items:
            continue
        summaries[name] = {
            "wer": statistics.mean(r["wer"] for r in items),
            "cer": statistics.mean(r["cer"] for r in items),
            "rtf": statistics.mean(r["rtf"] for r in items),
            "n": len(items),
        }

    out = render_markdown(rows, summaries)
    Path(args.output).write_text(out, encoding="utf-8")
    print(f"\nResultado: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
