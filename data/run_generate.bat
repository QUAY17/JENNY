@echo off
REM JENNY Generate - sends corrected config to pipeline
REM Fixes applied: s6_intro populated, highlighted step set to ilvl2

curl -s -X POST http://localhost:5000/api/generate -H "Content-Type: application/json" -d @generate_payload.json > generate_response.json
type generate_response.json
echo.

REM Extract download URL and fetch the docx
powershell -Command "$r = Get-Content generate_response.json | ConvertFrom-Json; if ($r.success) { Write-Host ('SCORE: ' + $r.score); Write-Host ('Downloading from ' + $r.download_url); Invoke-WebRequest -Uri ('http://localhost:5000' + $r.download_url) -OutFile 'JENNY_OUTPUT.docx'; Write-Host 'Saved: JENNY_OUTPUT.docx' } else { Write-Host ('FAILED: ' + $r.error) }"
pause