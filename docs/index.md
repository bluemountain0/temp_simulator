# 문서 허브

X-ray 애노드 열손상 예측 시뮬레이터의 모든 영구 지식은 여기서 시작한다.

## 진입 문서

- [../CLAUDE.md](../CLAUDE.md) — AI 작업 지도 (가장 먼저 읽기)
- [../AGENTS.md](../AGENTS.md) — 물리 모델·노드 구조·솔버 상세
- [../README.md](../README.md) — 사용자용 (있을 때)

## 네비게이션

| 목적 | 문서 |
|------|------|
| 어떤 기능이 어떤 파일에 있나 | [PROJECT_MAP.md](PROJECT_MAP.md) |
| 솔버 구조·데이터 흐름·의존성 | [ARCHITECTURE.md](ARCHITECTURE.md) |
| 코딩 규칙·네이밍·단위 | [CODING_RULES.md](CODING_RULES.md) |
| 작업 순서·5개 작업 모드 | [DEVELOPMENT_WORKFLOW.md](DEVELOPMENT_WORKFLOW.md) |
| 테스트 실행·체크리스트 | [TESTING.md](TESTING.md) |
| 디버깅·자주 발생하는 문제 | [DEBUGGING.md](DEBUGGING.md) |
| 품질 점수·우선순위 | [QUALITY_SCORE.md](QUALITY_SCORE.md) |
| 기술부채·임시 구현 | [TECH_DEBT.md](TECH_DEBT.md) |
| 설계 결정 기록 | [DECISIONS.md](DECISIONS.md) |

## 실행 계획

- 진행 중: [exec-plans/active/](exec-plans/active/)
- 완료: [exec-plans/completed/](exec-plans/completed/)
- 템플릿: [exec-plans/template.md](exec-plans/template.md)

## 문서 작성 규칙

- 코드와 불일치하면 **문서를 업데이트**한다 (코드를 맞추지 않는다).
- 확인 못 한 내용은 `> ⚠ 확인 필요` 마커로 표시.
- 새 설계 결정 → `DECISIONS.md`에 날짜와 함께 추가.
- 임시 우회 코드 → `TECH_DEBT.md`에 즉시 기록.
