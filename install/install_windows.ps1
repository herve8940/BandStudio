# Installation de ReaCue sous Windows / ReaCue installer for Windows.
# Lancé par « Install ReaCue.bat » (double-clic) ; ou :
#   powershell -ExecutionPolicy Bypass -File install\install_windows.ps1 [-Lang fr|en] [-Mcp yes|no|ask] [-Stems yes|no|ask] [-Structure yes|no|ask]
# Relançable sans risque (idempotent). Internet n'est nécessaire que pendant l'installation.
# Fichier enregistré en UTF-8 avec BOM (sinon Windows PowerShell 5.1 lit les accents en ANSI).
param(
  [string]$Lang = "",
  [ValidateSet("auto", "custom", "ask")][string]$Mode = "ask",
  [ValidateSet("yes", "no", "ask")][string]$Mcp = "ask",
  [ValidateSet("yes", "no", "ask")][string]$Stems = "ask",
  [ValidateSet("yes", "no", "ask")][string]$Structure = "ask",
  [ValidateSet("yes", "no", "ask")][string]$Chords = "ask",
  [ValidateSet("yes", "no", "ask")][string]$Drums = "ask",
  [ValidateSet("yes", "no", "ask")][string]$Words = "ask",
  [string]$ReaperDir = ""
)
if ($Mode -eq "ask" -and $env:REACUE_MODE) { $Mode = $env:REACUE_MODE.ToLower() }
if ($Chords -eq "ask" -and $env:REACUE_CHORDS) { $Chords = $env:REACUE_CHORDS.ToLower() }
if ($Drums -eq "ask" -and $env:REACUE_DRUMS) { $Drums = $env:REACUE_DRUMS.ToLower() }
if ($Words -eq "ask" -and $env:REACUE_WORDS) { $Words = $env:REACUE_WORDS.ToLower() }
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

if (-not $Lang) {
  Write-Host "ReaCue - installation"
  $Lang = Read-Host "Langue / Language [fr/en] (fr)"
}
$L = if ($Lang -and $Lang.ToLower().StartsWith("en")) { "en" } else { "fr" }
function T([string]$fr, [string]$en) { if ($L -eq "en") { $en } else { $fr } }
function Fail([string]$fr, [string]$en) {
  Write-Host ""
  Write-Host (T "ÉCHEC : $fr" "FAILED: $en") -ForegroundColor Red
  exit 1
}

if (-not $ReaperDir) {
  $ReaperDir = if ($env:REAPER_RESOURCE_PATH) { $env:REAPER_RESOURCE_PATH } else { Join-Path $env:APPDATA "REAPER" }
}

