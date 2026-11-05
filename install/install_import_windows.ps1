$ErrorActionPreference = "Stop"
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$env:Path = "$env:USERPROFILE\.local\bin;$env:USERPROFILE\.deno\bin;" + $env:Path
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw "Installe d'abord ReaCue (uv manquant)." }
foreach ($tool in @('ffmpeg', 'ffprobe', 'deno')) {
  if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
    Write-Host "Import necessite ffmpeg, ffprobe et Deno >= 2.3."
    Write-Host "Installe-les puis relance ce fichier. Avec winget :"
    Write-Host "winget install --id Gyan.FFmpeg --exact"
    Write-Host "winget install --id DenoLand.Deno --exact"
    exit 1
  }
}
if (-not (Test-Path .venv-import\Scripts\python.exe)) {
  & uv venv .venv-import --python 3.12
  if ($LASTEXITCODE -ne 0) { exit 1 }
}
& uv pip install --python .venv-import\Scripts\python.exe --upgrade -r requirements-import.txt
if ($LASTEXITCODE -ne 0) { exit 1 }
& .venv-import\Scripts\python.exe -m yt_dlp --version
if ($LASTEXITCODE -ne 0) { exit 1 }
Write-Host "Import installe. Rouvre ReaCue : + Nouveau morceau > Depuis un lien YouTube."
