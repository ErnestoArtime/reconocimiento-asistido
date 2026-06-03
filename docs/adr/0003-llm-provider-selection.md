# ADR 0003: seleccion de proveedor/modelo IA

Fecha: 2026-05-28

Estado: En evaluacion.

## Contexto

El sistema permite varios proveedores:

- `heuristic`
- `ollama`
- `cloudflare`
- `both`
- `both_cloudflare`

La seleccion de modelo debe basarse en datos: precision, recall, codigos invalidos, errores de negacion, alucinaciones y latencia contra golden set.

## Decision actual

- `heuristic` es la linea base local y segura.
- Ollama puede usarse como provider externo al Docker Compose, configurado por `OLLAMA_BASE_URL`.
- Cloudflare puede usarse solo en `demo` o bajo politica legal adecuada.
- En `prototype_local` y `production`, providers online se bloquean/degradan.
- No hay modelo LLM final recomendado todavia; queda pendiente de benchmark local.

## Metodo

Usar:

```powershell
.\.venv\Scripts\python.exe scripts\golden_eval.py --models heuristic,<modelo1>,<modelo2>
```

Y para JSON Schema:

```powershell
.\.venv\Scripts\python.exe scripts\spike_json_schema.py --model <modelo>
```

## Criterios de decision

- cero codigos prohibidos;
- cero codigos invalidos;
- baja tasa de errores de negacion;
- evidencia anclada al texto;
- buen balance precision/recall;
- latencia aceptable en hardware objetivo;
- estabilidad de JSON estructurado.

## Pendiente

- Ejecutar benchmark completo con modelos candidatos reales.
- Actualizar esta ADR con el modelo recomendado por hardware/perfil.

## Referencias

- `app/services/llm_provider.py`
- `app/services/extraction_guard.py`
- `scripts/golden_eval.py`
- `scripts/spike_json_schema.py`
- `tests/golden/`
