
# Runs every backend/tests/check_*.py and prints PASS or FAIL for each. Run from the repo root with the venv active.
# check_search and check_hidden_mv need the database; check_sentiment downloads models once; check_aspects and
# check_llm_mapping skip their live part when Ollama is not running.
$ErrorActionPreference = 'Continue'
Push-Location backend
$fail = 0
foreach ($f in Get-ChildItem tests -Filter 'check_*.py' | Sort-Object Name) {
  $mod = 'tests.' + $f.BaseName
  $out = python -m $mod 2>&1
  if ($LASTEXITCODE -eq 0) { Write-Host ("PASS  " + $f.BaseName) -ForegroundColor Green }
  else { Write-Host ("FAIL  " + $f.BaseName) -ForegroundColor Red; $out | Select-Object -Last 4 | ForEach-Object { Write-Host ("      " + $_) }; $fail++ }
}
Pop-Location
Write-Host ("`n" + $fail + " failed")
