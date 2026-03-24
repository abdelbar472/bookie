Set-Location $PSScriptRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
	Write-Host "Python virtualenv not found at .venv\Scripts\python.exe" -ForegroundColor Red
	exit 1
}

& .\.venv\Scripts\python.exe -m uvicorn RAG.main:app --host 127.0.0.1 --port 8006 --reload

