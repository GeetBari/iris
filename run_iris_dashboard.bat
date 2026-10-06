@echo off
set "OLLAMA_MODELS=E:\codex\iris-models"
set HF_HOME=%~dp0models\huggingface
set XDG_CACHE_HOME=%~dp0models\cache
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_dashboard.ps1"
