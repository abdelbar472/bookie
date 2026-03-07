# run_follow.ps1 – start the Follow micro-service
# HTTP on :8003  |  gRPC on :50052

$env:PYTHONPATH = "$PSScriptRoot"
$env:PYTHONUTF8 = "1"
Set-Location $PSScriptRoot
python -m uvicorn follow.main:app --host 127.0.0.1 --port 8003 --reload

