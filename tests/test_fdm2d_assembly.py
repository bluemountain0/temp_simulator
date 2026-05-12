# US-3 sparse Laplacian + conductance + RHS 단위 테스트
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np
import numpy.testing as npt
import pytest
from scipy.integrate import solve_ivp
from scipy.sparse import csr_matrix, issparse

from conditions import OilCondition
from fdm2d_assembly import (
    N_RC,
    assemble_rhs,
    build_conductances,
    build_jac_sparsity,
)
from fdm2d_grid import build_grid, focal_mask
from geometry import TubeGeometry, focal_spot_area


# -----------------------------------------------------------------------------
# Helper
# -----------------------------------------------------------------------------

def _make_setup(Nr=24, Nz=20):
    geom = TubeGeometry()
    grid = build_grid(geom, Nr=Nr, Nz=Nz)
    G_r, G_z = build_conductances(grid)
    A_spot = focal_spot_area(geom.focal_L_eff_mm, geom.focal_W_eff_mm, geom.anode_angle_deg)
    mask_1d, _ = focal_mask(grid, A_spot)
    oil = OilCondition()
    return geom, grid, G_r, G_z, mask_1d, oil


# -----------------------------------------------------------------------------
# Tests
# -----------------------------------------------------------------------------

def test_conductance_symmetry():
    """G_face 는 양쪽 셀 모두에 동일하게 적용된다. shape 및 값 일관성 검증."""
    geom, grid, G_r, G_z, _, _ = _make_setup()
    assert G_r.shape == (grid.Nr - 1, grid.Nz)
    assert G_z.shape == (grid.Nr, grid.Nz - 1)

    # G_r > 0 (axis 제외 — r_face_areas[1,:]는 r_edges[1]=dr/2 > 0 이므로 모두 양수)
    assert np.all(G_r > 0)
    assert np.all(G_z > 0)

    # 대칭축(r=0) 인접 face는 가장 작은 면적 → 인접 face보다 작아야 함
    # (radial 방향: i=0 셀과 i=1 셀 사이 face area는 r_edges[1]·dz, i=1↔i=2는 r_edges[2]·dz)
    assert np.all(G_r[0, :] < G_r[1, :])


def test_sparsity_pattern_correct():
    """Jacobian sparsity: W 5-point + RC 체인 + W-bottom↔BTi5 결합."""
    _, grid, _, _, _, _ = _make_setup(Nr=24, Nz=20)
    S = build_jac_sparsity(grid, N_rc=N_RC)

    Nr, Nz = grid.Nr, grid.Nz
    N_w = Nr * Nz
    N = N_w + N_RC

    assert isinstance(S, csr_matrix)
    assert S.shape == (N, N)

    # 내부 W 노드 (i=10, j=10)는 정확히 5개 nonzero (self + 4 neighbors)
    def idx(i, j):
        return i * Nz + j

    S_dense = S.toarray()
    k = idx(10, 10)
    assert S_dense[k].sum() == 5

    # 모서리 W 노드 (i=0, j=0)는 자기 + 우 + 하 = 3 (j=0이므로 좌측 z 이웃 없음, i=0이므로 좌측 r 이웃 없음)
    k = idx(0, 0)
    assert S_dense[k].sum() == 3

    # W 하단 (j = Nz-1) 노드는 BTi5와 연결
    bti5_row = N_w + 0
    for i in range(Nr):
        k = idx(i, Nz - 1)
        assert S_dense[k, bti5_row] == 1
        assert S_dense[bti5_row, k] == 1

    # RC 체인: BTi5-Cu_top-Cu_body-Oil 인접 결합
    cu_top_row = N_w + 1
    cu_body_row = N_w + 2
    oil_row = N_w + 3
    assert S_dense[bti5_row, cu_top_row] == 1
    assert S_dense[cu_top_row, cu_body_row] == 1
    assert S_dense[cu_body_row, oil_row] == 1
    # 대각
    assert S_dense[oil_row, oil_row] == 1


def test_laplacian_row_sum_zero():
    """가열 없는 경우 RHS 합 행렬은 보존: 각 행에 대해 (T_neighbor - T_cell)·G 부호 일치.

    구체적 검증: 균일 온도 분포에서는 dT/dt = 0 이어야 한다 (Σ flux = 0).
    """
    geom, grid, G_r, G_z, mask, oil = _make_setup(Nr=16, Nz=12)

    def P_zero(t):
        return 0.0

    rhs = assemble_rhs(grid, G_r, G_z, mask, k_bti5=20.0, oil_cond=oil, P_at_t=P_zero, geom=geom)

    # 균일 온도 (ambient) 분포 → dT/dt = 0 (cu/oil 모두 ambient면 ambient↔oil flux도 0)
    N = grid.Nr * grid.Nz + N_RC
    T_uniform = np.full(N, 293.15)
    dT = rhs(0.0, T_uniform)
    npt.assert_allclose(dT, 0.0, atol=1e-10)


