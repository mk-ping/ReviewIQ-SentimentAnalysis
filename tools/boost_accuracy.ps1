# Step 38: one command for the whole CPU accuracy boost, then the before/after benchmark.
# Usage (from the repo root):  .\tools\boost_accuracy.ps1
$ErrorActionPreference = "Stop"
Set-Location "$PSScriptRoot\..\backend"
& .\.venv\Scripts\Activate.ps1
pip install datasets scikit-learn | Out-Null
Copy-Item ..\docs\benchmark_results.md ..\docs\benchmark_before.md -ErrorAction SilentlyContinue
python -m scripts.train_mixed --per-set 1400
python -m scripts.benchmark_labeled --cap 500
Write-Host ""
Write-Host "Done. Compare docs\benchmark_before.md with docs\benchmark_results.md, and read docs\mixed_training.md."
