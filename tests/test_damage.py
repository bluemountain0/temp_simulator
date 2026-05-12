import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import pytest
from thermal_solver import ThermalResult
from damage import judge, DamageLevel


T_AMB = 293.15


def _make_result(w_surf_C=20, w_bulk_C=20, bti5_C=20, cu_top_C=20, cu_body_C=20, oil_C=20,
                 w_peak_C=None, t_end=10.0):
    """합성 ThermalResult 생성 헬퍼. 모든 온도는 °C 입력 → K 변환."""
    t = np.array([0.0, t_end])
    T = np.zeros((6, 2))
    for i, val_C in enumerate([w_surf_C, w_bulk_C, bti5_C, cu_top_C, cu_body_C, oil_C]):
        T[i] = [T_AMB, val_C + 273.15]
    peak_C = w_peak_C if w_peak_C is not None else w_surf_C
    T_pk = np.array([T_AMB, peak_C + 273.15])
    return ThermalResult(
        t=t, T=T, T_w_surface_peak=T_pk,
        ambient_K=T_AMB,
        node_names=["W_surf", "W_bulk", "BTi5", "Cu_top", "Cu_body", "Oil"],
    )


def test_safe_all_ambient():
    v = judge(_make_result())
    assert v.level == DamageLevel.SAFE
    assert v.time_to_damage_s is None
    assert v.first_failed_node == "없음"


def test_warning1_bti5_700():
    v = judge(_make_result(bti5_C=710))
    assert v.level == DamageLevel.WARNING1


def test_damage1_bti5_solidus():
    v = judge(_make_result(bti5_C=850))
    assert v.level == DamageLevel.DAMAGE1


def test_damage2_bti5_liquidus():
    v = judge(_make_result(bti5_C=890))
    assert v.level == DamageLevel.DAMAGE2


def test_damage3_cu_top():
    v = judge(_make_result(cu_top_C=1100))
    assert v.level == DamageLevel.DAMAGE3
    assert v.first_failed_node == "Cu top"


def test_damage3_cu_body():
    v = judge(_make_result(cu_body_C=1100))
    assert v.level == DamageLevel.DAMAGE3
    assert v.first_failed_node == "Cu body"


def test_damage4_w_surface():
    v = judge(_make_result(w_peak_C=2600))
    assert v.level == DamageLevel.DAMAGE4
    assert v.first_failed_node == "W surface"


def test_failure_w_melting():
    v = judge(_make_result(w_peak_C=3500))
    assert v.level == DamageLevel.FAILURE
    assert v.first_failed_node == "W surface"


def test_oil_warning_100():
    v = judge(_make_result(oil_C=110))
    assert v.level == DamageLevel.OIL_WARNING


def test_oil_danger_150():
    v = judge(_make_result(oil_C=160))
    assert v.level == DamageLevel.OIL_DANGER


def test_highest_level_wins():
    # DAMAGE4(5) vs DAMAGE1(2) → DAMAGE4
    v = judge(_make_result(w_peak_C=2600, bti5_C=850))
    assert v.level == DamageLevel.DAMAGE4


def test_oil_danger_overrides_failure():
    # IntEnum: OIL_DANGER=8 > FAILURE=6
    v = judge(_make_result(w_peak_C=3500, oil_C=160))
    assert v.level == DamageLevel.OIL_DANGER


def test_max_temps_in_celsius():
    v = judge(_make_result(w_peak_C=3500))
    assert abs(v.max_temps["W surface"] - 3500) < 1.0


def test_time_to_damage_first_crossing():
    """3점 시계열: t=0에서 ambient, t=5s에서 첫 임계값 초과."""
    t = np.array([0.0, 5.0, 10.0])
    T = np.full((6, 3), T_AMB)
    # W surface가 t=5s에서 2500°C 초과
    T_pk = np.array([T_AMB, 2600 + 273.15, 2700 + 273.15])
    result = ThermalResult(
        t=t, T=T, T_w_surface_peak=T_pk,
        ambient_K=T_AMB,
        node_names=["W_surf", "W_bulk", "BTi5", "Cu_top", "Cu_body", "Oil"],
    )
    v = judge(result)
    assert v.level == DamageLevel.DAMAGE4
    assert v.time_to_damage_s == pytest.approx(5.0)


def test_reasons_not_empty_on_damage():
    v = judge(_make_result(bti5_C=850))
    assert len(v.reasons) > 0


def test_reasons_empty_on_safe():
    v = judge(_make_result())
    assert v.reasons == []
