from types import SimpleNamespace

from webapp.app import create_app
from webapp import config
from webapp.routes import api_v1
from webapp.routes import api_reports
from webapp.routes import api_hosts
from webapp.services import dependency_service


def test_health_route():
    app = create_app()
    client = app.test_client()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"


def test_hosts_page_lazy_loads_asset_rows_until_requested(monkeypatch):
    calls = {"list_hosts": 0}

    def fake_list_hosts(**_kwargs):
        calls["list_hosts"] += 1
        return {"items": [], "total": 0, "page": 1, "page_size": 100}

    def fake_summary(*_args, **_kwargs):
        return {
            "auto_ingested": 0,
            "complete_assets": 0,
            "review_assets": 0,
            "missing_required_assets": 0,
            "environments": 0,
            "types": 0,
            "environment_breakdown": [],
            "type_breakdown": [],
        }

    monkeypatch.setattr(api_hosts.host_service, "list_hosts", fake_list_hosts)
    monkeypatch.setattr(api_hosts.host_service, "asset_scope_summary", fake_summary)
    monkeypatch.setattr(api_hosts.host_service, "status_counts", lambda: {})
    monkeypatch.setattr(api_hosts, "list_views", lambda _username: [])

    app = create_app()
    client = app.test_client()

    response = client.get("/hosts")

    assert response.status_code == 200
    assert calls["list_hosts"] == 0

    response = client.get("/hosts?show_assets=1")

    assert response.status_code == 200
    assert calls["list_hosts"] == 1


def test_version_segments_are_capped_at_99():
    parts = [int(part) for part in config.VERSION.split(".")]

    assert parts[0] == 1
    assert all(0 <= part <= 99 for part in parts[1:])


def test_api_key_post_install_verify_requires_token():
    app = create_app()
    client = app.test_client()

    response = client.get("/api/v1/post-install/verify")

    assert response.status_code == 401
    assert response.get_json()["error"] == "missing bearer token"


def test_api_key_post_install_verify_returns_checks(monkeypatch):
    monkeypatch.setattr("webapp.decorators.verify_token", lambda token, scope: token == "ok-token" and scope == "system:read")
    monkeypatch.setattr(api_v1.mongo_service, "ping", lambda: {"mongo": "ok", "db": "webitgpt"})
    monkeypatch.setattr(api_v1, "operations_data_quality", lambda: {"status": "ok", "score": 99, "warnings": []})
    app = create_app()
    client = app.test_client()

    response = client.get(
        f"/api/v1/post-install/verify?expected_version={config.VERSION}",
        headers={"Authorization": "Bearer ok-token"},
    )
    data = response.get_json()

    assert response.status_code == 200
    assert data["ok"] is True
    assert data["version"] == config.VERSION
    assert data["patch_id"] == config.PATCH_ID
    assert data["verification_source"] == "api_key"
    assert data["verification_label"] == "API Key 驗證"
    assert data["required_scope"] == "system:read"
    assert {item["name"] for item in data["checks"]} >= {"api_key", "version", "mongo", "data_quality_api"}


def test_core_impact_notifications_csv(monkeypatch):
    def fake_topology(**_kwargs):
        return {
            "meta": {
                "impact_panel": {
                    "notification_contacts": [
                        {
                            "core": "巡檢系統",
                            "system_id": "SYS-WEBITGPT",
                            "system_name": "webitgpt",
                            "owner": "ops",
                            "host_count": 2,
                            "status": "可通知",
                            "reason": "核心系統維護 / 故障影響通知",
                        }
                    ]
                }
            }
        }

    monkeypatch.setattr(api_reports, "topology", fake_topology)
    app = create_app()
    client = app.test_client()
    response = client.get("/api/dependencies/notifications.csv?view=core_impact")

    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert response.content_type.startswith("text/csv")
    assert "core,system_id,system_name,owner,host_count,status,reason" in body
    assert "SYS-WEBITGPT" in body


