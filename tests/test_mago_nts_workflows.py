"""Regression: Mago / NTS refresh cadence and hub rebuild gating."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_mago_workflow_hourly_without_scheduled_home_rebuild():
    text = (ROOT / ".github/workflows/mago.yml").read_text(encoding="utf-8")
    assert 'cron: "10 * * * *"' in text
    assert "group: mago-refresh" in text
    assert "if: github.event_name != 'schedule'" in text
    assert "Refresh home hub" in text


def test_nts_workflow_hourly_without_scheduled_home_rebuild():
    text = (ROOT / ".github/workflows/nts.yml").read_text(encoding="utf-8")
    assert 'cron: "40 * * * *"' in text
    assert "group: nts-refresh" in text
    assert "if: github.event_name != 'schedule'" in text
    assert "Refresh home hub" in text
