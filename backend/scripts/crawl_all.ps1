# Collects the real training corpus: EUW + EUNE Challenger solo-queue games.
# Run from anywhere: powershell -File backend\scripts\crawl_all.ps1
$ErrorActionPreference = "Continue"
$backend = Split-Path -Parent $PSScriptRoot
Set-Location $backend
$py = Join-Path $backend ".venv\Scripts\python.exe"
& $py -m nexuspulse crawl --max-matches 700 --platform euw1 *> (Join-Path $backend "data\crawl_euw.log")
& $py -m nexuspulse crawl --max-matches 300 --platform eun1 *> (Join-Path $backend "data\crawl_eune.log")
"done" | Out-File (Join-Path $backend "data\crawl_done.flag")
