"""
Versioned transform assumptions (ADR-002 Track A).

Pipelines should read parameters from here instead of burying magic numbers
only inside dashboard.py / ons_pipeline.py. Bump ``version`` when a formula
or constant changes so lake rebuilds and docs stay auditable.
"""
from __future__ import annotations

from typing import Any

# ONS estimated gas burn from verified MWmed (not published per plant by ONS).
ONS_GAS_HEAT: dict[str, Any] = {
    "version": 1,
    "natgas_kcal_per_m3": 9400.0,  # Brazil industry-standard PCS
    "heat_rate_combined_cycle_kcal_per_kwh": 1800.0,  # ~46% CCGT
    "heat_rate_simple_cycle_kcal_per_kwh": 2500.0,  # ~34% OCGT
    "notes": (
        "Combined vs simple cycle is inferred from multi-phase CEG dispatch "
        "structure, not a published cycle-type field."
    ),
    "owners": ("ons/ons_pipeline.py", "ons/dashboard.py"),
}

# POC / Desk / Contracts: R$/m³ = R$/MMBtu ÷ m³ per MMBtu.
# 26.8081 m³/MMBtu is 252,000 kcal/MMBtu ÷ 9,400 kcal/m³ (Brazil PCR).
POC_ENERGY: dict[str, Any] = {
    "version": 2,
    "m3_per_mmbtu": 26.8081,
    "notes": "R$/m³ = R$/MMBtu / 26.8081 (m³ per MMBtu).",
    "owners": ("poc/dashboard.py", "desk/build_payload.py", "contratos/dashboard.py"),
}

# CCEE PLD submarkets ↔ ONS subsystem codes used for cross-product joins.
PLD_ONS_SUBMARKET_MAP: dict[str, str] = {
    "N": "N",
    "NE": "NE",
    "SE": "SE",  # ONS SE/CO published as SE
    "S": "S",
}

# Peak / off-peak (ponta / fora ponta) for hourly PLD. CCEE does not publish
# a ponta flag; this is the common ANEEL-style 3-hour weekday window.
PLD_TOU: dict[str, Any] = {
    "version": 1,
    "peak_hours": (18, 19, 20),  # 18:00–21:00 (hour-beginning)
    "peak_weekdays": (0, 1, 2, 3, 4),  # Monday–Friday (pandas dayofweek)
    "notes": (
        "Peak is hours 18, 19, 20 (18:00–21:00) on Monday–Friday. "
        "All other hours, including weekends, are off-peak. National "
        "holidays are not excluded (no holiday calendar in this tree)."
    ),
    "owners": ("pld/pld_pipeline.py", "pld/dashboard.py", "api/main.py"),
}

# Health-gate thresholds. Pipelines should fail (not WARN) past these.
HEALTH: dict[str, Any] = {
    "version": 1,
    "pld_max_lag_days": 21,
    "flows_max_staleness_days": 75,
    "supply_max_lag_months": 5,
    "precos_max_lag_months": 6,
    "capacity_flow_window_days": 29,
    "desk_require_pld_se": True,
}

# Convenience aliases used at call sites.
M3_PER_MMBTU = float(POC_ENERGY["m3_per_mmbtu"])
NATGAS_KCAL_PER_M3 = float(ONS_GAS_HEAT["natgas_kcal_per_m3"])
PLD_MAX_LAG_DAYS = int(HEALTH["pld_max_lag_days"])
PLD_PEAK_HOURS = tuple(int(h) for h in PLD_TOU["peak_hours"])
PLD_PEAK_WEEKDAYS = tuple(int(d) for d in PLD_TOU["peak_weekdays"])
FLOWS_MAX_STALENESS_DAYS = int(HEALTH["flows_max_staleness_days"])
SUPPLY_MAX_LAG_MONTHS = int(HEALTH["supply_max_lag_months"])
PRECOS_MAX_LAG_MONTHS = int(HEALTH["precos_max_lag_months"])
CAPACITY_FLOW_WINDOW_DAYS = int(HEALTH["capacity_flow_window_days"])

TRANSFORM_REGISTRY: dict[str, dict[str, Any]] = {
    "ons_gas_heat": ONS_GAS_HEAT,
    "poc_energy": POC_ENERGY,
    "pld_ons_submarket_map": {
        "version": 1,
        "map": PLD_ONS_SUBMARKET_MAP,
        "notes": "SIN has no PLD; join is submarket-level only.",
    },
    "pld_tou": PLD_TOU,
    "health": HEALTH,
}


def pld_is_peak(date, hour) -> bool:
    """True when ``hour`` (0–23) on ``date`` is ANEEL-style ponta (TOU v1)."""
    import pandas as pd

    try:
        h = int(hour)
    except (TypeError, ValueError):
        return False
    if h not in PLD_PEAK_HOURS:
        return False
    ts = pd.Timestamp(date)
    if pd.isna(ts):
        return False
    return int(ts.dayofweek) in PLD_PEAK_WEEKDAYS


def pld_peak_mask(dates, hours):
    """Boolean mask aligned to ``dates`` / ``hours`` for peak (ponta) hours."""
    import pandas as pd

    dates_s = dates if isinstance(dates, pd.Series) else pd.Series(dates)
    hours_s = hours if isinstance(hours, pd.Series) else pd.Series(hours, index=dates_s.index)
    d = pd.to_datetime(dates_s, errors="coerce")
    h = pd.to_numeric(hours_s, errors="coerce")
    return d.dt.dayofweek.isin(PLD_PEAK_WEEKDAYS) & h.isin(PLD_PEAK_HOURS)


def brl_per_m3(price_mmbtu: Any, nd: int = 2) -> float | None:
    """Convert a R$/MMBtu price to R$/m³ by dividing by ``M3_PER_MMBTU``."""
    if price_mmbtu is None:
        return None
    try:
        value = float(price_mmbtu)
    except (TypeError, ValueError):
        return None
    if value != value:  # NaN
        return None
    return round(value / M3_PER_MMBTU, nd)


def registry_summary() -> list[dict[str, Any]]:
    """Compact list for /health or docs."""
    out = []
    for key, meta in TRANSFORM_REGISTRY.items():
        out.append({
            "id": key,
            "version": meta.get("version"),
            "notes": meta.get("notes"),
        })
    return out
