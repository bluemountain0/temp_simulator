# Phase 2 US-3 성능 스모크: 3 스케일 (Nr, Nz) 격자 벽시간 측정 + log-log 외삽
"""사용: python scripts/phase2_perf_smoke.py

검증 케이스: 100 kV · 12 mA · 50 s DC
3 스케일: (12, 10), (16, 16), (24, 20)
각 스케일별 wall-time 측정 → log-log 외삽으로 스케일링 거동 확인.
(24, 20) 스케일이 30초를 초과하면 즉시 알림 후 비-zero 종료.

requirements.lock 존재 시 INFO 출력, 없으면 경고 (skip 아님).
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from conditions import ExposureCondition, OilCondition
from fdm2d_assembly import N_RC, assemble_rhs, build_conductances, build_jac_sparsity
from fdm2d_grid import build_grid, focal_mask
from geometry import TubeGeometry, focal_spot_area
from waveform import build_power_trace


SCALES = [(12, 10), (16, 16), (24, 20)]
WALL_TIME_LIMIT_S = 30.0
SCENARIO = ExposureCondition(mode="dc_single", kV=100.0, mA_peak=12.0, on_time=50.0)


def run_one(Nr: int, Nz: int) -> float:
    """단일 스케일에서 1회 적분 wall-time [s] 반환."""
    geom = TubeGeometry()
    grid = build_grid(geom, Nr=Nr, Nz=Nz)
    G_r, G_z = build_conductances(grid)
    A_spot = focal_spot_area(geom.focal_L_eff_mm, geom.focal_W_eff_mm, geom.anode_angle_deg)
    mask_1d, _ = focal_mask(grid, A_spot)
    oil = OilCondition()

    t_arr, P_arr, _ = build_power_trace(SCENARIO)
    P_at_t = lambda tq: float(np.interp(tq, t_arr, P_arr))

    rhs = assemble_rhs(grid, G_r, G_z, mask_1d, k_bti5=20.0,
                       oil_cond=oil, P_at_t=P_at_t, geom=geom)
    S = build_jac_sparsity(grid, N_rc=N_RC)

    N = Nr * Nz + N_RC
    T0 = np.full(N, 293.15)

    t0 = time.perf_counter()
    sol = solve_ivp(
        rhs,
        (float(t_arr[0]), float(t_arr[-1])),
        T0,
        method="Radau",
        rtol=1e-4,
        atol=1e-2,
        t_eval=t_arr,
        jac_sparsity=S,
    )
    elapsed = time.perf_counter() - t0
    assert sol.success, f"({Nr},{Nz}) 솔버 실패: {sol.message}"
    return elapsed


def check_env() -> None:
    """requirements.lock 존재 여부 + 현재 환경 보고."""
    lock = ROOT / "requirements.lock"
    if lock.exists():
        print(f"[INFO] requirements.lock 존재: {lock}")
    else:
        print(f"[WARN] requirements.lock 필요: {lock} (개발 PC Windows 환경 + lock 양쪽 검증 권장)")
    print(f"[INFO] Python: {sys.version.split()[0]}, Platform: {sys.platform}")
    try:
        import numpy, scipy
        print(f"[INFO] numpy={numpy.__version__}, scipy={scipy.__version__}")
    except Exception as e:
        print(f"[WARN] 의존성 import 실패: {e}")


def main() -> int:
    check_env()
    print(f"\n=== Phase 2 US-3 perf smoke: {SCENARIO.kV} kV · {SCENARIO.mA_peak} mA · {SCENARIO.on_time} s ===")

    results: list[tuple[int, int, float]] = []
    for Nr, Nz in SCALES:
        N = Nr * Nz + N_RC
        elapsed = run_one(Nr, Nz)
        results.append((Nr, Nz, elapsed))
        print(f"[RUN]  (Nr={Nr:2d}, Nz={Nz:2d}) N={N:4d}  wall = {elapsed:7.3f} s")
        if (Nr, Nz) == (24, 20):
            if elapsed > WALL_TIME_LIMIT_S:
                print(f"\n[FAIL] (24,20) {elapsed:.2f}s > {WALL_TIME_LIMIT_S}s 초과 — 즉시 알림")
                return 1
            else:
                print(f"[OK]   (24,20) {elapsed:.2f}s <= {WALL_TIME_LIMIT_S}s")

    # log-log 외삽: t ~ N^p 형태
    if len(results) >= 2:
        Ns = np.array([Nr * Nz + N_RC for (Nr, Nz, _) in results], dtype=float)
        ts = np.array([t for (_, _, t) in results], dtype=float)
        # 0 또는 음수 wall-time 방지
        ts = np.maximum(ts, 1e-6)
        log_N = np.log(Ns)
        log_t = np.log(ts)
        p, log_c = np.polyfit(log_N, log_t, 1)
        c = float(np.exp(log_c))
        print(f"\n[FIT]  t ~ {c:.3e} * N^{p:.2f}  (log-log extrap)")
        # next scale prediction
        for N_predict in (1024, 2048):
            t_pred = c * N_predict ** p
            print(f"[PRED] N={N_predict} -> t ~ {t_pred:.2f} s")

    print("\n[DONE] perf smoke 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
