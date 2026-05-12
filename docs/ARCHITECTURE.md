# ARCHITECTURE — 시스템 구조

## 데이터 흐름

```
[사용자 입력 - Streamlit Sidebar]
        ↓
ExposureCondition / OilCondition / TubeGeometry  (conditions.py, geometry.py)
        ↓
beam.effective_power_peak()           ← kV × mA → W
        ↓
waveform.build_power_trace()           ← (t [s], P [W], meta dict)
        ↓
thermal_solver.HybridFDSolver().solve()  또는 RCSolver().solve()
        ↓
ThermalResult (t, T[6×N], T_w_surface_peak, ambient_K, node_names)
        ↓
damage.judge()                          ← DamageLevel + DamageVerdict
        ↓
app.py — Plotly 그래프 + 손상 배너
```

## 모듈 의존성 (DAG)

```
materials  ←──┐
              ├── geometry  ←──┐
conditions  ←─┘                ├── thermal_rc  ←─┐
                               │                  ├── thermal_solver  ←─┐
              ├── waveform  ←──┤                  │                      │
beam       ←──┘   (← conditions)                  │                      │
                                                  └── damage           ←─┤
                                                                          │
                                                              app.py  ←──┘
                                                              tests/  ←──┘
```

### 금지된 의존성

- `materials.py` → 어디에도 의존하지 않는다 (순수 상수)
- `conditions.py` → 어디에도 의존하지 않는다 (순수 데이터클래스)
- `geometry.py` → `materials`, `conditions`만 import. `thermal_*` import 금지
- `damage.py` → `thermal_solver.ThermalResult`만 의존. 솔버 내부 임포트 금지

## 솔버 계층

```
IThermalSolver (abstract)             ← thermal_solver.py
  ├── RCSolver         (Phase 1.0a)   ← 6-노드 집중 RC ODE
  ├── HybridFDSolver   (Phase 1.0b)   ← W 슬랩 1D-FD + RC 하부 (현재 기본)
  └── FEMSolver        (Phase 2)      ← NotImplementedError 플레이스홀더
```

세 솔버 모두 동일한 `solve(exp, geom, k_bti5, oil_cond, T_init) → ThermalResult` 시그니처.

## 핵심 물리 가정

| 항목 | 가정 | 영향 범위 |
|------|------|----------|
| 차원 | 1D (z방향만, 횡방향 r 미반영) | t > 100 ms DC에서 W 표면 과대 추정 |
| 입력 흡수 | 100% (반사·X-ray 변환 손실 무시) | Phase 1 단순화. Phase 3에서 보정 예정 |
| Ambient | 293.15 K 고정 boundary | 외기 변동 미반영 |
| Pulse > 10 Hz | 평균전력 트레이스 + peak envelope 보정 | 사이클 단위 표면 진동 평탄화 |
| 열확산 깊이 | δ = √(α·t), 상한 = W 반두께 | 단기 조사에 정확, 장기에 과소 추정 |
| 에너지 보존 | C[0] + C[1] = ρ·cp·V_total | `geometry.thermal_capacities()`에서 자동 검증 |

## ThermalResult 스키마

```python
@dataclass
class ThermalResult:
    t: np.ndarray                # (N,) 시간 [s]
    T: np.ndarray                # (6, N) 노드 온도 [K]
    T_w_surface_peak: np.ndarray # (N,) W 표면 peak 보정값 [K]
    ambient_K: float             # 293.15
    node_names: list             # ["W_surf", "W_bulk", "BTi5", "Cu_top", "Cu_body", "Oil"]
```

**T_w_surface_peak**: HF pulse(> 10 Hz) 모드에서 평균전력 트레이스에 단일 펄스 표면 상승분(Δ_pulse)을 더한 값. judge()는 W surface 판정 시 이 값을 사용.

## 상태 관리 / 캐싱

- Streamlit `st.cache_data` → `run_sim()` 단위. 입력 동일 시 재계산 없음.
- 솔버는 **무상태**. `solve()` 호출 간 메모리 공유 없음.
- 시뮬레이션 결과는 메모리에만 존재. 디스크 저장 기능 없음 (Phase 1 스코프 밖).

## 유지해야 할 아키텍처 원칙

1. **솔버는 인터페이스 뒤에 둔다.** `IThermalSolver` 시그니처 변경 = 모든 호출부 수정.
2. **물리 상수는 한 곳에.** `materials.py`/`geometry.py` 외 위치에 상수 넣지 말 것.
3. **`thermal_rc.py`는 절대 horizontal import 금지.** geometry/materials/conditions/waveform만.
4. **`damage.py`는 솔버 내부 미지원.** ThermalResult dataclass 인터페이스만 사용.
5. **`app.py`는 비즈니스 로직 미보유.** 입력 수집·결과 렌더링만 담당.
