import math
from dataclasses import dataclass, field
from typing import List

import numpy as np

import materials
from conditions import OilCondition

# W 표면 유효 열확산 시간 상한 [s]
# W 디스크 두께가 열확산 깊이보다 얇아지는 시점: target_t² / alpha_W
# alpha_W = 170 / (19250 * 135) ≈ 6.54e-5 m²/s
# MAX = (0.96e-3)² / 6.54e-5 ≈ 0.014 s (14 ms)
MAX_T_EXPOSURE_SURFACE: float = (0.96e-3) ** 2 / (170 / (19250 * 135))


@dataclass
class TubeGeometry:
    """X-ray tube 고정 애노드 형상 (도면 확정값)."""

    # W 타겟
    target_d: float = 8.73e-3       # 직경 [m]
    target_t: float = 0.96e-3       # 두께 [m]
    anode_angle_deg: float = 12.0   # 경사각 [deg]

    # BTi-5 접합층
    bti5_t: float = 11.8e-6         # bondline 두께 [m]

    # Cu 상부 (solid)
    cu_top_d: float = 19.0e-3       # 직경 [m]
    cu_top_h: float = 49.4e-3       # 높이 [m]

    # Cu 핀 구간
    cu_root_d: float = 13.0e-3      # 루트 직경 [m]
    cu_fin_od: float = 24.5e-3      # 핀 외경 [m]
    cu_fin_total_h: float = 21.0e-3 # 핀 구간 전체 높이 [m]
    fin_count: int = 10             # 핀 개수

    # 핀 두께 (도면 미기재 → 간격 패턴으로부터 추정 ~0.8 mm)
    fin_thickness: float = 0.8e-3   # [m]

    # 실효 포컬스팟 (도면 스펙값; UI 오버라이드 가능)
    focal_L_eff_mm: float = 1.1     # 실효 길이 [mm]
    focal_W_eff_mm: float = 0.75    # 실효 폭 [mm]

    # 핀 하단면 z-좌표 [mm], Cu 하단면 기준, 위→아래 순서
    # 주의: 최상단 핀(21.0mm)은 Cu top 경계와 맞닿음.
    #       fin_thickness=0.8mm 추가 시 21.8mm가 되어 cu_fin_total_h(21.0mm)를 초과하나
    #       fin_surface_area_total()에서 gap_above≤0 → skip으로 올바르게 처리됨.
    fin_z_positions_mm: List[float] = field(
        default_factory=lambda: [21.0, 18.5, 16.2, 14.2, 11.9, 9.9, 7.6, 5.6, 3.3, 1.0]
    )


# ---------------------------------------------------------------------------
# 공간/형상 계산 함수
# ---------------------------------------------------------------------------

def focal_spot_area(L_eff_mm: float, W_eff_mm: float, angle_deg: float) -> float:
    """실효 포컬스팟 → 실제 타겟 조사 면적 [m²].

    L_actual = L_eff / sin(angle)  (투영 역산)
    검증: (1.1, 0.75, 12°) → ≈ 3.97e-6 m²
    """
    sin_a = math.sin(math.radians(angle_deg))
    L_actual_mm = L_eff_mm / sin_a
    return (L_actual_mm * 1e-3) * (W_eff_mm * 1e-3)


def fin_surface_area_total(g: TubeGeometry) -> float:
    """핀 총 냉각 면적 [m²]: 핀 평면(상하면) + 루트 노출 원통면."""
    r_root = g.cu_root_d / 2
    r_fin = g.cu_fin_od / 2
    t = g.fin_thickness

    # 핀 평면(상면 + 하면)
    fin_flat_area = g.fin_count * 2 * math.pi * (r_fin ** 2 - r_root ** 2)

    # 루트 원통 노출면: 핀 사이 간격
    positions_m = sorted(p * 1e-3 for p in g.fin_z_positions_mm)  # 오름차순 [m]
    root_area = 0.0

    # 최하단 핀 아래 공간
    gap_below = positions_m[0]
    if gap_below > 0:
        root_area += 2 * math.pi * r_root * gap_below

    # 핀 사이 간격
    for i in range(len(positions_m) - 1):
        fin_top = positions_m[i] + t
        next_bottom = positions_m[i + 1]
        gap = next_bottom - fin_top
        if gap > 0:
            root_area += 2 * math.pi * r_root * gap

    # 최상단 핀 위 공간 (핀 구간 상단까지)
    highest_fin_top = positions_m[-1] + t
    gap_above = g.cu_fin_total_h - highest_fin_top
    if gap_above > 0:
        root_area += 2 * math.pi * r_root * gap_above

    return fin_flat_area + root_area


