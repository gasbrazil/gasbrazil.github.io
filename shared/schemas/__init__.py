"""
Canonical column contracts for GasBrazil lake tables (ADR-002 Track A).

These are the English, pipeline-facing names. Upstream Portuguese/API fields
are mapped in each project's *_pipeline.py before validate/publish.

Import as ``import schemas`` after ``sys.path`` includes ``shared/``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

# --- Transport ----------------------------------------------------------------

FLOWS_POINTS_COLUMNS = (
    "date",
    "point_code",
    "point_name",
    "point_type",
    "pipeline_code",
    "pipeline_name",
    "municipality",
    "uf",
    "tso",
    "variable",
    "value",
    "source",  # anp | tag | tbg | nts
)

FLOWS_POINT_SOURCES = ("anp", "tag", "tbg", "nts")

FLOWS_LEDGER_COLUMNS = (
    "date",
    "pipeline_code",
    "pipeline_name",
    "tso",
    "variable",
    "value",
)

POC_RESULTS_COLUMNS = (
    "Transporter (TSO)",
    "codigoProcesso",
    "Trade Date",
    "Flow Date Start",
    "Flow Date End",
    "Price",
    "Volume Accepted",
)

CONTRATOS_COLUMNS = (
    "Transporter (TSO)",
    "Contract Number",
    "Status",
    "Shipper",
    "Start Date",
    "End Date",
    "Contracted Capacity (000 m3/d)",
    "Allocated Tariff (R$/MMBtu)",
)

# --- Power --------------------------------------------------------------------

# Long tidy frame written by ons/ons_pipeline.py → data/daily.parquet.
ONS_DAILY_COLUMNS = (
    "date",
    "subsystem",
    "entity",
    "series",
    "value",
)

ONS_ENTITIES_COLUMNS = (
    "kind",
    "entity",
    "subsystem",
    "group",
    "capacity_mw",
    "heat_rate_kcal_per_kwh",
    "rolled_up",
)

PLD_DAILY_COLUMNS = (
    "date",
    "submarket",
    "pld",
)

SUBMARKET_CODES = ("N", "NE", "SE", "S")

# --- Supply -------------------------------------------------------------------

SUPPLY_MONTHLY_COLUMNS = (
    "month",
    "production",
    "available",
    "flare_loss",
    "own_use",
    "reinjection",
    "lgn",
    "imports",
)

# --- Prices (ANP Resolution 52/2011) -----------------------------------------

# Long tidy frame: producers (basin), distributors (market type × region),
# marketers (national). Suppressed months keep null price_brl_mmbtu.
ANP_PRICES_COLUMNS = (
    "month",
    "segment",
    "category",
    "region",
    "price_brl_mmbtu",
    "volume_thousand_m3_day",
)

ANP_PRICE_SEGMENTS = ("producers", "distributors", "marketers")

TSO_CODES = ("NTS", "TAG", "TBG", "TSB", "GOM")


def _require(df: "pd.DataFrame", columns: tuple[str, ...], label: str) -> None:
    import data_kit as dk  # noqa: PLC0415 — shared/ on sys.path

    dk.require_columns(df, columns, label=label)


def validate_flows_points(df: "pd.DataFrame") -> None:
    _require(df, FLOWS_POINTS_COLUMNS, "flows_points")


def validate_flows_ledger(df: "pd.DataFrame") -> None:
    _require(df, FLOWS_LEDGER_COLUMNS, "flows_ledger")


def validate_ons_daily(df: "pd.DataFrame") -> None:
    _require(df, ONS_DAILY_COLUMNS, "ons_daily")


def validate_ons_entities(df: "pd.DataFrame") -> None:
    _require(df, ONS_ENTITIES_COLUMNS, "ons_entities")


def validate_pld_daily(df: "pd.DataFrame") -> None:
    _require(df, PLD_DAILY_COLUMNS, "pld_daily")


def validate_supply_monthly(df: "pd.DataFrame") -> None:
    _require(df, SUPPLY_MONTHLY_COLUMNS, "supply_monthly")


def validate_anp_prices(df: "pd.DataFrame") -> None:
    _require(df, ANP_PRICES_COLUMNS, "anp_prices")


def validate_poc_results(df: "pd.DataFrame") -> None:
    _require(df, POC_RESULTS_COLUMNS, "poc_results")


def validate_contratos(df: "pd.DataFrame") -> None:
    _require(df, CONTRATOS_COLUMNS, "contratos")
