# Runs every check and script that needs your machine (database, models, Docker) and writes docs\run_report.txt.
# Run from the project root with the backend venv active and Docker Desktop running:
#   .\tools\run_everything.ps1                 checks, migrations, baseline, held-out evaluation, evidence, ABSA, topics
#   .\tools\run_everything.ps1 -Training       also builds the public training data first (long download)
#   .\tools\run_everything.ps1 -Docker         also builds and starts the full Docker stack and calls /health
# It keeps going after a failure and prints one PASS / FAIL / SKIP line per step at the end.
# Steps that need a person (labelling) are only exported; the real-file upload is done on the Upload page.
param([switch]$Training, [switch]$Docker)
$ErrorActionPreference = 'Continue'
$root = (Get-Location).Path
$report = Join-Path $root 'docs\run_report.txt'
New-Item -ItemType Directory -Force -Path (Join-Path $root 'docs') | Out-Null
("ReviewIQ run report " + (Get-Date -Format 'yyyy-MM-dd HH:mm')) | Out-File -Encoding utf8 $report
$script:results = @()

function Step([string]$name, [scriptblock]$body, [string]$dir = '') {
  Write-Host ("== " + $name) -ForegroundColor Cyan
  if ($dir) { Push-Location (Join-Path $root $dir) }
  $global:LASTEXITCODE = 0
  $out = & $body *>&1 | Out-String
  $code = $LASTEXITCODE
  if ($dir) { Pop-Location }
  ("`n===== " + $name + " (exit " + $code + ")`n" + $out) | Out-File -Append -Encoding utf8 $report
  $status = 'FAIL'
  if ($code -eq 0) { $status = 'PASS' } elseif ($code -eq 2) { $status = 'SKIP' }
  $lines = @($out -split "`r?`n" | Where-Object { $_.Trim() -ne '' })
  $note = ''
  if ($lines.Count -gt 0) { $note = $lines[-1] }
  $colour = 'Red'
  if ($status -eq 'PASS') { $colour = 'Green' } elseif ($status -eq 'SKIP') { $colour = 'Yellow' }
  Write-Host ("   " + $status + "  " + $note) -ForegroundColor $colour
  $script:results += [pscustomobject]@{ Step = $name; Status = $status; Note = $note }
}

if (-not (Get-Command python -ErrorAction SilentlyContinue)) { Write-Host "python not found. Activate the backend venv first." -ForegroundColor Red; exit 1 }

Step 'Database is up' { docker compose up -d db }
Step 'Migrations at head' { python -m alembic upgrade head } 'backend'
Step 'Offline checks (every tests/check_*.py)' { $o = (.\tools\run_checks.ps1 *>&1 | Out-String); Write-Output $o; if (($o -match '([0-9]+) failed') -and ([int]$Matches[1] -gt 0)) { $global:LASTEXITCODE = 1 } else { $global:LASTEXITCODE = 0 } }
if ($Training) { Step 'Build public training data' { python reviewiq_train.py build } 'ml' }
Step 'Train the TF-IDF baseline' { python -m scripts.train_tfidf } 'backend'
Step 'Held-out evaluation table' { python -m scripts.eval_heldout --cap 300 } 'backend'
Step 'Ensemble weights (dry run)' { python -m scripts.calibrate_weights } 'backend'
Step 'Export 100 sentences to hand-check' { python -m scripts.sentence_check export } 'backend'
Step 'Export hidden-dissatisfaction sample' { python -m scripts.hidden_check export } 'backend'
Step 'ABSA validation of aspect sentiment' { python -m scripts.absa_validate } 'backend'
Step 'Topic discovery (BERTopic style)' { python -m scripts.topic_discovery } 'backend'
Step 'EXPLAIN ANALYZE evidence file' { .\tools\make_evidence.ps1 }
if ($Docker) {
  Step 'Docker full stack builds and starts' { docker compose -f docker-compose.full.yml up -d --build }
  Step 'Docker API answers /health' { Start-Sleep -Seconds 20; $r = Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8010/health; Write-Output $r.Content; if ($r.StatusCode -ne 200) { $global:LASTEXITCODE = 1 } else { $global:LASTEXITCODE = 0 } }
}

Write-Host ""
Write-Host "Summary" -ForegroundColor Cyan
$table = $script:results | Format-Table -AutoSize -Wrap | Out-String
Write-Host $table
$table | Out-File -Append -Encoding utf8 $report
$fails = @($script:results | Where-Object { $_.Status -eq 'FAIL' }).Count
Write-Host ($fails.ToString() + " step(s) failed. Full output: docs\run_report.txt")
Write-Host "Still done by hand: upload a real file and press Run full analysis, then fill data\sentence_check.csv and data\hidden_check.csv and run the 'score' commands."
