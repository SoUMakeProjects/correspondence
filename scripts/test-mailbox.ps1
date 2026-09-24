param([ValidateSet('all', 'DEMO-01', 'DEMO-02', 'DEMO-03', 'DEMO-04', 'DEMO-05')][string]$Scenario = 'all')
$ErrorActionPreference = 'Stop'
$workspacePath = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $workspacePath
try {
    & .\.venv\Scripts\python.exe -m app.workflow_evaluation --live --mailbox --scenario $Scenario
    if ($LASTEXITCODE -ne 0) { throw 'Live mailbox evaluation failed. Inspect the retained report.' }
} finally {
    Pop-Location
}
