"""Endpoints HTTP de audio.

POST /api/audio/transcribe                -> texto + segmentos
POST /api/audio/transcribe-and-extract    -> texto + sugerencias validadas
GET  /api/audio/providers                 -> capabilities por provider
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)

from app.api.deps import (
    get_app_settings,
    get_cloudflare_provider,
    get_ollama_provider,
    get_persistence_store,
    get_questionnaire_engine,
)
from app.api.security import enforce_internal_api_key, internal_api_key_header
from app.core.config import Settings, get_settings
from app.models.extraction_contract import ExtractionResponseV1
from app.models.legacy_adapter import build_quality_report, legacy_to_v1
from app.models.suggestion import ExtractFromTextResponse, ValidatedSuggestion
from app.models.suggestion import ExtractFromTextRequest
from app.services.audio.base import Segment, TranscriptResult
from app.services.audio import available_providers, get_provider
from app.services.audio.clinical_prompt import build_clinical_prompt
from app.services.audio.extraction_v1 import (
    apply_audio_evidence_alignment,
    extraction_text_for_module,
    transcript_turns_v1,
    transcription_meta_v1,
)
from app.services.audio.registry import get_streaming_provider
from app.services.audio.streaming import StreamConfig, StreamingTranscriber
from app.services.audio.transcription_service import transcribe_upload
from app.services.graph_mapping_engine import build_graph_report
from app.services.risk_flag_policy import apply_risk_flags
from app.services.extraction_service import extract_from_text, merge_suggestions
from app.services.extraction_guard import (
    MODULE_WIDE_NARROW_THRESHOLD,
    ground_and_filter_llm,
    narrow_questions_by_relevance,
)
from app.services.llm_provider import CloudflareProvider, OllamaProvider
from app.services.question_family_builder import enrich_questions_with_ai_context
from app.services.questionnaire_engine import QuestionnaireEngine
from app.api.routes_ia import (
    _extract_validated_suggestions,
    is_module_wide,
    resolve_questions,
)
from app.services.provider_policy import enforce_audio_provider_allowed


logger = logging.getLogger(__name__)

router = APIRouter()
v1_router = APIRouter()


def _enforce_audio_model_allowed(model: str | None, settings: Settings) -> None:
    """Evita pedir un modelo no descargado (descargas enormes / fallo)."""
    if model and model not in settings.audio_allowed_models:
        raise HTTPException(
            status_code=400,
            detail=f"Modelo de audio no permitido: {model}. Permitidos: {settings.audio_allowed_models}",
        )


def _turn_from_partial(session_id: str, index: int, partial) -> dict[str, Any]:
    return {
        "turn_id": f"{session_id}-turn-{index:04d}",
        "speaker_cluster": None,
        "speaker_role": "unknown",
        "start": partial.start,
        "end": partial.end,
        "text": partial.text.strip(),
    }


def _segments_from_turns(turns: list[dict[str, Any]]) -> list[Segment]:
    return [
        Segment(
            start=float(turn.get("start") or 0.0),
            end=float(turn.get("end") or 0.0),
            text=str(turn.get("text") or ""),
            speaker=turn.get("speaker_cluster"),
        )
        for turn in turns
        if str(turn.get("text") or "").strip()
    ]


def _normalize_for_alignment(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\sáéíóúÁÉÍÓÚñÑüÜ]", " ", text).lower()).strip()


def _evidence_matches_turn(evidence: str, normalized_turn: str) -> bool:
    if not evidence or not normalized_turn:
        return False
    return evidence in normalized_turn


def _apply_turn_evidence_metadata(
    suggestions: list[Any],
    turns_snapshot: tuple[dict[str, Any], ...],
) -> list[Any]:
    """Atribuye turnos/timestamps de forma determinista desde la evidencia."""
    enriched = []
    normalized_turns = [
        (turn, _normalize_for_alignment(str(turn.get("text") or "")))
        for turn in turns_snapshot
    ]
    turns_by_id = {str(turn.get("turn_id")): (turn, normalized) for turn, normalized in normalized_turns}
    for suggestion in suggestions:
        evidence = _normalize_for_alignment(str(getattr(suggestion, "evidence", "") or ""))
        proposed_ids = [str(turn_id) for turn_id in getattr(suggestion, "evidence_turn_ids", [])]
        valid_proposed = [
            turn
            for turn_id in proposed_ids
            for turn, normalized in [turns_by_id.get(turn_id, ({}, ""))]
            if turn and _evidence_matches_turn(evidence, normalized)
        ]
        matches = [
            turn
            for turn, normalized in normalized_turns
            if _evidence_matches_turn(evidence, normalized)
        ]
        if valid_proposed:
            matched = valid_proposed
        elif len(matches) == 1:
            matched = matches
        elif len(matches) > 1 and len(evidence) >= 16 and len(evidence.split()) >= 3:
            matched = [matches[-1]]
        else:
            matched = []
        if not matched:
            enriched.append(
                suggestion.model_copy(
                    update={
                        "evidence_turn_ids": [],
                        "speaker_cluster": None,
                        "audio_start": None,
                        "audio_end": None,
                    }
                )
            )
            continue
        clusters = {
            turn.get("speaker_cluster")
            for turn in matched
            if turn.get("speaker_cluster")
        }
        updates: dict[str, Any] = {
            "evidence_turn_ids": [str(turn["turn_id"]) for turn in matched if turn.get("turn_id")],
            "audio_start": min(float(turn.get("start") or 0.0) for turn in matched),
            "audio_end": max(float(turn.get("end") or 0.0) for turn in matched),
        }
        if len(clusters) == 1:
            updates["speaker_cluster"] = next(iter(clusters))
        enriched.append(suggestion.model_copy(update=updates))
    return enriched


@router.get("/providers")
def list_providers(settings: Settings = Depends(get_app_settings)) -> dict[str, Any]:
    caps = []
    for name in available_providers():
        try:
            provider = get_provider(name)
            cap = provider.capabilities()
            # Expone modelos seleccionables para providers que lo soportan.
            if cap.get("supports_model_selection"):
                cap["models"] = settings.audio_allowed_models
            caps.append(cap)
        except Exception as exc:  # noqa: BLE001
            caps.append({"name": name, "error": str(exc)})
    return {"providers": caps}


@router.post("/transcribe")
async def transcribe(
    audio: UploadFile = File(..., description="WAV/MP3/M4A/WebM/OGG"),
    provider: str | None = Form(default=None),
    model: str | None = Form(default=None),
    language: str | None = Form(default=None),
    diarize: bool | None = Form(default=None),
    use_clinical_prompt: bool = Form(default=True),
    initial_prompt: str | None = Form(default=None),
    use_cache: bool = Form(default=True),
    settings: Settings = Depends(get_app_settings),
    engine: QuestionnaireEngine = Depends(get_questionnaire_engine),
) -> dict[str, Any]:
    raw = await audio.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Audio vacio")
    enforce_audio_provider_allowed(provider, settings)
    _enforce_audio_model_allowed(model, settings)

    prompt = initial_prompt
    if prompt is None and use_clinical_prompt:
        prompt = build_clinical_prompt(engine.data, extra=settings.audio_initial_prompt)

    try:
        result = transcribe_upload(
            raw_bytes=raw,
            filename=audio.filename or "audio.bin",
            settings=settings,
            provider_name=provider,
            language=language,
            initial_prompt=prompt,
            diarize=diarize,
            use_cache=use_cache,
            model=model,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return result.to_dict()


@router.post("/transcribe-and-extract")
async def transcribe_and_extract(
    audio: UploadFile = File(...),
    module: str = Form(...),
    section: str | None = Form(default=None),
    provider: str | None = Form(default=None),
    model: str | None = Form(default=None),
    ia_provider: str | None = Form(default=None),
    language: str | None = Form(default=None),
    diarize: bool | None = Form(default=None),
    use_clinical_prompt: bool = Form(default=True),
    use_cache: bool = Form(default=True),
    settings: Settings = Depends(get_app_settings),
    engine: QuestionnaireEngine = Depends(get_questionnaire_engine),
    ollama: OllamaProvider = Depends(get_ollama_provider),
    cloudflare: CloudflareProvider | None = Depends(get_cloudflare_provider),
) -> dict[str, Any]:
    if module not in {"history", "exam"}:
        raise HTTPException(status_code=400, detail="module debe ser history|exam")

    raw = await audio.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Audio vacio")
    enforce_audio_provider_allowed(provider, settings)
    _enforce_audio_model_allowed(model, settings)

    prompt = (
        build_clinical_prompt(engine.data, extra=settings.audio_initial_prompt)
        if use_clinical_prompt
        else (settings.audio_initial_prompt or None)
    )

    try:
        transcription = transcribe_upload(
            raw_bytes=raw,
            filename=audio.filename or "audio.bin",
            settings=settings,
            provider_name=provider,
            language=language,
            initial_prompt=prompt,
            diarize=diarize,
            use_cache=use_cache,
            model=model,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    questions, section_label = resolve_questions(
        engine=engine, module=module, section=section
    )

    text = transcription.text
    # Module-wide = muchas preguntas -> pre-filtra por relevancia antes del LLM.
    extraction_questions = enrich_questions_with_ai_context(questions)
    if len(questions) > MODULE_WIDE_NARROW_THRESHOLD:
        narrowed = narrow_questions_by_relevance(questions, text)
        if narrowed:
            extraction_questions = narrowed

    chosen_ia = (ia_provider or settings.ia_provider).strip().lower()
    if chosen_ia not in {"heuristic", "ollama", "cloudflare", "both", "both_cloudflare"}:
        chosen_ia = settings.ia_provider
    ia_provider = chosen_ia  # reusa variable abajo
    raw_suggestions = []
    extract_started = time.perf_counter()
    if ia_provider in {"ollama", "both"}:
        raw_suggestions = ground_and_filter_llm(
            ollama.extract(text=text, module=module, section=section_label, questions=extraction_questions),
            extraction_questions,
            text,
        )
    if ia_provider in {"cloudflare", "both_cloudflare"}:
        if not cloudflare:
            raise HTTPException(
                status_code=500,
                detail="Cloudflare provider no configurado",
            )
        raw_suggestions = ground_and_filter_llm(
            cloudflare.extract(text=text, module=module, section=section_label, questions=extraction_questions),
            extraction_questions,
            text,
        )
    if ia_provider in {"heuristic", "both", "both_cloudflare"}:
        heuristic = extract_from_text(text=text, module=module, section=section_label, questions=extraction_questions)
        if ia_provider == "heuristic":
            raw_suggestions = heuristic
        else:
            raw_suggestions = merge_suggestions(raw_suggestions, heuristic)

    validated: list[ValidatedSuggestion] = engine.validate_suggestions(raw_suggestions)
    extract_ms = (time.perf_counter() - extract_started) * 1000.0

    model_used = None
    if ia_provider == "ollama":
        model_used = settings.ollama_model
    elif ia_provider == "cloudflare":
        model_used = settings.cloudflare_model
    elif ia_provider == "both":
        model_used = f"{settings.ollama_model} + heuristic"
    elif ia_provider == "both_cloudflare":
        model_used = f"{settings.cloudflare_model} + heuristic"

    response = ExtractFromTextResponse(
        module=module,
        section=section_label,
        suggestions=validated,
        extract_ms=round(extract_ms, 1),
        ia_provider_used=ia_provider,
        ia_model_used=model_used,
    )
    payload = response.model_dump()
    payload["transcription"] = transcription.to_dict()
    return payload


@v1_router.post("/transcribe-and-extract", response_model=ExtractionResponseV1)
async def transcribe_and_extract_v1(
    audio: UploadFile = File(...),
    module: str = Form(...),
    section: str | None = Form(default=None),
    session_id: str | None = Form(default=None),
    provider: str | None = Form(default=None),
    model: str | None = Form(default=None),
    ia_provider: str | None = Form(default=None),
    ia_model: str | None = Form(default=None),
    language: str | None = Form(default=None),
    diarize: bool | None = Form(default=None),
    use_clinical_prompt: bool = Form(default=True),
    use_cache: bool = Form(default=True),
    settings: Settings = Depends(get_app_settings),
    engine: QuestionnaireEngine = Depends(get_questionnaire_engine),
    ollama: OllamaProvider = Depends(get_ollama_provider),
    cloudflare: CloudflareProvider | None = Depends(get_cloudflare_provider),
    store=Depends(get_persistence_store),
    internal_api_key: str | None = Depends(internal_api_key_header),
) -> ExtractionResponseV1:
    enforce_internal_api_key(settings, internal_api_key)
    if module not in {"history", "exam"}:
        raise HTTPException(status_code=400, detail="module debe ser history|exam")

    raw = await audio.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Audio vacio")
    enforce_audio_provider_allowed(provider, settings)
    _enforce_audio_model_allowed(model, settings)

    prompt = (
        build_clinical_prompt(engine.data, extra=settings.audio_initial_prompt)
        if use_clinical_prompt
        else (settings.audio_initial_prompt or None)
    )

    try:
        transcription = transcribe_upload(
            raw_bytes=raw,
            filename=audio.filename or "audio.bin",
            settings=settings,
            provider_name=provider,
            language=language,
            initial_prompt=prompt,
            diarize=diarize,
            use_cache=use_cache,
            model=model,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    questions, section_label = resolve_questions(
        engine=engine, module=module, section=section
    )
    request = ExtractFromTextRequest(
        module=module,  # type: ignore[arg-type]
        section=section_label,
        # Si la transcripcion esta diarizada, extrae solo los turnos del hablante
        # esperado (paciente en history, medico en exam). El transcript completo
        # se conserva para meta/alineacion de evidencia.
        text=extraction_text_for_module(transcription, module),
        ia_provider=ia_provider,
        ia_model=ia_model,
        transcript_turns=[
            turn.model_dump(exclude_none=True)
            for turn in transcript_turns_v1(transcription)
        ],
    )
    suggestions, _elapsed_ms, resolved_ia, model_used, clinical_summary = _extract_validated_suggestions(
        request=request,
        questions=questions,
        engine=engine,
        settings=settings,
        ollama=ollama,
        cloudflare=cloudflare,
    )

    v1_suggestions = [legacy_to_v1(suggestion) for suggestion in suggestions]
    graph_report = build_graph_report(
        module_entry_question_id=engine.data.get(module, {}).get("entry_question_id"),
        questions=questions,
        suggestions=v1_suggestions,
    )
    # Ver routes_ia.extract_v1: en module-wide no aplica reachability-discard
    # (entrevista libre, no recorrido secuencial). Solo en seccion guiada.
    discarded_ids = {item["question_id"] for item in graph_report.discarded}
    if discarded_ids and not is_module_wide(section_label):
        v1_suggestions = [
            suggestion.model_copy(
                update={
                    "technical_status": "discarded_by_graph",
                    "reason": "not_reachable_from_selected_path",
                }
            )
            if suggestion.question_id in discarded_ids
            else suggestion
            for suggestion in v1_suggestions
        ]

    v1_suggestions = apply_audio_evidence_alignment(v1_suggestions, transcription)
    v1_suggestions = apply_risk_flags(
        v1_suggestions,
        module=module,
        provider=resolved_ia,
        require_audio_timestamps=True,
    )

    from app.api.routes_sessions import persist_suggestions

    persist_suggestions(store, session_id, v1_suggestions)

    return ExtractionResponseV1(
        module=module,  # type: ignore[arg-type]
        section=section_label,
        suggestions=v1_suggestions,
        graph_report=graph_report,
        quality_report=build_quality_report(
            questions_considered=len(questions),
            suggestions=v1_suggestions,
            provider=resolved_ia,
            model=model_used or "",
            profile=getattr(settings, "deployment_profile", "demo") or "demo",
            extra={
                "empty_generation_count": 1 if not v1_suggestions else 0,
                "missing_required": len(graph_report.missing_required),
            },
        ),
        transcription=transcription_meta_v1(transcription),
        clinical_summary=clinical_summary,
    )


@router.websocket("/stream")
async def stream(websocket: WebSocket) -> None:
    """WebSocket de streaming.

    Cliente:
      1. connect ws://host/api/audio/stream?provider=faster_whisper&language=es
      2. envia bytes PCM s16le mono 16kHz (frames de 20-100 ms).
      3. recibe JSON {"text", "is_final", "start", "end"}.
      4. envia "__end__" cuando termina de grabar.
      5. recibe JSON {"done": true} cuando el servidor termino de procesar.
      6. cierra el socket.
    """
    await websocket.accept()
    settings = get_settings()
    qs = websocket.query_params
    requested_provider = qs.get("provider")
    provider_name = settings.audio_stream_provider or requested_provider or settings.audio_provider
    language = qs.get("language") or settings.audio_language

    logger.info("[stream] cliente conectado provider=%s lang=%s", provider_name, language)
    await websocket.send_json(
        {"type": "connected", "provider": provider_name, "language": language}
    )

    try:
        await websocket.send_json({"type": "loading_model", "provider": provider_name})
        if (
            requested_provider
            and not settings.audio_stream_provider
        ):
            requested = get_provider(requested_provider)
            if not requested.supports_streaming:
                logger.info(
                    "[stream] provider %s no soporta streaming nativo; usando provider dedicado",
                    requested_provider,
                )
                provider_name = settings.audio_stream_provider or settings.audio_provider
        provider = await asyncio.to_thread(get_streaming_provider, provider_name)
        await websocket.send_json({"type": "ready", "provider": provider_name})
    except Exception as exc:  # noqa: BLE001
        logger.exception("[stream] provider init failed: %s", exc)
        await websocket.send_json({"error": f"provider invalido: {exc}"})
        await websocket.close()
        return

    # Hint clinico al vuelo
    try:
        engine = QuestionnaireEngine(settings.questionnaire_path)
        initial_prompt = build_clinical_prompt(
            engine.data, extra=settings.audio_initial_prompt
        )
    except Exception:  # noqa: BLE001
        initial_prompt = settings.audio_initial_prompt or None

    cfg = StreamConfig(
        partial_every_s=float(qs.get("partial_every_s", str(settings.audio_stream_partial_every_s))),
        min_segment_s=float(qs.get("min_segment_s", str(settings.audio_stream_min_segment_s))),
        max_segment_s=float(qs.get("max_segment_s", str(settings.audio_stream_max_segment_s))),
        silence_ms_to_close=int(qs.get("silence_ms_to_close", str(settings.audio_stream_silence_ms))),
        language=language,
        initial_prompt=initial_prompt,
    )
    transcriber = StreamingTranscriber(provider, cfg)

    async def chunks():
        chunk_count = 0
        byte_count = 0
        try:
            while True:
                msg = await websocket.receive()
                if msg.get("type") == "websocket.disconnect":
                    break
                data = msg.get("bytes")
                if data is None:
                    text = msg.get("text")
                    if text == "__end__":
                        logger.info("[stream] received __end__ from client")
                        break
                    continue
                chunk_count += 1
                byte_count += len(data)
                if chunk_count == 1 or chunk_count % 25 == 0:
                    await websocket.send_json(
                        {
                            "type": "audio_received",
                            "chunks": chunk_count,
                            "bytes": byte_count,
                        }
                    )
                yield data
        except WebSocketDisconnect:
            return

    try:
        async for partial in transcriber.consume(chunks()):
            await websocket.send_json(
                {
                    "type": "transcribing",
                    "is_final": partial.is_final,
                    "start": partial.start,
                    "end": partial.end,
                    "provider": provider_name,
                }
            )
            await websocket.send_json(
                {
                    "type": "final" if partial.is_final else "partial",
                    "text": partial.text,
                    "is_final": partial.is_final,
                    "start": partial.start,
                    "end": partial.end,
                    "provider": provider_name,
                }
            )
        # Signal client that server finished flushing.
        await websocket.send_json({"type": "done", "done": True})
        logger.info("[stream] done sent to client")
    except WebSocketDisconnect:
        logger.info("[stream] client disconnected during processing")
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception("[stream] error: %s", exc)
        try:
            await websocket.send_json({"error": str(exc)})
        except Exception:  # noqa: BLE001
            pass
    finally:
        try:
            await websocket.close()
        except Exception:  # noqa: BLE001
            pass


@v1_router.websocket("/stream-and-extract")
async def stream_and_extract(websocket: WebSocket) -> None:
    """Streaming v1: audio -> transcript turns -> sugerencias parciales/finales."""
    await websocket.accept()
    settings = get_settings()
    qs = websocket.query_params
    module = (qs.get("module") or "history").strip().lower()
    if module not in {"history", "exam"}:
        await websocket.send_json({"type": "error", "error": "module debe ser history|exam"})
        await websocket.close()
        return

    try:
        enforce_internal_api_key(settings, websocket.headers.get("x-internal-api-key"))
    except Exception as exc:  # noqa: BLE001
        await websocket.send_json({"type": "error", "error": str(exc)})
        await websocket.close()
        return

    requested_provider = qs.get("provider")
    provider_name = settings.audio_stream_provider or requested_provider or settings.audio_provider
    language = qs.get("language") or settings.audio_language
    section = qs.get("section")
    ia_provider = qs.get("ia_provider")
    ia_model = qs.get("ia_model")
    session_id = (qs.get("session_id") or f"live-{uuid.uuid4().hex[:12]}").strip()
    await websocket.send_json(
        {
            "type": "connected",
            "provider": provider_name,
            "language": language,
            "module": module,
            "session_id": session_id,
        }
    )

    try:
        await websocket.send_json({"type": "loading_model", "provider": provider_name})
        if requested_provider and not settings.audio_stream_provider:
            requested = get_provider(requested_provider)
            if not requested.supports_streaming:
                provider_name = settings.audio_stream_provider or settings.audio_provider
        provider = await asyncio.to_thread(get_streaming_provider, provider_name)
        await websocket.send_json({"type": "ready", "provider": provider_name})
    except Exception as exc:  # noqa: BLE001
        logger.exception("[stream_extract] provider init failed: %s", exc)
        await websocket.send_json({"type": "error", "error": f"provider invalido: {exc}"})
        await websocket.close()
        return

    engine = get_questionnaire_engine()
    ollama = get_ollama_provider()
    cloudflare = get_cloudflare_provider()
    questions, section_label = resolve_questions(
        engine=engine,
        module=module,
        section=section,
    )

    try:
        initial_prompt = build_clinical_prompt(
            engine.data,
            extra=settings.audio_initial_prompt,
        )
    except Exception:  # noqa: BLE001
        initial_prompt = settings.audio_initial_prompt or None

    cfg = StreamConfig(
        partial_every_s=float(qs.get("partial_every_s", str(settings.audio_stream_partial_every_s))),
        min_segment_s=float(qs.get("min_segment_s", str(settings.audio_stream_min_segment_s))),
        max_segment_s=float(qs.get("max_segment_s", str(settings.audio_stream_max_segment_s))),
        silence_ms_to_close=int(qs.get("silence_ms_to_close", str(settings.audio_stream_silence_ms))),
        language=language,
        initial_prompt=initial_prompt,
    )
    transcriber = StreamingTranscriber(provider, cfg)
    turns: list[dict[str, Any]] = []
    audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=200)
    extraction_queue: asyncio.Queue[str | None] = asyncio.Queue(maxsize=20)
    send_lock = asyncio.Lock()

    async def send_event(payload: dict[str, Any]) -> None:
        async with send_lock:
            await websocket.send_json(payload)

    async def receive_audio() -> None:
        chunk_count = 0
        byte_count = 0
        try:
            while True:
                msg = await websocket.receive()
                if msg.get("type") == "websocket.disconnect":
                    break
                data = msg.get("bytes")
                if data is None:
                    text = msg.get("text")
                    if text == "__end__":
                        logger.info("[stream_extract] received __end__")
                        break
                    continue
                chunk_count += 1
                byte_count += len(data)
                if chunk_count == 1 or chunk_count % 25 == 0:
                    await send_event(
                        {
                            "type": "audio_received",
                            "chunks": chunk_count,
                            "bytes": byte_count,
                        }
                    )
                await audio_queue.put(data)
        except WebSocketDisconnect:
            return
        finally:
            await audio_queue.put(None)

    async def chunks():
        while True:
            item = await audio_queue.get()
            if item is None:
                break
            yield item

    async def emit_suggestions(event_type: str) -> None:
        turns_snapshot = tuple(dict(turn) for turn in turns)
        extraction_revision = len(turns_snapshot)
        processed_through_turn_id = (
            str(turns_snapshot[-1].get("turn_id")) if turns_snapshot else None
        )
        transcript = " ".join(
            turn["text"] for turn in turns_snapshot if turn.get("text")
        ).strip()
        if not transcript:
            return
        await send_event(
            {
                "type": "extracting",
                "event": event_type,
                "extraction_revision": extraction_revision,
                "processed_through_turn_id": processed_through_turn_id,
                "turn_ids": [turn["turn_id"] for turn in turns_snapshot],
            }
        )
        request = ExtractFromTextRequest(
            module=module,  # type: ignore[arg-type]
            section=section_label,
            text=transcript,
            ia_provider=ia_provider,
            ia_model=ia_model,
            transcript_turns=list(turns_snapshot),
        )
        suggestions, _elapsed_ms, resolved_ia, model_used, clinical_summary = await asyncio.to_thread(
            _extract_validated_suggestions,
            request=request,
            questions=questions,
            engine=engine,
            settings=settings,
            ollama=ollama,
            cloudflare=cloudflare,
        )
        v1_suggestions = [legacy_to_v1(suggestion) for suggestion in suggestions]
        graph_report = build_graph_report(
            module_entry_question_id=engine.data.get(module, {}).get("entry_question_id"),
            questions=questions,
            suggestions=v1_suggestions,
        )
        discarded_ids = {item["question_id"] for item in graph_report.discarded}
        if discarded_ids and not is_module_wide(section_label):
            v1_suggestions = [
                suggestion.model_copy(
                    update={
                        "technical_status": "discarded_by_graph",
                        "reason": "not_reachable_from_selected_path",
                    }
                )
                if suggestion.question_id in discarded_ids
                else suggestion
                for suggestion in v1_suggestions
            ]

        transcription = TranscriptResult(
            text=transcript,
            segments=_segments_from_turns(list(turns_snapshot)),
            language=language,
            provider=provider_name,
            model=getattr(provider, "model", "") or getattr(provider, "model_size", "") or "",
        )
        v1_suggestions = apply_audio_evidence_alignment(v1_suggestions, transcription)
        v1_suggestions = _apply_turn_evidence_metadata(v1_suggestions, turns_snapshot)
        v1_suggestions = apply_risk_flags(
            v1_suggestions,
            module=module,
            provider=resolved_ia,
            require_audio_timestamps=True,
        )
        response = ExtractionResponseV1(
            module=module,  # type: ignore[arg-type]
            section=section_label,
            suggestions=v1_suggestions,
            graph_report=graph_report,
            quality_report=build_quality_report(
                questions_considered=len(questions),
                suggestions=v1_suggestions,
                provider=resolved_ia,
                model=model_used or "",
                profile=getattr(settings, "deployment_profile", "demo") or "demo",
                extra={
                    "empty_generation_count": 1 if not v1_suggestions else 0,
                    "missing_required": len(graph_report.missing_required),
                },
            ),
            transcription=transcription_meta_v1(transcription),
            clinical_summary=clinical_summary,
        )
        await send_event(
            {
                "type": event_type,
                "extraction_revision": extraction_revision,
                "processed_through_turn_id": processed_through_turn_id,
                "processed_turn_ids": [turn["turn_id"] for turn in turns_snapshot],
                "response": response.model_dump(mode="json"),
            }
        )

    async def extraction_worker() -> None:
        pending_final = False
        while True:
            should_stop = False
            event_type = await extraction_queue.get()
            if event_type is None:
                if pending_final or turns:
                    event_type = "suggestions.final"
                    should_stop = True
                else:
                    break
            while not extraction_queue.empty():
                extra = extraction_queue.get_nowait()
                if extra is None:
                    pending_final = True
                    should_stop = True
                    continue
                event_type = "suggestions.final" if pending_final else extra
            try:
                await emit_suggestions(event_type)
            except Exception as exc:  # noqa: BLE001
                logger.exception("[stream_extract] extraction failed: %s", exc)
                try:
                    await send_event(
                        {
                            "type": "extraction_error",
                            "error": str(exc),
                            "turn_ids": [turn["turn_id"] for turn in turns],
                        }
                    )
                except Exception:  # noqa: BLE001
                    pass
            if pending_final or should_stop:
                break

    receiver_task = asyncio.create_task(receive_audio())
    extractor_task = asyncio.create_task(extraction_worker())

    try:
        async for partial in transcriber.consume(chunks()):
            await send_event(
                {
                    "type": "transcribing",
                    "is_final": partial.is_final,
                    "start": partial.start,
                    "end": partial.end,
                    "provider": provider_name,
                }
            )
            if partial.is_final:
                turn = _turn_from_partial(session_id, len(turns) + 1, partial)
                turns.append(turn)
                await send_event({"type": "transcript.final", "turn": turn})
                await extraction_queue.put("suggestions.partial")
            else:
                await send_event(
                    {
                        "type": "transcript.partial",
                        "text": partial.text,
                        "start": partial.start,
                        "end": partial.end,
                        "provider": provider_name,
                    }
                )
        await send_event({"type": "audio.done"})
        await send_event({"type": "suggestions.finalizing"})
        await extraction_queue.put(None)
        await extractor_task
        await receiver_task
        await send_event({"type": "done"})
    except WebSocketDisconnect:
        logger.info("[stream_extract] client disconnected")
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception("[stream_extract] error: %s", exc)
        try:
            await websocket.send_json({"type": "error", "error": str(exc)})
        except Exception:  # noqa: BLE001
            pass
    finally:
        for task in (receiver_task, extractor_task):
            if not task.done():
                task.cancel()
        try:
            await websocket.close()
        except Exception:  # noqa: BLE001
            pass
