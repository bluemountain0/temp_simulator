# QUALITY_SCORE — 영역별 품질 점수

> 최종 갱신: 2026-05-12 (Phase 1.0b 시점)
> 등급: A(우수) / B(양호) / C(개선 필요) / D(취약)

| 영역 | 등급 | 문제점 | 개선 방향 | 우선순위 |
|------|------|--------|----------|----------|
| 솔버 코어 (`thermal_*`) | B+ | 1D 가정, Phase 2 미구현 | 2D-FDM 도입 (Phase 2) | 중 |
| 형상/물성 (`geometry`, `materials`) | A- | 핀 두께 추정값 0.8 mm | 도면 정확 수치 확보 | 중 |
| 손상 판정 (`damage`) | A | 임계값 출처 문서화 일부 부족 | DECISIONS.md에 출처 보강 | 낮 |
| 파형 생성 (`waveform`) | B | `_MAX_SAMPLES` 하드코딩, 저주파 Pulse 샘플 효율 | adaptive sampling 검토 | 낮 |
| UI (`app.py`) | B- | 단일 파일 ~300줄, 비즈니스 로직 일부 섞임 | 결과 렌더링 분리 검토 | 낮 |
| 테스트 커버리지 | B | 61개 통과, 실험 데이터 검증 케이스 0 | Phase 3 실험 검증 | **높** |
| 문서화 | A- | 하네스 구축 직후, 일부 불일치 여지 | 정기 점검 (월 1회) | 낮 |
| 빌드/배포 | C | `실행.bat`만 존재, requirements 잠금 없음 | `requirements.lock` 또는 poetry | 중 |
| CI/CD | D | 없음 | GitHub Actions로 pytest 자동화 | 중 |
| 수치 안정성 검증 | C+ | Radau rtol=1e-4 고정, 적응성 미검증 | 솔버 비교 회귀 추가 | 중 |

## 우선순위 행동 항목

### 높음
1. **Phase 3 실험 데이터 확보** — `test_validation.py`에 실제 측정값 기반 케이스 추가

### 중간
2. **Phase 2 2D FEM** — `fem_model.py` 구현 (사용자 결정 후 진행)
3. **빌드 잠금** — `pip freeze > requirements.lock` 또는 poetry 도입
4. **CI 도입** — `.github/workflows/test.yml`로 push마다 pytest

### 낮음
5. **app.py 렌더링 분리** — 그래프 함수를 `ui_render.py`로
6. **임계값 출처 보강** — `DECISIONS.md`에 W 2500°C·BTi5 840°C 근거 추가

## 점수 갱신 규칙

- 큰 기능 추가/리팩터링 후 갱신
- Phase 전환 시 전체 재평가
- 등급 하향 시 `TECH_DEBT.md`에 동시 기록
