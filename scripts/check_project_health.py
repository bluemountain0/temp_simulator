# 하네스 엔지니어링 문서 체계와 코드 상태를 검증하는 헬스 체크 스크립트
"""
사용: python scripts/check_project_health.py

다음을 확인한다:
- 필수 문서 파일 존재 여부
- CLAUDE.md / AGENTS.md 길이가 권장 범위 안인지
- 큰 소스 파일 목록
- TODO/FIXME 개수
- pytest 명령이 문서에 등장하는지

종료 코드: 0 = 정상, 1 = 경고/실패 항목 있음
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent.parent
MAX_AGENTS_LINES = 160
MAX_CLAUDE_LINES = 100
LARGE_FILE_THRESHOLD = 400  # 줄 수

REQUIRED_FILES = [
    "CLAUDE.md",
    "AGENTS.md",
    "docs/index.md",
    "docs/PROJECT_MAP.md",
    "docs/ARCHITECTURE.md",
    "docs/CODING_RULES.md",
    "docs/DEVELOPMENT_WORKFLOW.md",
    "docs/TESTING.md",
    "docs/DEBUGGING.md",
    "docs/QUALITY_SCORE.md",
    "docs/TECH_DEBT.md",
    "docs/DECISIONS.md",
    "docs/exec-plans/template.md",
]

PYTHON_SOURCE_GLOBS = ["*.py", "tests/*.py"]

# 결과 누적
errors: list[str] = []
warnings: list[str] = []
infos: list[str] = []


def ok(msg: str) -> None:
    print(f"[OK]   {msg}")


def warn(msg: str) -> None:
    warnings.append(msg)
    print(f"[WARN] {msg}")


def err(msg: str) -> None:
    errors.append(msg)
    print(f"[ERR]  {msg}")


def info(msg: str) -> None:
    infos.append(msg)
    print(f"[INFO] {msg}")


def count_lines(path: Path) -> int:
    return sum(1 for _ in path.open(encoding="utf-8", errors="ignore"))


def check_required_files() -> None:
    print("\n=== 필수 문서 ===")
    for rel in REQUIRED_FILES:
        p = ROOT / rel
        if p.exists():
            ok(f"{rel} exists")
        else:
            err(f"{rel} 누락")


def check_doc_lengths() -> None:
    print("\n=== 문서 길이 ===")
    claude = ROOT / "CLAUDE.md"
    if claude.exists():
        n = count_lines(claude)
        if n <= MAX_CLAUDE_LINES:
            ok(f"CLAUDE.md = {n} lines (<= {MAX_CLAUDE_LINES})")
        else:
            warn(f"CLAUDE.md = {n} lines, 권장 {MAX_CLAUDE_LINES} 이내")
    agents = ROOT / "AGENTS.md"
    if agents.exists():
        n = count_lines(agents)
        if n <= MAX_AGENTS_LINES:
            ok(f"AGENTS.md = {n} lines (<= {MAX_AGENTS_LINES})")
        else:
            warn(f"AGENTS.md = {n} lines, 권장 {MAX_AGENTS_LINES} 이내")


def iter_python_files() -> Iterable[Path]:
    seen: set[Path] = set()
    for top in ["", "tests", "scripts"]:
        d = ROOT / top if top else ROOT
        if not d.exists():
            continue
        for p in d.glob("*.py"):
            if p not in seen:
                seen.add(p)
                yield p


def check_large_files() -> None:
    print("\n=== 큰 소스 파일 ===")
    for p in iter_python_files():
        n = count_lines(p)
        rel = p.relative_to(ROOT)
        if n >= LARGE_FILE_THRESHOLD:
            warn(f"Large file: {rel} = {n} lines")
        else:
            ok(f"{rel} = {n} lines")


def check_todos() -> None:
    print("\n=== TODO/FIXME ===")
    pattern = re.compile(r"\b(TODO|FIXME|XXX)\b")
    total = 0
    for p in iter_python_files():
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        hits = pattern.findall(text)
        if hits:
            rel = p.relative_to(ROOT)
            info(f"{rel}: {len(hits)} TODO/FIXME")
            total += len(hits)
    info(f"TODO 총 개수: {total}")


def check_test_command_documented() -> None:
    print("\n=== 테스트 명령 문서화 ===")
    needles = ["pytest tests/", "pytest tests"]
    docs_to_check = ["CLAUDE.md", "AGENTS.md", "docs/TESTING.md"]
    for rel in docs_to_check:
        p = ROOT / rel
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        if any(n in text for n in needles):
            ok(f"{rel} contains pytest command")
        else:
            warn(f"{rel} does NOT mention pytest 실행 명령")


def check_exec_plan_dirs() -> None:
    print("\n=== exec-plans 디렉토리 ===")
    for sub in ["active", "completed"]:
        d = ROOT / "docs" / "exec-plans" / sub
        if d.exists():
            ok(f"docs/exec-plans/{sub}/ 디렉토리 존재")
        else:
            info(f"docs/exec-plans/{sub}/ 미생성 (필요 시 자동 생성됨)")


def summary() -> int:
    print("\n=== 요약 ===")
    print(f"errors:   {len(errors)}")
    print(f"warnings: {len(warnings)}")
    print(f"infos:    {len(infos)}")
    if errors:
        print("\n실패 항목:")
        for e in errors:
            print(f"  - {e}")
        return 1
    if warnings:
        print("\n경고 항목:")
        for w in warnings:
            print(f"  - {w}")
        return 1
    return 0


def main() -> int:
    print(f"프로젝트 루트: {ROOT}")
    check_required_files()
    check_doc_lengths()
    check_large_files()
    check_todos()
    check_test_command_documented()
    check_exec_plan_dirs()
    return summary()


if __name__ == "__main__":
    sys.exit(main())
