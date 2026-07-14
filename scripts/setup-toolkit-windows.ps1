[CmdletBinding()]
param(
    [string]$ToolkitDirectory = "C:\cst",
    [string]$RepositoryUrl = "https://github.com/wjmlong/Codex_Sessions.git",
    [string]$ProxyUrl = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$patchFile = Join-Path $repositoryRoot "patches\toolkit-nested-session-meta.patch"

function Find-Python {
    $bundled = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    if (Test-Path -LiteralPath $bundled) {
        return $bundled
    }
    foreach ($name in @("python", "py", "python3")) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command) {
            return $command.Source
        }
    }
    throw "Python 3 was not found."
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "Git was not found."
}

if (-not (Test-Path -LiteralPath $ToolkitDirectory)) {
    if ($ProxyUrl) {
        git -c "http.proxy=$ProxyUrl" clone https://github.com/lyston11/codex-session-toolkit.git $ToolkitDirectory
    } else {
        git clone https://github.com/lyston11/codex-session-toolkit.git $ToolkitDirectory
    }
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to clone codex-session-toolkit."
    }
}

$previousErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
git -C $ToolkitDirectory apply --reverse --check $patchFile *> $null
$patchAlreadyApplied = $LASTEXITCODE -eq 0
$ErrorActionPreference = $previousErrorActionPreference
if (-not $patchAlreadyApplied) {
    git -C $ToolkitDirectory apply --check $patchFile
    if ($LASTEXITCODE -ne 0) {
        throw "The compatibility patch does not apply to this Toolkit version."
    }
    git -C $ToolkitDirectory apply $patchFile
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to apply the compatibility patch."
    }
}

$python = Find-Python
& (Join-Path $ToolkitDirectory "install.ps1") -Python $python
if ($LASTEXITCODE -ne 0) {
    throw "Toolkit installation failed."
}

$toolkit = Join-Path $ToolkitDirectory ".venv\Scripts\codex-session-toolkit.cmd"
Push-Location $ToolkitDirectory
try {
    & $toolkit connect-github $RepositoryUrl --branch main
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to connect the bundle repository."
    }

    $bundleRepository = Join-Path $ToolkitDirectory "codex_bundles"
    git -C $bundleRepository config --local core.longpaths true
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to enable long Windows paths for the bundle repository."
    }

    if ($ProxyUrl) {
        & $toolkit github-proxy $ProxyUrl
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to configure the Toolkit GitHub proxy."
        }
    }

    & $toolkit pull-github --branch main
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to pull Codex bundles."
    }

    & $toolkit validate-bundles
    if ($LASTEXITCODE -ne 0) {
        throw "Bundle validation failed."
    }
} finally {
    Pop-Location
}

Write-Host "Toolkit setup complete. Start it with:"
Write-Host "  $ToolkitDirectory\codex-session-toolkit.cmd"
Write-Host "Then import bundles from Bundle / Transfer with Desktop visibility enabled."
