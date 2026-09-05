[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Project,
    [string]$HwSet = 'hw_1'
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path -LiteralPath $Project -PathType Leaf)) {
    Write-Error "ILA_SETUP_BLOCKED: project file not found: $Project"
    exit 2
}

$projectPath = (Resolve-Path -LiteralPath $Project).Path
$projectRoot = Split-Path -Parent $projectPath
$projectName = [System.IO.Path]::GetFileNameWithoutExtension($projectPath)
$hwDir = Join-Path $projectRoot ("{0}.hw\{1}" -f $projectName, $HwSet)

if (-not (Test-Path -LiteralPath $hwDir -PathType Container)) {
    Write-Output "ILA_OUTPUT_READY path=$hwDir state=not-created"
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

$candidates = @()
$hwXml = Join-Path $hwDir 'hw.xml'
if (Test-Path -LiteralPath $hwXml -PathType Leaf) {
    $candidates += Get-Item -LiteralPath $hwXml
}
$waveDir = Join-Path $hwDir 'wave'
if (Test-Path -LiteralPath $waveDir -PathType Container) {
    $candidates += Get-ChildItem -LiteralPath $waveDir -File -Recurse -Force |
        Where-Object { $_.Extension -in @('.wdb', '.wcfg') }
}
$locked = @($candidates | Where-Object { -not (Test-ExclusiveAccess -Path $_.FullName) })

if ($locked.Count -gt 0) {
    Write-Output "ILA_OUTPUT_LOCKED path=$hwDir"
    $locked | ForEach-Object { Write-Output "locked_file=$($_.FullName)" }
    exit 3
}

Write-Output "ILA_OUTPUT_READY path=$hwDir state=exclusive-access-ok"
exit 0
