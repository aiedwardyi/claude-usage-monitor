param(
    [string]$InstallDir,
    [string]$SettingsPath,
    [switch]$SkipVerify
)

$ErrorActionPreference = "Stop"

function Find-Python {
    foreach ($candidate in @(
        @{ Command = "py"; Args = @("-3") },
        @{ Command = "python"; Args = @() },
        @{ Command = "python3"; Args = @() }
    )) {
        try {
            $null = Get-Command $candidate.Command -ErrorAction Stop
            return $candidate
        } catch {
        }
    }

    throw "py -3, python, or python3 is required."
}

function Invoke-Python {
    param(
        [hashtable]$Python,
        [string]$ScriptPath,
        [string[]]$ScriptArgs
    )

    & $Python.Command @($Python.Args + @($ScriptPath) + $ScriptArgs)
}

function Get-InstallerArgs {
    $result = @()
    if ($InstallDir) {
        $result += @("--install-dir", $InstallDir)
    }
    if ($SettingsPath) {
        $result += @("--settings-path", $SettingsPath)
    }
    if ($SkipVerify) {
        $result += "--skip-verify"
    }
    return $result
}

$python = Find-Python
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$localInstaller = Join-Path $scriptDir "install.py"
$installerArgs = Get-InstallerArgs

if (Test-Path $localInstaller) {
    Invoke-Python -Python $python -ScriptPath $localInstaller -ScriptArgs $installerArgs
    exit $LASTEXITCODE
}

$repo = if ($env:CLAUDE_USAGE_MONITOR_REPO) { $env:CLAUDE_USAGE_MONITOR_REPO } else { "aiedwardyi/claude-usage-monitor" }
$ref = if ($env:CLAUDE_USAGE_MONITOR_REF) { $env:CLAUDE_USAGE_MONITOR_REF } else { "v0.1.3" }
$rawBase = "https://raw.githubusercontent.com/$repo/$ref"
$tempDir = Join-Path ([System.IO.Path]::GetTempPath()) ("claude-usage-monitor-install-" + [System.Guid]::NewGuid().ToString("N"))

New-Item -ItemType Directory -Path $tempDir | Out-Null

try {
    foreach ($file in @("install.py", "statusline.py", "statusline.sh", "statusline.cmd")) {
        Invoke-WebRequest -Uri "$rawBase/$file" -OutFile (Join-Path $tempDir $file)
    }

    $remoteArgs = @("--source-dir", $tempDir) + $installerArgs
    Invoke-Python -Python $python -ScriptPath (Join-Path $tempDir "install.py") -ScriptArgs $remoteArgs
    exit $LASTEXITCODE
} finally {
    Remove-Item -LiteralPath $tempDir -Recurse -Force -ErrorAction SilentlyContinue
}
