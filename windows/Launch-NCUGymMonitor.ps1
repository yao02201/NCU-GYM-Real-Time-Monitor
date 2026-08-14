[CmdletBinding()]
param(
    [Parameter()]
    [string]$ProjectRoot,

    [Parameter()]
    [switch]$NoDialog,

    [Parameter()]
    [switch]$Wait
)

$ErrorActionPreference = 'Stop'

if (-not $ProjectRoot) {
    $ProjectRoot = Split-Path -Parent $PSScriptRoot
}

function Stop-Launcher {
    param(
        [Parameter(Mandatory)]
        [string]$Message,

        [Parameter(Mandatory)]
        [int]$ExitCode
    )

    if ($NoDialog) {
        [Console]::Error.WriteLine($Message)
    }
    else {
        Add-Type -AssemblyName PresentationFramework
        [System.Windows.MessageBox]::Show(
            $Message,
            'NCU Gym Monitor',
            [System.Windows.MessageBoxButton]::OK,
            [System.Windows.MessageBoxImage]::Error
        ) | Out-Null
    }

    exit $ExitCode
}

if (-not (Test-Path -LiteralPath $ProjectRoot -PathType Container)) {
    Stop-Launcher -ExitCode 10 -Message 'The NCU Gym Monitor checkout is missing. Restore it, then rerun Setup.'
}

$projectEnvironment = Join-Path $ProjectRoot '.venv'
if (-not (Test-Path -LiteralPath $projectEnvironment -PathType Container)) {
    Stop-Launcher -ExitCode 11 -Message 'The Project environment is missing. Rerun Setup to repair it.'
}

$windowedPython = Join-Path $projectEnvironment 'Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $windowedPython -PathType Leaf)) {
    Stop-Launcher -ExitCode 12 -Message 'The Project environment windowed Python is missing. Rerun Setup to repair it.'
}

$monitorEntryPoint = Join-Path $ProjectRoot 'monitor_entry.pyw'
if (-not (Test-Path -LiteralPath $monitorEntryPoint -PathType Leaf)) {
    Stop-Launcher -ExitCode 12 -Message 'The Monitor entry point is missing from the checkout. Restore the checkout, then rerun Setup.'
}

$instanceModule = Join-Path $ProjectRoot 'monitor_instance.py'
if (-not (Test-Path -LiteralPath $instanceModule -PathType Leaf)) {
    Stop-Launcher -ExitCode 12 -Message 'The Monitor instance module is missing from the checkout. Restore the checkout, then rerun Setup.'
}

$widgetEntryPoint = Join-Path $ProjectRoot 'gym.pyw'
if (-not (Test-Path -LiteralPath $widgetEntryPoint -PathType Leaf)) {
    Stop-Launcher -ExitCode 12 -Message 'The Widget entry point is missing from the checkout. Restore the checkout, then rerun Setup.'
}

$requirementsPath = Join-Path $ProjectRoot 'requirements-runtime.txt'
if (-not (Test-Path -LiteralPath $requirementsPath -PathType Leaf)) {
    Stop-Launcher -ExitCode 13 -Message 'The Widget runtime dependency contract is missing. Restore the checkout, then rerun Setup.'
}

$runtimeImports = Get-Content -LiteralPath $requirementsPath | ForEach-Object {
    if ($_ -match '#\s*import=([A-Za-z_][A-Za-z0-9_.]*)') {
        $Matches[1]
    }
}
if (-not $runtimeImports) {
    Stop-Launcher -ExitCode 13 -Message 'The Widget runtime dependency contract has no import mappings. Restore the checkout, then rerun Setup.'
}
$importCode = ($runtimeImports | ForEach-Object { "import $_" }) -join '; '
try {
    $dependencyCheck = Start-Process `
        -FilePath $windowedPython `
        -ArgumentList @('-c', "`"$importCode`"") `
        -WorkingDirectory $ProjectRoot `
        -WindowStyle Hidden `
        -Wait `
        -PassThru
}
catch {
    Stop-Launcher -ExitCode 12 -Message 'The Project environment windowed Python could not start. Rerun Setup to repair it.'
}

if ($dependencyCheck.ExitCode -ne 0) {
    Stop-Launcher -ExitCode 13 -Message 'The Widget runtime dependencies are missing. Rerun Setup to repair the Project environment.'
}

$launchArguments = @('"' + $monitorEntryPoint + '"')
if ($NoDialog) {
    $launchArguments += '--no-dialog'
}
if ($Wait) {
    try {
        $monitorProcess = Start-Process `
            -FilePath $windowedPython `
            -ArgumentList $launchArguments `
            -WorkingDirectory $ProjectRoot `
            -WindowStyle Hidden `
            -Wait `
            -PassThru
    }
    catch {
        Stop-Launcher -ExitCode 14 -Message 'The Widget process could not start. Rerun Setup; if the problem continues, restore the checkout.'
    }

    if ($monitorProcess.ExitCode -ne 0) {
        Stop-Launcher -ExitCode 14 -Message 'The Widget failed during startup. Rerun Setup; if the problem continues, restore the checkout.'
    }
}
else {
    try {
        Start-Process `
            -FilePath $windowedPython `
            -ArgumentList $launchArguments `
            -WorkingDirectory $ProjectRoot `
            -WindowStyle Hidden | Out-Null
    }
    catch {
        Stop-Launcher -ExitCode 14 -Message 'The Widget process could not start. Rerun Setup; if the problem continues, restore the checkout.'
    }
}