# ---------------------------------------------------------------------------
# 열회로 행렬 빌더 (geometry 기반 정적 파트)
# ---------------------------------------------------------------------------

def thermal_resistances(g: TubeGeometry, k_bti5: float, oil_cond: OilCondition) -> np.ndarray:
    """6×6 열저항 행렬 [K/W].

    비인접 노드 및 R[0,1] (W 표면↔W bulk, delta_eff 의존)은 np.inf.
    R[0,1]은 thermal_rc.build_rc_matrices에서 delta_eff 계산 후 채운다.

    노드 인덱스:
      0: W surface, 1: W bulk, 2: BTi-5, 3: Cu top, 4: Cu body, 5: Oil bulk
    """
    R = np.full((6, 6), np.inf)

    A_w_base = math.pi * (g.target_d / 2) ** 2         # W 전체 하면 [m²]
    A_cu_top = math.pi * (g.cu_top_d / 2) ** 2         # Cu 상부 단면적 [m²]
    A_cu_root = math.pi * (g.cu_root_d / 2) ** 2       # Cu 루트 단면적 [m²]
    A_fin = fin_surface_area_total(g)                   # 핀 냉각 면적 [m²]

    # R[1,2]: W bulk ↔ BTi-5 (반 두께 직렬 합산)
    r12 = (g.target_t / 2) / (materials.W.k * A_w_base) + \
          (g.bti5_t / 2) / (k_bti5 * A_w_base)
    R[1, 2] = R[2, 1] = r12

    # R[2,3]: BTi-5 ↔ Cu top
    r23 = (g.bti5_t / 2) / (k_bti5 * A_w_base) + \
          (g.cu_top_h / 2) / (materials.Cu.k * A_cu_top)
    R[2, 3] = R[3, 2] = r23

    # R[3,4]: Cu top ↔ Cu body (핀 루트 단면)
    r34 = (g.cu_top_h / 2) / (materials.Cu.k * A_cu_top) + \
          (g.cu_fin_total_h / 2) / (materials.Cu.k * A_cu_root)
    R[3, 4] = R[4, 3] = r34

    # R[4,5]: Cu body ↔ Oil (핀 대류)
    # oil_cond.h_oil을 그대로 사용. forced 모드 시 호출부에서 h_oil=200으로 설정.
    r45 = 1.0 / (oil_cond.h_oil * A_fin)
    R[4, 5] = R[5, 4] = r45

    return R


def thermal_capacities(
    g: TubeGeometry,
    focal_area: float,
    t_exp: float,
    oil_cond: OilCondition,
) -> np.ndarray:
    """6노드 열용량 벡터 [J/K].

    C[0] + C[1] = rho_W * cp_W * V_W_total (에너지 보존 자동 검증).
    t_exp는 MAX_T_EXPOSURE_SURFACE로 상한 클램프 적용된 값을 넘겨야 함.
    """
    alpha_W = materials.alpha(materials.W)
    delta_raw = math.sqrt(alpha_W * t_exp)
    delta_eff = min(delta_raw, 0.5 * g.target_t)

    V_W_total = math.pi * (g.target_d / 2) ** 2 * g.target_t
    A_w_base = math.pi * (g.target_d / 2) ** 2
    A_cu_top = math.pi * (g.cu_top_d / 2) ** 2

    # Cu body 부피: 루트 원통 + 핀 합
    r_root = g.cu_root_d / 2
    r_fin = g.cu_fin_od / 2
    V_cu_root_cyl = math.pi * r_root ** 2 * g.cu_fin_total_h
    V_fin_one = math.pi * (r_fin ** 2 - r_root ** 2) * g.fin_thickness
    V_cu_body = V_cu_root_cyl + g.fin_count * V_fin_one

    surface_vol = focal_area * delta_eff   # W 표면 노드 유효 체적

    C = np.zeros(6)
    C[0] = materials.W.rho * materials.W.cp * surface_vol
    C[1] = materials.W.rho * materials.W.cp * (V_W_total - surface_vol)
    C[2] = materials.BTi5.rho * materials.BTi5.cp * A_w_base * g.bti5_t
    C[3] = materials.Cu.rho * materials.Cu.cp * A_cu_top * g.cu_top_h
    C[4] = materials.Cu.rho * materials.Cu.cp * V_cu_body
    C[5] = materials.Oil.rho * materials.Oil.cp * (oil_cond.oil_volume_L * 1e-3)

    # 에너지 보존 내부 검증
    C_w_total = materials.W.rho * materials.W.cp * V_W_total
    rel_err = abs(C[0] + C[1] - C_w_total) / C_w_total
    assert rel_err < 1e-6, f"W 열용량 에너지 보존 위반: rel_err={rel_err:.2e}"

    return C
