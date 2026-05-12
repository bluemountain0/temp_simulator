from dataclasses import dataclass
from typing import Literal, Optional


@dataclass
class ExposureCondition:
    """조사 조건. mA_peak는 항상 peak current 기준."""
    mode: Literal["dc_single", "dc_cyclic", "pulse"]
    kV: float
    mA_peak: float
    on_time: float  # DC: 조사 시간 [s]; Pulse: total_time과 함께 사용
    off_time: float = 0.0  # DC cyclic 휴지 시간 [s]
    cycles: int = 1  # DC cyclic 반복 횟수
    freq_hz: float = 0.0  # Pulse 주파수 [Hz]
    duty: float = 1.0  # Pulse duty cycle (0~1)
    total_time: Optional[float] = None  # Pulse 총 조사 시간 [s]
    current_input_type: Literal["peak", "average"] = "peak"  # average 선택 시 변환


@dataclass
class OilCondition:
    """냉각 조건."""
    oil_volume_L: float = 30.0  # 절연유 부피 [L]
    cu_immersion_mm: float = 49.4  # Cu 침지 깊이 [mm]
    vessel_w_cm: float = 20.0  # 용기 폭 [cm]
    vessel_d_cm: float = 20.0  # 용기 깊이 [cm]
    h_oil: float = 50.0  # Cu→Oil 대류 계수 [W/m²·K]; forced 모드 시 200으로 설정
    h_oil_air: float = 10.0  # Oil→Ambient 대류 계수 [W/m²·K]
    convection_mode: Literal["natural", "forced"] = "natural"


@dataclass
class GeometryOverride:
    """도면 치수 일부 오버라이드 (None이면 TubeGeometry 기본값 사용)."""
    fin_thickness: Optional[float] = None  # 핀 두께 [m]
    cu_top_d: Optional[float] = None  # Cu 상부 직경 [m]
