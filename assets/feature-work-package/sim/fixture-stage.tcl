#==============================================================================
# Fixture staging template -- include only for file-backed simulation stimuli.
#
# Before copying, validate the source path, expected hash, and format expected
# by the TB (for example, legal $readmemh hexadecimal tokens for its width).
# Throw an error on any mismatch; the runner reports SIM_FIXTURE_BLOCKED before
# simulated time advances. Do not try alternative inputs or encodings here.
#==============================================================================

proc stage_sim_fixtures {sim_run_dir} {
    # Example:
    # set source "<AI_WORK_UNIT>/sim/fixtures/data_test.txt"
    # set target [file join $sim_run_dir data_test.txt]
    # if {![file exists $source]} { error "fixture missing: $source" }
    # if {![regexp {^[0-9A-Fa-f]+(?:[[:space:]]+[0-9A-Fa-f]+)*[[:space:]]*$} [read [open $source r]]]} {
    #     error "fixture is not legal hexadecimal-token input"
    # }
    # file copy $source $target
    error "replace stage_sim_fixtures with this test's fixture map and checks"
}
