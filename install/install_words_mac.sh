#!/bin/bash
# Paroles calées mot par mot (alignement forcé wav2vec2) et paroles automatiques (Whisper) pour ReaCue, en local — macOS.
# Word-by-word lyrics timing (wav2vec2 forced alignment) and automatic lyrics (Whisper) for ReaCue, local — macOS.
# Lancé par « Install ReaCue Words.command » ; ou :
#   bash install/install_words_mac.sh [fr|en]
# Langues des modèles : français et anglais (≈ 1,3 Go chacun) ; une seule : REACUE_WORDS_LANGS=fr (ou en).
# Paroles automatiques : modèle choisi par lyrics_model / REACUE_LYRICS_MODEL ; sans Whisper : REACUE_WHISPER=0.
# Environnement séparé .venv-words (n'abîme pas le .venv de ReaCue). Relançable sans risque : sur une installation
# existante, seul ce qui manque est ajouté (paquets et modèles déjà présents gardés).
# Internet nécessaire : environ 1 Go pour PyTorch (rien si la séparation de stems est déjà installée) + les modèles.
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$HERE"
case "$(echo "${1:-fr}" | tr '[:upper:]' '[:lower:]')" in
  en*) L=en ;;
  *) L=fr ;;
esac
t() { if [ "$L" = en ]; then echo "$2"; else echo "$1"; fi; }
fail() { echo; t "ÉCHEC : $1" "FAILED: $2"; exit 1; }
LANGS="${REACUE_WORDS_LANGS:-fr,en}"
WHISPER="${REACUE_WHISPER:-1}"

[ "$(uname -s)" = "Darwin" ] || fail "ce script est pour macOS." "this script is for macOS."
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
command -v uv >/dev/null 2>&1 || fail "uv introuvable : installe d'abord ReaCue (Install ReaCue.command)." \
                                      "uv not found: install ReaCue first (Install ReaCue.command)."
t "  Machine : $(uname -m) — paroles mot par mot (wav2vec2) dans $HERE/.venv-words" \
  "  Machine: $(uname -m) — word-by-word lyrics (wav2vec2) in $HERE/.venv-words"
t "  Licence : modèles wav2vec2 XLSR-53 de J. Grosman (Apache-2.0), base Meta XLSR-53 (Apache-2.0) ; téléchargés depuis Hugging Face. Détails : THIRD_PARTY_NOTICES.md" \
  "  Licence: J. Grosman's wav2vec2 XLSR-53 models (Apache-2.0), Meta XLSR-53 base (Apache-2.0); downloaded from Hugging Face. Details: THIRD_PARTY_NOTICES.md"
if [ ! -x .venv-words/bin/python ]; then
  uv venv .venv-words --python 3.12 || fail "création de .venv-words impossible." "could not create .venv-words."
fi
t "  installation de PyTorch et des dépendances (plusieurs minutes)…" \
  "  installing PyTorch and the dependencies (several minutes)…"
uv pip install --python .venv-words/bin/python --only-binary :all: -r requirements-words.txt \
  || fail "installation des dépendances impossible (voir ci-dessus)." "could not install the dependencies (see above)."
if [ "$WHISPER" != "0" ]; then
  uv pip install --python .venv-words/bin/python --no-deps -r requirements-whisper.txt \
    || fail "installation de Whisper impossible (voir ci-dessus)." "could not install Whisper (see above)."
fi
WORDS_ENGINE="$(.venv-words/bin/python -c 'import os, reacue_performance as p; print(os.environ.get("REACUE_WORDS_ENGINE") or p.settings().get("words_engine", "off"))')"
if [ "$WORDS_ENGINE" = "auto" ]; then
  t "  téléchargement des modèles ($LANGS, environ 1,3 Go chacun) et test…" \
    "  downloading the models ($LANGS, about 1.3 GB each) and testing…"
  .venv-words/bin/python reacue_words.py check --lang "$L" --langs "$LANGS" \
    || fail "le calage mot par mot ne fonctionne pas (voir ci-dessus)." "word-by-word timing does not work (see above)."
else
  t "  Calage mot par mot désactivé : modèles wav2vec2 conservés s'ils existent, aucun téléchargement." \
    "  Word alignment disabled: existing wav2vec2 models kept, no download."
fi
if [ "$WHISPER" != "0" ]; then
  WHISPER_MODEL="$(.venv-words/bin/python -c 'import reacue_transcribe as r; print(r.selected_model())')"
  t "  Licence : openai-whisper et modèle Whisper $WHISPER_MODEL d'OpenAI (MIT). Détails : THIRD_PARTY_NOTICES.md" \
    "  Licence: OpenAI's openai-whisper and Whisper $WHISPER_MODEL model (MIT). Details: THIRD_PARTY_NOTICES.md"
  t "  installation du modèle Whisper sélectionné ($WHISPER_MODEL) et test…" \
    "  installing the selected Whisper model ($WHISPER_MODEL) and testing…"
  .venv-words/bin/python reacue_transcribe.py check --download --lang "$L" --model "$WHISPER_MODEL" \
    || fail "les paroles automatiques (Whisper) ne fonctionnent pas (voir ci-dessus)." "automatic lyrics (Whisper) do not work (see above)."
  t "  Paroles automatiques installées : sans paroles.txt, ReaCue écrit un brouillon « paroles (auto).txt » à corriger (réglage « lyrics_auto »)." \
    "  Automatic lyrics installed: without lyrics.txt, ReaCue writes a draft “paroles (auto).txt” to correct (“lyrics_auto” setting)."
fi
