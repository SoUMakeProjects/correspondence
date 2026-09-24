$ErrorActionPreference = 'Stop'
$workspacePath = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $workspacePath
try {
    & .\.venv\Scripts\python.exe -m app.cli serve
    if ($LASTEXITCODE -ne 0) { throw 'Backend stopped with an error.' }
} finally {
    Pop-Location
}
