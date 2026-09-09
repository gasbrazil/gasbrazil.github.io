from __future__ import annotations

import gzip
import json

import pandas as pd

import data_kit as dk


def test_atomic_parquet_publish(tmp_path, monkeypatch):
    monkeypatch.setattr(dk, "LAKE_ROOT", tmp_path)
    dest = tmp_path / "power" / "pld_daily.parquet"
    monkeypatch.setitem(dk.LAKE_PATHS, "pld_daily", dest)
    monkeypatch.delenv("GASBRAZIL_LAKE_BUCKET", raising=False)
    monkeypatch.delenv("R2_ENDPOINT_URL", raising=False)

    df = pd.DataFrame({"date": ["2026-09-01"], "submarket": ["SE"], "pld": [1.5]})
    out = dk.publish("pld_daily", df)
    assert out.exists()
    assert not out.with_name(out.name + ".tmp").exists()
    got = pd.read_parquet(out)
    assert list(got.columns) == ["date", "submarket", "pld"]


def test_write_json_gzip_reproducible(tmp_path):
    payload = {"a": 1, "b": [2, 3]}
    p1 = dk.write_json_gzip(payload, tmp_path / "a.json.gz")
    p2 = dk.write_json_gzip(payload, tmp_path / "b.json.gz")
    assert p1.read_bytes() == p2.read_bytes()
    raw = gzip.decompress(p1.read_bytes())
    assert json.loads(raw) == payload


def test_payload_url_encodes_bust(monkeypatch):
    monkeypatch.setenv("GASBRAZIL_DATA_BASE_URL", "https://example.test")
    monkeypatch.setenv("GASBRAZIL_DATA_CACHE_BUST", "a b")
    url = dk.payload_url("pld")
    assert url.startswith("https://example.test/pld/payload.json.gz?v=")
    assert " " not in url.split("?", 1)[1]
