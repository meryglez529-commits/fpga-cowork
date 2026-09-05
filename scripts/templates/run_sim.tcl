#==============================================================================
# run_sim.tcl -- persistent project-simulation runner
#
# Invoke with Vivado batch mode:
#   vivado -mode batch -source run_sim.tcl -log <AI-run>/vivado.log \
#     -journal <AI-run>/vivado.jou -tclargs \
#     <project.xpr> <tb-file> <tb-top> <runtime> <AI-run> \
#     [oracle.tcl|-] [fixture-stage.tcl|-] [sim-set]
#
# Testbenches are official simulation sources under
# <project>.srcs/<sim-set>/new. The runner keeps the selected top and source
# membership in the project; it never creates a temporary sim set or restores
# an earlier top. WDB/WCFG/XSim logs remain only in the project XSim directory.
#==============================================================================

proc sim_emit {level message} {
    puts "$level: $message"
}

proc sim_stop {tag message code} {
    global sim_exit_code sim_terminal_tag
    if {$sim_exit_code == 0} {
        set sim_exit_code $code
        set sim_terminal_tag $tag
        sim_emit "ERROR" "$tag: $message"
    }
}

proc sim_output_is_locked {message} {
    return [regexp -nocase {(cannot[[:space:]]+(access|remove|delete|rename)|permission[[:space:]]+denied|file.*locked|used[[:space:]]+by[[:space:]]+another[[:space:]]+process)} $message]
}

proc path_is_within {child parent} {
    set child [file normalize $child]
    set parent [file normalize $parent]
    return [expr {$child eq $parent || [string match "${parent}/*" $child]}]
}

proc simset_contains_file {fileset canonical_path} {
    foreach f [get_files -quiet -of_objects $fileset] {
        if {![catch {set candidate [file normalize [get_property NAME $f]]}] &&
            $candidate eq $canonical_path} {
            return 1
        }
    }
    return 0
}

proc newest_matching_file {pattern minimum_mtime} {
    set newest ""
    set newest_time -1
    foreach f [glob -nocomplain $pattern] {
        if {[file mtime $f] >= $minimum_mtime && [file mtime $f] > $newest_time} {
            set newest $f
            set newest_time [file mtime $f]
        }
    }
    return $newest
}

proc write_analysis_summary {result_dir result project sim_set tb_top tb_file runtime xsim_dir wdb wcfg} {
    file mkdir $result_dir
    set summary_path [file join $result_dir SIMULATION_RESULT.txt]
    set summary [open $summary_path w]
    foreach {key value} [list \
        result $result \
        project $project \
        sim_set $sim_set \
        top $tb_top \
        testbench $tb_file \
        runtime $runtime \
        xsim_dir $xsim_dir \
        project_wdb $wdb \
        project_wcfg $wcfg \
        compile_log [file join $xsim_dir compile.log] \
        elaborate_log [file join $xsim_dir elaborate.log] \
        simulate_log [file join $xsim_dir simulate.log] \
        result_policy project-owned-current-output] {
        puts $summary "$key=$value"
    }
    close $summary
}

if {[llength $argv] < 5 || [llength $argv] > 8} {
    sim_emit "ERROR" "SIM_SETUP_BLOCKED: usage: <project.xpr> <tb-file> <tb-top> <runtime> <AI-run> ?oracle.tcl|-? ?fixture-stage.tcl|-? ?sim-set?"
    exit 2
}

set xpr [file normalize [lindex $argv 0]]
set tb_file [file normalize [lindex $argv 1]]
set tb_top [lindex $argv 2]
set runtime [lindex $argv 3]
set out_dir [file normalize [lindex $argv 4]]
set oracle_file ""
set fixture_file ""
set sim_set "sim_1"
if {[llength $argv] >= 6 && [lindex $argv 5] ni {"" "-"}} {
    set oracle_file [file normalize [lindex $argv 5]]
}
if {[llength $argv] >= 7 && [lindex $argv 6] ni {"" "-"}} {
    set fixture_file [file normalize [lindex $argv 6]]
}
if {[llength $argv] >= 8} {
    set sim_set [lindex $argv 7]
}

