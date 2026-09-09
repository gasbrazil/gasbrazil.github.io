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

# POC / Desk: PCR convention. 28.8081 is MMBtu per 1000 m³ (not per m³).
# R$/m³ = R$/MMBtu × MMBTU_PER_1000_M3 / 1000.
POC_ENERGY: dict[str, Any] = {
    "version": 1,
    "mmbtu_per_1000_m3": 28.8081,
    "notes": "POC PCR factor: MMBtu content of 1000 m³, not of 1 m³.",
    "owners": ("poc/dashboard.py", "desk/build_payload.py"),
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
MMBTU_PER_1000_M3 = float(POC_ENERGY["mmbtu_per_1000_m3"])
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
