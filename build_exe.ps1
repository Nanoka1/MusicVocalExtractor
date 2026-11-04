param([string]$FFmpegDir = "")
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Project .venv with Python 3.12 is required.' }
& $python -c 'import sys; assert sys.version_info[:2] == (3, 12); import torch, onnxruntime, gradio; from audio_separator.separator import Separator; import PyInstaller'
if ($LASTEXITCODE -ne 0) { throw 'Dependency check failed. Build does not install or upgrade packages.' }
$tempFolder = Join-Path $PSScriptRoot '.tools\build-tmp'
New-Item -ItemType Directory -Force -Path $tempFolder | Out-Null
$oldTemp = $env:TEMP
$oldTmp = $env:TMP
$oldFFmpeg = $env:MVE_FFMPEG_DIR
try {
    $env:TEMP = $tempFolder
    $env:TMP = $tempFolder
    if ($FFmpegDir) { $env:MVE_FFMPEG_DIR = (Resolve-Path -LiteralPath $FFmpegDir).Path }
    else { $env:MVE_FFMPEG_DIR = $null }
    # A timestamped build avoids deleting/overwriting any previous executable or its user data.
    $buildId = Get-Date -Format 'yyyyMMdd-HHmmss'
    $distRoot = Join-Path $PSScriptRoot 'dist'
    if (Test-Path -LiteralPath (Join-Path $distRoot 'MusicVocalExtractor')) {
        $distRoot = Join-Path $distRoot "build-$buildId"
    }
    & $python -X utf8 -m PyInstaller --distpath $distRoot --workpath "build\$buildId" MusicVocalExtractor.spec
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed; Python startup remains available.' }
    $package = Join-Path $distRoot 'MusicVocalExtractor'
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'FFMPEG_NOTICE.md') -Destination $package
    # Copy only known cache files, into a new package; leave source/old caches intact.
    $cacheNames = @('UVR_MDXNET_KARA_2.onnx', 'UVR-MDX-NET-Voc_FT.onnx',
                    'UVR-MDX-NET-Inst_HQ_3.onnx', 'htdemucs.yaml', '955717e8-8726e21a.th',
                    'download_checks.json', 'mdx_model_data.json', 'vr_model_data.json')
    $modelTarget = Join-Path $package 'models'
    New-Item -ItemType Directory -Force -Path $modelTarget | Out-Null
    foreach ($cacheName in $cacheNames) {
        $source = Join-Path (Join-Path $PSScriptRoot 'models') $cacheName
        $target = Join-Path $modelTarget $cacheName
        if ((Test-Path -LiteralPath $source) -and -not (Test-Path -LiteralPath $target)) {
            Copy-Item -LiteralPath $source -Destination $target
        }
    }
    Write-Host "Build files created: $package"
    Write-Host 'This is not a verified release until EXE startup and real audio separation pass.'
    Write-Host 'Keep the entire directory, including _internal. Existing known model caches are copied; no old caches are removed.'
} finally {
    $env:TEMP = $oldTemp
    $env:TMP = $oldTmp
    $env:MVE_FFMPEG_DIR = $oldFFmpeg
}
