$ErrorActionPreference = 'Stop'
$irisRoot = $PSScriptRoot
$irisUrl = 'http://127.0.0.1:8765/dev'
$irisData = Join-Path $irisRoot 'data'
New-Item -ItemType Directory -Path $irisData -Force | Out-Null
$env:OLLAMA_MODELS = 'E:\codex\iris-models'
$env:HF_HOME = Join-Path $irisRoot 'models\huggingface'
$env:XDG_CACHE_HOME = Join-Path $irisRoot 'models\cache'
try {
    $listener = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
    if (-not $listener) {
        $irisProcess = Start-Process -FilePath (Join-Path $irisRoot '.venv\Scripts\python.exe') -ArgumentList @('-u', ('"' + (Join-Path $irisRoot 'iris_dashboard.py') + '"')) -WorkingDirectory $irisRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $irisData 'dashboard-stdout.log') -RedirectStandardError (Join-Path $irisData 'dashboard-stderr.log')
    }
    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        try {
            $page = Invoke-WebRequest -UseBasicParsing -Uri $irisUrl -TimeoutSec 2
            if ($page.StatusCode -eq 200 -and $page.Content.Contains('Developer Workspace')) { $ready = $true; break }
        } catch {}
        if ($irisProcess -and $irisProcess.HasExited) { break }
        Start-Sleep -Milliseconds 300
    }
    if (-not $ready) { throw 'Dashboard did not become ready. Check data\dashboard-stderr.log. An older dashboard or another program may occupy port 8765.' }
    Start-Process $irisUrl
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    Read-Host 'Press Enter to close'
    exit 1
}
