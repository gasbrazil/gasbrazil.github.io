#!/usr/bin/env python3
"""Collect hub KPI teasers and publish hub/teasers.json.gz (Track B / R2)."""
from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import data_kit as dk  # noqa: E402


def _read(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _marker(text: str, key: str) -> str | None:
    # Same-line only ([ \\t]* not \\s*) so an empty value cannot spill into
    # the next marker on the following line. Lookbehind avoids matching
    # ``kpi_se`` inside ``kpi_pld_se``.
    m = re.search(rf"(?<![A-Za-z0-9_]){re.escape(key)}:[ \t]*([^\n]*)", text)
    if not m:
        return None
    val = m.group(1).strip()
    if val.endswith("-->"):
        val = val[:-3].strip()
    return val or None


def _floatish(raw: str | None) -> float | None:
    if raw is None:
        return None
    try:
        return float(raw.replace(",", ""))
    except ValueError:
        return None


def _intish(raw: str | None) -> int | None:
    v = _floatish(raw)
    if v is None:
        return None
    return int(v)


def collect() -> dict:
    items: dict = {}
    ons = _read(ROOT / "ons" / "index.html")
    if ons:
        g = _intish(_marker(ons, "kpi_gas_mwmed"))
        when = _marker(ons, "generated")
        if g is not None:
            n = f"{g:,}"
            items["ons"] = {
                "kpiEn": f"{n} MWmed gas",
                "kpiPt": f"{n} MWmed a gás",
                "when": when or "",
            }

    poc = _read(ROOT / "poc" / "index.html")
    if poc:
        price = _floatish(_marker(poc, "kpi_price_7d"))
        trades = _marker(poc, "kpi_trades_7d")
        when = _marker(poc, "kpi_when") or _marker(poc, "generated")
        if price is not None:
            items["poc"] = {
                "kpiEn": f"{price:.2f} R$/MMBtu · {trades or '?'} trades (7d)",
                "kpiPt": f"{price:.2f} R$/MMBtu · {trades or '?'} negócios (7d)",
                "when": when or "",
            }

    con = _read(ROOT / "contratos" / "index.html")
    if con:
        n = _intish(_marker(con, "kpi_contracts"))
        cap = _marker(con, "kpi_capacity")
        when = _marker(con, "generated")
        if n is not None:
            items["contratos"] = {
                "kpiEn": f"{n:,} contracts · {cap or '—'} thousand m³/d",
                "kpiPt": f"{n:,} contratos · {cap or '—'} mil m³/d",
                "when": when or "",
            }

    flows = _read(ROOT / "flows" / "index.html")
    if flows:
        total = _floatish(_marker(flows, "kpi_total_7d"))
        when = _marker(flows, "generated")
        if total is not None:
            vol = f"{total/1000:.1f}M" if total >= 1000 else f"{total:.0f}"
            items["flows"] = {
                "kpiEn": f"{vol} m³ realized (7d)",
                "kpiPt": f"{vol} m³ realizados (7d)",
                "when": when or "",
            }

    supply = _read(ROOT / "supply" / "index.html")
    if supply:
        prod = _floatish(_marker(supply, "kpi_production"))
        through = _marker(supply, "data_through")
        when = _marker(supply, "generated")
        if prod is not None:
            vol = (
                f"{prod/1_000_000:.1f}M" if prod >= 1_000_000
                else (f"{prod/1000:.0f}k" if prod >= 1000 else f"{prod:.0f}")
            )
            bit = f" · {through}" if through else ""
            items["supply"] = {
                "kpiEn": f"{vol} thousand m³ produced{bit}",
                "kpiPt": f"{vol} mil m³ produzidos{bit}",
                "when": when or "",
            }

    precos = _read(ROOT / "precos" / "index.html")
    if precos:
        s = _floatish(_marker(precos, "kpi_santos"))
        through = _marker(precos, "data_through")
        when = _marker(precos, "generated")
        if s is not None:
            bit = f" · {through}" if through else ""
            items["precos"] = {
                "kpiEn": f"Santos {s:.1f} R$/MMBtu{bit}",
                "kpiPt": f"Santos {s:.1f} R$/MMBtu{bit}",
                "when": when or "",
            }

    pld = _read(ROOT / "pld" / "index.html")
    if pld:
        se = _floatish(_marker(pld, "kpi_se"))
        day = _marker(pld, "latest_date")
        when = _marker(pld, "generated")
        if se is not None:
            bit = f" · {day}" if day else ""
            items["pld"] = {
                "kpiEn": f"SE {se:.2f} R$/MWh{bit}",
                "kpiPt": f"SE {se:.2f} R$/MWh{bit}",
                "when": when or "",
            }

    desk = _read(ROOT / "desk" / "index.html")
    if desk:
        se = _floatish(_marker(desk, "kpi_pld_se"))
        gas = _floatish(_marker(desk, "kpi_gen_gas"))
        when = _marker(desk, "generated") or _marker(desk, "data_through")
        if se is not None or gas is not None:
            parts_en, parts_pt = [], []
            if gas is not None:
                parts_en.append(f"{gas:.0f} MWmed gas")
                parts_pt.append(f"{gas:.0f} MWmed a gás")
            if se is not None:
                parts_en.append(f"PLD SE {se:.2f}")
                parts_pt.append(f"PLD SE {se:.2f}")
            items["desk"] = {
                "kpiEn": " · ".join(parts_en),
                "kpiPt": " · ".join(parts_pt),
                "when": when or "",
            }

    return {
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "items": items,
    }


def status_from_teasers(payload: dict | None = None) -> dict:
    """Hub card fields matching build_home.collect_status() KPI keys."""
    payload = payload if payload is not None else collect()
    items = payload.get("items") or {}
    mapping = {
        "ons": ("ons_kpi", "ons_kpi_pt", "ons_when"),
        "poc": ("poc_kpi", "poc_kpi_pt", "poc_when"),
        "contratos": ("contratos_kpi", "contratos_kpi_pt", "contratos_when"),
        "flows": ("flows_kpi", "flows_kpi_pt", "flows_when"),
        "supply": ("supply_kpi", "supply_kpi_pt", "supply_when"),
        "pld": ("pld_kpi", "pld_kpi_pt", "pld_when"),
        "precos": ("precos_kpi", "precos_kpi_pt", "precos_when"),
        "desk": ("desk_kpi", "desk_kpi_pt", "desk_when"),
    }
    out: dict = {}
    for slug, (en, pt, when) in mapping.items():
        item = items.get(slug) or {}
        out[en] = item.get("kpiEn")
        out[pt] = item.get("kpiPt")
        out[when] = item.get("when")
    return out


def main() -> None:
    payload = collect()
    path, url = dk.write_and_publish_teasers(payload, ROOT / "hub")
    print(f"Wrote teasers ({len(payload['items'])} items) -> {path} / {url}")


if __name__ == "__main__":
    main()
