# run_book.ps1 – start the Book micro-service
# HTTP on :8004  |  gRPC on :50054

Set-Location $PSScriptRoot
$env:PYTHONUTF8 = "1"
$env:PYTHONPATH = "$PSScriptRoot"
python -m uvicorn book.main:app --host 127.0.0.1 --port 8004 --reload

