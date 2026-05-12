from dataclasses import dataclass
from enum import IntEnum
from typing import Optional

import numpy as np

from thermal_solver import ThermalResult


class DamageLevel(IntEnum):
    SAFE        = 0
    WARNING1    = 1   # BTi-5 ≥ 700°C (solidus 17% 안전 마진)
    DAMAGE1     = 2   # BTi-5 ≥ 840°C (solidus)
    DAMAGE2     = 3   # BTi-5 ≥ 880°C (liquidus)
    DAMAGE3     = 4   # Cu ≥ 1085°C
    DAMAGE4     = 5   # W ≥ 2500°C
    FAILURE     = 6   # W ≥ 3422°C
    OIL_WARNING = 7   # Oil ≥ 100°C
    OIL_DANGER  = 8   # Oil ≥ 150°C (인화점)


@dataclass
class DamageVerdict:
    level: DamageLevel
    first_failed_node: str
    time_to_damage_s: Optional[float]
    max_temps: dict        # node_name → max temp [°C]
    reasons: list          # 심각도 내림차순 str list


# (DamageLevel, node_name, threshold_K)
_THRESHOLDS = [
    (DamageLevel.FAILURE,     "W surface",  3422 + 273.15),
    (DamageLevel.DAMAGE4,     "W surface",  2500 + 273.15),
    (DamageLevel.DAMAGE3,     "Cu top",     1085 + 273.15),
    (DamageLevel.DAMAGE3,     "Cu body",    1085 + 273.15),
    (DamageLevel.DAMAGE2,     "BTi5",        880 + 273.15),
    (DamageLevel.DAMAGE1,     "BTi5",        840 + 273.15),
    (DamageLevel.WARNING1,    "BTi5",        700 + 273.15),
    (DamageLevel.OIL_DANGER,  "Oil",         150 + 273.15),
    (DamageLevel.OIL_WARNING, "Oil",         100 + 273.15),
]

_NODE_SERIES_KEY = {
    "W surface": None,   # T_w_surface_peak 사용
    "W bulk":    1,
    "BTi5":      2,
    "Cu top":    3,
    "Cu body":   4,
    "Oil":       5,
}


def judge(result: ThermalResult) -> DamageVerdict:
    """시간별 max 온도 기반 8단계 손상 판정."""
    T_series = {
        "W surface": result.T_w_surface_peak,
        "W bulk":    result.T[1],
        "BTi5":      result.T[2],
        "Cu top":    result.T[3],
        "Cu body":   result.T[4],
        "Oil":       result.T[5],
    }
    node_max_K = {node: float(ts.max()) for node, ts in T_series.items()}

    violations: list[tuple] = []
    for level, node, threshold_K in _THRESHOLDS:
        if node_max_K[node] >= threshold_K:
            violations.append((level, node, threshold_K))

    if not violations:
        return DamageVerdict(
            level=DamageLevel.SAFE,
            first_failed_node="없음",
            time_to_damage_s=None,
            max_temps={k: v - 273.15 for k, v in node_max_K.items()},
            reasons=[],
        )

    max_level = max(v[0] for v in violations)

    # max_level 노드 중 임계값 최초 도달 시각/노드 탐색
    best_node = ""
    best_time: Optional[float] = None
    for lvl, node, threshold_K in violations:
        if lvl != max_level:
            continue
        ts = T_series[node]
        idx_arr = np.where(ts >= threshold_K)[0]
        if len(idx_arr) == 0:
            continue
        t_cross = float(result.t[idx_arr[0]])
        if best_time is None or t_cross < best_time:
            best_time = t_cross
            best_node = node

    reasons = [
        f"{node}: max {node_max_K[node]-273.15:.0f}°C ≥ {thresh-273.15:.0f}°C ({lvl.name})"
        for lvl, node, thresh in sorted(violations, key=lambda x: x[0], reverse=True)
    ]

    return DamageVerdict(
        level=max_level,
        first_failed_node=best_node or "없음",
        time_to_damage_s=best_time,
        max_temps={k: v - 273.15 for k, v in node_max_K.items()},
        reasons=reasons,
    )
