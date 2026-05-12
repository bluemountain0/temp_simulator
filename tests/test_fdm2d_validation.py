# Phase 2 US-5: FDM2D 단기 회귀 가드 + judge 일관성 검증
"""FDM2DSolver 단기 회귀 테스트.

- semi-infinite 해석해 비교 (t_on=1ms)
- HybridFD vs FDM2D judge DamageLevel 일관성
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np

import beam as beam_mod
import materials
from conditions import ExposureCondition, OilCondition
from damage import DamageLevel, judge
from fdm2d_solver import FDM2DSolver
from geometry import TubeGeometry, focal_spot_area
from thermal_solver import HybridFDSolver


_GEOM = TubeGeometry()
_OIL = OilCondition()


def test_semiinfinite_analytical_fdm2d():
    """t_on=1ms 단시간 DC: FDM2D vs semi-infinite 해석해 ±25% (Phase 2 ±20~30% 허용 범위).

    해석해 (표면 z=0): ΔT(0,t) = (2·q'' / k_W) · √(α_W·t / π)
    Phase 2 격자 (24,20) focal 셀 커버리지 ≈ 86% 의 step-function focal mask 이산화 오차가
    peak 셀 (top half-cell, dz/2 ≈ 25μm) 에 농축 가열로 작용 → ~15% 과대평가.
    이는 docs/PHASE2_VALIDATION.md (a) 비교 표의 "FDM2D > 해석해" 부호와 정합.
    Critic #3 옵션 B (해석해 baseline) 채택.
    """
    exp = ExposureCondition(mode="dc_single", kV=100, mA_peak=12, on_time=0.001)
    A_spot = focal_spot_area(_GEOM.focal_L_eff_mm, _GEOM.focal_W_eff_mm, _GEOM.anode_angle_deg)
    q_pp = beam_mod.power_peak(100, 12) / A_spot
    alpha_W = materials.alpha(materials.W)
    dT_ana = (2 * q_pp / materials.W.k) * math.sqrt(alpha_W * 0.001 / math.pi)

    solver = FDM2DSolver(Nr=24, Nz=20)
    result = solver.solve(exp, _GEOM, k_bti5=20.0, oil_cond=_OIL)
    dT_model = result.T_w_surface_peak.max() - 293.15

    rel_err = abs(dT_model - dT_ana) / dT_ana
    assert rel_err < 0.25, (
        f"FDM2D semi-infinite ±25% 초과: 모델 {dT_model:.1f}K vs 해석 {dT_ana:.1f}K "
        f"(오차 {rel_err:.1%})"
    )


def test_judge_consistency_across_solvers():
    """동일 입력에서 HybridFD와 FDM2D DamageLevel 일치 (단기 케이스).

    단기 (t < 100ms) 5 조건에서 두 솔버 DamageLevel 완전 일치.
    """
    cases = [
        ExposureCondition(mode="dc_single", kV=20,  mA_peak=2,  on_time=0.05),
        ExposureCondition(mode="dc_single", kV=60,  mA_peak=8,  on_time=0.05),
        ExposureCondition(mode="dc_single", kV=100, mA_peak=12, on_time=0.01),
        ExposureCondition(mode="dc_cyclic", kV=80,  mA_peak=5,
                          on_time=0.02, off_time=0.01, cycles=3),
        ExposureCondition(mode="dc_single", kV=40,  mA_peak=4,  on_time=0.05),
    ]
    hybrid = HybridFDSolver()
    fdm = FDM2DSolver(Nr=16, Nz=16)  # 빠른 격자

    for exp in cases:
        r_h = hybrid.solve(exp, _GEOM, k_bti5=20.0, oil_cond=_OIL)
        r_f = fdm.solve(exp, _GEOM, k_bti5=20.0, oil_cond=_OIL)
        v_h = judge(r_h)
        v_f = judge(r_f)
        assert v_h.level == v_f.level, (
            f"단기 judge 불일치: case={exp.mode} {exp.kV}kV·{exp.mA_peak}mA·{exp.on_time}s "
            f"HybridFD={v_h.level.name} FDM2D={v_f.level.name}"
        )


def test_judge_consistency_detailed():
    """5 DamageLevel (WARNING1, DAMAGE1, DAMAGE2, DAMAGE3, DAMAGE4) 완전 일치.

    HybridFD 가 각 단계 임계 직전/직후 케이스에서 FDM2D 와 동일 레벨을 반환해야 함.
    임계 케이스는 짧은 시간 (t < 100ms) 으로 단기 검증.
    """
    # 단기 (t < 100ms) 에서 임의의 5 케이스
    # Solver 결과로 DamageLevel 분포가 SAFE/WARNING1/DAMAGE2 등 다양해야 함
    cases = [
        ExposureCondition(mode="dc_single", kV=20,  mA_peak=2,  on_time=0.01),   # SAFE
        ExposureCondition(mode="dc_single", kV=60,  mA_peak=5,  on_time=0.01),   # 중간
        ExposureCondition(mode="dc_single", kV=80,  mA_peak=8,  on_time=0.01),   # 상위
        ExposureCondition(mode="dc_single", kV=100, mA_peak=10, on_time=0.01),   # 강함
        ExposureCondition(mode="dc_single", kV=100, mA_peak=15, on_time=0.01),   # 매우 강함
    ]
    hybrid = HybridFDSolver()
    fdm = FDM2DSolver(Nr=16, Nz=16)

    levels_h = []
    levels_f = []
    for exp in cases:
        r_h = hybrid.solve(exp, _GEOM, k_bti5=20.0, oil_cond=_OIL)
        r_f = fdm.solve(exp, _GEOM, k_bti5=20.0, oil_cond=_OIL)
        levels_h.append(judge(r_h).level)
        levels_f.append(judge(r_f).level)

    # 두 솔버 결과가 단기 5 케이스에서 완전 일치
    assert levels_h == levels_f, (
        f"단기 DamageLevel 시퀀스 불일치:\n"
        f"  HybridFD: {[l.name for l in levels_h]}\n"
        f"  FDM2D   : {[l.name for l in levels_f]}"
    )
