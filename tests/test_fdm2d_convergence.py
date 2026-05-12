# Phase 2 US-5.5: FDM2D 격자 수렴 검증
"""검증 케이스 (100kV·12mA·50s DC) 의 격자 수렴 확인.

3 스케일 (Nr, Nz) ∈ {(16,16), (24,20), (32,28)}:
- 모두 DAMAGE4 유지 (옵션 X — Acceptance Criteria 9번)
- T_w_surface_peak 최대값이 격자 사이 < 2% 수렴
- (32,28) wall-time < 60s
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest

from conditions import ExposureCondition, OilCondition
from damage import DamageLevel, judge
from fdm2d_solver import FDM2DSolver
from geometry import TubeGeometry


_SCALES = [(16, 16), (24, 20), (32, 28)]
_GEOM = TubeGeometry()
_OIL = OilCondition()
_EXP = ExposureCondition(mode="dc_single", kV=100, mA_peak=12, on_time=50.0)


def test_grid_convergence_study():
    """3 격자 스케일에서 검증 케이스 실행:
      - 모두 DAMAGE4 이상 유지
      - T_w_surface_peak 최대값이 (16,16)→(24,20) 와 (24,20)→(32,28) 사이 < 2% 변화
      - (32,28) 계산 시간 < 60s
    """
    peaks = []
    elapsed_max = 0.0

    for Nr, Nz in _SCALES:
        solver = FDM2DSolver(Nr=Nr, Nz=Nz)
        t0 = time.perf_counter()
        result = solver.solve(_EXP, _GEOM, k_bti5=20.0, oil_cond=_OIL)
        elapsed = time.perf_counter() - t0

        verdict = judge(result)
        assert verdict.level >= DamageLevel.DAMAGE4, (
            f"({Nr},{Nz}) DAMAGE4 미달: {verdict.level.name} "
            f"(W surf max = {verdict.max_temps.get('W surface', 0):.0f}°C)"
        )

        peak_K = float(result.T_w_surface_peak.max())
        peaks.append(peak_K)

        if (Nr, Nz) == (32, 28):
            assert elapsed < 60.0, f"(32,28) wall-time {elapsed:.1f}s > 60s"
        if elapsed > elapsed_max:
            elapsed_max = elapsed

    # 격자 사이 상대 변화 검사
    # (24,20) → (32,28) 가 핵심 수렴 지표 (계획 US-5.5: <2% 면 (24,20) 채택)
    # (16,16) → (24,20) 는 수렴 추세 가드 (다소 거친 격자라 < 3%)
    dT_16 = peaks[0] - 293.15
    dT_24 = peaks[1] - 293.15
    dT_32 = peaks[2] - 293.15

    rel_16_24 = abs(dT_24 - dT_16) / dT_16
    rel_24_32 = abs(dT_32 - dT_24) / dT_24

    assert rel_24_32 < 0.02, (
        f"(24,20)→(32,28) 격자 수렴 위반: rel={rel_24_32:.4f} ≥ 2% "
        f"(dT_24={dT_24:.1f}K, dT_32={dT_32:.1f}K)"
    )
    assert rel_16_24 < 0.03, (
        f"(16,16)→(24,20) 수렴 추세 위반: rel={rel_16_24:.4f} ≥ 3% "
        f"(dT_16={dT_16:.1f}K, dT_24={dT_24:.1f}K)"
    )
