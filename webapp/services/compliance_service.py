from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from pymongo import DESCENDING

from webapp import config
from webapp.services import host_service
from webapp.services.feature_flags import is_enabled
from webapp.services.host_dir_service import init_dir
from webapp.services.mongo_service import get_collection
from webapp.services.runner_dispatcher import get_runner


DEFAULT_RULES = [
    {
        "rule_id": "TWGCB-ACC-001",
        "type": "account",
        "action": "blacklist",
        "category": "white_box",
        "target": "guest",
        "scope": {"host_type": ["linux"], "host_group": [], "host_ids": [], "environment": []},
        "severity": "high",
        "remediation": {"command": "userdel guest", "type": "shell", "auto_apply": False},
        "compliance_ref": "TWGCB-ACC-001",
        "active": True,
        "yaml_source": "builtin",
    },
    {
        "rule_id": "TWGCB-PORT-001",
        "type": "port",
        "action": "blacklist",
        "category": "white_box",
        "target": "23",
        "scope": {"host_type": ["linux", "windows", "aix"], "host_group": [], "host_ids": [], "environment": []},
        "severity": "critical",
        "remediation": {"command": "disable telnet service", "type": "manual", "auto_apply": False},
        "compliance_ref": "TWGCB-PORT-001",
        "active": True,
        "yaml_source": "builtin",
    },
    {
        "rule_id": "TWGCB-SSH-001",
        "type": "setting",
        "action": "whitelist",
        "category": "white_box",
        "target": "PermitRootLogin=no",
        "scope": {"host_type": ["linux", "aix"], "host_group": [], "host_ids": [], "environment": []},
        "severity": "high",
        "remediation": {"command": "set PermitRootLogin no", "type": "manual", "auto_apply": False},
        "compliance_ref": "TWGCB-SSH-001",
        "active": True,
        "yaml_source": "builtin",
    },
    {
        "rule_id": "TWGCB-FILE-001",
        "type": "file",
        "action": "whitelist",
        "category": "white_box",
        "target": "/etc/ssh/sshd_config",
        "scope": {"host_type": ["linux", "aix"], "host_group": [], "host_ids": [], "environment": []},
        "severity": "medium",
        "remediation": {"command": "restore sshd_config baseline", "type": "manual", "auto_apply": False},
        "compliance_ref": "TWGCB-FILE-001",
        "active": True,
        "yaml_source": "builtin",
    },
    {
        "rule_id": "TWGCB-PKG-001",
        "type": "package",
        "action": "blacklist",
        "category": "white_box",
        "target": "telnet",
        "scope": {"host_type": ["linux", "aix"], "host_group": [], "host_ids": [], "environment": []},
        "severity": "medium",
        "remediation": {"command": "remove telnet package", "type": "manual", "auto_apply": False},
        "compliance_ref": "TWGCB-PKG-001",
        "active": True,
        "yaml_source": "builtin",
    },
    {
        "rule_id": "TWGCB-PROC-001",
        "type": "process",
        "action": "blacklist",
        "category": "white_box",
        "target": "telnetd",
        "scope": {"host_type": ["linux", "aix"], "host_group": [], "host_ids": [], "environment": []},
        "severity": "high",
        "remediation": {"command": "stop telnet daemon", "type": "manual", "auto_apply": False},
        "compliance_ref": "TWGCB-PROC-001",
        "active": True,
        "yaml_source": "builtin",
    },
    {
        "rule_id": "TWGCB-SVC-001",
        "type": "service",
        "action": "whitelist",
        "category": "white_box",
        "target": "sshd",
        "scope": {"host_type": ["linux", "aix"], "host_group": [], "host_ids": [], "environment": []},
        "severity": "medium",
        "remediation": {"command": "start sshd service", "type": "manual", "auto_apply": False},
        "compliance_ref": "TWGCB-SVC-001",
        "active": True,
        "yaml_source": "builtin",
    },
    {
        "rule_id": "TWGCB-IP-001",
        "type": "ip",
        "action": "blacklist",
        "category": "black_box",
        "target": "0.0.0.0/0",
        "scope": {"host_type": ["linux", "windows", "aix"], "host_group": [], "host_ids": [], "environment": []},
        "severity": "medium",
        "remediation": {"command": "restrict wide-open source network", "type": "manual", "auto_apply": False},
        "compliance_ref": "TWGCB-IP-001",
        "active": True,
        "yaml_source": "builtin",
    },
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


SEVERITY_LABELS = {"critical": "重大", "high": "高", "medium": "中", "low": "低"}
SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}


def _plain(doc: dict[str, Any]) -> dict[str, Any]:
    out = {k: v for k, v in doc.items() if k != "_id"}
    return out


