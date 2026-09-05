# Project Build and Bitstream Flow (B)

Use this flow to synthesize, implement, check timing, or generate a bitstream
for an existing Vivado project. It is a standalone operational flow: a request
to build an unchanged image does not require Mode 3. Mode 3 and Mode 4 may call
this flow after a source, constraint, IP, or board-baseline change.

## 1. Authority and boundary

Name the project, exact runs/stages, and decision question before launching:

| Input | Requirement |
|---|---|
| Project and runs | Existing `.xpr` and the exact named runs, normally `synth_1` and `impl_1` |
| Requested stage | `synth`, `impl`, or `bit`; do not infer bitstream generation from a request to inspect timing |
| Authority | Explicit user approval before resetting, launching, or replacing an existing run or generated bit/LTX |
| Acceptance | Declared timing/resource/DRC criteria, or an explicit statement that a criterion is not evaluated |
| Output owner | A new standalone `AI-work/build/<build-id>/`, or the calling unit's `out/build/<build-id>/` |

`reset_run`, implementation, and `write_bitstream` can replace the project's
current run products. If the named run/output is active or locked, report
`BUILD_OUTPUT_LOCKED` and stop. Do not terminate another tool, move `.runs`,
or create a clone solely to evade that condition.

This flow establishes build facts, not functional correctness or board
behavior. A successful bitstream does not substitute for S or H evidence.

## 2. Execute the declared stage

Use the project's approved Vivado runner or a unit-local runner that names the
same project and exact runs. Keep Vivado outer `-log` and `-journal` files in
the declared AI result directory; native synthesis/implementation products,
reports, checkpoints, `.bit`, and `.ltx` remain in their project-owned run
locations. Do not build a copied project or hand-copy a BD/IP/wrapper.

Run only the requested stage and its prerequisites:

| Request | Allowed work |
|---|---|
| `synth` | `synth_1` only |
| `impl` | Required synthesis, then `impl_1` without a bitstream |
| `bit` | Required synthesis/implementation through `write_bitstream` |

For implementation, collect WNS/TNS/WHS/THS when the project exposes them,
resource utilization, and the relevant DRC status. For a bitstream, record the
absolute bit/LTX paths and verify that the pair comes from the same declared
`impl_1` result. Existing warnings are reported with their identity and count;
they are not silently treated as a new regression.

## 3. Results and evidence

Write `BUILD_RESULT.txt` in the declared AI result directory. It records the
project, runs/stage, command, run status, decisive error/critical-warning
counts, timing/resource facts when applicable, bit/LTX identity when produced,
and absolute native paths.

| Result | Meaning |
|---|---|
| `BUILD_PASS` | The declared stage completed and every declared acceptance condition passed. Synthesis-only results state that timing is not evaluated. |
| `BUILD_TIMING_FAIL` | Implementation completed but a declared timing criterion failed. |
| `BUILD_SETUP_BLOCKED` | Project, run, requested stage, authority, or acceptance rule is missing. |
| `BUILD_OUTPUT_LOCKED` | The exact requested run/output is occupied. |
| `BUILD_TOOL_FAIL` | Vivado failed, or the requested run did not complete. |
| `BUILD_ARTIFACT_MISMATCH` | A requested bit/LTX pair is absent or cannot be tied to the declared run. |

Stop after the requested conclusion. Call H only if a board operation was
requested, and call D when existing logs/reports need explanation without a
rerun.
