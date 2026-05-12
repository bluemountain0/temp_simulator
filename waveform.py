import numpy as np
from typing import Optional, Tuple

from conditions import ExposureCondition
from beam import effective_power_peak

_MAX_SAMPLES = 100_000


def build_power_trace(
    exp: ExposureCondition,
) -> Tuple[np.ndarray, np.ndarray, dict]:
    """조사 조건 → (t [s], P [W], meta) 변환.

    meta keys:
      t_exp_per_pulse: float            단일 on-duration [s] (delta 계산용)
      peak_envelope:   ndarray | None   고주파 pulse peak 포락선
    """
    P_peak = effective_power_peak(exp)
    if exp.mode in ("dc_single", "dc_cyclic"):
        return _dc_trace(exp, P_peak)
    return _pulse_trace(exp, P_peak)


def _dc_trace(
    exp: ExposureCondition, P_peak: float
) -> Tuple[np.ndarray, np.ndarray, dict]:
    if exp.mode == "dc_single":
        total = exp.on_time
        dt = max(exp.on_time / 1000.0, 1e-4)
    else:
        total = exp.cycles * (exp.on_time + exp.off_time)
        # DC cyclic: on_time은 세밀하게, off_time은 적당하게 샘플링
        dt = max(min(exp.on_time / 100.0, exp.off_time / 10.0), 1e-4)

    n = int(total / dt) + 1
    _check_samples(n)

    t = np.linspace(0.0, total, n)
    if exp.mode == "dc_single":
        P = np.full(n, P_peak)
    else:
        period = exp.on_time + exp.off_time
        cycle_idx = np.floor(t / period).astype(int)
        cycle_phase = t % period
        P = np.where(
            (cycle_phase <= exp.on_time) & (cycle_idx < exp.cycles),
            P_peak, 0.0,
        )

    return t, P, {"t_exp_per_pulse": exp.on_time, "peak_envelope": None}


def _pulse_trace(
    exp: ExposureCondition, P_peak: float
) -> Tuple[np.ndarray, np.ndarray, dict]:
    freq = exp.freq_hz
    duty = exp.duty
    on_duration = duty / freq if freq > 0 else exp.on_time

    # 펄스 사이클 모드 판정
    pulse_cyclic = exp.off_time > 0 and exp.cycles > 1
    if pulse_cyclic:
        total = exp.cycles * (exp.on_time + exp.off_time)
    else:
        total = exp.total_time if exp.total_time is not None else exp.on_time

    if freq > 10.0:
        # 고주파: 평균전력 트레이스 + peak 포락선
        P_avg = P_peak * duty
        dt = max(total / 1000.0, 1e-4)
        n = int(total / dt) + 1
        t = np.linspace(0.0, total, n)

        if pulse_cyclic:
            period_cycle = exp.on_time + exp.off_time
            cycle_idx = np.floor(t / period_cycle).astype(int)
            in_on_phase = (t % period_cycle <= exp.on_time) & (cycle_idx < exp.cycles)
            P = np.where(in_on_phase, P_avg, 0.0)
        else:
            P = np.full(n, P_avg)

        return t, P, {
            "t_exp_per_pulse": on_duration,
            "peak_envelope": np.full(n, P_peak) if pulse_cyclic else np.full(n, P_peak),
        }

    # 저주파: 개별 펄스 시간축
    period_pulse = 1.0 / freq if freq > 0 else total
    dt = max(min(on_duration / 10.0, 0.01), 1e-6)
    n = int(total / dt) + 1
    _check_samples(n)

    t = np.linspace(0.0, total, n)

    if pulse_cyclic:
        period_cycle = exp.on_time + exp.off_time
        cycle_idx = np.floor(t / period_cycle).astype(int)
        in_on_phase = (t % period_cycle <= exp.on_time) & (cycle_idx < exp.cycles)
        pulse_phase = (t % period_pulse) <= on_duration
        P = np.where(in_on_phase & pulse_phase, P_peak, 0.0)
    else:
        P = np.where(t % period_pulse <= on_duration, P_peak, 0.0)

    return t, P, {"t_exp_per_pulse": on_duration, "peak_envelope": None}


def solver_dt_hint(exp: ExposureCondition) -> Optional[float]:
    """저주파 pulse 솔버 dt 힌트 반환. 그 외 None."""
    if exp.mode == "pulse" and 0 < exp.freq_hz <= 10.0:
        return 0.1 * exp.duty / exp.freq_hz
    return None


def t_exposure_per_pulse(exp: ExposureCondition) -> float:
    """단일 펄스 on-duration [s] 반환 (delta_eff 계산용)."""
    if exp.mode == "pulse" and exp.freq_hz > 0:
        return exp.duty / exp.freq_hz
    return exp.on_time


def _check_samples(n: int) -> None:
    if n > _MAX_SAMPLES:
        raise ValueError(
            f"시뮬레이션 시간 또는 해상도 초과 ({n:,} 샘플 > {_MAX_SAMPLES:,}). "
            "고주파 모드(>10 Hz) 사용 권장."
        )