Write-Host ""
Write-Host (T "== 1/9 Vérifications et analyse du matériel" "== 1/9 Checks and hardware analysis")
if (-not (Test-Path -LiteralPath $ReaperDir -PathType Container)) {
  Fail "dossier REAPER introuvable ($ReaperDir). Lance REAPER une fois, ferme-le, puis relance l'installation (REAPER portable : -ReaperDir <dossier>)." `
       "REAPER folder not found ($ReaperDir). Start REAPER once, close it, then run the installer again (portable REAPER: -ReaperDir <folder>)."
}
Write-Host "  REAPER : $ReaperDir"
Write-Host "  ReaCue : $Here"

$GpuInfo = $null
$GpuExtraIndex = ""
if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
  try {
    $out = & nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits 2>$null
    if ($LASTEXITCODE -eq 0 -and $out) {
      $parts = $out.Split(",")
      $name = $parts[0].Trim()
      $vram = [int]$parts[1].Trim()
      $GpuInfo = @{ Vendor = "nvidia"; Name = $name; VramMB = $vram; Dedicated = $true; Backend = "cuda" }
    }
  } catch { }
}
if (-not $GpuInfo) {
  try {
    $adapters = Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}\0*" -ErrorAction SilentlyContinue | Where-Object { $_.DriverDesc }
    foreach ($a in $adapters) {
      $vram = if ($a.'HardwareInformation.qwMemorySize') { [int64]$a.'HardwareInformation.qwMemorySize' } elseif ($a.'HardwareInformation.MemorySize') { [int64]$a.'HardwareInformation.MemorySize' } else { 0 }
      $prov = [string]$a.ProviderName
      $desc = [string]$a.DriverDesc
      $vramMB = [math]::Round($vram / 1MB)
      if ($vram -ge 2147483648) {
        if ($prov -match "NVIDIA" -or $desc -match "GeForce|RTX|GTX|Quadro") {
          $GpuInfo = @{ Vendor = "nvidia"; Name = $desc; VramMB = $vramMB; Dedicated = $true; Backend = "cuda" }
          break
        } elseif ($prov -match "Advanced Micro Devices|AMD|ATI" -or $desc -match "Radeon") {
          $GpuInfo = @{ Vendor = "amd"; Name = $desc; VramMB = $vramMB; Dedicated = $true; Backend = "rocm" }
          break
        }
      }
    }
  } catch { }
}
if ($GpuInfo -and $GpuInfo.Vendor -eq "nvidia") {
  $vramGb = [math]::Round($GpuInfo.VramMB / 1024)
  $GpuExtraIndex = "https://download.pytorch.org/whl/cu124"
  if ($GpuInfo.Name -match "RTX 50|5070|5080|5090|Blackwell") {
    $GpuExtraIndex = "https://download.pytorch.org/whl/cu128"
  }
  Write-Host (T "  GPU dédié : $($GpuInfo.Name) ($vramGb Go VRAM) : Accélération NVIDIA CUDA activée" `
                "  Dedicated GPU: $($GpuInfo.Name) ($vramGb GB VRAM) : NVIDIA CUDA acceleration enabled") -ForegroundColor Green
} elseif ($GpuInfo -and $GpuInfo.Vendor -eq "amd") {
  $vramGb = [math]::Round($GpuInfo.VramMB / 1024)
  Write-Host (T "  GPU dédié : $($GpuInfo.Name) ($vramGb Go VRAM) : Accélération AMD détectée" `
                "  Dedicated GPU: $($GpuInfo.Name) ($vramGb GB VRAM) : AMD acceleration detected") -ForegroundColor Green
} else {
  Write-Host (T "  Accélération : Processeur standard (CPU)" `
                "  Acceleration: Standard processor (CPU)")
}

Write-Host ""
Write-Host (T "== 2/9 uv (gestionnaire Python d'Astral)" "== 2/9 uv (Astral's Python manager)")
$env:Path = (Join-Path $env:USERPROFILE ".local\bin") + ";" + (Join-Path $env:USERPROFILE ".cargo\bin") + ";" + $env:Path
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Write-Host (T "  installation de uv (https://astral.sh/uv)…" "  installing uv (https://astral.sh/uv)…")
  try {
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
  } catch { Fail "installation de uv impossible (internet ?)." "could not install uv (internet?)." }
  if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Fail "uv introuvable après installation." "uv not found after installation."
  }
}
Write-Host ("  " + (uv --version))

Write-Host ""
Write-Host (T "== 3/9 Environnement Python 3.12 (.venv) et dépendances" "== 3/9 Python 3.12 environment (.venv) and dependencies")
$Py = Join-Path $Here ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Py)) {
  & uv venv .venv --python 3.12
  if ($LASTEXITCODE -ne 0) { Fail "création du .venv impossible." "could not create .venv." }
}
# --no-build : paquets précompilés uniquement (pas de compilateur nécessaire)
& uv pip install --no-build --python $Py -r requirements.txt
if ($LASTEXITCODE -ne 0) { Fail "installation des dépendances impossible (voir ci-dessus)." "could not install dependencies (see above)." }
& $Py -c "import librosa, soundfile, mcp; print('  librosa', librosa.__version__, 'OK')"
if ($LASTEXITCODE -ne 0) { Fail "dépendances incomplètes." "incomplete dependencies." }

Write-Host ""
Write-Host (T "== 4/9 Configuration de REAPER" "== 4/9 REAPER configuration")
$env:REAPER_RESOURCE_PATH = $ReaperDir
& $Py (Join-Path $Here "install\reacue_setup.py") install --lang $L --install-dir $Here --reaper-dir $ReaperDir --mcp $Mcp
if ($LASTEXITCODE -ne 0) { Fail "configuration incomplète." "configuration incomplete." }

# Audit complet de la suite d'IA
$suite = $null
try {
  $suiteRaw = & $Py (Join-Path $Here "reacue_gpu.py") --suite-json 2>$null
  if ($LASTEXITCODE -eq 0 -and $suiteRaw) {
    $suite = $suiteRaw | ConvertFrom-Json
  }
} catch { }

