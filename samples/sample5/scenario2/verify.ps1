param(
    [switch]$Timed,
    [switch]$SkipLts
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..\..")
$Converter = Join-Path $ProjectRoot "scripts\bpmn2mcrl2.py"
$Bpmn = Join-Path $PSScriptRoot "bpmn\depot_inventory_check.bpmn"
$OutputDir = Join-Path $PSScriptRoot "mcrl2"
$Suffix = if ($Timed) { "_timed" } else { "" }
$Mcrl2 = Join-Path $OutputDir ("depot_inventory_check" + $Suffix + "_output.mcrl2")
$Lps = Join-Path $OutputDir ("depot_inventory_check" + $Suffix + ".lps")
$Lts = Join-Path $OutputDir ("depot_inventory_check" + $Suffix + ".lts")
$McfReachable = Join-Path $PSScriptRoot "mcf\inventory_branches_reachable.mcf"
$PbesReachable = Join-Path $OutputDir "inventory_branches_reachable.pbes"
$McfSafety = Join-Path $PSScriptRoot "mcf\inventory_safety_invariants.mcf"
$PbesSafety = Join-Path $OutputDir "inventory_safety_invariants.pbes"
$env:PYTHONIOENCODING = "utf-8"

function Require-Command {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found in PATH."
    }
}

function Invoke-Checked {
    param([string]$Step, [scriptblock]$Command)
    Write-Host ""
    Write-Host "== $Step =="
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE."
    }
}

Require-Command "python"
Require-Command "mcrl22lps"
Require-Command "lps2pbes"
Require-Command "pbes2bool"
if (-not $SkipLts) {
    Require-Command "lps2lts"
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

Invoke-Checked "Convert BPMN to mCRL2" {
    if ($Timed) {
        & python $Converter $Bpmn $Mcrl2
    }
    else {
        & python $Converter $Bpmn $Mcrl2 --disable-timer
    }
}

Invoke-Checked "Check generated data guards and updates" {
    $Required = @(
        "Container_Count: Int",
        "(Container_Count > 0)",
        "(Container_Count == 0)",
        "s_send_empty_ctn_to_transport___count___1_to_transport__empty_ctn_received(oid, Container_Count)",
        "cont_activity_15hjzys(oid, Container_Count - 1)",
        "event_wait_for_empty_ctn_restock(oid)",
        "restock_empty_ctn___count___1(oid)"
    )
    foreach ($Pattern in $Required) {
        if (-not (Select-String -Path $Mcrl2 -Pattern ([regex]::Escape($Pattern)) -Quiet)) {
            throw "Expected generated mCRL2 to contain: $Pattern"
        }
    }
}

if ($Timed) {
    Invoke-Checked "Generate timed LPS" {
        & mcrl22lps --timed --lin-method=stack $Mcrl2 $Lps
    }
}
else {
    Invoke-Checked "Generate LPS" {
        & mcrl22lps --lin-method=stack $Mcrl2 $Lps
    }
}

if (-not $SkipLts) {
    Invoke-Checked "Generate LTS" {
        & lps2lts $Lps $Lts
    }
}

if (-not $Timed) {
    Invoke-Checked "Check inventory branch reachability" {
        & lps2pbes --quiet -f $McfReachable $Lps $PbesReachable
    }
    $PbesOutput = & pbes2bool $PbesReachable
    $PbesExitCode = $LASTEXITCODE
    if ($PbesExitCode -ne 0) {
        throw "pbes2bool failed with exit code $PbesExitCode."
    }
    $McfResult = ($PbesOutput | Select-Object -Last 1).Trim()
    if ($McfResult -ne "true") {
        throw "inventory_branches_reachable.mcf evaluated to $McfResult."
    }
    Write-Host ("mCF result: " + $McfResult)

    Invoke-Checked "Check inventory safety invariants" {
        & lps2pbes --quiet -f $McfSafety $Lps $PbesSafety
    }
    $SafetyOutput = & pbes2bool -s2 $PbesSafety
    $SafetyExitCode = $LASTEXITCODE
    if ($SafetyExitCode -ne 0) {
        throw "pbes2bool failed with exit code $SafetyExitCode."
    }
    $SafetyResult = ($SafetyOutput | Select-Object -Last 1).Trim()
    if ($SafetyResult -ne "true") {
        throw "inventory_safety_invariants.mcf evaluated to $SafetyResult."
    }
    Write-Host ("safety mCF result: " + $SafetyResult)
}

Write-Host ""
Write-Host "Scenario2 verification completed."
