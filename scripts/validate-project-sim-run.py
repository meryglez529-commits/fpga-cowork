#!/usr/bin/env python3
"""Validate one project-simulation analysis directory without scanning AI-work."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


SUCCESS_RESULTS = {"SIM_PASS", "SIM_FAIL", "SIM_COMPLETED"}
REQUIRED_FIELDS = {
    "result",
    "project",
    "sim_set",
    "top",
    "testbench",
    "runtime",
    "xsim_dir",
    "project_wdb",
    "project_wcfg",
    "compile_log",
    "elaborate_log",
    "simulate_log",
}


def parse_result(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def validate(run_dir: Path) -> list[str]:
    result_file = run_dir / "SIMULATION_RESULT.txt"
    if not result_file.is_file():
        return [f"missing result file: {result_file}"]
    values = parse_result(result_file)
    errors = [f"missing result field: {name}" for name in sorted(REQUIRED_FIELDS - values.keys())]
    if errors:
        return errors

    result = values["result"]
    if result not in SUCCESS_RESULTS:
        return [f"result is not a completed simulation: {result}"]

    testbench = Path(values["testbench"])
    xsim_dir = Path(values["xsim_dir"])
    if not testbench.is_file():
        errors.append(f"testbench does not exist: {testbench}")
    normalized_tb = testbench.as_posix().lower()
    expected_fragment = f".srcs/{values['sim_set'].lower()}/new/"
    if expected_fragment not in normalized_tb:
        errors.append(f"testbench is not under the selected sim-set source tree: {testbench}")
    if not xsim_dir.is_dir():
        errors.append(f"XSim directory does not exist: {xsim_dir}")

    artifacts = {name: Path(values[name]) for name in ("project_wdb", "project_wcfg", "compile_log", "elaborate_log", "simulate_log")}
    for name, artifact in artifacts.items():
        if not artifact.is_file():
            errors.append(f"missing project artifact {name}: {artifact}")
        elif artifact.parent != xsim_dir:
            errors.append(f"project artifact outside xsim_dir {name}: {artifact}")
    wdb = artifacts["project_wdb"]
    wcfg = artifacts["project_wcfg"]
    if wdb.stem != wcfg.stem:
        errors.append(f"WDB/WCFG basename mismatch: {wdb.name} / {wcfg.name}")
    return errors


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Validate one scoped project-simulation run.")
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args(argv)
    errors = validate(args.run_dir)
    if errors:
        print(f"FAIL: {args.run_dir}")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(f"PASS: {args.run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
