from conditions import ExposureCondition


def power_peak(kV: float, mA_peak: float) -> float:
    """P_peak [W] = kV × mA_peak (kV × mA = W)."""
    return kV * mA_peak


def power_average(P_peak: float, mode: str, duty: float = 1.0) -> float:
    """평균 전력 [W]. Pulse 모드는 P_peak × duty, DC 모드는 P_peak."""
    return P_peak * duty if mode == "pulse" else P_peak


def heat_flux(P: float, A_spot: float) -> float:
    """열유속 [W/m²] = P / A_spot."""
    return P / A_spot


def deposition_efficiency() -> float:
    """Phase 1: 입사 전력 100% 흡수 가정."""
    return 1.0


def resolve_mA_peak(exp: ExposureCondition) -> float:
    """current_input_type='average'이면 mA_avg / duty → mA_peak 변환."""
    if exp.current_input_type == "average" and exp.mode == "pulse" and exp.duty > 0:
        return exp.mA_peak / exp.duty
    return exp.mA_peak


def effective_power_peak(exp: ExposureCondition) -> float:
    """ExposureCondition에서 실효 P_peak [W] 반환."""
    return power_peak(exp.kV, resolve_mA_peak(exp))
