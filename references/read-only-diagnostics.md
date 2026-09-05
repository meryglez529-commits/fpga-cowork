# Read-only Diagnostics Flow (D)

Use this flow to explain existing simulation failures, synthesis or timing
reports, IP/source-resolution warnings, implementation failures, or existing
board/capture evidence without changing the design or executing another tool
stage. It is an independent, low-authority flow and may also be called after an
S, B, or H result is blocked or fails.

## 1. Boundary

Before inspection, state the exact question and the minimum authoritative
inputs: for example, an existing `simulate.log`, `runme.log`, timing report,
Vivado journal, project file list, or exported ILA result. Read only the files
that can resolve that question.

D may search, parse, compare, and summarize existing evidence. It must not:

- edit RTL, XDC, IP, block designs, project settings, or generated outputs;
- create a testbench, change a simulation top, run a simulation, reset or
  launch a build, program hardware, or arm an ILA;
- start Vivado or Hardware Manager merely to obtain a new report;
- delete, move, repair, or regenerate an existing artifact.

Do not turn a diagnostic request into a Mode 1 architecture audit. If a fix is
required, report the smallest next authorized flow: Mode 3 for a behavior/design
change, S for a test, B for a build, or H for board observation.

## 2. Evidence and output

For a standalone diagnosis, use a new directory:

```text
AI-work/diagnostics/<diagnostic-id>/
```

When D is called by an active Mode 3 or Mode 4 unit, use that unit's
`out/diagnostics/<diagnostic-id>/`. Write a concise `DIAGNOSIS_RESULT.md` with:

- decision question and examined absolute paths;
- decisive log/report excerpts with line numbers or report sections;
- classified cause: confirmed, likely, or not established;
- affected scope and an explicitly bounded next step, if any;
- what D did not execute or prove.

Never copy large native logs, WDB/WCFG, bitstreams, or `.ila` files into this
directory. Store only the analysis and small command/output excerpts needed to
reproduce the conclusion.

## 3. Results and stop conditions

| Result | Meaning |
|---|---|
| `DIAGNOSIS_COMPLETE` | Existing evidence supports a bounded cause/conclusion. |
| `DIAGNOSIS_INCONCLUSIVE` | Evidence is absent, contradictory, or insufficient; name the smallest additional authorized action. |
| `DIAGNOSIS_BLOCKED` | The required existing evidence cannot be read or its identity is unknown. |

Stop after classification. D never claims that a proposed repair works; that
requires the relevant follow-on flow and its own evidence.
