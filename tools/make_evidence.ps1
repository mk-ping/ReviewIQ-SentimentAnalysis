# Writes the EXPLAIN ANALYZE evidence file (UTF-8, so it opens normally). Run from the project root.
Get-Content backend\scripts\explain_evidence.sql | docker exec -i reviewiq_db psql -U reviewiq -d reviewiq | Out-File -Encoding utf8 docs\explain_evidence.txt
Write-Host "Wrote docs\explain_evidence.txt"
