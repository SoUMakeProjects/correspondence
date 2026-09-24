$ErrorActionPreference = 'Stop'
$workspacePath = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $workspacePath
try {
    $pythonPath = Join-Path $workspacePath '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $pythonPath)) {
        python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Python environment creation failed.' }
    }
    & $pythonPath -m pip install -r backend/requirements.lock
    if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed.' }
    & $pythonPath -m pip install --no-deps -e backend
    if ($LASTEXITCODE -ne 0) { throw 'Backend package installation failed.' }
    npm.cmd --prefix frontend ci --no-fund
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
    if (-not (Test-Path -LiteralPath '.env')) {
        Copy-Item -LiteralPath '.env.example' -Destination '.env'
    }
    & $pythonPath -m app.cli migrate
    if ($LASTEXITCODE -ne 0) { throw 'Database migration failed.' }
    Write-Output 'Setup complete. Existing .env values were preserved.'
} finally {
    Pop-Location
}
