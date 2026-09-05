#==============================================================================
# Mode 3 GUI evidence viewer
#
# This is deliberately not a simulation launcher. Run the project-level batch
# runner first, then point the WDB path at the project-local result recorded in
# SIMULATION_RESULT.txt. This avoids a second GUI run mutating the project sim
# set or concealing a batch-only issue.
#==============================================================================

set wdb_file  "<PROJECT_ROOT>/<project>.sim/<sim-set>/behav/xsim/<snapshot>.wdb"
set wcfg_file "[file rootname $wdb_file].wcfg"

foreach evidence [list $wdb_file $wcfg_file] {
    if {![file exists $evidence]} {
        error "saved simulation evidence not found: $evidence"
    }
}

open_wave_database $wdb_file
open_wave_config $wcfg_file
puts "INFO: opened project-local same-basename WDB/WCFG; this helper did not launch simulation."
