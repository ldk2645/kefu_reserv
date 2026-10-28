param([switch]$Smoke)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$projectPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $projectPython)) {
    throw 'Create .venv and install requirements-lock.txt first. See README.md.'
}
Push-Location -LiteralPath $projectRoot
try {
    if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'models\manifest.json'))) {
        & $projectPython 'scripts/prepare_ocr.py'
        if ($LASTEXITCODE -ne 0) { throw 'OCR model preparation failed.' }
    }
    if ($Smoke) { & $projectPython -m app.main --smoke }
    else { & $projectPython -m app.main }
    if ($LASTEXITCODE -ne 0) { throw 'Application exited with an error.' }
}
finally {
    Pop-Location
}
