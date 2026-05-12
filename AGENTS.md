# AGENTS.md — X-ray 고정 애노드 열손상 예측 시뮬레이터

## 프로젝트 개요

X-ray 고정 애노드(Fixed Anode) 튜브의 열손상 위험을 예측하는 Streamlit 시뮬레이션 앱.
사용자가 관전압(kV), 관전류(mA), 조사 시간, 냉각 조건을 입력하면
W 표면 → BTi5 → Cu → 절연유 경로의 온도 이력을 계산하고 손상 단계를 판정한다.

- **현재 단계**: Phase 1.0b (HybridFDSolver)
- **모델 신뢰도**: ±30~50% (1D 가정, 횡방향 열확산 미반영)
- **실행 방법**: `실행.bat` 더블클릭 또는 `streamlit run app.py`

---

## 노드 구조 (6-노드)

```
[열 입력: W 표면]
      ↓
  0: W surface     — W 타겟 표면 (포컬스팟 조사 지점)
  1: W bulk        — W 타겟 내부 평균
  2: BTi5          — W/Cu 접합 브레이징 층 (6680 kg/m³, k=10~40 W/m·K)
  3: Cu top        — Cu 상단 원통부
  4: Cu body       — Cu 핀 방열부
  5: Oil           — 절연유 (KS C 2301 1종 4호)
      ↓
  Ambient (293.15 K, 고정 경계)
```

---

## 파일 구조

| 파일 | 역할 |
|------|------|
| `app.py` | Streamlit UI 진입점. 사이드바 입력 → 솔버 호출 → 결과 탭 표시 |
| `thermal_solver.py` | 솔버 인터페이스(`IThermalSolver`), `RCSolver`, `HybridFDSolver` |
| `thermal_rc.py` | 6-노드 집중 RC ODE 구현 (`solve_rc`). RCSolver가 내부적으로 사용 |
| `waveform.py` | 조사 조건 → 전력 트레이스(t, P) 변환. DC 단발/사이클/Pulse 지원 |
| `beam.py` | 전력 계산 (`P = kV × mA`), 열유속 변환 |
| `geometry.py` | 튜브 형상 (`TubeGeometry`), 포컬스팟 면적, 열저항/열용량 계산 |
| `materials.py` | 재료 물성 상수 (W, Cu, BTi5, Oil) |
| `conditions.py` | `ExposureCondition`, `OilCondition` 데이터클래스 |
| `damage.py` | 손상 판정 (`judge`), `DamageLevel`, `DamageVerdict`, `_THRESHOLDS` |
| `fem_model.py` | Phase 2 플레이스홀더 — `NotImplementedError` 상태 |
| `tests/` | 61개 단위 테스트 (pytest) |
| `실행.bat` | 더블클릭 실행용 배치 파일 |

---

## 솔버 구조

### RCSolver (Phase 1.0a)
- 6-노드 집중 파라미터 RC ODE
- `scipy.integrate.solve_ivp` Radau 방법으로 시간 적분
- 비교/검증 용도로 유지

### HybridFDSolver (Phase 1.0b, 기본값)
- **W 슬랩**: 1D 유한차분법 N=20 노드 (z방향만, 횡방향 없음)
- **BTi5/Cu/Oil**: 집중 RC 체인
- `t_eval=t_arr` 지정 필수 — 없으면 OFF 구간 포인트 누락됨

---

## 핵심 설계 결정 및 제약

### 열확산 깊이 (δ)
```
δ = √(α_W × t_on)    α_W = 6.54e-5 m²/s
상한: W 반두께 (0.48 mm)
```
W 표면 노드 두께와 RC 열용량 계산에 사용.

### 1D 한계 (가장 큰 오차 원인)
- 횡방향(r 방향) 열확산 미반영
- t > 100 ms에서 W 표면 온도를 실제보다 높게 계산
- 단기 조사(< 10 ms): 영향 작음 / 장기 DC 조사: 영향 큼

### BTi5 열전도율 민감도
- 기본값 k=20 W/m·K, 범위 10~40 W/m·K
- 사이드바에서 변경 가능. BTi5/Cu 온도에 ±20~30% 영향

### DC 사이클 샘플링
```python
# waveform.py _dc_trace()
dt = max(min(on_time / 100.0, off_time / 10.0), 1e-4)
```
on_time과 off_time 균형 샘플링. 변경 시 샘플 수 초과(_MAX_SAMPLES=100,000) 주의.

### 손상 임계값
| 레벨 | 조건 |
|------|------|
| WARNING1 | BTi5 ≥ 700°C |
| DAMAGE1 | BTi5 ≥ 840°C (고상선) |
| DAMAGE2 | BTi5 ≥ 880°C (액상선) |
| DAMAGE3 | Cu body ≥ 1085°C |
| DAMAGE4 | W surface ≥ 2500°C |
| FAILURE | W surface ≥ 3422°C (용융) |
| OIL_WARNING | Oil ≥ 100°C |
| OIL_DANGER | Oil ≥ 150°C (인화점) |

---

## 테스트

```bash
pytest tests/ -v
# 61개 테스트, 전체 통과 확인됨 (2026-05-11 기준)
```

주요 테스트 파일:
- `test_beam.py`: 전력 계산 검증
- `test_geometry.py`: 형상/면적 계산
- `test_damage.py`: 손상 판정 로직
- `test_physics_oracle.py`: 물리 일관성 검증
- `test_validation.py`: 검증 케이스 (실험 데이터 미확보, 추후 추가 예정)

---

## Phase 로드맵

| 단계 | 내용 | 상태 |
|------|------|------|
| Phase 1.0a | 6-노드 RC 솔버 | ✅ 완료 |
| Phase 1.0b | W 슬랩 1D-FD + RC 하이브리드 | ✅ 완료 |
| Phase 2 | W 슬랩 2D-FDM (r-z 축대칭, 횡방향 포함) | 🔲 미구현 |
| Phase 3 | 실험 데이터 검증 및 재료 물성 보정 | 🔲 대기 중 |

---

## 작업 시 주의사항

- `thermal_solver.py`와 `thermal_rc.py` 양쪽 모두 `t_eval=t_arr` 유지할 것
- `_MAX_SAMPLES = 100_000` 초과 시 `ValueError` 발생 — DC 사이클 긴 조건에서 주의
- `fdm2d_solver.py`는 Phase 2 인플라이트 (`phase2-2dfdm` 브랜치). US-2부터 구현 진행 중
- `st.cache_data`가 `run_sim()`에 적용됨 — 입력값 동일 시 재계산 없음
- 재료 물성 변경 시 `materials.py`만 수정하면 전체 반영됨
