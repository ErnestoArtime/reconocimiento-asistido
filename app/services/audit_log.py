"""Audit log append-only con encadenamiento HMAC (Hito 11 base).

Cada entrada se escribe como una linea JSON en `audit.log.jsonl`. La integridad
se garantiza por una cadena HMAC: `chain_hmac_i = HMAC(secret, prev_chain_hmac || canonical_json(entry))`.

Detectar tampering = recalcular la cadena desde el inicio y comparar.

NO persiste PHI/PII en claro: la evidencia se almacena como `evidence_hash`
(SHA-256 del texto), no la cadena literal. Trazabilidad sin exposicion.

Requisitos:
- `INTERNAL_API_KEY` o variable dedicada `AUDIT_HMAC_KEY` como secreto.
- En `prototype_local`/`production`, el archivo debe vivir en disco cifrado o
  montado con permisos restrictivos.

Pendiente fuera de este modulo:
- Endpoint `POST /api/v1/audit` para inyectar eventos desde frontend al aceptar/editar.
- Endpoint `GET /api/v1/audit/verify` que recalcule la cadena.
- Rotacion de archivos por fecha + retencion configurable.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal


AuditAction = Literal[
    "suggestion_proposed",
    "suggestion_accepted",
    "suggestion_edited",
    "suggestion_rejected",
    "session_started",
    "session_closed",
]


_GENESIS_HMAC = "0" * 64  # sha256 hex placeholder for entry #0


@dataclass(frozen=True)
class AuditEntry:
    """Entrada inmutable de auditoria.

    Conviene tratarla como append-only. Ningun campo se modifica tras escribir.
    """

    timestamp_utc: str
    action: AuditAction
    user_id: str
    patient_id: str
    question_id: str
    selected_codes: list[str] = field(default_factory=list)
    evidence_hash: str = ""
    confidence: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_canonical_json(self) -> str:
        """JSON canonico: keys ordenadas, sin espacios, ascii safe.

        Necesario para que el HMAC sea reproducible (mismo orden = mismo digest).
        """
        payload = {
            "timestamp_utc": self.timestamp_utc,
            "action": self.action,
            "user_id": self.user_id,
            "patient_id": self.patient_id,
            "question_id": self.question_id,
            "selected_codes": list(self.selected_codes),
            "evidence_hash": self.evidence_hash,
            "confidence": self.confidence,
            "extra": self.extra,
        }
        return json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def hash_evidence(text: str) -> str:
    """SHA-256 hex de la evidencia. No revela el contenido pero permite verificar match."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _build_fernet(raw_key: str | bytes):
    """Construye objeto Fernet desde clave arbitraria.

    Si `raw_key` ya es una clave Fernet valida (32 bytes url-safe b64), se usa
    directamente. En caso contrario, se deriva via SHA-256 → base64-urlsafe
    (sin PBKDF2/salt; el secreto debe ser de alta entropia por contrato).
    """
    from cryptography.fernet import Fernet

    if isinstance(raw_key, str):
        raw_key_bytes = raw_key.encode("utf-8")
    else:
        raw_key_bytes = raw_key
    # Intentar usar tal cual si parece Fernet key
    try:
        return Fernet(raw_key_bytes)
    except Exception:
        digest = hashlib.sha256(raw_key_bytes).digest()
        return Fernet(base64.urlsafe_b64encode(digest))


def _compute_chain_hmac(secret: bytes, prev_hmac_hex: str, entry: AuditEntry) -> str:
    """`HMAC(secret, prev_hmac || canonical_json(entry))` → hex."""
    message = prev_hmac_hex.encode("ascii") + entry.to_canonical_json().encode("utf-8")
    return hmac.new(secret, message, hashlib.sha256).hexdigest()


