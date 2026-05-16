from webapp.services.legacy_parity_service import _build_diagnostic_check


def test_connectivity_detail_is_human_readable():
    raw = "secansible\n 10:23:01 up 7:02,  0 users,  load average: 0.09, 0.10, 0.04"

    check = _build_diagnostic_check("connectivity", "連線狀態", 0, raw, "")

    assert check["status"] == "ok"
    assert "連線狀態：主機可連線。" in check["detail"]
    assert "開機狀態：已開機 7 小時 2 分鐘。" in check["detail"]
    assert "使用者：目前無登入使用者。" in check["detail"]
    assert "load average" not in check["detail"]
    assert check["raw_detail"] == raw
