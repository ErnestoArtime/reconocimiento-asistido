# ADR 0001: alcance MVP - `exam / CABEZA` en batch

Fecha: 2026-05-28

Estado: Aceptado.

## Contexto

El MVP debe demostrar fiabilidad de rellenado, no automatizacion total ni cobertura completa del cuestionario.

El cuestionario local (`app/data/json_IA.json`) tiene dos modulos:

- `history`: dialogo medico/paciente.
- `exam`: exploracion fisica/dictado medico.

La seccion `exam/CABEZA` ofrece un caso controlado para validar audio/texto, extraccion, codigos, grafo, evidencia y revision.

## Decision

El MVP inicial se valida sobre:

- modulo principal: `exam`;
- seccion principal: `CABEZA`;
- modo: batch;
- provider audio base: `faster_whisper`;
- provider IA: configurable, medido contra golden set;
- golden set minimo: casos `exam/CABEZA` y `history/HABITOS`.

El sistema ya soporta extraccion de modulo completo y streaming, pero esas capacidades no cambian el criterio del MVP: primero fiabilidad.

## Consecuencias

- El frontend debe mostrar riesgos, evidencia, timestamps, `quality_report` y `graph_report`.
- El motor de grafo y validacion de codigos son obligatorios.
- Streaming, diarizacion y multi-sala son ampliaciones, no condiciones para el MVP inicial.
- Las pruebas golden siguen siendo el punto de control para cambios de extractor/modelo.

## Referencias

- `app/data/json_IA.json`
- `app/services/graph_mapping_engine.py`
- `app/services/risk_flag_policy.py`
- `tests/golden/`
- `docs/API_CONTRACT_V1.md`
