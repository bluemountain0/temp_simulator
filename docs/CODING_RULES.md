# CODING_RULES — 코딩 규칙

> 글로벌 행동 지침(단순하게/외과적 수정/커밋/한국어 종결/파일 헤더/에러 읽기)은
> `~/.claude/CLAUDE.md`에 있다. 여기는 이 프로젝트 고유 규칙만.

## 1. 단위 (SI 강제)

모든 내부 계산은 SI 단위. UI 표시용 변환은 출력 직전에만.

| 물리량 | 내부 단위 | UI 표시 |
|--------|----------|---------|
| 온도 | K (Kelvin) | °C |
| 길이 | m | mm 또는 cm |
| 시간 | s | s, ms |
| 전력 | W | W |
| 전류 | A (mA 직접 입력 후 곱셈) | mA |
| 전압 | V (kV 입력 후 곱셈) | kV |
| 면적 | m² | mm² |
| 부피 | m³ (L → 1e-3) | L |

**규칙**: 함수 인자가 비SI라면 변수명에 단위 접미사 명시 (`vessel_w_cm`, `cu_immersion_mm`).

## 2. 물리 상수 위치

- 재료 물성(ρ, cp, k, T_melt) → `materials.py`
- 도면 치수 → `geometry.TubeGeometry` 기본값
- 손상 임계값 → `damage._THRESHOLDS`
- 수치 한계(`MAX_T_EXPOSURE_SURFACE`, `_MAX_SAMPLES`) → 해당 모듈 상단 module-level

**다른 곳에 매직넘버 금지.** 단, 0/1/2 같은 인덱스·차원 상수는 제외.

## 3. 네이밍

- 노드 인덱스 상수: `NODE_W_SURFACE = 0`, `NODE_BTI5 = 2` 등 대문자
- 온도 변수: `T_`(K), 변환 후엔 `_C` 접미사
- 시간: `t_arr`(배열), `t_exp`(스칼라), `on_time`/`off_time`
- 행렬: 6×6은 `R`, 6-벡터는 `C` (열저항/열용량 관례)
- 솔버 클래스: `XxxSolver`로 끝남
- 데이터클래스: `XxxCondition`, `XxxResult`, `XxxVerdict`

## 4. 함수 크기 가이드라인

- 일반 함수: 50줄 이내 목표
- 솔버 `solve()`: 예외적으로 100~150줄 허용 (RHS 클로저 포함)
- 함수가 80줄 넘으면 분리 검토. 단, 분리하면 ODE 클로저가 깨지는 경우 예외.

## 5. 예외 처리

- 솔버 수렴 실패 → `assert sol.success, f"..."` (스택 트레이스로 디버깅)
- 입력 검증 실패 → `ValueError`만 사용 (예: `_check_samples()`)
- **broad `except Exception` 금지.** 어떤 예외인지 명시.
- 물리적으로 불가능한 상황(음수 면적 등)은 검증하지 않는다. 입력 단계에서 막을 것.

## 6. 로깅

- 현재 외부 로깅 없음. Streamlit `st.warning()` / `st.info()`로 사용자 알림.
- 디버깅용 `print()`는 커밋 전 제거.

## 7. 타입 힌트

- 함수 시그니처는 타입 힌트 권장 (필수는 아님)
- 데이터클래스는 모든 필드 타입 명시
- `Literal[...]`로 enum 대체 가능 (`ExposureCondition.mode`)

## 8. 테스트

- 모든 수치 비교는 `pytest.approx` 사용
- 물리 일관성(단조성, 보존, 클램프 등)을 oracle 테스트로 명시
- 새 임계값/상수 추가 시 회귀 테스트 1개 이상

## 9. Streamlit 특화

- `st.cache_data`로 감싸진 함수 내부에서 mutable 객체 반환 금지
- 입력 위젯은 `st.sidebar` 안에 묶기 (UI 일관성)
- Plotly 그래프 트레이스는 모듈 상수 `NODE_COLORS` / `THRESHOLD_LINES` 사용

## 10. 의존성 추가

`requirements.txt` 외 라이브러리 추가 시 사용자 승인 필수. 현재 의존:
- streamlit ≥1.30, scipy ≥1.11, numpy ≥1.26, plotly ≥5.18, pandas ≥2.1, pytest ≥7.4
