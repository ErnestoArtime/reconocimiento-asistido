from typing import Any

from app.models.suggestion import AiSuggestion
from app.services.text_utils import normalize_text


def merge_suggestions(
    primary: list[AiSuggestion],
    secondary: list[AiSuggestion],
) -> list[AiSuggestion]:
    """Une dos listas de sugerencias evitando duplicados por question_id.

    Las sugerencias de primary prevalecen. Las de secondary solo entran si
    aportan una question_id que primary no cubrio.
    """
    seen: set[str] = {item.question_id for item in primary}
    merged = list(primary)
    for item in secondary:
        if item.question_id in seen:
            continue
        merged.append(item)
        seen.add(item.question_id)
    return merged


NEGATION_MARKERS = (
    "no ",
    "niega",
    "nunca",
    "sin ",
)

AFFIRMATION_MARKERS = (
    "si ",
    "actualmente",
    "refiere",
    "presenta",
    "tiene",
    "consume",
    "fuma",
)


def extract_from_text(text: str, module: str, section: str, questions: list[dict[str, Any]]) -> list[AiSuggestion]:
    """Primer extractor determinista.

    Esta capa permite probar el flujo backend y sera reemplazada o complementada
    por un LLM con salida estructurada.
    """
    normalized_text = normalize_text(text)
    suggestions: list[AiSuggestion] = []

    for question in questions:
        question_text = normalize_text(question.get("text", ""))
        question_type = question.get("question_type", "")
        codes = question.get("codes", {})

        if question_type in {"yesno", "yesnoremember"}:
            suggestion = _extract_yes_no(question, question_text, codes, normalized_text, text)
            if suggestion:
                suggestions.append(suggestion)
            continue

        if question_type in {"choice", "multiple"}:
            suggestions.extend(_extract_code_matches(question, codes, normalized_text, text))
            continue

        if question_type == "free":
            suggestion = _extract_free_text(question, codes, normalized_text, text)
            if suggestion:
                suggestions.append(suggestion)

    return suggestions


def _extract_yes_no(
    question: dict[str, Any],
    question_text: str,
    codes: dict[str, str],
    normalized_text: str,
    original_text: str,
) -> AiSuggestion | None:
    topic_tokens = _topic_tokens(question_text)
    if not topic_tokens or not any(token in normalized_text for token in topic_tokens):
        return None

    evidence_text, evidence_normalized = _relevant_evidence(question_text, original_text)
    if not evidence_normalized:
        return None

    yes_code = _find_code(codes, {"si", "s"})
    no_code = _find_code(codes, {"no"})
    selected_code: str | None = None
    confidence = 0.55

    if _is_normal_exam_question(question_text) and _has_abnormal_exam_evidence(question_text, evidence_normalized) and no_code:
        selected_code = no_code
        confidence = 0.78
    elif _is_normal_exam_question(question_text) and "normal" in evidence_normalized and yes_code:
        selected_code = yes_code
        confidence = 0.74
    elif _is_previous_smoking_question(question_text) and _has_previous_smoking_evidence(evidence_normalized) and yes_code:
        selected_code = yes_code
        confidence = 0.76
    elif _is_current_smoking_question(question_text) and _has_stopped_smoking_evidence(evidence_normalized) and no_code:
        selected_code = no_code
        confidence = 0.78
    elif any(marker in evidence_normalized for marker in NEGATION_MARKERS) and no_code:
        selected_code = no_code
        confidence = 0.72
    elif any(marker in evidence_normalized for marker in AFFIRMATION_MARKERS) and yes_code:
        selected_code = yes_code
        confidence = 0.68

    if not selected_code:
        return None

    return AiSuggestion(
        question_id=question["id"],
        selected_codes=[selected_code],
        confidence=confidence,
        evidence=_short_evidence(evidence_text),
    )


