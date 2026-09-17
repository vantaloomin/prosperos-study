param([switch]$NoBrowser, [switch]$NoPause, [ValidateRange(1024, 65535)][int]$Port = 8765)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$result = 0
try {
    $python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $python)) { throw 'Dependencies are missing. Double-click install.bat first.' }
    if (-not (Test-Path -LiteralPath 'dist\index.html')) { throw 'The interface is not built. Double-click install.bat first.' }
    $arguments = @('-m', 'scripts.launch_interface', '--port', [string]$Port)
    if ($NoBrowser) { $arguments += '--no-browser' }
    & $python @arguments
    $result = $LASTEXITCODE
} catch {
    Write-Host "Launch failed: $($_.Exception.Message)" -ForegroundColor Red
    $result = 1
}
if ($result -ne 0 -and -not $NoPause) { Read-Host 'Press Enter to close' | Out-Null }
exit $result