class AuditLog:
    """Logger append-only encadenado.

    Thread-safe via lock (file handle compartido).

    Rotacion opcional:
      - `max_size_bytes > 0`: cuando el archivo activo excede, se mueve a
        `archive_dir/audit-YYYYmmddHHMMSS-<hash6>.jsonl` y arranca uno nuevo.
      - La cadena HMAC se mantiene cross-files: la primera entrada del nuevo
        archivo usa como `prev_chain_hmac` el `chain_hmac` ultimo del archivado.
    """

    def __init__(
        self,
        path: str | Path,
        secret_key: str | bytes | None = None,
        max_size_bytes: int = 0,
        archive_dir: str | Path | None = None,
        encrypt_archived: bool = False,
        encrypt_key: str | bytes | None = None,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        raw_secret = secret_key if secret_key is not None else os.getenv("AUDIT_HMAC_KEY", "")
        if isinstance(raw_secret, str):
            raw_secret = raw_secret.encode("utf-8")
        if not raw_secret:
            raise RuntimeError(
                "AuditLog requiere secret_key (parametro) o AUDIT_HMAC_KEY (env)"
            )
        self._secret = raw_secret
        self._lock = threading.Lock()
        self.max_size_bytes = max(0, int(max_size_bytes))
        self.archive_dir = (
            Path(archive_dir) if archive_dir else self.path.parent / "archive"
        )
        # Cuando rotamos, recordamos el ultimo chain del archivo archivado
        # para que la siguiente entrada lo use como prev_chain_hmac. Asi la
        # cadena HMAC se mantiene cross-files.
        self._post_rotate_prev: str | None = None
        # Cifrado Fernet de archivos archivados (opcional). El archivo activo
        # NUNCA se cifra: necesitamos append/lectura rapidos para verify.
        # Tras rotar, el archivado se sustituye por <name>.jsonl.enc (Fernet).
        self.encrypt_archived = bool(encrypt_archived)
        raw_enc = encrypt_key if encrypt_key is not None else os.getenv("AUDIT_ENCRYPT_KEY", "")
        self._fernet = None
        if self.encrypt_archived:
            if not raw_enc:
                raise RuntimeError(
                    "encrypt_archived=True requiere encrypt_key o AUDIT_ENCRYPT_KEY"
                )
            self._fernet = _build_fernet(raw_enc)

    # --- escritura ----------------------------------------------------------

    def _last_chain_hmac(self) -> str:
        """Lee la ultima linea del log y devuelve su `chain_hmac`. _GENESIS si vacio.

        Tras una rotacion, si el archivo activo aun esta vacio, devuelve el
        ultimo chain del archivo recien archivado (cross-file chain).
        """
        if not self.path.exists() or self.path.stat().st_size == 0:
            return self._post_rotate_prev or _GENESIS_HMAC
        with self.path.open("rb") as fh:
            # Lee desde el final hacia atras buscando la ultima linea
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            chunk = 4096
            offset = max(0, size - chunk)
            fh.seek(offset)
            data = fh.read()
        lines = [line for line in data.splitlines() if line.strip()]
        if not lines:
            return self._post_rotate_prev or _GENESIS_HMAC
        last = json.loads(lines[-1].decode("utf-8"))
        return str(last.get("chain_hmac", _GENESIS_HMAC))

    def _rotate_if_needed(self) -> None:
        """Si max_size_bytes > 0 y archivo excede, archiva y limpia.

        Tras rotar:
          - el archivo activo queda vacio,
          - `_post_rotate_prev` recuerda el ultimo chain del archivado para que
            la proxima entrada lo use como `prev_chain_hmac` (cadena cross-file).
        """
        if self.max_size_bytes <= 0:
            return
        if not self.path.exists() or self.path.stat().st_size < self.max_size_bytes:
            return
        from datetime import datetime, timezone

        self.archive_dir.mkdir(parents=True, exist_ok=True)
        prev_chain = self._last_chain_hmac()
        suffix = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        tag = prev_chain[:6] if prev_chain else "000000"
        target = self.archive_dir / f"audit-{suffix}-{tag}.jsonl"
        os.replace(self.path, target)
        if self.encrypt_archived and self._fernet is not None:
            self._encrypt_archive_file(target)
        self.path.touch()
        self._post_rotate_prev = prev_chain

    def _encrypt_archive_file(self, plaintext_path: Path) -> Path:
        """Cifra archivo archivado con Fernet y borra el plaintext.

        Resultado: `<name>.jsonl.enc` (token Fernet binario). El plaintext
        original se elimina tras escribir el cifrado correctamente.
        """
        assert self._fernet is not None
        data = plaintext_path.read_bytes()
        token = self._fernet.encrypt(data)
        enc_path = plaintext_path.with_suffix(plaintext_path.suffix + ".enc")
        enc_path.write_bytes(token)
        try:
            plaintext_path.unlink()
        except FileNotFoundError:
            pass
        return enc_path

    def decrypt_archive(self, enc_path: str | Path) -> bytes:
        """Descifra un fichero .jsonl.enc archivado y devuelve plaintext bytes.

        Util para verificacion offline o exportacion auditada. Requiere
        `encrypt_archived=True` en el constructor (clave disponible).
        """
        if self._fernet is None:
            raise RuntimeError("AuditLog sin clave de cifrado: no se puede descifrar")
        token = Path(enc_path).read_bytes()
        return self._fernet.decrypt(token)

    def append(self, entry: AuditEntry) -> dict[str, Any]:
        """Escribe entrada + chain_hmac. Devuelve el record final escrito.

        Si `max_size_bytes > 0`, rota antes de anadir cuando el archivo activo
        excede el limite. La cadena HMAC continua intacta: el nuevo archivo
        toma como `prev` el `chain_hmac` ultimo del archivado.
        """
        with self._lock:
            self._rotate_if_needed()
            prev = self._last_chain_hmac()
            chain = _compute_chain_hmac(self._secret, prev, entry)
            record = {
                **json.loads(entry.to_canonical_json()),
                "prev_chain_hmac": prev,
                "chain_hmac": chain,
            }
            line = json.dumps(record, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
            # Tras escribir, ya no hace falta el post-rotate prev (la cadena
            # esta en el archivo activo de nuevo).
            self._post_rotate_prev = None
            return record

    def log_suggestion_accepted(
        self,
        *,
        user_id: str,
        patient_id: str,
        question_id: str,
        selected_codes: list[str],
        evidence: str,
        confidence: float,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Helper para evento comun: medico acepta una sugerencia."""
        entry = AuditEntry(
            timestamp_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            action="suggestion_accepted",
            user_id=user_id,
            patient_id=patient_id,
            question_id=question_id,
            selected_codes=list(selected_codes),
            evidence_hash=hash_evidence(evidence),
            confidence=confidence,
            extra=extra or {},
        )
        return self.append(entry)

    # --- verificacion -------------------------------------------------------

    def verify_chain(self) -> tuple[bool, int, str | None]:
        """Recalcula HMAC desde inicio. Devuelve (ok, n_entries, error_line).

        - ok=True si la cadena es integra.
        - error_line = numero de linea (1-indexed) donde rompe la cadena.
        """
        if not self.path.exists() or self.path.stat().st_size == 0:
            return True, 0, None

        prev = _GENESIS_HMAC
        n = 0
        with self.path.open("r", encoding="utf-8") as fh:
            for idx, raw in enumerate(fh, start=1):
                raw = raw.strip()
                if not raw:
                    continue
                n += 1
                try:
                    record = json.loads(raw)
                except json.JSONDecodeError:
                    return False, n, f"parse error linea {idx}"

                stored_prev = record.get("prev_chain_hmac")
                stored_chain = record.get("chain_hmac")
                if stored_prev != prev:
                    return False, n, f"prev_chain_hmac mismatch linea {idx}"

                # Reconstruir AuditEntry sin los campos derivados
                entry_dict = {k: v for k, v in record.items() if k not in {"prev_chain_hmac", "chain_hmac"}}
                try:
                    entry = AuditEntry(
                        timestamp_utc=entry_dict["timestamp_utc"],
                        action=entry_dict["action"],
                        user_id=entry_dict["user_id"],
                        patient_id=entry_dict["patient_id"],
                        question_id=entry_dict["question_id"],
                        selected_codes=entry_dict.get("selected_codes", []),
                        evidence_hash=entry_dict.get("evidence_hash", ""),
                        confidence=entry_dict.get("confidence"),
                        extra=entry_dict.get("extra", {}),
                    )
                except KeyError as exc:
                    return False, n, f"campo faltante linea {idx}: {exc}"

                expected = _compute_chain_hmac(self._secret, prev, entry)
                if expected != stored_chain:
                    return False, n, f"chain_hmac mismatch linea {idx}"
                prev = stored_chain
        return True, n, None


__all__ = [
    "AuditAction",
    "AuditEntry",
    "AuditLog",
    "hash_evidence",
]
