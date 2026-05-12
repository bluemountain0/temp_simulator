import math
from dataclasses import dataclass
from typing import Callable, Tuple

import numpy as np
from scipy.integrate import solve_ivp

import materials
from conditions import ExposureCondition, OilCondition
from geometry import (
    TubeGeometry, focal_spot_area,
    thermal_resistances, thermal_capacities,
)
from waveform import build_power_trace

# 노드 인덱스
NODE_W_SURFACE = 0
NODE_W_BULK    = 1
NODE_BTI5      = 2
NODE_CU_TOP    = 3
NODE_CU_BODY   = 4
NODE_OIL       = 5
NODE_NAMES = ["W_surf", "W_bulk", "BTi5", "Cu_top", "Cu_body", "Oil"]

T_AMBIENT_K: float = 293.15

# W 표면 유효 열확산 시간 상한 [s]
# delta = sqrt(alpha_W * t) 가 W 반두께를 초과하는 시점: target_t² / alpha_W
MAX_T_EXPOSURE_SURFACE: float = (0.96e-3) ** 2 / (170 / (19250 * 135))


@dataclass
class _SolveOutput:
    t: np.ndarray
    T: np.ndarray
    T_w_surface_peak: np.ndarray
    ambient_K: float
    node_names: list


def effective_t_exposure(exp: ExposureCondition) -> float:
    """delta_eff 계산용 단일 on-duration [s], MAX_T_EXPOSURE_SURFACE 상한 적용."""
    if exp.mode == "pulse" and exp.freq_hz > 0:
        t_on = exp.duty / exp.freq_hz
    else:
        t_on = exp.on_time
    return min(t_on, MAX_T_EXPOSURE_SURFACE)


def effective_delta(t_exp: float, geom: TubeGeometry) -> float:
    """열확산 깊이 [m], 반두께 상한 클램프."""
    alpha_W = materials.alpha(materials.W)
    return min(math.sqrt(alpha_W * t_exp), 0.5 * geom.target_t)


def build_rc_matrices(
    geom: TubeGeometry,
    focal_area: float,
    t_exp: float,
    k_bti5: float,
    oil_cond: OilCondition,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(R[6,6], C[6], R_to_amb[6]) 반환.

    geometry.thermal_resistances()의 R[0,1]=inf를 delta_eff 기반 값으로 채운다.
    """
    delta_eff = effective_delta(t_exp, geom)

    R = thermal_resistances(geom, k_bti5=k_bti5, oil_cond=oil_cond)
    # R[0,1]: W 표면 → W bulk (focal spot 단면, 잔여 두께)
    remaining_t = geom.target_t - delta_eff   # >= 0.5 * target_t
    r01 = remaining_t / (materials.W.k * focal_area)
    R[0, 1] = R[1, 0] = r01

    C = thermal_capacities(geom, focal_area=focal_area, t_exp=t_exp, oil_cond=oil_cond)

    # Ambient boundary: 절연유 표면 → ambient
    R_to_amb = np.full(6, np.inf)
    A_oil_top = (oil_cond.vessel_w_cm / 100.0) * (oil_cond.vessel_d_cm / 100.0)
    R_to_amb[NODE_OIL] = 1.0 / (oil_cond.h_oil_air * A_oil_top)

    return R, C, R_to_amb


def _make_rhs(
    R: np.ndarray,
    C: np.ndarray,
    R_to_amb: np.ndarray,
    P_at_t: Callable,
) -> Callable:
    """R_inv/C_inv 사전 계산 후 ODE RHS 클로저 반환."""
    R_inv = np.where(np.isfinite(R), 1.0 / R, 0.0)
    np.fill_diagonal(R_inv, 0.0)
    R_amb_inv = np.where(np.isfinite(R_to_amb), 1.0 / R_to_amb, 0.0)
    C_inv = 1.0 / C

    def rhs(t: float, T: np.ndarray) -> np.ndarray:
        # 노드 간 열유속: q[i] = Σ_j (T[j]-T[i]) / R[i,j]
        T_diff = T[np.newaxis, :] - T[:, np.newaxis]
        q_nodes = np.sum(T_diff * R_inv, axis=1)
        # Ambient 경계
        q_amb = (T_AMBIENT_K - T) * R_amb_inv
        # W 표면 가열
        Q = np.zeros(6)
        Q[NODE_W_SURFACE] = P_at_t(t)
        return (q_nodes + q_amb + Q) * C_inv

    return rhs


def solve_rc(
    exp: ExposureCondition,
    geom: TubeGeometry,
    k_bti5: float,
    oil_cond: OilCondition,
    T_init: float = T_AMBIENT_K,
) -> _SolveOutput:
    """6-state lumped RC ODE를 Radau로 적분. ambient는 boundary condition."""
    t_exp = effective_t_exposure(exp)
    focal_area = focal_spot_area(
        geom.focal_L_eff_mm, geom.focal_W_eff_mm, geom.anode_angle_deg
    )

    R, C, R_to_amb = build_rc_matrices(geom, focal_area, t_exp, k_bti5, oil_cond)
    t_arr, P_arr, meta = build_power_trace(exp)

    P_at_t = lambda tq: float(np.interp(tq, t_arr, P_arr))
    rhs = _make_rhs(R, C, R_to_amb, P_at_t)

    y0 = np.full(6, float(T_init))
    t_span = (float(t_arr[0]), float(t_arr[-1]))

    sol = solve_ivp(
        rhs, t_span, y0,
        method="Radau",
        rtol=1e-4,
        atol=1e-2,
        t_eval=t_arr,
    )
    assert sol.success, f"ODE solver 실패: {sol.message}"

    T_result = sol.y   # (6, N)
    t_result = sol.t   # (N,)

    # 고주파 pulse W 표면 peak 보정
    T_w_surface_peak = T_result[NODE_W_SURFACE].copy()
    if (exp.mode == "pulse" and exp.freq_hz > 10
            and meta["peak_envelope"] is not None):
        alpha_W = materials.alpha(materials.W)
        t_on_pulse = meta["t_exp_per_pulse"]
        t_exp_p = min(t_on_pulse, MAX_T_EXPOSURE_SURFACE)
        delta_p = min(math.sqrt(alpha_W * t_exp_p), 0.5 * geom.target_t)
        q_peak = float(meta["peak_envelope"][0]) / focal_area
        dT_pulse = (q_peak * t_exp_p
                    / (materials.W.rho * materials.W.cp * delta_p))
        T_w_surface_peak = T_result[NODE_W_SURFACE] + dT_pulse

    return _SolveOutput(
        t=t_result,
        T=T_result,
        T_w_surface_peak=T_w_surface_peak,
        ambient_K=T_AMBIENT_K,
        node_names=NODE_NAMES,
    )
