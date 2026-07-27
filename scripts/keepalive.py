from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


DEFAULT_STREAMLIT_URL = "https://segav-erp.streamlit.app/"
DEFAULT_SUPABASE_TABLE = "segav_erp_clientes"


@dataclass
class CheckResult:
    name: str
    ok: bool
    status: int | None
    detail: str


def _env(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or "").strip()


def _request(url: str, *, headers: dict[str, str] | None = None, timeout: int = 45) -> CheckResult:
    req = Request(url, headers=headers or {"User-Agent": "SEGAV-ERP-KeepAlive/1.0"})
    try:
        with urlopen(req, timeout=timeout) as response:
            body = response.read(512).decode("utf-8", errors="ignore")
            return CheckResult(url, True, int(response.status), body[:160].replace("\n", " "))
    except HTTPError as exc:
        body = exc.read(512).decode("utf-8", errors="ignore")
        status = int(exc.code)
        return CheckResult(url, 300 <= status < 400, status, body[:160].replace("\n", " "))
    except URLError as exc:
        return CheckResult(url, False, None, str(exc.reason))
    except Exception as exc:
        return CheckResult(url, False, None, str(exc))


def ping_streamlit() -> list[CheckResult]:
    base_url = _env("KEEPALIVE_STREAMLIT_URL", DEFAULT_STREAMLIT_URL).rstrip("/") + "/"
    targets = [
        base_url,
        urljoin(base_url, "~/+/"),
    ]
    results: list[CheckResult] = []
    for target in targets:
        result = _request(target)
        result.name = "streamlit"
        results.append(result)
        time.sleep(2)
    return results


def ping_supabase() -> CheckResult:
    supabase_url = _env("SUPABASE_URL").rstrip("/")
    api_key = _env("SUPABASE_SERVICE_ROLE_KEY") or _env("SUPABASE_ANON_KEY")
    table = _env("KEEPALIVE_SUPABASE_TABLE", DEFAULT_SUPABASE_TABLE)

    if not supabase_url or not api_key:
        return CheckResult(
            "supabase",
            True,
            None,
            "Skipped: configure SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY or SUPABASE_ANON_KEY in GitHub Actions secrets.",
        )

    rest_url = f"{supabase_url}/rest/v1/{table}?select=*&limit=1"
    headers = {
        "User-Agent": "SEGAV-ERP-KeepAlive/1.0",
        "apikey": api_key,
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }
    result = _request(rest_url, headers=headers)
    result.name = "supabase"
    if result.status in {200, 206}:
        result.ok = True
    return result


def main() -> int:
    results = ping_streamlit()
    results.append(ping_supabase())

    print(json.dumps([r.__dict__ for r in results], ensure_ascii=False, indent=2))
    required = [r for r in results if r.name == "streamlit"]
    if required and not any(r.ok for r in required):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
