# =============================================================================
# Imagen Docker para el backend FastAPI de reconocimiento-asistido.
#
# - Multi-stage: builder instala wheels; runtime queda slim con solo lo necesario.
# - Base CPU. Para GPU usar Dockerfile.gpu (variante CUDA).
# - Incluye FFmpeg (necesario para preproceso de audio).
# - Modelos (faster-whisper, hf) se montan como volumen para no rehidratar la imagen.
# =============================================================================

ARG PYTHON_VERSION=3.11

# --- Stage 1: builder ---------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

# Toolchain para compilar wheels nativos (webrtcvad, av, ctranslate2 si falta wheel)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        g++ \
        cmake \
        pkg-config \
        libsndfile1-dev \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-audio.txt ./

# Wheels a un directorio para copiarlos al runtime
RUN pip wheel --wheel-dir=/wheels -r requirements.txt -r requirements-audio.txt


# --- Stage 2: runtime ---------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    APP_HOME=/app \
    HF_HOME=/models/huggingface \
    XDG_CACHE_HOME=/models/cache \
    AUDIO_CACHE_DIR=/app/.cache/audio \
    FFMPEG_PATH=/usr/bin/ffmpeg \
    FFPROBE_PATH=/usr/bin/ffprobe

# FFmpeg + libs runtime (audio I/O)
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libsndfile1 \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Usuario sin privilegios
RUN groupadd --system app && useradd --system --gid app --home ${APP_HOME} app

WORKDIR ${APP_HOME}

# Instala desde wheels pre-compilados
COPY --from=builder /wheels /wheels
COPY requirements.txt requirements-audio.txt ./
RUN pip install --no-index --find-links=/wheels -r requirements.txt -r requirements-audio.txt \
    && rm -rf /wheels

# Codigo aplicacion
COPY app ./app
COPY scripts ./scripts

# Crea dirs cache modelos
RUN mkdir -p /models/huggingface /models/cache ${APP_HOME}/.cache/audio \
    && chown -R app:app ${APP_HOME} /models

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
