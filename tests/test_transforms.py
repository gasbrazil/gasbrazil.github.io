from __future__ import annotations

import math

import transforms as xf


def test_poc_energy_v2_divides_by_m3_per_mmbtu():
    assert xf.POC_ENERGY["version"] == 2
    assert xf.M3_PER_MMBTU == 26.8081
    assert xf.brl_per_m3(26.8081) == 1.0
    # 33.51 is a real GUS print from the source feed.
    assert xf.brl_per_m3(33.51) == round(33.51 / 26.8081, 2)
    assert xf.brl_per_m3(None) is None
    assert xf.brl_per_m3(float("nan")) is None
    # Desk KPIs keep 3 decimals; tables keep 2.
    assert xf.brl_per_m3(42.99, nd=3) == round(42.99 / 26.8081, 3)
    assert not math.isclose(xf.brl_per_m3(42.99), 42.99 * 28.8081 / 1000, rel_tol=0.01)