def _extract_code_matches(
    question: dict[str, Any],
    codes: dict[str, str],
    normalized_text: str,
    original_text: str,
) -> list[AiSuggestion]:
    selected: list[str] = []
    free_text: str | None = None

    for code, label in codes.items():
        normalized_label = normalize_text(label)
        if normalized_label == "texto libre":
            continue

        if _code_label_matches(normalized_label, normalized_text):
            selected.append(code)

    free_text_code = _find_free_text_code(codes)
    if free_text_code and not selected and _looks_relevant(question, normalized_text):
        selected.append(free_text_code)
        free_text = _short_evidence(original_text)

    if not selected:
        return []

    return [
        AiSuggestion(
            question_id=question["id"],
            selected_codes=selected,
            free_text=free_text,
            confidence=0.7 if free_text is None else 0.52,
            evidence=_short_evidence(original_text),
        )
    ]


def _extract_free_text(
    question: dict[str, Any],
    codes: dict[str, str],
    normalized_text: str,
    original_text: str,
) -> AiSuggestion | None:
    free_text_code = _find_free_text_code(codes)
    if not free_text_code or not _looks_relevant(question, normalized_text):
        return None

    return AiSuggestion(
        question_id=question["id"],
        selected_codes=[free_text_code],
        free_text=_short_evidence(original_text),
        confidence=0.52,
        evidence=_short_evidence(original_text),
    )


def _find_code(codes: dict[str, str], labels: set[str]) -> str | None:
    for code, label in codes.items():
        if normalize_text(label) in labels:
            return code
    return None


def _find_free_text_code(codes: dict[str, str]) -> str | None:
    for code, label in codes.items():
        if "#TEXTO_LIBRE#" in label:
            return code
    return None


def _topic_tokens(question_text: str) -> set[str]:
    tokens: set[str] = set()
    mapping = {
        "fuma": {"fuma", "fumo", "fumaba", "fumado", "fumador", "tabaco", "cigarro", "cigarrillo"},
        "alcohol": {"alcohol", "bebida", "cerveza", "ron", "vino"},
        "alerg": {"alergia", "alergico", "alergica", "penicilina"},
        "trabaj": {"trabajo", "trabajado", "laboral", "industria"},
        "estupefaciente": {"droga", "estupefaciente", "marihuana", "cocaina", "cannabis"},
        "cuero cabelludo": {"cuero cabelludo", "cabello", "calvicie"},
        "cara": {"cara", "facial", "parotida", "acne", "dermatitis"},
        "boca": {"boca", "oral", "diente", "caries", "amigdala", "encia", "lengua"},
        "oido": {"oido", "oreja", "timpano", "cerumen", "weber", "rinne"},
        "ojos": {"ojo", "ojos", "catarata", "conjuntivitis", "orzuelo"},
        "nariz": {"nariz", "nasal", "tabique", "cornetes"},
        # --- Anamnesis / historia clinica ---
        "medicacion": {
            "medicacion", "medicamento", "medicamentos", "pastilla", "pastillas",
            "tratamiento", "farmaco", "antihipertensivo", "ibuprofeno", "omeprazol",
        },
        "medicament": {
            "medicacion", "medicamento", "medicamentos", "pastilla", "tratamiento",
            "farmaco",
        },
        "enfermedad": {
            "enfermedad", "enfermedades", "patologia", "diabetes", "hipertension",
            "asma", "cardiopatia", "tiroides", "colesterol", "cronica", "diagnostico",
        },
        "operacion": {
            "operacion", "operaciones", "operado", "operada", "cirugia", "intervencion",
            "quirurgica", "apendice", "vesicula", "hernia",
        },
        "intervencion": {
            "operacion", "operado", "cirugia", "intervencion", "quirurgica",
        },
        "actividad fisica": {
            "deporte", "ejercicio", "gimnasio", "correr", "caminar", "actividad fisica",
            "sedentario", "entreno", "bicicleta",
        },
        "deporte": {
            "deporte", "ejercicio", "gimnasio", "correr", "caminar", "entreno",
        },
        "padre": {"padre", "paterno", "antecedentes familiares", "familia", "hereditario"},
        "madre": {"madre", "materno", "antecedentes familiares", "familia", "hereditario"},
        "familiar": {
            "padre", "madre", "paterno", "materno", "antecedentes familiares",
            "familia", "hereditario", "hermano", "abuelo",
        },
        "epi": {
            "epi", "equipo de proteccion", "proteccion individual", "guantes",
            "casco", "mascarilla", "gafas de proteccion", "botas", "arnes",
        },
        "proteccion": {
            "epi", "equipo de proteccion", "proteccion individual", "guantes",
            "casco", "mascarilla", "arnes",
        },
        "jornada": {
            "jornada", "horario", "turno", "turnos", "horas", "nocturno", "diurno",
            "partida", "continua",
        },
        "horario": {"jornada", "horario", "turno", "turnos", "horas"},
        "ordenador": {
            "ordenador", "pantalla", "pantallas", "pvd", "monitor", "teclado",
            "ofimatica", "informatica",
        },
        "pantalla": {
            "ordenador", "pantalla", "pantallas", "pvd", "monitor", "ofimatica",
        },
    }
    for key, values in mapping.items():
        if key in question_text:
            tokens.update(values)
    return tokens


