import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import math
import numpy as np
import pytest
import materials
from geometry import TubeGeometry, focal_spot_area, fin_surface_area_total, thermal_resistances, thermal_capacities, MAX_T_EXPOSURE_SURFACE
from conditions import OilCondition


def test_focal_spot_area_spec_case():
    """스펙 케이스: L_eff=1.1mm, W_eff=0.75mm, 12° → ≈ 3.97e-6 m²."""
    A = focal_spot_area(1.1, 0.75, 12)
    assert abs(A - 3.97e-6) < 0.05e-6, f"focal_spot_area={A:.4e} (기대 3.97±0.05 e-6)"


def test_alpha_w():
    """alpha_W = k/(rho*cp) ≈ 6.54e-5 m²/s (±1%)."""
    a = materials.alpha(materials.W)
    assert abs(a - 6.54e-5) / 6.54e-5 < 0.01


def test_max_t_exposure_surface():
    """MAX_T_EXPOSURE_SURFACE ≈ 14 ms (±1 ms)."""
    assert abs(MAX_T_EXPOSURE_SURFACE - 0.014) < 0.001


def test_tube_geometry_defaults():
    g = TubeGeometry()
    assert len(g.fin_z_positions_mm) == 10
    assert g.target_d == pytest.approx(8.73e-3)
    assert g.target_t == pytest.approx(0.96e-3)
    assert g.cu_fin_total_h == pytest.approx(21.0e-3)


def test_fin_surface_area_reasonable():
    """핀 총 면적 > 50 cm² (bare cylinder 12.6 cm² 대비 충분한 향상)."""
    g = TubeGeometry()
    A = fin_surface_area_total(g)
    assert A > 50e-4, f"fin_area={A*1e4:.1f} cm² (기대 >50 cm²)"


def test_thermal_resistances_symmetry():
    """R 행렬은 대칭이고, R[0,1]은 inf (thermal_rc에서 채움)."""
    g = TubeGeometry()
    oil = OilCondition()
    R = thermal_resistances(g, k_bti5=20.0, oil_cond=oil)
    finite = np.isfinite(R)
    assert np.allclose(R[finite], R.T[finite])
    assert R[0, 1] == np.inf


def test_thermal_capacities_energy_conservation():
    """C[0]+C[1] = rho_W*cp_W*V_W_total (상대오차 < 1e-6)."""
    g = TubeGeometry()
    oil = OilCondition()
    A_spot = focal_spot_area(1.1, 0.75, 12)
    t_exp = min(0.001, MAX_T_EXPOSURE_SURFACE)   # 1 ms pulse case
    C = thermal_capacities(g, focal_area=A_spot, t_exp=t_exp, oil_cond=oil)
    V_W = math.pi * (g.target_d / 2) ** 2 * g.target_t
    C_w_ref = materials.W.rho * materials.W.cp * V_W
    assert abs(C[0] + C[1] - C_w_ref) / C_w_ref < 1e-6


def test_thermal_capacities_all_positive():
    """모든 열용량은 양수."""
    g = TubeGeometry()
    oil = OilCondition()
    A_spot = focal_spot_area(1.1, 0.75, 12)
    C = thermal_capacities(g, focal_area=A_spot, t_exp=0.001, oil_cond=oil)
    assert (C > 0).all(), f"음수 열용량 존재: {C}"


def test_bti5_k_sensitivity():
    """BTi-5 k=10/20/40 모두 정상 Material 반환."""
    for k in [10, 20, 40]:
        m = materials.bti5_with_k(k)
        assert m.k == k
        assert m.rho == materials.BTi5.rho


def test_fin_z_positions_consistency():
    """최상단 핀이 cu_fin_total_h를 초과해도 fin_surface_area_total이 양수 반환."""
    g = TubeGeometry()
    A = fin_surface_area_total(g)
    assert A > 0


def test_thermal_resistances_forced_vs_natural():
    """forced 모드(h_oil=200)는 natural(h_oil=50)보다 R[4,5]가 4배 작아야 함."""
    g = TubeGeometry()
    oil_nat = OilCondition(h_oil=50.0, convection_mode="natural")
    oil_frc = OilCondition(h_oil=200.0, convection_mode="forced")
    R_nat = thermal_resistances(g, k_bti5=20.0, oil_cond=oil_nat)
    R_frc = thermal_resistances(g, k_bti5=20.0, oil_cond=oil_frc)
    assert abs(R_nat[4, 5] / R_frc[4, 5] - 4.0) < 0.01, \
        f"R[4,5] 비율 = {R_nat[4,5]/R_frc[4,5]:.3f} (기대 4.0)"
