# Paroles calées mot par mot (alignement forcé wav2vec2) et paroles automatiques (Whisper) pour ReaCue, en local - Windows.
# Word-by-word lyrics timing (wav2vec2 forced alignment) and automatic lyrics (Whisper) for ReaCue, local - Windows.
# Lancé par « Install ReaCue Words.bat » ; ou :
#   powershell -ExecutionPolicy Bypass -File install\install_words_windows.ps1 [-Lang fr|en] [-ExtraIndexUrl <url>]
# Langues des modèles : français et anglais (≈ 1,3 Go chacun) ; une seule : $env:REACUE_WORDS_LANGS = "fr" (ou "en").
# Paroles automatiques : Whisper (lyrics_model / REACUE_LYRICS_MODEL) ; sans Whisper : $env:REACUE_WHISPER = "0".
# Environnement séparé .venv-words (n'abîme pas le .venv de ReaCue). Relançable sans risque : sur une installation
# existante, seul ce qui manque est ajouté (paquets et modèles déjà présents gardés).
# Fichier enregistré en UTF-8 avec BOM (sinon Windows PowerShell 5.1 lit les accents en ANSI).
param([string]$Lang = "", [string]$ExtraIndexUrl = "")
$ErrorActionPreference = "Stop"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$Here = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $Here

# Cache localisé : évite de remplir le disque système (C:)
if (-not $env:UV_CACHE_DIR) {
  $c = [System.Environment]::GetEnvironmentVariable("UV_CACHE_DIR", "User")
  if ($c) { $env:UV_CACHE_DIR = $c } else { $env:UV_CACHE_DIR = Join-Path $Here ".uv_cache" }
}
if (-not $env:TORCH_HOME) {
  $c = [System.Environment]::GetEnvironmentVariable("TORCH_HOME", "User")
  if ($c) { $env:TORCH_HOME = $c }
}
if (-not $env:HF_HOME) {
  $c = [System.Environment]::GetEnvironmentVariable("HF_HOME", "User")
  if ($c) { $env:HF_HOME = $c }
}
if (-not $Lang) { $Lang = Read-Host "Langue / Language [fr/en] (fr)" }
$L = if ($Lang -and $Lang.ToLower().StartsWith("en")) { "en" } else { "fr" }
function T([string]$fr, [string]$en) { if ($L -eq "en") { $en } else { $fr } }
function Fail([string]$fr, [string]$en) {
  Write-Host ""
  Write-Host (T "ÉCHEC : $fr" "FAILED: $en") -ForegroundColor Red
  exit 1
}
$Langs = if ($env:REACUE_WORDS_LANGS) { $env:REACUE_WORDS_LANGS } else { "fr,en" }
$Whisper = ($env:REACUE_WHISPER -ne "0")

$env:Path = (Join-Path $env:USERPROFILE ".local\bin") + ";" + (Join-Path $env:USERPROFILE ".cargo\bin") + ";" + $env:Path
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Fail "uv introuvable : installe d'abord ReaCue (Install ReaCue.bat)." "uv not found: install ReaCue first (Install ReaCue.bat)."
}
Write-Host (T "  Paroles mot par mot (wav2vec2) dans $Here\.venv-words" "  Word-by-word lyrics (wav2vec2) in $Here\.venv-words")
Write-Host (T "  Licence : modèles wav2vec2 XLSR-53 de J. Grosman (Apache-2.0), base Meta XLSR-53 (Apache-2.0) ; téléchargés depuis Hugging Face. Détails : THIRD_PARTY_NOTICES.md" "  Licence: J. Grosman's wav2vec2 XLSR-53 models (Apache-2.0), Meta XLSR-53 base (Apache-2.0); downloaded from Hugging Face. Details: THIRD_PARTY_NOTICES.md")
$Py = Join-Path $Here ".venv-words\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Py)) {
  & uv venv .venv-words --python 3.12
  if ($LASTEXITCODE -ne 0) { Fail "création de .venv-words impossible." "could not create .venv-words." }
}

Write-Host (T "  analyse du matériel et audit de l'environnement…" "  hardware analysis and environment audit…")
$audit = $null
try {
  $auditRaw = & $Py (Join-Path $Here "reacue_gpu.py") audit $Py 2>$null
  if ($LASTEXITCODE -eq 0 -and $auditRaw) {
    $audit = $auditRaw | ConvertFrom-Json
  }
} catch { }

if (-not $ExtraIndexUrl -and $audit -and $audit.target_index) {
  $ExtraIndexUrl = $audit.target_index
}