def question_topic_present(question: dict[str, Any], normalized_text: str) -> bool:
    """True si el texto normalizado toca el tema de la pregunta.

    Reutiliza la heuristica de relevancia (topic tokens + solape de palabras).
    Usado por la guardia anti-alucinacion para validar evidencia de LLM.
    """
    return _looks_relevant(question, normalized_text)


def _looks_relevant(question: dict[str, Any], normalized_text: str) -> bool:
    question_text = normalize_text(question.get("text", ""))
    topic_tokens = _topic_tokens(question_text)
    if topic_tokens:
        return any(token in normalized_text for token in topic_tokens)
    stopwords = {"que", "detecta", "tiene", "alguna", "otros", "otro", "cual", "consume"}
    question_words = {
        word for word in question_text.split()
        if len(word) > 3 and word not in stopwords
    }
    text_words = set(normalized_text.split())
    return bool(question_words & text_words)


def _short_evidence(text: str, limit: int = 240) -> str:
    clean = " ".join(text.split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3].rstrip() + "..."


def _is_current_smoking_question(question_text: str) -> bool:
    return "fuma" in question_text and "anteriormente" not in question_text


def _is_previous_smoking_question(question_text: str) -> bool:
    return "fumado anteriormente" in question_text


def _has_stopped_smoking_evidence(normalized_text: str) -> bool:
    markers = ("dejo de fumar", "deje de fumar", "exfumador", "ex fumador", "fumaba", "fumo hasta")
    return any(marker in normalized_text for marker in markers)


def _has_previous_smoking_evidence(normalized_text: str) -> bool:
    markers = ("dejo de fumar", "deje de fumar", "exfumador", "ex fumador", "fumaba", "fumo hasta")
    return any(marker in normalized_text for marker in markers)


def _is_normal_exam_question(question_text: str) -> bool:
    return "normal" in question_text and any(
        token in question_text
        for token in ("cuero cabelludo", "cara", "boca", "oido", "ojos", "nariz")
    )


def _has_abnormal_exam_evidence(question_text: str, normalized_text: str) -> bool:
    abnormal_markers = (
        "no es normal",
        "alterado",
        "presenta",
        "tapon",
        "cerumen",
        "caries",
        "inflamacion",
        "lesion",
        "perforacion",
        "catarata",
        "conjuntivitis",
        "desviacion",
    )
    if not any(marker in normalized_text for marker in abnormal_markers):
        return False

    return any(token in normalized_text for token in _topic_tokens(question_text))


