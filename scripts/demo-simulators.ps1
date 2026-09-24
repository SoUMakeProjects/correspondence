$ErrorActionPreference = 'Stop'
$workspacePath = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $workspacePath
try {
    & .\.venv\Scripts\python.exe -m app.simulator_demo
    if ($LASTEXITCODE -ne 0) { throw 'The local simulator demonstration failed. Inspect its recorded actions before retrying.' }
} finally {
    Pop-Location
}
