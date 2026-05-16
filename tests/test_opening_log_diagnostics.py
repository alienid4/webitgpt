from webapp.services.legacy_parity_service import (
    _build_diagnostic_check,
    _normalize_diagnostic_row,
)


def test_opening_log_warn_explains_problem_evidence_and_fix():
    raw = "May 16 09:21:01 secansible setroubleshootd[123]: failed to process SELinux denial logs"
    check = _build_diagnostic_check("log", "系統日誌", 0, raw, "")

    assert check["status"] == "warn"
    assert "問題點：" in check["detail"]
    assert "證據：" in check["detail"]
    assert "解決方式：" in check["detail"]
    assert "setroubleshootd" in check["detail"]
    assert "journalctl -p warning -n 30 --no-pager" in check["detail"]
    assert "systemctl --failed --no-pager" in check["detail"]


def test_opening_log_ok_still_has_evidence():
    check = _build_diagnostic_check("log", "系統日誌", 0, "", "")

    assert check["status"] == "ok"
    assert "問題點：未發現最近系統 warning/error 日誌。" in check["detail"]
    assert "證據：" in check["detail"]
    assert "解決方式：" in check["detail"]


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

    assert normalized["checks"][0]["detail"].startswith("問題點：")
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
    assert "未發現最近系統 warning/error 日誌" in normalized["checks"][0]["detail"]
    assert normalized["summary"]["warn"] == 0
