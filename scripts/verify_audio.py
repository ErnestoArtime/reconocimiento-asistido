"""Verifica el stack de audio sin tocar el modelo grande.

Pasos:
  1. Python version.
  2. FFmpeg + ffprobe en PATH.
  3. Import de faster_whisper y ctranslate2.
  4. (Opcional) Carga modelo `tiny` en CPU/int8 y transcribe un beep sintetico.

Uso:
    python scripts/verify_audio.py
    python scripts/verify_audio.py --skip-model
"""
from __future__ import annotations

import argparse
import math
import platform
import shutil
import struct
import sys
import tempfile
import wave
from pathlib import Path


def info(msg: str) -> None:
    print(f"[ OK ] {msg}")


def warn(msg: str) -> None:
    print(f"[WARN] {msg}")


def fail(msg: str) -> None:
    print(f"[FAIL] {msg}")


def check_python() -> bool:
    v = sys.version_info
    print(f"Python {v.major}.{v.minor}.{v.micro} en {platform.platform()}")
    if (v.major, v.minor) not in {(3, 11), (3, 12)}:
        warn("Recomendado Python 3.11 o 3.12 para ruedas IA estables")
    return True


def check_ffmpeg() -> bool:
    ok = True
    for tool in ("ffmpeg", "ffprobe"):
        path = shutil.which(tool)
        if path:
            info(f"{tool}: {path}")
        else:
            fail(f"{tool} no encontrado en PATH")
            ok = False
    return ok


def check_imports() -> bool:
    ok = True
    try:
        import faster_whisper  # noqa: F401

        info(f"faster_whisper {faster_whisper.__version__}")
    except Exception as exc:  # noqa: BLE001
        fail(f"faster_whisper import: {exc}")
        ok = False
    try:
        import ctranslate2  # noqa: F401

        info(f"ctranslate2 {ctranslate2.__version__}")
    except Exception as exc:  # noqa: BLE001
        fail(f"ctranslate2 import: {exc}")
        ok = False
    try:
        import soundfile  # noqa: F401

        info(f"soundfile {soundfile.__version__}")
    except Exception as exc:  # noqa: BLE001
        warn(f"soundfile no disponible: {exc}")
    return ok


def make_silent_wav(path: Path, seconds: float = 1.0, sr: int = 16000) -> None:
    n = int(seconds * sr)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sr)
        # tono 440 Hz suave
        frames = bytearray()
        for i in range(n):
            sample = int(0.1 * 32767 * math.sin(2 * math.pi * 440 * i / sr))
            frames += struct.pack("<h", sample)
        wav.writeframes(bytes(frames))


def check_model() -> bool:
    try:
        from faster_whisper import WhisperModel
    except Exception as exc:  # noqa: BLE001
        fail(f"No se puede importar WhisperModel: {exc}")
        return False
    try:
        info("Descargando/cargando modelo tiny en CPU/int8 (primera vez ~75MB)...")
        model = WhisperModel("tiny", device="cpu", compute_type="int8")
    except Exception as exc:  # noqa: BLE001
        fail(f"Carga modelo tiny fallo: {exc}")
        return False

    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "beep.wav"
        make_silent_wav(wav, seconds=1.0)
        try:
            segments, info_ = model.transcribe(str(wav), language="es", vad_filter=False)
            text = " ".join(s.text for s in segments).strip()
            info(f"Transcripcion test (beep): '{text or '(vacio)'}' duration={info_.duration:.2f}s")
        except Exception as exc:  # noqa: BLE001
            fail(f"transcribe() fallo: {exc}")
            return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-model", action="store_true", help="No descarga modelo tiny")
    args = parser.parse_args()

    print("== Verify audio stack ==")
    ok = True
    ok &= check_python()
    ok &= check_ffmpeg()
    ok &= check_imports()
    if not args.skip_model:
        ok &= check_model()
    else:
        warn("--skip-model: no se valida carga de modelo")

    print()
    if ok:
        info("Todo correcto. Stack listo.")
        return 0
    fail("Hay problemas en el stack. Revisa los WARN/FAIL anteriores.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
