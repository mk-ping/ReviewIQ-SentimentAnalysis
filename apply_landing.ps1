# Run from the repo root. Re-runnable. Changes frontend/src/main.tsx only. No migration.
$f = "frontend\src\main.tsx"
if (-not (Test-Path $f)) { Write-Host "Run this from the ReviewIQ repo root."; exit 1 }
$t = [IO.File]::ReadAllText($f)
if ($t -match "landing-upload") { Write-Host "Already applied."; exit 0 }
if ($t -notmatch '<Route index element=\{<Home />\} />') { Write-Host "Index route not found; no change made."; exit 1 }
$t = $t.Replace('import { BrowserRouter, Route, Routes } from "react-router-dom";', 'import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";')
$t = $t.Replace('<Route index element={<Home />} />', '{/* landing-upload: open on Upload, not on old results */}' + "`n" + '            <Route index element={<Navigate to="/upload" replace />} />' + "`n" + '            <Route path="home" element={<Home />} />')
[IO.File]::WriteAllText($f, $t, (New-Object Text.UTF8Encoding($true)))
$l = "frontend\src\Layout.tsx"
$x = [IO.File]::ReadAllText($l)
$x = $x.Replace('{ to: "/", label: "Home", ready: true },', '{ to: "/home", label: "Home (all data)", ready: true },')
[IO.File]::WriteAllText($l, $x, (New-Object Text.UTF8Encoding($true)))
Write-Host "Done. Restart npm run dev and open http://localhost:5173 - it lands on Upload."
