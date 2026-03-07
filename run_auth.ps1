# Run Auth Service  (HTTP :8001 + gRPC :50051)
# Usage: .\run_auth.ps1
Set-Location $PSScriptRoot
$env:PYTHONUTF8 = "1"
python -m uvicorn auth.main:app --host 127.0.0.1 --port 8001 --reload

