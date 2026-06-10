# Docker: uso diario

Guia rapida para trabajar con backend FastAPI y frontend Next.js usando Docker Compose.

## Menu interactivo

Tambien puedes usar el menu del proyecto:

```powershell
.\menu.bat
```

Opciones utiles:

- `22`: Docker UP backend + frontend.
- `23`: Docker DOWN.
- `24`: Docker PS.
- `25`: Docker logs API + frontend.
- `26`: Docker rebuild API.
- `27`: Docker rebuild frontend.
- `31`: Smoke test Cloudflare Workers AI.

## Requisitos

- Docker Desktop iniciado.
- Archivo `.env` creado desde `.env.example`.
- Si se usa Ollama, Ollama debe correr en el host, no dentro de Compose.

```powershell
ollama serve
ollama pull gemma4:e4b
```

Para ejecucion local directa, `.env` puede usar:

```ini
OLLAMA_BASE_URL=http://127.0.0.1:11434
```

En Docker Compose la API sobreescribe esa URL con:

```ini
http://host.docker.internal:11434
```

Si necesitas otra URL para Docker, define:

```ini
DOCKER_OLLAMA_BASE_URL=http://host.docker.internal:11434
```

## Puertos

- API: `http://127.0.0.1:8000`
- Frontend: `http://127.0.0.1:3010` por defecto

Si `3010` esta ocupado, usa otro puerto en `.env`:

```ini
FRONTEND_PORT=3012
```

Luego:

```powershell
docker compose up -d frontend
```

## Primer arranque

Desde la raiz del repo:

```powershell
cd C:\Proyectos\reconocimiento-asistido
docker compose up -d --build
```

Ver estado:

```powershell
docker compose ps
```

Ver logs:

```powershell
docker compose logs -f api frontend
```

Abrir:

```text
http://127.0.0.1:8000/docs
http://127.0.0.1:3010
```

Si configuraste `FRONTEND_PORT=3012`, abre:

```text
http://127.0.0.1:3012
```

## Arrancar y parar

Arrancar servicios ya construidos:

```powershell
docker compose up -d
```

Parar servicios sin borrar volumenes:

```powershell
docker compose down
```

Reiniciar un servicio:

```powershell
docker compose restart api
docker compose restart frontend
```

## Cambios en backend

El backend se copia dentro de la imagen. Si cambias archivos en `app/`, `scripts/`, `requirements.txt`, `requirements-audio-cpu.txt` o `Dockerfile`, reconstruye la API:

```powershell
docker compose build api
docker compose up -d api
```

Comando equivalente en una sola linea:

```powershell
docker compose up -d --build api
```

Si cambiaste dependencias o el build se comporta raro, fuerza build limpio:

```powershell
docker compose build --no-cache --progress=plain api
docker compose up -d api
```

Comprobar API:

```powershell
curl http://127.0.0.1:8000/health
```

## Cambios en frontend

El frontend tambien se copia dentro de la imagen. Si cambias archivos en `frontend-demo/app/`, `package.json`, `package-lock.json`, `next.config.mjs` o `frontend-demo/Dockerfile`, reconstruye frontend:

```powershell
docker compose build frontend
docker compose up -d frontend
```

O en una sola linea:

```powershell
docker compose up -d --build frontend
```

Si cambias `NEXT_PUBLIC_API_BASE`, reconstruye frontend. Next.js inyecta esa variable durante build:

```powershell
docker compose build --no-cache frontend
docker compose up -d frontend
```

## Cambios en `.env`

Si cambias variables de runtime del backend:

```powershell
docker compose up -d api
```

Si cambias variables de runtime del frontend que no sean `NEXT_PUBLIC_*`:

```powershell
docker compose up -d frontend
```

Si cambias `NEXT_PUBLIC_API_BASE`, reconstruye frontend:

```powershell
docker compose up -d --build frontend
```

## Ver logs y diagnostico

Logs de todo:

```powershell
docker compose logs -f
```

Logs solo API:

```powershell
docker compose logs -f api
```

Logs solo frontend:

```powershell
docker compose logs -f frontend
```

Estado de contenedores:

```powershell
docker compose ps
```

Inspeccionar procesos Docker:

```powershell
docker ps
```

## Ejecutar comandos dentro de contenedores

Shell en API:

```powershell
docker compose exec api sh
```

Shell en frontend:

```powershell
docker compose exec frontend sh
```

Probar salud desde dentro de la API:

```powershell
docker compose exec api curl -fsS http://127.0.0.1:8000/health
```

## Volumenes

Compose crea volumenes para no perder caches/estado entre reinicios:

- `hf_models`: modelos HuggingFace/faster-whisper.
- `hf_cache`: cache general HF.
- `audio_cache`: cache de audio.
- `app_state`: SQLite opcional y audit log.

Parar contenedores sin borrar volumenes:

```powershell
docker compose down
```

Borrar tambien volumenes:

```powershell
docker compose down -v
```

Usa `down -v` solo si quieres perder caches, base SQLite local y audit log local de Docker.

## Imagen CPU vs GPU

CPU:

```powershell
docker compose up -d --build
```

GPU:

```powershell
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
```

La variante GPU requiere drivers NVIDIA y NVIDIA Container Toolkit.

## Publicar imagenes

Construir:

```powershell
docker build -t reco-asistido:cpu .
docker build -t reco-asistido-frontend:latest ./frontend-demo
```

