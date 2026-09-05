#==============================================================================
# run_ila.tcl -- persistent project-Hardware-Manager capture runner
#
# Invoke with Vivado batch mode:
#   vivado -mode batch -source run_ila.tcl -log <AI-run>/vivado.log \
#     -journal <AI-run>/vivado.jou -tclargs \
#     <project.xpr> <hw-set> <hw-target> <device> <bit> <ltx> <ila-cell> \
#     <capture-id> <AI-run> USER_AUTHORIZED ?program|reuse?
#
# Native waveform state stays in <project>.hw/<hw-set>/ and the selected
# capture is written to <project>.hw/backup/<capture-id>.ila. AI-run receives
# only the outer Vivado log/journal and ILA_CAPTURE_RESULT.txt.
#==============================================================================

proc ila_emit {level message} {
    puts "$level: $message"
}

proc ila_safe_close {} {
    catch {close_hw_target}
    catch {disconnect_hw_server}
    catch {close_hw_manager}
    catch {close_project}
}

proc ila_write_result {path result fields} {
    file mkdir [file dirname $path]
    set fp [open $path w]
    puts $fp "result=$result"
    foreach {key value} $fields {
        puts $fp "$key=$value"
    }
    close $fp
}

if {[llength $argv] < 10 || [llength $argv] > 11} {
    ila_emit "ERROR" "ILA_SETUP_BLOCKED: usage: <project.xpr> <hw-set> <hw-target> <device> <bit> <ltx> <ila-cell> <capture-id> <AI-run> USER_AUTHORIZED ?program|reuse?"
    exit 2
}

set xpr [file normalize [lindex $argv 0]]
set hw_set [lindex $argv 1]
set target_name [lindex $argv 2]
set device_name [lindex $argv 3]
set bit_file [file normalize [lindex $argv 4]]
set ltx_file [file normalize [lindex $argv 5]]
set ila_cell [lindex $argv 6]
set capture_id [lindex $argv 7]
set ai_run [file normalize [lindex $argv 8]]
set authorization [lindex $argv 9]
set program_policy "program"
if {[llength $argv] == 11} {
    set program_policy [lindex $argv 10]
}

# Do not write a result anywhere until the caller's AI-owned result location
# has passed validation.  In particular, a rejected location must never turn
# this runner into a general filesystem writer.
set ai_run_valid [regexp {(^|/)AI-work(/|$)} [string map {\\ /} $ai_run]]
set result_path ""
set result "ILA_SETUP_BLOCKED"
set detail ""
set project_open 0
set hw_open 0
set native_ila ""
set selected_core ""
set root_spill_before {}
set capture_wait_seconds 10
set capture_status ""
set capture_samples ""
set capture_depth ""

foreach {label path} [list project $xpr bit $bit_file ltx $ltx_file] {
    if {![file exists $path]} {
        set detail "$label not found: $path"
    }
}
if {$detail eq "" && $authorization ne "USER_AUTHORIZED"} {
    set detail "explicit USER_AUTHORIZED argument is required"
}
if {$detail eq "" && ($hw_set eq "" || $target_name eq "" || $device_name eq "" || $ila_cell eq "")} {
    set detail "hw-set, target, device, and exact ILA cell name are required"
}
if {$detail eq "" && ![regexp {^[A-Za-z0-9._-]+$} $capture_id]} {
    set detail "invalid capture id: $capture_id"
}
if {$detail eq "" && $program_policy ni {program reuse}} {
    set detail "program policy must be program or reuse, got: $program_policy"
}
if {$detail eq "" && !$ai_run_valid} {
    set detail "AI result directory must be under AI-work: $ai_run"
}
if {$detail ne ""} {
    ila_emit "ERROR" "ILA_SETUP_BLOCKED: $detail"
    if {$ai_run_valid} {
        set result_path [file join $ai_run ILA_CAPTURE_RESULT.txt]
        catch {ila_write_result $result_path $result [list detail $detail]}
    }
    exit 2
}
set result_path [file join $ai_run ILA_CAPTURE_RESULT.txt]
if {[catch {file mkdir $ai_run} ai_run_error]} {
    set detail "cannot create AI result directory: $ai_run_error"
    ila_emit "ERROR" "ILA_SETUP_BLOCKED: $detail"
    exit 2
}

set project_dir [file dirname $xpr]
set project_name [file rootname [file tail $xpr]]
set hw_root [file join $project_dir "${project_name}.hw"]
set hw_dir [file join $hw_root $hw_set]
set backup_dir [file join $hw_root backup]
set native_ila [file join $backup_dir "${capture_id}.ila"]
if {[file exists $native_ila]} {
    set detail "refusing to overwrite existing native capture: $native_ila"
    ila_emit "ERROR" "ILA_SETUP_BLOCKED: $detail"
    catch {ila_write_result $result_path $result [list detail $detail native_ila $native_ila]}
    exit 2
}

# A project-bound run should never create these D-root placeholders. Snapshot
# only to detect a spill; do not move, delete, or normalize any pre-existing
# directories.
set root_spill_before [glob -nocomplain -directory D:/ hw_ila_data_*]

