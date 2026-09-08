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
    return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""


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
        return float(raw)
    except ValueError:
        return None


def collect() -> dict:
    items: dict = {}
    ons = _read(ROOT / "ons" / "index.html")
    if ons:
        g = _marker(ons, "kpi_gas_mwmed")
        when = _marker(ons, "generated")
        if g:
            n = f"{int(g):,}"
            items["ons"] = {
                "kpiEn": f"{n} MWmed gas",
                "kpiPt": f"{n} MWmed a gás",
                "when": when or "",
            }

    poc = _read(ROOT / "poc" / "index.html")
    if poc:
        price = _marker(poc, "kpi_price_7d")
        trades = _marker(poc, "kpi_trades_7d")
        when = _marker(poc, "kpi_when") or _marker(poc, "generated")
        if price:
            items["poc"] = {
                "kpiEn": f"{float(price):.2f} R$/MMBtu · {trades or '?'} trades (7d)",
                "kpiPt": f"{float(price):.2f} R$/MMBtu · {trades or '?'} negócios (7d)",
                "when": when or "",
            }

    con = _read(ROOT / "contratos" / "index.html")
    if con:
        n = _marker(con, "kpi_contracts")
        cap = _marker(con, "kpi_capacity")
        when = _marker(con, "generated")
        if n:
            items["contratos"] = {
                "kpiEn": f"{int(n):,} contracts · {cap or '—'} thousand m³/d",
                "kpiPt": f"{int(n):,} contratos · {cap or '—'} mil m³/d",
                "when": when or "",
            }

    flows = _read(ROOT / "flows" / "index.html")
    if flows:
        total = _marker(flows, "kpi_total_7d")
        when = _marker(flows, "generated")
        if total:
            t = float(total)
            vol = f"{t/1000:.1f}M" if t >= 1000 else f"{t:.0f}"
            items["flows"] = {
                "kpiEn": f"{vol} m³ realized (7d)",
                "kpiPt": f"{vol} m³ realizados (7d)",
                "when": when or "",
            }

    supply = _read(ROOT / "supply" / "index.html")
    if supply:
        prod = _marker(supply, "kpi_production")
        through = _marker(supply, "data_through")
        when = _marker(supply, "generated")
        if prod:
            p = float(prod)
            vol = f"{p/1_000_000:.1f}M" if p >= 1_000_000 else (f"{p/1000:.0f}k" if p >= 1000 else f"{p:.0f}")
            bit = f" · {through}" if through else ""
            items["supply"] = {
                "kpiEn": f"{vol} thousand m³ produced{bit}",
                "kpiPt": f"{vol} mil m³ produzidos{bit}",
                "when": when or "",
            }

    precos = _read(ROOT / "precos" / "index.html")
    if precos:
        s = _marker(precos, "kpi_santos")
        through = _marker(precos, "data_through")
        when = _marker(precos, "generated")
        if s:
            bit = f" · {through}" if through else ""
            items["precos"] = {
                "kpiEn": f"Santos {float(s):.1f} R$/MMBtu{bit}",
                "kpiPt": f"Santos {float(s):.1f} R$/MMBtu{bit}",
                "when": when or "",
            }

    pld = _read(ROOT / "pld" / "index.html")
    if pld:
        se = _marker(pld, "kpi_se")
        day = _marker(pld, "latest_date")
        when = _marker(pld, "generated")
        if se:
            bit = f" · {day}" if day else ""
            items["pld"] = {
                "kpiEn": f"SE {float(se):.2f} R$/MWh{bit}",
                "kpiPt": f"SE {float(se):.2f} R$/MWh{bit}",
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


def main() -> None:
    payload = collect()
    path, url = dk.write_and_publish_teasers(payload, ROOT / "hub")
    print(f"Wrote teasers ({len(payload['items'])} items) -> {path} / {url}")


if __name__ == "__main__":
    main()
