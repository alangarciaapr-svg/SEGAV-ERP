from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_STREAMLIT_URL = "https://segav-erp.streamlit.app/"
DEFAULT_SUPABASE_TABLE = "segav_erp_clientes"
KEEPALIVE_OK_TEXT = "SEGAV_KEEPALIVE_OK"
KEEPALIVE_ERROR_TEXT = "SEGAV_KEEPALIVE_ERROR"


@dataclass
class CheckResult:
    name: str
    ok: bool
    status: int | None
    detail: str


def _env(name: str, default: str = "") -> str:
    return str(os.getenv(name, default) or "").strip()


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "si", "sí"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except Exception:
        return default


def _clean_detail(value: object, limit: int = 240) -> str:
    text = str(value or "").replace("\n", " ").replace("\r", " ").strip()
    return text[:limit] if text else "sin detalle"


def _normalize_pg_dsn(dsn: str) -> str:
    dsn = (dsn or "").strip().strip("'").strip('"')
    if not dsn:
        return ""
    dsn = dsn.replace("\n", "").replace("\r", "")
    if dsn.startswith("postgres://"):
        dsn = "postgresql://" + dsn[len("postgres://") :]
    if "sslmode=" not in dsn:
        dsn += ("&" if "?" in dsn else "?") + "sslmode=require"
    if "connect_timeout=" not in dsn:
        dsn += ("&" if "?" in dsn else "?") + "connect_timeout=10"
    return dsn


def _build_pg_dsn_from_parts() -> str:
    host = _env("SUPABASE_DB_HOST", _env("PGHOST"))
    port = _env("SUPABASE_DB_PORT", _env("PGPORT", "5432")) or "5432"
    dbname = _env("SUPABASE_DB_NAME", _env("PGDATABASE", "postgres")) or "postgres"
    user = _env("SUPABASE_DB_USER", _env("PGUSER"))
    password = _env("SUPABASE_DB_PASSWORD", _env("PGPASSWORD"))
    if not (host and user and password):
        return ""
    return " ".join(
        [
            f"host={host}",
            f"port={port}",
            f"dbname={dbname}",
            f"user={user}",
            f"password={password}",
            "sslmode=require",
            "connect_timeout=10",
        ]
    )


def _pg_dsn_from_env() -> str:
    return _normalize_pg_dsn(_env("SUPABASE_DB_URL", _env("PG_DSN"))) or _build_pg_dsn_from_parts()


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


def _streamlit_keepalive_url() -> str:
    base_url = _env("KEEPALIVE_STREAMLIT_URL", DEFAULT_STREAMLIT_URL).rstrip("/") + "/"
    return f"{base_url}?segav_keepalive=1&segav_keepalive_ts={int(time.time())}"


def _click_streamlit_wake_button(page) -> bool:
    labels = [
        "Yes, get this app back up!",
        "Get this app back up",
        "Wake this app",
    ]
    for label in labels:
        try:
            locator = page.get_by_role("button", name=label)
            if locator.count() == 1:
                locator.click(timeout=10_000)
                return True
        except Exception:
            continue
    return False


def _body_text_from_all_frames(page) -> str:
    chunks: list[str] = []
    for frame in page.frames:
        try:
            text = frame.locator("body").inner_text(timeout=1_500)
        except Exception:
            continue
        text = str(text or "").strip()
        if text:
            chunks.append(text)
    return "\n".join(chunks)


def _wait_for_streamlit_keepalive(page, url: str) -> str:
    timeout_seconds = _env_int("KEEPALIVE_BROWSER_TIMEOUT_SECONDS", 420)
    deadline = time.monotonic() + max(60, timeout_seconds)
    next_refresh = time.monotonic() + 45
    last_text = ""

    while time.monotonic() < deadline:
        if _click_streamlit_wake_button(page):
            page.wait_for_timeout(25_000)
            page.goto(url, wait_until="domcontentloaded", timeout=90_000)
            next_refresh = time.monotonic() + 45

        body_text = _body_text_from_all_frames(page)
        if KEEPALIVE_OK_TEXT in body_text:
            return body_text[:220].replace("\n", " ")
        if KEEPALIVE_ERROR_TEXT in body_text:
            raise RuntimeError(body_text[:300].replace("\n", " "))
        if body_text:
            last_text = body_text[:240].replace("\n", " ")

        if time.monotonic() >= next_refresh:
            page.goto(url, wait_until="domcontentloaded", timeout=90_000)
            next_refresh = time.monotonic() + 45
        else:
            page.wait_for_timeout(5_000)

    detail = f"No se encontró {KEEPALIVE_OK_TEXT} dentro de Streamlit."
    if last_text:
        detail += f" Último texto visible: {last_text}"
    raise RuntimeError(detail)


