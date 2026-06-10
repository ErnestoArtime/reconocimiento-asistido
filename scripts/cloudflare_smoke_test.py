from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.config import get_settings


def _mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def _post_ai_run(
    *,
    account_id: str,
    api_token: str,
    model: str,
    timeout: float,
) -> tuple[int, dict[str, Any]]:
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
    payload = {
        "messages": [
            {
                "role": "system",
                "content": "Responde en JSON estricto y sin texto adicional.",
            },
            {
                "role": "user",
                "content": 'Devuelve exactamente {"status":"ok","provider":"cloudflare"}.',
            },
        ],
        "temperature": 0,
        "max_tokens": 64,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {api_token}"}
    with httpx.Client(timeout=timeout) as client:
        response = client.post(url, json=payload, headers=headers)
        try:
            data = response.json()
        except ValueError:
            data = {"raw": response.text[:500]}
        return response.status_code, data


def _verify_token(api_token: str, timeout: float) -> tuple[int, dict[str, Any]]:
    headers = {"Authorization": f"Bearer {api_token}"}
    with httpx.Client(timeout=timeout) as client:
        response = client.get(
            "https://api.cloudflare.com/client/v4/user/tokens/verify",
            headers=headers,
        )
        try:
            data = response.json()
        except ValueError:
            data = {"raw": response.text[:500]}
        return response.status_code, data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Smoke test de Cloudflare Workers AI usando .env."
    )
    parser.add_argument(
        "--model",
        default="",
        help="Modelo @cf/... a probar. Default: CLOUDFLARE_MODEL.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=0,
        help="Timeout en segundos. Default: CLOUDFLARE_TIMEOUT.",
    )
    parser.add_argument(
        "--skip-token-verify",
        action="store_true",
        help="No llama al endpoint /user/tokens/verify.",
    )
    parser.add_argument(
        "--skip-inference",
        action="store_true",
        help="Solo verifica credenciales, no ejecuta el modelo.",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    account_id = settings.cloudflare_account_id.strip()
    api_token = settings.cloudflare_api_token.strip()
    model = args.model.strip() or settings.cloudflare_model
    timeout = args.timeout or settings.cloudflare_timeout

    print("Cloudflare smoke test")
    print(f"  profile: {settings.deployment_profile}")
    print(f"  account: {_mask(account_id)}")
    print(f"  model:   {model}")
    print(f"  timeout: {timeout}s")

    if not account_id or not api_token:
        print(
            "[ERROR] Faltan CLOUDFLARE_ACCOUNT_ID o CLOUDFLARE_API_TOKEN en .env",
            file=sys.stderr,
        )
        return 2

    if model not in settings.cloudflare_allowed_models:
        print(
            "[WARN] El modelo no esta en CLOUDFLARE_ALLOWED_MODELS; "
            "la llamada directa se intentara igualmente."
        )

    if settings.local_only:
        print(
            "[WARN] DEPLOYMENT_PROFILE bloquea providers online en la API. "
            "Este smoke test directo solo valida credenciales/modelo."
        )

    try:
        if not args.skip_token_verify:
            started = time.perf_counter()
            status, data = _verify_token(api_token, timeout)
            elapsed = (time.perf_counter() - started) * 1000
            success = bool(data.get("success")) if isinstance(data, dict) else False
            print(f"  token verify: HTTP {status} success={success} ({elapsed:.0f} ms)")
            if status >= 400 or not success:
                print(json.dumps(data, ensure_ascii=False, indent=2))
                return 1

        if args.skip_inference:
            print("[OK] Credenciales Cloudflare verificadas.")
            return 0

        started = time.perf_counter()
        status, data = _post_ai_run(
            account_id=account_id,
            api_token=api_token,
            model=model,
            timeout=timeout,
        )
        elapsed = (time.perf_counter() - started) * 1000
    except httpx.HTTPError as exc:
        print(f"[ERROR] Error de red/HTTP Cloudflare: {exc}", file=sys.stderr)
        return 1

    success = bool(data.get("success")) if isinstance(data, dict) else False
    print(f"  inference: HTTP {status} success={success} ({elapsed:.0f} ms)")
    if status >= 400 or not success:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 1

    result = data.get("result") if isinstance(data, dict) else None
    response = result.get("response") if isinstance(result, dict) else result
    print("[OK] Cloudflare Workers AI responde correctamente.")
    if response:
        print(f"  response: {response}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
