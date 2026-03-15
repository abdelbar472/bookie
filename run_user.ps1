# Run User Service  (HTTP :8002)
# Usage: .\run_user.ps1
Set-Location $PSScriptRoot
$env:PYTHONUTF8 = "1"
$env:PYTHONPATH = "$PSScriptRoot"
python -m uvicorn user.main:app --host 127.0.0.1 --port 8002 --reload

