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
FROM python:${PYTHON_VERSION}-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=300 \
    PIP_RETRIES=20 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

COPY requirements.txt requirements-audio-cpu.txt ./

# Wheels a un directorio para copiarlos al runtime. La imagen CPU usa solo
# paquetes con wheels Linux; si alguna dependencia exigiera compilar, preferimos
# fallar rapido antes que instalar toolchains pesados en Docker.
RUN python -m pip install --upgrade pip setuptools wheel \
    && for attempt in 1 2 3; do \
        pip wheel \
            --timeout 300 \
            --retries 20 \
            --prefer-binary \
            --only-binary=:all: \
            --progress-bar off \
            --wheel-dir=/wheels \
            -r requirements.txt \
            -r requirements-audio-cpu.txt \
        && break; \
        status=$?; \
        echo "pip wheel failed on attempt ${attempt}; cleaning temporary files before retry"; \
        rm -rf /tmp/pip-* /root/.cache/pip; \
        if [ "$attempt" = "3" ]; then exit "$status"; fi; \
        sleep 10; \
    done


# --- Stage 2: runtime ---------------------------------------------------------
FROM python:${PYTHON_VERSION}-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=300 \
    PIP_RETRIES=20 \
    APP_HOME=/app \
    HF_HOME=/models/huggingface \
    XDG_CACHE_HOME=/models/cache \
    AUDIO_CACHE_DIR=/app/.cache/audio \
    FFMPEG_PATH=/usr/bin/ffmpeg \
    FFPROBE_PATH=/usr/bin/ffprobe

# Usuario sin privilegios
RUN groupadd --system app && useradd --system --gid app --home ${APP_HOME} app

WORKDIR ${APP_HOME}

# Instala desde wheels pre-compilados
COPY --from=builder /wheels /wheels
COPY requirements.txt requirements-audio-cpu.txt ./
RUN pip install --no-index --find-links=/wheels -r requirements.txt -r requirements-audio-cpu.txt \
    && rm -rf /wheels

# FFmpeg + libs runtime (audio I/O). Se instala despues de copiar wheels desde
# builder para evitar descargas apt en paralelo durante BuildKit.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        libsndfile1 \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

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
