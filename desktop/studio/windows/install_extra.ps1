param([ValidateSet('rhythm','drumsep','creative')][string]$Component)
$ErrorActionPreference = 'Stop'
$StudioRoot = Split-Path $PSScriptRoot -Parent
if ($Component -eq 'creative') {
    $StudioUv = Join-Path $StudioRoot 'tools\uv.exe'
    $CreativeEnv = Join-Path $StudioRoot '.venv-creative'
    $CreativePython = Join-Path $CreativeEnv 'Scripts\python.exe'
    if (-not (Test-Path $CreativePython)) {
        & $StudioUv venv --python (Join-Path $StudioRoot 'python\python.exe') $CreativeEnv
        if ($LASTEXITCODE -ne 0) { throw 'Creation du moteur creatif impossible.' }
    }
    & $StudioUv pip install --python $CreativePython 'torch==2.2.2' 'torchaudio==2.2.2' 'numpy==1.26.4' 'soundfile==0.13.1' 'transformers==4.44.2' 'sentencepiece==0.2.0' 'safetensors==0.4.5' 'onnxruntime==1.19.2'
    if ($LASTEXITCODE -ne 0) { throw 'Installation des dependances creatives interrompue.' }
    & $CreativePython (Join-Path $StudioRoot 'tools\setup_studio_creative.py') $StudioRoot
    if ($LASTEXITCODE -ne 0) { throw 'Installation des modeles creatives interrompue.' }
    Write-Host 'Creation musicale et separation vocale pretes. MusicGen : usage non commercial.'
    exit 0
}
$StudioPython = Join-Path $StudioRoot '.venv-demucs\Scripts\python.exe'
if (-not (Test-Path $StudioPython)) { throw 'Installe d’abord le composant Séparer les stems, puis relance cette installation.' }
$StudioUv = Join-Path $StudioRoot 'tools\uv.exe'
if ($Component -eq 'rhythm') {
    # Explicit NumPy pin also repairs existing environments created with NumPy 2.
    & $StudioUv pip install --python $StudioPython 'numpy==1.26.4' 'beat-this==1.1.0' 'rotary-embedding-torch==0.6.5' 'soxr==0.3.7' 'torch<2.9' 'torchaudio<2.9'
} else {
    & $StudioUv pip install --python $StudioPython 'gdown==5.2.0'
}
if ($LASTEXITCODE -ne 0) { throw 'Installation des dependances interrompue.' }
if ($Component -eq 'rhythm') {
    & $StudioPython -c "import numpy,soxr; from beat_this.inference import Audio2Beats; print('NumPy',numpy.__version__,'Beat This pret')"
    if ($LASTEXITCODE -ne 0) { throw 'Le moteur rythmique ne se charge pas. Relance cette installation pour le reparer.' }
}
& $StudioPython (Join-Path $StudioRoot 'tools\setup_studio_models.py') $StudioRoot $Component
if ($LASTEXITCODE -ne 0) { throw 'Le modele ne peut pas etre installe. Consulte le message ci-dessus.' }
Write-Host 'Composant pret. Ferme cette fenetre et relance ton analyse dans BandStudio.'
