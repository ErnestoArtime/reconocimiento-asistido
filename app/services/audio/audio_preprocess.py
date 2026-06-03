"""Pre-proceso de audio con FFmpeg.

Normaliza cualquier formato de entrada (.wav, .mp3, .m4a, .webm, .ogg, ...)
a WAV mono 16 kHz PCM 16-bit. Aplica filtros para mejorar la senal en consulta
medica: paso alto 80 Hz (quita rumble), paso bajo 8 kHz (quita silbidos),
denoise FFT, y loudnorm para uniformar volumen.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path


logger = logging.getLogger(__name__)


DEFAULT_FILTER = "highpass=f=80,lowpass=f=8000,afftdn=nr=12,loudnorm=I=-16:LRA=11:TP=-1.5"


def ffmpeg_available() -> bool:
    return _resolve_binary("FFMPEG_PATH", "ffmpeg") is not None


def normalize_audio(
    input_path: str | Path,
    output_path: str | Path,
    sample_rate: int = 16000,
    apply_filters: bool = True,
) -> Path:
    """Convierte input a WAV mono `sample_rate` Hz PCM_S16LE.

    Devuelve la ruta de salida. Lanza RuntimeError si FFmpeg no esta o falla.
    """
    if not ffmpeg_available():
        raise RuntimeError(
            "FFmpeg no encontrado en PATH. Instala con: winget install Gyan.FFmpeg"
        )

    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ffmpeg = _resolve_binary("FFMPEG_PATH", "ffmpeg")
    if not ffmpeg:
        raise RuntimeError(
            "FFmpeg no encontrado. Instala con winget install Gyan.FFmpeg "
            "o configura FFMPEG_PATH con la ruta completa a ffmpeg.exe."
        )

    cmd = [
        ffmpeg,
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(input_path),
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-sample_fmt",
        "s16",
    ]
    if apply_filters:
        cmd += ["-af", DEFAULT_FILTER]
    cmd += [str(output_path)]

    logger.debug("FFmpeg cmd: %s", " ".join(cmd))
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"FFmpeg fallo (code={result.returncode}): {result.stderr.strip()}"
        )
    return output_path


def probe_duration(audio_path: str | Path) -> float:
    """Devuelve duracion del audio en segundos via ffprobe."""
    ffprobe = _resolve_binary("FFPROBE_PATH", "ffprobe")
    if not ffprobe:
        return 0.0
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        return float(result.stdout.strip())
    except (TypeError, ValueError):
        return 0.0


def _resolve_binary(env_name: str, default_name: str) -> str | None:
    configured = os.getenv(env_name, "").strip()
    if configured and Path(configured).exists():
        return configured
    if configured:
        discovered = shutil.which(configured)
        if discovered:
            return discovered
    return shutil.which(default_name)
