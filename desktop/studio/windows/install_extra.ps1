param([ValidateSet('rhythm','drumsep')][string]$Component)
$ErrorActionPreference = 'Stop'
$StudioRoot = Split-Path $PSScriptRoot -Parent
$StudioPython = Join-Path $StudioRoot '.venv-demucs\Scripts\python.exe'
if (-not (Test-Path $StudioPython)) { throw 'Installe d’abord le composant Séparer les stems, puis relance cette installation.' }
$StudioUv = Join-Path $StudioRoot 'tools\uv.exe'
if ($Component -eq 'rhythm') {
    & $StudioUv pip install --python $StudioPython 'beat-this==1.1.0' 'rotary-embedding-torch==0.6.5' 'soxr==0.3.7'
} else {
    & $StudioUv pip install --python $StudioPython 'gdown==5.2.0'
}
if ($LASTEXITCODE -ne 0) { throw 'Installation des dependances interrompue.' }
& $StudioPython (Join-Path $StudioRoot 'tools\setup_studio_models.py') $StudioRoot $Component
if ($LASTEXITCODE -ne 0) { throw 'Le modele ne peut pas etre installe. Consulte le message ci-dessus.' }
Write-Host 'Composant pret. Ferme cette fenetre et relance ton analyse dans BandStudio.'
