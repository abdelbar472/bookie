# Run Auth Service  (HTTP :8001 + gRPC :50051)
# Usage: .\run_auth.ps1
Set-Location $PSScriptRoot
$env:PYTHONUTF8 = "1"
python -m uvicorn auth.main:app --port 8001 --reload

