"""Regression: combined Pipeline Monitor refresh workflow."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_monitor_workflow_hourly_combined_mago_nts():
    text = (ROOT / ".github/workflows/monitor.yml").read_text(encoding="utf-8")
    assert 'cron: "15 * * * *"' in text
    assert "group: monitor-refresh" in text
    assert "mago_pipeline.py fetch" in text
    assert "nts_pipeline.py fetch" in text
    assert "monitor/dashboard.py" in text
    assert "if: github.event_name != 'schedule'" in text
    assert "Refresh home hub" in text
    assert (ROOT / ".github/workflows/mago.yml").exists() is False
    assert (ROOT / ".github/workflows/nts.yml").exists() is False
