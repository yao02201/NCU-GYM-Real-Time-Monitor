[CmdletBinding()]
param(
    [Parameter()]
    [string]$ProjectRoot,

    [Parameter()]
    [string]$DesktopDirectory = [Environment]::GetFolderPath('Desktop'),

    [Parameter()]
    [string]$PythonPath,

    [Parameter()]
    [string]$PythonInstallerPath,

    [Parameter()]
    [string]$PythonInstallerSha256,

    [Parameter()]
    [string]$InstalledPythonPath,

    [Parameter()]
    [switch]$SkipPythonDiscovery,

    [Parameter()]
    [switch]$TestMode
)

$ErrorActionPreference = 'Stop'
$stage = 'initialization'
$downloadedInstaller = $null
$officialInstallerUri = 'https://www.python.org/ftp/python/3.13.15/python-3.13.15-amd64.exe'
$officialInstallerSha256 = 'edec09c4853aeae9ac36efb8c9f95b6b8e2fee65eee56d9767a8b7c69c574403'

if (-not $ProjectRoot) {
    $ProjectRoot = Split-Path -Parent $PSScriptRoot
}

function Resolve-RegularPython {
    if ($PythonPath) {
        if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
            throw "The requested Python executable does not exist: $PythonPath"
        }
        $explicitPython = (Resolve-Path -LiteralPath $PythonPath).Path
        if (-not $TestMode -and $explicitPython -match '[\\/](\.cache[\\/]codex-runtimes|\.codex)[\\/]') {
            throw 'A Codex-managed runtime cannot be used as the regular Python installation.'
        }
        if (-not (Test-SuitableRegularPython -Candidate $explicitPython -AllowCodex:$TestMode)) {
            throw 'The requested Python is not a suitable regular Python 3.10 or newer installation.'
        }
        return $explicitPython
    }

    $candidates = [System.Collections.Generic.List[string]]::new()
    $command = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($command) {
        $candidates.Add($command.Source)
    }

    $pythonInstallRoot = Join-Path $env:LOCALAPPDATA 'Programs\Python'
    if (Test-Path -LiteralPath $pythonInstallRoot -PathType Container) {
        Get-ChildItem -LiteralPath $pythonInstallRoot -Filter python.exe -File -Recurse -ErrorAction SilentlyContinue |
            Sort-Object FullName -Descending |
            ForEach-Object { $candidates.Add($_.FullName) }
    }

    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if (Test-SuitableRegularPython -Candidate $candidate) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }

    return $null
}

