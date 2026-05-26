from webapp.app import create_app
from webapp import config
from webapp.routes import api_v1
from webapp.routes import api_reports
from webapp.services import dependency_service


def test_health_route():
    app = create_app()
    client = app.test_client()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json()["status"] == "ok"


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
