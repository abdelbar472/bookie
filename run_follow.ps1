# run_follow.ps1 – start the Follow micro-service
# HTTP on :8003  |  gRPC on :50052

Set-Location $PSScriptRoot
$env:PYTHONUTF8 = "1"
$env:PYTHONPATH = "$PSScriptRoot"
python -m uvicorn follow.main:app --host 127.0.0.1 --port 8003 --reload

