# Estado de implementacion

Fecha: 2026-06-03

## Resumen

El sistema actual implementa un backend FastAPI, una demo frontend Next.js y un flujo de reconocimiento medico asistido desde texto o audio. La IA propone respuestas contra `app/data/json_IA.json`; el medico revisa antes de aplicar.

## Implementado

- Contrato versionado `ExtractionResponseV1` (`schema_version = 2026-05-voice-form-v1`).
- Endpoints v1 de texto y audio:
  - `POST /api/v1/ia/extract-from-text`
  - `POST /api/v1/audio/transcribe-and-extract`
- Endpoints legacy conservados para compatibilidad.
- Extraccion sobre seccion concreta o modulo completo (`section` vacia / `*` / `all` / `todas`).
- Validacion de sugerencias contra codigos reales del cuestionario.
- Extractor heuristico local.
- Providers LLM: Ollama externo/local, Cloudflare Workers AI y combinaciones con heuristica.
- JSON Schema dinamico para Ollama via `OLLAMA_USE_JSON_SCHEMA`.
- Auto-batching/lotes pequenos para reducir prompts grandes.
- Guardia anti-alucinacion con grounding literal/fuzzy y filtro de relevancia configurable.
- Resumen clinico opt-in (`IA_CLINICAL_SUMMARY_ENABLED`), expuesto como `clinical_summary`; no es fuente de evidencia.
- Audio con FFmpeg/FFprobe, normalizacion a WAV mono 16 kHz y providers seleccionables.
- Seleccion controlada de modelos de audio con `AUDIO_ALLOWED_MODELS`.
- Streaming WebSocket en `/api/audio/stream`.
- Alineacion de evidencia a segmentos de audio (`audio_start`, `audio_end`).
- Propagacion de speaker por diarizacion y filtrado del hablante esperado por modulo.
- Motor de grafo determinista (`graph_report`).
- `quality_report` y `risk_flags`.
- Reglas de negacion/incertidumbre/temporalidad clinica en YAML.
- Perfiles `DEPLOYMENT_PROFILE=demo|prototype_local|production`.
- Bloqueo de providers online en perfiles locales/productivos.
- API key interna para endpoints v1 fuera de `demo`.
- Logs seguros/sanitizados.
- Persistencia SQLite opcional para sesiones, sugerencias y revisiones.
- Audit log HMAC append-only con endpoints de eventos/listado/verificacion.
- Rotacion/cifrado opcional de archivos archivados de audit log.
- Cola async en memoria para jobs (`noop` implementado).
- Frontend demo Next.js/MUI usando endpoints v1 y mostrando riesgos/timestamps/reportes.
- Docker preparado para backend + frontend. Ollama no se incluye en Docker Compose.

## Stack Docker actual

Servicios:

- `api`: FastAPI.
- `frontend`: Next.js en `http://localhost:3010`.

No se levanta Ollama dentro del Compose. Para usar Ollama instalado en el host:

```ini
IA_PROVIDER=ollama
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

## Pendiente dependiente de infraestructura local

- Ejecutar `scripts/spike_json_schema.py` contra Ollama real/modelos descargados.
- Ejecutar benchmark completo de modelos locales con `scripts/golden_eval.py`.
- Actualizar ADR 0003 con modelo recomendado final tras benchmark.
- Validar diarizacion con hardware objetivo.

## Pendiente de producto/piloto

- Reemplazar cola en memoria por backend persistente si hay multi-sala real.
- Registrar handler real de jobs de audio.
- Exponer en `ExtractionResponseV1` los ids persistidos de sugerencias cuando se guarda una sesion, para revisar sin consultar la sesion.
- Migrar SQLite a Postgres si se necesita multi-nodo o alta concurrencia.
- Endurecer autenticacion externa si se expone fuera de localhost/LAN controlada.
- Deshabilitar Swagger/OpenAPI por perfil si se despliega en produccion.

## Verificacion ligera

```powershell
.\.venv\Scripts\python.exe tests\test_api_v1.py
.\.venv\Scripts\python.exe tests\test_audio_api_v1.py
.\.venv\Scripts\python.exe tests\golden\test_runner.py
.\.venv\Scripts\python.exe scripts\smoke_test.py
cd frontend-demo
npm run build
npm run typecheck
```

## Verificacion pesada

```powershell
.\.venv\Scripts\python.exe scripts\golden_eval.py --models ...
.\.venv\Scripts\python.exe scripts\spike_json_schema.py --model ...
```
