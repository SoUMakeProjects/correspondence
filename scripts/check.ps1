param([switch]$Browser)
$ErrorActionPreference = 'Stop'
$workspacePath = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $workspacePath
try {
    & .\.venv\Scripts\python.exe -m ruff check backend
    if ($LASTEXITCODE -ne 0) { throw 'Backend lint failed.' }
    & .\.venv\Scripts\python.exe -m ruff format --check backend
    if ($LASTEXITCODE -ne 0) { throw 'Backend formatting failed.' }
    & .\.venv\Scripts\python.exe -m pytest backend/tests
    if ($LASTEXITCODE -ne 0) { throw 'Backend tests failed.' }
    & .\.venv\Scripts\python.exe -m app.cli check-openapi
    if ($LASTEXITCODE -ne 0) { throw 'API contract is stale.' }
    & .\.venv\Scripts\python.exe -m app.cli check-data
    if ($LASTEXITCODE -ne 0) { throw 'Versioned fixture/catalog validation failed.' }
    npm.cmd --prefix frontend run check:api
    if ($LASTEXITCODE -ne 0) { throw 'Generated frontend API types are stale.' }
    npm.cmd --prefix frontend run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
    if ($Browser) {
        npm.cmd --prefix frontend run test:e2e
        if ($LASTEXITCODE -ne 0) { throw 'Browser checks failed.' }
    }
} finally {
    Pop-Location
}
