from webapp.app import create_app
from webapp import config
from webapp.routes import api_reports


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
