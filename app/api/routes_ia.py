import time

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import (
    get_app_settings,
    get_cloudflare_provider,
    get_ollama_provider,
    get_persistence_store,
    get_questionnaire_engine,
)
from app.api.security import enforce_internal_api_key, internal_api_key_header
from app.core.config import Settings
from app.models.extraction_contract import ExtractionResponseV1
from app.models.legacy_adapter import build_quality_report, legacy_to_v1
from app.models.suggestion import ExtractFromTextRequest, ExtractFromTextResponse
from app.models.suggestion import ValidatedSuggestion
from app.services.clinical_summary_service import generate_clinical_summary
from app.services.extraction_service import extract_from_text, merge_suggestions
from app.services.extraction_guard import (
    MODULE_WIDE_NARROW_THRESHOLD,
    ground_and_filter_llm,
    narrow_questions_by_relevance,
)
from app.services.field_extraction_service import extract_small_batches
from app.services.graph_mapping_engine import build_graph_report
from app.services.llm_provider import CloudflareProvider, OllamaProvider
from app.services.questionnaire_engine import QuestionnaireEngine
from app.services.risk_flag_policy import apply_risk_flags
from app.services.provider_policy import enforce_ia_provider_allowed

router = APIRouter()
v1_router = APIRouter()


ALLOWED_IA_PROVIDERS = {"heuristic", "ollama", "cloudflare", "both", "both_cloudflare"}


def _resolve_provider(requested: str | None, settings: Settings) -> str:
    provider = (requested or settings.ia_provider).strip().lower()
    if provider not in ALLOWED_IA_PROVIDERS:
        return settings.ia_provider
    return provider


def _resolve_ollama_model(requested: str | None, settings: Settings) -> str:
    model = (requested or settings.ollama_model).strip()
    allowed = set(getattr(settings, "ollama_allowed_models", []) or [])
    if allowed and model not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Modelo Ollama no permitido: {model}",
        )
    return model


def _ollama_for_model(ollama: OllamaProvider, model: str, settings: Settings) -> OllamaProvider:
    if model == settings.ollama_model:
        return ollama
    if hasattr(ollama, "with_model"):
        return ollama.with_model(model)
    # Para tests con fakes simples: conserva el objeto y deja visible el override.
    setattr(ollama, "model", model)
    return ollama


def _resolve_cloudflare_model(requested: str | None, settings: Settings) -> str:
    model = (requested or settings.cloudflare_model).strip()
    allowed = set(getattr(settings, "cloudflare_allowed_models", []) or [])
    if allowed and model not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Modelo Cloudflare no permitido: {model}",
        )
    return model


def _cloudflare_for_model(
    cloudflare: CloudflareProvider, model: str, settings: Settings
) -> CloudflareProvider:
    if model == settings.cloudflare_model:
        return cloudflare
    if hasattr(cloudflare, "with_model"):
        return cloudflare.with_model(model)
    setattr(cloudflare, "model", model)
    return cloudflare


def _model_used(
    provider: str,
    settings: Settings,
    ollama_model: str | None = None,
    cloudflare_model: str | None = None,
) -> str | None:
    active_ollama_model = ollama_model or settings.ollama_model
    active_cf_model = cloudflare_model or settings.cloudflare_model
    if provider == "ollama":
        return active_ollama_model
    if provider == "cloudflare":
        return active_cf_model
    if provider == "both":
        return f"{active_ollama_model} + heuristic"
    if provider == "both_cloudflare":
        return f"{active_cf_model} + heuristic"
    return None


