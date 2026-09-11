from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_health_reports_ok_false_without_lake():
    res = client.get("/health")
    body = res.json()
    assert "datasets" in body
    assert "pld_daily" in body["datasets"]
    assert "pld_hourly" in body["datasets"]
    # No lake in a clean checkout; critical datasets are absent.
    if not body["ok"]:
        assert res.status_code == 503
    else:
        assert res.status_code == 200
