# CLAUDE.md — X-ray 애노드 열손상 예측 시뮬레이터

> 이 파일은 AI 작업의 **진입점이자 지도**다. 세부 내용은 `docs/`로 위임한다.
> 글로벌 규칙(단순하게/외과적 수정/커밋/한국어 종결/파일 헤더/에러 읽기 등)은
> `~/.claude/CLAUDE.md`에서 상속받으므로 여기서는 중복 기술하지 않는다.

## 프로젝트 한 줄 요약

X-ray 고정 애노드의 W → BTi5 → Cu → Oil 열전달을 1D RC + FD 하이브리드로
풀어 손상 단계를 판정하는 Streamlit 시뮬레이터 (Phase 1.0b).

## 절대 규칙

- **물리 상수·치수는 `materials.py` / `geometry.py`에서만 수정.** 다른 곳에 하드코딩 금지.
- **솔버는 `IThermalSolver` 인터페이스를 깬다.** 새 솔버는 같은 시그니처로.
- **`t_eval=t_arr` 지정 유지.** RC/HybridFD 양쪽 모두 OFF 구간 샘플링에 필요.
- **`fem_model.py`는 Phase 2 플레이스홀더.** 사용자 승인 없이 구현하지 말 것.
- **완료 선언 전 반드시 `pytest tests/ -v` 실행 후 결과 보고.**

## 작업 시작 전 읽을 문서

1. [docs/PROJECT_MAP.md](docs/PROJECT_MAP.md) — 기능별 파일 위치
2. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — 솔버 구조, 데이터 흐름
3. [AGENTS.md](AGENTS.md) — 물리 모델 상세, 노드 구조, 설계 결정

## 작업 유형별 참조 문서

| 작업 | 우선 참조 |
|------|----------|
| 새 기능 추가 | `docs/DEVELOPMENT_WORKFLOW.md` → `docs/PROJECT_MAP.md` → `docs/CODING_RULES.md` |
| 버그 수정 | `docs/DEBUGGING.md` → 관련 파일 + 테스트 |
| 솔버 변경 | `AGENTS.md` 솔버 구조 → `docs/DECISIONS.md` → `thermal_solver.py` |
| 손상 판정 변경 | `damage.py` + `AGENTS.md` 임계값 표 |
| UI/그래프 변경 | `app.py` (300줄, 단일 파일) |
| 테스트 추가 | `docs/TESTING.md` |

## 구현 전 체크리스트

- [ ] 요청을 한 줄로 다시 쓸 수 있는가
- [ ] 관련 파일을 `docs/PROJECT_MAP.md`에서 식별했는가
- [ ] 대형 작업이면 `docs/exec-plans/active/<작업명>.md` 작성했는가
- [ ] 기존 테스트가 어떤 동작을 보장하는지 확인했는가

## 구현 후 체크리스트

- [ ] `pytest tests/ -v` 통과
- [ ] 변경된 설계 결정이 있다면 `docs/DECISIONS.md` 업데이트
- [ ] 미해결 이슈는 `docs/TECH_DEBT.md` 추가
- [ ] 새 파일은 첫 줄에 한국어 한 줄 주석으로 역할 명시
- [ ] 논리적 변경 단위 1개 → 즉시 커밋

## 사용자 판단이 필요한 경우 (에스컬레이션)

다음은 임의 진행하지 말고 사용자에게 확인:

- 재료 물성값(`materials.py`) 또는 도면 치수(`geometry.py`) 변경
- 손상 임계값(`damage.py`의 `_THRESHOLDS`) 조정
- 새 솔버 추가 (Phase 2 FEM 등)
- 의존성 추가 (numpy/scipy/streamlit/plotly/pandas 외)
- 테스트 케이스 삭제 또는 기대값 변경

## OMC 통합

이 프로젝트는 OMC 플러그인과 함께 운영된다. 다음 워크플로 활용:

- 대형 작업 계획 수립 → `/ralplan` 또는 `/plan`
- 자율 실행 → `/autopilot`, `/ralph`
- 코드 리뷰 → `code-reviewer` 에이전트
- 완료 검증 → `verifier` 에이전트 또는 `/verify`

## 빠른 명령어

```bash
streamlit run app.py        # GUI 실행
pytest tests/ -v             # 전체 테스트
python scripts/check_project_health.py   # 하네스 상태 점검
```
