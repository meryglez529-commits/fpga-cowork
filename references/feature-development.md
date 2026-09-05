# Feature Development and Change Verification (Mode 3)

> Mode 3 changes a defined FPGA design behavior and records why the behavior, source boundary, and selected evidence are correct. It invokes S, B, H, and D only when the changed requirement or an evidence gap requires them.

Use Mode 3 for authorized RTL, XDC, IP, block-design, or project behavior changes. Do not use it for a simulation-only request, an unchanged-image build, an existing-image ILA capture, or a read-only report investigation; use S, B, H, or D directly for those requests.

## 1. Boundary and work package

Create one unit under `AI-work/features/<feature-slug>/<UNIT>/` before editing authorized design files. Mode 3 may start without Mode 1. Reuse a Mode 1 guide when one exists; otherwise record only the project root, authorized source boundary, and uncertainty relevant to this change.

| Item | Requirement |
|---|---|
| Requirement | Confirm behavior, interfaces, units, legal ranges, and out-of-scope behavior before RTL changes. |
| Authority | Reuse `AI-work/env/RULES.md` when present; otherwise record the user-authorized design root and files in the unit. |
| Scope | List every RTL/XDC/IP/BD/project file changed. Do not call a passive ILA probe addition a business-function change. |
| Evidence plan | Select only needed S, B, H, and D flows, with an oracle and stop condition for each. |
| Continuation | Read the smallest relevant status, evidence, and changed inputs; rerun only invalidated flows. |

When entering from Mode 4, read its `MODE3_HANDOFF.md`, acceptance matrix, dependency matrix, and applicable reuse manifest before editing a shared path. Mark affected demo evidence `STALE`; never copy a demo-only source into product to avoid that dependency.

### Default unit layout

```text
AI-work/features/<feature>/<UNIT>/
  REQUIREMENTS.md
  ARCHITECTURE.md
  IMPLEMENTATION.md
  RTL_REVIEW.md                 # broad or multi-file handoff only
  sim/ build/ hardware/ diagnostics/    # only when the matching flow is used
  out/sim/ out/build/ out/ila/ out/diagnostics/ out/regression/
  evidence/ diagrams/
```

The flow folders are packets, not mandatory stages. Keep outer tool logs and result summaries under the matching `out/` directory; native project waveforms, run products, and captures remain in the project-owned locations defined by their flow.

## 2. Requirements, architecture, and implementation

`REQUIREMENTS.md` states the physical/business problem, relevant signals and units, existing paths reused, exclusions, and confirmed versus open decisions. If an unknown changes RTL behavior, stop and ask rather than encode a guess.

`ARCHITECTURE.md` describes data/trigger/control paths, insertion point, old-mode preservation, CDC/FIFO/memory implications, and selected evidence flows. A nontrivial change includes a CDC table plus an evidence table that maps each acceptance question to S, B, H, or D and states its limit. An exact latency needs both endpoints in one clocked observation or a verified common timestamp/cross-trigger; separate ILA captures prove correlation or ordering, not exact latency.

Record exact changed files, rationale, review risk, and selected-flow status in `IMPLEMENTATION.md`. Add `RTL_REVIEW.md` for a broad/multi-file handoff. Before editing a shared clock/reset, interface core, or board constraint, map the effect through an applicable Mode 4 dependency matrix.

## 3. Compose S, B, H, and D

| Flow | Call from Mode 3 when | Record in the unit |
|---|---|---|
| S — 项目仿真 | Changed behavior needs a self-checking test, waveform, or regression. | Scope, oracle, result, and project-native WDB/WCFG paths. |
| B — 构建与 bitstream | Changed input requires build evidence, or a debug image must be generated. | Requested runs, timing/resource outcome, and bit/LTX identity. |
| H — 硬件与 ILA/VIO | Board observation is needed after a qualified image exists. | Capture declaration, target/core/image identity, observation, and conclusion limit. |
| D — 只读诊断 | Existing evidence must be explained before selecting or changing a flow. | Diagnosis result, cited evidence, and bounded next action. |

Adding a passive ILA probe is an H+B debug-image change with explicit source and build authorization. If it also changes product behavior, it is both a Mode 3 change and an H+B activity. Never claim that a terminal-state capture retroactively proves an earlier startup sequence.

Do not run S merely because source changed, B merely because an ILA exists, or H merely because a bitstream was generated. Link each selected flow packet and result from `IMPLEMENTATION.md`.

## 4. Artifact containment and completion

| Artifact | Destination |
|---|---|
| Outer S/B/H tool logs and result summaries | This unit's `out/<flow>/<id>/` |
| Project XSim WDB/WCFG and XSim logs | `<project>.sim/<sim-set>/behav/xsim/` |
| Project build products, reports, bit/LTX | Named project run locations |
| Native Hardware Manager state and `.ila` | `<project>.hw/<hw-set>/` and `<project>.hw/backup/` |
| D excerpts and conclusion | This unit's `out/diagnostics/<id>/` |

Create an artifact marker before a tool flow and run `scripts/scan-artifact-spill.py` when available before closing a broad unit. Do not delete, relocate, or rewrite pre-existing user artifacts to satisfy a validator.

Synchronize only affected records: changed acceptance in `REQUIREMENTS.md`, changed architecture/evidence plan in `ARCHITECTURE.md`, changed source/build/image/execution state in `IMPLEMENTATION.md`, and a meaningful unit transition in `AI-work/LOG.md`. Mode 3 is complete when the authorized behavior change, selected evidence, and known limits are reviewable. It is not necessary to run every flow.
