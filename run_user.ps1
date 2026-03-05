# Run User Service  (HTTP :8002)
# Usage: .\run_user.ps1
Set-Location $PSScriptRoot
$env:PYTHONUTF8 = "1"
python -m uvicorn user.main:app --port 8002 --reload

