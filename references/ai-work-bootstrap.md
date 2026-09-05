# AI-work Bootstrap

Use this reference only for an explicit Mode 1 request. Mode 1 creates a compact, read-only architecture knowledge base; it is not an environment qualification or a build baseline.

## Determine the engineering root

Prefer a directory containing a Vivado `*.xpr`, Quartus `*.qpf`, or the project’s creation Tcl. If the user already named the design root, use it. Record the selected root and evidence boundary in `AI-work/env/RULES.md`; do not infer facts from generated `.runs`, `.gen`, `.cache`, or `.Xil` trees.

## Minimal Mode 1 skeleton

```text
AI-work/
  README.md
  LOG.md
  OPEN-QUESTIONS.md
  .gitignore
  env/
    RULES.md
  guide/
    FPGA_PROJECT_GUIDE.md
    data-paths/
      <DL*>_DEEP_READ.md
```

Create `annotations/`, `features/`, `bringup/`, `sim/`, `scripts/`, or `reports/` only when a later request needs them. Do not create empty directories to imitate a full project-management system.

`README.md` names this directory’s purpose and current reading scope. `RULES.md` identifies the official design root and says that Mode 1 is read-only. `LOG.md` records meaningful reading-state changes. `OPEN-QUESTIONS.md` holds only unresolved architecture facts; it is not a substitute for tool or hardware diagnostics.

## Mode 1 custody

- Read official source, project metadata, constraints, and IP configuration as evidence.
- Write only the listed `AI-work/` artifacts.
- Do not launch Vivado, run a simulator, create a testbench, modify `.xpr`, configure a linter, or write an engineering source file.
- Do not create baseline manifests, build reports, tool reports, or hardware inventory records.
- Do not delete, normalize, or rewrite existing `AI-work` material outside the requested reading scope.

If `AI-work/` already exists, load `README.md`, `LOG.md`, `OPEN-QUESTIONS.md`, `env/RULES.md`, and only the requested guide(s). Update the affected documents in place; do not use missing historical environment or build records as a reason to expand the task.
