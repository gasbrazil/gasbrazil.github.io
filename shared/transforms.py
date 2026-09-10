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
    "health": HEALTH,
}


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
