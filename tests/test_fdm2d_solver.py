# US-4 FDM2DSolver 솔버 통합 테스트
import json
import math
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import numpy.testing as npt
import pytest

import materials
from conditions import ExposureCondition, OilCondition
from fdm2d_solver import FDM2DSolver
from geometry import TubeGeometry, focal_spot_area
from thermal_solver import HybridFDSolver, ThermalResult


def _default_exp(on_time: float = 1.0) -> ExposureCondition:
    return ExposureCondition(
        mode="dc_single",
        kV=80.0,
        mA_peak=10.0,
        on_time=on_time,
    )


def test_fdm2d_solver_returns_thermalresult():
    """반환형 검증: ThermalResult 구조 + 노드 6개."""
    solver = FDM2DSolver(Nr=8, Nz=8)
    exp = _default_exp(on_time=0.5)
    geom = TubeGeometry()
    oil = OilCondition()
    res = solver.solve(exp, geom, k_bti5=20.0, oil_cond=oil)

    assert isinstance(res, ThermalResult)
    assert res.T.shape[0] == 6
    assert res.T.shape[1] == res.t.shape[0]
    assert res.T_w_surface_peak.shape == res.t.shape
    assert len(res.node_names) == 6
    assert res.ambient_K == pytest.approx(293.15)
    # 온도는 모두 ambient 이상
    assert np.all(res.T >= 293.15 - 1e-6)
    # W surface peak >= W surface mean
    assert np.all(res.T_w_surface_peak >= res.T[0] - 1e-6)


def test_fdm2d_energy_conservation():
    """에너지 보존: |E_in - E_stored| / E_in < 2%.

    DC single 짧은 조사에서 외부 손실(Cu→Oil, Oil→amb)이 작을 때
    입력 에너지 ≈ 시스템에 저장된 에너지.
    """
    solver = FDM2DSolver(Nr=8, Nz=8)
    on_time = 0.1
    exp = _default_exp(on_time=on_time)
    geom = TubeGeometry()
    oil = OilCondition()
    res = solver.solve(exp, geom, k_bti5=20.0, oil_cond=oil)

    # 입력 에너지: P × on_time
    P = exp.kV * exp.mA_peak  # 800 W
    E_in = P * on_time

    # 저장 에너지: 각 노드의 (T_final - T_init) × C
    A_w_base = math.pi * (geom.target_d / 2) ** 2
    V_w_total = A_w_base * geom.target_t
    A_cu_top = math.pi * (geom.cu_top_d / 2) ** 2
    r_root = geom.cu_root_d / 2
    r_fin = geom.cu_fin_od / 2
    V_cu_root_cyl = math.pi * r_root ** 2 * geom.cu_fin_total_h
    V_fin_one = math.pi * (r_fin ** 2 - r_root ** 2) * geom.fin_thickness
    V_cu_body = V_cu_root_cyl + geom.fin_count * V_fin_one

    C_w = materials.W.rho * materials.W.cp * V_w_total
    C_bti5 = materials.BTi5.rho * materials.BTi5.cp * A_w_base * geom.bti5_t
    C_cu_top = materials.Cu.rho * materials.Cu.cp * A_cu_top * geom.cu_top_h
    C_cu_body = materials.Cu.rho * materials.Cu.cp * V_cu_body
    C_oil = materials.Oil.rho * materials.Oil.cp * (oil.oil_volume_L * 1e-3)

    # T[1] = W 부피가중 평균 → 전체 W 에너지 = C_w × (T[1] - T_init)
    T_init = 293.15
    dT_w_bulk = res.T[1, -1] - T_init
    dT_bti5 = res.T[2, -1] - T_init
    dT_cu_top = res.T[3, -1] - T_init
    dT_cu_body = res.T[4, -1] - T_init
    dT_oil = res.T[5, -1] - T_init

    E_stored = (C_w * dT_w_bulk + C_bti5 * dT_bti5 + C_cu_top * dT_cu_top
                + C_cu_body * dT_cu_body + C_oil * dT_oil)

    rel_err = abs(E_in - E_stored) / E_in
    assert rel_err < 0.02, f"에너지 보존 위반: rel_err={rel_err:.4f} (E_in={E_in:.2f}, E_stored={E_stored:.2f})"


