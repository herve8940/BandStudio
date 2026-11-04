#!/bin/bash
# Installation de ReaCue sur macOS / ReaCue installer for macOS.
# Lancé par « Install ReaCue.command » (double-clic) ; ou : bash install/install_mac.sh [fr|en]
# Relançable sans risque (idempotent). Internet n'est nécessaire que pendant l'installation.
# REACUE_STEMS=yes|no : installer ou non la séparation de stems sans poser la question.
# REACUE_STRUCTURE=yes|no : idem pour l'analyse de structure (SongFormer).
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$HERE"

# ---------------------------------------------------------------- langue
LANG_CHOICE="${1:-}"
if [ -z "$LANG_CHOICE" ]; then
  echo "ReaCue — installation"
  read -r -p "Langue / Language [fr/en] (fr) : " LANG_CHOICE || true
fi
case "$(echo "${LANG_CHOICE:-fr}" | tr '[:upper:]' '[:lower:]')" in
  en*) L=en ;;
  *) L=fr ;;
esac

t() {  # t "texte français" "English text"
  if [ "$L" = en ]; then echo "$2"; else echo "$1"; fi
}
fail() {
  echo
  t "ÉCHEC : $1" "FAILED: $2"
  exit 1
}

REAPER_DIR="${REAPER_RESOURCE_PATH:-$HOME/Library/Application Support/REAPER}"

echo
t "== 1/9 Vérifications et analyse du matériel" "== 1/9 Checks and hardware analysis"
[ "$(uname -s)" = "Darwin" ] || fail "ce script est pour macOS." "this script is for macOS."
if [ ! -d "$REAPER_DIR" ]; then
  fail "dossier REAPER introuvable ($REAPER_DIR). Lance REAPER une fois, ferme-le, puis relance l'installation." \
       "REAPER folder not found ($REAPER_DIR). Start REAPER once, close it, then run the installer again."
fi
echo "  REAPER : $REAPER_DIR"
echo "  ReaCue : $HERE"
if [ "$(uname -m)" = "arm64" ]; then
  t "  Puce Apple Silicon détectée (Metal / MPS) — Accélération matérielle activée" \
    "  Apple Silicon detected (Metal / MPS) — Hardware acceleration enabled"
fi

echo
t "== 2/9 uv (gestionnaire Python d'Astral)" "== 2/9 uv (Astral's Python manager)"
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then
  t "  installation de uv (https://astral.sh/uv)…" "  installing uv (https://astral.sh/uv)…"
  curl -LsSf https://astral.sh/uv/install.sh | sh || fail "installation de uv impossible (internet ?)." "could not install uv (internet?)."
  command -v uv >/dev/null 2>&1 || fail "uv introuvable après installation." "uv not found after installation."
fi
echo "  $(uv --version)"

echo
t "== 3/9 Environnement Python 3.12 (.venv) et dépendances" "== 3/9 Python 3.12 environment (.venv) and dependencies"
rm -rf .venv
uv venv .venv --python 3.12 || fail "création du .venv impossible." "could not create .venv."
# --no-build : paquets précompilés uniquement (pas de compilateur nécessaire)
uv pip install --no-build --python .venv/bin/python -r requirements.txt \
  || fail "installation des dépendances impossible (voir ci-dessus)." "could not install dependencies (see above)."
.venv/bin/python -c "import librosa, soundfile, mcp; print('  librosa', librosa.__version__, 'OK')" \
  || fail "dépendances incomplètes." "incomplete dependencies."
command -v say >/dev/null 2>&1 || t "  ! commande say absente : pas d'annonces vocales." "  ! say command missing: no spoken cues."

echo
t "== 4/9 Configuration de REAPER" "== 4/9 REAPER configuration"
REAPER_RESOURCE_PATH="$REAPER_DIR" .venv/bin/python install/reacue_setup.py install --lang "$L" --install-dir "$HERE" \
  --reaper-dir "$REAPER_DIR" ${REACUE_MCP:+--mcp "$REACUE_MCP"} || fail "configuration incomplète." "configuration incomplete."

MODE="${REACUE_MODE:-ask}"
if [ "$MODE" = ask ]; then
  echo
  echo "======================================================================"
  t "  Choix du mode d'installation et sélection des modèles d'IA :" \
    "  Installation mode and AI model selection:"
  echo
  t "  1. Mode Automatique [Recommandé / Débutant]" \
    "  1. Automatic Mode [Recommended / Beginner]"
  t "     ReaCue choisit et configure automatiquement la suite optimale de modèles" \
    "     ReaCue automatically configures the optimal suite of models"
  t "     pour votre matériel sans poser de questions techniques :" \
    "     for your hardware without asking technical questions:"
  .venv/bin/python reacue_gpu.py --suite --lang "$L" 2>/dev/null || true
  echo
  t "  2. Mode Personnalisé [Avancé / Sélection détaillée]" \
    "  2. Custom Mode [Advanced / Detailed selection]"
  t "     Permet de choisir et configurer chaque modèle d'IA individuellement." \
    "     Choose and configure each AI model individually."
  echo "======================================================================"
  read -r -p "$(t '  Votre choix [1] (Entrée = Mode Automatique) : ' '  Your choice [1] (Enter = Automatic Mode): ')" MODE_ANS || true
  case "$(echo "${MODE_ANS:-1}" | tr '[:upper:]' '[:lower:]')" in
    2*|c*|p*) MODE=custom ;;
    *) MODE=auto ;;
  esac