def _extract_validated_suggestions(
    *,
    request: ExtractFromTextRequest,
    questions: list[dict],
    engine: QuestionnaireEngine,
    settings: Settings,
    ollama: OllamaProvider,
    cloudflare: CloudflareProvider | None,
) -> tuple[list[ValidatedSuggestion], float, str, str | None, str | None]:
    provider = _resolve_provider(request.ia_provider, settings)
    enforce_ia_provider_allowed(provider, settings)
    ollama_model = (
        _resolve_ollama_model(request.ia_model, settings)
        if provider in {"ollama", "both"}
        else None
    )
    active_ollama = (
        _ollama_for_model(ollama, ollama_model, settings) if ollama_model else ollama
    )
    cloudflare_model = (
        _resolve_cloudflare_model(request.ia_model, settings)
        if provider in {"cloudflare", "both_cloudflare"}
        else None
    )
    active_cloudflare = (
        _cloudflare_for_model(cloudflare, cloudflare_model, settings)
        if (cloudflare and cloudflare_model)
        else cloudflare
    )

    # Resumen clinico intermedio (opt-in). Se genera con el mismo proveedor LLM,
    # se devuelve como artefacto y se pasa como contexto de apoyo a la
    # extraccion. La evidencia sigue anclada al transcript en ground_and_filter.
    clinical_summary: str | None = None
    clinical_context: str | None = None
    if getattr(settings, "ia_clinical_summary_enabled", False):
        summarizer = None
        if provider in {"ollama", "both"}:
            summarizer = active_ollama
        elif provider in {"cloudflare", "both_cloudflare"} and active_cloudflare:
            summarizer = active_cloudflare
        if summarizer is not None:
            summary = generate_clinical_summary(request.text, summarizer)
            clinical_summary = summary or None
            clinical_context = summary or None
    # En entrevista libre la seccion puede venir vacia (modulo completo). Los
    # extractores solo usan section como contexto del prompt, no para filtrar.
    section_label = request.section or "*"

    # Modulo completo = muchas preguntas. Pre-filtra por relevancia al texto
    # antes de mandar al LLM para evitar alucinacion por sobrecarga de contexto.
    # `questions` completo se conserva fuera para el graph_report.
    extraction_questions = questions
    if len(questions) > MODULE_WIDE_NARROW_THRESHOLD:
        narrowed = narrow_questions_by_relevance(questions, request.text)
        if narrowed:
            extraction_questions = narrowed

    # Solo se pasa cuando hay resumen: mantiene compatibilidad con extractores
    # (fakes/tests) cuya firma de extract no acepta clinical_context.
    extract_extra = {"clinical_context": clinical_context} if clinical_context else {}

    raw_suggestions = []
    started = time.perf_counter()

    # Hito 6.1: si la seccion es grande y el operador activo batch_extraction,
    # usar `extract_small_batches` para acotar contexto por lote. Mantiene el
    # extractor monolitico como default (threshold=0).
    threshold = getattr(settings, "ia_batch_extraction_threshold", 0)
    batch_size = getattr(settings, "ia_batch_extraction_size", 6)
    batch_workers = getattr(settings, "ia_batch_max_workers", 1)
    # Auto-batch en module-wide: mandar muchas preguntas en una sola llamada LLM
    # provoca timeout (Cloudflare corta a los 60s) y/o salida JSON truncada por
    # max_tokens -> 0 sugerencias. Dividir en lotes mantiene cada llamada rapida
    # y dentro del budget de tokens. Se activa por encima del mismo umbral que
    # dispara el narrow (entrevista libre / modulo completo).
    auto_batch = len(extraction_questions) > MODULE_WIDE_NARROW_THRESHOLD
    explicit_batch = threshold > 0 and len(extraction_questions) >= threshold
    use_batch = (auto_batch or explicit_batch) and provider in {
        "ollama",
        "both",
        "cloudflare",
        "both_cloudflare",
    }

    if provider in {"ollama", "both"}:
        if use_batch:
            # Ollama es local: carga un solo modelo. Lotes en paralelo compiten
            # por RAM/GPU -> 500 / timeout / WinError 1450. Serializar (workers=1).
            llm_suggestions = extract_small_batches(
                text=request.text,
                module=request.module,
                section=section_label,
                questions=extraction_questions,
                batch_size=batch_size,
                extractor=active_ollama.extract,
                max_workers=1,
            )
        else:
            llm_suggestions = active_ollama.extract(
                text=request.text,
                module=request.module,
                section=section_label,
                questions=extraction_questions,
                **extract_extra,
            )
        raw_suggestions = ground_and_filter_llm(
            llm_suggestions, extraction_questions, request.text
        )

    if provider in {"cloudflare", "both_cloudflare"}:
        if not cloudflare:
            raise HTTPException(
                status_code=500,
                detail="Cloudflare provider no configurado (faltan CLOUDFLARE_ACCOUNT_ID/TOKEN)",
            )
        if use_batch:
            cf_suggestions = extract_small_batches(
                text=request.text,
                module=request.module,
                section=section_label,
                questions=extraction_questions,
                batch_size=batch_size,
                extractor=active_cloudflare.extract,
                max_workers=batch_workers,
            )
        else:
            cf_suggestions = active_cloudflare.extract(
                text=request.text,
                module=request.module,
                section=section_label,
                questions=extraction_questions,
                **extract_extra,
            )
        raw_suggestions = ground_and_filter_llm(
            cf_suggestions, extraction_questions, request.text
        )

    if provider in {"heuristic", "both", "both_cloudflare"}:
        heuristic_suggestions = extract_from_text(
            text=request.text,
            module=request.module,
            section=section_label,
            questions=extraction_questions,
        )
        if provider == "heuristic":
            raw_suggestions = heuristic_suggestions
        else:
            # both / both_cloudflare: LLM prevalece, heuristico cubre huecos
            raw_suggestions = merge_suggestions(raw_suggestions, heuristic_suggestions)

    suggestions = engine.validate_suggestions(raw_suggestions)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return (
        suggestions,
        elapsed_ms,
        provider,
        _model_used(provider, settings, ollama_model, cloudflare_model),
        clinical_summary,
    )


