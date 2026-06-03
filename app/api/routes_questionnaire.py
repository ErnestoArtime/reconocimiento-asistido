from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_questionnaire_engine
from app.services.questionnaire_engine import QuestionnaireEngine

router = APIRouter()


@router.get("/modules")
def get_modules(engine: QuestionnaireEngine = Depends(get_questionnaire_engine)) -> dict[str, list[str]]:
    return {"modules": engine.get_modules()}


@router.get("/{module}/sections")
def get_sections(
    module: str,
    engine: QuestionnaireEngine = Depends(get_questionnaire_engine),
) -> dict[str, object]:
    try:
        return {"module": module, "sections": engine.get_sections(module)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{module}/questions")
def get_questions_by_module(
    module: str,
    engine: QuestionnaireEngine = Depends(get_questionnaire_engine),
) -> dict[str, object]:
    """Todas las preguntas del modulo (entrevista libre, sin filtrar seccion)."""
    try:
        questions = engine.get_questions_by_module(module)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {"module": module, "questions": questions}


@router.get("/{module}/sections/{section}/questions")
def get_questions_by_section(
    module: str,
    section: str,
    engine: QuestionnaireEngine = Depends(get_questionnaire_engine),
) -> dict[str, object]:
    try:
        questions = engine.get_questions_by_section(module, section)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return {"module": module, "section": section, "questions": questions}
