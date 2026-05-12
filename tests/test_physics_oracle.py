"""Physics oracle 테스트: analytical 비교, 에너지 보존, ambient 수렴, pulse 보정.

RC solver는 semi-infinite 해석해 대비 25.7% 오차(±10% 초과)로 oracle 실패.
→ HybridFDSolver(W 슬랩 1D-FD) 활성화 (오차 8.1%, ±10% 통과).
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import math
import numpy as np
import pytest

from conditions import ExposureCondition, OilCondition
from geometry import TubeGeometry, focal_spot_area, thermal_capacities
from thermal_rc import MAX_T_EXPOSURE_SURFACE, effective_t_exposure
from thermal_solver import HybridFDSolver, RCSolver
import materials
import beam as beam_mod


def test_semiinfinite_slab_analytical():
    """단시간 DC (t_on=1ms): W surface 상승치를 semi-infinite 해석해와 ±10% 비교.

    해석해: ΔT(0,t) = (2*q''/ k_W) * sqrt(alpha_W * t / pi)
    RCSolver 오차 ~26% → HybridFDSolver 사용 (오차 8.1%, 통과 기준).
    """
    exp = ExposureCondition(mode="dc_single", kV=100, mA_peak=12, on_time=0.001)
    geom = TubeGeometry()
    A_spot = focal_spot_area(1.1, 0.75, 12)
    q_pp = beam_mod.power_peak(100, 12) / A_spot
    alpha_W = materials.alpha(materials.W)
    t = 0.001
    dT_ana = (2 * q_pp / materials.W.k) * math.sqrt(alpha_W * t / math.pi)

    result = HybridFDSolver().solve(exp, geom, k_bti5=20, oil_cond=OilCondition())
    dT_model = result.T[0].max() - 293.15

    rel_err = abs(dT_model - dT_ana) / dT_ana
    assert rel_err < 0.10, (
        f"HybridFD semi-infinite ±10% 초과: 모델 {dT_model:.1f}K vs 해석 {dT_ana:.1f}K "
        f"(오차 {rel_err:.1%})"
    )


def test_semiinfinite_rc_exceeds_threshold():
    """RCSolver는 semi-infinite 해석해 대비 10% 초과 (HybridFD 필요성 문서화)."""
    exp = ExposureCondition(mode="dc_single", kV=100, mA_peak=12, on_time=0.001)
    geom = TubeGeometry()
    A_spot = focal_spot_area(1.1, 0.75, 12)
    q_pp = beam_mod.power_peak(100, 12) / A_spot
    alpha_W = materials.alpha(materials.W)
    dT_ana = (2 * q_pp / materials.W.k) * math.sqrt(alpha_W * 0.001 / math.pi)

    result = RCSolver().solve(exp, geom, k_bti5=20, oil_cond=OilCondition())
    dT_rc = result.T[0].max() - 293.15
    rel_err = abs(dT_rc - dT_ana) / dT_ana
    assert rel_err > 0.10, "RCSolver가 예상과 달리 ±10% 내에 수렴 — 설계 검토 필요"


def test_energy_conservation():
    """단열 조건 (h≈0): 입력 에너지 = ΣC_i*(T_final - T_init), 오차 ±2% 이내."""
    exp = ExposureCondition(mode="dc_single", kV=100, mA_peak=12, on_time=10.0)
    geom = TubeGeometry()
    oil = OilCondition(h_oil=1e-12, h_oil_air=1e-12)
    T_init = 293.15

    result = RCSolver().solve(exp, geom, k_bti5=20, oil_cond=oil, T_init=T_init)

    E_in = beam_mod.power_peak(100, 12) * exp.on_time  # 12000 J

    focal_area = focal_spot_area(geom.focal_L_eff_mm, geom.focal_W_eff_mm, geom.anode_angle_deg)
    t_exp = effective_t_exposure(exp)
    C = thermal_capacities(geom, focal_area=focal_area, t_exp=t_exp, oil_cond=oil)

    T_final = result.T[:, -1]
    E_stored = float(np.sum(C * (T_final - T_init)))

    rel_err = abs(E_in - E_stored) / E_in
    assert rel_err < 0.02, f"에너지 보존 오차 {rel_err:.2%} (허용 2%)"


def test_ambient_convergence():
    """0 W, 1000s, 고속 냉각 조건 → 모든 노드 ambient ±0.5K 수렴."""
    exp = ExposureCondition(mode="dc_single", kV=0, mA_peak=0, on_time=1000.0)
    geom = TubeGeometry()
    oil = OilCondition(h_oil=1e4, h_oil_air=1e4)  # 빠른 수렴용

    result = RCSolver().solve(exp, geom, k_bti5=20, oil_cond=oil, T_init=400.0)

    T_final = result.T[:, -1]
    assert np.all(np.abs(T_final - 293.15) < 0.5), (
        f"ambient 미수렴: max 편차 = {np.max(np.abs(T_final - 293.15)):.3f} K"
    )


def test_pulse_peak_vs_avgpower_hotspot():
    """1kHz 10% duty pulse: T_w_surface_peak > 동일 평균전력 DC의 T_W_surf × 1.5."""
    exp_pulse = ExposureCondition(
        mode="pulse", kV=100, mA_peak=10, on_time=0.1, freq_hz=1000, duty=0.1,
    )
    # 동일 평균전력 DC: P_avg = 100kV * 10mA * 0.1 = 100W → mA_peak=1
    exp_avg = ExposureCondition(mode="dc_single", kV=100, mA_peak=1, on_time=0.1)
    geom = TubeGeometry()
    oil = OilCondition()

    r_pulse = RCSolver().solve(exp_pulse, geom, k_bti5=20, oil_cond=oil)
    r_avg   = RCSolver().solve(exp_avg,   geom, k_bti5=20, oil_cond=oil)

    # ambient 기준 온도 상승량(ΔT) 비교: ambient 오프셋이 배율을 희석하지 않도록
    dT_pulse = r_pulse.T_w_surface_peak.max() - 293.15
    dT_avg   = r_avg.T[0].max() - 293.15
    assert dT_pulse > dT_avg * 1.5, (
        f"pulse ΔT {dT_pulse:.1f}K vs avg ΔT {dT_avg:.1f}K — 보정 효과 불충분"
    )


def test_w_capacitance_energy_conservation():
    """geometry.thermal_capacities: C[0]+C[1] = rho_W * cp_W * V_W_total (1e-6 오차)."""
    import math
    geom = TubeGeometry()
    focal_area = focal_spot_area(1.1, 0.75, 12)
    oil = OilCondition()
    C = thermal_capacities(geom, focal_area=focal_area, t_exp=1e-3, oil_cond=oil)

    V_W = math.pi * (geom.target_d / 2) ** 2 * geom.target_t
    C_W_expected = materials.W.rho * materials.W.cp * V_W
    rel_err = abs(C[0] + C[1] - C_W_expected) / C_W_expected
    assert rel_err < 1e-6, f"W 열용량 에너지 보존 위반: rel_err={rel_err:.2e}"
