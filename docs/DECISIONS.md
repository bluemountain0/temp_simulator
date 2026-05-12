# DECISIONS — 설계 결정 기록

> 중요한 설계 결정과 그 근거. 한 번 적은 결정은 지우지 않고 "Superseded" 표시.

## 형식

```
## YYYY-MM-DD — 결정 제목
- **결정**: 무엇을 했나
- **이유**: 왜 그렇게 했나
- **대안**: 검토했으나 채택 안 한 옵션
- **영향**: 이 결정이 어디에 묶이는가
- **상태**: Active / Superseded by [yyyy-mm-dd 결정]
```

---

## 2026-05-11 — Phase 1.0b 기본 솔버를 HybridFDSolver로 채택

- **결정**: `app.py` 기본 솔버 = `HybridFDSolver` (RCSolver는 비교용 잔존)
- **이유**: 6-노드 RC만으로는 W 표면의 순간 가열을 과소 평가. W 슬랩만 1D-FD로 분해(N=20)하여 표면 정확도 개선
- **대안**:
  - RC 6노드만 유지 → W 표면 정확도 부족
  - 2D FEM 즉시 도입 → 개발 비용, 솔버 시간 과다
- **영향**: `thermal_solver.HybridFDSolver`, `app.py`에서 기본 호출
- **상태**: Active

## 2026-05-11 — `MAX_T_EXPOSURE_SURFACE` 도입

- **결정**: 열확산 깊이 `δ = √(α·t)`가 W 반두께를 넘으면 클램프
- **이유**: 장기 조사(t > ~14ms) 시 단순 RC가 발산. W 두께 한계로 자연 한계 적용
- **대안**: 사용자에게 경고만 표시 → 수치 폭주 위험
- **영향**: `thermal_rc.MAX_T_EXPOSURE_SURFACE`, `effective_t_exposure()`, `effective_delta()`
- **상태**: Active

## 2026-05-11 — 손상 8단계 + Oil 별도 경고

- **결정**: `DamageLevel` 8단계 (SAFE/WARNING1/DAMAGE1~4/FAILURE) + OIL_WARNING/OIL_DANGER 분리
- **이유**:
  - 700°C는 BTi5 고상선(840°C) 17% 안전 마진
  - Oil은 인화점(150°C) 기준 — 손상이 아니라 안전 문제
- **대안**: 단일 레벨 + 노드 표기만 → 우선순위 정렬 모호
- **영향**: `damage._THRESHOLDS`, `app.py LEVEL_COLORS`
- **상태**: Active

## 2026-05-11 — BTi5 k 기본값 20 W/m·K, 범위 10~40

- **결정**: BTi-5 열전도율 기본 20 W/m·K, 사이드바에서 조정 가능
- **이유**: 문헌 산포 큼(10~40). 단일 값 고정보다 sensitivity 분석 가능하게
- **대안**: 정확값 측정 → 측정 비용/시간
- **영향**: `materials.BTi5.k`, `materials.bti5_with_k()`, GUI 슬라이더
- **상태**: Active

## 2026-05-11 — 6-노드 집중 RC + W 슬랩 분해 하이브리드

- **결정**: BTi5/Cu_top/Cu_body/Oil은 집중 RC, W만 1D-FD
- **이유**:
  - W 표면이 손상 판정 1차 변수 → 정확도 우선
  - BTi5/Cu/Oil은 열용량이 크고 변화 느림 → 집중 RC로 충분
- **대안**:
  - 전체 1D-FD → 솔버 비용 증가, 효율 손실
  - 전체 집중 RC → W 표면 정확도 부족 (Phase 1.0a 상태)
- **영향**: `HybridFDSolver` 구조, 상태 벡터 N+4
- **상태**: Active

## 2026-05-11 — Ambient를 고정 boundary로 모델링

- **결정**: ambient = 293.15 K 고정, Oil → ambient 대류만 표현
- **이유**: Phase 1 스코프에서 환경 변동 무시 가능 (실내 운용 가정)
- **대안**: Ambient를 노드로 추가 → 7 노드, 외기 데이터 필요
- **영향**: `thermal_rc.T_AMBIENT_K`, `R_to_amb` 벡터
- **상태**: Active

## 2026-05-11 — Pulse 고주파(>10Hz) 모드는 평균전력 트레이스 + peak 보정

- **결정**: 100 Hz 이상 펄스는 ODE 시간축을 평균전력으로 풀고, W 표면 peak는 단일 펄스 분석해로 가산
- **이유**: 마이크로초 단위로 ODE 적분하면 샘플 수 폭주
- **대안**: 모든 펄스를 직접 적분 → `_MAX_SAMPLES` 초과
- **영향**: `waveform._pulse_trace()`, `thermal_rc.solve_rc()` peak 보정 블록, `HybridFDSolver` 동일 보정
- **상태**: Active

## 2026-05-12 — 하네스 엔지니어링 도입

- **결정**: `docs/` 디렉토리에 PROJECT_MAP/ARCHITECTURE/CODING_RULES/TESTING/DEBUGGING/QUALITY_SCORE/TECH_DEBT/DECISIONS 8개 영구 문서 + `scripts/check_project_health.py` 추가. `CLAUDE.md` 신규 생성 (AGENTS.md는 기존 유지)
- **이유**: AI 에이전트가 점진적으로 필요한 문서만 읽고 작업할 수 있는 구조 마련. 글로벌 OMC 규칙과 중복 없이 프로젝트 고유 지식 분리
- **대안**:
  - AGENTS.md 하나에 모두 통합 → 길이 증가, AI 컨텍스트 부담
  - OMC wiki/notepad에만 저장 → git 추적/공개 검토 불가
- **영향**: AI 작업 워크플로, 신규 기여자 온보딩
- **상태**: Active