if ($audit -and $audit.action -eq "reinstall") {
  Write-Host (T "  configuration matérielle non optimale : $($audit.reason_fr)" `
                "  hardware configuration not optimal: $($audit.reason)") -ForegroundColor Yellow
  if ($audit.installed) {
    Write-Host (T "  désinstallation des paquets PyTorch non adaptés ($($audit.torch_version))…" `
                  "  uninstalling mismatched PyTorch packages ($($audit.torch_version))…")
    & uv pip uninstall --python $Py torch torchaudio
  }
  $torchVer = $audit.target_version
  Write-Host (T "  installation de PyTorch $torchVer avec accélération ($ExtraIndexUrl)…" `
                "  installing PyTorch $torchVer with acceleration ($ExtraIndexUrl)…")
  & uv pip install --python $Py "torch==$torchVer" "torchaudio==$torchVer" --index $ExtraIndexUrl --reinstall
} elseif ($audit -and $audit.action -eq "install") {
  $torchVer = $audit.target_version
  if ($ExtraIndexUrl) {
    & uv pip install --python $Py "torch==$torchVer" "torchaudio==$torchVer" --index $ExtraIndexUrl --reinstall
  }
} elseif ($audit -and $audit.status -eq "optimal") {
  Write-Host (T "  accélération matérielle déjà optimale ($($audit.torch_version)) : aucun téléchargement nécessaire." `
                "  hardware acceleration already optimal ($($audit.torch_version)): no download needed.") -ForegroundColor Green
}

$indexArgs = @()
if ($ExtraIndexUrl) {
  $indexArgs = @("--extra-index-url", $ExtraIndexUrl)
}
& uv pip install --python $Py @indexArgs --only-binary ":all:" -r requirements-words.txt
if ($LASTEXITCODE -ne 0) { Fail "installation des dépendances impossible (voir ci-dessus)." "could not install the dependencies (see above)." }
if ($Whisper) {
  & uv pip install --python $Py --no-deps -r requirements-whisper.txt
  if ($LASTEXITCODE -ne 0) { Fail "installation de Whisper impossible (voir ci-dessus)." "could not install Whisper (see above)." }
}
$WordsEngine = (& $Py -c "import os, reacue_performance as p; print(os.environ.get('REACUE_WORDS_ENGINE') or p.settings().get('words_engine', 'off'))").Trim()
if ($LASTEXITCODE -ne 0) { Fail "lecture des réglages impossible." "could not read settings." }
if ($WordsEngine -eq "auto") {
  Write-Host (T "  téléchargement des modèles de calage et test sur un audio synthétique…" "  downloading the timing models and testing on synthetic audio…")
  & $Py (Join-Path $Here "reacue_words.py") check --langs $Langs --lang $L
  if ($LASTEXITCODE -ne 0) { Fail "le calage de paroles ne fonctionne pas (voir ci-dessus)." "lyrics timing does not work (see above)." }
} else {
  Write-Host (T "  Calage mot par mot désactivé : modèles existants conservés, aucun téléchargement." "  Word alignment disabled: existing models kept, no download.")
}
if ($Whisper) {
  $WhisperModel = (& $Py -c 'import reacue_transcribe as r; print(r.selected_model())').Trim()
  if ($LASTEXITCODE -ne 0) { Fail "lecture du modele impossible." "could not read selected model." }
  Write-Host (T "  Licence : openai-whisper et modèle Whisper $WhisperModel d'OpenAI (MIT). Détails : THIRD_PARTY_NOTICES.md" `
                "  Licence: OpenAI's openai-whisper and Whisper $WhisperModel model (MIT). Details: THIRD_PARTY_NOTICES.md")
  Write-Host (T "  modèle Whisper sélectionné ($WhisperModel) et test…" `
                "  selected Whisper model ($WhisperModel) and test…")
  & $Py (Join-Path $Here "reacue_transcribe.py") check --download --lang $L --model $WhisperModel
  if ($LASTEXITCODE -ne 0) { Fail "les paroles automatiques (Whisper) ne fonctionnent pas (voir ci-dessus)." "automatic lyrics (Whisper) do not work (see above)." }
  Write-Host (T "  Paroles automatiques installées : sans paroles.txt, ReaCue écrit un brouillon 'paroles (auto).txt' à corriger (réglage 'lyrics_auto')." `
                "  Automatic lyrics installed: without lyrics.txt, ReaCue writes a draft 'paroles (auto).txt' to correct ('lyrics_auto' setting).")
}

Write-Host (T "  Installation paroles terminée : actions 'ReaCue - Caler les paroles' et 'ReaCue - Paroles automatiques (Whisper)' dans REAPER." `
              "  Lyrics installation complete: 'ReaCue - Time lyrics' and 'ReaCue - Automatic lyrics (Whisper)' actions in REAPER.")
exit 0
