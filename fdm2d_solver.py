"""Phase 2 2D-FDM 솔버 (인플라이트). IThermalSolver 인터페이스 유지."""
from thermal_solver import IThermalSolver


class FDM2DSolver(IThermalSolver):
    def solve(self, exp, geom, k_bti5, oil_cond, T_init=293.15):
        raise NotImplementedError("Phase 2: 2D-FDM 인플라이트 (phase2-2dfdm 브랜치). US-2부터 구현.")
