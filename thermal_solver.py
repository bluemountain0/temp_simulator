import math
from abc import ABC, abstractmethod
from dataclasses import dataclass

import numpy as np
from scipy.integrate import solve_ivp

from conditions import ExposureCondition, OilCondition
from geometry import TubeGeometry


@dataclass
class ThermalResult:
    t: np.ndarray                # (N,) 시간 [s]
    T: np.ndarray                # (6, N) 노드 온도 [K]
    T_w_surface_peak: np.ndarray # (N,) W 표면 peak (pulse 보정 포함) [K]
    ambient_K: float             # boundary 온도 [K]
    node_names: list             # 노드 이름 6개


class IThermalSolver(ABC):
    @abstractmethod
    def solve(
        self,
        exp: ExposureCondition,
        geom: TubeGeometry,
        k_bti5: float,
        oil_cond: OilCondition,
        T_init: float = 293.15,
    ) -> ThermalResult: ...


class RCSolver(IThermalSolver):
    """6-state 집중 RC ODE 솔버 (ambient boundary). Phase 1.0a."""

    def solve(self, exp, geom, k_bti5, oil_cond, T_init=293.15) -> ThermalResult:
        import thermal_rc
        raw = thermal_rc.solve_rc(exp, geom, k_bti5, oil_cond, T_init)
        return ThermalResult(
            t=raw.t, T=raw.T,
            T_w_surface_peak=raw.T_w_surface_peak,
            ambient_K=raw.ambient_K, node_names=raw.node_names,
        )


