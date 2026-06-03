# Reconocimiento asistido

Sistema para asistir el llenado de reconocimientos medicos a partir de texto clinico o audio. La IA propone respuestas codificadas contra el cuestionario local, muestra evidencia y el medico revisa, edita, acepta o rechaza.

La IA no escribe directamente en el expediente.

## Flujo principal

```text
audio o texto clinico
-> transcripcion, si viene de audio
-> modulo history|exam
-> seccion concreta o modulo completo
-> extraccion por reglas o LLM
-> validacion contra app/data/json_IA.json
-> grafo + calidad + riesgos
-> revision medica en UI
-> auditoria/persistencia opcional
```

## Importante

- No usar `DEPLOYMENT_PROFILE=demo` con datos reales de pacientes.
- La IA no sustituye la revision medica.
- No subir audios reales, bases SQLite, logs, modelos, caches ni `.env` al repositorio.
- Para pilotos con datos reales usar `prototype_local` o `production`.
- En perfiles no demo, los endpoints v1 requieren `X-Internal-API-Key`.

## Arquitectura

- Backend: FastAPI, Pydantic v2, Uvicorn.
- Cuestionario: JSON local en `app/data/json_IA.json`.
- IA de extraccion: heuristica local, Ollama local, Cloudflare Workers AI o combinaciones.
- Audio: FFmpeg/FFprobe + providers de transcripcion.
- Frontend demo: Next.js en `frontend-demo`.
- Persistencia opcional: SQLite para sesiones, sugerencias y revisiones.
- Auditoria: JSONL append-only con cadena HMAC.
- Despliegue: scripts PowerShell y Docker Compose CPU/GPU.

## Requisitos

### Obligatorios

- Windows con PowerShell, o entorno equivalente capaz de ejecutar Python/Node.
- Python 3.11 o 3.12.
- FFmpeg y FFprobe en el `PATH`.
- Node.js para usar la demo web.

### Opcionales

- Ollama si se usara LLM local.
- GPU CUDA para transcripcion local mas rapida.
- Credenciales Cloudflare/OpenAI/Azure/Deepgram si se usan providers online en demo.
- Docker Desktop si se usara Docker Compose.

En Windows, instala Python desde `https://www.python.org/downloads/` y marca `Add python.exe to PATH`.

## Instalacion rapida en Windows

```powershell
cd C:\Proyectos\reconocimiento-asistido
copy .env.example .env
.\scripts\setup.ps1
.\scripts\start_api.ps1
```

Luego abre:

```text
http://127.0.0.1:8000/docs
```

## Configuracion minima

Edita `.env` antes de arrancar.

Configuracion simple para desarrollo:

```ini
DEPLOYMENT_PROFILE=demo
IA_PROVIDER=heuristic
AUDIO_PROVIDER=faster_whisper
AUDIO_MODEL=medium
AUDIO_ALLOWED_MODELS=large-v3,medium
AUDIO_DEVICE=auto
AUDIO_COMPUTE_TYPE=auto
AUDIO_LANGUAGE=es
```

Si usas Ollama local:

```ini
IA_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3:8b
OLLAMA_ALLOWED_MODELS=qwen3:8b,gpt-oss:20b
OLLAMA_THINK=false
```

Si usas Cloudflare Workers AI en demo:

```ini
IA_PROVIDER=cloudflare
CLOUDFLARE_ACCOUNT_ID=...
CLOUDFLARE_API_TOKEN=...
CLOUDFLARE_MODEL=@cf/meta/llama-3.3-70b-instruct-fp8-fast
```

## Perfiles

| Perfil | Uso | Providers online | Cache audio | API key | Datos reales |
|---|---|---|---|---|---|
| `demo` | desarrollo y demos | permitidos | activa por defecto | opcional | no |
| `prototype_local` | piloto controlado | bloqueados | desactivada por defecto | recomendada | con consentimiento |
| `production` | despliegue real | bloqueados | desactivada/cifrada | obligatoria | si, tras auditoria |

Mas detalle: `docs/DEPLOYMENT_PROFILES.md`.

## Arrancar backend manualmente

