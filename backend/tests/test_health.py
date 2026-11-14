from fastapi.testclient import TestClient

from app.main import app


def test_health_reports_that_the_api_is_running():
    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