def _questions_or_404(
    *,
    engine: QuestionnaireEngine,
    module: str,
    section: str,
) -> list[dict]:
    try:
        questions = engine.get_questions_by_section(module, section)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if not questions:
        raise HTTPException(
            status_code=404,
            detail=f"No hay preguntas para modulo={module}, seccion={section}",
        )
    return questions


_MODULE_WIDE_TOKENS = {"", "*", "all", "todas", "todo"}


def is_module_wide(section: str | None) -> bool:
    """True si la seccion pedida significa "modulo completo" (entrevista libre)."""
    return section is None or section.strip().lower() in _MODULE_WIDE_TOKENS


def resolve_questions(
    *,
    engine: QuestionnaireEngine,
    module: str,
    section: str | None,
) -> tuple[list[dict], str]:
    """Devuelve (questions, section_label).

    section_label = "*" cuando se extrae sobre el modulo completo; en ese caso
    se cargan todas las preguntas del modulo y cada sugerencia se ubica en su
    pregunta. Si section es concreta, se filtra como antes.
    """
    if is_module_wide(section):
        try:
            questions = engine.get_questions_by_module(module)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if not questions:
            raise HTTPException(
                status_code=404, detail=f"Modulo sin preguntas: {module}"
            )
        return questions, "*"
    return _questions_or_404(engine=engine, module=module, section=section), section


@router.get("/providers")
def list_ia_providers(
    settings: Settings = Depends(get_app_settings),
    ollama: OllamaProvider = Depends(get_ollama_provider),
    cloudflare: CloudflareProvider | None = Depends(get_cloudflare_provider),
) -> dict:
    """Lista los IA providers conocidos y si estan configurados/listos."""
    items = [
        {
            "name": "heuristic",
            "kind": "local",
            "configured": True,
            "model": None,
            "description": "Extractor por reglas. Sin LLM. Instantaneo.",
        },
        {
            "name": "ollama",
            "kind": "local",
            "configured": bool(ollama),
            "model": settings.ollama_model,
            "models": settings.ollama_allowed_models,
            "endpoint": settings.ollama_base_url,
            "description": "LLM local via Ollama.",
        },
        {
            "name": "cloudflare",
            "kind": "online",
            "configured": cloudflare is not None,
            "model": settings.cloudflare_model,
            "models": settings.cloudflare_allowed_models,
            "description": "Cloudflare Workers AI (free 10k Neurons/dia).",
        },
        {
            "name": "both",
            "kind": "combo",
            "configured": True,
            "model": f"{settings.ollama_model} + heuristic",
            "models": settings.ollama_allowed_models,
            "description": "Ollama prevalece + heuristic cubre huecos.",
        },
        {
            "name": "both_cloudflare",
            "kind": "combo",
            "configured": cloudflare is not None,
            "model": f"{settings.cloudflare_model} + heuristic",
            "models": settings.cloudflare_allowed_models,
            "description": "Cloudflare prevalece + heuristic cubre huecos.",
        },
    ]
    return {"providers": items, "default": settings.ia_provider}