fi

CHORDS="${REACUE_CHORDS:-ask}"
DRUMS="${REACUE_DRUMS:-ask}"
WORDS="${REACUE_WORDS:-ask}"

if [ "$MODE" = auto ]; then
  t "  >> Mode Automatique sélectionné : installation optimale en cours..." \
    "  >> Automatic Mode selected: applying optimal installation..."
  STEMS=yes
  STRUCT=yes
  CHORDS=yes
  DRUMS=yes
  WORDS=yes
  export REACUE_STRUCTURE_ACCEPT=yes
  export REACUE_DRUMS_ACCEPT=yes
fi

echo
t "== 5/9 Séparation de stems (Demucs v4)" "== 5/9 Stem separation (Demucs v4)"
STEMS="${REACUE_STEMS:-ask}"
if [ "$STEMS" = ask ] && [ -x .venv-demucs/bin/python ]; then
  STEMS=yes     # déjà installée : mise à jour
fi
if [ "$STEMS" = ask ]; then
  t "  Modèles de séparation disponibles (Demucs v4, en local) :" \
    "  Available separation models (Demucs v4, local):"
  t "    • htdemucs_6s : 6 stems (voix, batterie, basse, guitare, piano, autres) [Optimal sur Apple Silicon]" \
    "    • htdemucs_6s: 6 stems (vocals, drums, bass, guitar, piano, other) [Optimal on Apple Silicon]"
  t "    • htdemucs_ft : 4 stems haute fidélité fine-tuned (voix, batterie, basse, autres)" \
    "    • htdemucs_ft: 4 stems fine-tuned high fidelity (vocals, drums, bass, other)"
  t "    • htdemucs    : 4 stems standard plus léger et rapide [Conseillé sur Mac Intel sans GPU]" \
    "    • htdemucs   : 4 stems standard faster and lightweight [Recommended on Intel Mac without GPU]"
  read -r -p "$(t '  Installer la séparation de stems Demucs (environ 1 Go, 5 à 15 min) ? [o/N] ' \
                  '  Install Demucs stem separation (about 1 GB, 5 to 15 min)? [y/N] ')" A || true
  case "$(echo "${A:-n}" | tr '[:upper:]' '[:lower:]')" in
    o*|y*) STEMS=yes ;;
    *) STEMS=no ;;
  esac
fi
if [ "$STEMS" = yes ]; then
  bash install/install_stems_mac.sh "$L" \
    || t "  ! séparation de stems non installée (le reste de ReaCue fonctionne). Réessaie avec « Install ReaCue Stems.command »." \
         "  ! stem separation not installed (the rest of ReaCue works). Try again with “Install ReaCue Stems.command”."
else
  t "  Non installée. Plus tard : double-clic sur « Install ReaCue Stems.command »." \
    "  Not installed. Later: double-click “Install ReaCue Stems.command”."
fi

echo
t "== 6/9 Analyse de structure (SongFormer)" "== 6/9 Structure analysis (SongFormer)"
STRUCT="${REACUE_STRUCTURE:-ask}"
if [ "$STRUCT" = ask ] && [ -x .venv-structure/bin/python ]; then
  STRUCT=yes    # déjà installée : mise à jour
fi
if [ "$STRUCT" = ask ]; then
  t "  Détecte couplets, refrains, ponts… avec SongFormer (IA, en local) : c'est l'analyse par défaut de ReaCue." \
    "  Detects verses, choruses, bridges… with SongFormer (AI, local): ReaCue's default analysis."
  t "  Usage non commercial (licence des poids MuQ) : il faudra taper « J'accepte » à l'étape suivante." \
    "  Non-commercial use (MuQ weights licence): you will have to type “I accept” at the next step."
  read -r -p "$(t '  Installer l'"'"'analyse de structure (environ 3 Go à télécharger, 10 à 40 min, 8 Go de RAM conseillés) ? [O/n] ' \
                  '  Install structure analysis (about 3 GB to download, 10 to 40 min, 8 GB RAM recommended)? [Y/n] ')" A || true
  case "$(echo "${A:-o}" | tr '[:upper:]' '[:lower:]')" in
    n*) STRUCT=no ;;
    *) STRUCT=yes ;;
  esac
fi
if [ "$STRUCT" = yes ]; then
  bash install/install_structure_mac.sh "$L" \
    || t "  ! analyse de structure non installée (ReaCue garde sa détection). Réessaie avec « Install ReaCue Structure.command »." \
         "  ! structure analysis not installed (ReaCue keeps its own detection). Try again with “Install ReaCue Structure.command”."
else
  t "  Non installée. Plus tard : double-clic sur « Install ReaCue Structure.command »." \
    "  Not installed. Later: double-click “Install ReaCue Structure.command”."