def test_core_impact_system_center_limits_to_focused_system(monkeypatch):
    systems = [
        {
            "system_id": "SYS-DEBIAN",
            "display_name": "受監控主機-Debian",
            "tier": "C",
            "category": "AP",
            "owner": "ops",
            "host_refs": ["sec9c2"],
            "metadata": {"core_name": "巡檢系統"},
        },
        {
            "system_id": "SYS-ROCKY",
            "display_name": "受監控主機-Rocky",
            "tier": "C",
            "category": "AP",
            "owner": "ops",
            "host_refs": ["secclient1"],
            "metadata": {"core_name": "巡檢系統"},
        },
    ]
    hosts = [
        {"hostname": "sec9c2", "ip": "192.168.1.223"},
        {"hostname": "secclient1", "ip": "192.168.1.222"},
    ]

    monkeypatch.setattr(dependency_service, "list_systems", lambda *_args, **_kwargs: systems)
    monkeypatch.setattr(dependency_service, "_hosts", lambda: hosts)
    monkeypatch.setattr(dependency_service, "list_relations", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(dependency_service, "latest_collect_run", lambda: None)

    data = dependency_service.topology(view="core_impact", center="SYS-DEBIAN")
    node_ids = {node["id"] for node in data["nodes"]}

    assert data["meta"]["scope"] == "system_focus"
    assert data["meta"]["impact_panel"]["system_count"] == 1
    assert data["meta"]["impact_panel"]["host_count"] == 1
    assert "SYS-DEBIAN" in node_ids
    assert "host:sec9c2" in node_ids
    assert "SYS-ROCKY" not in node_ids
    assert "host:secclient1" not in node_ids
    assert all("x" in node and "y" in node for node in data["nodes"])
    assert all(
        {"x1", "y1", "x2", "y2"}.issubset(edge.keys())
        for edge in data["edges"]
        if edge["source"] in node_ids and edge["target"] in node_ids
    )


def test_core_impact_handles_custom_core_without_svg_position_gaps(monkeypatch):
    systems = [
        {
            "system_id": "SYS-ONLY",
            "display_name": "證券阿發",
            "tier": "C",
            "category": "AP",
            "owner": "ops",
            "host_refs": [],
            "metadata": {"core_name": "自訂核心"},
        }
    ]

    monkeypatch.setattr(dependency_service, "list_systems", lambda *_args, **_kwargs: systems)
    monkeypatch.setattr(dependency_service, "_hosts", lambda: [])
    monkeypatch.setattr(dependency_service, "list_relations", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(dependency_service, "latest_collect_run", lambda: None)

    data = dependency_service.topology(view="core_impact", center="SYS-ONLY")

    assert all("x" in node and "y" in node for node in data["nodes"])
    assert all(
        {"x1", "y1", "x2", "y2"}.issubset(edge.keys())
        for edge in data["edges"]
        if edge["source"] in {node["id"] for node in data["nodes"]}
        and edge["target"] in {node["id"] for node in data["nodes"]}
    )


def test_core_impact_unassigned_system_does_not_fallback_to_default_core(monkeypatch):
    systems = [
        {
            "system_id": "SYS-WATERMARK",
            "display_name": "浮水印系統",
            "tier": "C",
            "category": "AP",
            "owner": "ops",
            "host_refs": ["host-a"],
            "metadata": {},
        }
    ]
    hosts = [{"asset_seq": "HW-00000001", "asset_name": "浮水印系統", "hostname": "host-a", "ip": "10.0.0.1"}]

    monkeypatch.setattr(dependency_service, "list_systems", lambda *_args, **_kwargs: systems)
    monkeypatch.setattr(dependency_service, "_hosts", lambda: hosts)
    monkeypatch.setattr(dependency_service, "list_relations", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(dependency_service, "latest_collect_run", lambda: None)

    data = dependency_service.topology(view="core_impact", center="SYS-WATERMARK")
    active_core_labels = {
        node["label"]
        for node in data["nodes"]
        if str(node.get("id") or "").startswith("core:") and node.get("focus_state") == "active"
    }

    assert "未歸屬核心" in active_core_labels
    assert "好麥證券" not in active_core_labels
    assert data["meta"]["impact_panel"]["core_label"] == "未歸屬核心"


def test_core_assignment_rows_expose_manual_topology_governance(monkeypatch):
    systems = [
        {
            "system_id": "SYS-APP",
            "display_name": "應用系統",
            "owner": "ops",
            "host_refs": ["host-a", "host-b"],
            "category": "AP",
            "metadata": {"core_name": "管理核心"},
        },
        {
            "system_id": "SYS-FLOAT",
            "display_name": "浮水印系統",
            "owner": "",
            "host_refs": [],
            "category": "AP",
            "metadata": {},
        },
    ]

    monkeypatch.setattr(dependency_service, "list_systems", lambda *_args, **_kwargs: systems)

    data = dependency_service.core_assignment_rows()
    rows = {row["system_id"]: row for row in data["rows"]}

    assert "管理核心" in data["core_options"]
    assert rows["SYS-APP"]["core_name"] == "管理核心"
    assert rows["SYS-APP"]["explicit"] is True
    assert rows["SYS-FLOAT"]["core_name"] == "未歸屬核心"
    assert data["summary"]["explicit"] == 1
    assert data["summary"]["unassigned"] == 1


def test_update_core_assignments_sets_metadata_core_name(monkeypatch):
    updates = []

    class FakeCollection:
        def update_one(self, query, update, **_kwargs):
            updates.append((query, update))

            class Result:
                matched_count = 1
                modified_count = 1

            return Result()

    monkeypatch.setattr(dependency_service, "get_collection", lambda _name: FakeCollection())

    result = dependency_service.update_core_assignments({"SYS-APP": "管理核心"}, "tester")

    assert result["updated"] == 1
    assert updates[0][0] == {"system_id": "SYS-APP"}
    assert updates[0][1]["$set"]["metadata.core_name"] == "管理核心"


def test_host_business_system_name_excludes_discovery_scan_drafts():
    assert dependency_service._host_business_system_name(
        {
            "asset_seq": "DISC-20260531-192-168-1-230",
            "asset_name": "掃描發現 192.168.1.230",
            "hostname": "scan-192-168-1-230",
        }
    ) == ""
    assert dependency_service._host_business_system_name(
        {"asset_seq": "HW-1", "asset_name": "證券阿發", "hostname": "SECSVR002-011t"}
    ) == "證券阿發"


def test_dependency_hosts_reads_full_collection_without_page_cap(monkeypatch):
    docs = [{"hostname": f"host-{index:03d}", "asset_seq": f"HW-{index:08d}"} for index in range(150)]

    class FakeCursor(list):
        def sort(self, *_args, **_kwargs):
            return self

    class FakeCollection:
        def find(self, *_args, **_kwargs):
            return FakeCursor(docs)

    monkeypatch.setattr(dependency_service, "get_collection", lambda _name: FakeCollection())

    assert len(dependency_service._hosts()) == 150


def test_core_impact_backfills_hosts_from_asset_master_when_host_refs_are_stale(monkeypatch):
    system_name = "證券阿發"
    system_id = dependency_service._system_id(system_name)
    systems = [
        {
            "system_id": system_id,
            "display_name": system_name,
            "tier": "C",
            "category": "AP",
            "owner": "ops",
            "host_refs": ["SECSVR002-011t"],
            "metadata": {"core_name": "好麥證券"},
        }
    ]
    hosts = [
        {
            "asset_seq": "HW-00012045",
            "asset_name": system_name,
            "hostname": "SECSVR002-011t",
            "ip": "10.0.0.11",
        },
        {
            "asset_seq": "HW-00012046",
            "asset_name": system_name,
            "hostname": "SECSVR002-012t",
            "ip": "10.0.0.12",
        },
        {
            "asset_seq": "HW-00012047",
            "asset_name": system_name,
            "hostname": "SECSVR002-040T",
            "ip": "10.0.0.40",
        },
    ]

    monkeypatch.setattr(dependency_service, "list_systems", lambda *_args, **_kwargs: systems)
    monkeypatch.setattr(dependency_service, "_hosts", lambda: hosts)
    monkeypatch.setattr(dependency_service, "list_relations", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(dependency_service, "latest_collect_run", lambda: None)

    data = dependency_service.topology(view="core_impact", center=system_id)
    host_nodes = [node for node in data["nodes"] if str(node.get("id") or "").startswith("host:")]

    assert data["meta"]["impact_panel"]["host_count"] == 3
    assert {node["id"] for node in host_nodes} == {
        "host:HW-00012045",
        "host:HW-00012046",
        "host:HW-00012047",
    }


def test_core_impact_backfills_hosts_when_system_name_field_differs(monkeypatch):
    system_id = dependency_service._system_id("證券阿發")
    systems = [
        {
            "system_id": system_id,
            "display_name": "證券阿發",
            "tier": "C",
            "category": "AP",
            "owner": "ops",
            "host_refs": ["SECSVR002-011t"],
            "metadata": {"core_name": "好麥證券", "asset_name": "證券阿發", "system_name": "好麥證券"},
        }
    ]
    hosts = [
        {
            "asset_seq": "HW-00012045",
            "system_name": "好麥證券",
            "asset_name": "證券阿發",
            "hostname": "SECSVR002-011t",
            "ip": "10.0.0.11",
        },
        {
            "asset_seq": "HW-00012046",
            "system_name": "好麥證券",
            "asset_name": "證卷阿發",
            "hostname": "SECSVR002-012t",
            "ip": "10.0.0.12",
        },
        {
            "asset_seq": "HW-00012047",
            "system_name": "其他欄位",
            "device_type": "證券阿發",
            "hostname": "SECSVR002-040T",
            "ip": "10.0.0.40",
        },
    ]

    monkeypatch.setattr(dependency_service, "list_systems", lambda *_args, **_kwargs: systems)
    monkeypatch.setattr(dependency_service, "_hosts", lambda: hosts)
    monkeypatch.setattr(dependency_service, "list_relations", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(dependency_service, "latest_collect_run", lambda: None)

    data = dependency_service.topology(view="core_impact", center=system_id)
    host_nodes = [node for node in data["nodes"] if str(node.get("id") or "").startswith("host:")]

    assert data["meta"]["impact_panel"]["host_count"] == 3
    assert {node["id"] for node in host_nodes} == {
        "host:HW-00012045",
        "host:HW-00012046",
        "host:HW-00012047",
    }


def test_ss_tunp_local_probe_targets_are_env_configured(monkeypatch):
    calls = []

    def fake_run(cmd, **_kwargs):
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setenv("WEBITGPT_LOCAL_PROBE_HOSTS", "local-probe")
    monkeypatch.setattr(dependency_service.subprocess, "run", fake_run)

    dependency_service._run_ss_tunp({"hostname": "local-probe", "ip": "10.0.0.10"})

    assert calls[-1] == ["bash", "-lc", "ss -tunp || netstat -tunp"]

    dependency_service._run_ss_tunp({"hostname": "remote-probe", "ip": "10.0.0.11"})

    assert calls[-1][0] == "ssh"
    assert "remote-probe" not in {"127.0.0.1", "localhost"}
