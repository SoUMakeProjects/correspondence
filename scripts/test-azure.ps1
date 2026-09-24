$ErrorActionPreference = 'Stop'
$workspacePath = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $workspacePath
try {
    & .\.venv\Scripts\python.exe -m app.azure_probe --live
    if ($LASTEXITCODE -ne 0) { throw 'The live Azure capability check did not pass; see the redacted result above.' }
} finally {
    Pop-Location
}
