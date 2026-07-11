[CmdletBinding()]
param(
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$Version = '1.1.0',

    [switch]$SkipBuild
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Python = Join-Path $Root '.venv\Scripts\python.exe'
$Executable = Join-Path $Root 'dist\ECUMapStudio.exe'
$Manual = Join-Path $Root 'output\pdf\ECU_Map_Studio_User_Manual.pdf'
$ReleaseDirectory = Join-Path $Root "release\v$Version"

function Invoke-Checked {
    param(
        [Parameter(Mandatory)]
        [scriptblock]$Command,

        [Parameter(Mandatory)]
        [string]$Description
    )

    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE."
    }
}

if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw 'Project virtual environment not found. Install requirements-dev.txt first.'
}

if (-not [Environment]::Is64BitProcess) {
    throw 'Release builds must run from a 64-bit Python environment.'
}

Push-Location $Root
try {
    $PyProject = Get-Content -Raw -LiteralPath 'pyproject.toml'
    if ($PyProject -notmatch "(?m)^version\s*=\s*`"$([regex]::Escape($Version))`"$") {
        throw "pyproject.toml does not declare version $Version."
    }

    $PackageVersion = (& $Python -c 'import ecu_map_tool; print(ecu_map_tool.__version__)').Trim()
    if ($LASTEXITCODE -ne 0 -or $PackageVersion -ne $Version) {
        throw "ecu_map_tool.__version__ is $PackageVersion; expected $Version."
    }

    $VersionInfo = Get-Content -Raw -LiteralPath 'packaging\version_info.txt'
    if ($VersionInfo -notmatch [regex]::Escape("FileVersion', u'$Version'")) {
        throw "packaging/version_info.txt does not declare version $Version."
    }

    $Changelog = Get-Content -Raw -LiteralPath 'CHANGELOG.md'
    if ($Changelog -notmatch "(?m)^## \[$([regex]::Escape($Version))\]") {
        throw "CHANGELOG.md does not contain a $Version release entry."
    }

    if (-not $SkipBuild) {
        Invoke-Checked {
            & $Python -m ruff check app.py ecu_map_tool packaging tests
        } 'Lint check'
        Invoke-Checked {
            & $Python -m ruff format --check app.py ecu_map_tool packaging tests
        } 'Format check'
        Invoke-Checked {
            & $Python -m unittest discover -s tests -v
        } 'Test suite'
        Invoke-Checked {
            & $Python app.py --smoke-test
        } 'Source smoke test'
        Invoke-Checked {
            & (Join-Path $Root 'build_exe.bat')
        } 'Executable build'

        $SmokeProcess = Start-Process `
            -FilePath $Executable `
            -ArgumentList '--smoke-test' `
            -Wait `
            -PassThru `
            -WindowStyle Hidden
        if ($SmokeProcess.ExitCode -ne 0) {
            throw "Packaged smoke test failed with exit code $($SmokeProcess.ExitCode)."
        }
    }

    if (-not (Test-Path -LiteralPath $Executable -PathType Leaf)) {
        throw 'Packaged executable was not found.'
    }
    if (-not (Test-Path -LiteralPath $Manual -PathType Leaf)) {
        throw 'Published PDF manual was not found.'
    }

    New-Item -ItemType Directory -Force -Path $ReleaseDirectory | Out-Null

    $ReleaseExecutable = Join-Path $ReleaseDirectory "ECU-Map-Studio-$Version-Windows-x64.exe"
    $ReleaseManual = Join-Path $ReleaseDirectory "ECU-Map-Studio-$Version-Manual.pdf"
    $ReleaseZip = Join-Path $ReleaseDirectory "ECU-Map-Studio-$Version-Windows-x64.zip"
    $Checksums = Join-Path $ReleaseDirectory 'SHA256SUMS.txt'

    Copy-Item -Force -LiteralPath $Executable -Destination $ReleaseExecutable
    Copy-Item -Force -LiteralPath $Manual -Destination $ReleaseManual

    Compress-Archive -Force -CompressionLevel Optimal -LiteralPath @(
        $ReleaseExecutable,
        $ReleaseManual,
        (Join-Path $Root 'README.md'),
        (Join-Path $Root 'CHANGELOG.md')
    ) -DestinationPath $ReleaseZip

    $ChecksumLines = foreach ($Artifact in @($ReleaseExecutable, $ReleaseManual, $ReleaseZip)) {
        $Hash = Get-FileHash -Algorithm SHA256 -LiteralPath $Artifact
        '{0}  {1}' -f $Hash.Hash, (Split-Path -Leaf $Artifact)
    }
    Set-Content -Encoding ascii -LiteralPath $Checksums -Value $ChecksumLines

    $Signature = Get-AuthenticodeSignature -LiteralPath $ReleaseExecutable
    Write-Host ''
    Write-Host "Release v$Version is ready: $ReleaseDirectory"
    Get-ChildItem -LiteralPath $ReleaseDirectory -File |
        Select-Object Name, Length |
        Format-Table -AutoSize
    Write-Host "Executable signature: $($Signature.Status)"
    Write-Host 'GitHub will add source code ZIP and TAR archives when the release is created.'
}
finally {
    Pop-Location
}