if ($Mode -eq "ask") {
  Write-Host ""
  Write-Host "======================================================================" -ForegroundColor Cyan
  Write-Host (T "  Choix du mode d'installation et sélection des modèles d'IA :" `
                "  Installation mode and AI model selection:") -ForegroundColor Cyan
  Write-Host ""
  Write-Host (T "  1. Mode Automatique [Recommandé / Débutant]" `
                "  1. Automatic Mode [Recommended / Beginner]") -ForegroundColor Green
  Write-Host (T "     ReaCue choisit et configure automatiquement les meilleurs modèles" `
                "     ReaCue automatically selects and configures the best AI models")
  Write-Host (T "     adaptés à votre machine sans poser de questions techniques." `
                "     suited for your hardware without asking technical questions.")
  if ($suite) {
    $pTitle = if ($L -eq "en") { $suite.title_en } else { $suite.title_fr }
    $pDesc = if ($L -eq "en") { $suite.desc_en } else { $suite.desc_fr }
    Write-Host "     • $(T "Profil matériel :" "Hardware profile:") $pTitle" -ForegroundColor Yellow
    Write-Host "       $pDesc"
    Write-Host "     • $(T "Stems (Demucs) :" "Stems (Demucs):") $($suite.stems_model)"
    Write-Host "     • $(T "Structure :" "Structure:") SongFormer (MuQ + MusicFM)"
    Write-Host "     • $(T "Accords & Batterie :" "Chords & Drums:") ISMIR 2019 + ADTOF"
    if ($suite.install_words) {
      Write-Host "     • $(T "Paroles & Chant :" "Lyrics & Vocals:") Whisper small (Essentiel / Essential)"
    }
  }
  Write-Host ""
  Write-Host (T "  2. Mode Personnalisé [Avancé / Sélection détaillée]" `
                "  2. Custom Mode [Advanced / Detailed selection]")
  Write-Host (T "     Permet de choisir et configurer chaque modèle d'IA individuellement." `
                "     Choose and configure each AI model individually.")
  Write-Host "======================================================================" -ForegroundColor Cyan

  $choice = ""
  if (-not [Console]::IsInputRedirected) {
    $choice = Read-Host (T "  Votre choix [1] (Entrée = Mode Automatique) " "  Your choice [1] (Enter = Automatic Mode) ")
  }
  if (-not $choice -or $choice.Trim() -eq "1" -or $choice.ToLower().StartsWith("a") -or $choice.ToLower().StartsWith("o")) {
    $Mode = "auto"
  } else {
    $Mode = "custom"
  }
}

