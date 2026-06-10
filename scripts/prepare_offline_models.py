from __future__ import annotations

import argparse
import json
from pathlib import Path


DEFAULT_MODELS = {
    "faster_whisper": [
        "Systran/faster-whisper-base",
        "Systran/faster-whisper-medium",
    ],
    "pyannote": [
        "pyannote/speaker-diarization-3.1",
    ],
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Descarga modelos STT/diarizacion para ejecucion offline."
    )
    parser.add_argument(
        "--target",
        default="models",
        help="Directorio destino para snapshots locales.",
    )
    parser.add_argument(
        "--manifest",
        default="models/offline_manifest.json",
        help="Archivo JSON con rutas locales generadas.",
    )
    parser.add_argument(
        "--model",
        action="append",
        default=[],
        help="Repo HF adicional. Puede repetirse.",
    )
    parser.add_argument(
        "--skip-pyannote",
        action="store_true",
        help="Omite modelos pyannote gated si no hay token HF.",
    )
    args = parser.parse_args()

    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise SystemExit(
            "Instala huggingface_hub para preparar modelos offline: "
            "pip install huggingface_hub"
        ) from exc

    target = Path(args.target).resolve()
    target.mkdir(parents=True, exist_ok=True)

    repos = list(DEFAULT_MODELS["faster_whisper"])
    if not args.skip_pyannote:
        repos.extend(DEFAULT_MODELS["pyannote"])
    repos.extend(args.model)

    manifest: dict[str, str] = {}
    for repo_id in repos:
        local_dir = target / repo_id.replace("/", "__")
        path = snapshot_download(
            repo_id=repo_id,
            local_dir=str(local_dir),
            local_dir_use_symlinks=False,
        )
        manifest[repo_id] = str(Path(path).resolve())
        print(f"{repo_id} -> {manifest[repo_id]}")

    manifest_path = Path(args.manifest).resolve()
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