def ping_streamlit_browser() -> CheckResult:
    url = _streamlit_keepalive_url()
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return CheckResult("streamlit_browser", False, None, f"Playwright no disponible: {_clean_detail(exc)}")

    browser = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="SEGAV-ERP-KeepAlive/1.0",
                viewport={"width": 1440, "height": 1000},
            )
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=90_000)
            detail = _wait_for_streamlit_keepalive(page, url)
        return CheckResult("streamlit_browser", True, None, detail)
    except Exception as exc:
        return CheckResult("streamlit_browser", False, None, _clean_detail(exc))
    finally:
        try:
            if browser is not None:
                browser.close()
        except Exception:
            pass


def ping_streamlit() -> list[CheckResult]:
    base_url = _env("KEEPALIVE_STREAMLIT_URL", DEFAULT_STREAMLIT_URL).rstrip("/") + "/"
    targets = [
        base_url,
        _streamlit_keepalive_url(),
    ]
    results: list[CheckResult] = []
    for target in targets:
        result = _request(target)
        result.name = "streamlit"
        results.append(result)
        time.sleep(2)
    return results


def ping_supabase_postgres() -> CheckResult:
    dsn = _pg_dsn_from_env()
    if not dsn:
        return CheckResult(
            "supabase",
            False,
            None,
            "Sin DSN: configura SUPABASE_DB_URL, PG_DSN o los secretos separados SUPABASE_DB_HOST/USER/PASSWORD.",
        )

    try:
        import psycopg
    except Exception as exc:
        return CheckResult("supabase", False, None, f"psycopg no disponible: {_clean_detail(exc)}")

    try:
        with psycopg.connect(dsn, prepare_threshold=None) as conn:
            with conn.cursor() as cur:
                cur.execute("select 1")
                row = cur.fetchone()
        ok = bool(row and row[0] == 1)
        return CheckResult("supabase", ok, None, "Postgres SELECT 1 OK" if ok else "Postgres SELECT 1 sin resultado")
    except Exception as exc:
        return CheckResult("supabase", False, None, f"Postgres falló: {_clean_detail(exc)}")


def ping_supabase_rest() -> CheckResult:
    supabase_url = _env("SUPABASE_URL").rstrip("/")
    api_key = _env("SUPABASE_SERVICE_ROLE_KEY") or _env("SUPABASE_ANON_KEY")
    table = _env("KEEPALIVE_SUPABASE_TABLE", DEFAULT_SUPABASE_TABLE)

    if not supabase_url or not api_key:
        return CheckResult(
            "supabase",
            False,
            None,
            "Sin REST: configura SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY o SUPABASE_ANON_KEY.",
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


def ping_supabase() -> CheckResult:
    required = _as_bool(_env("KEEPALIVE_REQUIRE_SUPABASE"), False)

    postgres_result = ping_supabase_postgres()
    if postgres_result.ok:
        return postgres_result

    rest_result = ping_supabase_rest()
    if rest_result.ok:
        rest_result.detail = f"REST OK; Postgres no usado: {postgres_result.detail}"
        return rest_result

    detail = f"{postgres_result.detail} | {rest_result.detail}"
    if not required:
        return CheckResult("supabase", True, None, f"Skipped: {detail}")
    return CheckResult("supabase", False, None, detail)


def main() -> int:
    browser_mode = _as_bool(_env("KEEPALIVE_BROWSER"), False)
    if browser_mode:
        browser_result = ping_streamlit_browser()
        results = [browser_result]
        if browser_result.ok:
            results.append(CheckResult("supabase", True, None, "Touched through Streamlit keepalive endpoint."))
    else:
        results = ping_streamlit()
        results.append(ping_supabase())

    print(json.dumps([r.__dict__ for r in results], ensure_ascii=False, indent=2))
    required = [r for r in results if r.name in {"streamlit", "streamlit_browser"}]
    if required and not any(r.ok for r in required):
        return 1
    supabase_required = _as_bool(_env("KEEPALIVE_REQUIRE_SUPABASE"), False)
    supabase_results = [r for r in results if r.name == "supabase"]
    if supabase_required and (not supabase_results or not any(r.ok for r in supabase_results)):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