if ($Mode -eq "auto") {
  Write-Host ""
  Write-Host (T "  >> Mode Automatique sélectionné : configuration optimale en cours..." `
                "  >> Automatic Mode selected: applying optimal configuration...") -ForegroundColor Green
  if ($Stems -eq "ask") { $Stems = "yes" }
  if ($Structure -eq "ask") { $Structure = "yes" }
  if ($Chords -eq "ask") { $Chords = "yes" }
  if ($Drums -eq "ask") { $Drums = "yes" }
  if ($Words -eq "ask") {
    $Words = if ($suite -and $suite.install_words) { "yes" } else { "no" }
  }
  # Acceptation automatique des licences d'usage non commercial pour les novices
  $env:REACUE_STRUCTURE_ACCEPT = "yes"
  $env:REACUE_DRUMS_ACCEPT = "yes"
}

Write-Host ""
Write-Host (T "== 5/9 Séparation de stems (Demucs v4)" "== 5/9 Stem separation (Demucs v4)")
$demucsPy = Join-Path $Here ".venv-demucs\Scripts\python.exe"
if (Test-Path -LiteralPath $demucsPy) {
  $audit = $null
  try {
    $auditRaw = & $demucsPy (Join-Path $Here "reacue_gpu.py") audit $demucsPy 2>$null
    if ($LASTEXITCODE -eq 0 -and $auditRaw) {
      $audit = $auditRaw | ConvertFrom-Json
    }
  } catch { }

  if ($audit -and $audit.action -eq "reinstall") {
    Write-Host (T "  ! Réalignement matériel requis dans .venv-demucs : $($audit.reason_fr)" `
                  "  ! Hardware realignment needed in .venv-demucs: $($audit.reason)") -ForegroundColor Yellow
    $Stems = "yes"
  } elseif ($audit -and $audit.status -eq "optimal") {
    Write-Host (T "  Accélération matérielle déjà optimale ($($audit.torch_version)) dans .venv-demucs." `
                  "  Hardware acceleration already optimal ($($audit.torch_version)) in .venv-demucs.") -ForegroundColor Green
    if ($Stems -eq "ask") { $Stems = "no" }
  } else {
    if ($Stems -eq "ask") { $Stems = "yes" }
  }
}
if ($Stems -eq "ask") {
  Write-Host (T "  Modèles de séparation disponibles (Demucs v4, en local) :" `
                "  Available separation models (Demucs v4, local):")
  Write-Host (T "    • htdemucs_6s : 6 stems (voix, batterie, basse, guitare, piano, autres) [Optimal si GPU >= 8 Go]" `
                "    • htdemucs_6s: 6 stems (vocals, drums, bass, guitar, piano, other) [Optimal if GPU >= 8 GB]")
  Write-Host (T "    • htdemucs_ft : 4 stems haute fidélité fine-tuned (voix, batterie, basse, autres) [GPU 2 à 8 Go]" `
                "    • htdemucs_ft: 4 stems fine-tuned high fidelity (vocals, drums, bass, other) [GPU 2 to 8 GB]")
  Write-Host (T "    • htdemucs    : 4 stems standard plus léger et rapide [Recommandé sur processeur CPU]" `
                "    • htdemucs   : 4 stems standard faster and lightweight [Recommended on CPU]")
  $A = Read-Host (T "  Installer la séparation de stems Demucs (environ 1 Go, 5 à 15 min) ? [o/N]" `
                    "  Install Demucs stem separation (about 1 GB, 5 to 15 min)? [y/N]")
  $Stems = if ($A -and ($A.ToLower().StartsWith("o") -or $A.ToLower().StartsWith("y"))) { "yes" } else { "no" }
}
if ($Stems -eq "yes") {
  & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Here "install\install_stems_windows.ps1") -Lang $L -ExtraIndexUrl $GpuExtraIndex
  if ($LASTEXITCODE -ne 0) {
    Write-Host (T "  ! séparation de stems non installée (le reste de ReaCue fonctionne). Réessaie avec « Install ReaCue Stems.bat »." "  ! stem separation not installed (the rest of ReaCue works). Try again with 'Install ReaCue Stems.bat'.") -ForegroundColor Yellow
  }
} else {
  if (-not (Test-Path -LiteralPath $demucsPy)) {
    Write-Host (T "  Non installée. Plus tard : double-clic sur « Install ReaCue Stems.bat »." "  Not installed. Later: double-click 'Install ReaCue Stems.bat'.")
  }
}

