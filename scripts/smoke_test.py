from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.extraction_service import extract_from_text
from app.services.questionnaire_engine import QuestionnaireEngine


def main() -> None:
    engine = QuestionnaireEngine(Path("app/data/json_IA.json"))

    cases = [
        {
            "module": "history",
            "section": "HABITOS",
            "text": "El paciente dice que no fuma actualmente, pero fumo hasta hace tres anos. No consume alcohol.",
        },
        {
            "module": "history",
            "section": "ALERGIAS",
            "text": "El paciente refiere alergia a la penicilina.",
        },
        {
            "module": "exam",
            "section": "CABEZA",
            "text": "La boca esta normal. El oido derecho presenta un tapon de cerumen.",
        },
    ]

    print("Modulos:", ", ".join(engine.get_modules()))
    print("Secciones history:", len(engine.get_sections("history")))
    print("Secciones exam:", len(engine.get_sections("exam")))
    print()

    for case in cases:
        questions = engine.get_questions_by_section(case["module"], case["section"])
        raw_suggestions = extract_from_text(
            text=case["text"],
            module=case["module"],
            section=case["section"],
            questions=questions,
        )
        suggestions = engine.validate_suggestions(raw_suggestions)

        print(f"Caso: {case['module']} / {case['section']}")
        print(f"Texto: {case['text']}")
        if not suggestions:
            print("Sin sugerencias")
        for suggestion in suggestions:
            labels = ", ".join(suggestion.selected_labels) or suggestion.free_text or "-"
            print(
                f"- {suggestion.question_id} | {suggestion.question_text} -> "
                f"{labels} | confianza={suggestion.confidence}"
            )
        print()


if __name__ == "__main__":
    main()
