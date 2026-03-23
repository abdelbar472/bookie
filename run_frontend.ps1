# run_frontend.ps1 - start frontend BFF + static UI
# HTTP on :8080

Set-Location $PSScriptRoot
$env:PYTHONUTF8 = "1"
$env:PYTHONPATH = "$PSScriptRoot"
python -m uvicorn frontend.app:app --host 127.0.0.1 --port 8080 --reload