fi

echo
t "== 7/9 Reconnaissance d'accords (Modèle ISMIR 2019)" "== 7/9 Chord recognition (ISMIR 2019 Model)"
if [ "$CHORDS" = ask ] && [ -x .venv-chords/bin/python ]; then
  CHORDS=no
  t "  Modèle d'accords déjà installé dans .venv-chords." "  Chord model already installed in .venv-chords."
fi
if [ "$CHORDS" = ask ]; then
  t "  Reconnaissance d'accords par IA (Large-Vocabulary CNN, en local, licence MIT) :" \
    "  AI chord recognition (Large-Vocabulary CNN, local, MIT license):"
  t "  Détecte avec précision accords majeurs/mineurs, 7e, m7, maj7, dim, aug, sus et renversements (D/F#)." \
    "  Accurately detects major/minor, 7th, m7, maj7, dim, aug, sus, and inversions (D/F#)."
  read -r -p "$(t "  Installer la reconnaissance d'accords (environ 60 Mo, rapide) ? [O/n] " \
                  '  Install chord recognition (about 60 MB, fast)? [Y/n] ')" A || true
  case "$(echo "${A:-o}" | tr '[:upper:]' '[:lower:]')" in
    n*) CHORDS=no ;;
    *) CHORDS=yes ;;
  esac
fi
if [ "$CHORDS" = yes ]; then
  bash install/install_chords_mac.sh "$L" \
    || t "  ! reconnaissance d'accords non installée (ReaCue garde sa détection standard)." \
         "  ! chord recognition not installed (ReaCue keeps standard detection)."
fi

echo
t "== 8/9 Transcription de batterie (ADTOF)" "== 8/9 Drum transcription (ADTOF)"
if [ "$DRUMS" = ask ] && [ -x .venv-drums/bin/python ]; then
  DRUMS=no
  t "  Modèle de batterie ADTOF déjà installé dans .venv-drums." "  ADTOF drum model already installed in .venv-drums."
fi
if [ "$DRUMS" = ask ]; then
  t "  Transcription de batterie ADTOF (entraîné sur 359h de musique, en local) :" \
    "  ADTOF drum transcription (trained on 359h real music, local):"
  t "  Alimente le prompteur batterie : kick, snare, toms, charley ouvert/fermé, crashs, fills et breaks." \
    "  Feeds drummer prompter: kick, snare, toms, open/closed hi-hat, crashes, fills and breaks."
  read -r -p "$(t '  Installer la transcription de batterie ADTOF (environ 16 Mo) ? [O/n] ' \
                  '  Install ADTOF drum transcription (about 16 MB)? [Y/n] ')" A || true
  case "$(echo "${A:-o}" | tr '[:upper:]' '[:lower:]')" in
    n*) DRUMS=no ;;
    *) DRUMS=yes ;;
  esac
fi
if [ "$DRUMS" = yes ]; then
  bash install/install_drums_mac.sh "$L" \
    || t "  ! transcription de batterie non installée (ReaCue garde sa détection standard)." \
         "  ! drum transcription not installed (ReaCue keeps standard detection)."
fi

echo
t "== 9/9 Paroles et chant (Whisper)" "== 9/9 Lyrics and vocals (Whisper)"
if [ "$WORDS" = ask ] && [ -x .venv-words/bin/python ]; then
  WORDS=no
  t "  Modèles de paroles déjà installés dans .venv-words." "  Lyrics models already installed in .venv-words."
fi
if [ "$WORDS" = ask ]; then
  t "  Paroles Essentiel : Whisper small en local, calage par ligne." \
    "  Essential lyrics: local Whisper small, line timing."
  t "  Profil Avancé facultatif : large-v3-turbo et calage mot-à-mot wav2vec2." \
    "  Optional Advanced profile: large-v3-turbo and wav2vec2 word alignment."
  read -r -p "$(t '  Installer les paroles Essentiel ? [o/N] ' \
                  '  Install Essential lyrics? [y/N] ')" A || true
  case "$(echo "${A:-n}" | tr '[:upper:]' '[:lower:]')" in
    o*|y*) WORDS=yes ;;
    *) WORDS=no ;;
  esac
fi
if [ "$WORDS" = yes ]; then
  bash install/install_words_mac.sh "$L" \
    || t "  ! modèles de paroles non installés (ReaCue garde le calage par ligne)." \
         "  ! lyrics models not installed (ReaCue keeps line-by-line alignment)."
fi

# Synchronisation finale des réglages REAPER
SETTINGS_FILE="$REAPER_DIR/ReaCueMCP/reacue_settings.json"
.venv/bin/python reacue_gpu.py sync-settings "$SETTINGS_FILE" >/dev/null 2>&1 || true

echo
echo "======================================================================"
t "  Installation de ReaCue terminée avec succès !" \
  "  ReaCue installation completed successfully!"
t "  Lancez REAPER et ouvrez l'action « ReaCue » depuis la barre d'outils." \
  "  Launch REAPER and open the “ReaCue” action from the toolbar."
echo "======================================================================"

