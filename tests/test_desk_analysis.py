"""Regression tests for Desk Analysis tab:
1. drawAnalysisChart must use days.length, not undefined dates.length.
2. Template must include .analysis-resizer splitter element with ARIA separator role.
3. JavaScript must include initAnalysisResizer with localStorage key.
4. CSS must constrain .analysis-catalog height for vertical scrolling.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_desk_analysis_no_dates_reference_error():
    src = (ROOT / "desk" / "dashboard.py").read_text(encoding="utf-8")
    assert "drawAnalysisChart(days, plotSeries, dualMeta)" in src

    # Verify xAt in drawAnalysisChart does not use dates.length
    idx = src.find("function drawAnalysisChart(")
    assert idx != -1
    end_idx = src.find("function compareBlock()", idx)
    func_body = src[idx:end_idx]

    assert "dates.length" not in func_body, (
        "drawAnalysisChart must not reference dates.length (dates is undefined; use days.length)"
    )
    assert "days.length" in func_body


def test_desk_analysis_resizer_markup_and_css():
    src = (ROOT / "desk" / "dashboard.py").read_text(encoding="utf-8")
    assert 'class="analysis-resizer"' in src
    assert 'role="separator"' in src
    assert 'aria-orientation="vertical"' in src
    assert 'initAnalysisResizer()' in src
    assert "gasbrazil-desk-sidebar-w" in src
    assert "--desk-sidebar-w" in src

    # Verify CSS constraints for .analysis-catalog scrolling
    assert ".analysis-catalog {" in src
    assert "overflow-y: auto;" in src


def test_desk_built_shell_contains_fixes():
    html = (ROOT / "desk" / "index.html").read_text(encoding="utf-8")
    assert 'id="analysis-resizer"' in html
    assert "initAnalysisResizer" in html
    assert "gasbrazil-desk-sidebar-w" in html
    assert "dates.length - 1" not in html[html.find("drawAnalysisChart") : html.find("compareBlock")]


def test_desk_analysis_stage_spans_full_width():
    src = (ROOT / "desk" / "dashboard.py").read_text(encoding="utf-8")
    assert ".analysis-stage {" in src
    stage_idx = src.find(".analysis-stage {")
    stage_block = src[stage_idx : src.find("}", stage_idx)]
    assert "flex: 1 1 0;" in stage_block
    assert "min-width: 0;" in stage_block

    html = (ROOT / "desk" / "index.html").read_text(encoding="utf-8")
    assert "observeAnalysisResize" in html
