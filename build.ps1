# Ndërton dist\ShkarkuesMP3.exe (një skedar i vetëm, me ffmpeg brenda).
#
# Përdorim:   .\build.ps1
#             .\build.ps1 -FfmpegDir "C:\ffmpeg\bin"
#
# Kërkon: .venv me requirements-dev.txt të instaluar, dhe ffmpeg.exe + ffprobe.exe.

param(
    [string]$FfmpegDir = "C:\ProgramData\chocolatey\lib\ffmpeg\tools\ffmpeg\bin"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$py = ".\.venv\Scripts\python.exe"

if (-not (Test-Path $py)) {
    throw "Nuk u gjet .venv. Krijoje me:  uv venv; uv pip install -r requirements-dev.txt"
}
foreach ($exe in "ffmpeg.exe", "ffprobe.exe") {
    if (-not (Test-Path (Join-Path $FfmpegDir $exe))) {
        throw "Nuk u gjet $exe në '$FfmpegDir'. Jepe rrugën me -FfmpegDir."
    }
}

Write-Host "1/3  Përditësoj yt-dlp (YouTube ndryshon shpesh)..." -ForegroundColor Cyan
uv pip install --python $py -U yt-dlp | Out-Host

Write-Host "2/3  Krijoj logon..." -ForegroundColor Cyan
& $py tools\make_logo.py

Write-Host "3/3  Ndërtoj .exe..." -ForegroundColor Cyan
$ff = $FfmpegDir.Replace('\', '/')
& $py -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name ShkarkuesMP3 `
    --icon assets\logo.ico `
    --add-data "assets;assets" `
    --add-binary "$ff/ffmpeg.exe;ffmpeg" `
    --add-binary "$ff/ffprobe.exe;ffmpeg" `
    --collect-submodules yt_dlp `
    main.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller dështoi" }

$exe = Get-Item dist\ShkarkuesMP3.exe
Write-Host ("Exe: {0}  ({1:N0} MB)" -f $exe.FullName, ($exe.Length / 1MB)) -ForegroundColor Green

# --- Paketimi: exe + udhëzuesi PDF në një zip, gati për t'u dërguar
Write-Host "Paketoj zip-in me udhëzuesin..." -ForegroundColor Cyan
$version = (& $py -c "import shkarkues; print(shkarkues.__version__)").Trim()
$pkg = "dist\ShkarkuesMP3"
if (Test-Path $pkg) { Remove-Item $pkg -Recurse -Force }
New-Item -ItemType Directory $pkg | Out-Null
Copy-Item $exe.FullName $pkg

$edge = @("${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
          "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
$pdf = Join-Path (Resolve-Path $pkg) "UDHEZUESI.pdf"
if ($edge) {
    $html = "file:///" + (Resolve-Path docs\udhezuesi.html).Path.Replace('\', '/')
    $profileDir = Join-Path $env:TEMP "shkarkues-edge-pdf"
    & $edge --headless --disable-gpu --no-pdf-header-footer "--user-data-dir=$profileDir" "--print-to-pdf=$pdf" $html | Out-Null
    Start-Sleep -Seconds 2
}
if (-not (Test-Path $pdf)) {
    Write-Warning "PDF nuk u krijua (s'u gjet Edge). Po vendos udhëzuesin si HTML."
    Copy-Item docs\udhezuesi.html "$pkg\UDHEZUESI.html"
}

$zip = "dist\ShkarkuesMP3-v$version.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path "$pkg\*" -DestinationPath $zip
$z = Get-Item $zip
Write-Host ("Gati për t'u dërguar: {0}  ({1:N0} MB)" -f $z.FullName, ($z.Length / 1MB)) -ForegroundColor Green