def _json_dump(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _finding_query(asset_seq: str, rule_id: Optional[str] = None) -> dict[str, Any]:
    query: dict[str, Any] = {"asset_seq": asset_seq, "fixed_at": None}
    if rule_id:
        query["rule_id"] = rule_id
    return query


def ensure_default_rules(user: str = "bootstrap") -> int:
    inserted = 0
    now = _now()
    for rule in DEFAULT_RULES:
        doc = {**rule, "created_at": now, "updated_at": now, "created_by": user}
        result = get_collection("compliance_rules").update_one({"rule_id": rule["rule_id"]}, {"$setOnInsert": doc}, upsert=True)
        if result.upserted_id:
            inserted += 1
    return inserted


def list_rules(active_only: bool = False) -> list[dict[str, Any]]:
    query = {"active": True} if active_only else {}
    return list(get_collection("compliance_rules").find(query, {"_id": 0}).sort("rule_id", 1))


def upsert_rule(rule: dict[str, Any], user: str) -> dict[str, Any]:
    rule_id = rule.get("rule_id", "").strip()
    if not rule_id:
        raise ValueError("rule_id is required")
    now = _now()
    doc = {
        "rule_id": rule_id,
        "type": rule.get("type", "setting"),
        "action": rule.get("action", "blacklist"),
        "category": rule.get("category", "white_box"),
        "target": rule.get("target", ""),
        "scope": rule.get("scope") or {"host_type": [], "host_group": [], "host_ids": [], "environment": []},
        "severity": rule.get("severity", "medium"),
        "remediation": rule.get("remediation") or {"command": "", "type": "manual", "auto_apply": False},
        "compliance_ref": rule.get("compliance_ref", rule_id),
        "active": bool(rule.get("active", True)),
        "updated_at": now,
        "updated_by": user,
    }
    get_collection("compliance_rules").update_one({"rule_id": rule_id}, {"$set": doc, "$setOnInsert": {"created_at": now, "created_by": user}}, upsert=True)
    return doc


def _rule_applies(rule: dict[str, Any], host: dict[str, Any]) -> bool:
    scope = rule.get("scope") or {}
    host_types = scope.get("host_type") or []
    if host_types and host.get("host_type") not in host_types:
        return False
    host_ids = scope.get("host_ids") or []
    if host_ids and host.get("asset_seq") not in host_ids:
        return False
    groups = scope.get("host_group") or []
    if groups and host.get("group_name") not in groups:
        return False
    envs = scope.get("environment") or []
    if envs and host.get("environment") not in envs:
        return False
    return True


def _compare(rule: dict[str, Any], actual: dict[str, Any]) -> str:
    target = str(rule.get("target", ""))
    rule_type = rule.get("type")
    action = rule.get("action")
    if rule_type == "account":
        present = target in actual.get("accounts", [])
    elif rule_type == "package":
        present = target in actual.get("packages", [])
    elif rule_type == "port":
        present = int(target) in [int(port) for port in actual.get("ports", [])]
    elif rule_type == "process":
        present = target in actual.get("processes", [])
    elif rule_type == "service":
        present = actual.get("services", {}).get(target) == "running"
    elif rule_type == "file":
        present = actual.get("files", {}).get(target) == "present"
    elif rule_type == "ip":
        present = target in actual.get("ip_rules", [])
    elif rule_type == "setting" and "=" in target:
        key, expected = target.split("=", 1)
        present = str(actual.get("settings", {}).get(key)) == expected
    else:
        present = False
    if action == "blacklist" and present:
        return f"blacklisted {rule_type} present: {target}"
    if action == "whitelist" and not present:
        return f"required {rule_type} missing/mismatch: {target}"
    return ""


def evaluate_host(asset_seq: str, user: str = "system") -> dict[str, Any]:
    host = host_service.get_host(asset_seq)
    if not host:
        raise KeyError(f"host not found: {asset_seq}")
    actual = get_runner(host).collect_audit("all")
    findings = []
    now = _now()
    for rule in list_rules(active_only=True):
        if not _rule_applies(rule, host):
            continue
        violation = _compare(rule, actual)
        if not violation:
            continue
        finding = {
            "asset_seq": asset_seq,
            "rule_id": rule["rule_id"],
            "category": rule.get("category", "white_box"),
            "type": rule.get("type"),
            "severity": rule.get("severity", "medium"),
            "violation": violation,
            "remediation": rule.get("remediation", {}),
            "compliance_ref": rule.get("compliance_ref", rule["rule_id"]),
            "found_at": now,
            "fixed_at": None,
            "exception": None,
            "created_by": user,
        }
        findings.append(finding)
    col = get_collection("compliance_findings")
    col.delete_many({"asset_seq": asset_seq, "fixed_at": None})
    if findings:
        col.insert_many(findings)
        for finding in findings:
            finding.pop("_id", None)
    score = max(0, 100 - sum({"critical": 25, "high": 15, "medium": 8, "low": 3}.get(item["severity"], 5) for item in findings))
    get_collection("hosts").update_one({"asset_seq": asset_seq}, {"$set": {"compliance_score": score, "last_compliance_at": now}})
    host_dir = init_dir(host)
    target = Path(host_dir) / "security_audit" / f"whitebox_{now.strftime('%Y%m%d_%H%M%S')}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"actual": actual, "findings": findings, "score": score}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return {"asset_seq": asset_seq, "score": score, "findings": findings, "finding_count": len(findings)}


def dashboard() -> dict[str, Any]:
    findings = list(get_collection("compliance_findings").find({"fixed_at": None}, {"_id": 0}))
    by_severity: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for item in findings:
        by_severity[item.get("severity", "medium")] = by_severity.get(item.get("severity", "medium"), 0) + 1
    top_rules = list(get_collection("compliance_findings").aggregate([
        {"$match": {"fixed_at": None}},
        {"$group": {"_id": "$rule_id", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]))
    return {
        "open_findings": len(findings),
        "by_severity": by_severity,
        "rules_total": get_collection("compliance_rules").count_documents({}),
        "top_rules": [{"rule_id": item["_id"], "count": item["count"]} for item in top_rules],
        "recent_findings": list(get_collection("compliance_findings").find({}, {"_id": 0}).sort("found_at", DESCENDING).limit(25)),
    }


def host_audit_overview() -> dict[str, Any]:
    hosts = [_plain(host) for host in get_collection("hosts").find({"status": {"$ne": "retired"}}, {"ssh_key": 0}).sort("asset_seq", 1)]
    findings = list(get_collection("compliance_findings").find({"fixed_at": None}, {"_id": 0}).sort([("asset_seq", 1), ("severity", 1)]))
    by_host: dict[str, list[dict[str, Any]]] = {}
    for finding in findings:
        severity = finding.get("severity", "medium")
        finding["severity_label"] = SEVERITY_LABELS.get(severity, severity)
        by_host.setdefault(finding.get("asset_seq", ""), []).append(finding)

    rows = []
    for host in hosts:
        asset_seq = host.get("asset_seq", "")
        host_findings = by_host.get(asset_seq, [])
        severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for finding in host_findings:
            severity = finding.get("severity", "medium")
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
        highest = "none"
        for severity in ("critical", "high", "medium", "low"):
            if severity_counts.get(severity):
                highest = severity
                break
        rows.append(
            {
                "host": host,
                "asset_seq": asset_seq,
                "hostname": host.get("hostname", ""),
                "ip": host.get("ip", ""),
                "os": host.get("os", ""),
                "host_type": host.get("host_type", ""),
                "compliance_score": host.get("compliance_score", 0),
                "last_compliance_at": host.get("last_compliance_at"),
                "open_count": len(host_findings),
                "severity_counts": severity_counts,
                "highest_severity": highest,
                "highest_severity_label": SEVERITY_LABELS.get(highest, "無"),
                "findings": host_findings,
            }
        )

    rows.sort(key=lambda item: (-item["open_count"], -SEVERITY_RANK.get(item["highest_severity"], 0), item["asset_seq"]))
    return {
        "hosts": rows,
        "affected_hosts": sum(1 for item in rows if item["open_count"]),
        "total_hosts": len(rows),
    }


def list_remediation_plans(asset_seq: Optional[str] = None, limit: int = 30) -> list[dict[str, Any]]:
    query: dict[str, Any] = {}
    if asset_seq:
        query["asset_seq"] = asset_seq
    return list(get_collection("compliance_remediation_plans").find(query, {"_id": 0}).sort("created_at", DESCENDING).limit(limit))


def create_remediation_plan(asset_seq: str, rule_id: Optional[str] = None, user: str = "system") -> dict[str, Any]:
    host = host_service.get_host(asset_seq)
    if not host:
        raise KeyError(f"host not found: {asset_seq}")
    query = _finding_query(asset_seq, rule_id)
    findings = list(get_collection("compliance_findings").find(query, {"_id": 0}).sort("rule_id", 1))
    if not findings:
        raise ValueError("沒有找到未修補項目")

    now = _now()
    mode = "single" if rule_id else "all"
    plan_id = f"REM-{now.strftime('%Y%m%d%H%M%S')}-{asset_seq}-{mode}-{uuid4().hex[:6]}"
    readonly = is_enabled("phase_readonly_mode", default=True)
    status = "blocked_by_phase_readonly" if readonly else "ready_to_apply"
    host_dir = Path(init_dir(host))
    plan_dir = host_dir / "security_audit" / "remediation" / plan_id
    backup_path = plan_dir / "backup_manifest.json"
    rollback_path = plan_dir / "rollback_plan.json"
    command_list = []
    rollback_steps = []
    for finding in findings:
        remediation = finding.get("remediation") or {}
        command = remediation.get("command") or "人工判斷修補方式"
        command_list.append(
            {
                "rule_id": finding.get("rule_id"),
                "type": finding.get("type"),
                "severity": finding.get("severity"),
                "command": command,
                "auto_apply": bool(remediation.get("auto_apply")),
                "source_violation": finding.get("violation"),
            }
        )
        rollback_steps.append(
            {
                "rule_id": finding.get("rule_id"),
                "step": "依修補前備份與異動紀錄還原，正式執行前需補上平台專屬回復命令",
                "backup_required": True,
            }
        )

    backup_manifest = {
        "plan_id": plan_id,
        "created_at": now,
        "created_by": user,
        "asset_seq": asset_seq,
        "hostname": host.get("hostname"),
        "ip": host.get("ip"),
        "mode": mode,
        "rule_id": rule_id,
        "finding_count": len(findings),
        "host_snapshot": host,
        "selected_findings": findings,
        "note": "修補前備份清單。Phase 1 目前先保存主機資料與稽核 finding，正式修補前再擴充平台檔案備份。",
    }
    rollback_plan = {
        "plan_id": plan_id,
        "asset_seq": asset_seq,
        "mode": mode,
        "status": status,
        "readonly_mode": readonly,
        "backup_path": str(backup_path),
        "rollback_steps": rollback_steps,
        "note": "rollback 不會自動執行；正式修補前需先驗證備份存在與平台專屬回復命令。",
    }
    _json_dump(backup_path, backup_manifest)
    _json_dump(rollback_path, rollback_plan)

    plan = {
        "plan_id": plan_id,
        "asset_seq": asset_seq,
        "hostname": host.get("hostname"),
        "ip": host.get("ip"),
        "mode": mode,
        "rule_id": rule_id,
        "status": status,
        "readonly_mode": readonly,
        "requires_backup": True,
        "backup_path": str(backup_path),
        "rollback_path": str(rollback_path),
        "finding_count": len(findings),
        "commands": command_list,
        "created_at": now,
        "created_by": user,
        "applied_at": None,
        "rolled_back_at": None,
    }
    get_collection("compliance_remediation_plans").insert_one(plan)
    plan.pop("_id", None)
    return plan


def rollback_remediation_plan(plan_id: str, user: str = "system") -> dict[str, Any]:
    col = get_collection("compliance_remediation_plans")
    plan = col.find_one({"plan_id": plan_id}, {"_id": 0})
    if not plan:
        raise KeyError(f"plan not found: {plan_id}")
    now = _now()
    readonly = is_enabled("phase_readonly_mode", default=True)
    status = "rollback_blocked_by_phase_readonly" if readonly else "rollback_ready"
    event = {
        "requested_at": now,
        "requested_by": user,
        "status": status,
        "readonly_mode": readonly,
        "rollback_path": plan.get("rollback_path"),
    }
    col.update_one({"plan_id": plan_id}, {"$set": {"last_rollback_request": event, "updated_at": now}})
    return {**plan, "rollback_request": event}


def export_findings_csv() -> str:
    output = io.StringIO()
    fields = ["asset_seq", "rule_id", "category", "type", "severity", "violation", "compliance_ref", "found_at", "fixed_at"]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for item in get_collection("compliance_findings").find({}, {"_id": 0}).sort("found_at", DESCENDING):
        writer.writerow(item)
    return output.getvalue()


def export_twgcb_excel_html() -> str:
    output = io.StringIO()
    output.write("<html><head><meta charset='utf-8'></head><body>")
    output.write("<h1>TWGCB 合規報表</h1>")
    output.write("<h2>規則庫</h2><table border='1'><tr><th>規則</th><th>類型</th><th>嚴重度</th><th>目標</th><th>啟用</th></tr>")
    for rule in list_rules():
        output.write(
            f"<tr><td>{rule.get('rule_id','')}</td><td>{rule.get('type','')}</td><td>{rule.get('severity','')}</td><td>{rule.get('target','')}</td><td>{rule.get('active')}</td></tr>"
        )
    output.write("</table><h2>未結異常</h2><table border='1'><tr><th>主機</th><th>規則</th><th>嚴重度</th><th>違規內容</th></tr>")
    for item in get_collection("compliance_findings").find({"fixed_at": None}, {"_id": 0}).sort("severity", DESCENDING):
        output.write(
            f"<tr><td>{item.get('asset_seq','')}</td><td>{item.get('rule_id','')}</td><td>{item.get('severity','')}</td><td>{item.get('violation','')}</td></tr>"
        )
    output.write("</table></body></html>")
    return output.getvalue()