Write-Host ""
Write-Host (T "== 6/9 Analyse de structure (SongFormer)" "== 6/9 Structure analysis (SongFormer)")
$structurePy = Join-Path $Here ".venv-structure\Scripts\python.exe"
if (Test-Path -LiteralPath $structurePy) {
  $structAudit = $null
  try {
    $structAuditJson = & $MainPy (Join-Path $Here "reacue_gpu.py") audit $structurePy 2>$null
    if ($LASTEXITCODE -eq 0 -and $structAuditJson) {
      $structAudit = $structAuditJson | ConvertFrom-Json
    }
  } catch { }

  if ($structAudit -and $structAudit.action -eq "reinstall") {
    Write-Host (T "  ! Réalignement matériel requis dans .venv-structure : $($structAudit.reason_fr)" `
                  "  ! Hardware realignment needed in .venv-structure: $($structAudit.reason)") -ForegroundColor Yellow
    $Structure = "yes"
  } elseif ($structAudit -and $structAudit.status -eq "optimal") {
    Write-Host (T "  Accélération matérielle déjà optimale ($($structAudit.torch_version)) dans .venv-structure." `
                  "  Hardware acceleration already optimal ($($structAudit.torch_version)) in .venv-structure.") -ForegroundColor Green
    if ($Structure -eq "ask") { $Structure = "no" }
  } else {
    if ($Structure -eq "ask") { $Structure = "yes" }
  }
}
if ($Structure -eq "ask") {
  Write-Host (T "  Détecte couplets, refrains, ponts… avec SongFormer (IA, en local) : c'est l'analyse par défaut de ReaCue." "  Detects verses, choruses, bridges… with SongFormer (AI, local): ReaCue's default analysis.")
  Write-Host (T "  Usage non commercial (licence des poids MuQ) : il faudra taper « J'accepte » à l'étape suivante." "  Non-commercial use (MuQ weights licence): you will have to type 'I accept' at the next step.")
  $A = Read-Host (T "  Installer l'analyse de structure (environ 3 Go à télécharger, 10 à 40 min, 8 Go de RAM conseillés) ? [O/n]" "  Install structure analysis (about 3 GB to download, 10 to 40 min, 8 GB RAM recommended)? [Y/n]")
  $Structure = if ($A -and $A.ToLower().StartsWith("n")) { "no" } else { "yes" }
}
if ($Structure -eq "yes") {
  & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Here "install\install_structure_windows.ps1") -Lang $L -ExtraIndexUrl $GpuExtraIndex
  if ($LASTEXITCODE -ne 0) {
    Write-Host (T "  ! analyse de structure non installée (ReaCue garde sa détection). Réessaie avec « Install ReaCue Structure.bat »." "  ! structure analysis not installed (ReaCue keeps its own detection). Try again with 'Install ReaCue Structure.bat'.") -ForegroundColor Yellow
  }
} else {
  if (-not (Test-Path -LiteralPath $structurePy)) {
    Write-Host (T "  Non installée. Plus tard : double-clic sur « Install ReaCue Structure.bat »." "  Not installed. Later: double-click 'Install ReaCue Structure.bat'.")
  }
}

Write-Host ""
Write-Host (T "== 7/9 Reconnaissance d'accords (Modèle ISMIR 2019)" "== 7/9 Chord recognition (ISMIR 2019 Model)")
$chordsPy = Join-Path $Here ".venv-chords\Scripts\python.exe"
if (Test-Path -LiteralPath $chordsPy) {
  Write-Host (T "  Modèle d'accords déjà installé dans .venv-chords." "  Chord model already installed in .venv-chords.") -ForegroundColor Green
  if ($Chords -eq "ask") { $Chords = "no" }
}
if ($Chords -eq "ask") {
  Write-Host (T "  Reconnaissance d'accords par IA (Large-Vocabulary CNN, en local, licence MIT) :" `
                "  AI chord recognition (Large-Vocabulary CNN, local, MIT license):")
  Write-Host (T "  Détecte avec précision accords majeurs/mineurs, 7e, m7, maj7, dim, aug, sus et renversements (D/F#)." `
                "  Accurately detects major/minor, 7th, m7, maj7, dim, aug, sus, and inversions (D/F#).")
  $A = Read-Host (T "  Installer la reconnaissance d'accords (environ 60 Mo, rapide) ? [O/n]" `
                    "  Install chord recognition (about 60 MB, fast)? [Y/n]")
  $Chords = if ($A -and $A.ToLower().StartsWith("n")) { "no" } else { "yes" }
}
if ($Chords -eq "yes") {
  & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Here "install\install_chords_windows.ps1") -Lang $L -ExtraIndexUrl $GpuExtraIndex
  if ($LASTEXITCODE -ne 0) {
    Write-Host (T "  ! reconnaissance d'accords non installée (ReaCue garde sa détection standard)." `
                  "  ! chord recognition not installed (ReaCue keeps standard detection).") -ForegroundColor Yellow
  }
} else {
  if (-not (Test-Path -LiteralPath $chordsPy)) {
    Write-Host (T "  Non installée. Plus tard : double-clic sur « Install ReaCue Chords.bat »." `
                  "  Not installed. Later: double-click 'Install ReaCue Chords.bat'.")
  }
}

Write-Host ""
Write-Host (T "== 8/9 Transcription de batterie (ADTOF)" "== 8/9 Drum transcription (ADTOF)")
$drumsPy = Join-Path $Here ".venv-drums\Scripts\python.exe"
if (Test-Path -LiteralPath $drumsPy) {
  Write-Host (T "  Modèle de batterie ADTOF déjà installé dans .venv-drums." "  ADTOF drum model already installed in .venv-drums.") -ForegroundColor Green
  if ($Drums -eq "ask") { $Drums = "no" }
}
if ($Drums -eq "ask") {
  Write-Host (T "  Transcription de batterie ADTOF (entraîné sur 359h de musique, en local) :" `
                "  ADTOF drum transcription (trained on 359h real music, local):")
  Write-Host (T "  Alimente le prompteur batterie : kick, snare, toms, charley ouvert/fermé, crashs, fills et breaks." `
                "  Feeds drummer prompter: kick, snare, toms, open/closed hi-hat, crashes, fills and breaks.")
  $A = Read-Host (T "  Installer la transcription de batterie ADTOF (environ 16 Mo) ? [O/n]" `
                    "  Install ADTOF drum transcription (about 16 MB)? [Y/n]")
  $Drums = if ($A -and $A.ToLower().StartsWith("n")) { "no" } else { "yes" }
}
if ($Drums -eq "yes") {
  & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Here "install\install_drums_windows.ps1") -Lang $L -ExtraIndexUrl $GpuExtraIndex
  if ($LASTEXITCODE -ne 0) {
    Write-Host (T "  ! transcription de batterie non installée (ReaCue garde sa détection standard)." `
                  "  ! drum transcription not installed (ReaCue keeps standard detection).") -ForegroundColor Yellow
  }
} else {
  if (-not (Test-Path -LiteralPath $drumsPy)) {
    Write-Host (T "  Non installée. Plus tard : double-clic sur « Install ReaCue Drums.bat »." `
                  "  Not installed. Later: double-click 'Install ReaCue Drums.bat'.")
  }
}

