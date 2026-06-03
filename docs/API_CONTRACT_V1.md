# API contract v1

Fecha: 2026-06-03

Contrato preferido para clientes nuevos. Los endpoints legacy siguen existiendo, pero las integraciones deben usar `/api/v1/...`.

## Texto

```http
POST /api/v1/ia/extract-from-text
Content-Type: application/json
```

Body:

```json
{
  "module": "exam",
  "section": "CABEZA",
  "text": "La boca esta normal.",
  "ia_provider": "heuristic",
  "ia_model": null,
  "session_id": null
}
```

Notas:

- `module`: `history` o `exam`.
- `section` opcional. Vacia, `*`, `all`, `todas` o `todo` significa modulo completo.
- `ia_provider`: override opcional (`heuristic`, `ollama`, `cloudflare`, `both`, `both_cloudflare`).
- `ia_model`: override opcional para modelos Ollama o Cloudflare permitidos.
- `session_id`: si existe y `PERSISTENCE_ENABLED=true`, guarda sugerencias en la sesion.

Respuesta: `ExtractionResponseV1`.

Incluye:

- `schema_version`
- `module`
- `section`
- `suggestions`
- `graph_report`
- `quality_report`
- `transcription: null`
- `clinical_summary` si `IA_CLINICAL_SUMMARY_ENABLED=true`

## Audio

```http
POST /api/v1/audio/transcribe-and-extract
Content-Type: multipart/form-data
```

Campos:

- `audio`: fichero.
- `module`: `history|exam`.
- `section`: seccion opcional. Vacia = modulo completo.
- `session_id`: opcional.
- `provider`: provider STT opcional.
- `model`: modelo STT opcional, validado contra `AUDIO_ALLOWED_MODELS`.
- `ia_provider`: provider extractor opcional.
- `ia_model`: modelo IA opcional.
- `language`: idioma opcional.
- `diarize`: boolean opcional.
- `use_clinical_prompt`: boolean.
- `use_cache`: boolean.

Respuesta: `ExtractionResponseV1`.

Ademas de la respuesta de texto:

- `transcription` contiene metadata STT.
- Las sugerencias pueden incluir `audio_start` / `audio_end`.
- Si una evidencia no alinea con segmentos de audio, se marca `no_audio_timestamp`.
- Si hay diarizacion, `history` prioriza turnos de paciente y `exam` turnos de medico para extraer.

## Sesiones y revision

Requiere `PERSISTENCE_ENABLED=true` para crear/leer/cerrar sesiones.

```http
POST /api/v1/sessions
GET  /api/v1/sessions/{session_id}
POST /api/v1/sessions/{session_id}/close
```

Revision humana:

```http
PATCH /api/v1/suggestions/{suggestion_id}/review
```

La revision escribe audit log HMAC y, si la sugerencia existe en SQLite, actualiza su `review_status`.

## Audit log

Requiere `AUDIT_LOG_PATH` y `AUDIT_HMAC_KEY`.

```http
POST /api/v1/audit/events
GET  /api/v1/audit/events?n=50
GET  /api/v1/audit/verify
```

El audit log guarda metadata, hashes de evidencia y cadena HMAC. No guarda evidencia clinica en claro.

## Jobs

```http
POST /api/v1/jobs
GET  /api/v1/jobs/{job_id}
GET  /api/v1/jobs
```

La cola actual es en memoria y el handler implementado es `noop`. Los jobs de audio pesados deben registrarse antes de un piloto multi-sala real.

## Seguridad por perfil

En `DEPLOYMENT_PROFILE=demo`, los endpoints v1 no requieren API key.

En `prototype_local` y `production`, los endpoints v1 exigen:

```http
X-Internal-API-Key: <INTERNAL_API_KEY>
```

Los proveedores IA/audio online se bloquean en perfiles locales/productivos.
