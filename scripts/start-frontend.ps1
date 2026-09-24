$ErrorActionPreference = 'Stop'
$workspacePath = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $workspacePath
try {
    npm.cmd --prefix frontend run dev
    if ($LASTEXITCODE -ne 0) { throw 'Frontend stopped with an error.' }
} finally {
    Pop-Location
}
