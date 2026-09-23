@echo off
set "OLLAMA_MODELS=E:\codex\iris-models"
set HF_HOME=%~dp0models\huggingface
set XDG_CACHE_HOME=%~dp0models\cache
start "Iris Dashboard" /b "%~dp0.venv\Scripts\python.exe" "%~dp0iris_dashboard.py"
timeout /t 3 /nobreak >nul
start "" "http://127.0.0.1:8765"
