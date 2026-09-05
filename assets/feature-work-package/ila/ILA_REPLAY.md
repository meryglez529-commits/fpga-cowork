# ILA Replay

Use this packet for one hardware ILA capture in an existing Vivado project.
The canonical procedure is the project Hardware SOP:
`fpga-cowork/references/hardware-debug-environment.md`.

## Capture declaration

| Field | Value |
|---|---|
| Decision question | `<one observable fact>` |
| Project / hardware set | `<absolute project.xpr>` / `hw_1` |
| Exact JTAG target / device | `<target>` / `<device>` |
| Qualified image | `<absolute impl_1 bit>` + `<absolute matching ltx>` |
| Exact ILA `CELL_NAME` | `<hierarchical cell name>` |
| Capture id | `<unique safe label>` |
| Policy | `program` or qualified `reuse` |
| Expected observation | `<what proves or disproves the question>` |

If the bit/LTX does not contain the required probe, record `PROBE_GAP`; do not
start a capture. A new ILA is created in the original project source/IP tree
and built through its original runs, as defined by the Hardware SOP.

## Preflight and replay

Create a fresh result directory: standalone H uses
`AI-work/hardware/<capture-id>/`, while a Mode 3/4 caller uses
`AI-work/features/<feature>/<UNIT>/out/ila/<capture-id>/`. Preflight only the
project-owned Hardware workspace, then run the canonical runner once:

```powershell
powershell -ExecutionPolicy Bypass -File <skill>/scripts/check-hw-occupancy.ps1 `
  -Project <project>.xpr -HwSet hw_1

& <vivado.bat> -mode batch -source <skill>/scripts/templates/run_ila.tcl `
  -log <AI-run>/vivado.log -journal <AI-run>/vivado.jou -tclargs `
  <project>.xpr hw_1 <target> <device> <bit> <ltx> <ila-cell-name> `
  <capture-id> <AI-run> USER_AUTHORIZED program
```

The runner opens the project before Hardware Manager, resets the one selected
core to all-don't-care, performs an immediate bounded capture, and exports one
native file to `<project>.hw/backup/<capture-id>.ila`. AI-work retains only
the command log, `ILA_CAPTURE_RESULT.txt`, and the interpretation; it never
receives a copied `.ila`, WDB, or WCFG.

## Result and review

`ILA_CAPTURE_PASS` requires the exact target/device/core, a full capture, a
non-empty native `.ila`, and no new `D:/hw_ila_data_*` directory. Record the
absolute project-native path, selected probes, observed values/timing, and
scope limit in the unit result directory.

For visual review, open the original project in Vivado and load the native
`.ila` from `<project>.hw/backup/`; do not rerun hardware merely to inspect an
existing capture.
