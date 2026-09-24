$ErrorActionPreference = 'Stop'
$workspacePath = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $workspacePath
try {
    & .\.venv\Scripts\python.exe -m app.cli export-openapi
    if ($LASTEXITCODE -ne 0) { throw 'OpenAPI export failed.' }
    npm.cmd --prefix frontend run generate:api
    if ($LASTEXITCODE -ne 0) { throw 'Frontend type generation failed.' }
} finally {
    Pop-Location
}