class HybridFDSolver(IThermalSolver):
    """W disk 1D-FD (focal spot 단면) + BTi5/Cu/Oil 집중 RC. Phase 1.0b.

    W 표면 온도를 정확히 예측하기 위해 W 슬랩을 N_W개의 FD 노드로 분해.
    하부 RC 체인은 RCSolver와 동일.
    """

    N_W: int = 20  # W 슬랩 FD 노드 수

    def solve(self, exp, geom, k_bti5, oil_cond, T_init=293.15) -> ThermalResult:
        import thermal_rc
        import materials
        from geometry import focal_spot_area, fin_surface_area_total
        from waveform import build_power_trace

        N = self.N_W
        dz = geom.target_t / N
        focal_area = focal_spot_area(
            geom.focal_L_eff_mm, geom.focal_W_eff_mm, geom.anode_angle_deg
        )

        # 기하 면적
        A_w_base = math.pi * (geom.target_d / 2) ** 2
        A_cu_top = math.pi * (geom.cu_top_d / 2) ** 2
        A_cu_root = math.pi * (geom.cu_root_d / 2) ** 2
        A_oil_top = (oil_cond.vessel_w_cm / 100.0) * (oil_cond.vessel_d_cm / 100.0)
        A_fin = fin_surface_area_total(geom)
        r_root = geom.cu_root_d / 2
        r_fin = geom.cu_fin_od / 2

        # 열용량 [J/K]
        C_W_node = materials.W.rho * materials.W.cp * focal_area * dz
        C_BTi5 = materials.BTi5.rho * materials.BTi5.cp * A_w_base * geom.bti5_t
        C_cu_top = materials.Cu.rho * materials.Cu.cp * A_cu_top * geom.cu_top_h
        V_cu_body = (math.pi * r_root ** 2 * geom.cu_fin_total_h
                     + geom.fin_count * math.pi * (r_fin**2 - r_root**2) * geom.fin_thickness)
        C_cu_body = materials.Cu.rho * materials.Cu.cp * V_cu_body
        C_oil = materials.Oil.rho * materials.Oil.cp * (oil_cond.oil_volume_L * 1e-3)

        # 열저항 [K/W]
        # W 하단 노드 → BTi5 (W 측: A_spot, BTi5 측: A_w_base)
        R_W_BTi5 = ((dz / 2) / (materials.W.k * focal_area)
                    + (geom.bti5_t / 2) / (k_bti5 * A_w_base))
        R_BTi5_Cu = ((geom.bti5_t / 2) / (k_bti5 * A_w_base)
                     + (geom.cu_top_h / 2) / (materials.Cu.k * A_cu_top))
        R_Cu_top_body = ((geom.cu_top_h / 2) / (materials.Cu.k * A_cu_top)
                         + (geom.cu_fin_total_h / 2) / (materials.Cu.k * A_cu_root))
        R_Cu_oil = 1.0 / (oil_cond.h_oil * A_fin)
        R_oil_amb = 1.0 / (oil_cond.h_oil_air * A_oil_top)

        # W FD 인접 노드 간 열전도 [W/K]
        G_int = materials.W.k * focal_area / dz

        # 역용량 (RHS 계산용)
        C_inv_W = 1.0 / C_W_node  # 모든 W 노드 동일
        C_inv_rc = 1.0 / np.array([C_BTi5, C_cu_top, C_cu_body, C_oil])

        T_AMB = thermal_rc.T_AMBIENT_K
        t_arr, P_arr, meta = build_power_trace(exp)
        P_at_t = lambda tq: float(np.interp(tq, t_arr, P_arr))

        def rhs(t: float, y: np.ndarray) -> np.ndarray:
            T_W = y[:N]
            T_rc = y[N:]   # [BTi5, Cu_top, Cu_body, Oil]
            P_in = P_at_t(t)

            dy = np.empty_like(y)

            # W FD: 상단 노드 (열 입력 + 하단으로 전도)
            q_to_BTi5 = (T_W[N - 1] - T_rc[0]) / R_W_BTi5

            dy[0] = (P_in + G_int * (T_W[1] - T_W[0])) * C_inv_W
            # 중간 노드 (벡터화)
            dy[1:N - 1] = G_int * (T_W[:-2] + T_W[2:] - 2 * T_W[1:-1]) * C_inv_W
            # 하단 노드
            dy[N - 1] = (G_int * (T_W[N - 2] - T_W[N - 1]) - q_to_BTi5) * C_inv_W

            # RC 노드
            q_BTi5_Cu = (T_rc[0] - T_rc[1]) / R_BTi5_Cu
            q_Cu_body = (T_rc[1] - T_rc[2]) / R_Cu_top_body
            q_Cu_oil  = (T_rc[2] - T_rc[3]) / R_Cu_oil
            q_oil_amb = (T_rc[3] - T_AMB) / R_oil_amb

            dy[N]     = (q_to_BTi5 - q_BTi5_Cu) * C_inv_rc[0]
            dy[N + 1] = (q_BTi5_Cu - q_Cu_body)  * C_inv_rc[1]
            dy[N + 2] = (q_Cu_body  - q_Cu_oil)   * C_inv_rc[2]
            dy[N + 3] = (q_Cu_oil   - q_oil_amb)  * C_inv_rc[3]

            return dy

        y0 = np.full(N + 4, float(T_init))
        t_span = (float(t_arr[0]), float(t_arr[-1]))

        sol = solve_ivp(rhs, t_span, y0, method="Radau", rtol=1e-4, atol=1e-2,
                        t_eval=t_arr)
        assert sol.success, f"HybridFD ODE 실패: {sol.message}"

        # 6-노드 ThermalResult 매핑
        T6 = np.zeros((6, sol.y.shape[1]))
        T6[0] = sol.y[0]                         # W 표면 = FD 최상단 노드
        T6[1] = np.mean(sol.y[:N], axis=0)       # W bulk ≈ FD 노드 평균
        T6[2] = sol.y[N]                          # BTi5
        T6[3] = sol.y[N + 1]                      # Cu_top
        T6[4] = sol.y[N + 2]                      # Cu_body
        T6[5] = sol.y[N + 3]                      # Oil

        # 고주파 pulse peak 보정 (RC와 동일 방식)
        T_w_surface_peak = T6[0].copy()
        if (exp.mode == "pulse" and exp.freq_hz > 10
                and meta["peak_envelope"] is not None):
            alpha_W = materials.alpha(materials.W)
            t_on_p = meta["t_exp_per_pulse"]
            t_exp_p = min(t_on_p, thermal_rc.MAX_T_EXPOSURE_SURFACE)
            delta_p = min(math.sqrt(alpha_W * t_exp_p), 0.5 * geom.target_t)
            q_peak = float(meta["peak_envelope"][0]) / focal_area
            dT = q_peak * t_exp_p / (materials.W.rho * materials.W.cp * delta_p)
            T_w_surface_peak = T6[0] + dT

        return ThermalResult(
            t=sol.t, T=T6,
            T_w_surface_peak=T_w_surface_peak,
            ambient_K=T_AMB, node_names=thermal_rc.NODE_NAMES,
        )
