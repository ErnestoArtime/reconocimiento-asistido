# AGENTS.md

Instrucciones para agentes que trabajen en este repositorio.

## Objetivo del proyecto

Este proyecto implementa un sistema de reconocimiento medico asistido. Convierte texto clinico o audio de entrevista/exploracion en sugerencias estructuradas contra el cuestionario local `app/data/json_IA.json`.

La IA no debe escribir directamente en el expediente. Siempre propone respuestas con evidencia y el medico revisa, edita, acepta o rechaza.

## Arquitectura actual

- Backend: FastAPI, Pydantic v2 y Uvicorn.
- Cuestionario: JSON local en `app/data/json_IA.json`.
- Extraccion IA: heuristica local, Ollama local, Cloudflare Workers AI o combinaciones con heuristica.
- Audio: FFmpeg/FFprobe, faster-whisper/WhisperX y hooks para OpenAI, Azure y Deepgram.
- Frontend demo: Next.js en `frontend-demo`, React, MUI y componentes existentes JSX.
- Persistencia opcional: SQLite para sesiones, sugerencias y revisiones.
- Auditoria: log append-only JSONL encadenado con HMAC.
- Despliegue: scripts PowerShell y Docker Compose CPU/GPU.

## Carpetas principales

- `app/main.py`: crea la app FastAPI y monta routers.
- `app/core/config.py`: lee `.env`; aqui viven perfiles, providers y flags.
- `app/api/`: endpoints HTTP y WebSocket.
- `app/models/`: contratos Pydantic, especialmente `ExtractionResponseV1`.
- `app/services/`: logica de cuestionario, extraccion, audio, grafo, riesgos, persistencia y auditoria.
- `app/services/audio/`: proveedores y orquestacion de transcripcion.
- `app/data/`: cuestionario y reglas clinicas locales.
- `frontend-demo/`: demo operativa para el flujo medico.
- `tests/`: pruebas unitarias/integracion ligera.
- `tests/golden/`: set de evaluacion determinista.
- `docs/`: contratos, ADR, politicas y planes.
- `scripts/`: setup, smoke tests, auditoria, benchmarks y utilidades.

## Flujo funcional

```text
audio o texto clinico
-> transcripcion si hay audio
-> modulo history|exam
-> seccion concreta o modulo completo
-> extraccion heuristica/LLM
-> guardia anti-alucinacion
-> validacion contra json_IA.json
-> grafo + quality_report + risk_flags
-> revision humana
-> auditoria/persistencia opcional
```

## Contrato API preferido

Usa endpoints v1 para trabajo nuevo:

- `POST /api/v1/ia/extract-from-text`
- `POST /api/v1/audio/transcribe-and-extract`
- `POST /api/v1/sessions`
- `GET /api/v1/sessions/{session_id}`
- `PATCH /api/v1/suggestions/{suggestion_id}/review`
- `POST /api/v1/audit/events`
- `GET /api/v1/audit/verify`
- `POST /api/v1/jobs`

Mantener endpoints legacy solo por compatibilidad.

## Reglas clinicas y de seguridad

- No inventar datos clinicos. Toda sugerencia debe tener evidencia textual clara.
- No usar el resumen clinico como evidencia. `clinical_summary` es apoyo; la evidencia debe venir del transcript/texto original.
- No persistir audio ni transcripcion completa. La persistencia actual solo guarda sesiones, sugerencias, revisiones y evidencia corta.
- El audit log debe guardar hashes/metadata, no PHI en claro.
- En `prototype_local` y `production`, providers online estan bloqueados por politica.
- En perfiles no demo, endpoints v1 requieren `X-Internal-API-Key`.
- No relajar `extraction_guard` sin prueba que demuestre que no aumenta alucinaciones.
- No cambiar codigos del cuestionario sin actualizar pruebas y golden set afectado.
- Mantener separacion entre `technical_status` y `review_status`.
- `risk_flags` deben ser aditivas y explicitas; no ocultar riesgos para que la UI "se vea limpia".

## Extraccion IA

