# Offline Audio Stack

Objetivo: que transcripcion, diarizacion y extraccion puedan ejecutarse sin
servicios externos en runtime.

## Recomendacion del proyecto

Flujo en vivo:

```text
Next.js AudioWorklet
-> WebSocket local /api/audio/stream
-> faster_whisper con modelo pequeno/medio
-> texto provisional en UI
```

Flujo final/refinado:

```text
audio completo o bloque 30-60s
-> ffmpeg WAV mono 16 kHz
-> faster_whisper o WhisperX
-> pyannote/NeMo offline si hay diarizacion
-> alineacion timestamps
-> extraccion local con Ollama
```

`faster_whisper` es la opcion preferida para vivo porque es mas ligero. WhisperX
queda para batch/refinado, alineacion y diarizacion; no debe usarse como motor
principal de parciales en vivo.

## Configuracion recomendada

```env
AUDIO_PROVIDER=faster_whisper
AUDIO_MODEL=medium
AUDIO_STREAM_PROVIDER=faster_whisper
AUDIO_STREAM_MODEL=base
AUDIO_STREAM_PARTIAL_EVERY_S=1.0
AUDIO_STREAM_MIN_SEGMENT_S=1.5
AUDIO_STREAM_MAX_SEGMENT_S=12.0
AUDIO_STREAM_SILENCE_MS=600
IA_PROVIDER=ollama
OLLAMA_THINK=false
AUDIO_MODEL_CACHE_DIR=C:\models\huggingface
AUDIO_OFFLINE_MODE=true
WHISPERX_DIARIZATION_MODEL=C:\models\huggingface\pyannote__speaker-diarization-3.1
```

Para equipos con CPU modesta, usar `AUDIO_STREAM_MODEL=tiny` o `base`. Para el
refinado final, usar `medium`, `large-v3` o `large-v3-turbo` segun hardware.

## Modelos locales

Pre-descargar modelos antes de produccion. Cache usual en Windows:

```powershell
Get-ChildItem "$env:USERPROFILE\.cache\huggingface\hub" -Directory
```

Rutas habituales:

```text
C:\Users\<usuario>\.cache\huggingface\hub
C:\Users\<usuario>\.cache\torch
C:\Users\<usuario>\.ollama\models
```

En Docker, montar esas rutas como volumen o copiarlas dentro de la imagen. La
aplicacion no debe depender de Hugging Face, OpenAI, Deepgram, Google ni CDNs en
runtime.

Preparacion de snapshots:

```powershell
.\.venv\Scripts\python.exe scripts\prepare_offline_models.py --target C:\models\huggingface
```

Si no tienes token/permisos de pyannote todavia:

```powershell
.\.venv\Scripts\python.exe scripts\prepare_offline_models.py --target C:\models\huggingface --skip-pyannote
```

## Diarizacion

Mejor precision:

```text
microfono/canal izquierdo  = medico
microfono/canal derecho    = paciente
```

Si solo hay un microfono, usar diarizacion offline en fase de refinado, no para
el primer texto en vivo. WhisperX + pyannote requiere modelos descargados y
`HF_TOKEN` solo durante preparacion/descarga, no en runtime.

## Prueba obligatoria de offline real

Ejecutar el servicio sin red despues de descargar modelos:

```powershell
docker run --network none <imagen>
```

Si el arranque o una transcripcion intenta descargar modelos, el paquete offline
no esta completo.
