"""Cliente LLM para extraccion estructurada contra Ollama.

El proveedor recibe la transcripcion y el subconjunto de preguntas relevantes,
y devuelve una lista de AiSuggestion validables por QuestionnaireEngine.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from app.models.suggestion import AiSuggestion


logger = logging.getLogger(__name__)


BASE_SYSTEM_PROMPT = (
    "Eres un extractor de datos clinicos en espanol. "
    "Recibes una transcripcion de una entrevista o exploracion medica y un conjunto "
    "de preguntas con sus codigos permitidos.\n"
    "Reglas estrictas:\n"
    "- Solo devuelve respuestas con evidencia textual clara en la transcripcion.\n"
    "- No inventes informacion. Si no hay evidencia, no incluyas la pregunta.\n"
    "- Solo usa codigos presentes en codes de cada pregunta.\n"
    "- question_type yesno, yesnoremember o choice: exactamente 1 codigo.\n"
    "- question_type multiple: 1 o varios codigos, pero SOLO los que tengan "
    "soporte textual explicito. No anadas opciones plausibles que no se hayan "
    "mencionado (no sobre-extraigas).\n"
    "- question_type free: usa el codigo cuya etiqueta sea #TEXTO_LIBRE# y "
    "rellena free_text con el fragmento literal de la transcripcion.\n"
    "- Si ninguna etiqueta de codes encaja con lo dicho y existe un codigo con "
    "etiqueta #TEXTO_LIBRE#, usa ESE con free_text. NUNCA fuerces el codigo 'mas "
    "parecido' si es incorrecto (ej. 'sector tecnologico' NO es 'Textil'). Si no "
    "hay #TEXTO_LIBRE# y ningun codigo encaja, omite la pregunta.\n"
    "- confidence entre 0 y 1.\n"
    "- evidence: copia EXACTA y corta de la transcripcion (verbatim). Debe poder "
    "encontrarse como subcadena literal del texto. NO la parafrasees, NO la traduzcas, "
    "NO corrijas tildes ni puntuacion. Si no puedes copiar un fragmento literal que "
    "soporte la respuesta, no incluyas la pregunta.\n"
    "- No respondas 'Si'/'No' por defecto: solo cuando el hablante clinicamente "
    "relevante para el modulo afirme o niegue explicitamente ESA pregunta o "
    "hallazgo. Si no aborda el tema, omite la pregunta.\n"
    "- question_id: usa EXACTAMENTE el id de la pregunta a la que responde la evidencia. "
    "No mezcles la evidencia de una pregunta con el id de otra.\n"
    "- No reutilices la MISMA evidencia para muchas preguntas distintas. Cada evidencia "
    "debe sustentar especificamente su pregunta. Si una sola frase responde a 2 preguntas "
    "(ej. 'no fumo ni bebo'), esta bien, pero no la copies en 5+ preguntas no relacionadas.\n"
    "- IMPORTANTE: la pregunta puede estar reformulada o resumida respecto al audio. "
    "Empareja por SIGNIFICADO clinico, no por coincidencia de palabras. La evidencia "
    "puede no contener la palabra-tema de la pregunta.\n"
    "- Salida unicamente JSON valido segun el esquema. Sin comentarios. Sin razonamiento.\n"
    "\n"
    "COBERTURA DE NEGACIONES (critico para la precision del formulario):\n"
    "- Si el paciente NIEGA algo explicitamente ('no', 'nunca', 'jamas', 'niega', "
    "'no tengo', 'no he tenido', 'no lo tomo'), INCLUYE la pregunta con el codigo "
    "de negacion. Omitir NO equivale a negacion: el formulario distingue 'sin "
    "respuesta' de 'respondido con No'. Si hay negacion clara, SIEMPRE incluye.\n"
    "- Si el paciente usa incertidumbre ('no se', 'no recuerdo', 'no estoy seguro', "
    "'creo que no') y la pregunta es yesnoremember, usa el codigo 'No recuerda'. "
    "Si la pregunta es yesno sin opcion de no-recuerda, usa el codigo negativo con "
    "confidence <= 0.6.\n"
    "\n"
    "Negaciones implicitas en espanol medico:\n"
    "- 'lo deje hace X', 'ya no lo tomo', 'no lo tomo desde hace...' -> actualmente NO.\n"
    "- 'antes si pero ahora no', 'de joven si' -> actualmente NO, historicamente SI.\n"
    "- 'algo asi', 'me parece que si', 'creo que', 'puede ser' -> SI con confidence 0.5-0.65.\n"
    "\n"
    "Ejemplos de extraccion correcta:\n"
    "Texto: 'Medico: ¿Fuma? Paciente: No, lo deje hace tres anos. "
    "Medico: ¿Antes fumaba? Paciente: Si, fumaba bastante de joven.'\n"
    "-> '¿Fuma?' (yesno {X1:Si,X2:No}): codes=[X2], evidence='lo deje hace tres anos'\n"
    "-> '¿Ha fumado anteriormente?' (yesno {X3:Si,X4:No}): codes=[X3], evidence='fumaba bastante de joven'\n"
    "Texto: 'Medico: ¿Alergias? Paciente: No se, quiza al ibuprofeno, me sento mal una vez.'\n"
    "-> '¿Alergias?' (yesnoremember {Y1:Si,Y2:No,Y3:NoRecuerda}): codes=[Y3], "
    "evidence='No se, quiza al ibuprofeno, me sento mal una vez'\n"
    "Texto: 'Medico: ¿Operaciones? Paciente: No, nunca me han operado.'\n"
    "-> '¿Intervenciones?' (yesno {Z1:Si,Z2:No}): codes=[Z2], "
    "evidence='No, nunca me han operado'  <- INCLUIR: la negacion tiene codigo propio\n"
    "\n"
    "Razonamiento temporal (CRITICO):\n"
    "- Distingue presente vs historico. Una pregunta puede ser actual ('Fuma?') o "
    "historica/anterior ('Ha fumado anteriormente?', 'Ha consumido alguna vez?').\n"
    "- 'Dejo hace X', 'exfumador', 'fumaba antes', 'consumi en el pasado': la persona "
    "SI tuvo el habito en algun momento. Para pregunta historica/anterior la respuesta "
    "es Si. Para pregunta actual/presente la respuesta es No.\n"
    "- Ejemplo: texto 'No fumo. Deje hace 3 anos.' -> 'Fuma?' = No, "
    "'Ha fumado anteriormente?' = Si (porque dejarlo implica que fumo antes).\n"
    "- 'Nunca he fumado', 'jamas', 'no he probado': para AMBAS preguntas (actual e "
    "historica) la respuesta es No.\n"
    "- Si la transcripcion no menciona el habito, no incluyas esa pregunta."
)


def build_system_prompt(module: str) -> str:
    """Prompt de extraccion con reglas de evidencia dependientes del modulo."""
    normalized = (module or "").strip().lower()
    if normalized == "exam":
        evidence_rules = (
            "\nReglas de hablante/evidencia por modulo:\n"
            "- En exploracion fisica, la evidencia clinica suele ser dictada por el MEDICO.\n"
            "- Para module=exam, evidence puede copiar palabras del medico cuando describen hallazgos.\n"
            "- No exijas palabras del paciente en exploracion fisica.\n"
            "- Si hay turnos con hablante, usa el hablante como contexto, pero la cita debe ser literal del transcript.\n"
        )
    else:
        evidence_rules = (
            "\nReglas de hablante/evidencia por modulo:\n"
            "- En historia clinica, el medico aporta contexto y el PACIENTE aporta la evidencia principal.\n"
            "- Para module=history, evidence debe copiar la respuesta del paciente siempre que haya turnos.\n"
            "- Puedes usar la pregunta del medico para entender a que campo responde un 'si' o 'no', pero no la uses como unica evidencia.\n"
            "- Si no hay etiquetas de hablante, usa solo citas literales del transcript con soporte clinico claro.\n"
        )
    return BASE_SYSTEM_PROMPT + evidence_rules


SYSTEM_PROMPT = build_system_prompt("history")


SUMMARY_SYSTEM_PROMPT = (
    "Eres un asistente clinico. Resume en espanol la transcripcion de una "
    "entrevista o exploracion medica, en secciones cortas.\n"
    "Reglas:\n"
    "- Solo informacion EXPLICITA en la transcripcion. No infieras ni inventes.\n"
    "- Conserva las negaciones ('no fuma', 'niega alergias').\n"
    "- Omite las secciones sin informacion. No escribas 'sin datos'.\n"
    "- Texto plano breve. Sin markdown, sin preambulo, sin razonamiento.\n"
    "Secciones posibles: Antecedentes personales, Antecedentes familiares, "
    "Habitos, Alergias, Medicacion, Intervenciones, Anamnesis (motivo y "
    "sintomas actuales), Exploracion fisica.\n"
    "Al final, agrega una seccion 'Preguntas del medico:' listando cada pregunta "
    "que el medico formulo explicitamente con la respuesta breve del paciente. "
    "Formato por linea: '- [tema de la pregunta] -> [respuesta del paciente en 1-10 palabras]'. "
    "Ejemplo correcto: '- ¿Fuma? -> no, lo dejo hace 3 anos'. "
    "Ejemplo correcto: '- ¿Alergias? -> no sabe, quiza al ibuprofeno'. "
    "Incluye TODAS las preguntas del medico, incluso las que el paciente respondio con no o no recuerda. "
    "Omite esta seccion solo si no hay preguntas claras del medico."
)


DOCTOR_DETECTOR_SYSTEM_PROMPT = (
    "Eres un asistente que analiza transcripciones de entrevistas medicas en espanol. "
    "Tu tarea: identificar los temas que el MEDICO pregunto explicitamente al paciente. "
    "Solo cuenta preguntas del medico, no lo que el paciente menciona voluntariamente.\n"
    "Devuelve unicamente JSON valido: {\"temas\": [\"tema1\", \"tema2\", ...]}\n"
    "Los temas deben ser palabras clave cortas (1-4 palabras) que capturen el concepto "
    "preguntado. Ejemplos validos de temas: 'fuma', 'alergias', 'operaciones previas', "
    "'trabajo actual', 'enfermedades familiares', 'medicacion actual', 'habitos alcohol', "
    "'actividad fisica', 'antecedentes quirurgicos', 'historia laboral'.\n"
    "Sin texto adicional. Solo JSON."
)


def _compact_question(question: dict[str, Any]) -> dict[str, Any]:
    compact = {
        "id": question.get("id"),
        "section": question.get("section"),
        "text": question.get("text"),
        "context": question.get("ai_context"),
        "parent_question_id": question.get("parent_question_id"),
        "parent_question": question.get("parent_question"),
        "required_parent_codes": question.get("required_parent_codes", []),
        "subject": question.get("subject"),
        "temporal_scope": question.get("temporal_scope"),
        "question_type": question.get("question_type"),
        "codes": question.get("codes", {}),
    }
    return {key: value for key, value in compact.items() if value not in (None, [], {})}


def build_extraction_schema(questions: list[dict[str, Any]]) -> dict[str, Any]:
    """Construye JSON Schema cerrado para restringir preguntas/codigos.

    No llama a ningun provider. Se usa para spikes o providers que soporten
    schema nativo.
    """
    suggestion_variants = []
    for question in questions:
        question_id = question.get("id")
        codes = list((question.get("codes") or {}).keys())
        if not question_id or not codes:
            continue
        suggestion_variants.append(
            {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "question_id",
                    "selected_codes",
                    "confidence",
                    "evidence",
                ],
                "properties": {
                    "question_id": {"const": question_id},
                    "selected_codes": {
                        "type": "array",
                        "items": {"enum": codes},
                        "minItems": 1,
                        "uniqueItems": True,
                    },
                    "free_text": {"type": ["string", "null"]},
                    "confidence": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                    },
                    "evidence": {"type": "string", "minLength": 1},
                    "evidence_turn_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "uniqueItems": True,
                    },
                    "speaker_cluster": {"type": ["string", "null"]},
                },
            }
        )

    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["suggestions"],
        "properties": {
            "suggestions": {
                "type": "array",
                "items": {"anyOf": suggestion_variants or [{"not": {}}]},
            }
        },
    }


def _build_user_prompt(
    text: str,
    module: str,
    section: str,
    questions: list[dict[str, Any]],
    clinical_context: str | None = None,
    transcript_turns: list[dict[str, Any]] | None = None,
) -> str:
    from app.services.extraction_service import narrow_codes_by_relevance
    from app.services.text_utils import normalize_text as _normalize

    norm_text = _normalize(text)

    compact_questions: list[dict[str, Any]] = []
    for q in questions:
        cq = _compact_question(q)
        if q.get("question_type") == "multiple":
            codes = cq.get("codes", {})
            if len(codes) > 8:
                narrowed = narrow_codes_by_relevance(codes, norm_text)
                if len(narrowed) < len(codes):
                    cq = {**cq, "codes": narrowed}
        compact_questions.append(cq)

    payload: dict[str, Any] = {
        "module": module,
        "section": section,
        "transcript": text,
        "questions": compact_questions,
        "output_schema": {
            "suggestions": [
                {
                    "question_id": "string",
                    "selected_codes": ["string"],
                    "free_text": "string|null",
                    "confidence": 0.0,
                    "evidence": "string",
                    "evidence_turn_ids": ["string"],
                    "speaker_cluster": "string|null",
                }
            ]
        },
    }
    if transcript_turns:
        payload["transcript_turns"] = transcript_turns
    context_note = ""
    if clinical_context:
        payload["clinical_context"] = clinical_context
        context_note = (
            "clinical_context es un resumen de apoyo para entender el caso. "
            "La evidencia DEBE copiarse del campo transcript, NUNCA de "
            "clinical_context.\n"
        )
    return (
        "Devuelve solo JSON valido con la clave suggestions.\n"
        + context_note
        + "Datos:\n" + json.dumps(payload, ensure_ascii=False)
    )


def _strip_thinking(raw: str) -> str:
    """Algunos modelos rodean su salida con <think>...</think> u otros marcos."""
    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL | re.IGNORECASE)
    cleaned = cleaned.strip()
    # Si viene envuelto en bloque de codigo
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*", "", cleaned).strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()
    return cleaned


def _extract_first_json_object(raw: str) -> str | None:
    start = raw.find("{")
    if start == -1:
        return None
    depth = 0
    for index in range(start, len(raw)):
        char = raw[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return raw[start : index + 1]
    return None


def _has_suggestions_payload(raw: str) -> bool:
    """True si `raw` contiene un objeto JSON con clave `suggestions` (lista).

    Distingue un fallo de generacion / JSON roto (sin payload) de una respuesta
    legitima con `suggestions: []`. Se usa para decidir el reintento de schema.
    """
    cleaned = _strip_thinking(raw)
    candidate = cleaned
    try:
        json.loads(cleaned)
    except json.JSONDecodeError:
        candidate = _extract_first_json_object(cleaned) or ""
        if not candidate:
            return False
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return False
    return isinstance(data, dict) and isinstance(data.get("suggestions"), list)


def _parse_suggestions(raw: str) -> list[AiSuggestion]:
    cleaned = _strip_thinking(raw)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        candidate = _extract_first_json_object(cleaned)
        if not candidate:
            logger.warning("Respuesta LLM sin JSON detectable: %s", raw[:300])
            return []
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            logger.warning("Respuesta LLM JSON invalido: %s", candidate[:300])
            return []

    raw_suggestions = data.get("suggestions") if isinstance(data, dict) else None
    if not isinstance(raw_suggestions, list):
        return []

    parsed: list[AiSuggestion] = []
    for item in raw_suggestions:
        if not isinstance(item, dict):
            continue
        try:
            parsed.append(AiSuggestion(**item))
        except Exception as exc:  # pydantic ValidationError u otros
            logger.warning("Sugerencia descartada: %s | %s", item, exc)
    return parsed


class CloudflareProvider:
    """Workers AI (Llama 3.3 70B fp8 fast u otros modelos `@cf/...`).

    Free tier 10k Neurons/dia. JSON mode nativo.
    """

    def __init__(
        self,
        account_id: str,
        api_token: str,
        model: str = "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
        timeout: float = 60.0,
        temperature: float = 0.1,
        max_tokens: int = 2048,
    ) -> None:
        if not account_id or not api_token:
            raise RuntimeError(
                "CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN no definidos"
            )
        self.account_id = account_id
        self.api_token = api_token
        self.model = model
        self.timeout = timeout
        self.temperature = temperature
        self.max_tokens = max_tokens

    def with_model(self, model: str) -> "CloudflareProvider":
        return CloudflareProvider(
            account_id=self.account_id,
            api_token=self.api_token,
            model=model,
            timeout=self.timeout,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

    def _run(self, messages: list[dict[str, str]], *, json_mode: bool) -> str:
        payload: dict[str, Any] = {
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        url = (
            f"https://api.cloudflare.com/client/v4/accounts/"
            f"{self.account_id}/ai/run/{self.model}"
        )
        headers = {"Authorization": f"Bearer {self.api_token}"}
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, json=payload, headers=headers)
                if response.status_code == 400 and json_mode:
                    # Algunos modelos CF (ej. Qwen 2.5) no soportan response_format.
                    # Reintentar sin el parametro; el parser downstream sigue siendo robusto.
                    logger.info(
                        "CF 400 con json_mode, reintento sin response_format (model=%s)",
                        self.model,
                    )
                    payload.pop("response_format", None)
                    response = client.post(url, json=payload, headers=headers)
                if not response.is_success:
                    logger.error(
                        "Cloudflare error %s para %s — body: %s",
                        response.status_code,
                        self.model,
                        response.text[:400],
                    )
                    response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            logger.error("Error llamando a Cloudflare Workers AI: %s", exc)
            return ""

        content: Any = ""
        if isinstance(data, dict):
            result = data.get("result")
            if isinstance(result, dict):
                content = result.get("response", "") or ""
            elif isinstance(result, str):
                content = result
        # Algunos modelos (ej. llama-4-scout) devuelven `response` ya como objeto
        # JSON (dict/list) en lugar de string. Serializar para que el parser
        # downstream (_strip_thinking/_parse_suggestions) reciba siempre str.
        if isinstance(content, (dict, list)):
            content = json.dumps(content, ensure_ascii=False)
        elif not isinstance(content, str):
            content = "" if content is None else str(content)
        if not content:
            logger.warning("Cloudflare devolvio respuesta vacia: %s", data)
        return content

    def extract(
        self,
        text: str,
        module: str,
        section: str,
        questions: list[dict[str, Any]],
        clinical_context: str | None = None,
        transcript_turns: list[dict[str, Any]] | None = None,
    ) -> list[AiSuggestion]:
        if not questions:
            return []

        user_prompt = _build_user_prompt(
            text, module, section, questions, clinical_context, transcript_turns
        )
        content = self._run(
            [
                {"role": "system", "content": build_system_prompt(module)},
                {"role": "user", "content": user_prompt},
            ],
            json_mode=True,
        )
        if not content:
            return []
        return _parse_suggestions(content)

    def summarize(self, text: str) -> str:
        if not text.strip():
            return ""
        content = self._run(
            [
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            json_mode=False,
        )
        return _strip_thinking(content)

    def detect_doctor_topics(self, transcript: str) -> str:
        """Detecta los temas que el médico preguntó explícitamente. Devuelve JSON crudo."""
        if not transcript.strip():
            return ""
        user_content = (
            "Transcripcion:\n"
            + transcript[:3000]
            + "\n\nIdentifica los temas que el MEDICO pregunto explicitamente. "
            "Devuelve JSON: {\"temas\": [...]}"
        )
        content = self._run(
            [
                {"role": "system", "content": DOCTOR_DETECTOR_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            json_mode=True,
        )
        return _strip_thinking(content)


class OllamaProvider:
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout: float = 180.0,
        temperature: float = 0.1,
        num_ctx: int = 8192,
        use_json_schema: bool = False,
        schema_max_questions: int = 30,
        think: bool | None = None,
    ) -> None:
        """Cliente Ollama.

        Args:
            think: controla el modo razonamiento de modelos thinking (qwen3,
                deepseek-r1...). En CPU el thinking dispara la latencia ~36x y
                provoca timeouts. None = no enviar el campo (comportamiento del
                modelo). False = desactivar (recomendado para extraccion).
            use_json_schema: si True, pasa `build_extraction_schema(questions)`
                en `format` (Ollama 0.5+). Restringe a codigos validos por
                pregunta. Fallback automatico a `"json"` si:
                  - len(questions) > schema_max_questions, o
                  - el modelo devuelve parse_error / generacion vacia.
                Default False para mantener compatibilidad legacy.
            schema_max_questions: limite por encima del cual el schema se
                vuelve demasiado grande para modelos pequenos. Default 30.
        """
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.temperature = temperature
        self.num_ctx = num_ctx
        self.use_json_schema = use_json_schema
        self.schema_max_questions = schema_max_questions
        self.think = think

    def with_model(self, model: str) -> "OllamaProvider":
        return OllamaProvider(
            base_url=self.base_url,
            model=model,
            timeout=self.timeout,
            temperature=self.temperature,
            num_ctx=self.num_ctx,
            use_json_schema=self.use_json_schema,
            schema_max_questions=self.schema_max_questions,
            think=self.think,
        )

    def _resolve_format(self, questions: list[dict[str, Any]]) -> Any:
        """Devuelve el valor a usar en payload['format']."""
        if not self.use_json_schema:
            return "json"
        if not questions or len(questions) > self.schema_max_questions:
            return "json"
        try:
            return build_extraction_schema(questions)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "build_extraction_schema fallo, fallback a json: %s", exc
            )
            return "json"

    def _chat(self, messages: list[dict[str, str]], *, fmt: Any) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_ctx": self.num_ctx,
            },
            "messages": messages,
        }
        if fmt is not None:
            payload["format"] = fmt
        if self.think is not None:
            payload["think"] = self.think
        url = f"{self.base_url}/api/chat"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            logger.error("Error llamando a Ollama: %s", exc)
            return ""

        content = ""
        if isinstance(data, dict):
            message = data.get("message")
            if isinstance(message, dict):
                content = message.get("content", "") or ""
        if not content:
            logger.warning("Ollama devolvio respuesta vacia: %s", data)
        return content

    def extract(
        self,
        text: str,
        module: str,
        section: str,
        questions: list[dict[str, Any]],
        clinical_context: str | None = None,
        transcript_turns: list[dict[str, Any]] | None = None,
    ) -> list[AiSuggestion]:
        if not questions:
            return []

        user_prompt = _build_user_prompt(
            text, module, section, questions, clinical_context, transcript_turns
        )
        messages = [
            {"role": "system", "content": build_system_prompt(module)},
            {"role": "user", "content": user_prompt},
        ]
        fmt = self._resolve_format(questions)
        content = self._chat(messages, fmt=fmt)

        # Fallback de schema: modelos pequenos pueden ahogarse con el JSON Schema
        # cerrado y devolver vacio o JSON roto. Si se uso schema y no hubo payload
        # `suggestions`, reintentar una vez con `"json"` plano (mas permisivo).
        used_schema = fmt != "json"
        if used_schema and not _has_suggestions_payload(content):
            logger.info("Schema sin payload, reintento con json plano")
            content = self._chat(messages, fmt="json")

        if not content:
            return []
        return _parse_suggestions(content)

    def summarize(self, text: str) -> str:
        if not text.strip():
            return ""
        content = self._chat(
            [
                {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            fmt=None,
        )
        return _strip_thinking(content)

    def detect_doctor_topics(self, transcript: str) -> str:
        """Detecta los temas que el médico preguntó explícitamente. Devuelve JSON crudo."""
        if not transcript.strip():
            return ""
        user_content = (
            "Transcripcion:\n"
            + transcript[:3000]
            + "\n\nIdentifica los temas que el MEDICO pregunto explicitamente. "
            "Devuelve JSON: {\"temas\": [...]}"
        )
        content = self._chat(
            [
                {"role": "system", "content": DOCTOR_DETECTOR_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            fmt="json",
        )
        return _strip_thinking(content)
