from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from webapp import config
from webapp.services.nmon_raw_service import nmon_raw_pipeline_status


DEBUG_ROOT = Path(config.INSPECTION_HOME) / "debug"
BUNDLE_DIR = DEBUG_ROOT / "reports"
AI_LOOP_DIR = DEBUG_ROOT / "ai_loop"
AI_RUNTIME_MANIFEST = DEBUG_ROOT / "config" / "ai_runtime_builder_itweb_gpt.json"
AI_RUNTIME_ID = "itweb-gpt.minimal-ai-debug-loop"
DEBUG_SUBDIRS = [
    DEBUG_ROOT / "logs",
    BUNDLE_DIR,
    AI_LOOP_DIR,
    DEBUG_ROOT / "config",
    DEBUG_ROOT / "scripts",
]

SECRET_RE = re.compile(r"(?i)(password|passwd|pwd|token|secret|api[_-]?key|authorization|private[_-]?key)\s*[:=]\s*\S+")
IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
PRIVATE_KEY_RE = re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----.*?-----END [A-Z ]+PRIVATE KEY-----", re.S)


def ensure_debug_layout() -> None:
    for path in DEBUG_SUBDIRS:
        path.mkdir(parents=True, exist_ok=True)
    dev_config = DEBUG_ROOT / "config" / "dev.yaml"
    if not dev_config.exists():
        dev_config.write_text(
            "debug:\n"
            "  dry_run: true\n"
            "  verbose: false\n"
            "  mask_sensitive_data: true\n"
            "  intended_llm: GPT Enterprise only\n",
            encoding="utf-8",
        )
    AI_RUNTIME_MANIFEST.write_text(json.dumps(ai_runtime_manifest(), ensure_ascii=False, indent=2), encoding="utf-8")


def ai_runtime_manifest() -> dict[str, Any]:
    return {
        "runtime_id": AI_RUNTIME_ID,
        "app": config.APP_NAME,
        "version": config.VERSION,
        "patch_id": config.PATCH_ID,
        "purpose": "公司 VM 只產生去識別化除錯資料，GPT Enterprise 只負責分析，不直接連線 VM。",
        "loop": [
            "READ_ISSUE",
            "COLLECT_SANITIZED_BUNDLE",
            "BUILD_GPT_ENTERPRISE_PROMPT",
            "WAIT_FOR_ANALYSIS",
            "CODEX_PATCH_WITH_REGRESSION_TEST",
            "DEPLOY_AND_VERIFY",
        ],
        "inputs": [
            "問題標題",
            "問題描述：現象、操作步驟、預期結果、實際結果",
            "verbose debug 開關",
        ],
        "outputs": [
            "debug/reports/debug_bundle_YYYYMMDD_HHMMSS.zip",
            "debug/ai_loop/ai-debug-loop-YYYYMMDD_HHMMSS.md",
            "debug/ai_loop/ai-debug-loop-YYYYMMDD_HHMMSS.json",
        ],
        "bundle_files": [
            "app_version.json",
            "config_summary.json",
            "runtime.json",
            "system_checks.json",
            "nmon_raw_pipeline.json",
            "logs.json",
            "README_GPT_ENTERPRISE_PROMPT.txt",
            "ai_runtime_manifest.json",
        ],
        "masking": ["IP", "hostname", "username", "password", "token", "api key", "private key"],
        "guardrails": [
            "只使用 GPT Enterprise 分析公司 VM log",
            "不貼個人 GPT Pro",
            "不讓 GPT 直接連線 VM",
            "不在 prompt 中要求未遮蔽敏感資訊",
            "修 code 前先把 bug 轉成回歸測試",
            "部署、刪除資料、憑證調整與破壞性動作必須人工確認",
        ],
        "state_schema": {
            "loop_id": "ai-debug-loop-YYYYMMDD_HHMMSS",
            "status": "waiting_gpt_enterprise_analysis | codex_fixing | verified | blocked",
            "bundle": "debug bundle zip filename",
            "prompt": "GPT Enterprise prompt filename",
            "created_by": "operator",
            "created_at": "ISO-8601 datetime",
            "regression_test": "pytest or functional_validation check",
        },
        "audit": {
            "ui_action": "dev_console.ai_debug_loop",
            "metadata_file": "debug/ai_loop/<loop_id>.json",
            "sensitive_data_policy": "mask before writing bundle and prompt",
        },
        "commands": {
            "create_loop": "./venv/bin/python scripts/ai_debug_loop.py --title '<title>' --detail '<detail>'",
            "collect_bundle": "bash scripts/collect_debug_bundle.sh",
            "regression": "./venv/bin/python -m pytest tests/test_debug_bundle_service.py tests/test_ui_contracts.py -q",
            "health": "curl -fsS http://127.0.0.1:8002/health",
        },
        "validation": [
            "確認 bundle zip 內含 ai_runtime_manifest.json",
            "確認 prompt 不含真實 IP、hostname、帳號、密碼或 token",
            "確認 /health 正常",
            "確認修正前先補 regression test 或 functional_validation 項目",
        ],
    }


