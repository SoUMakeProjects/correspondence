$ErrorActionPreference = 'Stop'
$workspacePath = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $workspacePath
try {
    & .\.venv\Scripts\python.exe -m app.agent_evaluation --live
    if ($LASTEXITCODE -ne 0) { throw 'Live agent evaluation failed. Inspect .local/phase6-live-latest.json and the retained run records.' }
} finally {
    Pop-Location
}
