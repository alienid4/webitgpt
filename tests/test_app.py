from webapp.app import create_app
from webapp import config


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
