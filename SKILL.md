---
name: fpga-cowork
description: Safely understand and change FPGA/RTL projects, or run scoped simulation, build, hardware, and read-only diagnostic flows for existing Vivado projects.
metadata:
  version: 1.0.0
---

# FPGA Co-work

Use this skill to keep official FPGA sources, project-owned tool output, and AI analysis distinct. Select the smallest task mode and only the operational flows that answer the user's question. The four Modes express intent; S, B, H, and D are composable operational flows, not extra Modes.

## Classify requests before opening sources

| Intent Mode | Use when | Outcome | Read first |
|---|---|---|---|
| **Mode 1 — 工程接手与架构阅读** | User explicitly asks to take over, map, organize, or establish shared understanding of an existing project. | `AI-work/` plus a project guide and data-path reading guides. | `references/ai-work-bootstrap.md`, `references/reading-workflow.md`, `references/data-path-deep-reading.md`, `references/foundation-setup.md`, `references/output-format.md` |
| **Mode 2 — 单文件精读 / 注释** | User asks to explain, read closely, annotate, or compare a source file. | Evidence-backed explanation, or an authorized comment-only closure annotation. | `references/single-file-close-reading.md` |
| **Mode 3 — 功能开发与变更验证** | User asks to add, change, or fix a design's RTL/XDC/IP behavior. | One resumable feature unit under `AI-work/features/`. | `references/feature-development.md` |
| **Mode 4 — 新板卡开发与接口 Bring-up** | User has a new/planned board and needs an FPGA baseline from schematics or interface requirements. | A board bring-up unit, demos, and a Mode 3 handoff. | `references/new-board-development.md`, `references/ai-work-bootstrap.md` |

| Operational flow | Use when | Standalone output | Read first |
|---|---|---|---|
| **S — 项目仿真** | Run a testbench, inspect a waveform, or verify a named DUT/scenario. | `AI-work/sim/<test-id>/` | `references/simulation-environment.md` |
| **B — 构建与 bitstream** | Synthesize, implement, check timing, or generate a bitstream for a declared project/run. | `AI-work/build/<build-id>/` | `references/build-environment.md` |
| **H — 硬件与 ILA/VIO** | Program or reuse a qualified image, capture one ILA/VIO scenario, or perform a bounded board observation. | `AI-work/hardware/<capture-id>/` | `references/hardware-debug-environment.md` |
| **D — 只读诊断** | Explain existing logs, reports, source/IP resolution, or prior evidence without executing a new stage. | `AI-work/diagnostics/<diagnostic-id>/` | `references/read-only-diagnostics.md` |

A simulation-only request uses S directly. A source/behavior change uses Mode 3 and then only the needed S/B/H/D flows. A build-only or capture-only request uses B or H directly; it does not require Mode 3. An explicit request for a new board uses Mode 4 and its needed flows. Do not enter Mode 1 merely because a request contains “仿真” or “诊断”.

## Shared custody and evidence rules

- Official RTL, XDC, IP, block designs, project files, testbenches, and fixtures remain in the user-confirmed design root.
- For an established Vivado set, testbenches and stable fixtures belong in `<project>.srcs/<sim-set>/new` (normally `sim_1/new`). WDB, same-basename WCFG, XSim logs, journals, and `xsim.dir` belong in `<project>.sim/<sim-set>/behav/xsim`.
- For established Vivado Hardware Manager state, use `<project>.hw/<hw-set>/` (normally `hw_1`) for native ILA wave state and `<project>.hw/backup/` for exported `.ila` captures. Open the `.xpr` before Hardware Manager so Vivado binds to this project-owned hardware workspace.
- `AI-work` contains only analysis, replay metadata, documentation, reports, and AI-owned feature or bring-up work. Never copy ordinary project-local XSim or Hardware Manager waveform/capture outputs into it.
- Do not create a history directory or move old XSim output before a rerun. A rerun may overwrite the current project-owned output in place.
- Before an action, define the decision question, minimum evidence, restoration needed, and stop condition. Do not expand a local task into a project audit.
- Never modify unrelated historical reports or manifests merely to satisfy a validator.

## Flow S — 项目仿真

Use this flow for ordinary simulation of an existing Vivado project, either standalone or as a selected verification flow of Mode 3/4.