```powershell
cd C:\Proyectos\reconocimiento-asistido
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install -r requirements-audio.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Arrancar frontend demo

```powershell
cd C:\Proyectos\reconocimiento-asistido\frontend-demo
npm install
npm run dev
```

Abrir:

```text
http://localhost:3010
```

Por defecto consume:

```text
http://127.0.0.1:8000
```

Para cambiarlo:

```powershell
$env:NEXT_PUBLIC_API_BASE="http://127.0.0.1:8000"
npm run dev
```

## Uso desde la demo web

1. Abre `http://localhost:3010`.
2. Selecciona `Historia Clinica` o `Exploracion Fisica`.
3. Elige una seccion o deja `Todas` para entrevista libre.
4. Escribe texto, graba audio o sube un archivo.
5. Usa una de estas acciones:
   - transcribir;
   - extraer desde texto;
   - transcribir y extraer;
   - streaming en vivo, si esta habilitado.
6. Revisa sugerencias, evidencia, confianza, riesgos, timestamps y provider/modelo.
7. Acepta o edita solo despues de validar clinicamente.

## Endpoints principales

Salud:

```text
GET /health
```

Cuestionario:

```text
GET /api/questionnaire/modules
GET /api/questionnaire/{module}/sections
GET /api/questionnaire/{module}/questions
GET /api/questionnaire/{module}/sections/{section}/questions
```

IA:

```text
GET  /api/ia/providers
POST /api/v1/ia/extract-from-text
```

Audio:

```text
GET  /api/audio/providers
POST /api/audio/transcribe
POST /api/v1/audio/transcribe-and-extract
WS   /api/audio/stream
```

Sesiones, revision, auditoria y jobs:

```text
POST  /api/v1/sessions
GET   /api/v1/sessions/{session_id}
POST  /api/v1/sessions/{session_id}/close
PATCH /api/v1/suggestions/{suggestion_id}/review
POST  /api/v1/audit/events
GET   /api/v1/audit/events
GET   /api/v1/audit/verify
POST  /api/v1/jobs
GET   /api/v1/jobs/{job_id}
GET   /api/v1/jobs
```

## Ejemplo texto v1

```http
POST /api/v1/ia/extract-from-text
Content-Type: application/json
```

```json
{
  "module": "history",
  "section": "HABITOS",
  "text": "El paciente dice que no fuma actualmente, pero fumo hasta hace tres anos. No consume alcohol.",
  "ia_provider": "heuristic"
}
```

`section` puede omitirse o mandarse vacia para extraer sobre todo el modulo.

## Audio

El backend acepta `WAV`, `MP3`, `M4A`, `WebM`, `OGG`, `FLAC` y formatos compatibles con FFmpeg. Todo se normaliza a WAV mono 16 kHz antes de transcribir.

Providers previstos:

- `faster_whisper`
- `whisperx`
- `openai`
- `azure`
- `deepgram`

Variables utiles:

```ini
AUDIO_PROVIDER=faster_whisper
AUDIO_MODEL=medium
AUDIO_ALLOWED_MODELS=large-v3,medium
AUDIO_DEVICE=auto
AUDIO_COMPUTE_TYPE=auto
AUDIO_LANGUAGE=es
AUDIO_CACHE_ENABLED=false
```

## Persistencia

La persistencia esta apagada por defecto.

```ini
PERSISTENCE_ENABLED=true
PERSISTENCE_DB_PATH=data/reconocimiento.db
```

Guarda:

- sesiones;
- sugerencias;
- revisiones.

No debe guardar:

- audio;
- transcripcion completa;
- secretos.

## Auditoria

Para activar audit log:

```ini
AUDIT_LOG_PATH=audit.log.jsonl
AUDIT_HMAC_KEY=<secreto-largo>
```

El audit log guarda metadata, hashes de evidencia y cadena HMAC. No debe guardar PHI en claro.

Verificar integridad:

```powershell
.\.venv\Scripts\python.exe scripts\audit_verify.py
```

## Docker

CPU:

```powershell
docker compose up -d --build
```

GPU:

```powershell
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
```

El compose levanta:

- `api`: backend FastAPI.
- `frontend`: demo Next.js en `http://localhost:3010`.

