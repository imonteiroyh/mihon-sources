$ErrorActionPreference = 'Stop'
$bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
if (Test-Path -LiteralPath $bundledPython) {
    $pythonPath = $bundledPython
} else {
    $python = Get-Command python -CommandType Application -ErrorAction SilentlyContinue
    if (-not $python) {
        throw 'Python 3 was not found. Install it or add it to PATH.'
    }
    $pythonPath = $python.Source
}
& $pythonPath (Join-Path $PSScriptRoot 'generate_pb.py')
if ($LASTEXITCODE -ne 0) {
    throw "Generation failed with exit code $LASTEXITCODE."
}
Write-Host ''
Write-Host 'Done. Review the changes, then commit and push the files.'
