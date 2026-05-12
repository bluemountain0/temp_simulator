# Phase 2 2D-FDM 솔버: W 2D-FVM + RC 체인 결합 ODE를 Radau로 적분 (US-4)
"""FDM2DSolver: IThermalSolver 인터페이스 구현.

상태 벡터 레이아웃 (총 N = Nr·Nz + 4):
  T[0 : Nr·Nz]       W 셀 (row-major: index = i·Nz + j)
  T[Nr·Nz + 0..3]    BTi5, Cu_top, Cu_body, Oil

ThermalResult 매핑 (6-node):
  T[0] (W surface): focal 영역 셀들의 **부피가중 평균** (Phase 2 정의)
  T[1] (W bulk):    전체 W 셀 부피가중 평균
  T[2..5]:          BTi5, Cu_top, Cu_body, Oil (RC 노드)
  T_w_surface_peak: focal 영역 표면(j=0) 셀 최대값 + HF pulse 보정
"""
from __future__ import annotations

import json
import math
import os
import platform
import time
from datetime import datetime, timezone

import numpy as np
from scipy.integrate import solve_ivp

import materials
import thermal_rc
from conditions import ExposureCondition, OilCondition
from fdm2d_assembly import (
    N_RC,
    RC_BTI5,
    RC_CU_BODY,
    RC_CU_TOP,
    RC_OIL,
    assemble_rhs,
    build_conductances,
    build_jac_sparsity,
)
from fdm2d_grid import Grid, build_grid, focal_mask
from geometry import TubeGeometry, focal_spot_area
from thermal_solver import IThermalSolver, ThermalResult
from waveform import build_power_trace


_PERF_LOG_PATH = os.path.join(".omc", "logs", "phase2_perf.json")


