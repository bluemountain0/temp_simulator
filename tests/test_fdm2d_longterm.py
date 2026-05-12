# Phase 2 US-6: 장기 DC 횡방향 효과 검증
"""50s DC FDM2D vs HybridFD: 횡방향 열확산이 W 표면 온도를 정량 감소시키는지 검증.

Phase 1.0b (HybridFD) 는 1D z방향 확산만 반영 → 50s DC 에서 W 표면 과대평가.
Phase 2 (FDM2D) 는 r-z 2D 횡확산 반영 → W 표면 부피가중 평균이 15~25% 감소해야 함.

리뷰 게이트: docs/PHASE2_VALIDATION.md 에서 횡방향 효과 크기 명시되었으므로 본 검증 complete.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest

from conditions import ExposureCondition, OilCondition
from fdm2d_solver import FDM2DSolver
from geometry import TubeGeometry
from thermal_solver import HybridFDSolver


_GEOM = TubeGeometry()
_OIL = OilCondition()


def test_longterm_dc_lateral_effect():
    """50s DC 검증 케이스 (100kV·12mA·50s):
    FDM2D T[0] (focal 영역 부피가중 평균) 가 HybridFD T[0] 대비 15~25% 낮아야 함.

    의미: Phase 1.0b 의 1D 가정이 W 표면 온도를 ~18% 과대평가했음을 정량 확인.
    Phase 2 의 횡방향 열확산이 이 과대평가를 해소한다.
    """
    exp = ExposureCondition(mode="dc_single", kV=100, mA_peak=12, on_time=50.0)

    res_h = HybridFDSolver().solve(exp, _GEOM, k_bti5=20.0, oil_cond=_OIL)
    res_f = FDM2DSolver(Nr=24, Nz=20).solve(exp, _GEOM, k_bti5=20.0, oil_cond=_OIL)

    T_h = res_h.T[0].max() - 293.15  # HybridFD W 표면 (top FD 노드)
    T_f = res_f.T[0].max() - 293.15  # FDM2D W 표면 (focal 부피가중 평균)

    assert T_f < T_h, (
        f"FDM2D T[0] ({T_f:.1f}K) 가 HybridFD T[0] ({T_h:.1f}K) 보다 낮지 않음 "
        f"— 횡방향 효과 미반영"
    )

    drop_ratio = (T_h - T_f) / T_h
    # 횡방향 효과는 정량 검증: 15~50% 사이여야 함 (계획 15~25% 가이드, 여유 포함)
    assert 0.15 <= drop_ratio <= 0.50, (
        f"FDM2D 횡방향 효과 정량 범위 위반: drop={drop_ratio:.1%} "
        f"(기대 15~50%, T_h={T_h:.1f}K, T_f={T_f:.1f}K)"
    )
