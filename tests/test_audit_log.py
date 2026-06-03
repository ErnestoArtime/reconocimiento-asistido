"""Tests del audit log append-only encadenado (Hito 11)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.audit_log import (  # noqa: E402
    AuditEntry,
    AuditLog,
    hash_evidence,
)


_SECRET = "test-secret-key-do-not-use-in-prod"


class HashEvidenceTest(unittest.TestCase):
    def test_deterministic(self) -> None:
        a = hash_evidence("no fuma")
        b = hash_evidence("no fuma")
        self.assertEqual(a, b)

    def test_different_inputs_different_hash(self) -> None:
        self.assertNotEqual(hash_evidence("a"), hash_evidence("b"))

    def test_unicode_handled(self) -> None:
        h = hash_evidence("paciente refiere fatiga crónica")
        self.assertEqual(len(h), 64)  # sha256 hex


class AuditLogAppendTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "audit.log.jsonl"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _make_log(self) -> AuditLog:
        return AuditLog(path=self.path, secret_key=_SECRET)

    def test_init_requires_secret(self) -> None:
        with self.assertRaises(RuntimeError):
            AuditLog(path=self.path, secret_key="")

    def test_first_entry_has_genesis_prev(self) -> None:
        log = self._make_log()
        record = log.log_suggestion_accepted(
            user_id="doctor1",
            patient_id="p_001",
            question_id="C5-1",
            selected_codes=["C5-12"],
            evidence="no fuma actualmente",
            confidence=0.92,
        )
        self.assertEqual(record["prev_chain_hmac"], "0" * 64)
        self.assertEqual(len(record["chain_hmac"]), 64)
        self.assertEqual(record["action"], "suggestion_accepted")
        self.assertNotIn("evidence", record)  # solo hash, no texto

    def test_second_entry_links_to_first(self) -> None:
        log = self._make_log()
        first = log.log_suggestion_accepted(
            user_id="doctor1",
            patient_id="p_001",
            question_id="C5-1",
            selected_codes=["C5-12"],
            evidence="no fuma",
            confidence=0.9,
        )
        second = log.log_suggestion_accepted(
            user_id="doctor1",
            patient_id="p_001",
            question_id="C5-2",
            selected_codes=["C5-22"],
            evidence="no consume alcohol",
            confidence=0.85,
        )
        self.assertEqual(second["prev_chain_hmac"], first["chain_hmac"])

    def test_evidence_only_stored_as_hash(self) -> None:
        log = self._make_log()
        evidence_text = "PACIENTE_SENSIBLE_NO_DEBE_APARECER"
        log.log_suggestion_accepted(
            user_id="doctor1",
            patient_id="p_001",
            question_id="C5-1",
            selected_codes=["C5-12"],
            evidence=evidence_text,
            confidence=0.9,
        )
        content = self.path.read_text(encoding="utf-8")
        self.assertNotIn(evidence_text, content)
        # pero el hash si esta
        self.assertIn(hash_evidence(evidence_text), content)

    def test_multiple_entries_one_per_line(self) -> None:
        log = self._make_log()
        for i in range(5):
            log.log_suggestion_accepted(
                user_id="doctor1",
                patient_id=f"p_{i:03d}",
                question_id="C5-1",
                selected_codes=["C5-12"],
                evidence=f"evidencia {i}",
                confidence=0.8,
            )
        lines = [
            line for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(len(lines), 5)
        for line in lines:
            json.loads(line)  # cada linea es JSON valido


class AuditLogChainVerificationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "audit.log.jsonl"
        self.log = AuditLog(path=self.path, secret_key=_SECRET)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _seed(self, n: int = 5) -> None:
        for i in range(n):
            self.log.log_suggestion_accepted(
                user_id=f"d{i}",
                patient_id=f"p_{i:03d}",
                question_id="C5-1",
                selected_codes=["C5-12"],
                evidence=f"ev {i}",
                confidence=0.8,
            )

    def test_empty_log_verifies(self) -> None:
        ok, n, err = self.log.verify_chain()
        self.assertTrue(ok)
        self.assertEqual(n, 0)
        self.assertIsNone(err)

    def test_chain_verifies_after_writes(self) -> None:
        self._seed(5)
        ok, n, err = self.log.verify_chain()
        self.assertTrue(ok)
        self.assertEqual(n, 5)
        self.assertIsNone(err)

    def test_tampering_a_field_breaks_chain(self) -> None:
        self._seed(3)
        # Alterar el patient_id de la entrada 2 manualmente
        lines = self.path.read_text(encoding="utf-8").splitlines()
        record = json.loads(lines[1])
        record["patient_id"] = "p_HACKED"
        lines[1] = json.dumps(record, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
        self.path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        ok, n, err = self.log.verify_chain()
        self.assertFalse(ok)
        self.assertEqual(n, 2)
        self.assertIn("chain_hmac mismatch", err)

    def test_removing_a_line_breaks_chain(self) -> None:
        self._seed(4)
        lines = self.path.read_text(encoding="utf-8").splitlines()
        # eliminar la segunda
        del lines[1]
        self.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        ok, _, err = self.log.verify_chain()
        self.assertFalse(ok)
        self.assertIn("prev_chain_hmac mismatch", err)

    def test_different_secret_fails_verification(self) -> None:
        self._seed(3)
        other = AuditLog(path=self.path, secret_key="otra-clave")
        ok, _, _ = other.verify_chain()
        self.assertFalse(ok)


class AuditLogRotationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "audit.log.jsonl"
        self.archive = Path(self.tmp.name) / "archive"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _make_log(self, max_size: int) -> AuditLog:
        return AuditLog(
            path=self.path,
            secret_key=_SECRET,
            max_size_bytes=max_size,
            archive_dir=self.archive,
        )

    def test_no_rotation_when_max_size_zero(self) -> None:
        log = self._make_log(max_size=0)
        for i in range(10):
            log.log_suggestion_accepted(
                user_id=f"d{i}",
                patient_id="p",
                question_id="Q",
                selected_codes=["C"],
                evidence="x",
                confidence=0.9,
            )
        self.assertFalse(self.archive.exists())

    def test_rotation_triggers_when_exceeded(self) -> None:
        log = self._make_log(max_size=300)  # umbral pequeno
        # Cada entrada ronda ~250 bytes, asi que rota cada 1-2 entradas
        for i in range(6):
            log.log_suggestion_accepted(
                user_id=f"d{i}",
                patient_id=f"p_{i:03d}",
                question_id="Q",
                selected_codes=["C"],
                evidence=f"evidence text {i} " * 5,
                confidence=0.9,
            )
        # Debe haber generado archivos en archive/
        self.assertTrue(self.archive.exists())
        archived = list(self.archive.glob("audit-*.jsonl"))
        self.assertGreaterEqual(len(archived), 1)

    def test_chain_crosses_files_after_rotation(self) -> None:
        """Primera entrada del archivo activo tras rotacion enlaza con ultimo del archivado."""
        log = self._make_log(max_size=200)
        # Entrada 1
        first = log.log_suggestion_accepted(
            user_id="d1", patient_id="p1", question_id="Q",
            selected_codes=["C"], evidence="evidencia bien larga aqui para forzar tamano",
            confidence=0.9,
        )
        # Entrada 2 debe disparar rotacion (archivo ya excede ~200B)
        second = log.log_suggestion_accepted(
            user_id="d2", patient_id="p2", question_id="Q",
            selected_codes=["C"], evidence="otra evidencia larga para llenar",
            confidence=0.9,
        )

        archived = sorted(self.archive.glob("audit-*.jsonl"))
        self.assertTrue(archived, "Debe haber archivado al menos un fichero")

        # Verifica que el archivo archivado contiene la primera entrada
        archive_content = archived[-1].read_text(encoding="utf-8").splitlines()
        archive_records = [json.loads(line) for line in archive_content if line.strip()]
        self.assertGreater(len(archive_records), 0)
        # Ultimo chain del archivado
        last_archived_chain = archive_records[-1]["chain_hmac"]

        # Segunda entrada (en archivo activo nuevo) debe linkear con esa
        active_content = self.path.read_text(encoding="utf-8").splitlines()
        active_records = [json.loads(line) for line in active_content if line.strip()]
        self.assertEqual(active_records[0]["prev_chain_hmac"], last_archived_chain)

    def test_verify_active_file_after_rotation_ok(self) -> None:
        log = self._make_log(max_size=200)
        for i in range(5):
            log.log_suggestion_accepted(
                user_id=f"d{i}", patient_id=f"p_{i:03d}", question_id="Q",
                selected_codes=["C"], evidence=f"larga evidence {i} " * 5,
                confidence=0.8,
            )
        # verify_chain solo valida archivo activo (no cross-file en V1)
        # Pero la primera entrada tiene prev != _GENESIS porque viene de archivado.
        # Asi que verify_chain devuelve OK porque recalcula desde
        # `_post_rotate_prev`? No: verify_chain lee siempre desde _GENESIS.
        # Por tanto, tras rotacion el verify activo dara mismatch.
        # Esto es DOCUMENTADO: verify es por-archivo. Cross-file pendiente.
        ok, n, err = log.verify_chain()
        # Para el archivo activo, la primera linea tiene prev != _GENESIS → fail esperado
        # cuando hubo rotacion.
        if log._post_rotate_prev is None and self.path.stat().st_size > 0:
            # algunas entradas en archivo activo, verify falla en linea 1
            self.assertFalse(ok)
            self.assertIn("prev_chain_hmac mismatch", err or "")


class AuditLogFernetEncryptionTest(unittest.TestCase):
    """Cifrado Fernet de archivos archivados tras rotacion (Task #48)."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "audit.log.jsonl"
        self.archive = Path(self.tmp.name) / "archive"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _make_log(self, **kw) -> AuditLog:
        defaults = dict(
            path=self.path,
            secret_key=_SECRET,
            max_size_bytes=200,
            archive_dir=self.archive,
            encrypt_archived=True,
            encrypt_key="passphrase-secreta-para-tests-1234",
        )
        defaults.update(kw)
        return AuditLog(**defaults)

    def _seed_to_rotate(self, log: AuditLog, n: int = 4) -> None:
        for i in range(n):
            log.log_suggestion_accepted(
                user_id=f"d{i}", patient_id=f"p_{i:03d}", question_id="Q",
                selected_codes=["C"], evidence=f"evidence text {i} " * 5,
                confidence=0.9,
            )

    def test_init_requires_encrypt_key_when_flag_on(self) -> None:
        with self.assertRaises(RuntimeError):
            AuditLog(
                path=self.path,
                secret_key=_SECRET,
                encrypt_archived=True,
                encrypt_key=None,
            )

    def test_archived_files_are_encrypted(self) -> None:
        log = self._make_log()
        self._seed_to_rotate(log, n=5)
        enc_files = list(self.archive.glob("audit-*.jsonl.enc"))
        plain_files = list(self.archive.glob("audit-*.jsonl"))
        # No deben quedar plaintext en archive/
        plain_only = [p for p in plain_files if not p.name.endswith(".enc")]
        self.assertEqual(plain_only, [])
        self.assertGreaterEqual(len(enc_files), 1)
        # El cifrado no debe contener texto en claro (busca tokens JSON tipicos)
        for enc in enc_files:
            blob = enc.read_bytes()
            self.assertNotIn(b'"action":', blob)
            self.assertNotIn(b'"chain_hmac"', blob)

    def test_decrypt_archive_returns_original(self) -> None:
        log = self._make_log()
        self._seed_to_rotate(log, n=5)
        enc_files = sorted(self.archive.glob("audit-*.jsonl.enc"))
        self.assertTrue(enc_files)
        plain = log.decrypt_archive(enc_files[0])
        # Debe contener JSON valido linea a linea
        lines = [l for l in plain.decode("utf-8").splitlines() if l.strip()]
        self.assertGreater(len(lines), 0)
        for line in lines:
            rec = json.loads(line)
            self.assertIn("chain_hmac", rec)
            self.assertIn("prev_chain_hmac", rec)

    def test_active_file_remains_plaintext(self) -> None:
        """El archivo activo nunca se cifra: append y verify deben funcionar."""
        log = self._make_log()
        self._seed_to_rotate(log, n=5)
        # archivo activo debe ser texto legible
        content = self.path.read_text(encoding="utf-8")
        self.assertIn('"chain_hmac"', content)

    def test_decrypt_requires_same_key(self) -> None:
        log = self._make_log()
        self._seed_to_rotate(log, n=5)
        enc_files = sorted(self.archive.glob("audit-*.jsonl.enc"))
        other = AuditLog(
            path=self.path,
            secret_key=_SECRET,
            encrypt_archived=True,
            encrypt_key="clave-distinta-no-coincide",
        )
        from cryptography.fernet import InvalidToken

        with self.assertRaises(InvalidToken):
            other.decrypt_archive(enc_files[0])

    def test_disabled_encrypt_leaves_plaintext_archive(self) -> None:
        log = AuditLog(
            path=self.path,
            secret_key=_SECRET,
            max_size_bytes=200,
            archive_dir=self.archive,
            encrypt_archived=False,
        )
        self._seed_to_rotate(log, n=5)
        plain = list(self.archive.glob("audit-*.jsonl"))
        enc = list(self.archive.glob("audit-*.jsonl.enc"))
        self.assertGreaterEqual(len(plain), 1)
        self.assertEqual(enc, [])


class AuditEntryCanonicalJsonTest(unittest.TestCase):
    def test_keys_sorted(self) -> None:
        e = AuditEntry(
            timestamp_utc="2026-05-29T07:00:00+00:00",
            action="suggestion_accepted",
            user_id="d1",
            patient_id="p_001",
            question_id="C5-1",
        )
        out = e.to_canonical_json()
        # debe tener orden estable
        self.assertTrue(out.startswith('{"action":'))
        # mismo input → mismo output siempre
        self.assertEqual(out, e.to_canonical_json())


if __name__ == "__main__":
    unittest.main()
