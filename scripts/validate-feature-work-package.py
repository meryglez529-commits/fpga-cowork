#!/usr/bin/env python3
"""Validate a Mode 3 FPGA feature work package.

This is a guardrail for documentation/evidence structure. It does not judge RTL
correctness.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


REQUIRED_FILES = [
    "REQUIREMENTS.md",
    "ARCHITECTURE.md",
    "IMPLEMENTATION.md",
    "sim/SIM_REPLAY.md",
]

CORE_REQUIRED_DIRS = [
    "sim",
    "out",
    "out/sim",
]

OPTIONAL_STAGE_DIRS = [
    "out/regression",
    "out/synth",
    "out/impl",
    "out/bitstream",
    "out/ila",
    "out/hw_debug",
]

IMPLEMENTATION_PATTERNS = [
    ("current conclusion/status", re.compile(r"当前结论|状态", re.IGNORECASE)),
    ("implementation order", re.compile(r"实施顺序|执行顺序|变更记录")),
    ("verification/evidence", re.compile(r"仿真|综合|实现|ILA|证据", re.IGNORECASE)),
]

REPLAY_PATTERNS = [
    ("testbench/top", re.compile(r"testbench|仿真 top|tb_", re.IGNORECASE)),
    ("GUI command", re.compile(r"source .*run_gui|Vivado GUI|Tcl Console", re.IGNORECASE)),
    ("project-runner command", re.compile(r"run_sim\.tcl|launch_simulation|PowerShell|batch", re.IGNORECASE)),
    ("pass/fail criteria", re.compile(r"通过标准|PASS|FAIL", re.IGNORECASE)),
]

PLACEHOLDER_RE = re.compile(r"<[^>\n]+>")
PASS_RE = re.compile(r"\b(PASS|BUILD PASS|errors\s*=\s*0|0 ERROR)\b", re.IGNORECASE)


def read_text(path: Path) -> str:
    for enc in ("utf-8", "utf-8-sig", "gbk"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    return path.read_bytes().decode("utf-8", errors="replace")


def validate(unit: Path, project_root: Path | None) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if not unit.is_dir():
        return [f"unit directory not found: {unit}"], warnings

    for d in CORE_REQUIRED_DIRS:
        if not (unit / d).is_dir():
            errors.append(f"missing directory: {d}")

    missing_optional_dirs = [d for d in OPTIONAL_STAGE_DIRS if not (unit / d).is_dir()]
    if missing_optional_dirs:
        warnings.append(
            "optional stage directories not present yet: "
            + ", ".join(missing_optional_dirs)
        )

    for f in REQUIRED_FILES:
        p = unit / f
        if not p.is_file():
            errors.append(f"missing file: {f}")
        elif p.stat().st_size == 0:
            errors.append(f"empty file: {f}")

    impl = unit / "IMPLEMENTATION.md"
    if impl.is_file():
        text = read_text(impl)
        for label, rx in IMPLEMENTATION_PATTERNS:
            if not rx.search(text):
                errors.append(f"IMPLEMENTATION.md missing {label}")

        pass_logs: list[str] = []
        for stage in ("out/sim", "out/regression", "out/synth", "out/impl", "out/bitstream", "out/ila", "out/hw_debug"):
            for log in (unit / stage).glob("*.log"):
                if PASS_RE.search(read_text(log)):
                    pass_logs.append(log.relative_to(unit).as_posix())
        unreferenced_pass_logs: list[str] = []
        for log in pass_logs:
            if log not in text:
                unreferenced_pass_logs.append(log)
        if unreferenced_pass_logs:
            sample = ", ".join(unreferenced_pass_logs[:5])
            suffix = "" if len(unreferenced_pass_logs) <= 5 else f" (+{len(unreferenced_pass_logs) - 5} more)"
            warnings.append(
                "PASS-like evidence not referenced in IMPLEMENTATION.md: "
                + sample
                + suffix
            )

    replay = unit / "sim" / "SIM_REPLAY.md"
    if replay.is_file():
        text = read_text(replay)
        for label, rx in REPLAY_PATTERNS:
            if not rx.search(text):
                errors.append(f"sim/SIM_REPLAY.md missing {label}")
        placeholders = PLACEHOLDER_RE.findall(text)
        if placeholders:
            warnings.append(f"sim/SIM_REPLAY.md still has placeholders: {', '.join(sorted(set(placeholders))[:8])}")

    if not any((unit / "out" / sub).glob("*") for sub in ("sim", "regression", "synth", "impl", "bitstream", "ila", "hw_debug")):
        warnings.append("no evidence files found under out/* yet")

    if project_root:
        # Stale-doc heuristic: changed RTL/scripts newer than implementation doc.
        if impl.is_file():
            impl_time = impl.stat().st_mtime
            candidates = []
            for pattern in ("**/*.v", "**/*.sv", "**/*.vhd", "**/*.xdc", "**/*.tcl"):
                candidates.extend(project_root.glob(pattern))
            newer = [
                p for p in candidates
                if "AI-work" not in p.parts and p.is_file() and p.stat().st_mtime > impl_time
            ]
            if newer:
                warnings.append(
                    "project source/script files are newer than IMPLEMENTATION.md; "
                    "verify the unit status is synced"
                )

    return errors, warnings


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Validate a Mode 3 feature work package.")
    parser.add_argument("unit", type=Path, help="Path to AI-work/features/<feature>/<UNIT>")
    parser.add_argument("--project-root", type=Path, default=None)
    parser.add_argument("--strict", action="store_true", help="Treat warnings as errors")
    args = parser.parse_args(argv)

    errors, warnings = validate(args.unit, args.project_root)
    for warning in warnings:
        print(f"WARN: {warning}")
    if errors:
        print(f"FAIL: {args.unit}")
        for error in errors:
            print(f"  - {error}")
        return 1
    if args.strict and warnings:
        print(f"FAIL (strict): {args.unit}")
        return 1
    print(f"PASS: {args.unit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
