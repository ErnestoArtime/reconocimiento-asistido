"""CLI para purgar archivos rotados del audit log por retencion.

Borra archivos `audit-*.jsonl` en el directorio de archivado cuya antiguedad
exceda `--retention-days`. NO toca el archivo activo.

Uso tipico (cron diario):
    python scripts/audit_cleanup.py --retention-days 365
    python scripts/audit_cleanup.py --archive-dir /var/log/reco/archive --retention-days 90 --dry-run

Exit codes:
    0 OK (con o sin archivos borrados)
    2 config invalida
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path


def find_archived_files(archive_dir: Path) -> list[Path]:
    if not archive_dir.exists():
        return []
    return sorted(archive_dir.glob("audit-*.jsonl"))


def stale_files(files: list[Path], retention_days: int, now_ts: float | None = None) -> list[Path]:
    if retention_days <= 0:
        return []
    if now_ts is None:
        now_ts = time.time()
    cutoff = now_ts - (retention_days * 86400)
    return [f for f in files if f.stat().st_mtime < cutoff]


def main() -> int:
    parser = argparse.ArgumentParser(description="Purga archivos rotados del audit log")
    parser.add_argument(
        "--archive-dir",
        default=os.getenv("AUDIT_ARCHIVE_DIR", ""),
        help="Directorio de archivado. Default: $AUDIT_ARCHIVE_DIR o ./archive",
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=int(os.getenv("AUDIT_RETENTION_DAYS", "365")),
        help="Dias de retencion. Archivos mas viejos se borran. Default: 365.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="No borra, solo lista qu archivos serian borrados.",
    )
    args = parser.parse_args()

    if args.retention_days <= 0:
        print(f"[ERROR] retention-days debe ser > 0 (recibido: {args.retention_days})", file=sys.stderr)
        return 2

    archive_dir = Path(args.archive_dir) if args.archive_dir else Path("archive")
    if not archive_dir.exists():
        print(f"[INFO] archive_dir no existe: {archive_dir} (nada que borrar)")
        return 0

    all_files = find_archived_files(archive_dir)
    if not all_files:
        print(f"[INFO] sin archivos audit-*.jsonl en {archive_dir}")
        return 0

    to_delete = stale_files(all_files, args.retention_days)
    if not to_delete:
        print(f"[OK] {len(all_files)} archivos, ninguno excede {args.retention_days}d")
        return 0

    print(f"[INFO] {len(to_delete)}/{len(all_files)} archivos exceden {args.retention_days}d:")
    for f in to_delete:
        age_days = (time.time() - f.stat().st_mtime) / 86400
        size_kb = f.stat().st_size / 1024
        marker = "[DRY]" if args.dry_run else "[DEL]"
        print(f"  {marker} {f.name}  age={age_days:.0f}d  size={size_kb:.1f}KB")
        if not args.dry_run:
            f.unlink()

    if args.dry_run:
        print(f"\n[DRY-RUN] No se borraron archivos. Re-ejecuta sin --dry-run para confirmar.")
    else:
        print(f"\n[OK] {len(to_delete)} archivos eliminados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
