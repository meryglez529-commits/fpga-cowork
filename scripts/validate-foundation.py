#!/usr/bin/env python3
"""Validate Mode 1 architecture-reading artifacts only.

No build manifest, simulator log, hardware record, or global baseline is
required. This script must never be used to validate an individual simulation.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


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
    guide = ai_work / "guide" / "FPGA_PROJECT_GUIDE.md"
    rules = ai_work / "env" / "RULES.md"
    paths_dir = ai_work / "guide" / "data-paths"

    for path, label in ((guide, "project guide"), (rules, "custody rules")):
        if not path.is_file() or not read_text(path).strip():
            errors.append(f"missing or empty {label}: {path}")

    if guide.is_file():
        text = read_text(guide)
        for label, pattern in {
            "engineering entry evidence": r"\.xpr|\.qpf|project|工程文件",
            "architecture or hierarchy": r"架构|层级|hierarchy|module|模块",
            "clock/reset evidence": r"clock|clk|时钟|reset|rst",
            "data-path evidence": r"数据链路|data.path|DAC|ADC|DDR|Ethernet|以太网",
        }.items():
            if not re.search(pattern, text, re.IGNORECASE):
                errors.append(f"project guide missing {label}")

    deep_reads = list(paths_dir.glob("*_DEEP_READ.md")) if paths_dir.is_dir() else []
    if not deep_reads:
        warnings.append("no data-path guide found; document an explicit scope exclusion in FPGA_PROJECT_GUIDE.md")
    for path in deep_reads:
        text = read_text(path)
        for label, pattern in {
            "source evidence": r"\.v(?::\d+)?|\.sv(?::\d+)?|文件位置|证据",
            "reading entry": r"搜索入口|search|打开",
            "scope boundary": r"先忽略|范围|boundary|忽略",
        }.items():
            if not re.search(pattern, text, re.IGNORECASE):
                errors.append(f"{path.name} missing {label}")
    return errors, warnings


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Validate Mode 1 architecture-reading artifacts.")
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
