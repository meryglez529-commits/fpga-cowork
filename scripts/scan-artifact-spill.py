#!/usr/bin/env python3
"""Scan for runtime artifacts spilled outside authorized generated-output paths.

This helps Mode 3 and Mode 4 avoid leaving Vivado/xsim/ILA outputs in D: root or the
project root. It reports findings only; it never moves or deletes files.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import fnmatch
import sys
from pathlib import Path


DEFAULT_PATTERNS = [
    "vivado*.log",
    "vivado*.jou",
    "vivado*.str",
    "xvlog.log",
    "xelab.log",
    "xsim.log",
    "xvlog.pb",
    "xsim.dir",
    "hw_ila_data_*",
    "*.wdb",
    "*.wcfg",
    "*.vcd",
]


def is_inside_ai_work(path: Path) -> bool:
    return "AI-work" in path.parts


def is_project_xsim_output(path: Path) -> bool:
    """Allow only Vivado's standard <project>.sim/<set>/behav/xsim tree."""
    parts = [part.lower() for part in path.parts]
    for index, part in enumerate(parts):
        if part.endswith(".sim") and parts[index + 2:index + 4] == ["behav", "xsim"]:
            return True
    return False


def parse_since(value: str) -> float:
    text = value.strip()
    dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return dt.timestamp()


def scan(root: Path, patterns: list[str], max_depth: int, min_mtime: float | None) -> list[Path]:
    root = root.resolve()
    findings: list[Path] = []
    for p in root.rglob("*"):
        try:
            rel = p.relative_to(root)
        except ValueError:
            continue
        if len(rel.parts) > max_depth:
            continue
        if is_inside_ai_work(p) or is_project_xsim_output(p):
            continue
        if min_mtime is not None and p.stat().st_mtime <= min_mtime:
            continue
        name = p.name
        if any(fnmatch.fnmatch(name, pat) for pat in patterns):
            findings.append(p)
    return sorted(findings)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Find runtime artifacts outside AI-work.")
    parser.add_argument("root", type=Path, help="Project root or broader directory to scan")
    parser.add_argument("--max-depth", type=int, default=4)
    parser.add_argument("--pattern", action="append", default=[], help="Additional glob pattern")
    parser.add_argument("--since", help="Only report artifacts modified after ISO time, e.g. 2026-06-05T11:30:00")
    parser.add_argument("--since-file", type=Path, help="Only report artifacts newer than this file's mtime")
    args = parser.parse_args(argv)

    if args.since and args.since_file:
        print("FAIL: use only one of --since or --since-file")
        return 2

    min_mtime = None
    if args.since_file:
        if not args.since_file.exists():
            print(f"FAIL: since-file not found: {args.since_file}")
            return 2
        min_mtime = args.since_file.stat().st_mtime
    elif args.since:
        try:
            min_mtime = parse_since(args.since)
        except ValueError as exc:
            print(f"FAIL: invalid --since value {args.since!r}: {exc}")
            return 2

    patterns = DEFAULT_PATTERNS + args.pattern
    findings = scan(args.root, patterns, args.max_depth, min_mtime)
    if findings:
        print("ARTIFACT SPILL:")
        for p in findings:
            print(f"  - {p}")
        return 1
    print(f"PASS: no spilled runtime artifacts under {args.root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