def _run(command: list[str], timeout: int = 8) -> dict[str, Any]:
    try:
        proc = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
        return {"command": " ".join(command), "rc": proc.returncode, "stdout": proc.stdout[-12000:], "stderr": proc.stderr[-4000:]}
    except Exception as exc:
        return {"command": " ".join(command), "rc": -1, "stdout": "", "stderr": str(exc)}


def _tail(path: Path, limit: int = 24000) -> str:
    if not path.exists():
        return ""
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - limit), os.SEEK_SET)
            return handle.read().decode("utf-8", errors="replace")
    except Exception as exc:
        return f"read_failed: {exc}"


def _known_hostnames() -> list[str]:
    names = {platform.node(), "secansible", "secclient1", "sec9c2", "localhost"}
    try:
        hosts_path = Path("/etc/hosts")
        if hosts_path.exists():
            for token in re.split(r"\s+", hosts_path.read_text(encoding="utf-8", errors="replace")):
                if token and re.search(r"[A-Za-z]", token) and "." not in token and token not in {"localhost4", "localhost6"}:
                    names.add(token)
    except Exception:
        pass
    return sorted({name for name in names if name and len(name) >= 3}, key=len, reverse=True)


def _known_usernames() -> list[str]:
    names = {"sysinfra", "root", "superadmin", "admin"}
    try:
        passwd_path = Path("/etc/passwd")
        if passwd_path.exists():
            for line in passwd_path.read_text(encoding="utf-8", errors="replace").splitlines():
                name = line.split(":", 1)[0].strip()
                if name and not name.startswith("_") and len(name) >= 3:
                    names.add(name)
    except Exception:
        pass
    return sorted(names, key=len, reverse=True)


def mask_debug_text(text: str) -> str:
    masked = PRIVATE_KEY_RE.sub("<SECRET_MASKED>", str(text))
    masked = SECRET_RE.sub(r"\1=<SECRET_MASKED>", masked)
    masked = IP_RE.sub("<IP_MASKED>", masked)
    for name in _known_hostnames():
        masked = re.sub(rf"\b{re.escape(name)}\b", "<HOST_MASKED>", masked)
    for name in _known_usernames():
        masked = re.sub(rf"\b{re.escape(name)}\b", "<USER_MASKED>", masked)
    return masked


def mask_debug_data(data: Any) -> Any:
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            if re.search(r"(?i)(password|passwd|pwd|token|secret|api[_-]?key|authorization|private[_-]?key)", str(key)):
                result[key] = "<SECRET_MASKED>"
            else:
                result[key] = mask_debug_data(value)
        return result
    if isinstance(data, list):
        return [mask_debug_data(item) for item in data]
    if isinstance(data, str):
        return mask_debug_text(data)
    return data


