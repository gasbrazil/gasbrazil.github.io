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

# CCEE PLD submarkets ↔ ONS subsystem codes used for cross-product joins.
PLD_ONS_SUBMARKET_MAP: dict[str, str] = {
    "N": "N",
    "NE": "NE",
    "SE": "SE",  # ONS SE/CO published as SE
    "S": "S",
}

TRANSFORM_REGISTRY: dict[str, dict[str, Any]] = {
    "ons_gas_heat": ONS_GAS_HEAT,
    "pld_ons_submarket_map": {
        "version": 1,
        "map": PLD_ONS_SUBMARKET_MAP,
        "notes": "SIN has no PLD; join is submarket-level only.",
    },
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
