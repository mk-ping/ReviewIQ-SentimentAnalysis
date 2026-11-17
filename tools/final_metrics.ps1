# Produces every number for the final report: model comparison, learned model combination, full metric tables and figures.
# Run from the project root:  .\tools\final_metrics.ps1        (needs the database running and ml data built)
param([int]$ValCap = 1500, [int]$TestCap = 600)
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $root "backend")
if (Test-Path ".\.venv\Scripts\Activate.ps1") { . .\.venv\Scripts\Activate.ps1 }
Write-Host "1/3 Held-out model comparison and ablation" -ForegroundColor Cyan
python -m scripts.eval_heldout --cap $TestCap
Write-Host "2/3 Learned model combination (stacker) with gating" -ForegroundColor Cyan
python -m scripts.train_stacker --val-cap $ValCap --test-cap $TestCap
Write-Host "3/3 Writing docs\final_metrics.md and docs\figures" -ForegroundColor Cyan
python -m scripts.final_report
Set-Location $root
Write-Host "Done. Open docs\final_metrics.md" -ForegroundColor Green
