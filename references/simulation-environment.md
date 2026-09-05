# Project Simulation SOP

Use this reference for Flow S in an existing Vivado project. S is standalone
for a simulation-only request and may be selected by Mode 3 or Mode 4; it does
not create or update a project-wide simulation baseline.

## 1. Ownership and locations

| Item | Required location |
|---|---|
| Testbench and stable fixtures | `<project>.srcs/<sim-set>/new/` (normally `sim_1/new`) |
| Selected testbench and source membership | Existing project sim set (normally `sim_1`) |
| WDB, matching WCFG, XSim logs, generated Tcl, `xsim.dir` | `<project>.sim/<sim-set>/behav/xsim/` |
| Command, result, scope, and interpretation | Standalone `AI-work/sim/<test-id>/`, or the calling unit's `out/sim/<test-id>/` |

The project simulation set is normal persistent verification state. A requested testbench remains an official simulation source and becomes the selected top; do not create parallel sim sets and do not automatically restore the previous top or remove the testbench.

## 2. Preflight only the actual simulation output

Before launch, inspect this exact directory:

```text
<project>.sim/<sim-set>/behav/xsim/
```

Use:

```powershell
powershell -ExecutionPolicy Bypass -File <skill>/scripts/check-sim-occupancy.ps1 \
  -Project <project>.xpr -SimSet sim_1
```

The check tests exclusive access to active XSim result/log files. An open Vivado GUI is not itself a blocker. Only a locked file in that directory or a launch-time output access error is `SIM_OUTPUT_LOCKED`; report it and stop without killing processes, removing logs, or moving output.

## 3. Run one scoped simulation

Declare before running:

| Input | Requirement |
|---|---|
| DUT/scenario | The behavior to observe or verify. |
| Testbench/top | Under the official `sim_1/new` tree and selected as the `sim_1` top. |
| Runtime | A finite XSim runtime; never default unattended work to `run all`. |
| Fixture map | Only when file stimulus is used: source, format, and staged destination. |
| Check | Optional testbench assertion or Tcl oracle. Omit it for waveform-only inspection. |

Run the supplied project-level runner through Vivado:

```powershell
& <vivado.bat> -mode batch -source <skill>/scripts/templates/run_sim.tcl `
  -log <AI-work>/sim/<test-id>/vivado.log `
  -journal <AI-work>/sim/<test-id>/vivado.jou `
  -tclargs <project>.xpr <tb-file> <tb-top> <runtime> <AI-work>/sim/<test-id> `
           [oracle.tcl|-] [fixture-stage.tcl|-] [sim_1]
```

The runner adds the testbench to the existing sim set when required, retains
the selected top and runtime settings that Vivado persists in the project, sets
the XSim runtime before `launch_simulation`, and saves a WCFG with the fresh
WDB basename. It does not copy WDB/WCFG/XSim logs to `AI-work`.

## 4. Results and stop conditions

| Result | Meaning |
|---|---|
| `SIM_PASS` / `SIM_FAIL` | A declared testbench self-check or Tcl oracle passed/failed. |
| `SIM_COMPLETED` | Simulation produced the project-local WDB/WCFG, but no functional oracle was declared. |
| `SIM_OUTPUT_LOCKED` | The precise project XSim output is occupied. Stop. |
| `SIM_SETUP_BLOCKED`, `SIM_FIXTURE_BLOCKED`, `SIM_TOOL_FAIL` | Setup, fixture, compile/elaboration, launch, or artifact failure. Preserve the small analysis result and stop. |

After a normal run, write a short report under the declared S result directory
with the testbench/top, declared runtime, observed conclusion, and absolute
paths to the WDB/WCFG/logs. Do not update `AI-work/env/`, project guides, Mode
1 status, build baselines, or unrelated historical reports.

Use only the scoped validator when validation is needed:

```powershell
python <skill>/scripts/validate-project-sim-run.py <AI-work>/sim/<test-id>
```

Do not run `validate-ai-work.py`, `validate-foundation.py`, or `validate-simulation-sop.py` for a single project simulation.
