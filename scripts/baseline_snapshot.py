from __future__ import annotations

import datetime as dt
import importlib.metadata as metadata
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASELINES_DIR = ROOT / "docs" / "baselines"

ENV_KEYS = (
    "IA_PROVIDER",
    "OLLAMA_BASE_URL",
    "OLLAMA_MODEL",
    "OLLAMA_NUM_CTX",
    "AUDIO_PROVIDER",
    "AUDIO_MODEL",
    "AUDIO_DEVICE",
    "AUDIO_COMPUTE_TYPE",
    "AUDIO_LANGUAGE",
    "DEPLOYMENT_PROFILE",
    "LOCAL_ONLY",
)

SECRET_MARKERS = ("TOKEN", "KEY", "SECRET", "PASSWORD", "ACCOUNT_ID", "EMAIL")


def _read_env_file() -> dict[str, str]:
    values: dict[str, str] = {}
    env_path = ROOT / ".env"
    if not env_path.exists():
        return values

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _safe_env_value(key: str, value: str | None) -> str:
    if value is None:
        return ""
    if any(marker in key.upper() for marker in SECRET_MARKERS):
        return "<redacted>"
    return value


def _run_command(command: list[str], timeout_s: int = 60) -> tuple[int, str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
            check=False,
        )
    except FileNotFoundError as exc:
        return 127, str(exc)
    except subprocess.TimeoutExpired as exc:
        return 124, f"Timeout after {timeout_s}s\n{exc.stdout or ''}\n{exc.stderr or ''}"

    output = (completed.stdout or "") + (completed.stderr or "")
    return completed.returncode, output.strip()


def _python_package_version(package: str) -> str:
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return ""


def _read_requirements_file(path: Path) -> str:
    if not path.exists():
        return "<not found>"
    return path.read_text(encoding="utf-8").strip() or "<empty>"


def build_snapshot() -> str:
    env_file_values = _read_env_file()
    now = dt.datetime.now().replace(microsecond=0)

    env_lines = []
    for key in ENV_KEYS:
        value = os.getenv(key, env_file_values.get(key, ""))
        env_lines.append(f"- `{key}`: `{_safe_env_value(key, value)}`")

    ollama_rc, ollama_output = _run_command(["ollama", "--version"], timeout_s=15)
    mojibake_rc, mojibake_output = _run_command(
        ["rg", "-n", "Ã|Â|ð|ï|�", "frontend-demo/app", "frontend-demo/README.md"],
        timeout_s=15,
    )
    smoke_rc, smoke_output = _run_command([sys.executable, "scripts/smoke_test.py"], timeout_s=45)

    package_lines = []
    for package in ("fastapi", "pydantic", "uvicorn", "httpx", "faster-whisper"):
        version = _python_package_version(package)
        package_lines.append(f"- `{package}`: `{version or 'not installed'}`")

    requirements_txt = _read_requirements_file(ROOT / "requirements.txt")
    requirements_audio_txt = _read_requirements_file(ROOT / "requirements-audio.txt")

    return "\n".join(
        [
            f"# Baseline {now.date().isoformat()}",
            "",
            "## Timestamp",
            "",
            f"- Local time: `{now.isoformat(sep=' ')}`",
            "",
            "## System",
            "",
            f"- OS: `{os.name}`",
            f"- Python: `{sys.version.split()[0]}`",
            f"- Executable: `{sys.executable}`",
            "",
            "## Packages",
            "",
            *package_lines,
            "",
            "### requirements.txt",
            "",
            "```text",
            requirements_txt,
            "```",
            "",
            "### requirements-audio.txt",
            "",
            "```text",
            requirements_audio_txt,
            "```",
            "",
            "## Configuration",
            "",
            *env_lines,
            "",
            "## Encoding check",
            "",
            "- Command: `rg -n \"Ã|Â|ð|ï|�\" frontend-demo/app frontend-demo/README.md`",
            f"- Exit code: `{mojibake_rc}`",
            "- Interpretation: exit code `1` means no matches were found.",
            "",
            "```text",
            mojibake_output or "<no output>",
            "```",
            "",
            "## Ollama",
            "",
            f"- Exit code: `{ollama_rc}`",
            "",
            "```text",
            ollama_output or "<no output>",
            "```",
            "",
            "## Smoke test",
            "",
            f"- Exit code: `{smoke_rc}`",
            "",
            "```text",
            smoke_output or "<no output>",
            "```",
            "",
        ]
    )


def main() -> None:
    BASELINES_DIR.mkdir(parents=True, exist_ok=True)
    today = dt.date.today().isoformat()
    output_path = BASELINES_DIR / f"{today}.md"
    output_path.write_text(build_snapshot(), encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    main()
