from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from typing import Any, Iterable, Optional


DEFAULT_PAGES = [
    {"path": "/", "name": "首頁", "marker": "IT 巡檢系統"},
    {"path": "/dashboard", "name": "儀表板", "marker": "儀表板"},
    {"path": "/executive", "name": "主管儀表板", "marker": "主管儀表板"},
    {"path": "/hosts", "name": "資產管理", "marker": "資產管理"},
    {"path": "/inspections", "name": "開門檢查", "marker": "開門檢查"},
    {"path": "/accounts", "name": "帳號盤點", "marker": "帳號盤點"},
    {"path": "/software", "name": "軟體盤點", "marker": "軟體盤點"},
    {"path": "/nmon", "name": "效能月報", "marker": "效能月報"},
    {"path": "/security_audit", "name": "安全稽核", "marker": "安全稽核"},
    {"path": "/dependencies", "name": "系統拓撲", "marker": "系統拓撲"},
    {"path": "/superadmin", "name": "系統管理", "marker": "系統管理"},
    {"path": "/superadmin/dev-console", "name": "開發後台", "marker": "開發後台"},
    {"path": "/superadmin/users", "name": "使用者與權限", "marker": "使用者與權限"},
    {"path": "/superadmin/system-health", "name": "健康檢查", "marker": "健康檢查"},
    {"path": "/superadmin/backup-dr", "name": "備份與 DR", "marker": "備份"},
    {"path": "/superadmin/patches", "name": "Patch 與回滾", "marker": "Patch"},
]


MOJIBAKE_PATTERNS = [
    "\ufffd",
    "???",
    "撌",
    "隢",
    "瑼",
    "蝟",
    "甇",
    "閬",
    "敺",
    "銝",
    "嚗",
    "憭",
    "鞈",
    "摰",
    "啣",
    "",
    "",
    "?",
    "?",
]


def parse_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def request(
    opener: urllib.request.OpenerDirector,
    method: str,
    url: str,
    *,
    form: Optional[dict[str, str]] = None,
    timeout: int = 10,
) -> tuple[int, str, Any]:
    headers = {"User-Agent": "webitgpt-smoke-pages/1.0"}
    body: Optional[bytes] = None
    if form is not None:
        body = urllib.parse.urlencode(form).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with opener.open(req, timeout=timeout) as resp:
            raw = resp.read()
            text = raw.decode("utf-8", errors="replace")
            return resp.status, text, parse_json(text)
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        return exc.code, text, parse_json(text)
    except urllib.error.URLError as exc:
        return 0, str(exc), None


def find_mojibake(text: str) -> list[str]:
    found: list[str] = []
    for pattern in MOJIBAKE_PATTERNS:
        if pattern in text and pattern not in found:
            found.append(pattern)
    return found


def html_title(text: str) -> str:
    match = re.search(r"<title>(.*?)</title>", text, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return re.sub(r"\s+", " ", match.group(1)).strip()


def check_page(
    opener: urllib.request.OpenerDirector,
    base_url: str,
    page: dict[str, str],
    expected_version: str,
    timeout: int,
) -> dict[str, Any]:
    url = base_url + page["path"]
    status, text, _ = request(opener, "GET", url, timeout=timeout)
    mojibake = find_mojibake(text)
    checks = {
        "http_200": status == 200,
        "marker": page["marker"] in text,
        "version": expected_version in text,
        "no_mojibake": not mojibake,
        "no_traceback": "Traceback (most recent call last)" not in text and "Internal Server Error" not in text,
    }
    return {
        "name": page["name"],
        "path": page["path"],
        "status": status,
        "title": html_title(text),
        "checks": checks,
        "mojibake": mojibake,
        "ok": all(checks.values()),
    }


def summarize(results: Iterable[dict[str, Any]]) -> dict[str, int]:
    items = list(results)
    passed = sum(1 for item in items if item.get("ok"))
    return {"total": len(items), "passed": passed, "failed": len(items) - passed}


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test webitgpt HTML pages before deployment handoff.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8002")
    parser.add_argument("--username", default="superadmin")
    parser.add_argument("--password", default="change-me")
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--output", default="")
    parser.add_argument("--no-login", action="store_true")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))

    status, _, health = request(opener, "GET", base_url + "/health", timeout=args.timeout)
    expected_version = health.get("version") if status == 200 and isinstance(health, dict) else ""
    health_ok = status == 200 and isinstance(health, dict) and health.get("status") == "ok" and bool(expected_version)

    login_status = None
    if not args.no_login:
        login_status, _, _ = request(
            opener,
            "POST",
            base_url + "/login",
            form={"username": args.username, "password": args.password},
            timeout=args.timeout,
        )

    page_results = [check_page(opener, base_url, page, expected_version, args.timeout) for page in DEFAULT_PAGES]
    summary = summarize(page_results)
    ok = health_ok and summary["failed"] == 0
    result = {
        "ok": ok,
        "base_url": base_url,
        "expected_version": expected_version,
        "health": {"status": status, "ok": health_ok, "body": health},
        "login_status": login_status,
        "summary": summary,
        "pages": page_results,
    }

    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(output + "\n")
    print(output)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
