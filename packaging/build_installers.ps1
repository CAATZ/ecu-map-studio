[CmdletBinding()]
param(
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$Version = '1.2.0',

    [string]$NuitkaPython,

    [string]$Iscc = 'C:\tmp\ECUEditor-InnoSetup6\ISCC.exe'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$ProjectPython = Join-Path $Root '.venv\Scripts\python.exe'
if (-not $NuitkaPython) {
    $NuitkaPython = $ProjectPython
}
$NuitkaPython = (Resolve-Path -LiteralPath $NuitkaPython).Path
$Iscc = (Resolve-Path -LiteralPath $Iscc).Path
$ReleaseDirectory = Join-Path $Root "release\v$Version"
$TemporaryRoot = Join-Path $Root "tmp\installer-$Version"
$NuitkaBuild = Join-Path $TemporaryRoot 'nuitka-build'
$NuitkaCache = Join-Path ([IO.Path]::GetTempPath()) 'ECUMapStudio-Nuitka'
$RegularStage = Join-Path $TemporaryRoot 'pyinstaller'
$NuitkaStage = Join-Path $TemporaryRoot 'nuitka'
$NumericVersion = "$Version.0"

function Reset-TemporaryDirectory {
    param([Parameter(Mandatory)][string]$Path)

    $ResolvedRoot = [IO.Path]::GetFullPath((Join-Path $Root 'tmp'))
    $ResolvedPath = [IO.Path]::GetFullPath($Path)
    if ($ResolvedPath -eq $ResolvedRoot -or -not $ResolvedPath.StartsWith(
        $ResolvedRoot + [IO.Path]::DirectorySeparatorChar,
        [StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Refusing to reset path outside $ResolvedRoot`: $ResolvedPath"
    }
    if (Test-Path -LiteralPath $ResolvedPath) {
        Remove-Item -Recurse -Force -LiteralPath $ResolvedPath
    }
    New-Item -ItemType Directory -Force -Path $ResolvedPath | Out-Null
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory)][scriptblock]$Command,
        [Parameter(Mandatory)][string]$Description
    )

    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE."
    }
}

function Copy-PackageFiles {
    param([Parameter(Mandatory)][string]$Destination)

    Copy-Item -Force -LiteralPath (Join-Path $Root 'output\pdf\ECU_Map_Studio_User_Manual.pdf') `
        -Destination (Join-Path $Destination 'ECU-Map-Studio-Manual.pdf')
    Copy-Item -Force -LiteralPath (Join-Path $Root 'LICENSE') `
        -Destination (Join-Path $Destination 'LICENSE.txt')
    Copy-Item -Force -LiteralPath (Join-Path $Root 'README.md') -Destination $Destination
    Copy-Item -Force -LiteralPath (Join-Path $Root 'CHANGELOG.md') -Destination $Destination
}

Push-Location $Root
try {
    Reset-TemporaryDirectory $TemporaryRoot
    & (Join-Path $Root 'packaging\prepare_release.ps1') -Version $Version

    New-Item -ItemType Directory -Force -Path $RegularStage, $NuitkaBuild | Out-Null
    Copy-Item -Force -LiteralPath (Join-Path $Root 'dist\ECUMapStudio.exe') `
        -Destination (Join-Path $RegularStage 'ECUMapStudio.exe')
    Copy-PackageFiles $RegularStage

    $NuitkaReport = Join-Path $NuitkaBuild 'nuitka-report.xml'
    $env:NUITKA_CACHE_DIR = $NuitkaCache
    $NuitkaArguments = @(
        '-m', 'nuitka',
        '--mode=standalone',
        '--msvc=latest',
        '--assume-yes-for-downloads',
        '--enable-plugin=pyqt5',
        '--include-package=ecu_map_tool',
        '--include-package=scipy._external.array_api_compat.numpy',
        '--windows-console-mode=disable',
        '--include-windows-runtime-dlls=yes',
        "--include-data-dir=$(Join-Path $Root 'assets')=assets",
        "--windows-icon-from-ico=$(Join-Path $Root 'assets\ECUMapStudio.ico')",
        '--output-filename=ECUMapStudio.exe',
        "--output-dir=$NuitkaBuild",
        "--report=$NuitkaReport",
        '--company-name=CAATZ',
        '--product-name=ECU Map Studio',
        '--file-description=ECU Map Studio',
        "--file-version=$NumericVersion",
        "--product-version=$NumericVersion",
        (Join-Path $Root 'app.py')
    )
    Invoke-Checked {
        & $NuitkaPython @NuitkaArguments
    } 'Nuitka standalone build'

    $BuiltNuitka = Join-Path $NuitkaBuild 'app.dist'
    $NuitkaExecutable = Join-Path $BuiltNuitka 'ECUMapStudio.exe'
    if (-not (Test-Path -LiteralPath $NuitkaExecutable -PathType Leaf)) {
        throw 'Nuitka did not produce ECUMapStudio.exe.'
    }
    $NuitkaSmoke = Start-Process -FilePath $NuitkaExecutable -ArgumentList '--smoke-test' `
        -Wait -PassThru -WindowStyle Hidden
    if ($NuitkaSmoke.ExitCode -ne 0) {
        throw "Nuitka packaged smoke test failed with exit code $($NuitkaSmoke.ExitCode)."
    }

    New-Item -ItemType Directory -Force -Path $NuitkaStage | Out-Null
    Copy-Item -Recurse -Force -Path (Join-Path $BuiltNuitka '*') -Destination $NuitkaStage
    Copy-PackageFiles $NuitkaStage

    $NuitkaZip = Join-Path $ReleaseDirectory "ECU-Map-Studio-$Version-Windows-x64-Nuitka.zip"
    Compress-Archive -Force -CompressionLevel Optimal -Path (Join-Path $NuitkaStage '*') `
        -DestinationPath $NuitkaZip

    foreach ($Package in @(
        @{ Source = $RegularStage; Suffix = '' },
        @{ Source = $NuitkaStage; Suffix = '-Nuitka' }
    )) {
        Invoke-Checked {
            & $Iscc `
                "/DAppVersion=$Version" `
                "/DAppNumericVersion=$NumericVersion" `
                "/DPackageSuffix=$($Package.Suffix)" `
                "/DSourceDir=$($Package.Source)" `
                "/DOutputDir=$ReleaseDirectory" `
                'packaging\ECUMapStudio.iss'
        } "Inno Setup $($Package.Suffix) installer"
    }

    $Checksums = Join-Path $ReleaseDirectory 'SHA256SUMS.txt'
    $ChecksumLines = Get-ChildItem -LiteralPath $ReleaseDirectory -File |
        Where-Object Name -ne 'SHA256SUMS.txt' |
        Sort-Object Name |
        ForEach-Object {
            $Hash = Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName
            '{0}  {1}' -f $Hash.Hash, $_.Name
        }
    Set-Content -Encoding ascii -LiteralPath $Checksums -Value $ChecksumLines

    Write-Host ''
    Write-Host "Dual-installer release v$Version is ready: $ReleaseDirectory"
    Get-ChildItem -LiteralPath $ReleaseDirectory -File |
        Select-Object Name, Length |
        Format-Table -AutoSize
}
finally {
    Pop-Location
}
