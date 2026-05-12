# Phase 2 2D-FDM 어셈블리: sparse Laplacian, conductance, RC 체인 결합 RHS (US-3)
"""W 2D FVM (Nr×Nz) + 4 RC 노드 (BTi5, Cu_top, Cu_body, Oil) 결합 RHS 빌더.

상태 벡터 레이아웃 (총 N = Nr·Nz + 4):
  T[0 : Nr·Nz]       W 셀 (row-major: index = i·Nz + j, (i, j) = (r, z))
  T[Nr·Nz + 0]       BTi5
  T[Nr·Nz + 1]       Cu_top
  T[Nr·Nz + 2]       Cu_body
  T[Nr·Nz + 3]       Oil

face conductance (직선 거리 G = k·A_face / Δ):
  G_r: (Nr-1, Nz)    셀 (i, j)와 (i+1, j) 사이 radial face (r-방향)
  G_z: (Nr, Nz-1)    셀 (i, j)와 (i, j+1) 사이 axial face (z-방향)

Laplacian: ∂T/∂t = (1/C_cell)·Σ G_face·(T_neighbor - T_cell)
  여기서 C_cell = ρ_W·cp_W·V_cell.

W ↔ BTi5: W 하단 (j = Nz-1) 노드 전체와 BTi5 단일 노드 사이 RC 저항 사용.
"""
from __future__ import annotations

from typing import Callable, Tuple

import numpy as np
from scipy.sparse import csr_matrix, lil_matrix

import materials
from conditions import OilCondition
from fdm2d_grid import Grid
from geometry import TubeGeometry, thermal_resistances


# 텅스텐 열전도율 [W/m·K] (materials.W.k 와 일치)
K_W_DEFAULT: float = materials.W.k  # 170 W/m·K (요구사항 표기 130은 일반 텅스텐 합금값으로, materials와 일치 우선)

# RC 노드 오프셋 (W 평면 다음 4개)
N_RC: int = 4
RC_BTI5: int = 0
RC_CU_TOP: int = 1
RC_CU_BODY: int = 2
RC_OIL: int = 3

T_AMBIENT_K: float = 293.15


# ---------------------------------------------------------------------------
# Conductance
# ---------------------------------------------------------------------------

def build_conductances(
    grid: Grid, k_w: float = None
) -> Tuple[np.ndarray, np.ndarray]:
    """Face conductance G = k·A_face / Δ 계산.

    G_r: (Nr-1, Nz)  셀 i와 i+1 사이 radial face
         A_face[i, j] = grid.r_face_areas[i+1, j]  (셀 i의 외측 면 = i+1의 내측 면)
         Δ[i] = r_centers[i+1] - r_centers[i]

    G_z: (Nr, Nz-1)  셀 j와 j+1 사이 axial face
         A_face[i, j] = grid.z_face_areas[i, j+1]  (셀 j의 상단 면 = j+1의 하단 면)
         Δ[j] = z_centers[j+1] - z_centers[j]
    """
    if k_w is None:
        k_w = K_W_DEFAULT

    Nr, Nz = grid.Nr, grid.Nz

    # G_r: (Nr-1, Nz)
    dr_pairs = np.diff(grid.r_centers)  # (Nr-1,)
    A_r = grid.r_face_areas[1:Nr, :]    # (Nr-1, Nz)  내부 face (i=1..Nr-1)
    G_r = k_w * A_r / dr_pairs[:, None]

    # G_z: (Nr, Nz-1)
    dz_pairs = np.diff(grid.z_centers)  # (Nz-1,)
    A_z = grid.z_face_areas[:, 1:Nz]    # (Nr, Nz-1)  내부 face (j=1..Nz-1)
    G_z = k_w * A_z / dz_pairs[None, :]

    return G_r, G_z


# ---------------------------------------------------------------------------
# Sparsity pattern
# ---------------------------------------------------------------------------

def build_jac_sparsity(grid: Grid, N_rc: int = N_RC) -> csr_matrix:
    """Jacobian sparsity pattern (5-point stencil + RC 체인 밀집 블록).

    크기: (Nr·Nz + N_rc) × (Nr·Nz + N_rc)
    W 영역: 각 행은 자기 자신 + 상하좌우 (최대 5개 nonzero)
    W ↔ BTi5: W 하단 (j = Nz-1) 노드 전체 ↔ BTi5 (양방향)
    RC 체인: BTi5-Cu_top-Cu_body-Oil 인접 결합 + Oil-ambient (대각)
            거기에 W 하단↔BTi5 결합 (이미 포함)
    """
    Nr, Nz = grid.Nr, grid.Nz
    N_w = Nr * Nz
    N = N_w + N_rc

    S = lil_matrix((N, N), dtype=np.int8)

    def idx(i: int, j: int) -> int:
        return i * Nz + j

    # W 5-point stencil
    for i in range(Nr):
        for j in range(Nz):
            k = idx(i, j)
            S[k, k] = 1
            if i > 0:
                S[k, idx(i - 1, j)] = 1
            if i < Nr - 1:
                S[k, idx(i + 1, j)] = 1
            if j > 0:
                S[k, idx(i, j - 1)] = 1
            if j < Nz - 1:
                S[k, idx(i, j + 1)] = 1

    bti5_row = N_w + RC_BTI5
    cu_top_row = N_w + RC_CU_TOP
    cu_body_row = N_w + RC_CU_BODY
    oil_row = N_w + RC_OIL

    # W bottom (j = Nz-1) ↔ BTi5 양방향
    for i in range(Nr):
        k = idx(i, Nz - 1)
        S[k, bti5_row] = 1
        S[bti5_row, k] = 1

    # RC 체인 인접 결합 (BTi5-Cu_top-Cu_body-Oil)
    for r in (bti5_row, cu_top_row, cu_body_row, oil_row):
        S[r, r] = 1
    S[bti5_row, cu_top_row] = 1
    S[cu_top_row, bti5_row] = 1
    S[cu_top_row, cu_body_row] = 1
    S[cu_body_row, cu_top_row] = 1
    S[cu_body_row, oil_row] = 1
    S[oil_row, cu_body_row] = 1
    # Oil → ambient 는 대각 (자기 자신만)

    return S.tocsr()