set sim_exit_code 0
set sim_terminal_tag ""
set project_open 0
set sim_open 0
set simulation_started 0
set fileset ""
set xsim_dir ""
set launch_started 0
set project_wdb ""
set project_wcfg ""
set pending_wcfg ""

foreach {label path} [list project $xpr testbench $tb_file] {
    if {![file exists $path]} {
        sim_stop "SIM_SETUP_BLOCKED" "$label not found: $path" 2
    }
}
if {$tb_top eq "" || $runtime eq ""} {
    sim_stop "SIM_SETUP_BLOCKED" "testbench top and finite runtime are required" 2
}
if {$oracle_file ne "" && ![file exists $oracle_file]} {
    sim_stop "SIM_SETUP_BLOCKED" "oracle not found: $oracle_file" 2
}
if {$fixture_file ne "" && ![file exists $fixture_file]} {
    sim_stop "SIM_FIXTURE_BLOCKED" "fixture adapter not found: $fixture_file" 2
}
if {[file exists [file join $out_dir SIMULATION_RESULT.txt]]} {
    sim_stop "SIM_SETUP_BLOCKED" "analysis directory already has SIMULATION_RESULT.txt: $out_dir" 2
}

if {$sim_exit_code == 0 && $oracle_file ne ""} {
    if {[catch {source $oracle_file} error_text]} {
        sim_stop "SIM_SETUP_BLOCKED" "cannot source oracle: $error_text" 2
    } elseif {[llength [info procs sim_oracle]] != 1} {
        sim_stop "SIM_SETUP_BLOCKED" "oracle must define: proc sim_oracle {} { return 1 or 0 }" 2
    }
}
if {$sim_exit_code == 0 && $fixture_file ne ""} {
    if {[catch {source $fixture_file} error_text]} {
        sim_stop "SIM_FIXTURE_BLOCKED" "cannot source fixture adapter: $error_text" 2
    } elseif {[llength [info procs stage_sim_fixtures]] != 1} {
        sim_stop "SIM_FIXTURE_BLOCKED" "fixture adapter must define: proc stage_sim_fixtures {sim_run_dir} { ... }" 2
    }
}

if {$sim_exit_code == 0 && [catch {open_project $xpr} error_text]} {
    sim_stop "SIM_SETUP_BLOCKED" "open_project failed: $error_text" 3
} elseif {$sim_exit_code == 0} {
    set project_open 1
}

set project_dir [file dirname $xpr]
set project_name [file rootname [file tail $xpr]]
set sim_source_dir [file join $project_dir "${project_name}.srcs" $sim_set new]
set xsim_dir [file join $project_dir "${project_name}.sim" $sim_set behav xsim]

if {$sim_exit_code == 0 && ![path_is_within $tb_file $sim_source_dir]} {
    sim_stop "SIM_SETUP_BLOCKED" "testbench must be under $sim_source_dir, got $tb_file" 3
}
if {$sim_exit_code == 0} {
    set fileset [get_filesets -quiet $sim_set]
    if {[llength $fileset] != 1} {
        sim_stop "SIM_SETUP_BLOCKED" "simulation set not found or ambiguous: $sim_set" 3
    }
}
if {$sim_exit_code == 0 && ![simset_contains_file $fileset $tb_file]} {
    if {[catch {add_files -fileset $sim_set $tb_file} error_text]} {
        sim_stop "SIM_SETUP_BLOCKED" "cannot add testbench to $sim_set: $error_text" 3
    }
}
if {$sim_exit_code == 0 && [catch {set_property top $tb_top $fileset} error_text]} {
    sim_stop "SIM_SETUP_BLOCKED" "cannot select simulation top: $error_text" 3
}
if {$sim_exit_code == 0 && [catch {set_property xsim.simulate.runtime $runtime $fileset} error_text]} {
    sim_stop "SIM_SETUP_BLOCKED" "cannot set finite XSim runtime $runtime: $error_text" 3
}

if {$sim_exit_code == 0 && $fixture_file ne ""} {
    file mkdir $xsim_dir
    if {[catch {stage_sim_fixtures $xsim_dir} error_text]} {
        sim_stop "SIM_FIXTURE_BLOCKED" "$error_text" 4
    }
}

