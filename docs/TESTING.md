# TESTING — 테스트 가이드

## 실행 명령

```bash
pytest tests/ -v                              # 전체 실행 (61개)
pytest tests/test_validation.py -v            # 회귀 테스트만
pytest tests/ -k "hybrid" -v                  # 키워드 필터
pytest tests/ --collect-only                  # 케이스 목록만
```

## 테스트 파일별 책임

| 파일 | 검증 영역 | 케이스 수 (대략) |
|------|----------|------------------|
| `test_beam.py` | 전력 계산 (kV·mA, peak/avg 변환) | ~5 |
| `test_geometry.py` | 형상·면적·열저항·열용량 | ~15 |
| `test_damage.py` | DamageLevel 판정 로직, 임계값 경계 | ~15 |
| `test_physics_oracle.py` | 물리 일관성 (단조성, 보존, 클램프) | ~15 |
| `test_validation.py` | 기준 케이스 회귀 (100kV·12mA·50s 등) | 11 |

총 ~61개. 정확한 개수는 `pytest tests/ --collect-only -q`로 확인.

## 최소 검증 기준 (PR/커밋 직전)

1. `pytest tests/ -v` → 전부 통과
2. 변경 영역의 새 케이스 1개 이상 추가
3. 변경된 임계값/상수 → 회귀 케이스 업데이트

## 기능별 테스트 체크리스트

### 솔버 변경 시
- [ ] `test_validation.py`의 기준 케이스 통과
- [ ] `test_physics_oracle.py` 일관성 통과 (에너지·단조성)
- [ ] 새 솔버라면 `ThermalResult.T.shape == (6, N)` 검증
- [ ] BTi5 k 민감도 (`test_bti5_k_sensitivity`)
- [ ] 강제대류 (`test_forced_convection_lower_temp`)

### 손상 판정 변경 시
- [ ] 경계값 ±1 K 테스트
- [ ] DamageLevel 단조성 (높은 노드 > 낮은 노드)
- [ ] OIL_WARNING / OIL_DANGER 동시 위반 시 우선순위

### 파형 변경 시
- [ ] `test_dc_cyclic_n_cycles_temperature_accumulates`
- [ ] DC 단발 / DC 사이클 / Pulse(>10Hz) / Pulse(≤10Hz) 4가지 모드
- [ ] `_MAX_SAMPLES` 초과 케이스에서 ValueError

### 형상 변경 시
- [ ] `focal_spot_area()` 검증값 (1.1×0.75×12° → ~3.97e-6 m²)
- [ ] `thermal_capacities()` 에너지 보존 (`C[0]+C[1] == ρ·cp·V`)
- [ ] `fin_surface_area_total()` 핀 위치 경계 처리

## 수동 검증 (Streamlit GUI)

자동 테스트가 커버하지 못하는 영역:

1. `streamlit run app.py` 실행
2. 기본 입력 (100 kV, 12 mA, 10s DC) → 손상 단계 배너 표시 확인
3. BTi5 k 슬라이더 10 → 40 변경 시 W 표면 온도 감소 확인
4. Pulse 모드 100Hz·duty=0.1 → peak envelope 그래프 표시
5. 캐시 동작: 동일 입력 재실행 시 지연 거의 없음 확인

> ⚠ 확인 필요: 현재 자동 UI 테스트는 없음. Phase 3에서 Playwright 또는 streamlit testing API 도입 검토.

## OMC 통합

- `/verify` 또는 `verifier` 에이전트로 자동 완료 검증 가능
- `qa-tester` 에이전트로 실험적 GUI 검증 위임 가능

## 새 테스트 추가 가이드

```python
# tests/test_xxx.py 첫 줄에 한국어 한 줄 주석
"""<영역명> 단위 테스트."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
import numpy as np
# 필요한 모듈 import

def test_describe_what_in_korean_or_english():
    # Arrange
    # Act
    # Assert (pytest.approx로 수치 비교)
```

- 테스트 함수명은 `test_<기능>_<조건>_<기대>` 패턴
- 수치 비교는 항상 `pytest.approx(expected, rel=1e-4)`
- 물리적 의미 있는 메시지 (`f"Expected ≥ DAMAGE4, got {verdict.level.name}"`)
