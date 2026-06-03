# Contrato API v1 - referencia tecnica

Fecha: 2026-06-03

Origen principal: `app/models/extraction_contract.py`.

```text
schema_version = "2026-05-voice-form-v1"
```

## `ExtractionResponseV1`

```jsonc
{
  "schema_version": "2026-05-voice-form-v1",
  "module": "exam",
  "section": "CABEZA",
  "suggestions": [],
  "graph_report": {},
  "quality_report": {},
  "transcription": null,
  "clinical_summary": null
}
```

Campos:

- `module`: `"history"` o `"exam"`.
- `section`: seccion resuelta. `"*"` cuando se extrajo modulo completo.
- `suggestions`: lista de `SuggestionV1`.
- `graph_report`: `GraphReportV1`.
- `quality_report`: `QualityReportV1`.
- `transcription`: `TranscriptionMetaV1 | null`.
- `clinical_summary`: string opcional si `IA_CLINICAL_SUMMARY_ENABLED=true`.

`clinical_summary` no es fuente de evidencia. Las citas deben seguir ancladas al texto/transcript original.

## `SuggestionV1`

```jsonc
{
  "question_id": "E1-3",
  "selected_codes": ["E1-32"],
  "selected_labels": ["No"],
  "free_text": null,
  "confidence": 0.85,
  "evidence": "La boca no es normal",
  "audio_start": 12.4,
  "audio_end": 14.1,
  "speaker": "medico",
  "technical_status": "valid",
  "review_status": "pending",
  "risk_flags": ["low_confidence"],
  "reason": null
}
```

## `GraphReportV1`

```jsonc
{
  "entry_question_id": "E1-1",
  "path": ["E1-1", "E1-2"],
  "accepted_question_ids": ["E1-1"],
  "discarded": [
    {"question_id": "E1-121", "reason": "not_reachable_from_selected_path"}
  ],
  "missing_required": ["E1-2"],
  "conflicts": []
}
```

En extraccion de modulo completo no se aplica descarte por reachability de la misma forma que en seccion guiada.

## `QualityReportV1`

```jsonc
{
  "total_questions_considered": 12,
  "suggestions_valid": 7,
  "suggestions_needing_review": 2,
  "discarded_invalid_code": 0,
  "discarded_by_graph": 1,
  "discarded_by_validator_count": 0,
  "missing_required": 2,
  "evidence_without_timestamp": 1,
  "schema_parse_fail_count": 0,
  "empty_generation_count": 0,
  "provider": "heuristic",
  "model": "",
  "profile": "demo"
}
```

## `TranscriptionMetaV1`

```jsonc
{
  "text": "Cuero cabelludo normal. Boca no es normal.",
  "duration_s": 9.2,
  "rtf": 0.31,
  "provider": "faster_whisper",
  "model": "medium",
  "language": "es",
  "diarized": false
}
```

## Vocabularios

`technical_status`:

- `valid`
- `invalid_code`
- `discarded_by_graph`
- `missing_evidence`
- `parse_error`

`review_status`:

- `pending`
- `accepted`
- `edited`
- `rejected`

`risk_flags`:

- `low_confidence`
- `free_text`
- `conflict`
- `uncertain_negation`
- `no_audio_timestamp`
- `speaker_not_expected`
- `online_provider_used`
- `historical_temporality`

`speaker`:

- `medico`
- `paciente`
- `acompanante`
- `unknown`
- `null`

## Errores HTTP

| Codigo | Caso |
|---|---|
| 200 | OK |
| 400 | Provider/modelo invalido, audio vacio o parametro fuera de rango |
| 401 | API key invalida en perfiles no demo |
| 403 | Provider online bloqueado por perfil local/productivo |
| 404 | Modulo, seccion, job, sesion o sugerencia no encontrada |
| 422 | Body Pydantic invalido |
| 500 | Provider configurado pero no disponible o fallo runtime |
| 503 | Persistencia/audit no configurados cuando el endpoint los requiere |

## Provider resolution

- `IA_PROVIDER` define el default.
- `ia_provider` en request puede sobrescribir el default si esta permitido.
- En `prototype_local` y `production`, `cloudflare` y `both_cloudflare` se bloquean/degradan.
- `ia_model` permite seleccionar un modelo permitido para Ollama o Cloudflare.
- `model` en audio se valida contra `AUDIO_ALLOWED_MODELS`.

## TypeScript

```ts
export type ModuleName = "history" | "exam";
export type TechnicalStatus =
  | "valid"
  | "invalid_code"
  | "discarded_by_graph"
  | "missing_evidence"
  | "parse_error";
export type ReviewStatus = "pending" | "accepted" | "edited" | "rejected";
export type RiskFlag =
  | "low_confidence"
  | "free_text"
  | "conflict"
  | "uncertain_negation"
  | "no_audio_timestamp"
  | "speaker_not_expected"
  | "online_provider_used"
  | "historical_temporality";
export type SpeakerRole = "medico" | "paciente" | "acompanante" | "unknown";

export interface ExtractionResponseV1 {
  schema_version: "2026-05-voice-form-v1";
  module: ModuleName;
  section: string;
  suggestions: SuggestionV1[];
  graph_report: GraphReportV1;
  quality_report: QualityReportV1;
  transcription: TranscriptionMetaV1 | null;
  clinical_summary: string | null;
}
```

## Endpoints relacionados

Ver `docs/API_CONTRACT_V1.md` para lista operativa de endpoints v1.
