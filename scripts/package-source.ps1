param([string]$OutputPath)
$ErrorActionPreference = 'Stop'
$workspacePath = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $workspacePath '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Run scripts/setup.ps1 first to install the packaging dependencies.'
}
# Resolve a supplied output relative to the caller before changing directories.
$packageArguments = @()
if ($OutputPath) {
    $packageArguments = @('--output', $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputPath))
}
Push-Location -LiteralPath $workspacePath
try {
    & $pythonPath .\scripts\package_source.py @packageArguments
    if ($LASTEXITCODE -ne 0) { throw 'Source packaging failed.' }
} finally {
    Pop-Location
}
