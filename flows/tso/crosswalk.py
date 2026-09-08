"""Optional TSO point-name → ANP point_code crosswalk.

JSON shape::

    {
      "tag": {"tag|cacimbas utgc": "123456"},
      "tbg": {},
      "nts": {}
    }

Keys are ``normalize_key(f"{tso}|{point_name}")``. Values are ANP
``Código da Instalação de Gasoduto``.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .base import normalize_key

HERE = Path(__file__).resolve().parent
CROSSWALK_PATH = HERE / "point_crosswalk.json"


def load_crosswalk(path: Path = CROSSWALK_PATH) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {"tag": {}, "tbg": {}, "nts": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"tag": {}, "tbg": {}, "nts": {}}
    out: dict[str, dict[str, str]] = {"tag": {}, "tbg": {}, "nts": {}}
    for source in out:
        raw = data.get(source) or {}
        if isinstance(raw, dict):
            out[source] = {str(k): str(v) for k, v in raw.items()}
    return out


def save_crosswalk(data: dict, path: Path = CROSSWALK_PATH) -> None:
    path.write_text(
        json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def propose_matches(
    tso_points: pd.DataFrame,
    anp_points: pd.DataFrame,
    *,
    source: str = "tag",
) -> list[dict]:
    """Suggest crosswalk entries by normalized name (+ optional UF)."""
    if tso_points.empty or anp_points.empty:
        return []
    anp_meta = (
        anp_points.sort_values("date")
        .drop_duplicates(subset=["point_code"], keep="last")
        [["point_code", "point_name", "uf", "tso"]]
        .copy()
    )
    anp_meta["_key"] = anp_meta["point_name"].map(normalize_key)
    anp_by_key: dict[str, list] = {}
    for _, row in anp_meta.iterrows():
        anp_by_key.setdefault(row["_key"], []).append(row)

    tso_meta = (
        tso_points.drop_duplicates(subset=["point_name"], keep="last")
        [["point_name", "uf", "tso", "point_code"]]
    )
    proposals = []
    for _, row in tso_meta.iterrows():
        key = normalize_key(row["point_name"])
        cw_key = normalize_key(f"{row['tso']}|{row['point_name']}")
        candidates = list(anp_by_key.get(key, []))
        if not candidates:
            for ak, rows in anp_by_key.items():
                if key and ak and (key in ak or ak in key):
                    candidates.extend(rows)
        best = None
        for cand in candidates:
            if str(cand["tso"]).upper() != str(row["tso"]).upper():
                continue
            if row.get("uf") and cand.get("uf") and str(row["uf"]).casefold() != str(cand["uf"]).casefold():
                continue
            best = cand
            break
        if best is None and candidates:
            best = candidates[0]
        if best is not None:
            proposals.append({
                "source": source,
                "crosswalk_key": cw_key,
                "tso_point_name": row["point_name"],
                "tso_point_code": row["point_code"],
                "anp_point_code": best["point_code"],
                "anp_point_name": best["point_name"],
            })
    return proposals
