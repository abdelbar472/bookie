# run_bookv2.ps1 - start the Book V2 micro-service
# HTTP on :8007

Set-Location $PSScriptRoot
$env:PYTHONUTF8 = "1"
$env:PYTHONPATH = "$PSScriptRoot"
python -m uvicorn bookv2.main:app --host 127.0.0.1 --port 8007 --reload

