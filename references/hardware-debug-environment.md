# Hardware and ILA/VIO Flow (H)

Use this flow for every Vivado ILA/VIO capture, qualified-image programming, or
bounded board observation in an existing project. It is independent of Mode 3:
an existing-image capture uses H directly, while Mode 3 and Mode 4 may call H
when their evidence plan requires board observation. It is the Hardware Manager
equivalent of Flow S: one native project workspace, one bounded runner, and a
small AI analysis record.

## 1. Ownership and locations

| Item | Required location |
|---|---|
| ILA/VIO IP, RTL instances, constraints, bit/LTX | Existing project source tree and `impl_1` run |
| Hardware Manager project state and native ILA WDB/WCFG | `<project>.hw/<hw-set>/` (normally `hw_1`) |
| Exported ILA capture | `<project>.hw/backup/<capture-id>.ila` |
| Command log, capture plan, identities, oracle, and interpretation | Standalone `AI-work/hardware/<capture-id>/`, or the calling unit's `out/ila/<capture-id>/` |

The `.hw` tree is normal persistent Vivado project state, just as `.sim` is
normal persistent XSim state. Do not make `AI-work` the Hardware Manager
working directory and do not copy project-native `.ila`, WDB, or WCFG data
there.

## 2. Decide whether the existing image is sufficient

Start with a capture declaration and probe review in the active result packet.
If the qualified matching bit/LTX already exposes the selected signal and
clock domain, do not build: use `reuse` only after the image identity was
qualified, or use the explicitly authorized `program` policy to load that
exact pair.

If the required signal is absent, record `PROBE_GAP` and make one authorized
debug-image change. The path is the same one used by Vivado GUI:

1. Open the original `<project>.xpr`; do not clone, flatten, or create an
   AI-work Vivado project.
2. Create and generate the RTL-instantiated ILA IP in the existing
   `<project>.srcs/sources_1/ip/` tree, and let Vivado register its `.xci` in
   the original project.
3. Instantiate that IP only in the approved official RTL, keeping the
   project's existing filesets, BD, generated IP outputs, and wrappers.
4. Use the original `synth_1` and `impl_1` runs to `write_bitstream`. Running
   an authorized debug build may replace those runs; do not copy their inputs
   into an isolated build or hand-copy a BD/IP/wrapper.
5. Take the `.bit` and `.ltx` produced by that same `impl_1` run into the
   capture interface below. A core mismatch during the runner's exact
   `CELL_NAME` check is a failed image pairing, not a reason to try another
   core opportunistically.

This is an H+B debug-image change, not a read-only capture. It requires
explicit source and build authorization. It may be recorded in a Mode 3/4 unit
when it supports that work, but does not itself require a business-feature
change or Mode 3.

## 3. Preflight only the project Hardware output

Before capture, inspect the exact Hardware workspace:

```powershell
powershell -ExecutionPolicy Bypass -File <skill>/scripts/check-hw-occupancy.ps1 `
  -Project <project>.xpr -HwSet hw_1
```

An open Vivado GUI is not itself a blocker. A locked `hw.xml`, relevant native
Hardware WDB/WCFG, or an output-access error is `ILA_OUTPUT_LOCKED`; report it
and stop. Do not kill a process, move hardware data, or switch to a standalone
Hardware Manager session.

## 4. Run one scoped capture

Declare before programming Hardware Manager:

| Input | Requirement |
|---|---|
| Project / hardware set | Existing `.xpr` and hardware set, normally `hw_1` |
| Target / device | Exact Hardware target name and FPGA device name |
| Image | Exact matching bit/LTX pair; choose `program` or authorized `reuse` explicitly |
| Core | One ILA identified by exact `CELL_NAME`; do not use an ordinal `hw_ila_N` as identity |
| Capture | Unique label and the runner's reset-to-all-don't-care, immediate-trigger policy |
| Check | Target/part/core identity, completed capture, non-empty project-native `.ila`, and no new D-root spill |

Use the supplied runner through Vivado:

```powershell
& <vivado.bat> -mode batch -source <skill>/scripts/templates/run_ila.tcl `
  -log <AI-run>/vivado.log -journal <AI-run>/vivado.jou -tclargs `
  <project>.xpr <hw-set> <hw-target> <device> <bit> <ltx> <ila-cell-name> `
  <capture-id> <AI-run> USER_AUTHORIZED ?program|reuse?
```

The runner opens the project before Hardware Manager, binds the session to the
project `.hw` workspace, uses only the declared target/device/core, waits 15 s
after programming before refreshing, and writes the selected capture to
`<project>.hw/backup/<capture-id>.ila`. Before each default capture it calls
`reset_hw_ila -reset_compare_values true`, then uses `run_hw_ila -trigger_now`
and a 10-second bounded wait. Thus the capture is explicitly immediate with all
probe comparisons disabled; it never inherits stale GUI trigger settings. It
does not enumerate or display every ILA core and does not write business
registers or start product behavior.

`program` is the default. `reuse` is permitted only when the current image and
LTX were already qualified for this batch; it skips reconfiguration but still
sets the probes file and verifies the requested core.

The template implements only that default immediate capture. A custom trigger
or a trigger that can wait indefinitely needs a unit-local scenario wrapper
with an explicit timeout and stop condition.

## 5. Results and stop conditions

| Result | Meaning |
|---|---|
| `ILA_CAPTURE_PASS` | Exact target/device/core captured and a non-empty `.ila` exists under `<project>.hw/backup/`. |
| `ILA_OUTPUT_LOCKED` | The project Hardware workspace is occupied. Stop before opening Hardware Manager. |
| `ILA_SETUP_BLOCKED` | Project, image, target, device, core, label, or authorization is invalid. |
| `ILA_CORE_NOT_READY` | The declared core is still absent after the bounded post-program refresh. |
| `ILA_CAPTURE_TIMEOUT` | The immediate capture did not fill the declared ILA buffer within 10 seconds. |
| `ILA_CAPTURE_FAIL` | Hardware capture or native export failed. |
| `ILA_ARTIFACT_SPILL` | A new `D:/hw_ila_data_*` appeared. Leave it in place, report it, and repair project binding before another capture. |

After the run, write a concise report in the declared AI result directory with
the oracle and absolute project-native `.ila` path. Do not copy native capture
data into AI-work or modify unrelated project documents. If existing evidence
is insufficient to explain a result, stop the capture batch and use D rather
than repeating an equivalent capture.
