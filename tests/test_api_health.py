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


def test_openapi_schema_documents_models_and_pagination():
    res = client.get("/openapi.json")
    assert res.status_code == 200
    schema = res.json()
    schemas = schema.get("components", {}).get("schemas", {})
    assert "HealthResponse" in schemas
    assert "FlowsPointsResponse" in schemas
    assert "PldDailyResponse" in schemas
    assert "PldHourlyResponse" in schemas
    assert "PowerPldCmoResponse" in schemas

    # Verify offset parameter is exposed in query endpoints
    paths = schema.get("paths", {})
    for p in ("/v1/flows/points", "/v1/pld/daily", "/v1/pld/hourly", "/v1/supply/monthly"):
        params = paths[p]["get"]["parameters"]
        param_names = [param["name"] for param in params]
        assert "offset" in param_names
        assert "limit" in param_names


def test_records_pagination_offset():
    import pandas as pd

    from api.main import _records

    df = pd.DataFrame({"id": list(range(10)), "date": pd.date_range("2026-01-01", periods=10)})
    page1 = _records(df, limit=3, offset=0)
    assert len(page1) == 3
    assert [r["id"] for r in page1] == [0, 1, 2]

    page2 = _records(df, limit=3, offset=3)
    assert len(page2) == 3
    assert [r["id"] for r in page2] == [3, 4, 5]

    page3 = _records(df, limit=5, offset=8)
    assert len(page3) == 2
    assert [r["id"] for r in page3] == [8, 9]

