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


def _domain_meta(domain: str) -> dict:
    meta = {}
    json_meta = dk.read_pipeline_metadata(domain)
    if json_meta:
        meta.update(json_meta)
    html = _read(ROOT / domain / "index.html")
    if html:
        for k in (
            "kpi_gas_mwmed", "generated", "kpi_price_7d", "kpi_trades_7d", "kpi_when",
            "kpi_contracts", "kpi_capacity", "kpi_total_7d", "kpi_production", "data_through",
            "kpi_santos", "kpi_se", "latest_date", "kpi_pld_se", "kpi_gen_gas", "kpi_linepack",
            "kpi_rate", "kpi_snapshot", "kpi_tag_lp", "kpi_nts_lp", "kpi_nts_rate",
        ):
            v = _marker(html, k)
            if v is not None and k not in meta:
                meta[k] = v
    return meta


def collect() -> dict:
    items: dict = {}
    ons = _domain_meta("ons")
    if ons:
        g = _intish(str(ons.get("kpi_gas_mwmed"))) if ons.get("kpi_gas_mwmed") is not None else None
        when = ons.get("generated")
        if g is not None:
            n = f"{g:,}"
            items["ons"] = {
                "kpiEn": f"{n} MWmed gas",
                "kpiPt": f"{n} MWmed a gás",
                "when": when or "",
            }

    poc = _domain_meta("poc")
    if poc:
        price = _floatish(str(poc.get("kpi_price_7d"))) if poc.get("kpi_price_7d") is not None else None
        trades = poc.get("kpi_trades_7d")
        when = poc.get("kpi_when") or poc.get("generated")
        if price is not None:
            items["poc"] = {
                "kpiEn": f"{price:.2f} R$/MMBtu · {trades or '?'} trades (7d)",
                "kpiPt": f"{price:.2f} R$/MMBtu · {trades or '?'} negócios (7d)",
                "when": when or "",
            }

    con = _domain_meta("contratos")
    if con:
        n = _intish(str(con.get("kpi_contracts"))) if con.get("kpi_contracts") is not None else None
        cap = con.get("kpi_capacity")
        when = con.get("generated")
        if n is not None:
            items["contratos"] = {
                "kpiEn": f"{n:,} contracts · {cap or '—'} thousand m³/d",
                "kpiPt": f"{n:,} contratos · {cap or '—'} mil m³/d",
                "when": when or "",
            }

    flows = _domain_meta("flows")
    if flows:
        total = _floatish(str(flows.get("kpi_total_7d"))) if flows.get("kpi_total_7d") is not None else None
        when = flows.get("generated")
        if total is not None:
            vol = f"{total/1000:.1f}M" if total >= 1000 else f"{total:.0f}"
            items["flows"] = {
                "kpiEn": f"{vol} m³ realized (7d)",
                "kpiPt": f"{vol} m³ realizados (7d)",
                "when": when or "",
            }

    supply = _domain_meta("supply")
    if supply:
        prod = _floatish(str(supply.get("kpi_production"))) if supply.get("kpi_production") is not None else None
        through = supply.get("data_through")
        when = supply.get("generated")
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

    precos = _domain_meta("precos")
    if precos:
        s = _floatish(str(precos.get("kpi_santos"))) if precos.get("kpi_santos") is not None else None
        through = precos.get("data_through")
        when = precos.get("generated")
        if s is not None:
            bit = f" · {through}" if through else ""
            items["precos"] = {
                "kpiEn": f"Santos {s:.1f} R$/MMBtu{bit}",
                "kpiPt": f"Santos {s:.1f} R$/MMBtu{bit}",
                "when": when or "",
            }

    pld = _domain_meta("pld")
    if pld:
        se = _floatish(str(pld.get("kpi_se"))) if pld.get("kpi_se") is not None else None
        day = pld.get("latest_date")
        when = pld.get("generated")
        if se is not None:
            bit = f" · {day}" if day else ""
            items["pld"] = {
                "kpiEn": f"SE {se:.2f} R$/MWh{bit}",
                "kpiPt": f"SE {se:.2f} R$/MWh{bit}",
                "when": when or "",
            }

    desk = _domain_meta("desk")
    if desk:
        se = _floatish(str(desk.get("kpi_pld_se"))) if desk.get("kpi_pld_se") is not None else None
        gas = _floatish(str(desk.get("kpi_gen_gas"))) if desk.get("kpi_gen_gas") is not None else None
        when = desk.get("generated") or desk.get("data_through")
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

    mago = _domain_meta("mago")
    if mago:
        lp = _floatish(str(mago.get("kpi_linepack"))) if mago.get("kpi_linepack") is not None else None
        when = mago.get("generated")
        snap = mago.get("kpi_snapshot")
        if lp is not None:
            items["mago"] = {
                "kpiEn": f"{lp:.2f} Mm³ line pack",
                "kpiPt": f"{lp:.2f} Mm³ empacotamento",
                "when": when or snap or "",
            }

    nts = _domain_meta("nts")
    if nts:
        lp = _floatish(str(nts.get("kpi_linepack"))) if nts.get("kpi_linepack") is not None else None
        rate = _floatish(str(nts.get("kpi_rate"))) if nts.get("kpi_rate") is not None else None
        when = nts.get("generated")
        if lp is not None:
            rate_str = f" · {int(rate):+,} m³/h" if rate is not None else ""
            items["nts"] = {
                "kpiEn": f"{lp:.2f} Mm³ line pack{rate_str}",
                "kpiPt": f"{lp:.2f} Mm³ empacotamento{rate_str}",
                "when": when or "",
            }

    monitor = _domain_meta("monitor")
    if monitor:
        tag_lp = _floatish(str(monitor.get("kpi_tag_lp"))) if monitor.get("kpi_tag_lp") is not None else None
        nts_lp = _floatish(str(monitor.get("kpi_nts_lp"))) if monitor.get("kpi_nts_lp") is not None else None
        when = monitor.get("generated")
        parts_en, parts_pt = [], []
        if tag_lp is not None:
            parts_en.append(f"TAG {tag_lp:.2f} Mm³")
            parts_pt.append(f"TAG {tag_lp:.2f} Mm³")
        if nts_lp is not None:
            parts_en.append(f"NTS {nts_lp:.2f} Mm³")
            parts_pt.append(f"NTS {nts_lp:.2f} Mm³")
        if parts_en:
            items["monitor"] = {
                "kpiEn": " · ".join(parts_en),
                "kpiPt": " · ".join(parts_pt),
                "when": when or "",
            }

    return {
        "generated": dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M UTC"),
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
        "mago": ("mago_kpi", "mago_kpi_pt", "mago_when"),
        "nts": ("nts_kpi", "nts_kpi_pt", "nts_when"),
        "monitor": ("monitor_kpi", "monitor_kpi_pt", "monitor_when"),
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