1. Resolve the project, existing sim set, DUT, selected top, testbench, optional fixture map, finite runtime, and any requested check.
2. Before launch, inspect only the exact `<project>.sim/<sim-set>/behav/xsim` output directory. Use `scripts/check-sim-occupancy.ps1` or an equivalent read-only lock check. A Vivado GUI process is **not** a blocker unless it actually holds a file in that directory. If the directory is occupied, report `SIM_OUTPUT_LOCKED` and stop; do not kill a process or move output.
3. Reuse the existing sim set. Put a newly needed testbench in `<project>.srcs/<sim-set>/new`; add it to that sim set and make it the selected top. This is normal persistent project simulation state. Do not create a parallel sim set and do not apply an automatic `temporary`/restore workflow.
4. Use `scripts/templates/run_sim.tcl` through Vivado’s project simulation manager. It sets the declared finite XSim runtime before `launch_simulation`, keeps the selected top/testbench membership, and saves a WCFG beside the fresh WDB with the same basename.
5. Write only this run’s command, result, scope, decisive observations, and project-local artifact paths under its standalone `AI-work/sim/<test-id>/` directory or the calling unit's `out/sim/<test-id>/`. Then stop. Do not update unrelated Mode 1 or baseline records.
6. A self-checking testbench or Tcl oracle produces `SIM_PASS`/`SIM_FAIL`. Without one, a completed run with WDB/WCFG is `SIM_COMPLETED`, not a functional pass. Run only `scripts/validate-project-sim-run.py <AI-work/sim/<test-id>>` when validation is useful; never run Mode 1 validators for a project simulation.

Do not use bare `xsim`, hand-assembled `xvlog`/`xelab`, a substituted IP model, or GUI clicking as the acceptance path when an established `.xpr` sim set exists.

## Mode 1 — 工程接手与架构阅读

Mode 1 is an explicit, read-only collaboration-onboarding workflow. Its job is to make a project understandable to later engineers or sessions; it does **not** prove that Vivado, IP licenses, synthesis, implementation, bitstream generation, or hardware are usable. The user owns the prerequisite that the engineering project is usable before development begins.

Mode 1 may read official sources and write only `AI-work/`. It must not run Vivado, create testbenches, change `.xpr`, `.vscode`, RTL, XDC, IP, generated outputs, build runs, or hardware state.

Required outcomes:

```text
AI-work/
  README.md
  LOG.md
  OPEN-QUESTIONS.md
  .gitignore
  env/RULES.md
  guide/FPGA_PROJECT_GUIDE.md
  guide/data-paths/<DL*>_DEEP_READ.md
```

Create only the additional directories needed by a later route. The project guide records the engineering boundary, entry project/top, modules, clocks/resets, interfaces, and evidence limits. Data-path guides describe the identified business paths or explicitly record why a path is out of scope. Use source paths and line numbers; do not turn inferred tool or board facts into architecture facts.

Mode 1 completes at `ARCHITECTURE_READY` when those reading artifacts are sufficient for the requested scope. It has no `READY` gate and never blocks Mode 3. Run `validate-ai-work.py` and `validate-foundation.py` only when this explicit Mode 1 work is being delivered; those validators check the Mode 1 reading artifacts, not a simulation/build baseline.

## Mode 2 — 单文件精读 / 注释

Classify before editing:

- **Read-only close reading** (`解释` / `精读` / `比较`) does not authorize source edits. Trace only the active hierarchy required for an evidence-backed explanation and state generated/IP/third-party boundaries.
- **Explicit annotation** (`注释` / `添加注释` / `comment the module`) authorizes comment-only changes. Resolve the full transitive active user-RTL instantiation closure before the first edit, preserve encoding/newlines, change only comments, and write an annotation manifest.

If close reading reveals a functional defect, record it and use Mode 3 for any change.

## Mode 3 — 功能开发与变更验证

Create one unit under `AI-work/features/<feature>/<UNIT>/` before changing authorized RTL, XDC, IP, block-design, or project behavior. Mode 3 may start directly; it may reuse a Mode 1 guide when available, but must not wait for Mode 1 or a global engineering baseline. When project facts are unknown, record only the risk relevant to the feature and verify the affected scope.

Use `references/feature-development.md`. Select S, B, H, and D only when the changed requirement or evidence gap needs them. A passive debug-image probe addition belongs to H plus B with explicit source/build authorization; it is not automatically a Mode 3 business-feature change.

## Mode 4 — 新板卡开发与接口 Bring-up

Use `references/new-board-development.md` for new-board work. Keep its product baseline, demos, and Mode 3 handoff separate from an existing-project Mode 1 reading workflow. Use S/B/H/D only when the corresponding board action is required; board operations require the user’s explicit authorization for that session.

## Reference routing

- `references/ai-work-bootstrap.md`: Mode 1 minimal AI-work skeleton.
- `references/foundation-setup.md`: Mode 1 architecture-reading scope and completion.
- `references/reading-workflow.md` and `references/data-path-deep-reading.md`: project and data-path reading.
- `references/simulation-environment.md`: each S request.
- `references/build-environment.md`: each B request.
- `references/hardware-debug-environment.md`: each H request.
- `references/read-only-diagnostics.md`: each D request.
- `references/execution-discipline.md`: scope, reuse, and completion decisions for every Mode and flow.
- `references/single-file-close-reading.md`, `references/feature-development.md`, and `references/new-board-development.md`: their respective modes only.

Never claim a check passed without command output or board evidence. Do not overwrite or delete user work; stop and request direction if the authorized scope cannot be isolated.
