from webapp.services import csv_service


def test_csv_downloads_include_utf8_bom():
    assert csv_service.csv_template().startswith("\ufeff")
    assert csv_service.export_hosts_csv([{"hostname": "主機A", "ip": "192.168.1.10"}]).startswith("\ufeff")
    report = {"errors": [{"line": 2, "field": "ip", "error": "required"}], "warnings": []}
    assert csv_service.validation_errors_csv(report).startswith("\ufeff")


def test_xlsx_export_can_be_read_back():
    payload = csv_service.export_hosts_xlsx([{"hostname": "主機A", "ip": "192.168.1.10", "asset_seq": "DA-1"}])
    rows = csv_service.xlsx_rows_from_bytes(payload)

    assert rows[0]["hostname"] == "主機A"
    assert rows[0]["ip"] == "192.168.1.10"
    assert rows[0]["asset_seq"] == "DA-1"


def test_import_rows_summarizes_human_readable_failures(monkeypatch):
    def fail_upsert(doc, user="system"):
        raise ValueError("ip must be a valid IPv4/IPv6 address")

    monkeypatch.setattr(csv_service.host_service, "get_host", lambda key: None)
    monkeypatch.setattr(csv_service.host_service, "upsert_host", fail_upsert)

    result = csv_service.import_rows([{"hostname": "bad", "ip": "not-ip"}], user="tester")

    assert result["failed"] == 1
    assert result["summary"]["failed"] == 1
    assert result["summary"]["categories"][0]["category"] == "IP 格式錯誤"
    assert result["errors"][0]["human_message"]
    assert result["elapsed_seconds"] >= 0


def test_import_rows_rejects_too_many_rows_before_writes(monkeypatch):
    called = {"value": False}

    def fail_if_called(doc, user="system"):
        called["value"] = True

    monkeypatch.setattr(csv_service.host_service, "upsert_host", fail_if_called)
    rows = [{"hostname": f"h{i}", "ip": f"10.1.1.{i % 250}"} for i in range(csv_service.MAX_UI_IMPORT_ROWS + 1)]

    result = csv_service.import_rows(rows, user="tester")

    assert result["failed"] == 1
    assert result["summary"]["categories"][0]["category"] == "匯入筆數過大"
    assert called["value"] is False
