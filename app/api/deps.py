from functools import lru_cache

from app.core.config import Settings, get_settings
from app.services.llm_provider import CloudflareProvider, OllamaProvider
from app.services.persistence import PersistenceStore
from app.services.questionnaire_engine import QuestionnaireEngine


@lru_cache
def get_questionnaire_engine() -> QuestionnaireEngine:
    settings = get_settings()
    return QuestionnaireEngine(settings.questionnaire_path)


@lru_cache
def get_ollama_provider() -> OllamaProvider:
    settings = get_settings()
    return OllamaProvider(
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
        timeout=settings.ollama_timeout,
        temperature=settings.ollama_temperature,
        num_ctx=settings.ollama_num_ctx,
        use_json_schema=settings.ollama_use_json_schema,
        schema_max_questions=settings.ollama_schema_max_questions,
        think=settings.ollama_think,
    )


@lru_cache
def get_cloudflare_provider() -> CloudflareProvider | None:
    settings = get_settings()
    if not settings.cloudflare_account_id or not settings.cloudflare_api_token:
        return None
    return CloudflareProvider(
        account_id=settings.cloudflare_account_id,
        api_token=settings.cloudflare_api_token,
        model=settings.cloudflare_model,
        timeout=settings.cloudflare_timeout,
        temperature=settings.cloudflare_temperature,
        max_tokens=settings.cloudflare_max_tokens,
    )


@lru_cache
def get_persistence_store() -> PersistenceStore | None:
    settings = get_settings()
    if not settings.persistence_enabled:
        return None
    return PersistenceStore(settings.persistence_db_path)


def get_app_settings() -> Settings:
    return get_settings()