Los modelos, caches, SQLite opcional y audit log se montan como volumenes. El cuestionario sigue dentro de la imagen en `app/data/json_IA.json`.

Ollama no se incluye dentro del Docker Compose. Si quieres usar Ollama instalado en el host, configura `.env` asi:

```ini
IA_PROVIDER=ollama
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

Si no vas a usar Ollama, usa `IA_PROVIDER=heuristic` o un provider online permitido por el perfil.

La variable `NEXT_PUBLIC_API_BASE` se inyecta en el build del frontend. Para uso local normal:

```ini
NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000
```

Si vas a abrir la demo desde otra maquina, pon la URL accesible desde el navegador, por ejemplo:

```powershell
$env:NEXT_PUBLIC_API_BASE="http://192.168.1.50:8000"
docker compose up -d --build
```

Builds individuales:

```powershell
docker build -t reco-asistido:cpu .
docker build -t reco-asistido-frontend:latest .\frontend-demo
```

## Pruebas

Pruebas ligeras recomendadas:

```powershell
.\.venv\Scripts\python.exe tests\test_api_v1.py
.\.venv\Scripts\python.exe tests\test_audio_api_v1.py
.\.venv\Scripts\python.exe tests\golden\test_runner.py
.\.venv\Scripts\python.exe scripts\smoke_test.py
```

Suite completa:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
```

Frontend:

```powershell
cd frontend-demo
npm run build
npm run typecheck
npm run lint
```

Comandos pesados, ejecutar solo si se necesita benchmark/modelos:

```powershell
.\.venv\Scripts\python.exe scripts\golden_eval.py --models ...
.\.venv\Scripts\python.exe scripts\spike_json_schema.py --model ...
```

## Archivos que no deben subirse

El `.gitignore` cubre estos casos:

- `.env`, `.env.*` y secretos.
- `.venv/`, `.venv311/`, `node_modules/`.
- `.cache/`, caches de audio/modelos y Hugging Face.
- modelos/pesos: `*.gguf`, `*.safetensors`, `*.pt`, `*.onnx`, etc.
- audios: `*.wav`, `*.mp3`, `*.m4a`, `*.webm`, etc.
- logs: `*.log`, `audit.log.jsonl`, `uvicorn.*.log`, `ollama_pull.log`.
- bases locales: `data/`, `*.db`, `*.sqlite`, WAL/SHM.
- builds frontend: `.next/`, `out/`, `dist/`, `tsconfig.tsbuildinfo`.
- screenshots temporales.

Antes de commitear:

```powershell
git status --short
git check-ignore -v .env audit.log.jsonl data/reconocimiento.db
```

## Estructura del proyecto

```text
app/
  api/        endpoints HTTP y WebSocket
  core/       configuracion
  data/       cuestionario y reglas clinicas
  models/     contratos Pydantic
  services/   extraccion, audio, grafo, riesgos, persistencia, audit
docs/         contratos, ADR, RGPD, perfiles y estado
frontend-demo/ demo Next.js
scripts/      setup, smoke tests, auditoria, benchmarks
tests/        pruebas y golden set
```

## Documentacion adicional

- `AGENTS.md`: reglas para agentes de desarrollo.
- `frontend-demo/AGENTS.md`: reglas especificas del frontend.
- `docs/API_CONTRACT_V1.md`: contrato operativo v1.
- `docs/API_CONTRACT_V1_REFERENCE.md`: referencia detallada del contrato.
- `docs/DEPLOYMENT_PROFILES.md`: perfiles y politica operacional.
- `docs/RGPD_POLICY.md`: politica de privacidad/compliance.
- `docs/IMPLEMENTATION_STATUS.md`: estado actual y pendientes.
- `docs/adr/`: decisiones de arquitectura.

## Pendientes conocidos

- Ejecutar benchmark completo de modelos locales.
- Validar diarizacion con hardware objetivo.
- Registrar handlers reales de jobs de audio si se usa multi-sala.
- Migrar SQLite a Postgres si se necesita multi-nodo o alta concurrencia.
- Endurecer autenticacion externa si se expone fuera de localhost/LAN controlada.
