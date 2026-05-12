# Phase 2 2D-FDM 균일 직교 r-z 축대칭 격자 (US-2)
"""W 디스크 r-z 축대칭 균일 격자 빌더.

R_W: W 타겟 반경 (TubeGeometry.target_d / 2)
target_t: W 타겟 두께

vertex-centered 격자 (노드 = 셀 중심):
  - r_centers = [0, dr, 2dr, ..., R_W], dr = R_W/(Nr-1)
  - 셀 컨트롤 볼륨 = 노드 둘레 [r_i-dr/2, r_i+dr/2] (경계 노드는 half-cell)
  - r=0 셀: [0, dr/2] 디스크 → V = π·(dr/2)²·Δz
  - r=R_W 셀: [R_W-dr/2, R_W] half-annulus
  - Σ V = π·R_W²·target_t (정확)

  - r=0 면의 radial face area = 0 (대칭축)
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple

import numpy as np

from geometry import TubeGeometry


@dataclass
class Grid:
    """균일 vertex-centered r-z 축대칭 격자.

    필드:
      r_centers: (Nr,) 셀 중심(=노드) r 좌표 [m], r_centers[0]=0, r_centers[-1]=R_W
      z_centers: (Nz,) 셀 중심(=노드) z 좌표 [m], z_centers[0]=0, z_centers[-1]=target_t
      r_edges:   (Nr+1,) 컨트롤 볼륨 경계 r 좌표 [m]
      z_edges:   (Nz+1,) 컨트롤 볼륨 경계 z 좌표 [m]
      cell_volumes: (Nr, Nz) 각 노드 컨트롤 볼륨 [m³]
      r_face_areas: (Nr+1, Nz) r 방향 face area [m²] (i = 셀 i의 내측 면)
      z_face_areas: (Nr, Nz+1) z 방향 face area [m²] (j = 셀 j의 하단 면)
      Nr, Nz: 노드(=셀) 수
      R_W: W 타겟 반경 [m]
      target_t: W 타겟 두께 [m]
    """

    r_centers: np.ndarray
    z_centers: np.ndarray
    r_edges: np.ndarray
    z_edges: np.ndarray
    cell_volumes: np.ndarray
    r_face_areas: np.ndarray
    z_face_areas: np.ndarray
    Nr: int
    Nz: int
    R_W: float
    target_t: float

    def to_nonuniform(self):
        """Option B 진화 stub (비균일 격자 전환 예정)."""
        raise NotImplementedError("Option B 진화 stub")


def build_grid(geom: TubeGeometry, Nr: int = 24, Nz: int = 20) -> Grid:
    """TubeGeometry로부터 균일 vertex-centered r-z 축대칭 격자 생성.

    Nr, Nz는 노드(=컨트롤 볼륨) 수. r_centers[0]=0, r_centers[-1]=R_W.
    dr = R_W/(Nr-1), dz = target_t/(Nz-1) (노드 간격).
    경계 노드(r=0, r=R_W, z=0, z=target_t)는 half-cell.
    """
    R_W = geom.target_d / 2.0
    target_t = geom.target_t

    r_centers = np.linspace(0.0, R_W, Nr)
    z_centers = np.linspace(0.0, target_t, Nz)
    dr = R_W / (Nr - 1)
    dz = target_t / (Nz - 1)

    # 컨트롤 볼륨 경계: 인접 노드 중점
    # r_edges[0]=0, r_edges[Nr]=R_W, 내부는 (r_centers[i-1]+r_centers[i])/2
    r_edges = np.empty(Nr + 1)
    r_edges[0] = 0.0
    r_edges[-1] = R_W
    r_edges[1:-1] = 0.5 * (r_centers[:-1] + r_centers[1:])

    z_edges = np.empty(Nz + 1)
    z_edges[0] = 0.0
    z_edges[-1] = target_t
    z_edges[1:-1] = 0.5 * (z_centers[:-1] + z_centers[1:])

    # 셀 단면적 (z-평면 투영): annulus 또는 r=0 디스크
    # r=0 셀: [0, dr/2] 디스크 → π·(dr/2)²
    # 그 외: π·(r_edges[i+1]² - r_edges[i]²)
    cell_areas = np.empty(Nr)
    cell_areas[0] = math.pi * r_edges[1] ** 2  # = π·(dr/2)²
    for i in range(1, Nr):
        cell_areas[i] = math.pi * (r_edges[i + 1] ** 2 - r_edges[i] ** 2)

    # z 방향 셀 폭: 경계 노드는 dz/2, 내부는 dz
    dz_per_cell = np.diff(z_edges)  # (Nz,)

    # 셀 부피: (Nr, Nz) = cell_areas[:, None] · dz_per_cell[None, :]
    cell_volumes = cell_areas[:, None] * dz_per_cell[None, :]

    # r 방향 face area: r_edges[i] 원통 측면 × z방향 셀 폭
    # A_r[i, j] = 2π·r_edges[i]·dz_per_cell[j]
    # r_edges[0] = 0 → A_r[0, :] = 0 (대칭축)
    r_face_areas = (2.0 * math.pi * r_edges)[:, None] * dz_per_cell[None, :]

    # z 방향 face area: z_edges 단면 = cell_areas (z 방향 균일)
    z_face_areas = np.tile(cell_areas[:, None], (1, Nz + 1))

    return Grid(
        r_centers=r_centers,
        z_centers=z_centers,
        r_edges=r_edges,
        z_edges=z_edges,
        cell_volumes=cell_volumes,
        r_face_areas=r_face_areas,
        z_face_areas=z_face_areas,
        Nr=Nr,
        Nz=Nz,
        R_W=R_W,
        target_t=target_t,
    )


def focal_mask(grid: Grid, focal_area: float) -> Tuple[np.ndarray, float]:
    """focal_area를 등가 원으로 변환한 r_f로부터 셀 마스크 생성.

    r_f² = focal_area / π  → r_f = sqrt(focal_area / π)
    반환: (mask[Nr] = r_centers < r_f, r_f)
    """
    r_f = math.sqrt(focal_area / math.pi)
    mask = grid.r_centers < r_f
    return mask, r_f