- El extractor heuristico esta en `app/services/extraction_service.py`.
- Los providers LLM estan en `app/services/llm_provider.py`.
- El filtrado anti-alucinacion esta en `app/services/extraction_guard.py`.
- `section` vacia, `*`, `all`, `todas` o `todo` significa extraccion sobre modulo completo.
- En modulo completo se prefiltran preguntas por relevancia y se puede usar auto-batching.
- Para Ollama, `OLLAMA_THINK=false` es el default recomendado; thinking causa latencias altas y JSON peor para extraccion.
- Cloudflare solo debe exponer modelos instruct no-thinking desde `CLOUDFLARE_ALLOWED_MODELS`.
- `IA_CLINICAL_SUMMARY_ENABLED` es opt-in y no debe cambiar grounding.

## Audio

- Todo audio subido se normaliza con FFmpeg a WAV mono 16 kHz.
- El provider se elige por `AUDIO_PROVIDER` o por request.
- `AUDIO_ALLOWED_MODELS` limita modelos seleccionables para evitar descargas enormes.
- En audio diarizado:
  - `history` extrae preferentemente turnos del paciente.
  - `exam` extrae preferentemente turnos del medico.
  - El transcript completo se conserva para metadatos y alineacion.
- Si evidencia no alinea con segmentos, debe recibir `no_audio_timestamp`.
- No subir audios reales ni fixtures pesados al repo.

## Persistencia y auditoria

- `PERSISTENCE_ENABLED=false` por defecto.
- SQLite local va en `data/reconocimiento.db` por defecto; no versionar bases locales.
- Si se pasa `session_id` a extraccion v1, las sugerencias se guardan si la persistencia esta activa.
- La revision humana registra audit HMAC y, si existe store, actualiza `review_status`.
- `AUDIT_LOG_PATH` y `AUDIT_HMAC_KEY` son necesarios para audit activo.
- No escribir secretos en logs, fixtures, docs ni commits.

## Frontend

- La demo vive en `frontend-demo`.
- Puerto dev: `3010`.
- API base default: `http://127.0.0.1:8000`.
- Mantener el flujo principal como herramienta util, no landing page.
- Mostrar riesgos, evidencia, timestamps, provider/modelo y calidad cuando existan.
- No aceptar automaticamente sugerencias con riesgo bloqueante.

## Comandos utiles

Backend:

```powershell
.\scripts\setup.ps1
.\scripts\start_api.ps1
```

Pruebas ligeras:

```powershell
.\.venv\Scripts\python.exe tests\test_api_v1.py
.\.venv\Scripts\python.exe tests\test_audio_api_v1.py
.\.venv\Scripts\python.exe tests\golden\test_runner.py
.\.venv\Scripts\python.exe scripts\smoke_test.py
```

Frontend:

```powershell
cd frontend-demo
npm install
npm run build
npm run typecheck
```

Evitar ejecuciones pesadas salvo que se pidan:

```powershell
.\.venv\Scripts\python.exe scripts\golden_eval.py --models ...
.\.venv\Scripts\python.exe scripts\spike_json_schema.py --model ...
```

## Git e ignores

- No versionar `.env`, entornos virtuales, caches, logs, bases SQLite, modelos, audios ni screenshots ad-hoc.
- No versionar `frontend-demo/.next`, `node_modules`, `tsconfig.tsbuildinfo` ni reports de pruebas.
- Antes de modificar ignores, comprobar con `git status --short` y `git check-ignore -v <archivo>`.
- Puede haber cambios no confirmados del usuario; no revertirlos sin permiso.

## Criterios de cambio

- Cambios de contrato v1 deben mantener compatibilidad aditiva o actualizar `SCHEMA_VERSION`.
- Cualquier cambio de extraccion, negacion, grafo o riesgos necesita pruebas enfocadas.
- Cambios de audio deben probar al menos provider registry/preproceso o tests existentes si no hay hardware/modelo.
- Cambios frontend deben compilar con `npm run build` cuando sea viable.
- Documentar flags nuevos en `.env.example`, README y/o docs relevantes.
