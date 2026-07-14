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
    throw "Refusing to restore from a public session repository."
}

$python = Find-Python
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$snapshotTool = Join-Path $scriptRoot "codex_sessions.py"
$temporaryDirectory = Join-Path ([System.IO.Path]::GetTempPath()) "codex-session-restore"
if (Test-Path -LiteralPath $temporaryDirectory) {
    Remove-Item -LiteralPath $temporaryDirectory -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $temporaryDirectory | Out-Null

gh release download $ReleaseTag -R $Repository --dir $temporaryDirectory --pattern "codex-sessions-latest.*"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to download the Codex session snapshot."
}

$archive = Join-Path $temporaryDirectory "codex-sessions-latest.zip"
$checksumFile = Join-Path $temporaryDirectory "codex-sessions-latest.sha256"
$expected = ((Get-Content -LiteralPath $checksumFile -Raw).Trim() -split "\s+")[0].ToLowerInvariant()
$actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $archive).Hash.ToLowerInvariant()
if ($expected -ne $actual) {
    throw "Downloaded snapshot checksum does not match."
}

& $python $snapshotTool restore --archive $archive
if ($LASTEXITCODE -ne 0) {
    throw "Codex session restore failed."
}

Write-Host "Restored Codex sessions. Start Codex and verify the task list."

