"""Streaming de transcripcion sobre cualquier TranscriptionProvider sincrono.

Estrategia simple (sirve para faster_whisper, openai, deepgram batch):
  - Cliente envia chunks de PCM s16le mono 16kHz como bytes.
  - Servidor mantiene un buffer rodante.
  - Cada `partial_every_s` segundos transcribe el buffer entero -> emit partial.
  - VAD (webrtcvad o energia) detecta silencio sostenido -> cierra segmento,
    emite final, recorta buffer.

Para providers nativamente streaming (Azure, Deepgram live), conviene
delegar al SDK; eso se hace en proveedor especifico, no aqui.
"""
from __future__ import annotations

import asyncio
import logging
import tempfile
import time
import wave
from dataclasses import dataclass
from pathlib import Path

from app.services.audio.base import PartialTranscript, TranscriptionProvider


logger = logging.getLogger(__name__)


SAMPLE_RATE = 16000
SAMPLE_WIDTH = 2  # int16
CHANNELS = 1


@dataclass
class StreamConfig:
    partial_every_s: float = 1.5
    min_segment_s: float = 2.0
    max_segment_s: float = 12.0
    silence_ms_to_close: int = 800
    language: str = "es"
    initial_prompt: str | None = None


class _EnergyVAD:
    """VAD por energia (RMS). Fallback si webrtcvad no esta instalado."""

    def __init__(self, threshold: int = 200) -> None:
        self.threshold = threshold

    def is_speech(self, pcm: bytes) -> bool:
        if not pcm:
            return False
        # RMS de int16
        n = len(pcm) // 2
        total = 0
        for i in range(0, n * 2, 2):
            sample = int.from_bytes(pcm[i : i + 2], "little", signed=True)
            total += sample * sample
        rms = (total / max(n, 1)) ** 0.5
        return rms > self.threshold


def _load_vad() -> object:
    try:
        import webrtcvad  # type: ignore

        return webrtcvad.Vad(2)  # agresividad 0-3
    except Exception:  # noqa: BLE001
        logger.warning("webrtcvad no disponible, usando VAD por energia")
        return _EnergyVAD()


def _is_speech(vad: object, frame: bytes) -> bool:
    try:
        return vad.is_speech(frame, SAMPLE_RATE)  # type: ignore[attr-defined]
    except TypeError:
        return vad.is_speech(frame)  # type: ignore[attr-defined]


def _frame_iter(pcm: bytes, frame_ms: int = 20):
    frame_bytes = int(SAMPLE_RATE * frame_ms / 1000) * SAMPLE_WIDTH
    for i in range(0, len(pcm) - frame_bytes + 1, frame_bytes):
        yield pcm[i : i + frame_bytes]


def _silence_ms(pcm: bytes, vad: object) -> int:
    """Cuenta ms finales sin habla."""
    frames = list(_frame_iter(pcm))
    silence_frames = 0
    for frame in reversed(frames):
        if _is_speech(vad, frame):
            break
        silence_frames += 1
    return silence_frames * 20


def _write_wav(path: Path, pcm: bytes) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm)


class StreamingTranscriber:
    """Driver de streaming sobre un provider sincrono.

    Uso (en un endpoint WebSocket):
        st = StreamingTranscriber(provider, StreamConfig())
        async for partial in st.consume(chunk_iter()):
            await ws.send_json({"text": partial.text, "final": partial.is_final, ...})
    """

    def __init__(self, provider: TranscriptionProvider, config: StreamConfig) -> None:
        self.provider = provider
        self.config = config
        self._vad = _load_vad()
        self._buffer = bytearray()
        self._segment_started_at = 0.0
        self._last_partial_at = 0.0

    def _segment_duration_s(self) -> float:
        return len(self._buffer) / (SAMPLE_RATE * SAMPLE_WIDTH)

    async def _transcribe_buffer(self, is_final: bool) -> PartialTranscript | None:
        if not self._buffer:
            return None
        buf_dur = self._segment_duration_s()
        logger.info(
            "[stream] transcribing buffer: %.2fs %d bytes is_final=%s",
            buf_dur, len(self._buffer), is_final,
        )
        with tempfile.TemporaryDirectory(prefix="reco_stream_") as tmp:
            wav_path = Path(tmp) / "chunk.wav"
            _write_wav(wav_path, bytes(self._buffer))
            try:
                result = await asyncio.to_thread(
                    self.provider.transcribe,
                    str(wav_path),
                    self.config.language,
                    self.config.initial_prompt,
                    False,
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("[stream] transcribe failed: %s", exc)
                return None
        text = result.text.strip() if result.text else ""
        logger.info("[stream] transcribe result: %d chars final=%s", len(text), is_final)
        return PartialTranscript(
            text=text,
            is_final=is_final,
            start=self._segment_started_at,
            end=self._segment_started_at + self._segment_duration_s(),
        )

    async def consume(self, chunks):
        """Consume un async iterable de bytes PCM y emite PartialTranscript.

        chunks: async iterator de bytes (PCM s16le 16kHz mono).
        """
        self._segment_started_at = 0.0
        self._last_partial_at = time.time()
        chunk_count = 0
        bytes_total = 0
        last_log = time.time()
        logger.info("[stream] consume started, waiting for chunks...")

        async for chunk in chunks:
            if not chunk:
                continue
            chunk_count += 1
            bytes_total += len(chunk)
            self._buffer.extend(chunk)
            now = time.time()
            dur = self._segment_duration_s()

            # Heartbeat log cada 2s
            if now - last_log > 2.0:
                logger.info(
                    "[stream] chunks=%d total_bytes=%d buf_dur=%.2fs",
                    chunk_count, bytes_total, dur,
                )
                last_log = now

            # Forzar corte si excede max
            if dur >= self.config.max_segment_s:
                logger.info("[stream] max_segment reached %.2fs -> final transcribe", dur)
                final = await self._transcribe_buffer(is_final=True)
                if final:
                    logger.info("[stream] FINAL: %s", final.text[:80])
                    yield final
                self._segment_started_at += dur
                self._buffer.clear()
                self._last_partial_at = now
                continue

            # Cierre por silencio
            if dur >= self.config.min_segment_s:
                tail = bytes(self._buffer[-SAMPLE_RATE * SAMPLE_WIDTH :])  # 1s final
                sil_ms = _silence_ms(tail, self._vad)
                if sil_ms >= self.config.silence_ms_to_close:
                    logger.info(
                        "[stream] silence %dms detected -> final transcribe (dur=%.2fs)",
                        sil_ms, dur,
                    )
                    final = await self._transcribe_buffer(is_final=True)
                    if final:
                        logger.info("[stream] FINAL: %s", final.text[:80])
                        yield final
                    self._segment_started_at += dur
                    self._buffer.clear()
                    self._last_partial_at = now
                    continue

            # Partials cada N segundos
            if now - self._last_partial_at >= self.config.partial_every_s:
                logger.info("[stream] partial tick dur=%.2fs", dur)
                partial = await self._transcribe_buffer(is_final=False)
                if partial:
                    logger.info("[stream] partial: %s", partial.text[:80])
                    yield partial
                self._last_partial_at = now

        # Flush al cerrar
        if self._buffer:
            logger.info(
                "[stream] flushing %d bytes (%.2fs) at end of stream",
                len(self._buffer), self._segment_duration_s(),
            )
            final = await self._transcribe_buffer(is_final=True)
            if final:
                yield final
            self._buffer.clear()
        logger.info("[stream] consume finished, total chunks=%d bytes=%d", chunk_count, bytes_total)
