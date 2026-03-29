# run_recommendation.ps1 - start Recommendation micro-service
# HTTP on :8008

Set-Location $PSScriptRoot
$env:PYTHONUTF8 = "1"
$env:PYTHONPATH = "$PSScriptRoot"
python -m uvicorn recommendation.main:app --host 127.0.0.1 --port 8008 --reload