class FDM2DSolver(IThermalSolver):
    """2D-FDM (W) + RC (BTi5/Cu_top/Cu_body/Oil) 결합 ODE 솔버. Phase 2.

    Nr=1, Nz=N_W 인 경우 1D 축대칭 → HybridFDSolver와 동등 (M5).
    """

    def __init__(self, Nr: int = 24, Nz: int = 20):
        self.Nr = Nr
        self.Nz = Nz

    def solve(self, exp, geom, k_bti5, oil_cond, T_init=293.15) -> ThermalResult:
        t_arr, _, meta = build_power_trace(exp)
        t_wall_0 = time.perf_counter()

        grid, G_r, G_z, focal_mask_1d, rhs, S = self._build_problem(
            exp, geom, k_bti5, oil_cond
        )

        N = grid.Nr * grid.Nz + N_RC
        y0 = np.full(N, float(T_init))

        # max_step: on-time/10 (저주파 펄스 OFF 구간에서도 안정성 확보)
        on_time = max(exp.on_time, meta.get("t_exp_per_pulse", exp.on_time))
        on_time = on_time if on_time > 0 else exp.on_time
        sol = self._integrate(rhs, y0, t_arr, S, on_time=on_time)

        result = self._pack_result(sol, grid, focal_mask_1d, exp, geom, meta)

        wall_time = time.perf_counter() - t_wall_0
        self._dump_perf(wall_time, len(t_arr), sol)
        return result

    # ------------------------------------------------------------------ build
    def _build_problem(self, exp, geom, k_bti5, oil_cond):
        """문제 어셈블리: grid, G_r, G_z, focal_mask, rhs, sparsity."""
        grid = build_grid(geom, Nr=self.Nr, Nz=self.Nz)
        G_r, G_z = build_conductances(grid)
        A_spot = focal_spot_area(
            geom.focal_L_eff_mm, geom.focal_W_eff_mm, geom.anode_angle_deg
        )
        focal_mask_1d, _ = focal_mask(grid, A_spot)

        t_arr, P_arr, _ = build_power_trace(exp)
        P_at_t = lambda tq: float(np.interp(tq, t_arr, P_arr))

        rhs = assemble_rhs(
            grid, G_r, G_z, focal_mask_1d,
            k_bti5=k_bti5, oil_cond=oil_cond, P_at_t=P_at_t, geom=geom,
        )
        S = build_jac_sparsity(grid, N_rc=N_RC)
        return grid, G_r, G_z, focal_mask_1d, rhs, S

    # -------------------------------------------------------------- integrate
    def _integrate(self, rhs, y0, t_arr, S, on_time: float):
        """Radau ODE 적분. sparsity 패턴 전달로 가속."""
        t_span = (float(t_arr[0]), float(t_arr[-1]))
        max_step = max(on_time / 10.0, 1e-6)
        sol = solve_ivp(
            rhs, t_span, y0,
            method="Radau",
            rtol=1e-4,
            atol=1e-2,
            jac_sparsity=S,
            t_eval=t_arr,
            first_step=1e-6,
            max_step=max_step,
        )
        assert sol.success, f"FDM2D ODE 실패: {sol.message}"
        return sol

    # ---------------------------------------------------------------- package
    def _pack_result(self, sol, grid: Grid, focal_mask_1d, exp, geom, meta) -> ThermalResult:
        """sol.y → 6-node ThermalResult 변환 + HF pulse peak 보정."""
        Nr, Nz = grid.Nr, grid.Nz
        N_w = Nr * Nz
        n_t = sol.y.shape[1]

        T_w = sol.y[:N_w].reshape(Nr, Nz, n_t)              # (Nr, Nz, N_t)
        cell_V = grid.cell_volumes                          # (Nr, Nz)

        # focal 영역 셀 (mask=True 인 i 전체 + 모든 j) 부피가중 평균
        focal_i = np.where(focal_mask_1d)[0]
        V_focal = cell_V[focal_i, :]                        # (Nf, Nz)
        T_focal = T_w[focal_i, :, :]                        # (Nf, Nz, N_t)
        V_focal_sum = float(np.sum(V_focal))
        T_w_surface = np.sum(T_focal * V_focal[:, :, None], axis=(0, 1)) / V_focal_sum

        # 전체 W 부피가중 평균
        V_total = float(np.sum(cell_V))
        T_w_bulk = np.sum(T_w * cell_V[:, :, None], axis=(0, 1)) / V_total

        # T_w_surface_peak: focal 영역 표면 셀 (j=0) 최대값 + HF pulse 보정
        T_focal_top = T_focal[:, 0, :]                      # (Nf, N_t)
        T_w_surface_peak = np.max(T_focal_top, axis=0).copy()

        if (exp.mode == "pulse" and exp.freq_hz > 10
                and meta.get("peak_envelope") is not None):
            A_spot = focal_spot_area(
                geom.focal_L_eff_mm, geom.focal_W_eff_mm, geom.anode_angle_deg
            )
            alpha_W = materials.alpha(materials.W)
            t_on_p = meta["t_exp_per_pulse"]
            t_exp_p = min(t_on_p, thermal_rc.MAX_T_EXPOSURE_SURFACE)
            delta_p = min(math.sqrt(alpha_W * t_exp_p), 0.5 * geom.target_t)
            q_peak = float(meta["peak_envelope"][0]) / A_spot
            dT = q_peak * t_exp_p / (materials.W.rho * materials.W.cp * delta_p)
            T_w_surface_peak = T_w_surface_peak + dT

        T6 = np.zeros((6, n_t))
        T6[0] = T_w_surface
        T6[1] = T_w_bulk
        T6[2] = sol.y[N_w + RC_BTI5]
        T6[3] = sol.y[N_w + RC_CU_TOP]
        T6[4] = sol.y[N_w + RC_CU_BODY]
        T6[5] = sol.y[N_w + RC_OIL]

        return ThermalResult(
            t=sol.t, T=T6,
            T_w_surface_peak=T_w_surface_peak,
            ambient_K=thermal_rc.T_AMBIENT_K,
            node_names=thermal_rc.NODE_NAMES,
        )

    # --------------------------------------------------------- observability
    def _dump_perf(self, wall_time: float, n_t: int, sol) -> None:
        """`.omc/logs/phase2_perf.json` 에 성능 레코드 append."""
        try:
            os.makedirs(os.path.dirname(_PERF_LOG_PATH), exist_ok=True)
            record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "env": platform.system(),
                "runner_image": platform.platform(),
                "Nr": self.Nr,
                "Nz": self.Nz,
                "wall_time": float(wall_time),
                "n_t": int(n_t),
                "nfev": int(getattr(sol, "nfev", 0)),
                "njev": int(getattr(sol, "njev", 0)),
                "nlu": int(getattr(sol, "nlu", 0)),
            }
            records = []
            if os.path.exists(_PERF_LOG_PATH):
                try:
                    with open(_PERF_LOG_PATH, "r", encoding="utf-8") as f:
                        records = json.load(f)
                    if not isinstance(records, list):
                        records = []
                except (json.JSONDecodeError, OSError):
                    records = []
            records.append(record)
            with open(_PERF_LOG_PATH, "w", encoding="utf-8") as f:
                json.dump(records, f, ensure_ascii=False, indent=2)
        except OSError:
            # observability 실패는 솔버 실패로 전파하지 않음
            pass
