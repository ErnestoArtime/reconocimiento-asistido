# ADR 0005: negacion e incertidumbre clinica via reglas YAML

Fecha: 2026-05-28

Estado: Aceptado.

## Contexto

La negacion mal interpretada es un fallo clinico critico:

- "no fuma" debe ser NO actual.
- "nunca ha fumado" debe ser NO actual + NO historico.
- "dejo de fumar hace 3 anos" debe ser NO actual + SI historico.
- "no recuerda" debe marcar incertidumbre/revision.
- "sin alergias conocidas" debe ser NO alergias.

## Decision

Usar reglas YAML propias estilo NegEx-lite como V1.

Implementacion:

- Reglas: `app/data/clinical_negation_es.yaml`.
- Detector: `app/services/clinical_negation.py`.
- Politica de riesgo: `app/services/risk_flag_policy.py`.

## Integracion actual

`apply_risk_flags()` ejecuta `detect_clinical_negation()` sobre la evidencia de cada sugerencia y marca:

- `uncertain_negation` si detecta categoria `uncertainty`.
- `historical_temporality` si detecta categoria `historical`.

Tambien conserva otras banderas (`low_confidence`, `free_text`, `online_provider_used`, `no_audio_timestamp`, `speaker_not_expected`).

## Alcance

La capa actual no invierte codigos automaticamente. Solo marca riesgo para revision humana. Esto es deliberado: ante duda clinica, el medico revisa.

## Limitaciones conocidas

- Scope semantico limitado: la regla detecta cues, pero no resuelve todos los alcances sintacticos complejos.
- Reglas dependen de cobertura del YAML.
- Si aparece un patron nuevo en golden/piloto, debe agregarse al YAML y a tests.

## Alternativas consideradas

- medspaCy completo: mayor dependencia y tamano Docker.
- NegEx-ES standalone: viable para V2.
- Confiar solo en prompt LLM: rechazado por riesgo de inversion de negacion.

## Referencias

- `app/data/clinical_negation_es.yaml`
- `app/services/clinical_negation.py`
- `app/services/risk_flag_policy.py`
- `tests/test_clinical_negation.py`
- `tests/test_risk_flag_policy.py`
