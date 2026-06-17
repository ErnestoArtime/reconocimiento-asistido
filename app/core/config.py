from functools import lru_cache
import os
from pathlib import Path
from typing import Literal

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


IaProvider = Literal["heuristic", "ollama", "cloudflare", "both", "both_cloudflare"]
DeploymentProfile = Literal["demo", "prototype_local", "production"]
_ALLOWED_IA = {"heuristic", "ollama", "cloudflare", "both", "both_cloudflare"}
_ALLOWED_PROFILES = {"demo", "prototype_local", "production"}
_ONLINE_IA = {"cloudflare", "both_cloudflare"}


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "si"}


class Settings:
    def __init__(self) -> None:
        self.questionnaire_path = Path(
            os.getenv("QUESTIONNAIRE_PATH", "app/data/json_IA.json")
        )

        deployment_profile = os.getenv("DEPLOYMENT_PROFILE", "demo").strip().lower()
        if deployment_profile not in _ALLOWED_PROFILES:
            deployment_profile = "demo"
        self.deployment_profile: DeploymentProfile = deployment_profile  # type: ignore[assignment]
        self.local_only = self.deployment_profile in {"prototype_local", "production"}
        self.debug_transcripts = _env_bool(
            "DEBUG_TRANSCRIPTS",
            self.deployment_profile == "demo",
        )
        self.internal_api_key = os.getenv("INTERNAL_API_KEY", "")

        # --- Persistencia (sesiones, sugerencias, revisiones) ---
        # Off por defecto. Persiste solo sugerencias/revisiones, NO transcripcion.
        self.persistence_enabled = _env_bool("PERSISTENCE_ENABLED", False)
        self.persistence_db_path = Path(
            os.getenv("PERSISTENCE_DB_PATH", "data/reconocimiento.db")
        )

        provider = os.getenv("IA_PROVIDER", "heuristic").strip().lower()
        if provider not in _ALLOWED_IA:
            provider = "heuristic"
        if self.local_only and provider in _ONLINE_IA:
            provider = "heuristic"
        self.ia_provider: IaProvider = provider  # type: ignore[assignment]

        self.ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        self.ollama_model = os.getenv("OLLAMA_MODEL", "gpt-oss:20b")
        self.ollama_allowed_models = [
            item.strip()
            for item in os.getenv(
                "OLLAMA_ALLOWED_MODELS",
                "qwen3:8b,gpt-oss:20b,gemma4:e4b,gemma4:31b,deepseek-r1:8b,glm-4.7:cloud",
            ).split(",")
            if item.strip()
        ]
        if self.ollama_model not in self.ollama_allowed_models:
            self.ollama_allowed_models.insert(0, self.ollama_model)
        self.ollama_timeout = float(os.getenv("OLLAMA_TIMEOUT", "300"))
        self.ollama_temperature = float(os.getenv("OLLAMA_TEMPERATURE", "0.1"))
        self.ollama_num_ctx = int(os.getenv("OLLAMA_NUM_CTX", "8192"))
        # Modo "thinking" (qwen3, deepseek-r1...). En CPU el razonamiento dispara
        # la latencia ~36x (43s vs 1.2s medido) -> timeouts y lotes perdidos.
        # Off por defecto: extraccion estructurada no necesita cadena de
        # pensamiento. Subir a true solo si un modelo lo requiere.
        self.ollama_think = _env_bool("OLLAMA_THINK", False)
        self.ollama_use_json_schema = _env_bool("OLLAMA_USE_JSON_SCHEMA", False)
        self.ollama_schema_max_questions = int(
            os.getenv("OLLAMA_SCHEMA_MAX_QUESTIONS", "30")
        )
        # Hito 6.1: extraccion por lotes pequenos si la seccion tiene >= threshold
        # preguntas. 0 = desactivado (comportamiento default: extractor monolitico).
        self.ia_batch_extraction_threshold = int(
            os.getenv("IA_BATCH_EXTRACTION_THRESHOLD", "0")
        )
        self.ia_batch_extraction_size = int(
            os.getenv("IA_BATCH_EXTRACTION_SIZE", "6")
        )
        # Lotes en paralelo. Module-wide trocea en muchos lotes; secuencial suma
        # latencias (Cloudflare 70B ~100s) y el cliente agota el timeout. Las
        # llamadas LLM son I/O-bound -> paralelizar baja el wall time a ~oleadas.
        # Subir con cuidado por rate limits del proveedor (free tier).
        self.ia_batch_max_workers = int(os.getenv("IA_BATCH_MAX_WORKERS", "4"))
        # Resumen clinico intermedio: genera un resumen estructurado del
        # transcript antes de extraer y lo expone como artefacto + contexto de
        # apoyo al LLM. La evidencia sigue anclada al transcript original, no al
        # resumen. Off por defecto (cero cambio de comportamiento).
        self.ia_clinical_summary_enabled = _env_bool(
            "IA_CLINICAL_SUMMARY_ENABLED", False
        )
        # Pase de recuperacion: detecta via LLM que preguntas hizo el medico
        # explicitamente y reextrae las no respondidas con guardrails permisivos
        # (lenient). Añade una llamada LLM extra (consume neurons en Cloudflare).
        # Off por defecto. Activar cuando se requiera cobertura maxima.
        self.ia_recovery_pass_enabled = _env_bool("IA_RECOVERY_PASS_ENABLED", False)
        # Deteccion heuristica de turnos medico/paciente. Los segmentos con '?'
        # se etiquetan como MED, el resto como PAC. Mejora la extraccion de
        # historia clinica al dar al LLM contexto de quien habla.
        self.ia_turn_detection_enabled = _env_bool("IA_TURN_DETECTION_ENABLED", True)
        # BM25 passage retrieval: envia al LLM solo las top-K frases mas relevantes.
        # La evidencia de grounding siempre verifica contra el transcript completo.
        self.ia_bm25_enabled = _env_bool("IA_BM25_ENABLED", False)
        self.ia_bm25_top_k = int(os.getenv("IA_BM25_TOP_K", "15"))

        # --- Guardia anti-alucinacion (calibracion) ---
        # Cuando el audio usa preguntas reformuladas/resumidas, el LLM responde
        # con citas validas que NO contienen la palabra-tema. El check de
        # relevancia contra la evidencia (la respuesta) las descartaba. Estos
        # flags relajan la guardia sin desactivar el anclaje real al transcript.
        #
        # fuzzy_grounding: acepta evidencia con cobertura de tokens (no solo
        #   substring literal) -> tolera reescritura menor del LLM. Default on.
        self.extraction_fuzzy_grounding = _env_bool("EXTRACTION_FUZZY_GROUNDING", True)
        # relevance_scope: "transcript" (default) valida el tema contra TODO el
        #   transcript; "evidence" (legacy) lo exige dentro de la cita.
        scope = os.getenv("EXTRACTION_RELEVANCE_SCOPE", "transcript").strip().lower()
        if scope not in {"transcript", "evidence"}:
            scope = "transcript"
        self.extraction_relevance_scope = scope
        # lenient_mode: omite por completo el check de relevancia (solo exige
        #   anclaje al transcript). Escape hatch para audios muy parafraseados.
        self.extraction_lenient_mode = _env_bool("EXTRACTION_LENIENT_MODE", False)

        # --- Cloudflare Workers AI (LLM online gratis) ---
        self.cloudflare_account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
        self.cloudflare_api_token = os.getenv("CLOUDFLARE_API_TOKEN", "")
        self.cloudflare_model = os.getenv(
            "CLOUDFLARE_MODEL", "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
        )
        # Modelos CF seleccionables por peticion (override ia_model). Solo
        # instruct NO-thinking: los thinking (qwen3, deepseek-r1, glm-flash, qwq,
        # kimi-k2, gpt-oss, gemma-3/4, nemotron-3) devuelven razonamiento y no
        # JSON usable -> excluidos.
        self.cloudflare_allowed_models = [
            item.strip()
            for item in os.getenv(
                "CLOUDFLARE_ALLOWED_MODELS",
                "@cf/meta/llama-3.3-70b-instruct-fp8-fast,"
                "@cf/meta/llama-4-scout-17b-16e-instruct,"
                "@cf/mistralai/mistral-small-3.1-24b-instruct,"
                "@cf/qwen/qwen2.5-coder-32b-instruct,"
                "@cf/meta/llama-3.1-8b-instruct-fp8,"
                "@cf/ibm/granite-4.0-h-micro,"
                "@cf/meta/llama-3.1-8b-instruct-fast,"
                "@cf/meta/llama-3.2-3b-instruct,"
                "@cf/meta/llama-3.2-1b-instruct,"
                "@cf/aisingapore/gemma-sea-lion-v4-27b-it",
            ).split(",")
            if item.strip()
        ]
        if self.cloudflare_model not in self.cloudflare_allowed_models:
            self.cloudflare_allowed_models.insert(0, self.cloudflare_model)
        self.cloudflare_timeout = float(os.getenv("CLOUDFLARE_TIMEOUT", "60"))
        self.cloudflare_temperature = float(os.getenv("CLOUDFLARE_TEMPERATURE", "0.1"))
        self.cloudflare_max_tokens = int(os.getenv("CLOUDFLARE_MAX_TOKENS", "2048"))

        # --- Audio / transcripcion ---
        self.audio_provider = os.getenv("AUDIO_PROVIDER", "faster_whisper").strip().lower()
        self.audio_model = os.getenv("AUDIO_MODEL", "large-v3")
        # Modelos descargados/seleccionables en la UI (faster_whisper/whisperx).
        # Restringe que se pida un modelo no presente (evita descargas enormes).
        self.audio_allowed_models = [
            item.strip()
            for item in os.getenv("AUDIO_ALLOWED_MODELS", "large-v3,medium").split(",")
            if item.strip()
        ]
        if self.audio_model not in self.audio_allowed_models:
            self.audio_allowed_models.insert(0, self.audio_model)
        self.audio_device = os.getenv("AUDIO_DEVICE", "auto")  # auto|cpu|cuda
        self.audio_compute_type = os.getenv("AUDIO_COMPUTE_TYPE", "auto")
        self.audio_language = os.getenv("AUDIO_LANGUAGE", "es")
        self.audio_beam_size = int(os.getenv("AUDIO_BEAM_SIZE", "5"))
        self.audio_vad_filter = _env_bool("AUDIO_VAD_FILTER", True)
        self.audio_diarization = _env_bool("AUDIO_DIARIZATION", False)
        self.audio_cpu_threads = int(os.getenv("AUDIO_CPU_THREADS", "0"))
        self.audio_cache_dir = Path(os.getenv("AUDIO_CACHE_DIR", ".cache/audio"))
        self.audio_cache_enabled = _env_bool(
            "AUDIO_CACHE_ENABLED",
            self.deployment_profile == "demo",
        )
        self.audio_cache_ttl_hours = int(os.getenv("AUDIO_CACHE_TTL_HOURS", "24"))
        self.audio_apply_filters = _env_bool("AUDIO_APPLY_FILTERS", True)
        self.audio_initial_prompt = os.getenv("AUDIO_INITIAL_PROMPT", "").strip()
        self.audio_fallback_provider = os.getenv(
            "AUDIO_FALLBACK_PROVIDER", "faster_whisper"
        ).strip().lower()
        self.audio_model_cache_dir = os.getenv("AUDIO_MODEL_CACHE_DIR", "").strip()
        self.audio_offline_mode = _env_bool("AUDIO_OFFLINE_MODE", False)
        self.whisperx_diarization_model = os.getenv(
            "WHISPERX_DIARIZATION_MODEL", ""
        ).strip()
        self.whisperx_hf_token = os.getenv("HF_TOKEN", "").strip()

        # --- Streaming dedicado (modelo mas pequeno = mas rapido para tiempo real) ---
        self.audio_stream_model = os.getenv("AUDIO_STREAM_MODEL", "").strip() or None
        self.audio_stream_provider = (
            os.getenv("AUDIO_STREAM_PROVIDER", "").strip().lower() or None
        )
        self.audio_stream_partial_every_s = float(
            os.getenv("AUDIO_STREAM_PARTIAL_EVERY_S", "1.0")
        )
        self.audio_stream_min_segment_s = float(
            os.getenv("AUDIO_STREAM_MIN_SEGMENT_S", "1.5")
        )
        self.audio_stream_max_segment_s = float(
            os.getenv("AUDIO_STREAM_MAX_SEGMENT_S", "12.0")
        )
        self.audio_stream_silence_ms = int(
            os.getenv("AUDIO_STREAM_SILENCE_MS", "600")
        )
        self.ffmpeg_path = os.getenv("FFMPEG_PATH", "ffmpeg")
        self.ffprobe_path = os.getenv("FFPROBE_PATH", "ffprobe")

        # Providers online (opcionales)
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        self.openai_audio_model = os.getenv("OPENAI_AUDIO_MODEL", "whisper-1")
        self.azure_speech_key = os.getenv("AZURE_SPEECH_KEY", "")
        self.azure_speech_region = os.getenv("AZURE_SPEECH_REGION", "")
        self.azure_speech_endpoint_id = os.getenv("AZURE_SPEECH_ENDPOINT_ID") or None
        self.deepgram_api_key = os.getenv("DEEPGRAM_API_KEY", "")
        self.deepgram_model = os.getenv("DEEPGRAM_MODEL", "nova-2-medical")


@lru_cache
def get_settings() -> Settings:
    return Settings()
