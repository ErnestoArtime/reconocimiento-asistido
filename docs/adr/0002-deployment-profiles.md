# ADR 0002: perfiles de despliegue

Fecha: 2026-05-28

Estado: Aceptado.

## Decision

`DEPLOYMENT_PROFILE` es la variable maestra:

- `demo`
- `prototype_local`
- `production`

`LOCAL_ONLY` no existe como flag independiente; se deriva como `settings.local_only`.

## Consecuencias implementadas

- En `prototype_local` y `production`, providers IA online (`cloudflare`, `both_cloudflare`) se bloquean por request y se degradan desde configuracion inicial.
- Providers audio online (`openai`, `azure`, `deepgram`) devuelven HTTP 403 en perfiles locales/productivos.
- `AUDIO_CACHE_ENABLED` es true por defecto solo en `demo`.
- `DEBUG_TRANSCRIPTS` es true por defecto solo en `demo`.
- Endpoints v1 requieren `X-Internal-API-Key` fuera de `demo`.

## Docker

Docker Compose no incluye Ollama. Si se usa Ollama, debe correr fuera del stack y configurarse via `OLLAMA_BASE_URL`.

## Referencias

- `app/core/config.py`
- `app/services/provider_policy.py`
- `app/api/security.py`
- `docs/DEPLOYMENT_PROFILES.md`