if {$sim_exit_code == 0} {
    sim_emit "INFO" "reuse project simulation output: $xsim_dir"
    sim_emit "INFO" "launch project simulation: sim_set=$sim_set top=$tb_top runtime=$runtime"
    set launch_started [clock seconds]
    if {[catch {launch_simulation -simset $sim_set -mode behavioral} error_text]} {
        if {[sim_output_is_locked $error_text]} {
            sim_stop "SIM_OUTPUT_LOCKED" "$error_text" 4
        } else {
            sim_stop "SIM_TOOL_FAIL" "launch_simulation failed: $error_text" 4
        }
    } else {
        set sim_open 1
        set simulation_started 1
    }
}

if {$sim_open} {
    set pending_wcfg [file join $xsim_dir ".fpga-cowork-[pid]-[clock seconds].wcfg"]
    if {[catch {save_wave_config $pending_wcfg} error_text]} {
        if {$sim_exit_code == 0} {
            sim_stop "SIM_TOOL_FAIL" "save_wave_config failed: $error_text" 5
        }
    }
}

if {$sim_exit_code == 0 && $oracle_file ne ""} {
    if {[catch {set oracle_result [sim_oracle]} error_text]} {
        sim_stop "SIM_FAIL" "oracle raised an error: $error_text" 5
    } elseif {$oracle_result eq "1"} {
        sim_emit "INFO" "oracle returned PASS"
        set sim_terminal_tag "SIM_PASS"
    } elseif {$oracle_result eq "0"} {
        sim_stop "SIM_FAIL" "oracle returned FAIL" 5
    } else {
        sim_stop "SIM_FAIL" "oracle must return exactly 1 or 0, got: $oracle_result" 5
    }
} elseif {$sim_exit_code == 0 && $sim_open} {
    set sim_terminal_tag "SIM_COMPLETED"
}

if {$sim_open} {
    if {[catch {close_sim} error_text] && $sim_exit_code == 0} {
        sim_stop "SIM_TOOL_FAIL" "close_sim failed: $error_text" 5
    }
    set sim_open 0
}
# Vivado 2021.1 has no valid no-argument save_project form.  The project
# mutations above (add_files and set_property) are already persisted in the
# open XPR by Vivado, so do not issue a redundant save command here.  This
# keeps the runner usable on Vivado 2021.1 while retaining the already
# persisted sim-set membership, selected top, and runtime settings.

if {$launch_started > 0} {
    set project_wdb [newest_matching_file [file join $xsim_dir *.wdb] $launch_started]
    if {$project_wdb eq ""} {
        if {$pending_wcfg ne "" && [file exists $pending_wcfg]} {
            file delete -force $pending_wcfg
        }
        if {$sim_exit_code == 0} {
            sim_stop "SIM_TOOL_FAIL" "no fresh WDB found in $xsim_dir" 6
        }
    } elseif {$pending_wcfg ne "" && [file exists $pending_wcfg]} {
        set project_wcfg "[file rootname $project_wdb].wcfg"
        if {[catch {file rename -force $pending_wcfg $project_wcfg} error_text]} {
            if {$sim_exit_code == 0} {
                sim_stop "SIM_TOOL_FAIL" "cannot save same-basename WCFG: $error_text" 6
            }
        } elseif {![file exists $project_wcfg]} {
            if {$sim_exit_code == 0} {
                sim_stop "SIM_TOOL_FAIL" "same-basename WCFG was not created: $project_wcfg" 6
            }
        }
    }
}

if {$project_open} {
    if {[catch {close_project} error_text] && $sim_exit_code == 0} {
        sim_stop "SIM_TOOL_FAIL" "close_project failed: $error_text" 6
    }
    set project_open 0
}

set result $sim_terminal_tag
if {$sim_exit_code == 0 && $result eq ""} {
    set result "SIM_COMPLETED"
}
if {[catch {write_analysis_summary $out_dir $result $xpr $sim_set $tb_top $tb_file $runtime $xsim_dir $project_wdb $project_wcfg} error_text]} {
    sim_emit "ERROR" "cannot write SIMULATION_RESULT.txt: $error_text"
    if {$sim_exit_code == 0} {
        set sim_exit_code 6
        set result "SIM_TOOL_FAIL"
    }
}

sim_emit "RESULT" "$result"
if {$sim_exit_code == 0} {
    exit 0
}
exit $sim_exit_code
