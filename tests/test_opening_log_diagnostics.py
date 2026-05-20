from webapp.services.legacy_parity_service import (
    _build_diagnostic_check,
    _normalize_diagnostic_row,
)


def test_opening_log_warn_is_compact():
    raw = "May 16 09:21:01 secansible setroubleshootd[123]: failed to process SELinux denial logs"
    check = _build_diagnostic_check("log", "系統日誌", 0, raw, "")

    assert check["status"] == "warn"
    assert check["detail"].startswith("警示:有日誌訊息")
    assert "setroubleshootd" in check["detail"]
    assert "建議處置" not in check["detail"]


def test_opening_log_ok_is_one_line():
    check = _build_diagnostic_check("log", "系統日誌", 0, "", "")

    assert check["status"] == "ok"
    assert check["detail"] == "警示:無"


def test_old_opening_log_row_is_normalized_for_display():
    row = {
        "checks": [
            {
                "key": "log",
                "label": "系統日誌",
                "status": "warn",
                "detail": "May 16 09:21:01 secansible kernel: warning sample",
            }
        ]
    }
    normalized = _normalize_diagnostic_row(row)

    assert normalized["checks"][0]["detail"].startswith("警示:有日誌訊息")
    assert "warning sample" in normalized["checks"][0]["detail"]
    assert normalized["summary"]["warn"] == 1


def test_old_opening_log_without_evidence_is_normalized_to_ok():
    row = {
        "checks": [
            {
                "key": "log",
                "label": "系統日誌",
                "status": "warn",
                "detail": "無輸出",
            }
        ]
    }
    normalized = _normalize_diagnostic_row(row)

    assert normalized["checks"][0]["status"] == "ok"
    assert normalized["checks"][0]["detail"] == "警示:無"
    assert normalized["summary"]["warn"] == 0


def test_passwd_account_log_warning_lists_accounts_compactly():
    raw = "\n".join(
        [
            "4月 17 20:23:21 sec9c2 passwd[3861]: can't view or modify password information for systemd-network",
            "4月 17 20:23:21 sec9c2 passwd[3906]: can't view or modify password information for systemd-timesync",
            "4月 17 20:23:21 sec9c2 passwd[3951]: can't view or modify password information for messagebus",
            "4月 17 20:23:21 sec9c2 passwd[3996]: can't view or modify password information for alien",
            "4月 17 20:23:21 sec9c2 passwd[4041]: can't view or modify password information for sshd",
        ]
    )
    check = _build_diagnostic_check("log", "系統日誌", 0, raw, "")

    assert check["status"] == "warn"
    assert check["detail"].startswith("警示:passwd 訊息")
    assert "systemd-network, systemd-timesync, messagebus, sshd" in check["detail"]
    assert "需確認:alien" in check["detail"]
    assert "建議處置" not in check["detail"]


def test_opening_log_whitelist_exception_downgrades_known_noise(monkeypatch):
    def fake_assess(lines, scope="opening_log"):
        return {
            "matched_lines": lines,
            "unmatched_lines": [],
            "matched_rule_ids": ["logex-test"],
            "matched_rule_names": ["已確認 setroubleshootd 雜訊"],
            "all_matched": True,
            "has_match": True,
        }

    monkeypatch.setattr("webapp.services.legacy_parity_service.assess_lines", fake_assess)
    raw = "May 16 09:21:01 secansible setroubleshootd[123]: failed to process SELinux denial logs"

    check = _build_diagnostic_check("log", "系統日誌", 0, raw, "")

    assert check["status"] == "ok"
    assert check["detail"].startswith("警示:已列例外")
    assert "已確認 setroubleshootd 雜訊" in check["detail"]
    assert "可能需要 IT 人員確認" not in check["detail"]
