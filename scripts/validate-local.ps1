$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot

$tempRoot = Join-Path $repoRoot ('.local-validation-' + [guid]::NewGuid().ToString('N'))
$apiOut = Join-Path $tempRoot 'api.out.log'
$apiErr = Join-Path $tempRoot 'api.err.log'
$uiOut = Join-Path $tempRoot 'react.out.log'
$uiErr = Join-Path $tempRoot 'react.err.log'
$oldTemp = $env:TEMP
$oldTmp = $env:TMP
$oldApiTarget = $env:NHSC_API_TARGET
$oldUiUrl = $env:NHSC_UI_BASE_URL
$oldPrewarm = $env:NHSC_PREWARM_SEARCH
$apiProcess = $null
$frontendProcess = $null

function Get-FreeLoopbackPort {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
    $listener.Start()
    $port = ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port
    $listener.Stop()
    return $port
}

function Wait-ForUrl([string]$Url, [int]$ProcessId, [string]$Label) {
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        if (-not (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)) {
            throw "$Label exited before becoming ready. See logs under $tempRoot"
        }
        try {
            $null = Invoke-WebRequest -UseBasicParsing $Url -TimeoutSec 2
            return
        } catch {
            Start-Sleep -Seconds 1
        }
    }
    throw "$Label did not become ready at $Url. See logs under $tempRoot"
}

try {
    New-Item -ItemType Directory -Path $tempRoot | Out-Null
    $env:TEMP = $tempRoot
    $env:TMP = $tempRoot

    Write-Host 'Compiling Python modules...'
    python -m compileall -q cases.py footer.py pages utils scripts api tests validate_ui.py webapp/backend
    if ($LASTEXITCODE -ne 0) { throw 'Python compile check failed' }

    Write-Host 'Running Python tests...'
    python -m pytest tests -q
    if ($LASTEXITCODE -ne 0) { throw 'Python test suite failed' }

    Write-Host 'Installing frontend dependencies and building React...'
    $localVite = Join-Path $repoRoot 'webapp/frontend/node_modules/vite/bin/vite.js'
    Push-Location (Join-Path $repoRoot 'webapp/frontend')
    try {
        if (-not (Test-Path -LiteralPath $localVite)) {
            npm ci
            if ($LASTEXITCODE -ne 0) { throw 'npm ci failed' }
        } else {
            Write-Host 'Using the installed frontend dependencies.'
        }
        npm run build
        if ($LASTEXITCODE -ne 0) { throw 'React production build failed' }
    } finally {
        Pop-Location
    }

    Write-Host 'Testing the frontend API proxy...'
    node --test webapp/frontend/tests/proxy.test.js
    if ($LASTEXITCODE -ne 0) { throw 'Frontend proxy tests failed' }

    $apiPort = Get-FreeLoopbackPort
    $uiPort = Get-FreeLoopbackPort
    if ($uiPort -eq $apiPort) { $uiPort = Get-FreeLoopbackPort }
    $env:NHSC_PREWARM_SEARCH = '0'
    $env:NHSC_API_TARGET = "http://127.0.0.1:$apiPort"
    $env:NHSC_UI_BASE_URL = "http://127.0.0.1:$uiPort"

    $apiProcess = Start-Process -FilePath 'python' -ArgumentList @(
        '-m', 'uvicorn', 'webapp.backend.main:app', '--host', '127.0.0.1', '--port', "$apiPort"
    ) -WorkingDirectory $repoRoot -RedirectStandardOutput $apiOut -RedirectStandardError $apiErr -PassThru -WindowStyle Hidden

    $nodePath = (Get-Command node.exe).Source
    $vitePath = Join-Path $repoRoot 'webapp/frontend/node_modules/vite/bin/vite.js'
    $frontendProcess = Start-Process -FilePath $nodePath -ArgumentList @(
        $vitePath, '--host', '127.0.0.1', '--port', "$uiPort", '--strictPort'
    ) -WorkingDirectory (Join-Path $repoRoot 'webapp/frontend') -RedirectStandardOutput $uiOut -RedirectStandardError $uiErr -PassThru -WindowStyle Hidden

    Wait-ForUrl "http://127.0.0.1:$apiPort/api/health" $apiProcess.Id 'FastAPI'
    Wait-ForUrl "http://127.0.0.1:$uiPort/" $frontendProcess.Id 'React'

    Write-Host 'Running React and FastAPI Playwright smoke checks...'
    python scripts/validate_react_ui.py
    if ($LASTEXITCODE -ne 0) { throw 'Playwright smoke checks failed' }

    Write-Host 'All local validation checks passed.'
} catch {
    Write-Host "Validation failed: $($_.Exception.Message)" -ForegroundColor Red
    if (Test-Path -LiteralPath $apiErr) { Get-Content -LiteralPath $apiOut,$apiErr,$uiOut,$uiErr -ErrorAction SilentlyContinue }
    exit 1
} finally {
    if ($frontendProcess) { Stop-Process -Id $frontendProcess.Id -Force -ErrorAction SilentlyContinue }
    if ($apiProcess) { Stop-Process -Id $apiProcess.Id -Force -ErrorAction SilentlyContinue }
    $env:TEMP = $oldTemp
    $env:TMP = $oldTmp
    $env:NHSC_API_TARGET = $oldApiTarget
    $env:NHSC_UI_BASE_URL = $oldUiUrl
    $env:NHSC_PREWARM_SEARCH = $oldPrewarm
    Pop-Location
    if (Test-Path -LiteralPath $tempRoot) {
        $resolvedTemp = (Resolve-Path -LiteralPath $tempRoot).Path
        if ($resolvedTemp.StartsWith($repoRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
            Remove-Item -LiteralPath $resolvedTemp -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}
