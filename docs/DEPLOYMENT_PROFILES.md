# Perfiles de despliegue

Fecha: 2026-06-03

Tres perfiles controlados por `DEPLOYMENT_PROFILE` en `.env`.

```ini
DEPLOYMENT_PROFILE=demo
```

`settings.local_only` se deriva del perfil. No se configura como bandera independiente.

## Matriz

| Aspecto | `demo` | `prototype_local` | `production` |
|---|---|---|---|
| Proposito | desarrollo y demos | piloto clinico controlado | despliegue clinico real |
| `local_only` | false | true | true |
| IA online | permitida | bloqueada/degradada | bloqueada/degradada |
| Audio online | permitido | bloqueado | bloqueado |
| Cache audio default | true | false | false |
| Debug transcripts default | true | false | false |
| API key v1 | opcional | obligatoria si se define perfil no demo | obligatoria |
| Persistencia | opcional SQLite | opcional SQLite | opcional, requiere endurecimiento |
| Audit log | opcional | recomendado | obligatorio operacionalmente |
| Datos reales | no | solo con consentimiento | si, tras auditoria |

## Reglas aplicadas por codigo

- `prototype_local` y `production` bloquean providers IA online (`cloudflare`, `both_cloudflare`).
- Si el `IA_PROVIDER` del `.env` apunta a online en perfil local/productivo, se degrada a `heuristic`.
- Requests explicitos a providers de audio online (`openai`, `azure`, `deepgram`) devuelven HTTP 403 en perfiles locales/productivos.
- Endpoints v1 fuera de `demo` requieren header:

```http
X-Internal-API-Key: <INTERNAL_API_KEY>
```

- Si `INTERNAL_API_KEY` falta en perfiles no demo, los endpoints protegidos responden 503.
- `AUDIO_CACHE_ENABLED` es false por defecto fuera de demo.

## `demo`

Para desarrollo, demos y pruebas con datos sinteticos.

`.env` minimo:

```ini
DEPLOYMENT_PROFILE=demo
IA_PROVIDER=heuristic
AUDIO_PROVIDER=faster_whisper
AUDIO_MODEL=medium
AUDIO_ALLOWED_MODELS=large-v3,medium
```

Puede usar providers online si se configuran credenciales. No usar con datos reales.

## `prototype_local`

Para piloto controlado en entorno clinico local.

`.env` minimo:

```ini
DEPLOYMENT_PROFILE=prototype_local
IA_PROVIDER=heuristic
AUDIO_PROVIDER=faster_whisper
AUDIO_MODEL=medium
AUDIO_CACHE_ENABLED=false
INTERNAL_API_KEY=<token-rotable>
```

Si se usa Ollama instalado fuera de Docker:

```ini
IA_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
```

Si la API corre dentro de Docker y Ollama corre en el host:

```ini
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

## `production`

Perfil contractual para despliegue real. Requiere auditoria operativa antes de uso con pacientes.

`.env` minimo:

```ini
DEPLOYMENT_PROFILE=production
IA_PROVIDER=heuristic
AUDIO_PROVIDER=faster_whisper
AUDIO_MODEL=large-v3
AUDIO_CACHE_ENABLED=false
INTERNAL_API_KEY=<token-rotable-largo>
PERSISTENCE_ENABLED=true
PERSISTENCE_DB_PATH=/app/var/reconocimiento.db
AUDIT_LOG_PATH=/app/var/audit.log.jsonl
AUDIT_HMAC_KEY=<secreto-largo>
```

Recomendado:

- reverse proxy con TLS;
- bind interno/controlado;
- almacenamiento cifrado;
- rotacion de `INTERNAL_API_KEY` y `AUDIT_HMAC_KEY`;
- backups cifrados;
- deshabilitar `/docs` y `/redoc` por configuracion antes de exposicion real.

## Docker

Docker Compose levanta:

- `api`
- `frontend`

No levanta Ollama. Usar Ollama externo solo si se configura `OLLAMA_BASE_URL`.

CPU:

```powershell
docker compose up -d --build
```

GPU:

```powershell
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
```

## Verificacion

```powershell
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/ia/providers
```

Frontend:

```text
http://localhost:3010
```

## Tests asociados

- `tests/test_deployment_profiles.py`
- `tests/test_local_only_profile.py`
- `tests/test_provider_policy.py`
- `tests/test_internal_api_key.py`
- `tests/test_safe_logging.py`