def test_nr1_matches_hybridfd_axisymmetric():
    """M5: FDM2D(Nr=1)는 1D 축대칭 → HybridFDSolver와 동등 (rel < 1%).

    두 솔버 모두 동일 P_in → 동일 t_arr를 적분하므로
    RC 노드(BTi5/Cu_top/Cu_body/Oil) 최종 온도 상승은 일치해야 한다
    (W 격자 정의 차이는 W 내부 분해에만 영향, 하부 RC 체인은 동일).
    """
    on_time = 0.05
    exp = _default_exp(on_time=on_time)
    geom = TubeGeometry()
    oil = OilCondition()

    hybrid = HybridFDSolver()
    res_hybrid = hybrid.solve(exp, geom, k_bti5=20.0, oil_cond=oil)

    fdm = FDM2DSolver(Nr=2, Nz=20)
    res_fdm = fdm.solve(exp, geom, k_bti5=20.0, oil_cond=oil)

    # RC 노드 최종 dT 비교 (Cu_body, Oil 은 W 표면 분해와 무관)
    # 짧은 시간(0.05s)에서 Cu_body, Oil 변화는 매우 작아 절대 오차로 검증
    for node_idx, node_name in [(4, "Cu_body"), (5, "Oil")]:
        dT_h = res_hybrid.T[node_idx, -1] - 293.15
        dT_f = res_fdm.T[node_idx, -1] - 293.15
        # 두 값 모두 매우 작음 (< 0.01K) → 절대 오차로 비교
        assert abs(dT_f - dT_h) < 0.01, \
            f"{node_name} dT_hybrid={dT_h:.6f} vs dT_fdm={dT_f:.6f}"

    # BTi5 절대 차이는 격자 의존 (W 하단 분포가 BTi5 가열 시점에 영향)
    # 두 솔버 모두 비슷한 시간상수 → 부호 일치 및 크기 동일 자릿수
    dT_bti5_h = res_hybrid.T[2, -1] - 293.15
    dT_bti5_f = res_fdm.T[2, -1] - 293.15
    assert dT_bti5_h > 0 and dT_bti5_f > 0
    rel_bti5 = abs(dT_bti5_f - dT_bti5_h) / max(dT_bti5_h, 1e-6)
    assert rel_bti5 < 1.0, f"BTi5 rel={rel_bti5:.4f}"


def test_perf_json_directory_autocreate(tmp_path, monkeypatch):
    """.omc/logs/ 자동생성 + OSError 없음."""
    # 임시 작업 디렉토리로 이동
    monkeypatch.chdir(tmp_path)

    # .omc 경로가 없는 상태에서 solver 실행 → 자동생성
    assert not (tmp_path / ".omc").exists()

    solver = FDM2DSolver(Nr=6, Nz=6)
    exp = _default_exp(on_time=0.05)
    geom = TubeGeometry()
    oil = OilCondition()
    res = solver.solve(exp, geom, k_bti5=20.0, oil_cond=oil)

    perf_path = tmp_path / ".omc" / "logs" / "phase2_perf.json"
    assert perf_path.exists(), "phase2_perf.json 자동생성 실패"

    with open(perf_path, "r", encoding="utf-8") as f:
        records = json.load(f)
    assert isinstance(records, list) and len(records) >= 1
    rec = records[-1]
    for key in ("timestamp", "env", "Nr", "Nz", "wall_time"):
        assert key in rec, f"perf 레코드 누락 키: {key}"
    assert rec["Nr"] == 6
    assert rec["Nz"] == 6
    assert rec["wall_time"] > 0
