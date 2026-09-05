#!/usr/bin/env python3
"""Validate the minimal AI-work skeleton created by explicit Mode 1 work.

This validator deliberately knows nothing about project simulation, build, board,
feature, or bring-up evidence. Use their scoped validators instead.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


REQUIRED_DIRS = ("guide", "guide/data-paths", "env")
REQUIRED_FILES = (
    "README.md",
    "LOG.md",
    "OPEN-QUESTIONS.md",
    ".gitignore",
    "env/RULES.md",
    "guide/FPGA_PROJECT_GUIDE.md",
)


def read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def validate(ai_work: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not ai_work.is_dir():
        return [f"AI-work directory not found: {ai_work}"], warnings

    for directory in REQUIRED_DIRS:
        if not (ai_work / directory).is_dir():
            errors.append(f"missing directory: AI-work/{directory}")
    for relative in REQUIRED_FILES:
        path = ai_work / relative
        if not path.is_file():
            errors.append(f"missing file: AI-work/{relative}")
        elif not read_text(path).strip():
            errors.append(f"empty file: AI-work/{relative}")

    log = ai_work / "LOG.md"
    if log.is_file() and not re.search(r"\d{4}-\d{2}-\d{2}", read_text(log)):
        warnings.append("LOG.md has no dated entry")
    questions = ai_work / "OPEN-QUESTIONS.md"
    if questions.is_file() and not re.search(r"\|", read_text(questions)):
        warnings.append("OPEN-QUESTIONS.md has no structured question table")
    return errors, warnings


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Validate minimal Mode 1 AI-work artifacts.")
    parser.add_argument("ai_work", type=Path)
    parser.add_argument("--strict", action="store_true", help="treat warnings as errors")
    args = parser.parse_args(argv)
    errors, warnings = validate(args.ai_work)
    for warning in warnings:
        print(f"WARN: {warning}")
    if errors:
        print(f"FAIL: {args.ai_work}")
        for error in errors:
            print(f"  - {error}")
        return 1
    if args.strict and warnings:
        print(f"FAIL (strict): {args.ai_work}")
        return 1
    print(f"PASS: {args.ai_work}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