Etiquetar para un registro:

```powershell
docker tag reco-asistido:cpu <registro>/reco-asistido:cpu
docker tag reco-asistido-frontend:latest <registro>/reco-asistido-frontend:latest
```

Subir:

```powershell
docker push <registro>/reco-asistido:cpu
docker push <registro>/reco-asistido-frontend:latest
```

## Exportar y restaurar imagenes

Exportar imagenes sirve para llevar una version ya construida a otra PC sin
reconstruir alli. Es util si la otra PC tiene mala conexion, no tiene toolchain
o quieres entregar una version cerrada.

En la PC origen:

```powershell
docker save reco-asistido:cpu -o reco-asistido-api.tar
docker save reco-asistido-frontend:latest -o reco-asistido-frontend.tar
```

Copia los `.tar` a la otra PC y cargalos:

```powershell
docker load -i reco-asistido-api.tar
docker load -i reco-asistido-frontend.tar
```

Luego arranca con Compose desde una carpeta que tenga `docker-compose.yml` y un
`.env` local:

```powershell
docker compose up -d
```

### Que llevan las imagenes

La imagen backend lleva:

- codigo de `app/`;
- codigo de `scripts/`;
- dependencias Python instaladas;
- FFmpeg dentro de Linux;
- defaults definidos en el `Dockerfile`.

La imagen frontend lleva:

- codigo de `frontend-demo`;
- build generado de Next.js;
- `NEXT_PUBLIC_API_BASE` usado durante el build.

### Que no llevan las imagenes

Las imagenes no incluyen:

- `.env`;
- `frontend-demo/.env.local`;
- secretos Cloudflare/OpenAI/Azure/Deepgram;
- `AUDIT_HMAC_KEY`;
- bases SQLite locales;
- audit logs locales;
- audios;
- modelos/caches HuggingFace montados en volumen;
- Ollama ni modelos descargados por Ollama.

Cada PC debe tener su propio `.env`. Ejemplo local:

```ini
DEPLOYMENT_PROFILE=demo
IA_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
DOCKER_OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=gemma4:e4b

NEXT_PUBLIC_API_BASE=http://127.0.0.1:8000
FRONTEND_PORT=3010

AUDIO_PROVIDER=faster_whisper
AUDIO_MODEL=tiny
AUDIO_DEVICE=cpu
AUDIO_COMPUTE_TYPE=int8

AUDIT_HMAC_KEY=<secreto-propio>
```

Si se usa Ollama, la otra PC tambien debe instalar Ollama y descargar el modelo:

```powershell
ollama pull gemma4:e4b
```

### Actualizar imagenes cuando cambia el codigo

Las imagenes no se actualizan solas. Si cambia el codigo hay dos caminos.

Opcion recomendada para trabajo diario: actualizar codigo y reconstruir en cada
PC:

```powershell
git pull
docker compose up -d --build
```

Tambien se puede reconstruir solo un servicio:

```powershell
docker compose up -d --build api
docker compose up -d --build frontend
```

Opcion para distribuir una version cerrada: reconstruir en una PC, exportar de
nuevo y cargar en la otra:

```powershell
docker build -t reco-asistido:cpu .
docker build -t reco-asistido-frontend:latest ./frontend-demo

docker save reco-asistido:cpu -o reco-asistido-api.tar
docker save reco-asistido-frontend:latest -o reco-asistido-frontend.tar
```

En la otra PC:

```powershell
docker load -i reco-asistido-api.tar
docker load -i reco-asistido-frontend.tar
docker compose up -d
```

Para un equipo de desarrollo, lo mas claro suele ser Git + `.env` local por PC +
`docker compose up -d --build`. Exportar imagenes conviene mas para despliegues
cerrados o equipos con conexion limitada.

## Problemas comunes

### Puerto 3010 ocupado

Ver que proceso usa el puerto:

```powershell
Get-NetTCPConnection -LocalPort 3010 | Select-Object LocalAddress,LocalPort,State,OwningProcess
Get-Process -Id <PID>
```

Solucion recomendada: usar otro puerto en `.env`:

```ini
FRONTEND_PORT=3012
```

Y levantar:

```powershell
docker compose up -d frontend
```

### Ollama no responde desde Docker

Comprueba en el host:

```powershell
ollama list
curl http://127.0.0.1:11434/api/tags
```

Comprueba desde el contenedor:

```powershell
docker compose exec api curl http://host.docker.internal:11434/api/tags
```

Si falla, revisa que Ollama este corriendo y que Docker Desktop pueda resolver `host.docker.internal`.

### Build lento o timeout en PyPI/Debian

Reintenta con salida detallada:

```powershell
docker compose build --no-cache --progress=plain api
```

Si falla descargando paquetes Debian o PyPI, suele ser red lenta/inestable. Reintenta en una red estable o conserva las capas ya descargadas evitando `--no-cache` en el siguiente intento:

```powershell
docker compose build --progress=plain api
```

### Cambios no se ven en la UI

Reconstruye frontend:

```powershell
docker compose up -d --build frontend
```

Si cambiaste `NEXT_PUBLIC_API_BASE`, usa build limpio:

```powershell
docker compose build --no-cache frontend
docker compose up -d frontend
```

### Cambios de backend no se reflejan

Reconstruye API:

```powershell
docker compose up -d --build api
```
