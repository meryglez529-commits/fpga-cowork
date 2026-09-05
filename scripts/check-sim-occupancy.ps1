[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Project,
    [string]$SimSet = 'sim_1'
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $Project -PathType Leaf)) {
    Write-Error "SIM_SETUP_BLOCKED: project file not found: $Project"
    exit 2
}

$projectPath = (Resolve-Path -LiteralPath $Project).Path
$projectRoot = Split-Path -Parent $projectPath
$projectName = [System.IO.Path]::GetFileNameWithoutExtension($projectPath)
$xsimDir = Join-Path $projectRoot ("{0}.sim\{1}\behav\xsim" -f $projectName, $SimSet)

if (-not (Test-Path -LiteralPath $xsimDir -PathType Container)) {
    Write-Output "SIM_OUTPUT_READY path=$xsimDir state=not-created"
    exit 0
}

function Test-ExclusiveAccess {
    param([Parameter(Mandatory = $true)][string]$Path)
    $stream = $null
    try {
        $stream = [System.IO.File]::Open(
            $Path,
            [System.IO.FileMode]::Open,
            [System.IO.FileAccess]::ReadWrite,
            [System.IO.FileShare]::None
        )
        return $true
    }
    catch {
        return $false
    }
    finally {
        if ($null -ne $stream) {
            $stream.Dispose()
        }
    }
}

$candidates = Get-ChildItem -LiteralPath $xsimDir -File -Force |
    Where-Object {
        $_.Name -in @('compile.log', 'elaborate.log', 'simulate.log', 'xelab.pb', 'xvlog.pb') -or
        $_.Extension -in @('.wdb', '.wcfg')
    }
$locked = @($candidates | Where-Object { -not (Test-ExclusiveAccess -Path $_.FullName) })

if ($locked.Count -gt 0) {
    Write-Output "SIM_OUTPUT_LOCKED path=$xsimDir"
    $locked | ForEach-Object { Write-Output "locked_file=$($_.FullName)" }
    exit 3
}

# A process named xsim/xelab/xvlog elsewhere is not proof that this sim-set is
# occupied. The lock result above is authoritative for this project output.
$otherProcesses = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match '^(xsim|xelab|xvlog)\.exe$' })
if ($otherProcesses.Count -gt 0) {
    Write-Warning "Unscoped XSim tool process(es) exist; $xsimDir has no locked active result files."
}

Write-Output "SIM_OUTPUT_READY path=$xsimDir state=exclusive-access-ok"
exit 0
