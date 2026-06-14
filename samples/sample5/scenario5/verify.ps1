param(
    [switch]$SkipLts
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..\..")
$Converter = Join-Path $ProjectRoot "scripts\bpmn2mcrl2.py"
$Bpmn = Join-Path $PSScriptRoot "bpmn\owner_payment_reconciliation.bpmn"
$OutputDir = Join-Path $PSScriptRoot "mcrl2"
$Mcrl2 = Join-Path $OutputDir "owner_payment_reconciliation_output.mcrl2"
$Lps = Join-Path $OutputDir "owner_payment_reconciliation.lps"
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

# ========== Phase 1: Generate mCRL2 with data payloads ==========
Invoke-Checked "Convert BPMN to mCRL2 (with data payloads)" {
    & python $Converter $Bpmn $Mcrl2 --disable-timer
}

Invoke-Checked "Check generated guards, data updates, and data payloads" {
    $Required = @(
        "Amount_Due: Int",
        "Amount_Paid: Int",
        "Current_Payment: Int",
        "(Amount_Paid >= Amount_Due)",
        "(Amount_Paid < Amount_Due)",
        "pay_freight_charges(oid) . cont_activity_1p1hn9r(oid, Amount_Due, Amount_Paid + Current_Payment, Current_Payment)",
        "record_amount_statement(oid) . cont_activity_recordstatement(oid, 3, 0, 1)",
        "c_payment_settled_notice : OrderId # Int # Int",
        "c_balance_reminder : OrderId # Int # Int",
        "s_payment_settled_notice(oid, Amount_Due, Amount_Paid)",
        "s_balance_reminder(oid, Amount_Due, Amount_Paid)"
    )
    foreach ($Pattern in $Required) {
        if (-not (Select-String -Path $Mcrl2 -Pattern ([regex]::Escape($Pattern)) -Quiet)) {
            throw "Expected generated mCRL2 to contain: $Pattern"
        }
    }
}

Invoke-Checked "Generate LPS" {
    & mcrl22lps --lin-method=regular2 $Mcrl2 $Lps
}

if (-not $SkipLts) {
    Invoke-Checked "Generate LTS" {
        & lps2lts $Lps (Join-Path $OutputDir "owner_payment_reconciliation.lts")
    }
}

# ========== Phase 2: Verify Safety Invariants (with -s2 strategy) ==========
$McfSafety = Join-Path $PSScriptRoot "mcf\payment_safety_invariants.mcf"
$PbesSafety = Join-Path $OutputDir "payment_safety_invariants.pbes"

Invoke-Checked "Verify data-bound safety invariants" {
    & lps2pbes --quiet -f $McfSafety $Lps $PbesSafety
    if ($LASTEXITCODE -ne 0) {
        throw "lps2pbes (safety) failed with exit code $LASTEXITCODE."
    }
    $PbesOutput = & pbes2bool -s2 $PbesSafety
    $PbesExitCode = $LASTEXITCODE
    if ($PbesExitCode -ne 0) {
        throw "pbes2bool (safety) failed with exit code $PbesExitCode."
    }
    $McfResult = ($PbesOutput | Select-Object -Last 1).Trim()
    if ($McfResult -ne "true") {
        throw "payment_safety_invariants.mcf evaluated to $McfResult."
    }
    Write-Host ("mCF safety result: " + $McfResult)
}

# ========== Phase 3: Generate no-data mCRL2 for reachability ==========
Write-Host ""
Write-Host "== Stripping payload annotations for reachability check =="
$BpmnContent = Get-Content $Bpmn -Raw -Encoding UTF8
# Remove mcrl2:payload documentation from messageFlows
$BpmnClean = $BpmnContent -replace '\s*<bpmn:documentation>mcrl2:payload[^<]*</bpmn:documentation>', ''
# Also convert self-closing messageFlow tags back if they were expanded
$BpmnClean = $BpmnClean -replace '<bpmn:messageFlow([^>]*?)>\s*</bpmn:messageFlow>', '<bpmn:messageFlow$1 />'
$TempBpmn = Join-Path $OutputDir "_temp_no_payload.bpmn"
$BpmnClean | Set-Content $TempBpmn -Encoding UTF8

$Mcrl2NoData = Join-Path $OutputDir "owner_payment_reconciliation_no_data.mcrl2"
$LpsNoData = Join-Path $OutputDir "owner_payment_reconciliation_no_data.lps"

Invoke-Checked "Convert BPMN to mCRL2 (no data payloads)" {
    & python $Converter $TempBpmn $Mcrl2NoData --disable-timer
}
Remove-Item $TempBpmn -Force -ErrorAction SilentlyContinue

Invoke-Checked "Generate LPS (no data)" {
    & mcrl22lps --lin-method=regular2 $Mcrl2NoData $LpsNoData
}

# ========== Phase 4: Verify Reachability ==========
$McfReach = Join-Path $PSScriptRoot "mcf\payment_reconciliation_reachable.mcf"
$PbesReach = Join-Path $OutputDir "payment_reconciliation_reachable.pbes"

Invoke-Checked "Verify reachability properties" {
    & lps2pbes --quiet -f $McfReach $LpsNoData $PbesReach
    if ($LASTEXITCODE -ne 0) {
        throw "lps2pbes (reachability) failed with exit code $LASTEXITCODE."
    }
    $PbesOutput = & pbes2bool $PbesReach
    $PbesExitCode = $LASTEXITCODE
    if ($PbesExitCode -ne 0) {
        throw "pbes2bool (reachability) failed with exit code $PbesExitCode."
    }
    $McfResult = ($PbesOutput | Select-Object -Last 1).Trim()
    if ($McfResult -ne "true") {
        throw "payment_reconciliation_reachable.mcf evaluated to $McfResult."
    }
    Write-Host ("mCF reachability result: " + $McfResult)
}

Write-Host ""
Write-Host "Payment reconciliation verification completed (safety + reachability)."
