# Mode 1 — 工程接手与架构阅读

## Purpose and boundary

Mode 1 answers one question: **can a later engineer or session find its way through this FPGA project and its main business data paths?** It creates shared reading artifacts, not a claim that the project, toolchain, IP licenses, build flow, bitstream, or board are healthy.

Treat engineering usability as a user-owned prerequisite. If the user asks to
run a simulation, build, board action, or read-only tool diagnosis, route that
request to S, B, H, or D (and Mode 3/4 only when their task intent applies)
instead of expanding Mode 1.

Mode 1 is read-only with respect to the official design root. It may not start Vivado, add a testbench, edit project settings, create `.vscode/settings.json`, build any run, generate a bitstream, query hardware, or write product sources.

## Required reading artifacts

| Artifact | Required content |
|---|---|
| `AI-work/env/RULES.md` | Confirmed design root, AI-work custody boundary, and the statement that engineering usability is assumed rather than re-qualified. |
| `AI-work/guide/FPGA_PROJECT_GUIDE.md` | Project entry, top, part, constraints, source organization, system boundary, clocks/resets, architecture/module hierarchy, identified main data paths, and evidence limits. |
| `AI-work/guide/data-paths/<DL*>_DEEP_READ.md` | A reproducible reading guide for each business data path in the user-agreed scope, or an explicit exclusion and next reading entry. |
| `AI-work/OPEN-QUESTIONS.md` | Only architecture questions that cannot be resolved from the current source evidence. |

Use `reading-workflow.md` for the project guide and `data-path-deep-reading.md` for each selected path. Cite authoritative paths and line numbers. Do not replace a missing fact with tool output, filename guesses, or board assumptions.

## Execution order

1. Confirm the design root and project entry from user context or project metadata.
2. Read only the top-level ports, constraints, project metadata, and source windows needed to identify architecture and business data paths.
3. Produce the project guide, then read each user-requested or clearly primary business path. Keep non-business support paths as boundaries or exclusions rather than treating every IP as a main path.
4. Record unresolved source-level questions without launching tools to answer them.
5. Stop at `ARCHITECTURE_READY` once the requested reading scope is reproducible.

## Completion and validation

Mode 1 is complete when the architecture guide and selected data-path guides can be followed from source evidence. It does not have `SIM_READY`, `BUILD_READY`, or `READY` statuses, and it does not gate Mode 3.

For an explicit Mode 1 delivery, run only:

```powershell
python <skill>/scripts/validate-ai-work.py <project-root>/AI-work
python <skill>/scripts/validate-foundation.py <project-root>/AI-work
```

These validators inspect only the minimal AI-work and architecture-reading artifacts. They do not inspect historical simulation, synthesis, implementation, bitstream, or hardware evidence.
