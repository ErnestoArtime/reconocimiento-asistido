# AGENTS.md

Instrucciones especificas para agentes que trabajen en `frontend-demo`.

## Rol del frontend

Esta carpeta contiene la demo operativa de reconocimiento medico asistido. La primera pantalla debe seguir siendo una herramienta de trabajo: seleccionar modulo, capturar texto/audio, ver sugerencias, revisar evidencia y aceptar/editar respuestas.

## Stack

- Next.js App Router.
- React 19.
- MUI 7 y `@mui/material-nextjs`.
- Lucide React y MUI Icons.
- Codigo mixto TSX/JSX existente; no migrar todo a TypeScript salvo que se pida.

## Archivos clave

- `app/page.jsx`: flujo principal de la demo.
- `app/lib/api.js`: cliente HTTP/WebSocket contra FastAPI.
- `app/components/SuggestionsPanel.jsx`: arbol de sugerencias y edicion.
- `app/components/AuditPanel.jsx`: visualizacion/verificacion del audit log.
- `app/layout.tsx`, `app/providers.tsx`, `app/theme.ts`: layout y theme MUI.
- `app/globals.css`: estilos globales.

## Reglas de UI

- No convertir la app en landing page.
- La UI debe priorizar flujo clinico denso y escaneable.
- Mostrar siempre que sea posible: evidencia, confianza, riesgos, timestamps, speaker, provider/modelo y reportes de calidad/grafo.
- No aceptar masivamente sugerencias con `riskFlags` o `technicalStatus` distinto de `valid`.
- Mantener agrupacion por seccion backend y dependencias secuenciales del cuestionario.
- No ocultar errores de API; mostrar mensaje accionable al usuario.
- No enviar `X-Internal-API-Key` salvo que se implemente una forma explicita y segura de configurarlo.

## Integracion API

- Preferir endpoints v1:
  - `/api/v1/ia/extract-from-text`
  - `/api/v1/audio/transcribe-and-extract`
  - `/api/v1/audit/...`
  - `/api/v1/suggestions/{id}/review`
- `section` vacia significa modulo completo. No mandar `section` si el usuario eligio "Todas".
- Al seleccionar modelo IA:
  - Ollama y Cloudflare usan `ia_model`.
  - Audio usa `model`.
- Para streaming, el cliente envia PCM s16le mono 16 kHz por WebSocket.

## Comandos

```powershell
npm install
npm run dev
npm run build
npm run typecheck
npm run lint
```

## No versionar

- `node_modules/`
- `.next/`
- `out/`, `build/`, `dist/`
- `.env`, `.env*.local`
- `tsconfig.tsbuildinfo`
- logs, coverage, reports y screenshots ad-hoc.
