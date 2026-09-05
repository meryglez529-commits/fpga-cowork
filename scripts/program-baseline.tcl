# HISTORICAL ENTRY POINT — blocked to avoid a projectless Hardware Manager
# session and D:/hw_ila_data_* artifact spill. Use templates/run_ila.tcl with
# an explicit project, hw-set, target, device, bit/LTX, selected ILA, and
# USER_AUTHORIZED instead.
puts "FAIL: LEGACY_HARDWARE_RUNNER_BLOCKED: use scripts/templates/run_ila.tcl"
exit 2
