
# Pins backend/requirements.txt to the versions installed in the active venv. Run from the repo root with the venv active
# and the app working. Keeps the original order, removes duplicates, writes the old file to requirements.unpinned.txt once.
$ErrorActionPreference = 'Stop'
$req = 'backend\requirements.txt'
$installed = @{}
(python -m pip list --format=json | ConvertFrom-Json) | ForEach-Object { $installed[($_.name.ToLower() -replace '[-_.]+', '-')] = $_.version }
if (-not (Test-Path 'backend\requirements.unpinned.txt')) { Copy-Item $req 'backend\requirements.unpinned.txt' }
$seen = @{}
$out = @('# Pinned to the versions that work (tools/pin_requirements.ps1). torch comes from the CPU index in the Dockerfile.')
foreach ($line in Get-Content 'backend\requirements.unpinned.txt') {
  $l = $line.Trim()
  if ($l -eq '' -or $l.StartsWith('#')) { continue }
  if ($l -notmatch '^([A-Za-z0-9_.-]+)(\[[^\]]*\])?') { continue }
  $name = $Matches[1]; $extra = $Matches[2]
  $key = $name.ToLower() -replace '[-_.]+', '-'
  if ($seen.ContainsKey($key)) { continue }
  $seen[$key] = $true
  if ($installed.ContainsKey($key)) {
    $v = $installed[$key] -replace '\+.*$', ''
    $out += "$name$extra==$v"
  } else {
    Write-Warning "$name is not installed in this venv, left unpinned"
    $out += $l
  }
}
Set-Content -Path $req -Value $out -Encoding ascii
Write-Host "wrote $req with $($out.Count - 1) packages"
