$ErrorActionPreference = 'Stop'
$workspacePath = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $workspacePath
try {
    & .\.venv\Scripts\python.exe -m app.recovery_evaluation --live
    if ($LASTEXITCODE -ne 0) { throw 'Live recovery evaluation failed. Inspect .local/phase8-live-latest.json and retained records.' }
} finally {
    Pop-Location
}
