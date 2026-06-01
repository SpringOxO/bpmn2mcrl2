param(
    [switch]$SkipLts
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$Converter = Join-Path $ProjectRoot "scripts\bpmn2mcrl2.py"
$OutputDir = Join-Path $PSScriptRoot "mcrl2"
$env:PYTHONIOENCODING = "utf-8"

function Require-Command {
    param([string]$Name)

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found in PATH."
    }
}

function Invoke-Checked {
    param(
        [string]$Step,
        [scriptblock]$Command
    )

    Write-Host ""
    Write-Host "== $Step =="
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE."
    }
}

Require-Command "python"
Require-Command "mcrl22lps"
if (-not $SkipLts) {
    Require-Command "lps2lts"
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

$Models = @(
    @{
        Name = "Transport"
        Input = Join-Path $PSScriptRoot "bpmn\Transport.bpmn"
        Base = "transport"
    },
    @{
        Name = "Freight Forwarder"
        Input = Join-Path $PSScriptRoot "bpmn\Freight-Forward.bpmn"
        Base = "freight-forward"
    }
)

$Results = @()

foreach ($Model in $Models) {
    $Mcrl2 = Join-Path $OutputDir ($Model.Base + "_output.mcrl2")
    $Lps = Join-Path $OutputDir ($Model.Base + ".lps")
    $Lts = Join-Path $OutputDir ($Model.Base + ".lts")

    Write-Host ""
    Write-Host "############################################################"
    Write-Host ("Verifying " + $Model.Name)
    Write-Host "############################################################"

    Invoke-Checked "Convert BPMN to mCRL2" {
        & python $Converter $Model.Input $Mcrl2
    }

    $HasTimedProcess = Select-String -Path $Mcrl2 -Pattern "t: Real" -Quiet
    if ($HasTimedProcess) {
        Invoke-Checked "Generate timed LPS" {
            & mcrl22lps --timed $Mcrl2 $Lps
        }
    }
    else {
        Invoke-Checked "Generate LPS" {
            & mcrl22lps $Mcrl2 $Lps
        }
    }

    if (-not $SkipLts) {
        Invoke-Checked "Generate LTS" {
            & lps2lts $Lps $Lts
        }

        if (Get-Command "ltsinfo" -ErrorAction SilentlyContinue) {
            Write-Host ""
            Write-Host "LTS summary:"
            & ltsinfo $Lts
            if ($LASTEXITCODE -ne 0) {
                throw "ltsinfo failed with exit code $LASTEXITCODE."
            }
        }
    }

    $Results += [pscustomobject]@{
        Model = $Model.Name
        Mcrl2 = $Mcrl2
        Lps = $Lps
        Lts = if ($SkipLts) { "" } else { $Lts }
    }
}

Write-Host ""
Write-Host "Verification completed."
$Results | Format-Table -AutoSize
