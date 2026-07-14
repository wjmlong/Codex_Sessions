[CmdletBinding()]
param(
    [string]$Repository = "wjmlong/Codex_Sessions",
    [string]$ReleaseTag = "codex-sessions-latest"
)

$ErrorActionPreference = "Stop"

function Find-Python {
    $bundled = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    if (Test-Path -LiteralPath $bundled) {
        return $bundled
    }
    $command = Get-Command python -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }
    throw "Python was not found. Install Codex or Python 3 first."
}

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw "GitHub CLI was not found. Install it and run gh auth login."
}

$isPrivate = gh repo view $Repository --json isPrivate --jq .isPrivate
if ($LASTEXITCODE -ne 0) {
    throw "Cannot access GitHub repository $Repository."
}
if ($isPrivate.Trim().ToLowerInvariant() -ne "true") {
    throw "Refusing to upload Codex sessions because $Repository is public. Change it to private first."
}

$python = Find-Python
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$snapshotTool = Join-Path $scriptRoot "codex_sessions.py"
$temporaryDirectory = Join-Path ([System.IO.Path]::GetTempPath()) "codex-session-sync"
New-Item -ItemType Directory -Force -Path $temporaryDirectory | Out-Null
$archive = Join-Path $temporaryDirectory "codex-sessions-latest.zip"
$checksumFile = Join-Path $temporaryDirectory "codex-sessions-latest.sha256"

& $python $snapshotTool backup --output $archive
if ($LASTEXITCODE -ne 0) {
    throw "Codex session backup failed."
}

$checksum = (Get-FileHash -Algorithm SHA256 -LiteralPath $archive).Hash.ToLowerInvariant()
Set-Content -LiteralPath $checksumFile -Value "$checksum *codex-sessions-latest.zip" -Encoding ascii

gh release view $ReleaseTag -R $Repository *> $null
if ($LASTEXITCODE -ne 0) {
    gh release create $ReleaseTag -R $Repository --title "Latest Codex session snapshot" --notes "Managed by scripts/sync-to-github.ps1."
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create GitHub Release."
    }
}

gh release upload $ReleaseTag $archive $checksumFile -R $Repository --clobber
if ($LASTEXITCODE -ne 0) {
    throw "Failed to upload the Codex session snapshot."
}

Write-Host "Uploaded verified Codex session snapshot to $Repository release $ReleaseTag."

