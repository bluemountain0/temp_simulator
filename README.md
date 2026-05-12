# X-ray 애노드 열손상 예측 시뮬레이터

X-ray 튜브 고정 애노드의 W 표면 → BTi5 → Cu → Oil 열전달을 1D RC + FD 하이브리드로
풀어 손상 단계를 8단계로 판정하는 Streamlit 웹앱.

- **단계:** Phase 1.0b (HybridFDSolver)
- **모델 신뢰도:** ±30~50% (1D 가정, 횡방향 열확산 미반영)
- **Python:** 3.13

## 빠른 실행

```bash
pip install -r requirements.txt
streamlit run app.py
```

Windows에서는 `실행.bat` 더블클릭으로도 실행된다.

## 테스트

```bash
pytest tests/ -v          # 61개 테스트
```

## 문서

| 대상 | 문서 |
|------|------|
| Claude Code · AI 에이전트 | [CLAUDE.md](CLAUDE.md) |
| 물리 모델 · 노드 구조 · 솔버 설계 | [AGENTS.md](AGENTS.md) |
| 전체 문서 허브 | [docs/index.md](docs/index.md) |
| 기능 → 파일 매핑 | [docs/PROJECT_MAP.md](docs/PROJECT_MAP.md) |
| 아키텍처 · 의존성 · 가정 | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| 설계 결정 기록 | [docs/DECISIONS.md](docs/DECISIONS.md) |
| 기술부채 | [docs/TECH_DEBT.md](docs/TECH_DEBT.md) |

## 폴더 구조 (요약)

```
anode_damage_model/
├── app.py                 ← Streamlit UI
├── thermal_solver.py      ← IThermalSolver + HybridFDSolver
├── thermal_rc.py          ← RC ODE 구현
├── geometry.py            ← 형상·열저항·열용량
├── materials.py           ← 재료 물성 상수
├── waveform.py / beam.py  ← 조사 파형·전력
├── conditions.py          ← 입력 데이터클래스
├── damage.py              ← 손상 단계 판정
├── tests/                 ← pytest 61개
├── docs/                  ← 영구 지식베이스
└── scripts/               ← 헬스 체크
```

## 의존성

`requirements.txt` 참조. 정확한 버전 잠금은 `requirements.lock`.

## 라이선스

내부 연구용 (LICENSE 미지정).
