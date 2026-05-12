"""검증 케이스 회귀 테스트.

기준 케이스: 100 kV · 12 mA · 50 s DC (HybridFDSolver)
Validity envelope: t_on=50s DC → ±50~100% 신뢰도 영역.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
import numpy as np

from conditions import ExposureCondition, OilCondition
from geometry import TubeGeometry
from thermal_solver import HybridFDSolver, RCSolver
from thermal_rc import effective_t_exposure, effective_delta, MAX_T_EXPOSURE_SURFACE
from damage import judge, DamageLevel
import beam as beam_mod


_GEOM = TubeGeometry()
_OIL  = OilCondition()


def test_baseline_100kV_12mA_50s_HybridFD():
    """스펙 Acceptance Criteria 9번: 타겟 손상 위험 판정.

    HybridFDSolver (RC 에스컬레이션 후 기본 솔버).
    Validity envelope: t_on=50s DC → ±50~100% 신뢰도.
    """
    exp = ExposureCondition(mode="dc_single", kV=100, mA_peak=12, on_time=50.0)
    result = HybridFDSolver().solve(exp, _GEOM, k_bti5=20, oil_cond=_OIL)
    verdict = judge(result)

    assert verdict.level >= DamageLevel.DAMAGE4, (
        f"Expected ≥ DAMAGE4, got {verdict.level.name}. "
        f"W surf max = {verdict.max_temps.get('W surface', 0):.0f}°C"
    )
    assert verdict.first_failed_node in ("W surface", "W bulk")


def test_safe_low_power():
    """저전력 조건 → SAFE."""
    exp = ExposureCondition(mode="dc_single", kV=10, mA_peak=0.1, on_time=1.0)
    result = HybridFDSolver().solve(exp, _GEOM, k_bti5=20, oil_cond=_OIL)
    assert judge(result).level == DamageLevel.SAFE


def test_rc_solver_passes_basic():
    """RCSolver 기본 동작 확인 (DAMAGE4 미달이지만 오류 없음)."""
    exp = ExposureCondition(mode="dc_single", kV=100, mA_peak=12, on_time=10.0)
    result = RCSolver().solve(exp, _GEOM, k_bti5=20, oil_cond=_OIL)
    assert result.T.shape == (6, len(result.t))
    assert result.T.min() >= 293.15 - 1.0  # ambient 이하로 내려가지 않음


def test_pulse_peak_vs_average_power():
    """Pulse peak mA 기반 P_avg 계산."""
    P_avg = beam_mod.power_average(beam_mod.power_peak(100, 10), mode="pulse", duty=0.1)
    assert P_avg == pytest.approx(100.0)


def test_bti5_k_sensitivity():
    """BTi-5 k↓ → W 표면 온도↑ (열저항 증가)."""
    exp = ExposureCondition(mode="dc_single", kV=80, mA_peak=8, on_time=5.0)
    T_k10 = HybridFDSolver().solve(exp, _GEOM, k_bti5=10,  oil_cond=_OIL).T[0].max()
    T_k40 = HybridFDSolver().solve(exp, _GEOM, k_bti5=40,  oil_cond=_OIL).T[0].max()
    assert T_k10 > T_k40, "k_bti5 낮을수록 온도 높아야 함"


def test_max_t_exposure_clamped():
    """on_time=10s DC → t_exp = MAX_T_EXPOSURE_SURFACE (≈14ms)로 클램프."""
    exp = ExposureCondition(mode="dc_single", kV=100, mA_peak=12, on_time=10.0)
    assert effective_t_exposure(exp) == pytest.approx(MAX_T_EXPOSURE_SURFACE)


def test_delta_clamped_to_half_thickness():
    """delta_eff ≤ 0.5 * target_t 항상 성립."""
    geom = TubeGeometry()
    for t_exp_val in [1e-6, 1e-3, 0.1, 1.0, 100.0]:
        delta = effective_delta(t_exp_val, geom)
        assert delta <= 0.5 * geom.target_t + 1e-12, (
            f"t_exp={t_exp_val}: delta={delta:.6f} > 0.5*target_t={0.5*geom.target_t:.6f}"
        )


def test_dc_cyclic_n_cycles_temperature_accumulates():
    """DC cyclic 5사이클: Cu_body 온도가 1사이클보다 5사이클에서 높아야 함."""
    oil = OilCondition(h_oil=1, h_oil_air=1)  # 약한 냉각 → 누적 효과 강조
    exp1 = ExposureCondition(mode="dc_cyclic", kV=80, mA_peak=5,
                             on_time=1.0, off_time=0.5, cycles=1)
    exp5 = ExposureCondition(mode="dc_cyclic", kV=80, mA_peak=5,
                             on_time=1.0, off_time=0.5, cycles=5)
    T1 = HybridFDSolver().solve(exp1, _GEOM, k_bti5=20, oil_cond=oil).T[4].max()
    T5 = HybridFDSolver().solve(exp5, _GEOM, k_bti5=20, oil_cond=oil).T[4].max()
    assert T5 > T1, f"5사이클({T5-273.15:.1f}°C) ≤ 1사이클({T1-273.15:.1f}°C)"


def test_hybridfd_ode_converges():
    """HybridFD ODE solver가 성공적으로 수렴해야 함."""
    exp = ExposureCondition(mode="dc_single", kV=100, mA_peak=12, on_time=5.0)
    result = HybridFDSolver().solve(exp, _GEOM, k_bti5=20, oil_cond=_OIL)
    assert result.t[-1] >= 4.9  # 시뮬레이션 완료


def test_forced_convection_lower_temp():
    """강제대류 (h=200) → 자연대류 (h=50) 대비 Cu_body 온도 낮아야 함."""
    exp = ExposureCondition(mode="dc_single", kV=100, mA_peak=12, on_time=10.0)
    oil_nat  = OilCondition(h_oil=50)
    oil_forc = OilCondition(h_oil=200, convection_mode="forced")
    T_nat  = HybridFDSolver().solve(exp, _GEOM, k_bti5=20, oil_cond=oil_nat).T[4].max()
    T_forc = HybridFDSolver().solve(exp, _GEOM, k_bti5=20, oil_cond=oil_forc).T[4].max()
    assert T_forc < T_nat, "강제대류 시 Cu_body 온도가 자연대류보다 낮아야 함"