_CODE_SYNONYMS: dict[str, tuple[str, ...]] = {
    "biologicos": ("biologico", "virus", "bacteria", "microorganismo"),
    "ruido": ("ruidoso", "ruidos", "acustico", "decibeles", "sonido alto"),
    "manipulacion de cargas": ("carga pesada", "levantamiento", "cargas manuales", "levantar peso"),
    "movimientos repetitivos": ("repeticion", "repetitivo", "movimiento repetido"),
    "pantallas de visualizacion": ("pantalla", "pvd", "monitor", "ordenador"),
    "posturas forzadas": ("postura", "ergonomia", "posicion forzada"),
    "quimicos": ("quimico", "quimica", "sustancia quimica", "disolvente", "toxico"),
    "radiaciones ionizantes": ("radiacion", "rayos x", "radiografia", "rx"),
    "radiaciones no ionizantes": ("ultravioleta", "uv", "infrarrojo", "laser"),
    "riesgo electrico": ("electrico", "electricidad", "corriente electrica"),
    "sustancias cancerigenas": ("cancerigeno", "carcinogeno", "amianto", "asbesto"),
    "temperaturas altas": ("calor", "temperatura alta", "caluroso"),
    "temperaturas bajas": ("frio", "temperatura baja", "frio extremo"),
    "turnicidad": ("turno", "turnos", "nocturno", "rotatorio", "turno de noche"),
    "caidas de alturas": ("altura", "caida", "andamio", "escalera", "trabajo en altura"),
    "espacio confinado": ("confinado", "espacio cerrado", "espacio limitado"),
    "tapon de cerumen dcho": ("cerumen derecho", "oido derecho", "tapon derecho"),
    "tapon de cerumen izdo": ("cerumen izquierdo", "oido izquierdo", "tapon izquierdo"),
    "tapon cerumen bilateral": ("cerumen bilateral", "ambos oidos", "tapones bilaterales"),
    "derivados penicilina": ("penicilina", "amoxicilina", "ampicilina"),
    "aines": ("ibuprofeno", "naproxeno", "diclofenaco", "antiinflamatorio"),
}


def narrow_codes_by_relevance(
    codes: dict[str, str],
    norm_text: str,
    min_keep: int = 3,
) -> dict[str, str]:
    """Filtra los codigos de una pregunta multiple sin mencion en el texto.

    Para preguntas con muchas opciones (riesgos laborales, hallazgos fisicos),
    el LLM recibe solo los codigos cuyos terminos aparecen en el transcript.
    Siempre conserva los codigos #TEXTO_LIBRE# y al menos min_keep codigos de
    contenido. Si el filtrado dejaria menos de min_keep, devuelve todos.
    """
    free_text_codes: dict[str, str] = {}
    candidate_codes: dict[str, str] = {}

    for code, label in codes.items():
        if "#TEXTO_LIBRE#" in label:
            free_text_codes[code] = label
        else:
            candidate_codes[code] = label

    kept: dict[str, str] = {}
    for code, label in candidate_codes.items():
        norm_label = normalize_text(label)
        if _code_mentioned_in_text(norm_label, norm_text):
            kept[code] = label

    if len(kept) < min_keep:
        return codes

    return {**kept, **free_text_codes}


def _code_mentioned_in_text(norm_label: str, norm_text: str) -> bool:
    if len(norm_label) >= 4 and norm_label in norm_text:
        return True
    synonyms = _CODE_SYNONYMS.get(norm_label, ())
    return any(syn in norm_text for syn in synonyms)


def _code_label_matches(normalized_label: str, normalized_text: str) -> bool:
    if len(normalized_label) >= 4 and normalized_label in normalized_text:
        return True

    synonyms = {
        "derivados penicilina": ("penicilina", "amoxicilina"),
        "tapon de cerumen dcho": (
            "tapon de cerumen derecho",
            "oido derecho tapon",
            "oido derecho presenta un tapon",
            "cerumen derecho",
        ),
        "tapon de cerumen izdo": (
            "tapon de cerumen izquierdo",
            "oido izquierdo tapon",
            "oido izquierdo presenta un tapon",
            "cerumen izquierdo",
        ),
        "tapon cerumen bilateral": ("tapon bilateral", "cerumen bilateral", "ambos oidos cerumen"),
    }
    return any(marker in normalized_text for marker in synonyms.get(normalized_label, ()))


def _relevant_evidence(question_text: str, original_text: str) -> tuple[str, str]:
    topic_tokens = _topic_tokens(question_text)
    sentences = _split_sentences(original_text)
    relevant = [
        sentence
        for sentence in sentences
        if any(token in normalize_text(sentence) for token in topic_tokens)
    ]
    evidence = " ".join(relevant)
    return evidence, normalize_text(evidence)


def _split_sentences(text: str) -> list[str]:
    normalized = text.replace(";", ".").replace("\n", ".")
    parts = [part.strip() for part in normalized.split(".")]
    return [part for part in parts if part]
