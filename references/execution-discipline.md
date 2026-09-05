# FPGA Execution Discipline

Use this reference in every Mode and S/B/H/D flow to keep work resumable,
evidence-driven, and proportional. It does not create a new user-facing Mode;
it governs how much of the selected work runs in the current iteration.

## 1. Frame the iteration

Before tool actions, write a compact internal evidence plan:

- **Decision question**: the exact fact this iteration must establish.
- **Oracle**: the observable condition that distinguishes pass, fail, or blocked.
- **Minimum evidence**: the smallest authoritative source, simulation, build, readback, capture, or board observation that answers the question.
- **Restoration**: the STOP, register restore, session close, or source-state action required on exit.
- **Stop condition**: the point after which more reading, building, capture, or documentation cannot change the requested conclusion.

Static review, simulation, synthesis/implementation, and board testing are evidence levels. Select the level that can answer the question; do not automatically climb every level.

For Flow S, the unit of work is one selected `sim_1` run plus its analysis
directory. Its completion check is scoped to that run; do not read, repair, or
validate a Mode 1 foundation as part of the simulation. For Flow D, stop after
classifying existing evidence; do not launch a tool stage to remove uncertainty.

## 2. Resume packet

First classify the request as a fresh unit or a continuation. For a continuation, read the smallest authoritative packet:

1. the status block at the top of the current `IMPLEMENTATION.md` or equivalent state file;
2. only the relevant requirements and architecture sections;
3. the artifact, image, parameter, or replay manifest for the active stage;
4. only the changed or directly affected source files, constraints, IP settings, hashes, or evidence summaries;
5. the latest unresolved item that controls this iteration.

Do not automatically reread the complete Mode 1 foundation, all historical reports, long scripts, every ILA export, or the whole worktree. Expand the packet only when a required fact is absent, stale, contradictory, or its identity changed.

## 3. Invalidation matrix

| Current change | Rerun or recheck | Do not automatically rerun |
|---|---|---|
| Test parameters or scenario script only | Script checks and the corresponding simulation or board scenario; result report | Full RTL review, synthesis, implementation |
| Report wording or evidence interpretation only | Report consistency and applicable validator | Simulation, hardware, build stages |
| One project simulation | Output-directory occupancy, the selected `sim_1` run, WDB/WCFG, and its scoped analysis | Mode 1 reading, global baseline, unrelated simulations |
| One read-only diagnosis | The cited existing logs/reports and diagnosis result | Simulation, build, programming, or a source change |
| RTL behavior changed | Elaboration/lint if available, affected simulation; synthesis/implementation only when required by risk or board evidence | Unrelated demos and unrelated full regressions |
| XDC, clock/reset, part, or vendor IP changed | Affected synthesis, implementation, timing, mapping, and dependent demos | Unrelated features and board scenarios |
| Host/protocol sequence changed | Protocol decode, affected model/simulation or board flow, readback/oracle | Unrelated RTL/build stages when the image is unchanged |
| Qualified bit/LTX/target unchanged | Verify identities once per batch and run the targeted board query | Rebuild, reprogram, or full ILA inventory |
| User scope or acceptance clarified | Affected requirement, verification, and report sections | Unrelated evidence stages |

If several rows apply, take their union. A stage is invalid only when an input, assumption, artifact identity, acceptance rule, or dependency that it relies on changed.

## 4. Context and command hygiene

- Search with `rg`; request line ranges or structured fields rather than entire files.
- Scope source-state checks, for example `git status -- <authoritative paths> <active-unit paths>`.
- Never place full `.runs`, `.gen`, `.Xil`, cache, generated-project, or legacy-artifact inventories in model context.
- Set bounded output limits. Save long raw output under the active unit and summarize the decisive lines plus their path.
- Combine independent read-only checks into one batch when their outputs remain distinguishable.
- Do not repeatedly compute the same hashes, inventories, or validations after their inputs are known unchanged.
- Treat previous evidence as valid until a recorded dependency invalidates it; age alone is not invalidation.

## 5. Reuse and script threshold

Prefer the unit's canonical build runner, scenario runner, protocol decoder, capture tool, and report generator. Do not create a parallel parser or second source of truth.

Use a bounded command or existing parser for a one-time simple extraction. Add a persistent script only when at least one condition holds:

- the user needs a replayable entry point;
- the operation will run repeatedly;
- manual steps are complex or error-prone;
- deterministic parsing materially improves the evidence.

Do not add a script, report, manifest, or checksum layer merely to make a narrow result look more complete. When a new script is justified, validate it once with a known case and then reuse it.

## 6. Board and ILA batches

For an existing-image batch:

1. verify JTAG target, FPGA part, programmed-image identity, bitstream, and LTX compatibility once;
2. reuse the qualified image when it already matches;
3. preflight the project-owned `<project>.hw/<hw-set>/` output, open the `.xpr`, then open or reuse one Hardware Manager session bound to that project; inventory only relevant debug cores;
4. start packet capture after hardware preparation and stop it when the suite ends;
5. use host commands/readback for the routine loop and ILA only for a targeted trigger or timing question;
6. export only relevant captures to `<project>.hw/backup/` and record their project-native paths and structured observations under `AI-work`;
7. if the required signal is absent, record `PROBE_GAP` and stop repeating captures that cannot answer the oracle;
8. in one cleanup path, issue STOP, restore authorized parameters/state, confirm relevant readback, and close sessions.

Reprogram only when image identity is wrong, state recovery requires it, or the evidence plan explicitly tests configuration. Do not repeat target scans, full core inventories, or bit/LTX hashes within the same unchanged batch.

Do not `cd` Hardware Manager into `AI-work`, create a second standalone hardware workspace, or move `D:/hw_ila_data_*` into evidence. A newly-created `D:/hw_ila_data_*` is `ILA_ARTIFACT_SPILL`: preserve it in place, report its exact path, and stop. It means the runner did not remain bound to the project Hardware workspace.

## 7. Proportional documentation

Map changed facts to their owners:

| Changed fact | Update |
|---|---|
| Scope or acceptance | `REQUIREMENTS.md` |
| Architecture or verification strategy | `ARCHITECTURE.md` |
| Source/build/image/execution state | `IMPLEMENTATION.md` |
| Test execution, evidence, or conclusion | Applicable test, replay, issue, or board report |
| Meaningful unit state transition | One consolidated `AI-work/LOG.md` entry |
| Unknown that blocks a future decision | `OPEN-QUESTIONS.md` |

Unchanged documents do not need a ceremonial rewrite. Batch related edits after evidence collection. Run the relevant validator once after the final edit, unless it reports a concrete failure that must be corrected.

## 8. Completion gate

Stop the iteration when all applicable conditions hold:

- the decision question has decisive evidence or an explicitly evidenced blocker;
- authorized source, board, register, and capture state is restored;
- only affected documentation and manifests are synchronized;
- the applicable final validator has passed once;
- no new artifact spill remains outside the authorized unit;
- out-of-scope findings are recorded without being pursued.

Do not continue broad review, add optional evidence layers, rerun unchanged stages, or generate extra reports after this gate passes.
