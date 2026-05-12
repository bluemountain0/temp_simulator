from dataclasses import dataclass
from typing import Union, Tuple


@dataclass(frozen=True)
class Material:
    name: str
    rho: float                                      # 밀도 [kg/m³]
    cp: float                                       # 비열 [J/kg·K]
    k: float                                        # 열전도율 [W/m·K]
    T_melt: Union[float, Tuple[float, float]]       # 용융점 [K] (BTi-5는 (solidus, liquidus))


# --- 모듈 상수 (SI 단위) ---

W = Material("W", 19250, 135, 170, 3422 + 273.15)

Cu = Material("Cu", 8960, 385, 401, 1085 + 273.15)

# BTi-5: k는 sensitivity 기본값 20 W/m·K, T_melt = (solidus, liquidus) K
BTi5 = Material("BTi-5", 6680, 500, 20, (840 + 273.15, 880 + 273.15))

# 절연유 KS C 2301 1종 4호: T_melt 자리에 인화점
Oil = Material("Oil-KS-C-2301", 848, 1800, 0.13, 150 + 273.15)


# --- 헬퍼 함수 ---

def alpha(mat: Material) -> float:
    """열확산도 [m²/s] = k / (rho * cp)."""
    return mat.k / (mat.rho * mat.cp)


def bti5_with_k(k: float) -> Material:
    """BTi-5 k 오버라이드 헬퍼 (sensitivity: 10 / 20 / 40 W/m·K)."""
    return Material(BTi5.name, BTi5.rho, BTi5.cp, k, BTi5.T_melt)