if {[catch {
    cd $project_dir
    open_project $xpr
    set project_open 1
    file mkdir $backup_dir

    open_hw_manager
    connect_hw_server
    set target_matches {}
    foreach target [get_hw_targets -quiet] {
        if {[get_property NAME $target] eq $target_name} {
            lappend target_matches $target
        }
    }
    if {[llength $target_matches] != 1} {
        error "expected exactly one hardware target '$target_name', found [llength $target_matches]"
    }
    set target [lindex $target_matches 0]
    current_hw_target $target
    open_hw_target
    set hw_open 1

    set device_matches {}
    foreach device [get_hw_devices -quiet] {
        if {[get_property NAME $device] eq $device_name} {
            lappend device_matches $device
        }
    }
    if {[llength $device_matches] != 1} {
        error "expected exactly one hardware device '$device_name', found [llength $device_matches]"
    }
    set device [lindex $device_matches 0]
    current_hw_device $device
    set_property PROBES.FILE $ltx_file $device
    set_property FULL_PROBES.FILE $ltx_file $device

    if {$program_policy eq "program"} {
        set_property PROGRAM.FILE $bit_file $device
        program_hw_devices $device
        after 15000
    }
    refresh_hw_device $device

    set selected_matches {}
    foreach candidate [get_hw_ilas -quiet -of_objects $device] {
        if {[get_property CELL_NAME $candidate] eq $ila_cell} {
            lappend selected_matches $candidate
        }
    }
    if {[llength $selected_matches] == 0 && $program_policy eq "program"} {
        after 5000
        refresh_hw_device $device
        foreach candidate [get_hw_ilas -quiet -of_objects $device] {
            if {[get_property CELL_NAME $candidate] eq $ila_cell} {
                lappend selected_matches $candidate
            }
        }
    }
    if {[llength $selected_matches] == 0} {
        set result "ILA_CORE_NOT_READY"
        error "declared ILA cell not found after bounded refresh: $ila_cell"
    }
    if {[llength $selected_matches] != 1} {
        error "declared ILA cell is ambiguous: $ila_cell"
    }
    set selected_core [lindex $selected_matches 0]
    current_hw_ila $selected_core

    # Make the default capture independent of stale GUI settings.  reset_hw_ila
    # restores all probe compares to X and capture mode to ALWAYS; -trigger_now
    # then performs the documented immediate-trigger capture.
    reset_hw_ila -reset_compare_values true $selected_core
    set_property CONTROL.TRIGGER_POSITION 0 $selected_core
    run_hw_ila -trigger_now $selected_core
    wait_on_hw_ila -timeout $capture_wait_seconds $selected_core

    set capture_status [get_property STATUS.CORE_STATUS $selected_core]
    set capture_samples [get_property STATUS.SAMPLE_COUNT $selected_core]
    set capture_depth [get_property CONTROL.DATA_DEPTH $selected_core]
    if {[catch {expr {int($capture_samples)}} samples_int] ||
        [catch {expr {int($capture_depth)}} depth_int] ||
        $samples_int < $depth_int} {
        set result "ILA_CAPTURE_TIMEOUT"
        error "immediate capture did not fill its buffer within ${capture_wait_seconds}s: status=$capture_status samples=$capture_samples depth=$capture_depth"
    }
    set data [upload_hw_ila_data $selected_core]
    if {[llength $data] != 1} {
        error "expected exactly one uploaded capture data object, found [llength $data]"
    }
    write_hw_ila_data $native_ila $data
    if {![file exists $native_ila] || [file size $native_ila] == 0} {
        error "native ILA export missing or empty: $native_ila"
    }
    set result "ILA_CAPTURE_PASS"
} detail]} {
    if {$result eq "ILA_SETUP_BLOCKED"} {
        set result "ILA_CAPTURE_FAIL"
    }
}

set root_spill_after [glob -nocomplain -directory D:/ hw_ila_data_*]
set new_spill {}
foreach candidate $root_spill_after {
    if {[lsearch -exact $root_spill_before $candidate] < 0} {
        lappend new_spill $candidate
    }
}
if {[llength $new_spill] > 0} {
    set result "ILA_ARTIFACT_SPILL"
    append detail " | new D-root spill: [join $new_spill {, }]"
}

set fields [list \
    project $xpr \
    hw_set $hw_set \
    project_hw_dir $hw_dir \
    target $target_name \
    device $device_name \
    bit_file $bit_file \
    ltx_file $ltx_file \
    ila_cell $ila_cell \
    selected_core $selected_core \
    capture_policy reset-all-x-immediate \
    capture_wait_seconds $capture_wait_seconds \
    capture_status $capture_status \
    capture_samples $capture_samples \
    capture_depth $capture_depth \
    program_policy $program_policy \
    native_ila $native_ila \
    detail $detail \
    d_root_new_spill [join $new_spill {, }]]
catch {ila_safe_close}
if {[catch {ila_write_result $result_path $result $fields} write_error]} {
    ila_emit "ERROR" "cannot write ILA result: $write_error"
    exit 6
}
ila_emit "RESULT" $result
if {$result eq "ILA_CAPTURE_PASS"} {
    exit 0
}
exit 5
