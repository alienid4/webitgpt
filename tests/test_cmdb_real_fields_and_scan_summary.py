from webapp.services import cmdb_service, csv_service
from webapp.services.cmdb_service import DISCOVERY_TCP_PORTS, _scan_report_summary


def test_real_cmdb_chinese_headers_are_mapped_to_host_fields():
    csv_text = "\n".join(
        [
            "總點單位-級別,總點單位-部門,資產序號,資產狀態,群組名稱,資料類別,APID,資產名稱,整體基礎架構,資料保留年限,資料備份方式,擁有者,保管者,主機名稱,IP,備份頻率,使用單位,附加說明,個資群組名稱,個人資料,完整性(I),機密性(C),可用性(A),申請單編號",
            "資訊管理處,金融交易資訊部,DA-0005872,使用中,D2-機密資料,系統資料,N-011,興櫃管理系統,地端資產,依業務存續期間,資料備份軟體,金融交易資訊部,李宗翰,SECSVR019-025,10.93.19.25,每日,金融交易資訊部,,無,無,3,3,3,無",
        ]
    )

    report = csv_service.validate_csv(csv_text)
    doc = csv_service._coerce(next(csv_service.csv.DictReader(csv_service.io.StringIO(csv_text))))

    assert report["status"] == "ok"
    assert doc["asset_seq"] == "DA-0005872"
    assert doc["status"] == "active"
    assert doc["hostname"] == "SECSVR019-025"
    assert doc["ip"] == "10.93.19.25"
    assert doc["integrity"] == 3
    assert doc["confidentiality"] == 3
    assert doc["availability"] == 3
    assert doc["extensions"]["backup_frequency"] == "每日"
    assert doc["extensions"]["data_retention_period"] == "依業務存續期間"
    assert doc["extensions"]["backup_method"] == "資料備份軟體"


def test_scan_summary_makes_hidden_filtering_explicit():
    rows = [
        {"type": "already_in_cmdb", "ip": "10.92.198.14"},
        {"type": "scan_not_in_cmdb", "ip": "10.92.198.11"},
        {"type": "scan_not_in_cmdb", "ip": "10.92.198.13"},
    ]

    summary = _scan_report_summary(rows, discovered_count=9, cmdb_count=1)

    assert summary["discovered"] == 9
    assert summary["already_in_cmdb"] == 1
    assert summary["scan_not_in_cmdb"] == 2
    assert summary["shown_rows"] == 3
    assert summary["hidden_rows"] == 0
    assert "50000" in DISCOVERY_TCP_PORTS
    assert "8002" in DISCOVERY_TCP_PORTS


def test_combined_scan_falls_back_to_default_nmap_when_targeted_scans_find_nothing(monkeypatch):
    calls = []

    monkeypatch.setattr(cmdb_service.shutil, "which", lambda name: "/usr/bin/nmap")
    monkeypatch.setattr(cmdb_service, "_host_ips_in_network", lambda cidr: {})

    class FakeCollection:
        def insert_one(self, report):
            return None

    monkeypatch.setattr(cmdb_service, "get_collection", lambda name: FakeCollection())

    def fake_run(command, timeout=180):
        calls.append(command)
        if command[:2] == ["nmap", "-R"]:
            return ([{"ip": "10.92.198.11", "hostname": "", "os": "", "host_type": "end_device", "open_ports": []}], "")
        return ([], "")

    monkeypatch.setattr(cmdb_service, "_run_nmap_xml", fake_run)

    report = cmdb_service.run_asset_discovery_scan("10.92.198.0/24", scan_mode="combined")

    assert report["discovered_count"] == 1
    assert report["summary"]["scan_not_in_cmdb"] == 1
    assert any(command[:2] == ["nmap", "-R"] for command in calls)
