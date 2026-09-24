param(
    [ValidateSet('all', 'DEMO-01', 'DEMO-02', 'DEMO-03', 'DEMO-04', 'DEMO-05')]
    [string]$Scenario = 'all',
    [ValidateSet('base', 'missing_document', 'unreadable_document', 'wrong_loan', 'followup')]
    [string]$Variant = 'base',
    [switch]$Fresh
)
$ErrorActionPreference = 'Stop'
$workspacePath = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $workspacePath
try {
    $seedArguments = @('-m', 'app.cli', 'seed-demo', '--scenario', $Scenario, '--variant', $Variant)
    if ($Fresh) { $seedArguments += '--fresh' }
    & .\.venv\Scripts\python.exe @seedArguments
    if ($LASTEXITCODE -ne 0) { throw 'Demo fixture loading failed.' }
} finally {
    Pop-Location
}
