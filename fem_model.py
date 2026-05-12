"""Phase 2 FEM placeholder. IThermalSolver 인터페이스 유지."""
from thermal_solver import IThermalSolver


class FEMSolver(IThermalSolver):
    def solve(self, exp, geom, k_bti5, oil_cond, T_init=293.15):
        raise NotImplementedError("Phase 2: FEM 미구현. RCSolver() 또는 HybridFDSolver() 사용.")
