# Historical direct-XSim troubleshooting notes

This document preserves the previous simulation approach for diagnosis and historical log interpretation. It is **not** an execution recipe and is not a fallback for `scripts/templates/run_sim.tcl`.

## Retired default

The retired approach assembled a simulation outside the Vivado project manager: generated or guessed a `.prj` file, called `xvlog`, called `xelab`, and started `xsim` directly or through a Vivado Tcl wrapper. Some templates also used `run all` and inferred PASS from text in a simulator log.

That approach is no longer a supported `fpga-cowork` flow because it can diverge from the project's sim set, compile order, IP libraries, generated/encrypted models, working directory, and GUI configuration. It also made failures slow and ambiguous: a direct `xsim` `init.tcl` encryption/corruption error says nothing conclusive about `launch_simulation`, and `$display` is often written to the outer Vivado log rather than `simulate.log`.

## How to use these notes

Use them only to classify an already observed failure, compare an old log, or explain why the current project-level runner was chosen. Do not revive the retired commands automatically, replace project IP models, patch the Vivado installation, delete a locked simulation log, or use an unbounded `run all` from this document.

| Historical symptom | Interpretation under the current SOP |
|---|---|
| Direct `xsim` fails while reading `init.tcl` | Treat the direct-launch wrapper as unverified. Re-run through the project sim set; do not modify installed Tcl files. |
| `xvlog`/`xelab` reports missing IP, library, macro, or source-order errors | The manually assembled closure differed from the project. Use `launch_simulation` with the project's existing sim set. |
| `simulate.log` lacks the TB's PASS text | This does not decide the result. The outer Vivado log and declared oracle are authoritative. |
| `$readmemh` reports `Illegal hex digit` | The GUI may continue with `X` data. Stop as `SIM_FIXTURE_BLOCKED`, validate the fixture map, and stage the corrected file into the actual XSim working directory before advancing time. |
| `launch_simulation` cannot access or remove a log | The GUI or another process may own the project simulation output. Stop as `SIM_OUTPUT_LOCKED`; do not kill the GUI or delete artifacts. |

## Why this became historical

The project-manager path has the project's real source membership, compile order, IP configuration, libraries, and simulation working directory. It completed ordinary smoke simulation in seconds to tens of seconds once the project was open. Long exploratory direct-command loops and unbounded runs are therefore neither a reliable acceptance test nor a reasonable default use of time.

For the current authoritative procedure, see [Simulation Environment SOP](simulation-environment.md).
