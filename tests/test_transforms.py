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


def test_pld_tou_weekday_peak_hours():
    assert xf.PLD_TOU["version"] == 1
    friday = "2026-09-11"  # Friday
    saturday = "2026-09-12"
    assert xf.pld_is_peak(friday, 18) is True
    assert xf.pld_is_peak(friday, 19) is True
    assert xf.pld_is_peak(friday, 20) is True
    assert xf.pld_is_peak(friday, 17) is False
    assert xf.pld_is_peak(saturday, 18) is False
    import pandas as pd
    mask = xf.pld_peak_mask(
        pd.to_datetime([friday, friday, saturday]),
        [18, 12, 18],
    )
    assert list(mask) == [True, False, False]
