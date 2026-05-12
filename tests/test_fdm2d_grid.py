# US-2 균일 r-z 축대칭 격자 단위 테스트
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import math
import numpy as np
import numpy.testing as npt
import pytest

from geometry import TubeGeometry, focal_spot_area
from fdm2d_grid import Grid, build_grid, focal_mask


def test_grid_dimensions():
    """격자 배열 shape 검증."""
    g = build_grid(TubeGeometry(), Nr=24, Nz=20)
    assert g.Nr == 24
    assert g.Nz == 20
    assert g.r_centers.shape == (24,)
    assert g.z_centers.shape == (20,)
    assert g.r_edges.shape == (25,)
    assert g.z_edges.shape == (21,)
    assert g.cell_volumes.shape == (24, 20)
    assert g.r_face_areas.shape == (25, 20)
    assert g.z_face_areas.shape == (24, 21)


def test_cell_volumes_sum_to_total():
    """Σ V = π·R_W²·target_t (rel < 1e-12)."""
    geom = TubeGeometry()
    g = build_grid(geom, Nr=24, Nz=20)
    V_total_expected = math.pi * g.R_W ** 2 * g.target_t
    V_total_actual = float(np.sum(g.cell_volumes))
    npt.assert_allclose(V_total_actual, V_total_expected, rtol=1e-12)


def test_axis_cell_volume():
    """r=0 셀 단면 부피 = π·(Δr/2)²·Δz (디스크 일관성)."""
    geom = TubeGeometry()
    Nr, Nz = 24, 20
    g = build_grid(geom, Nr=Nr, Nz=Nz)
    dr = g.R_W / (Nr - 1)
    # z=0, z=target_t 경계 셀은 half (dz/2), 내부 셀은 dz
    dz_interior = g.target_t / (Nz - 1)
    V_axis_interior = math.pi * (dr / 2.0) ** 2 * dz_interior
    V_axis_boundary = math.pi * (dr / 2.0) ** 2 * (dz_interior / 2.0)
    # z=0, z=target_t에서 half-cell
    npt.assert_allclose(g.cell_volumes[0, 0], V_axis_boundary, rtol=1e-12)
    npt.assert_allclose(g.cell_volumes[0, -1], V_axis_boundary, rtol=1e-12)
    # 내부 z 위치에서 full cell
    for j in range(1, Nz - 1):
        npt.assert_allclose(g.cell_volumes[0, j], V_axis_interior, rtol=1e-12)


def test_axis_radial_face_area():
    """r=0 셀의 내측 radial face area = 0 (대칭축)."""
    g = build_grid(TubeGeometry(), Nr=24, Nz=20)
    # r_edges[0] = 0 이므로 face_areas[0, :] = 0
    npt.assert_array_equal(g.r_face_areas[0, :], np.zeros(g.Nz))


def test_focal_equivalent_radius():
    """focal_mask: r_f² = focal_area / π."""
    geom = TubeGeometry()
    g = build_grid(geom, Nr=24, Nz=20)
    A_spot = focal_spot_area(1.1, 0.75, 12)
    mask, r_f = focal_mask(g, A_spot)
    npt.assert_allclose(r_f ** 2, A_spot / math.pi, rtol=1e-12)
    # 마스크 길이 및 단조성 검증 (r 작은 셀만 True)
    assert mask.shape == (g.Nr,)
    assert mask.dtype == bool
    # mask가 True인 셀의 r_centers는 모두 r_f 미만
    assert np.all(g.r_centers[mask] < r_f)
    # mask가 False인 셀의 r_centers는 모두 r_f 이상
    assert np.all(g.r_centers[~mask] >= r_f)


def test_to_nonuniform_stub():
    """to_nonuniform()은 NotImplementedError 반환."""
    g = build_grid(TubeGeometry(), Nr=24, Nz=20)
    with pytest.raises(NotImplementedError):
        g.to_nonuniform()
