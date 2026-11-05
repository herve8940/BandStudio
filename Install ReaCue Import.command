#!/bin/bash
# Optional online import component; the rest of ReaCue stays offline.
set -euo pipefail
cd "$(dirname "$0")"
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$HOME/.deno/bin:/usr/local/bin:/opt/homebrew/bin:$PATH"
command -v uv >/dev/null || { echo 'Installe d’abord ReaCue : uv est nécessaire.'; exit 1; }
if ! command -v ffmpeg >/dev/null || ! command -v ffprobe >/dev/null || ! command -v deno >/dev/null; then
  echo 'Import nécessite ffmpeg, ffprobe et Deno >= 2.3.'
  if command -v brew >/dev/null; then
    read -r -p 'Installer ffmpeg et Deno avec Homebrew ? [o/N] ' answer
    case "$answer" in o|O|y|Y) brew install ffmpeg deno ;; *) exit 1 ;; esac
  else
    echo 'Installe ffmpeg et Deno (https://deno.com/) puis relance ce fichier.'
    echo 'Avec Homebrew : brew install ffmpeg deno'
    read -r -p 'Entrée pour fermer… ' _ || true
    exit 1
  fi
fi
[ -x .venv-import/bin/python ] || uv venv .venv-import --python 3.12
uv pip install --python .venv-import/bin/python --upgrade -r requirements-import.txt
.venv-import/bin/python -m yt_dlp --version
ffmpeg -version
deno --version
echo 'Import installé. Rouvre ReaCue : + Nouveau morceau > Depuis un lien YouTube.'
read -r -p 'Entrée pour fermer… ' _ || true