function Test-SuitableRegularPython {
    param(
        [Parameter(Mandatory)]
        [string]$Candidate,

        [Parameter()]
        [switch]$AllowCodex
    )

    if (-not (Test-Path -LiteralPath $Candidate -PathType Leaf)) {
        return $false
    }
    if ($Candidate -like '*WindowsApps*') {
        return $false
    }
    if (-not $AllowCodex -and $Candidate -match '[\\/](\.cache[\\/]codex-runtimes|\.codex)[\\/]') {
        return $false
    }

    try {
        & $Candidate -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
}

try {
    if (
        -not $TestMode -and
        ($SkipPythonDiscovery -or $PythonInstallerPath -or $PythonInstallerSha256 -or $InstalledPythonPath)
    ) {
        throw 'Controlled Python installer options are test-only and require -TestMode.'
    }

    if (-not (Test-Path -LiteralPath $ProjectRoot -PathType Container)) {
        throw "The checkout does not exist: $ProjectRoot"
    }
    if (-not (Test-Path -LiteralPath $DesktopDirectory -PathType Container)) {
        throw "The desktop directory does not exist: $DesktopDirectory"
    }

    $launcherPath = Join-Path $ProjectRoot 'windows\Launch-NCUGymMonitor.ps1'
    $silentLauncherPath = Join-Path $ProjectRoot 'windows\Launch-NCUGymMonitor.vbs'
    $monitorEntryPath = Join-Path $ProjectRoot 'monitor_entry.pyw'
    $instanceModulePath = Join-Path $ProjectRoot 'monitor_instance.py'
    $widgetEntryPath = Join-Path $ProjectRoot 'gym.pyw'
    $requirementsPath = Join-Path $ProjectRoot 'requirements-runtime.txt'
    $iconPath = Join-Path $ProjectRoot 'assets\ncu-gym-monitor.ico'
    foreach ($requiredPath in @($launcherPath, $silentLauncherPath, $monitorEntryPath, $instanceModulePath, $widgetEntryPath, $requirementsPath, $iconPath)) {
        if (-not (Test-Path -LiteralPath $requiredPath -PathType Leaf)) {
            throw "The checkout is incomplete. Missing: $requiredPath"
        }
    }

    $stage = 'Python discovery'
    $resolvedPython = if ($SkipPythonDiscovery) { $null } else { Resolve-RegularPython }
    if (-not $resolvedPython) {
        $installerToRun = $PythonInstallerPath
        $expectedInstallerHash = $PythonInstallerSha256
        $controlledInstaller = [bool]$PythonInstallerPath

        if (-not $installerToRun) {
            $stage = 'Python installer download'
            $downloadedInstaller = Join-Path ([System.IO.Path]::GetTempPath()) 'ncu-gym-python-3.13.15-amd64.exe'
            Invoke-WebRequest -Uri $officialInstallerUri -OutFile $downloadedInstaller -UseBasicParsing
            $installerToRun = $downloadedInstaller
            $expectedInstallerHash = $officialInstallerSha256
        }

        $stage = 'Python installer validation'
        if (-not (Test-Path -LiteralPath $installerToRun -PathType Leaf)) {
            throw "Python installation media does not exist: $installerToRun"
        }
        if (-not $expectedInstallerHash) {
            throw 'An expected SHA-256 is required before Python installation media can run.'
        }
        $actualInstallerHash = (Get-FileHash -LiteralPath $installerToRun -Algorithm SHA256).Hash
        if ($actualInstallerHash -ne $expectedInstallerHash) {
            throw 'Python installation media failed SHA-256 validation.'
        }

        if (-not $controlledInstaller) {
            $signature = Get-AuthenticodeSignature -LiteralPath $installerToRun
            if (
                $signature.Status -ne [System.Management.Automation.SignatureStatus]::Valid -or
                $signature.SignerCertificate.Subject -notlike '*Python Software Foundation*'
            ) {
                throw 'Python installation media does not have a valid Python Software Foundation signature.'
            }
        }

        $stage = 'per-user Python installation'
        if ($controlledInstaller) {
            $installerProcess = Start-Process -FilePath $installerToRun -Wait -PassThru
        }
        else {
            $installerProcess = Start-Process `
                -FilePath $installerToRun `
                -ArgumentList @(
                    '/quiet',
                    'InstallAllUsers=0',
                    'PrependPath=0',
                    'Include_launcher=0',
                    'Include_test=0',
                    'SimpleInstall=1'
                ) `
                -Wait `
                -PassThru
        }
        if ($installerProcess.ExitCode -ne 0) {
            throw "Python installer exited with code $($installerProcess.ExitCode)."
        }

        if ($InstalledPythonPath) {
            if (-not (Test-Path -LiteralPath $InstalledPythonPath -PathType Leaf)) {
                throw "The installed Python executable was not found: $InstalledPythonPath"
            }
            $resolvedPython = (Resolve-Path -LiteralPath $InstalledPythonPath).Path
        }
        else {
            $resolvedPython = Resolve-RegularPython
        }
        if (-not $resolvedPython) {
            throw 'Python installation completed, but python.exe could not be located.'
        }
    }

    $stage = 'Python validation'
    & $resolvedPython -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'
    if ($LASTEXITCODE -ne 0) {
        throw 'Python 3.10 or newer is required for the Project environment.'
    }

    $stage = 'Project environment creation'
    $environmentPath = Join-Path $ProjectRoot '.venv'
    $environmentPython = Join-Path $environmentPath 'Scripts\python.exe'
    $environmentHealthy = $false
    if (Test-Path -LiteralPath $environmentPython -PathType Leaf) {
        try {
            & $environmentPython -c 'import sys; raise SystemExit(0 if sys.prefix != sys.base_prefix else 1)'
            $environmentHealthy = $LASTEXITCODE -eq 0
        }
        catch {
            $environmentHealthy = $false
        }
    }

    if (-not $environmentHealthy) {
        if (Test-Path -LiteralPath $environmentPath) {
            $normalizedProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\')
            $normalizedEnvironmentPath = [System.IO.Path]::GetFullPath($environmentPath).TrimEnd('\')
            $expectedEnvironmentPath = (Join-Path $normalizedProjectRoot '.venv').TrimEnd('\')
            if ($normalizedEnvironmentPath -ne $expectedEnvironmentPath) {
                throw 'Refusing to repair a Project environment outside the checkout.'
            }
            Remove-Item -LiteralPath $normalizedEnvironmentPath -Recurse -Force
        }
        & $resolvedPython -m venv $environmentPath
        if ($LASTEXITCODE -ne 0) {
            throw 'Python could not create the Project environment.'
        }
    }

    $stage = 'runtime dependency installation'
    & $environmentPython -m pip install --disable-pip-version-check -r $requirementsPath
    if ($LASTEXITCODE -ne 0) {
        throw 'Widget runtime dependencies could not be installed.'
    }

    $stage = 'Desktop shortcut creation'
    $shortcutPath = Join-Path $DesktopDirectory 'NCU Gym Monitor.lnk'
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = (Get-Command wscript.exe).Source
    $shortcut.Arguments = "`"$silentLauncherPath`""
    $shortcut.WorkingDirectory = $ProjectRoot
    $shortcut.IconLocation = "$iconPath,0"
    $shortcut.Description = 'Launch NCU Gym Monitor'
    $shortcut.Save()

    Write-Host "NCU Gym Monitor Setup completed. Shortcut: $shortcutPath"
}
catch {
    [Console]::Error.WriteLine("Setup failed during ${stage}: $($_.Exception.Message)")
    exit 1
}
finally {
    if ($downloadedInstaller -and (Test-Path -LiteralPath $downloadedInstaller -PathType Leaf)) {
        Remove-Item -LiteralPath $downloadedInstaller -Force
    }
}
