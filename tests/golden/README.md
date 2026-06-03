# Golden set

Casos de referencia etiquetados manualmente para medir cambios en modelos,
prompts, reglas y validadores.

Reglas:

- Los valores esperados no deben salir de un LLM.
- Cada `question_id` y `selected_codes` debe existir en `app/data/json_IA.json`.
- `forbidden_codes` documenta falsos positivos conocidos o peligrosos.
- Los casos deben mantenerse pequenos y auditables.
- `expected_graph_path` empieza en la primera pregunta de la seccion.
- Toda pregunta en `expected_graph_path` debe tener una respuesta esperada o estar en `expected_missing`.
- Las transiciones entre preguntas respondidas deben coincidir con `transitions` del cuestionario.

Validacion:

```powershell
.\.venv\Scripts\python.exe tests\golden\test_runner.py
```
