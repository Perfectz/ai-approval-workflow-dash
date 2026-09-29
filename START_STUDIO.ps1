param([int]$Port = 8767, [switch]$Foreground, [switch]$Rebuild)
$ErrorActionPreference = 'Stop'
$studioRoot = $PSScriptRoot
$studioPython = Join-Path $studioRoot '.venv\Scripts\python.exe'
Set-Location -LiteralPath $studioRoot
if (-not (Test-Path -LiteralPath $studioPython)) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
    & $studioPython -m pip install -r requirements-lock.txt
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
}
if ($Rebuild -or -not (Test-Path -LiteralPath (Join-Path $studioRoot 'dist\index.html'))) {
    npm ci
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
}
$studioUrl = "http://127.0.0.1:$Port"
if ($Foreground) { & $studioPython -m uvicorn studio.app:app --host 127.0.0.1 --port $Port; exit $LASTEXITCODE }
try { $studioSession = Invoke-RestMethod "$studioUrl/api/session" -TimeoutSec 2 } catch { $studioSession = $null }
if (-not $studioSession) {
    $studioLogs = Join-Path $studioRoot 'studio-data'
    New-Item -ItemType Directory -Path $studioLogs -Force | Out-Null
    Start-Process -FilePath $studioPython -ArgumentList @('-m','uvicorn','studio.app:app','--host','127.0.0.1','--port',"$Port") -WorkingDirectory $studioRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $studioLogs 'server.log') -RedirectStandardError (Join-Path $studioLogs 'server-error.log') | Out-Null
    for ($studioAttempt = 0; $studioAttempt -lt 20; $studioAttempt++) {
        Start-Sleep -Milliseconds 300
        try { $studioSession = Invoke-RestMethod "$studioUrl/api/session" -TimeoutSec 2; break } catch {}
    }
    if (-not $studioSession) { throw "Studio did not start. See studio-data/server-error.log." }
}
Write-Host "Director Studio is ready at $studioUrl"
Write-Host 'Data stays in studio-data. This server is bound to your computer only.'