@router.post("/extract-from-text", response_model=ExtractFromTextResponse)
def extract(
    request: ExtractFromTextRequest,
    engine: QuestionnaireEngine = Depends(get_questionnaire_engine),
    settings: Settings = Depends(get_app_settings),
    ollama: OllamaProvider = Depends(get_ollama_provider),
    cloudflare: CloudflareProvider | None = Depends(get_cloudflare_provider),
) -> ExtractFromTextResponse:
    questions, section_label = resolve_questions(
        engine=engine,
        module=request.module,
        section=request.section,
    )
    suggestions, elapsed_ms, provider, model_used, _summary = _extract_validated_suggestions(
        request=request,
        questions=questions,
        engine=engine,
        settings=settings,
        ollama=ollama,
        cloudflare=cloudflare,
    )

    return ExtractFromTextResponse(
        module=request.module,
        section=section_label,
        suggestions=suggestions,
        extract_ms=round(elapsed_ms, 1),
        ia_provider_used=provider,
        ia_model_used=model_used,
    )


@v1_router.post("/extract-from-text", response_model=ExtractionResponseV1)
def extract_v1(
    request: ExtractFromTextRequest,
    engine: QuestionnaireEngine = Depends(get_questionnaire_engine),
    settings: Settings = Depends(get_app_settings),
    ollama: OllamaProvider = Depends(get_ollama_provider),
    cloudflare: CloudflareProvider | None = Depends(get_cloudflare_provider),
    store=Depends(get_persistence_store),
    internal_api_key: str | None = Depends(internal_api_key_header),
) -> ExtractionResponseV1:
    """Extraccion v1 desde texto. Devuelve `ExtractionResponseV1`.

    Diferencias vs endpoint legacy:
    - Salida con contrato versionado (`SCHEMA_VERSION`).
    - Estados separados (`technical_status` + `review_status` + `risk_flags`).
    - `quality_report` agregado.
    - `graph_report` con path, faltantes y descartes fuera de recorrido.
    """
    enforce_internal_api_key(settings, internal_api_key)
    questions, section_label = resolve_questions(
        engine=engine,
        module=request.module,
        section=request.section,
    )
    suggestions, _elapsed_ms, provider, model_used, clinical_summary = _extract_validated_suggestions(
        request=request,
        questions=questions,
        engine=engine,
        settings=settings,
        ollama=ollama,
        cloudflare=cloudflare,
    )

    v1_suggestions = [legacy_to_v1(suggestion) for suggestion in suggestions]
    graph_report = build_graph_report(
        module_entry_question_id=engine.data.get(request.module, {}).get("entry_question_id"),
        questions=questions,
        suggestions=v1_suggestions,
    )
    # En module-wide (entrevista libre) el cuestionario completo no es un unico
    # recorrido secuencial: el paciente salta entre secciones. Un hueco temprano
    # (p.ej. A1-1 no capturado) dejaria "no alcanzable" todo lo de aguas abajo y
    # descartaria sugerencias validas y ancladas. Reachability-discard solo aplica
    # al flujo guiado por seccion; en module-wide el graph_report es informativo.
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
    v1_suggestions = apply_risk_flags(
        v1_suggestions,
        module=request.module,
        provider=provider,
        require_audio_timestamps=False,
    )

    from app.api.routes_sessions import persist_suggestions

    persist_suggestions(store, request.session_id, v1_suggestions)

    return ExtractionResponseV1(
        module=request.module,
        section=section_label,
        suggestions=v1_suggestions,
        graph_report=graph_report,
        quality_report=build_quality_report(
            questions_considered=len(questions),
            suggestions=v1_suggestions,
            provider=provider,
            model=model_used or "",
            profile=getattr(settings, "deployment_profile", "demo") or "demo",
            extra={
                "empty_generation_count": 1 if not v1_suggestions else 0,
                "missing_required": len(graph_report.missing_required),
            },
        ),
        transcription=None,
        clinical_summary=clinical_summary,
    )