Write-Host ""
Write-Host (T "== 9/9 Paroles et chant (Whisper)" "== 9/9 Lyrics and vocals (Whisper)")
$wordsPy = Join-Path $Here ".venv-words\Scripts\python.exe"
if (Test-Path -LiteralPath $wordsPy) {
  Write-Host (T "  Modèles de paroles déjà installés dans .venv-words." "  Lyrics models already installed in .venv-words.") -ForegroundColor Green
  if ($Words -eq "ask") { $Words = "no" }
}
if ($Words -eq "ask") {
  Write-Host (T "  Paroles Essentiel : Whisper small en local, calage par ligne." `
                "  Essential lyrics: local Whisper small, line timing.")
  Write-Host (T "  Profil Avancé facultatif : large-v3-turbo et calage mot-à-mot wav2vec2." `
                "  Optional Advanced profile: large-v3-turbo and wav2vec2 word alignment.")
  $A = Read-Host (T "  Installer les paroles Essentiel ? [o/N]" `
                    "  Install Essential lyrics? [y/N]")
  $Words = if ($A -and ($A.ToLower().StartsWith("o") -or $A.ToLower().StartsWith("y"))) { "yes" } else { "no" }
}
if ($Words -eq "yes") {
  & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Here "install\install_words_windows.ps1") -Lang $L -ExtraIndexUrl $GpuExtraIndex
  if ($LASTEXITCODE -ne 0) {
    Write-Host (T "  ! modèles de paroles non installés (ReaCue garde le calage par ligne)." `
                  "  ! lyrics models not installed (ReaCue keeps line-by-line alignment).") -ForegroundColor Yellow
  }
} else {
  if (-not (Test-Path -LiteralPath $wordsPy)) {
    Write-Host (T "  Non installés. Plus tard : double-clic sur « Install ReaCue Words.bat »." `
                  "  Not installed. Later: double-click 'Install ReaCue Words.bat'.")
  }
}

# Synchronisation finale des réglages REAPER (modèle de stems adapté au matériel)
try {
  $settingsFile = Join-Path (Join-Path $ReaperDir "ReaCueMCP") "reacue_settings.json"
  & $Py (Join-Path $Here "reacue_gpu.py") sync-settings $settingsFile | Out-Null
} catch { }

Write-Host ""
Write-Host "======================================================================" -ForegroundColor Green
Write-Host (T "  Installation de ReaCue terminée avec succès !" `
              "  ReaCue installation completed successfully!") -ForegroundColor Green
Write-Host (T "  Lancez REAPER et ouvrez l'action « ReaCue » depuis la barre d'outils." `
              "  Launch REAPER and open the 'ReaCue' action from the toolbar.")
Write-Host "======================================================================" -ForegroundColor Green
exit 0
