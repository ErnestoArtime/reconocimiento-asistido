# ADR 0006: audit log append-only con cadena HMAC

Fecha: 2026-05-29

Estado: Aceptado e implementado V1.

## Contexto

Cada decision humana sobre una sugerencia IA debe quedar trazada sin exponer PHI en claro.

Requisitos:

- trazabilidad;
- deteccion de tampering;
- minimizacion de datos;
- verificacion reproducible.

## Decision

Implementar `AuditLog` en `app/services/audit_log.py`:

- formato JSONL append-only;
- cadena HMAC por entrada;
- JSON canonico;
- evidencia como `evidence_hash`;
- verificacion de integridad;
- rotacion opcional por tamano;
- cifrado Fernet opcional de archivos archivados;
- lock interno para concurrencia.

## Endpoints implementados

```text
POST /api/v1/audit/events
GET  /api/v1/audit/events?n=50
GET  /api/v1/audit/verify
PATCH /api/v1/suggestions/{suggestion_id}/review
```

La revision humana escribe audit log automaticamente y actualiza SQLite si la persistencia esta activa.

## Configuracion

```ini
AUDIT_LOG_PATH=audit.log.jsonl
AUDIT_HMAC_KEY=<secreto>
AUDIT_MAX_SIZE_BYTES=0
AUDIT_ARCHIVE_DIR=
AUDIT_ENCRYPT_ARCHIVED=false
AUDIT_ENCRYPT_KEY=
```

Sin `AUDIT_HMAC_KEY`, audit queda desactivado y los endpoints dependientes responden 503.

## Consecuencias

- No guardar evidencia literal en audit.
- Preservar orden exacto de lineas en backups.
- Rotar y cifrar archivados si el almacenamiento no esta cifrado por el sistema.
- No commitear `audit.log.jsonl` ni claves.

## Pendiente

- Firma externa/TSA si se requiere no repudio fuerte.
- Rotacion operacional por fecha/retencion.
- UI de auditor mas completa para DPO.
- Rotacion de clave con re-cifrado de archivados.

## Referencias

- `app/services/audit_log.py`
- `app/api/routes_audit.py`
- `app/api/routes_review.py`
- `tests/test_audit_log.py`
- `tests/test_routes_audit.py`
- `tests/test_routes_review.py`
- `docs/RGPD_POLICY.md`
