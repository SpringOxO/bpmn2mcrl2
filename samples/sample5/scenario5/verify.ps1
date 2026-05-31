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
$Lts = Join-Path $OutputDir "owner_payment_reconciliation.lts"
$Mcf = Join-Path $PSScriptRoot "mcf\payment_reconciliation_reachable.mcf"
$Pbes = Join-Path $OutputDir "payment_reconciliation_reachable.pbes"
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
    & python $Converter $Bpmn $Mcrl2 --disable-timer
}

Invoke-Checked "Check generated guards and data updates" {
    $Required = @(
        "Amount_Due: Int",
        "Amount_Paid: Int",
        "Current_Payment: Int",
        "(Amount_Paid >= Amount_Due)",
        "(Amount_Paid < Amount_Due)",
        "pay_freight_charges(oid) . cont_activity_1p1hn9r(oid, Amount_Due, Amount_Paid + Current_Payment, Current_Payment)",
        "record_amount_statement(oid) . cont_activity_recordstatement(oid, 3, 0, 1)"
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
        & lps2lts $Lps $Lts
    }
}

Invoke-Checked "Check payment reconciliation property" {
    & lps2pbes --quiet -f $Mcf $Lps $Pbes
    if ($LASTEXITCODE -ne 0) {
        throw "lps2pbes failed with exit code $LASTEXITCODE."
    }
    $PbesOutput = & pbes2bool $Pbes
    $PbesExitCode = $LASTEXITCODE
    if ($PbesExitCode -ne 0) {
        throw "pbes2bool failed with exit code $PbesExitCode."
    }
    $McfResult = ($PbesOutput | Select-Object -Last 1).Trim()
    if ($McfResult -ne "true") {
        throw "payment_reconciliation_reachable.mcf evaluated to $McfResult."
    }
    Write-Host ("mCF result: " + $McfResult)
}

Write-Host ""
Write-Host "Payment reconciliation verification completed."