# ---------------------------------------------------------------------------
# RHS 어셈블리
# ---------------------------------------------------------------------------

def assemble_rhs(
    grid: Grid,
    G_r: np.ndarray,
    G_z: np.ndarray,
    focal_mask_1d: np.ndarray,
    k_bti5: float,
    oil_cond: OilCondition,
    P_at_t: Callable[[float], float],
    geom: TubeGeometry = None,
) -> Callable[[float, np.ndarray], np.ndarray]:
    """결합 RHS f(t, T) 빌더.

    인자:
      grid:           Grid (W 2D 격자)
      G_r, G_z:       face conductance
      focal_mask_1d:  (Nr,) bool, focal 영역 셀 마스크 (r-방향)
      k_bti5:         BTi-5 열전도율
      oil_cond:       OilCondition
      P_at_t:         t → P [W] callable
      geom:           TubeGeometry (None이면 기본값)

    반환:
      rhs(t, T) → dT/dt  ndarray (Nr·Nz + 4,)
    """
    if geom is None:
        geom = TubeGeometry()

    Nr, Nz = grid.Nr, grid.Nz
    N_w = Nr * Nz

    # W 셀 열용량 (개별)
    C_w_cells = materials.W.rho * materials.W.cp * grid.cell_volumes  # (Nr, Nz)
    C_w_flat = C_w_cells.flatten()  # row-major

    # focal 면적 (focal 셀들의 상면 면적 합; z=0 면)
    # z_face_areas[:, 0] = z=0 면 단면적 (Nr,)
    focal_top_areas = grid.z_face_areas[:, 0] * focal_mask_1d.astype(float)  # (Nr,)
    focal_area_total = float(np.sum(focal_top_areas))

    # focal 인덱스 (i, j=0) 평면 (z=0 면, focal_mask_1d 만족)
    focal_i_indices = np.where(focal_mask_1d)[0]

    # ---------------------------------------------------------------
    # W ↔ BTi5 conductance (전체 W 하면 → BTi5 단일 노드)
    # ---------------------------------------------------------------
    # 기존 RC 모델 R[1,2] = (target_t/2) / (k_W·A_w_base) + (bti5_t/2) / (k_bti5·A_w_base)
    # 여기서는 W 하단 셀 (j=Nz-1) → BTi5 단일 노드.
    # 각 W 하단 셀의 conductance: G_w_bti5_cell = 1 / R_cell
    # R_cell = (dz/2) / (k_W · A_cell_top) + (bti5_t/2) / (k_bti5 · A_cell_top)
    # 여기서 dz = z_centers[-1] - z_edges[-2] (셀 중심에서 하단면까지)
    dz_last_half = grid.z_edges[-1] - grid.z_centers[-1]  # 마지막 셀 중심에서 하단 경계까지
    # 단, 경계 셀 (j=Nz-1)은 half cell이므로 중심에서 경계까지 = dz/2
    # cell top area for bottom face = grid.z_face_areas[:, -1] (Nr,)
    A_bot = grid.z_face_areas[:, -1]  # (Nr,)
    # 각 W 하단 셀 → BTi5 face conductance
    # R = dz_last_half / (k_W * A_bot) + (bti5_t / 2) / (k_bti5 * A_bot)
    R_w_bti5_cells = (dz_last_half / (K_W_DEFAULT * A_bot)
                      + (geom.bti5_t / 2.0) / (k_bti5 * A_bot))
    G_w_bti5_cells = 1.0 / R_w_bti5_cells  # (Nr,)

    # ---------------------------------------------------------------
    # RC 노드 사이 저항 (기존 thermal_rc 로직 재사용)
    # ---------------------------------------------------------------
    R_rc = thermal_resistances(geom, k_bti5=k_bti5, oil_cond=oil_cond)
    # R_rc[2,3] = BTi5 ↔ Cu_top, R_rc[3,4] = Cu_top ↔ Cu_body, R_rc[4,5] = Cu_body ↔ Oil
    G_bti5_cu_top = 1.0 / R_rc[2, 3]
    G_cu_top_body = 1.0 / R_rc[3, 4]
    G_cu_body_oil = 1.0 / R_rc[4, 5]

    # Oil → ambient
    A_oil_top = (oil_cond.vessel_w_cm / 100.0) * (oil_cond.vessel_d_cm / 100.0)
    G_oil_amb = oil_cond.h_oil_air * A_oil_top  # = 1 / R_to_amb

    # ---------------------------------------------------------------
    # RC 노드 열용량
    # ---------------------------------------------------------------
    import math
    A_w_base = math.pi * (geom.target_d / 2) ** 2
    A_cu_top = math.pi * (geom.cu_top_d / 2) ** 2
    r_root = geom.cu_root_d / 2
    r_fin = geom.cu_fin_od / 2
    V_cu_root_cyl = math.pi * r_root ** 2 * geom.cu_fin_total_h
    V_fin_one = math.pi * (r_fin ** 2 - r_root ** 2) * geom.fin_thickness
    V_cu_body = V_cu_root_cyl + geom.fin_count * V_fin_one

    C_bti5 = materials.BTi5.rho * materials.BTi5.cp * A_w_base * geom.bti5_t
    C_cu_top = materials.Cu.rho * materials.Cu.cp * A_cu_top * geom.cu_top_h
    C_cu_body = materials.Cu.rho * materials.Cu.cp * V_cu_body
    C_oil = materials.Oil.rho * materials.Oil.cp * (oil_cond.oil_volume_L * 1e-3)
    C_rc = np.array([C_bti5, C_cu_top, C_cu_body, C_oil])

    # 평탄화 인덱스 헬퍼
    def flat_idx(i: int, j: int) -> int:
        return i * Nz + j

    # 하단 W 셀 (j = Nz-1) 인덱스 배열
    bottom_w_indices = np.array([flat_idx(i, Nz - 1) for i in range(Nr)])

    def rhs(t: float, T: np.ndarray) -> np.ndarray:
        # 상태 분리
        T_w = T[:N_w].reshape(Nr, Nz)
        T_bti5 = T[N_w + RC_BTI5]
        T_cu_top = T[N_w + RC_CU_TOP]
        T_cu_body = T[N_w + RC_CU_BODY]
        T_oil = T[N_w + RC_OIL]

        # Net heat flow into each W cell [W]
        Qw = np.zeros((Nr, Nz))

        # r-방향 face: 셀 (i, j) ↔ (i+1, j), G_r shape (Nr-1, Nz)
        flux_r = G_r * (T_w[1:Nr, :] - T_w[0:Nr - 1, :])  # (Nr-1, Nz), + 이면 (i+1)→(i) 흐름은 -, (i)→(i+1) 흐름은 ...
        # flux_r[i, j] = G·(T[i+1]-T[i]) = heat into cell i (from i+1)
        Qw[0:Nr - 1, :] += flux_r       # 셀 i: + (T[i+1]-T[i])·G
        Qw[1:Nr, :] -= flux_r           # 셀 i+1: + (T[i]-T[i+1])·G = -flux_r

        # z-방향 face: G_z shape (Nr, Nz-1)
        flux_z = G_z * (T_w[:, 1:Nz] - T_w[:, 0:Nz - 1])
        Qw[:, 0:Nz - 1] += flux_z
        Qw[:, 1:Nz] -= flux_z

        # W 하단 → BTi5 (j = Nz-1 셀 전체)
        flux_w_bti5 = G_w_bti5_cells * (T_bti5 - T_w[:, Nz - 1])  # (Nr,)
        Qw[:, Nz - 1] += flux_w_bti5

        # focal 가열 (z=0 면, focal 영역)
        P_now = P_at_t(t)
        if focal_area_total > 0.0:
            q_flux = P_now / focal_area_total  # [W/m²]
            # 각 focal 셀에 q_flux · A_top 만큼 입사 (j=0 면)
            for i in focal_i_indices:
                Qw[i, 0] += q_flux * grid.z_face_areas[i, 0]

        # W dT/dt
        dT_w = (Qw / C_w_cells).flatten()

        # RC 노드 dT/dt
        # BTi5: -Σ flux_w_bti5 (BTi5 측에서 보면 W로 빠져나가는 양 = -flux_w_bti5 합) + (T_cu_top - T_bti5)·G
        Q_bti5 = -float(np.sum(flux_w_bti5)) \
                 + G_bti5_cu_top * (T_cu_top - T_bti5)
        Q_cu_top = G_bti5_cu_top * (T_bti5 - T_cu_top) \
                   + G_cu_top_body * (T_cu_body - T_cu_top)
        Q_cu_body = G_cu_top_body * (T_cu_top - T_cu_body) \
                    + G_cu_body_oil * (T_oil - T_cu_body)
        Q_oil = G_cu_body_oil * (T_cu_body - T_oil) \
                + G_oil_amb * (T_AMBIENT_K - T_oil)

        dT_rc = np.array([Q_bti5, Q_cu_top, Q_cu_body, Q_oil]) / C_rc

        return np.concatenate([dT_w, dT_rc])

    return rhs
