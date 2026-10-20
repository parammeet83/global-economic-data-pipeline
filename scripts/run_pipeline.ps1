<#
.SYNOPSIS
  Runs the pipeline once as a scheduled run (used by Windows Task Scheduler, D-31).

.DESCRIPTION
  Calls the same CLI as a manual run with --triggered-by scheduler, appends the output to
  logs\pipeline-YYYY-MM-DD.log (git-ignored) and exits with the CLI's exit code so Task
  Scheduler's "Last Run Result" is meaningful:
    0 success, 1 failed, 2 partial_success, 3 another run in progress, 4 startup error.
  Overlapping runs are refused by the database itself (D-19).

.EXAMPLE
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\run_pipeline.ps1
#>
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo ".venv\Scripts\python.exe"
$backend = Join-Path $repo "backend"
$logDir = Join-Path $repo "logs"
$logFile = Join-Path $logDir ("pipeline-{0:yyyy-MM-dd}.log" -f (Get-Date))

if (-not (Test-Path $python)) {
    Write-Error "Python virtual environment not found at $python. Create it and install backend\requirements.txt first."
    exit 4
}
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

Push-Location $backend
try {
    "===== {0:yyyy-MM-dd HH:mm:ss} scheduled run starting =====" -f (Get-Date) | Add-Content -Path $logFile -Encoding utf8
    # cmd.exe does the redirection so Python's log output on stderr never passes through Windows
    # PowerShell 5.1's error handling (which can abort the script and orphan a running run).
    # The CLI prints counts and a sanitized summary; it never prints credentials.
    $env:PYTHONIOENCODING = "utf-8"
    & cmd.exe /d /c "`"$python`" -m src.pipeline.cli run --triggered-by scheduler >> `"$logFile`" 2>&1"
    $code = $LASTEXITCODE
    "===== {0:yyyy-MM-dd HH:mm:ss} finished with exit code {1} =====" -f (Get-Date), $code | Add-Content -Path $logFile -Encoding utf8
} finally {
    Pop-Location
}
exit $code
