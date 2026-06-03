# ADR 0004: validacion del cuestionario como grafo

Fecha: 2026-05-28

Estado: Aceptado.

## Contexto

El cuestionario `app/data/json_IA.json` no es una lista plana. Cada pregunta puede tener transiciones segun el codigo seleccionado.

Sin validar el recorrido, una respuesta puede tener codigo valido pero ser imposible segun la rama tomada.

Ejemplo:

```text
C5-1 = "no fuma" -> rama historica
C5-131 = "cuanto fuma" -> solo alcanzable si fuma actualmente
```

## Decision

Usar `app/services/graph_mapping_engine.py` para generar `GraphReportV1`:

- `entry_question_id`
- `path`
- `accepted_question_ids`
- `discarded`
- `missing_required`
- `conflicts`

## Reglas principales

- Si el `entry_question_id` del modulo pertenece a las preguntas procesadas, se usa como entrada.
- Si no, se usa la primera pregunta del conjunto procesado.
- Con respuesta, se avanza por `transitions[codigo]`.
- Sin respuesta, se avanza solo si todas las transiciones posibles llevan al mismo destino.
- Sugerencias fuera del path se listan en `discarded`.
- El endpoint v1 marca esas sugerencias como `technical_status="discarded_by_graph"` en seccion guiada.
- En modulo completo, el descarte por reachability se relaja para no penalizar entrevista libre multi-seccion.

## Consecuencias

- Todo endpoint v1 de extraccion emite `graph_report`.
- El frontend debe mostrarlo o usarlo para explicar descartes.
- Las sugerencias descartadas no se borran: se conservan para auditoria/revision.

## Limitaciones

- `conflicts` esta reservado y suele estar vacio.
- Si el JSON tiene transiciones incompletas, el path puede truncarse.
- El motor es determinista y no llama a IA.

## Referencias

- `app/services/graph_mapping_engine.py`
- `app/models/extraction_contract.py`
- `tests/test_graph_mapping.py`
- `docs/API_CONTRACT_V1_REFERENCE.md`
