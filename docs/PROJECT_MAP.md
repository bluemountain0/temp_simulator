# PROJECT_MAP — 기능별 파일 지도

## 폴더 구조

```
anode_damage_model/
├── CLAUDE.md, AGENTS.md       ← AI 진입점
├── app.py                      ← Streamlit UI (단일 파일)
├── thermal_solver.py           ← 솔버 인터페이스 + HybridFDSolver
├── thermal_rc.py               ← RCSolver 실제 구현 (RC ODE)
├── fem_model.py                ← Phase 2 플레이스홀더
├── geometry.py                 ← 형상·열저항·열용량 계산
├── materials.py                ← 재료 물성 상수
├── waveform.py                 ← 조사 파형 → (t, P) 트레이스
├── beam.py                     ← 전력 계산 (kV·mA → W)
├── conditions.py               ← 입력 데이터클래스
├── damage.py                   ← 손상 판정 로직
├── tests/                      ← pytest 61개
├── docs/                       ← 영구 지식베이스 (이 문서 포함)
├── scripts/                    ← 검증 스크립트
├── requirements.txt
└── 실행.bat
```

## 기능 → 진입점

| 기능 | 파일 | 핵심 심볼 |
|------|------|----------|
| GUI 입력 폼 | `app.py` | `st.sidebar`, `run_sim()` |
| GUI 결과 렌더링 | `app.py` | `LEVEL_COLORS`, `THRESHOLD_LINES` |
| 솔버 선택 인터페이스 | `thermal_solver.py` | `IThermalSolver`, `ThermalResult` |
| HybridFD 솔버 | `thermal_solver.py` | `HybridFDSolver.solve()` |
| RC ODE 솔버 | `thermal_rc.py` | `solve_rc()`, `_make_rhs()` |
| 열저항 행렬 | `geometry.py` | `thermal_resistances()` |
| 열용량 벡터 | `geometry.py` | `thermal_capacities()` |
| 포컬스팟 면적 | `geometry.py` | `focal_spot_area()` |
| 핀 냉각 면적 | `geometry.py` | `fin_surface_area_total()` |
| 재료 물성 | `materials.py` | `W`, `Cu`, `BTi5`, `Oil`, `alpha()` |
| 전력 트레이스 생성 | `waveform.py` | `build_power_trace()`, `_dc_trace()`, `_pulse_trace()` |
| 전력 계산 (kV×mA) | `beam.py` | `power_peak()`, `effective_power_peak()` |
| 입력 조건 | `conditions.py` | `ExposureCondition`, `OilCondition` |
| 손상 단계 판정 | `damage.py` | `judge()`, `DamageLevel`, `_THRESHOLDS` |
| 열확산 깊이 | `thermal_rc.py` | `effective_delta()`, `MAX_T_EXPOSURE_SURFACE` |

## 노드 인덱스 (모든 솔버 공통)

| Index | 노드 | 출력 키 |
|-------|------|---------|
| 0 | W surface | `T_w_surface_peak` |
| 1 | W bulk | `T[1]` |
| 2 | BTi5 | `T[2]` |
| 3 | Cu top | `T[3]` |
| 4 | Cu body | `T[4]` |
| 5 | Oil | `T[5]` |

## 수정 시 주의

| 변경 대상 | 주의 |
|-----------|------|
| `materials.py` | 모든 솔버에 즉시 영향. 변경 후 전체 테스트 필수 |
| `geometry.py` | `thermal_resistances()`/`thermal_capacities()` 둘 다 의존. 도면 변경 시 둘 다 검토 |
| `damage.py _THRESHOLDS` | 임계값 변경 = 판정 기준 변경. `DECISIONS.md`에 근거 명시 |
| `thermal_solver.py` `N_W=20` | FD 노드 수. 줄이면 W 표면 정확도 ↓ |
| `waveform.py _MAX_SAMPLES` | DC 사이클 긴 조건에서 ValueError 가능 |
| `thermal_rc.py MAX_T_EXPOSURE_SURFACE` | W 두께·alpha_W로부터 자동 계산. 직접 수정 금지 |

## 테스트 파일 매핑

| 테스트 | 검증 대상 |
|--------|----------|
| `test_beam.py` | `beam.py` 전력 계산 |
| `test_geometry.py` | `geometry.py` 면적/열저항/열용량 |
| `test_damage.py` | `damage.py` 판정 로직 |
| `test_physics_oracle.py` | 물리 일관성 (에너지 보존, 단조성 등) |
| `test_validation.py` | 기준 케이스 회귀 (100 kV · 12 mA · 50 s 등) |
