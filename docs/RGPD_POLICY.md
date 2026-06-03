# Politica de datos sensibles y RGPD

Fecha: 2026-06-03

Documento tecnico-operativo. Debe revisarse legalmente antes de uso real con datos de pacientes.

## Principio central

La IA propone. El medico decide.

El sistema no debe aplicar automaticamente respuestas clinicas sin revision humana.

## Datos tratados

| Dato | Categoria | Estado actual |
|---|---|---|
| Audio | dato de salud | procesado temporalmente; no se persiste por defecto |
| Transcripcion completa | dato de salud | devuelta al cliente; no se guarda en SQLite |
| Sugerencias | dato de salud | memoria; opcionalmente SQLite si `PERSISTENCE_ENABLED=true` |
| Evidencia corta | dato de salud | parte de la sugerencia; se guarda solo si se persiste la sugerencia |
| Audit log | metadata/hash | guarda hashes de evidencia, no texto clinico literal |
| `.env` / API keys | secreto | no versionar ni registrar |

## Perfiles

| Aspecto | `demo` | `prototype_local` | `production` |
|---|---|---|---|
| Datos reales | no | con consentimiento | tras auditoria |
| Providers online | permitidos | bloqueados | bloqueados |
| Cache audio | activa por defecto | desactivada por defecto | desactivada por defecto |
| Logs verbosos | si | no | no |
| API key v1 | opcional | obligatoria | obligatoria |
| Audit HMAC | opcional | recomendado | obligatorio operacionalmente |

## Garantias implementadas

- `DEPLOYMENT_PROFILE` deriva `settings.local_only`.
- Providers IA online se bloquean/degradan en perfiles locales/productivos.
- Providers audio online se bloquean con HTTP 403 en perfiles locales/productivos.
- Endpoints v1 requieren `X-Internal-API-Key` fuera de `demo`.
- `AUDIO_CACHE_ENABLED=false` por defecto fuera de `demo`.
- `safe_logging.py` ofrece logs sanitizados.
- `PersistenceStore` SQLite guarda sesiones, sugerencias y revisiones, no audio ni transcripcion completa.
- `AuditLog` JSONL usa cadena HMAC y `evidence_hash`.
- El endpoint de revision humana escribe audit log y actualiza persistencia si existe.

## Persistencia

Activacion:

```ini
PERSISTENCE_ENABLED=true
PERSISTENCE_DB_PATH=data/reconocimiento.db
```

Tablas:

- `sessions`
- `suggestions`
- `reviews`

No guardar:

- audio;
- transcripcion completa;
- claves/API tokens;
- texto libre en audit log sin hash.

## Audit log

Activacion:

```ini
AUDIT_LOG_PATH=audit.log.jsonl
AUDIT_HMAC_KEY=<secreto>
```

El log:

- es append-only JSONL;
- encadena entradas con HMAC;
- guarda `evidence_hash`;
- puede rotar por tamano;
- puede cifrar archivados con Fernet si `AUDIT_ENCRYPT_ARCHIVED=true`.

## Obligaciones del operador

- Obtener consentimiento antes de grabar.
- Formar al personal: no aceptar sugerencias sin revisar.
- Configurar `INTERNAL_API_KEY` en perfiles no demo.
- Configurar `AUDIT_HMAC_KEY` si se usa audit.
- Mantener `.env`, bases SQLite, logs y backups fuera del repo.
- Usar almacenamiento cifrado en pilotos/produccion.
- Definir politica de retencion y borrado por paciente.
- Revisar logs y audit trail periodicamente.

## Brechas conocidas antes de produccion

| Brecha | Estado |
|---|---|
| Swagger/OpenAPI visible | pendiente deshabilitar por perfil si se expone fuera de red controlada |
| Persistencia SQLite | suficiente para piloto local; migrar a Postgres si hay multi-nodo |
| Cola async en memoria | reemplazar si hay multi-sala real |
| IDs persistidos no vuelven en `ExtractionResponseV1` | frontend debe consultar sesion para revisar por id persistido |
| Auth externa fuerte | pendiente si se expone fuera de localhost/LAN |

## Providers externos

Solo usar con datos sinteticos o bajo contrato legal adecuado. En `prototype_local` y `production` estan bloqueados por codigo.

| Provider | Uso | Riesgo |
|---|---|---|
| Cloudflare Workers AI | LLM online | requiere DPA/region/politica clara |
| OpenAI | ASR/LLM si se habilita | requiere DPA/region/opt-out |
| Azure Speech | ASR | puede ser viable con region EU |
| Deepgram | ASR | no recomendado para datos salud UE sin revision legal |

## Referencias

- `docs/DEPLOYMENT_PROFILES.md`
- `docs/API_CONTRACT_V1.md`
- `docs/adr/0002-deployment-profiles.md`
- `docs/adr/0006-audit-log-hmac-chain.md`
- `app/services/provider_policy.py`
- `app/api/security.py`
- `app/services/persistence.py`
- `app/services/audit_log.py`
