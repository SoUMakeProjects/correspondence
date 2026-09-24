$ErrorActionPreference = 'Stop'
$workspacePath = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $workspacePath
try {
    & .\.venv\Scripts\python.exe .\scripts\package_demo.py
    if ($LASTEXITCODE -ne 0) { throw 'Demo packaging failed.' }
} finally {
    Pop-Location
}
