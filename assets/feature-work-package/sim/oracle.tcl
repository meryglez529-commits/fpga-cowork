#==============================================================================
# Simulation oracle template
#
# The project-level runner calls sim_oracle after its finite run completes.
# Return exactly 1 for PASS or 0 for FAIL. Inspect actual XSim objects, TB
# result signals, or a test-owned result file; do not grep simulator logs.
#==============================================================================

proc sim_oracle {} {
    # Example: return [expr {[get_value /tb/done] == 1 && [get_value /tb/error] == 0}]
    error "replace sim_oracle with this test's explicit pass/fail condition"
}
