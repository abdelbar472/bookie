# run_bookv3.ps1 - start Book Service V3
# HTTP on :8009, gRPC configured via env/config (default 50057)

param(
    [switch]$Reload
)

Set-Location $PSScriptRoot
$env:PYTHONUTF8 = "1"
$env:PYTHONPATH = "$PSScriptRoot"

if ($Reload) {
    python -m uvicorn book_service_v3.main:app --host 127.0.0.1 --port 8009 --reload
}
else {
    python -m uvicorn book_service_v3.main:app --host 127.0.0.1 --port 8009
}

