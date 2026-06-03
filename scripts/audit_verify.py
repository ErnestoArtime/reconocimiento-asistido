"""CLI para verificar integridad del audit log.

Uso:
    python scripts/audit_verify.py
    python scripts/audit_verify.py --path /var/log/reco/audit.log.jsonl
    AUDIT_HMAC_KEY=xxx python scripts/audit_verify.py

Exit code: 0 si OK, 1 si tampering, 2 si config invalida.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.services.audit_log import AuditLog  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Verifica cadena HMAC del audit log")
    parser.add_argument(
        "--path",
        default=os.getenv("AUDIT_LOG_PATH", "audit.log.jsonl"),
        help="Ruta al audit log (default: $AUDIT_LOG_PATH o audit.log.jsonl)",
    )
    parser.add_argument(
        "--secret",
        default=os.getenv("AUDIT_HMAC_KEY", ""),
        help="Secret HMAC (default: $AUDIT_HMAC_KEY)",
    )
    args = parser.parse_args()

    if not args.secret:
        print("[ERROR] AUDIT_HMAC_KEY o --secret requerido", file=sys.stderr)
        return 2

    path = Path(args.path)
    if not path.exists():
        print(f"[INFO] audit log no existe: {path} (n=0, ok)")
        return 0

    try:
        log = AuditLog(path=path, secret_key=args.secret)
    except RuntimeError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2

    ok, n, err = log.verify_chain()
    if ok:
        print(f"[OK] {n} entradas, cadena integra")
        return 0
    print(f"[FAIL] n={n} error={err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
