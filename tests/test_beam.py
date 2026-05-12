import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
import numpy as np
import beam
from waveform import build_power_trace, t_exposure_per_pulse, solver_dt_hint
from conditions import ExposureCondition


def test_power_peak_basic():
    assert beam.power_peak(100, 12) == pytest.approx(1200.0)


def test_power_average_dc():
    assert beam.power_average(1200.0, "dc_single") == pytest.approx(1200.0)


def test_power_average_pulse():
    P_peak = beam.power_peak(100, 10)   # 1000 W
    assert beam.power_average(P_peak, "pulse", duty=0.1) == pytest.approx(100.0)


def test_heat_flux():
    P = beam.power_peak(100, 12)
    A = 3.97e-6
    assert beam.heat_flux(P, A) == pytest.approx(P / A)


def test_deposition_efficiency():
    assert beam.deposition_efficiency() == pytest.approx(1.0)


def test_resolve_mA_peak_average_input():
    """current_input_type='average' → mA_avg / duty 변환."""
    exp = ExposureCondition(mode="pulse", kV=100, mA_peak=1.0,
                            on_time=1.0, freq_hz=100, duty=0.1,
                            current_input_type="average")
    assert beam.resolve_mA_peak(exp) == pytest.approx(10.0)


def test_resolve_mA_peak_peak_input():
    exp = ExposureCondition(mode="pulse", kV=100, mA_peak=10.0,
                            on_time=1.0, freq_hz=100, duty=0.1)
    assert beam.resolve_mA_peak(exp) == pytest.approx(10.0)


def test_high_freq_peak_envelope_not_none():
    """100 Hz, duty=0.5 → meta['peak_envelope'] is not None."""
    exp = ExposureCondition(mode="pulse", kV=100, mA_peak=10,
                            on_time=1.0, freq_hz=100, duty=0.5)
    _, _, meta = build_power_trace(exp)
    assert meta["peak_envelope"] is not None


def test_high_freq_average_power_correct():
    """고주파 P_array 값이 P_peak × duty인지 확인."""
    exp = ExposureCondition(mode="pulse", kV=100, mA_peak=10,
                            on_time=1.0, freq_hz=100, duty=0.5)
    _, P, _ = build_power_trace(exp)
    assert np.allclose(P, 100 * 10 * 0.5)


def test_high_freq_1kHz_1h_no_error():
    """1 kHz, 1시간 → 고주파 분기 자동 진입, 샘플 수 100k 이하."""
    exp = ExposureCondition(mode="pulse", kV=100, mA_peak=10,
                            on_time=3600.0, freq_hz=1000, duty=0.1)
    t, P, meta = build_power_trace(exp)
    assert len(t) <= 100_000
    assert meta["peak_envelope"] is not None


def test_low_freq_100h_raises():
    """0.5 Hz, 100시간 → 샘플 초과 ValueError."""
    exp = ExposureCondition(mode="pulse", kV=100, mA_peak=10,
                            on_time=360_000.0, freq_hz=0.5, duty=0.1)
    with pytest.raises(ValueError, match="초과"):
        build_power_trace(exp)


def test_dc_single_trace_shape():
    exp = ExposureCondition(mode="dc_single", kV=100, mA_peak=12, on_time=10.0)
    t, P, meta = build_power_trace(exp)
    assert t[0] == pytest.approx(0.0)
    assert t[-1] == pytest.approx(10.0)
    assert np.all(P == pytest.approx(1200.0))
    assert meta["peak_envelope"] is None


def test_dc_cyclic_on_off_pattern():
    """dc_cyclic: on 구간 P_peak, off 구간 0."""
    exp = ExposureCondition(mode="dc_cyclic", kV=100, mA_peak=5,
                            on_time=1.0, off_time=1.0, cycles=3)
    t, P, _ = build_power_trace(exp)
    # t=0.5s → on 구간 → P == 500
    idx_on = np.argmin(np.abs(t - 0.5))
    assert P[idx_on] == pytest.approx(500.0)
    # t=1.5s → off 구간 → P == 0
    idx_off = np.argmin(np.abs(t - 1.5))
    assert P[idx_off] == pytest.approx(0.0, abs=1e-9)


def test_t_exposure_per_pulse_dc():
    exp = ExposureCondition(mode="dc_single", kV=100, mA_peak=12, on_time=10.0)
    assert t_exposure_per_pulse(exp) == pytest.approx(10.0)


def test_t_exposure_per_pulse_pulse():
    exp = ExposureCondition(mode="pulse", kV=100, mA_peak=10,
                            on_time=1.0, freq_hz=1000, duty=0.1)
    assert t_exposure_per_pulse(exp) == pytest.approx(0.1 / 1000)


def test_solver_dt_hint_low_freq():
    exp = ExposureCondition(mode="pulse", kV=100, mA_peak=10,
                            on_time=1.0, freq_hz=5, duty=0.2)
    hint = solver_dt_hint(exp)
    assert hint == pytest.approx(0.1 * 0.2 / 5)


def test_solver_dt_hint_high_freq_none():
    exp = ExposureCondition(mode="pulse", kV=100, mA_peak=10,
                            on_time=1.0, freq_hz=1000, duty=0.1)
    assert solver_dt_hint(exp) is None


def test_solver_dt_hint_dc_none():
    exp = ExposureCondition(mode="dc_single", kV=100, mA_peak=12, on_time=5.0)
    assert solver_dt_hint(exp) is None
