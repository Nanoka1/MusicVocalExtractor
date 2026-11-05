param([string]$FFmpegDir = '', [switch]$Cpu, [switch]$IncludeCachedModels)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if ($IncludeCachedModels) { throw 'Models are shared through runtime-config.json; embedding duplicate caches is no longer supported.' }
$flavor = if ($Cpu) { 'CPU' } else { 'GPU' }
$environment = if ($Cpu) { '.venv' } else { '.venv-gpu' }
$python = Join-Path $PSScriptRoot "$environment\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { throw "Missing isolated $environment. See GPU_ACCELERATION.md." }
$distRoot = Join-Path $PSScriptRoot "dist\candidate-$($flavor.ToLower())"
$package = Join-Path $distRoot 'MusicVocalExtractor'
if (Test-Path -LiteralPath $package) { throw "Existing candidate is preserved: $package. Verify/publish it or review it before building again." }
& $python -X utf8 -c 'import sys; assert sys.version_info[:2] == (3,12); import gradio, PyInstaller; from audio_separator.separator import Separator'
if ($LASTEXITCODE -ne 0) { throw 'Dependency check failed; nothing installed or repaired.' }
if (-not $Cpu) {
    & $python -X utf8 verify_gpu.py
    if ($LASTEXITCODE -ne 0) { throw 'Real CUDA preflight failed; GPU build stopped and all old packages preserved.' }
}
$tempFolder = Join-Path $PSScriptRoot '.tools\build-tmp'
New-Item -ItemType Directory -Force -Path $tempFolder | Out-Null
$oldTemp = $env:TEMP
$oldTmp = $env:TMP
$oldFFmpeg = $env:MVE_FFMPEG_DIR
$oldFlavor = $env:MVE_BUILD_FLAVOR
try {
    $env:TEMP = $tempFolder
    $env:TMP = $tempFolder
    $env:MVE_BUILD_FLAVOR = $flavor
    $env:MVE_FFMPEG_DIR = if ($FFmpegDir) { (Resolve-Path -LiteralPath $FFmpegDir).Path } else { $null }
    & $python -X utf8 -m PyInstaller --distpath $distRoot --workpath "build\$($flavor.ToLower())" MusicVocalExtractor.spec
    if ($LASTEXITCODE -ne 0) { throw 'Build failed; candidate kept for diagnosis. Old releases were not changed.' }
    foreach ($name in @('FFMPEG_NOTICE.md','THIRD_PARTY_NOTICES.md','LICENSE')) {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination $package
    }
    # Local deployment configuration only; model/data directories are never moved or copied.
    @{ data_dir=$PSScriptRoot; model_dir=(Join-Path $PSScriptRoot 'models') } |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $package 'runtime-config.json') -Encoding UTF8
    @{ flavor=$flavor; source_commit=(git rev-parse HEAD); built_at=(Get-Date -Format o) } |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $package 'build-info.json') -Encoding UTF8
    Write-Host "Candidate: $package"
    Write-Host 'Not a release until frozen GPU model proof and HTTP verification pass.'
    Write-Host "Next: $python verify_release.py --package `"$package`""
    Write-Host 'No old builds, weights, environments, outputs or user settings were removed.'
} finally {
    $env:TEMP=$oldTemp
    $env:TMP=$oldTmp
    $env:MVE_FFMPEG_DIR=$oldFFmpeg
    $env:MVE_BUILD_FLAVOR=$oldFlavor
}
