@echo off
set "OLLAMA_MODELS=E:\codex\iris-models"
set HF_HOME=%~dp0models\huggingface
set XDG_CACHE_HOME=%~dp0models\cache
powershell.exe -WindowStyle Hidden -NoProfile -Command "if (-not (Test-NetConnection -ComputerName 127.0.0.1 -Port 11434 -InformationLevel Quiet -WarningAction SilentlyContinue)) { Start-Process -FilePath 'E:\codex\ollama\ollama.exe' -ArgumentList 'serve' -WindowStyle Hidden; Start-Sleep -Seconds 2 }"
"%~dp0.venv\Scripts\python.exe" "%~dp0assistant.py"
