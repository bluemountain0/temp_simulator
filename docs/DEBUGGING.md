# DEBUGGING — 디버깅 가이드

> 글로벌 원칙: 에러 스택 전체를 읽고, 패턴 매칭 추측 금지.

## 자주 발생하는 문제

### 1. ODE solver 실패 (`AssertionError: ODE solver 실패`)

**증상**: `assert sol.success` 가 `False`로 떨어짐.

**원인 후보**
- 입력 전력이 너무 큼 → 온도 폭주
- `_MAX_SAMPLES` 가까운 샘플 수에서 stiff 솔버 한계
- 사용자가 임의로 `rtol`/`atol` 변경
- `t_arr`에 중복 시각 또는 비단조 값

**확인 절차**
1. `print(sol.message)` 출력 (RHS 평가 실패 위치 확인)
2. `exp.kV`, `exp.mA_peak`, `exp.on_time` 값 출력 → 합리적 범위인지
3. `len(t_arr)` 확인 (`waveform._check_samples()` 통과했는지)
4. RC 행렬 NaN/Inf 검사: `np.isfinite(R).all()`

### 2. `ValueError: 시뮬레이션 시간 또는 해상도 초과`

**증상**: `waveform._check_samples()`에서 발생.

**원인**: DC 사이클 또는 저주파 Pulse에서 샘플 수가 100,000 초과.

**해결**
- 사이클 수 / 총 시간 줄이기
- Pulse 주파수 > 10 Hz로 올려 평균전력 모드 진입
- `_MAX_SAMPLES` 자체는 임시 조정하지 말 것 (메모리 폭주 위험)

### 3. W 표면 온도가 비현실적으로 높음

**증상**: 10 ms 미만 조사에서 W 표면 > 5000 K.

**원인 후보**
- `effective_delta()`가 0에 가까워 표면 노드 두께 → 0
- `MAX_T_EXPOSURE_SURFACE` 클램프 미적용
- 솔버가 RCSolver인데 t_on이 매우 짧음 (HybridFD로 전환 필요)

**확인 절차**
1. `effective_t_exposure(exp)` 값 확인 (14ms 클램프 적용됐는지)
2. `effective_delta(t_exp, geom)` 값 확인 (0.48mm 상한 적용됐는지)
3. HybridFDSolver로 다시 풀어 비교

### 4. Cu/Oil 온도가 누적되지 않음 (사이클이 무의미)

**증상**: 1사이클과 10사이클 결과가 거의 같음.

**원인**
- `OilCondition.h_oil` / `h_oil_air`가 너무 커서 모든 열이 빠져나감
- `t_eval=t_arr` 누락 → OFF 구간 샘플 없음
- DC 사이클 dt가 너무 큼

**확인 절차**
1. `t_arr` 길이와 첫 5개 / 마지막 5개 출력
2. T[4] (Cu body) 시간 추이 그래프
3. `oil_cond.h_oil=1`로 극단 테스트 → 누적 보여야 함

### 5. Streamlit 캐시가 결과를 갱신하지 않음

**증상**: 입력 바꿔도 그래프 그대로.

**원인**
- `@st.cache_data` 가 입력 동등성 판정에서 GeometryOverride 객체 차이를 못 잡음
- DataClass 필드 추가 후 캐시 해시 불일치

**해결**
- 브라우저 새로고침 (`R` 또는 Ctrl+Shift+R)
- 사이드바 메뉴 → Clear cache
- `@st.cache_data(ttl=0)`로 임시 비활성화 후 재현

### 6. 테스트 import 에러 (`ModuleNotFoundError`)

**증상**: `tests/`에서 `from thermal_solver import ...` 실패.

**원인**: PYTHONPATH 미설정.

**해결**: 테스트 파일 상단 패턴 그대로 사용
```python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
```

### 7. 에너지 보존 assert 실패

**증상**: `geometry.thermal_capacities()`에서 `AssertionError: W 열용량 에너지 보존 위반`.

**원인**: `surface_vol > V_W_total` 즉 `delta_eff > target_t` (클램프 누락).

**확인**: `effective_delta()`가 `0.5 * target_t` 상한을 반환하는지.

## 로그 확인

현재 외부 로깅 시스템 없음. 디버깅 시:

1. Streamlit 콘솔 출력: `streamlit run app.py` 실행 터미널
2. pytest 상세 출력: `pytest tests/ -v -s` (`-s`로 stdout 캡처 해제)
3. 솔버 내부 trace: `solve_ivp(..., dense_output=True)` 후 중간점 평가

## 재현 절차 표준

버그 보고/디버깅 시 다음 정보 수집:

```
- 모드: dc_single / dc_cyclic / pulse
- kV, mA_peak, on_time, off_time, cycles, freq_hz, duty
- 솔버: RCSolver / HybridFDSolver
- k_bti5, oil_cond.h_oil, oil_cond.convection_mode
- 에러 메시지 전체 (스택 트레이스)
- 기대 동작 vs 실제 동작
```

## 디버깅 체크리스트

- [ ] 에러 스택 전체를 읽었는가
- [ ] 최소 재현 케이스를 작성했는가
- [ ] 원인을 검증하는 print/log를 추가했는가 (추측 금지)
- [ ] 회귀 테스트를 먼저 작성했는가
- [ ] 수정 후 `pytest tests/ -v` 통과했는가