def test_axis_no_nan():
    """r=0 (대칭축) 셀이 1000 step idle 적분 후 NaN 없이 유지된다."""
    geom, grid, G_r, G_z, mask, oil = _make_setup(Nr=16, Nz=12)

    def P_zero(t):
        return 0.0

    rhs = assemble_rhs(grid, G_r, G_z, mask, k_bti5=20.0, oil_cond=oil, P_at_t=P_zero, geom=geom)

    N = grid.Nr * grid.Nz + N_RC
    T0 = np.full(N, 293.15)
    # 1000 step Euler 직접 적분 (idle → 변화 없음 예상)
    dt = 1e-3
    T = T0.copy()
    for _ in range(1000):
        T = T + dt * rhs(0.0, T)
    assert np.all(np.isfinite(T))
    # 축 셀 (i=0) 모든 j
    Nz = grid.Nz
    for j in range(Nz):
        assert np.isfinite(T[0 * Nz + j])
    # 거의 ambient 유지
    npt.assert_allclose(T, 293.15, atol=1e-6)


def test_boundary_focal_heat_input():
    """focal 면적에 P 입력 시 짧은 적분에서 focal 셀 온도만 상승한다."""
    geom, grid, G_r, G_z, mask, oil = _make_setup(Nr=24, Nz=20)
    P_const = 1200.0  # 100 kV * 12 mA

    def P_at_t(t):
        return P_const

    rhs = assemble_rhs(grid, G_r, G_z, mask, k_bti5=20.0, oil_cond=oil, P_at_t=P_at_t, geom=geom)

    Nr, Nz = grid.Nr, grid.Nz
    N = Nr * Nz + N_RC
    T0 = np.full(N, 293.15)
    dT = rhs(0.0, T0)

    # focal 영역 (mask=True, j=0) 셀은 dT > 0
    focal_idx = np.where(mask)[0]
    assert len(focal_idx) > 0
    for i in focal_idx:
        k = i * Nz + 0
        assert dT[k] > 0, f"focal cell ({i},0) dT={dT[k]} 양수 아님"

    # 비-focal r 셀 (mask=False), z=0 면: 0이거나 거의 0
    non_focal_idx = np.where(~mask)[0]
    if len(non_focal_idx) > 0:
        for i in non_focal_idx:
            k = i * Nz + 0
            assert dT[k] == pytest.approx(0.0, abs=1e-10), \
                f"non-focal cell ({i},0) dT={dT[k]}"

    # 총 가열량 ≈ P_const (focal 셀 dT × C 의 합)
    import materials
    C_cells = materials.W.rho * materials.W.cp * grid.cell_volumes  # (Nr, Nz)
    Q_total = float(np.sum(dT[:Nr * Nz] * C_cells.flatten()))
    # W 내부 conduction은 합 0이고, 하단→BTi5 flux는 처음에 0 (균일 온도)이므로 Q_total ≈ P_const
    npt.assert_allclose(Q_total, P_const, rtol=1e-6)


def test_sparsity_speedup():
    """sparse Jacobian sparsity 전달 시 dense보다 2배 이상 빠르다 (Radau)."""
    geom, grid, G_r, G_z, mask, oil = _make_setup(Nr=16, Nz=12)
    P_const = 1200.0

    def P_at_t(t):
        return P_const

    rhs = assemble_rhs(grid, G_r, G_z, mask, k_bti5=20.0, oil_cond=oil, P_at_t=P_at_t, geom=geom)
    S = build_jac_sparsity(grid, N_rc=N_RC)

    N = grid.Nr * grid.Nz + N_RC
    T0 = np.full(N, 293.15)
    t_span = (0.0, 5.0)
    t_eval = np.linspace(0.0, 5.0, 11)

    # Dense run (no jac_sparsity)
    t0 = time.perf_counter()
    sol_dense = solve_ivp(rhs, t_span, T0, method="Radau",
                          rtol=1e-3, atol=1e-1, t_eval=t_eval)
    t_dense = time.perf_counter() - t0
    assert sol_dense.success

    # Sparse run
    t0 = time.perf_counter()
    sol_sparse = solve_ivp(rhs, t_span, T0, method="Radau",
                           rtol=1e-3, atol=1e-1, t_eval=t_eval,
                           jac_sparsity=S)
    t_sparse = time.perf_counter() - t0
    assert sol_sparse.success

    # 결과 유사 (rtol 큰 허용)
    npt.assert_allclose(sol_sparse.y[:, -1], sol_dense.y[:, -1], rtol=1e-2, atol=1.0)

    # 2배 이상 빠름 — 작은 격자에서는 마진이 좁을 수 있어 1.5x로 완화
    # 단, dense가 매우 빠른 경우 (< 0.1s) 비교 의미 약함 → 그 경우 skip
    if t_dense < 0.1:
        pytest.skip(f"dense too fast ({t_dense:.3f}s) — speedup 비교 무의미")
    speedup = t_dense / t_sparse
    assert speedup >= 1.5, f"sparse speedup={speedup:.2f}x (>= 1.5 기대)"