def _write_json(work_dir: Path, name: str, data: Any) -> None:
    masked = mask_debug_data(data)
    (work_dir / name).write_text(json.dumps(masked, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _write_text(work_dir: Path, name: str, text: str) -> None:
    (work_dir / name).write_text(mask_debug_text(text), encoding="utf-8")


def collect_debug_bundle(created_by: str = "system", verbose: bool = False) -> dict[str, Any]:
    ensure_debug_layout()
    stamp = datetime.now(timezone.utc).astimezone().strftime("%Y%m%d_%H%M%S")
    bundle_name = f"debug_bundle_{stamp}.zip"
    work_dir = BUNDLE_DIR / f"_work_{stamp}"
    work_dir.mkdir(parents=True, exist_ok=True)

    app_info = {
        "app": config.APP_NAME,
        "version": config.VERSION,
        "patch_id": config.PATCH_ID,
        "release_note": config.RELEASE_NOTE,
        "build_time": config.BUILD_TIME,
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "created_by": created_by,
        "policy": "Use GPT Enterprise for company VM logs. Do not paste real DEV logs to personal GPT Pro.",
        "dry_run": True,
        "verbose": bool(verbose),
    }
    config_summary = {
        "inspection_home": config.INSPECTION_HOME,
        "web_port": config.WEB_PORT,
        "edge_port": config.EDGE_PORT,
        "mongo_uri": config.MONGO_URI,
        "mongo_db": config.MONGO_DB_NAME,
        "tz": config.TZ_NAME,
        "debug_root": str(DEBUG_ROOT),
    }
    runtime = {
        "python_version": sys.version,
        "executable": sys.executable,
        "platform": platform.platform(),
        "hostname": platform.node(),
        "os_release": _tail(Path("/etc/os-release"), 8000),
        "pip_freeze": _run([sys.executable, "-m", "pip", "freeze"], timeout=20),
    }
    commands = {
        "health_check": _run(["curl", "-fsS", f"http://127.0.0.1:{config.WEB_PORT}/health"]),
        "systemctl_web": _run(["systemctl", "status", "webitgpt.service", "--no-pager"], timeout=12),
        "systemctl_edge": _run(["systemctl", "status", "webitgpt-edge.service", "--no-pager"], timeout=12),
        "disk": _run(["df", "-h"], timeout=8),
        "memory": _run(["free", "-m"], timeout=8),
        "uptime": _run(["uptime"], timeout=8),
    }
    logs = {
        "app_log": _tail(Path(config.LOGS_DIR) / "app.log"),
        "error_log": _tail(Path(config.LOGS_DIR) / "error.log"),
        "access_log": _tail(Path(config.LOGS_DIR) / "access.log", 16000),
        "install_audit": _tail(Path(config.LOGS_DIR) / "install_audit.log", 12000),
    }
    try:
        nmon_pipeline = nmon_raw_pipeline_status()
    except Exception as exc:
        nmon_pipeline = {"status": "error", "error": str(exc)}

    _write_json(work_dir, "app_version.json", app_info)
    _write_json(work_dir, "config_summary.json", config_summary)
    _write_json(work_dir, "runtime.json", runtime)
    _write_json(work_dir, "system_checks.json", commands)
    _write_json(work_dir, "nmon_raw_pipeline.json", nmon_pipeline)
    _write_json(work_dir, "ai_runtime_manifest.json", ai_runtime_manifest())
    _write_json(work_dir, "logs.json", logs)
    _write_text(
        work_dir,
        "README_GPT_ENTERPRISE_PROMPT.txt",
        "以下是公司 DEV VM 上 Python APP 的去識別化 debug bundle。\n"
        "請協助判斷根本原因、可能修法、需要補哪些 log，以及下一步排查順序。\n"
        "請不要要求直接連線 VM；所有修正會由公司 repo 與部署流程執行。\n",
    )

    zip_path = BUNDLE_DIR / bundle_name
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(work_dir.iterdir()):
            archive.write(path, arcname=path.name)
    for path in work_dir.iterdir():
        path.unlink()
    work_dir.rmdir()
    return {"status": "ok", "bundle": bundle_name, "path": str(zip_path), "size": zip_path.stat().st_size, "created_at": stamp}


def create_ai_debug_loop(issue_title: str, issue_detail: str, created_by: str = "system", verbose: bool = False) -> dict[str, Any]:
    ensure_debug_layout()
    title = (issue_title or "未命名問題").strip()[:120]
    detail = (issue_detail or "請依 debug bundle 判斷問題。").strip()
    bundle = collect_debug_bundle(created_by=created_by, verbose=verbose)
    stamp = datetime.now(timezone.utc).astimezone().strftime("%Y%m%d_%H%M%S")
    loop_id = f"ai-debug-loop-{stamp}"
    prompt_name = f"{loop_id}.md"
    meta_name = f"{loop_id}.json"
    prompt = (
        f"# AI Debug Loop: {title}\n\n"
        "## Runtime\n"
        f"- runtime_id：`{AI_RUNTIME_ID}`\n"
        "- runtime manifest：`ai_runtime_manifest.json`\n"
        "- 模式：ai-runtime-builder 最小單一 debug loop\n\n"
        "## 使用邊界\n"
        "- 只能貼到 GPT Enterprise。\n"
        "- 不讓 GPT 直接連線 VM。\n"
        "- 先判斷根本原因，再提出最小修法與回歸測試。\n"
        "- 請勿要求提供未遮蔽 IP、hostname、帳號、密碼、token 或 key。\n\n"
        "## 問題描述\n"
        f"{detail}\n\n"
        "## 附件\n"
        f"- 去識別化 Debug Bundle：`{bundle['bundle']}`\n\n"
        "## 請 GPT Enterprise 回答格式\n"
        "1. 根本原因：\n"
        "2. 需要確認的證據：\n"
        "3. 最小修法：\n"
        "4. 風險與 rollback：\n"
        "5. 必補回歸測試：\n"
        "6. 部署後驗證指令：\n"
    )
    prompt_path = AI_LOOP_DIR / prompt_name
    prompt_path.write_text(mask_debug_text(prompt), encoding="utf-8")
    meta = {
        "loop_id": loop_id,
        "title": title,
        "bundle": bundle["bundle"],
        "bundle_path": bundle["path"],
        "prompt": prompt_name,
        "prompt_path": str(prompt_path),
        "created_by": created_by,
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "status": "waiting_gpt_enterprise_analysis",
        "regression_test": "先把問題轉成 pytest 或 functional_validation 檢查，再修 code。",
    }
    (AI_LOOP_DIR / meta_name).write_text(json.dumps(mask_debug_data(meta), ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return {**meta, "status": "ok", "loop_status": meta["status"], "bundle_size": bundle["size"]}


def list_debug_bundles(limit: int = 10) -> list[dict[str, Any]]:
    ensure_debug_layout()
    items = []
    for path in sorted(BUNDLE_DIR.glob("debug_bundle_*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        items.append(
            {
                "name": path.name,
                "path": str(path),
                "size": path.stat().st_size,
                "mtime": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).astimezone(),
            }
        )
    return items


def list_ai_debug_loops(limit: int = 10) -> list[dict[str, Any]]:
    ensure_debug_layout()
    items = []
    for path in sorted(AI_LOOP_DIR.glob("ai-debug-loop-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = {"loop_id": path.stem, "status": "read_failed"}
        data["mtime"] = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).astimezone()
        items.append(data)
    return items


def get_ai_debug_loop_prompt(loop_id: str) -> Optional[dict[str, Any]]:
    ensure_debug_layout()
    safe_id = re.sub(r"[^A-Za-z0-9._-]+", "", loop_id or "")
    meta_path = AI_LOOP_DIR / f"{safe_id}.json"
    if not safe_id or not meta_path.exists():
        return None
    data = json.loads(meta_path.read_text(encoding="utf-8"))
    prompt_path = AI_LOOP_DIR / str(data.get("prompt", ""))
    if not prompt_path.exists() or prompt_path.parent != AI_LOOP_DIR:
        return None
    return {"loop": data, "path": str(prompt_path), "name": prompt_path.name}
