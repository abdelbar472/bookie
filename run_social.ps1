# run_social.ps1 - start the Social micro-service
# HTTP on :8005

Set-Location $PSScriptRoot
$env:PYTHONUTF8 = "1"
$env:PYTHONPATH = "$PSScriptRoot"
python -m uvicorn social.main:app --host 127.0.0.1 --port 8005 --reload

