$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Executable failed with exit code $LASTEXITCODE" }
}

$pythonPath = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
Invoke-Checked $pythonPath @('scripts/check_repository.py')
$testBase = Join-Path $PSScriptRoot 'test-results'
New-Item -ItemType Directory -Force -Path $testBase | Out-Null
$testPath = Join-Path $testBase ('pytest-' + [guid]::NewGuid().ToString('N'))
if (-not $testPath.StartsWith($PSScriptRoot + '\')) { throw 'Invalid test directory' }
Invoke-Checked $pythonPath @('-m', 'pytest', '-q', '--tb=short', "--basetemp=$testPath")
Invoke-Checked $pythonPath @('-m', 'ruff', 'check', 'server', 'tests', 'scripts')
Invoke-Checked 'npm.cmd' @('run', 'test:ui-models')
Invoke-Checked 'npm.cmd' @('run', 'lint')
Invoke-Checked 'npm.cmd' @('run', 'build')
