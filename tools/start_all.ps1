$root = Split-Path -Parent $PSScriptRoot
Start-Process 'C:\Users\Mehak\AppData\Local\Programs\DockerDesktop\Docker Desktop.exe' -ErrorAction SilentlyContinue
do { Start-Sleep -Seconds 5; docker info *> $null } until ($LASTEXITCODE -eq 0)
Set-Location $root
docker compose up -d db
Start-Sleep -Seconds 8
Start-Process powershell -ArgumentList '-NoExit','-Command',"cd '$root\backend'; .\.venv\Scripts\Activate.ps1; uvicorn app.main:app --reload --port 8010"
Start-Process powershell -ArgumentList '-NoExit','-Command',"cd '$root\backend'; .\.venv\Scripts\Activate.ps1; python -m app.worker.main"
Write-Host 'Docker, database, API and worker are starting. API: http://127.0.0.1:8010/app'
