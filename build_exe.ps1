param([string]$FFmpegDir = '', [switch]$Cpu, [switch]$Gpu, [switch]$IncludeCachedModels,
      [string]$BuildId = "$(Get-Date -Format yyyyMMdd-HHmmss)-$([guid]::NewGuid().ToString('N').Substring(0,8))")
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if ($IncludeCachedModels) { throw 'Models are shared through runtime-config.json; embedding duplicate caches is no longer supported.' }
if ($Cpu -and $Gpu) { throw 'Choose only one of -Cpu and -Gpu.' }
$Cpu = -not $Gpu
$flavor = if ($Gpu) { 'GPU' } else { 'CPU' }
$environment = if ($Gpu) { '.venv-gpu' } else { '.venv' }
$python = Join-Path $PSScriptRoot "$environment\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { throw "Missing isolated $environment. See GPU_ACCELERATION.md." }
if ($BuildId -notmatch '^[A-Za-z0-9][A-Za-z0-9_-]{0,39}$') { throw 'Invalid build ID.' }
$distRoot = Join-Path $PSScriptRoot "build\packaging\staging\$($flavor.ToLower())"
$package = Join-Path $distRoot 'MusicVocalExtractor'
if (Test-Path -LiteralPath $package) { throw "Existing candidate is preserved: $package. Verify/publish it or review it before building again." }
$tempFolder = Join-Path $PSScriptRoot ".tools\build-tmp\$BuildId"
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
    & $python -X utf8 -c 'import sys; assert sys.version_info[:2] == (3,12); import gradio, PyInstaller; from audio_separator.separator import Separator'
    if ($LASTEXITCODE -ne 0) { throw 'Dependency check failed; nothing installed or repaired.' }
    if ($Gpu) {
        Push-Location -LiteralPath $tempFolder
        try {
            & $python -X utf8 (Join-Path $PSScriptRoot 'verify_gpu.py')
            if ($LASTEXITCODE -ne 0) { throw 'Real CUDA preflight failed.' }
        } finally { Pop-Location }
    }
    & $python -X utf8 -m PyInstaller --distpath $distRoot --workpath "build\packaging\work\$($flavor.ToLower())" MusicVocalExtractor.spec
    if ($LASTEXITCODE -ne 0) { throw 'Build failed; candidate kept for diagnosis. Old releases were not changed.' }
    foreach ($name in @('FFMPEG_NOTICE.md','THIRD_PARTY_NOTICES.md','LICENSE')) {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination $package
    }
    # Keep explicit overrides valid even though the candidate has a different depth.
    $settings = @{ application_id='MusicVocalExtractor'; schema_version=1; data_dir=$PSScriptRoot; model_dir=(Join-Path $PSScriptRoot 'models') }
    $formal = Join-Path $PSScriptRoot 'dist\MusicVocalExtractor'
    $formalConfig = Join-Path $formal 'runtime-config.json'
    if (Test-Path -LiteralPath $formalConfig) {
        $old = Get-Content -Raw -LiteralPath $formalConfig | ConvertFrom-Json
        foreach ($key in @('data_dir','model_dir')) {
            if ($old.PSObject.Properties[$key]) {
                $settings[$key] = [IO.Path]::GetFullPath([IO.Path]::Combine($formal, $old.$key))
            }
        }
    }
    $settings |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $package 'runtime-config.json') -Encoding UTF8
    $revision = & $python -X utf8 -c 'from runtime_paths import web_revision; import sys; assert web_revision()==web_revision(sys.argv[1]); print(web_revision())' (Join-Path $package '_internal')
    if ($LASTEXITCODE -ne 0 -or $revision -notmatch '^[0-9a-f]{16}$') { throw 'Bundled web assets failed version check.' }
    @{ flavor=$flavor; source_commit=(git rev-parse HEAD); source_dirty=[bool](git status --porcelain); built_at=(Get-Date -Format o); web_revision=$revision } |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $package 'build-info.json') -Encoding UTF8
    Write-Host "Candidate: $package"
    Write-Host 'Not a release until frozen device/model proof and HTTP verification pass.'
    $verifyDevice = if ($Cpu) { '--cpu' } else { '' }
    Write-Host "Next: $python verify_release.py $verifyDevice --package `"$package`""
    Write-Host "After verification: $python publish_release.py $verifyDevice --build-id $BuildId --publish"
    Write-Host 'No old builds, weights, environments, outputs or user settings were removed.'
} finally {
    $env:TEMP=$oldTemp
    $env:TMP=$oldTmp
    $env:MVE_FFMPEG_DIR=$oldFFmpeg
    $env:MVE_BUILD_FLAVOR=$oldFlavor
}
