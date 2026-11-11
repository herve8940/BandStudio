# Composants tiers et licences / Third-party components and licences

*Vérifié le 22 octobre 2026 (PyPI, dépôts GitHub, pages Hugging Face). Ce document n'est pas un avis
juridique. / Checked on 22 October 2026 (PyPI, GitHub repositories, Hugging Face pages). This document is
not legal advice.*

ReaCue lui-même est sous **licence MIT** ([LICENSE](LICENSE)). Il est fourni « tel quel », sans aucune
garantie. / ReaCue itself is under the **MIT licence** ([LICENSE](LICENSE)), provided “as is”, without
any warranty.

**Ce dépôt ne contient aucun poids de modèle ni aucun fichier audio.** Les modèles sont téléchargés par
l'utilisateur, au moment de l'installation, directement depuis les sites de leurs auteurs ; chaque
utilisateur est responsable du respect de leurs licences. / **This repository contains no model weights
and no audio.** Models are downloaded by the user, at install time, directly from their authors; each user
is responsible for complying with their licences.

## ⚠️ Usage non commercial / Non-commercial use

L'**analyse de structure (SongFormer)**, composant facultatif, télécharge les poids **MuQ-large-msd-iter**,
publiés sous **CC BY-NC 4.0 : usage non commercial uniquement**. Le modèle MusicFM (MSD) n'a pas de
licence propre clairement indiquée (voir plus bas). N'utilise pas ce composant dans un cadre commercial
(produit ou service payant) sans l'accord des ayants droit. De même, la **transcription de batterie
(ADTOF)**, composant facultatif, télécharge des poids sous **CC BY-NC-SA 4.0 (non commerciale)**. Le reste
de ReaCue n'est pas concerné.

The optional **structure analysis (SongFormer)** component downloads the **MuQ-large-msd-iter** weights,
released under **CC BY-NC 4.0: non-commercial use only**. The MusicFM (MSD) checkpoint has no clearly
stated licence of its own (see below). Do not use this component commercially (paid product or service)
without the rights holders' permission. Likewise, the optional **drum transcription (ADTOF)** component
downloads weights under **CC BY-NC-SA 4.0 (non-commercial)**. The rest of ReaCue is not affected.

## Inclus dans le dépôt / Included in this repository

| Composant / Component | Rôle / Role | Auteurs / Authors | Licence | Fichier |
|---|---|---|---|---|
| [luaqrcode](https://github.com/speedata/luaqrcode) | QR code du prompteur / prompter QR code | Patrick Gundlach and contributors | BSD 3 clauses / 3-clause BSD | `reaper/ReaCue_qrcode.lua` (copié sans modification, en-tête de licence conservé / unmodified, licence header kept) |
| [IBM Plex Sans, IBM Plex Mono](https://github.com/IBM/plex) | Polices de ReaCue Studio / ReaCue Studio fonts | IBM Corp. | SIL Open Font License 1.1 (OFL-1.1) | `reacue_mcp/web/reacue_studio/fonts/ibm-plex-*.woff2` (sous-ensemble latin des paquets npm `@fontsource/ibm-plex-sans` et `@fontsource/ibm-plex-mono` 5.3.0, non modifié / latin subset, unmodified) ; licences : `OFL-IBM-Plex-Sans.txt`, `OFL-IBM-Plex-Mono.txt` |
| [Barlow Condensed](https://github.com/jpt/barlow) | Titres de ReaCue Studio / ReaCue Studio headings | The Barlow Project Authors | SIL Open Font License 1.1 (OFL-1.1) | `reacue_mcp/web/reacue_studio/fonts/barlow-condensed-*.woff2` (`@fontsource/barlow-condensed` 5.3.0, sous-ensemble latin, non modifié / latin subset, unmodified) ; licence : `OFL-Barlow-Condensed.txt` |

Les polices sont servies par REAPER avec la page `studio.html` (aucun accès internet) ; l'OFL permet de les
redistribuer avec un logiciel, à condition de garder leur licence et de ne pas les vendre seules. / The fonts are
served by REAPER with `studio.html` (no internet access); the OFL allows bundling them with software, provided
their licence is kept and they are not sold on their own.

## Modèles téléchargés par l'utilisateur / Models downloaded by the user

| Modèle / Model | Utilisé par / Used by | Source | Licence du code / Code licence | Licence des poids / Weights licence |
|---|---|---|---|---|
| **Demucs** `htdemucs`, `htdemucs_6s` | Séparation de stems (facultatif) / stem separation (optional) | [facebookresearch/demucs](https://github.com/facebookresearch/demucs) (A. Défossez, Meta AI) — modèles téléchargés par Demucs depuis les serveurs de Meta | MIT | Pas de licence séparée indiquée pour les modèles ; le dépôt est sous MIT / no separate licence stated for the models; the repository is MIT |
| **SongFormer** (`SongFormer.safetensors`) | Analyse de structure (facultatif) / structure analysis (optional) | [ASLP-lab/SongFormer](https://github.com/ASLP-lab/SongFormer), [HF ASLP-lab/SongFormer](https://huggingface.co/ASLP-lab/SongFormer) | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) (attribution obligatoire / attribution required) | Page HF : badge CC BY 4.0, pas d'étiquette de licence formelle / HF page: CC BY 4.0 badge, no formal licence tag |
| **MuQ** `OpenMuQ/MuQ-large-msd-iter` | Dépendance de SongFormer / SongFormer dependency | [tencent-ailab/MuQ](https://github.com/tencent-ailab/MuQ) (Tencent AI Lab), [HF OpenMuQ/MuQ-large-msd-iter](https://huggingface.co/OpenMuQ/MuQ-large-msd-iter) | MIT | **[CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) — non commercial** (fichier `LICENSE_weights` du dépôt et étiquette HF / `LICENSE_weights` file and HF tag) |
| **MusicFM** MSD (`pretrained_msd.pt`, `msd_stats.json`) | Dépendance de SongFormer / SongFormer dependency | [minzwon/musicfm](https://github.com/minzwon/musicfm) (Minz Won, Yun-Ning Hung, Duc Le — ByteDance), [HF minzwon/MusicFM](https://huggingface.co/minzwon/MusicFM) | MIT (+ Apache-2.0 pour `modules/flash_conformer.py`) | **Incertaine / uncertain** : le dépôt HF est étiqueté MIT mais n'a pas de carte et rien n'est dit sur `pretrained_msd.pt` ; ce modèle est entraîné sur le Million Song Dataset, et le README des auteurs ne publie volontairement que le modèle FMA « pour éviter des complications de licence ». / The HF repo is tagged MIT but has no model card and says nothing about `pretrained_msd.pt`; this checkpoint is trained on the Million Song Dataset, and the authors' README says they chose to release the FMA model “to avoid potential licensing complications”. |
| **wav2vec2 XLSR-53 français / anglais** `jonatasgrosman/wav2vec2-large-xlsr-53-french`, `jonatasgrosman/wav2vec2-large-xlsr-53-english` | Paroles calées mot par mot (facultatif) / word-by-word lyrics timing (optional) | [HF jonatasgrosman/wav2vec2-large-xlsr-53-french](https://huggingface.co/jonatasgrosman/wav2vec2-large-xlsr-53-french), [HF jonatasgrosman/wav2vec2-large-xlsr-53-english](https://huggingface.co/jonatasgrosman/wav2vec2-large-xlsr-53-english) (Jonatas Grosman), affinés à partir de / fine-tuned from [facebook/wav2vec2-large-xlsr-53](https://huggingface.co/facebook/wav2vec2-large-xlsr-53) (Meta AI) sur / on Common Voice (CC0) | — (pas de code : ReaCue lit les poids avec PyTorch / torchaudio ; no code: ReaCue reads the weights with PyTorch / torchaudio) | Apache-2.0 (étiquette des pages HF des modèles et du modèle de base / tag of the model pages and of the base model; à revérifier sur ces pages, non consultables depuis l'environnement de développement le 23 octobre 2026 / to be re-checked on those pages, not reachable from the development environment on 23 October 2026) |
| **Reconnaissance d'accords / chord recognition** — Jiang et al., ISMIR 2019 (5 réseaux `joint_chord_net_ismir_naive_v1.0_reweight(0.0,10.0)_s0…s4.best.sdict`, ~29 Mo) | Accords du prompteur et de la grille PDF (facultatif) / prompter and PDF chart chords (optional) | [music-x-lab/ISMIR2019-Large-Vocabulary-Chord-Recognition](https://github.com/music-x-lab/ISMIR2019-Large-Vocabulary-Chord-Recognition) (Junyan Jiang, Ke Chen, Wei Li, Gus Xia — Music X Lab), révision figée / pinned revision `481f4ce7`, téléchargée dans `chords/model` | MIT (© 2023 Music X Lab) | MIT : les poids sont fournis dans le même dépôt GitHub, sous la même licence, sans licence séparée (vérifié le 23 octobre 2026). Entraîné sur des annotations publiques et des enregistrements commerciaux non redistribués. / MIT: the weights ship in the same GitHub repository, under the same licence, with no separate licence (checked on 23 October 2026). Trained on public annotations and commercial recordings that are not redistributed. |
| **ADTOF** Frame_RNN (`adtof_frame_rnn_pytorch_weights.pth`, 16 Mo / MB) | Transcription de batterie (facultatif) / drum transcription (optional) | [MZehren/ADTOF](https://github.com/MZehren/ADTOF) (Mickaël Zehren, Marco Alunno, Paolo Bientinesi) ; poids convertis pour PyTorch par / weights converted to PyTorch by [xavriley/ADTOF-pytorch](https://github.com/xavriley/ADTOF-pytorch) (Xavier Riley), téléchargés depuis GitHub / downloaded from GitHub | ADTOF : **[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)** ; ADTOF-pytorch : **aucune licence indiquée / no licence stated** | **CC BY-NC-SA 4.0 — non commercial** (poids d'origine d'ADTOF, fichier `LICENSE` du dépôt ; la conversion PyTorch en dérive / original ADTOF weights, repository `LICENSE` file; the PyTorch conversion derives from them) |
| **Whisper** `large-v3-turbo` (`large-v3-turbo.pt`, ≈ 1,6 Go / GB) | Paroles automatiques : brouillon « paroles (auto).txt » quand le morceau n'a pas de fichier de paroles (facultatif) / automatic lyrics: draft when the song has no lyrics file (optional) | [openai/whisper](https://github.com/openai/whisper) (OpenAI) — téléchargé par l'installateur depuis le serveur d'OpenAI (contrôle SHA-256), repli / fallback [HF openai/whisper-large-v3-turbo](https://huggingface.co/openai/whisper-large-v3-turbo) converti localement / converted locally | MIT (openai-whisper, PyPI) | MIT (« Whisper's code and model weights are released under the MIT License », README d'openai/whisper ; carte du modèle HF : MIT / HF model card: MIT) |
| Configuration `facebook/wav2vec2-conformer-rope-large-960h-ft` | Configuration lue par MusicFM (pas de poids) / config read by MusicFM (no weights) | [Hugging Face](https://huggingface.co/facebook/wav2vec2-conformer-rope-large-960h-ft) (Meta) | — | Apache-2.0 (étiquette HF / HF tag) |

## Code source téléchargé par l'installateur / Source code fetched by the installer

Révisions figées (voir `reacue_mcp/structure.py`) / Pinned revisions: SongFormer (CC BY 4.0), MuQ (MIT),
MusicFM (MIT / Apache-2.0) — téléchargés dans `structure/`, jamais redistribués par ce dépôt.
Reconnaissance d'accords / chord recognition : dépôt music-x-lab (MIT, voir `reacue_mcp/chord_model.py`)
téléchargé dans `chords/model` ; son code est importé tel quel par `reacue_chords.py` (sans modification).
/ fetched into `chords/model`; its code is imported unmodified by `reacue_chords.py`.

Transcription de batterie (voir `reacue_mcp/drums.py`) / Drum transcription: ADTOF-pytorch, révision
figée / pinned revision `85c192e78f716ea0b111cc8a5ee4a8f6a3a4f8a9` (code sans licence indiquée + poids
CC BY-NC-SA 4.0 / code with no stated licence + CC BY-NC-SA 4.0 weights) — téléchargé dans `drums/` après
l'accord « J'accepte », jamais redistribué par ce dépôt ; ReaCue n'en utilise que le chargement du modèle
(son propre code fait le reste) / fetched into `drums/` after the “I accept” step, never redistributed by
this repository; ReaCue only uses its model loading (its own code does the rest).

## Paquets Python / Python packages

Installés par l'installateur depuis PyPI dans `.venv`, `.venv-demucs`, `.venv-structure` ou `.venv-words` ; jamais
redistribués par ce dépôt. Licences relevées sur PyPI le 22/10/2026. / Installed from PyPI by the
installer; never redistributed by this repository.

| Paquet / Package | Environnement | Licence (PyPI) |
|---|---|---|
| mcp (Model Context Protocol SDK) | `.venv` | MIT |
| librosa | `.venv`, `.venv-structure` | ISC |
| soundfile | tous / all | BSD 3-Clause (la roue embarque libsndfile, LGPL-2.1, avec LAME et mpg123, LGPL : export MP3 de ReaCue Studio / the wheel bundles libsndfile, LGPL-2.1, with LAME and mpg123, LGPL: ReaCue Studio MP3 export) |
| lameenc (facultatif / optional) | `.venv`, si soundfile < 0.13 / if soundfile < 0.13 | LGPL-3.0-or-later (non installé par défaut / not installed by default) |
| numpy | tous / all | BSD-3-Clause (+ 0BSD, MIT, Zlib, CC0-1.0 pour des parties incluses / for bundled parts) |
| scipy | tous / all | BSD |
| demucs | `.venv-demucs` | MIT |
| torch | `.venv-demucs`, `.venv-structure`, `.venv-words` | BSD-3-Clause (+ Apache-2.0 / LLVM exception et autres pour des parties incluses / for bundled parts) |
| torchaudio, torchvision | `.venv-demucs`, `.venv-structure`, `.venv-words` (torchaudio) | BSD |
| numba, llvmlite | `.venv`, `.venv-structure`, `.venv-words` | BSD (llvmlite : BSD-2-Clause + Apache-2.0 with LLVM exception) |
| openai-whisper | `.venv-words` | MIT |
| tiktoken | `.venv-words` | MIT |
| more-itertools | `.venv-words` | MIT |
| omegaconf | `.venv-structure` | BSD |
| hydra-core | `.venv-structure` | MIT |
| einops | `.venv-structure` | MIT |
| x-transformers, x-clip, ema-pytorch | `.venv-structure` | MIT |
| transformers, safetensors, huggingface-hub | `.venv-structure` ; `.venv-words` (safetensors, huggingface-hub) | Apache-2.0 |
| nnAudio | `.venv-structure` | MIT |
| easydict | `.venv-structure` | **LGPL-3.0** (bibliothèque utilisée telle quelle, non modifiée, non redistribuée / used unmodified, not redistributed) |
| pandas | `.venv-structure` | BSD 3-Clause |
| matplotlib | `.venv-structure` | Licence matplotlib (de type PSF / PSF-based) |
| requests | `.venv-structure` | Apache-2.0 |
| tqdm | `.venv-structure`, `.venv-words` | MPL-2.0 AND MIT |
| uv (installateur / installer, Astral) | outil / tool | MIT OR Apache-2.0 |
| Tests : pytest, lupa, playwright | développement / development | MIT, MIT, Apache-2.0 |

Reconnaissance d'accords / chord recognition (`.venv-chords`, `requirements-chords.txt`) : torch
(BSD-3-Clause), librosa (ISC), numpy, scipy, soundfile (BSD), numba / llvmlite (BSD) — les mêmes paquets
que ci-dessus / the same packages as above.

Les dépendances indirectes de ces paquets suivent leurs propres licences (voir PyPI). / Transitive
dependencies follow their own licences (see PyPI).

## Logiciels et services utilisés, non fournis / Software and services used, not provided

| Élément / Item | Licence / Terms | Remarque / Note |
|---|---|---|
| [REAPER](https://www.reaper.fm/) (Cockos Incorporated) | Logiciel commercial, licence propre / commercial software, own licence | REAPER est une marque de Cockos Incorporated. ReaCue n'est ni affilié à Cockos ni approuvé par Cockos. / REAPER is a trademark of Cockos Incorporated. ReaCue is not affiliated with or endorsed by Cockos. |
| Voix système : macOS `say`, Windows SAPI, Linux `espeak-ng` (GPL-3.0) | Celles du système / the system's | Appelées comme programmes externes, non fournies / called as external programs, not provided |
| [js_ReaScriptAPI](https://github.com/juliansader/ReaExtensions) (facultatif, ReaPack) | Licence de son auteur (non vérifiée ici) / its author's licence (not checked here) | Utilisée seulement si l'utilisateur l'a installée lui-même / used only if the user installed it |
| Claude / Claude Desktop (Anthropic) — mode MCP facultatif / optional | Conditions d'Anthropic / Anthropic's terms | ReaCue n'est ni affilié à Anthropic ni approuvé par Anthropic. / ReaCue is not affiliated with or endorsed by Anthropic. |
| Moises (cité dans la doc / mentioned in docs) | — | Marque de son propriétaire ; aucun lien avec ReaCue / trademark of its owner; no relationship with ReaCue |

## Références / References

- Chunbo Hao, Ruibin Yuan, Jixun Yao, Qixin Deng, Xinyi Bai, Yanbo Wang, Wei Xue, Lei Xie (ASLP-lab),
  *SongFormer: Scaling Music Structure Analysis with Heterogeneous Supervision*, arXiv:2510.02797. https://arxiv.org/abs/2510.02797
- Haina Zhu, Yizhi Zhou, Hangting Chen et al. (Tencent AI Lab), *MuQ: Self-Supervised Music Representation Learning with Mel Residual
  Vector Quantization*, arXiv:2501.01108, 2025. https://arxiv.org/abs/2501.01108
- Minz Won, Yun-Ning Hung, Duc Le, *A Foundation Model for Music Informatics*, arXiv:2311.03318, 2023.
  https://arxiv.org/abs/2311.03318
- Alexis Conneau, Alexei Baevski, Ronan Collobert, Abdelrahman Mohamed, Michael Auli (Meta AI), *Unsupervised
  Cross-lingual Representation Learning for Speech Recognition* (XLSR-53), arXiv:2006.13979, 2020.
  https://arxiv.org/abs/2006.13979 — modèles affinés / fine-tuned models : Jonatas Grosman, *Fine-tuned XLSR-53 large
  model for speech recognition in French / English*, Hugging Face, 2021.
- Alec Radford, Jong Wook Kim, Tao Xu, Greg Brockman, Christine McLeavey, Ilya Sutskever (OpenAI), *Robust Speech
  Recognition via Large-Scale Weak Supervision* (Whisper), arXiv:2212.04356, 2022. https://arxiv.org/abs/2212.04356
- Mickaël Zehren, Marco Alunno, Paolo Bientinesi, *ADTOF: A large dataset of non-synthetic music for
  automatic drum transcription*, ISMIR 2021, pp. 818–824 ; *High-Quality and Reproducible Automatic Drum
  Transcription from Crowdsourced Data*, Signals 4(4), 768–787, 2023. https://doi.org/10.3390/signals4040042
- Simon Rouard, Francisco Massa, Alexandre Défossez, *Hybrid Transformers for Music Source Separation*,
  ICASSP 2023, arXiv:2211.08553. https://arxiv.org/abs/2211.08553
- Junyan Jiang, Ke Chen, Wei Li, Gus Xia, *Large-Vocabulary Chord Transcription via Chord Structure
  Decomposition*, ISMIR 2019. https://archives.ismir.net/ismir2019/paper/000078.pdf

## ADT_STR — optional advanced drum transcription

Melucci, Merialdo and Akama, ADT_STR (2026).
Code: https://github.com/pier-maker92/ADT_STR
Weights: https://huggingface.co/Pierfrancesco/adt-str
Code revision: 77dbef225e7029478ebfb916f20c7a00274f0f12.
Weights revision: a33c5c6b191a4ca1e0f6dc22140947485eb36ce8, setting-tau-0.8.
Upstream licence: CC BY-SA 4.0. Downloaded separately, including upstream
LICENSE/README. ReaCue's adapter preserves the predicted events and projects
supported GM drum notes onto its existing nine display lanes; it does not retrain
or modify the model weights. Refer to the upstream licence for attribution and
share-alike conditions when distributing adaptations.

## BandStudio 0.4 — nouveaux composants locaux (8 novembre 2026)

- Beat This 1.1.0, modèle final0 : code et poids MIT, Francesco Foscarin, Jan Schlüter et Gerhard Widmer / CPJKU. Source : https://github.com/CPJKU/beat_this ; poids téléchargés depuis le serveur des auteurs. Empreinte du checkpoint : `8c328b45f59d8dd3dff219253ff6a8d6482be57d0133a29140e2febbf8eb8331`.
- DrumSep 49469ca8 : dépôt MIT, Copyright (c) 2024 Iñaki Goyeneche. Source et lien des poids : https://github.com/inagoy/drumsep ; modèle Hybrid Demucs pour grosse caisse, caisse claire, toms et cymbales/charleston. Empreinte : `aefaa8543c9b9c75e22f5f32b53ab86dfe416457849af1383ff1aef83401423f`. Les poids ne sont pas ajoutés au dépôt Git.
- rotary-embedding-torch 0.6.5 : MIT ; soxr 0.3.7 : bibliothèque de rééchantillonnage (licences de la distribution et de libsoxr conservées dans le moteur).
- ReportLab 4.4.10 : BSD ; police Bitstream Vera embarquée par ReportLab avec sa licence.
- qrcode 8.2 : BSD ; Pillow : HPND et licences des composants embarqués.
- gdown 5.2.0 : MIT, utilitaire de téléchargement facultatif des poids DrumSep.

Le runtime Mac conserve les notices des paquets et les fichiers LICENSE des deux modèles.
Les archives Windows installent ces modèles séparément ; aucun audio personnel n’est distribué.
La normalisation utilise les filtres loudnorm de FFmpeg (mesure EBU R128) et ne constitue pas un moteur
de mastering artistique. Le prompteur réseau utilise la bibliothèque standard Python et reste désactivé
jusqu’à son activation par l’utilisateur.

## BandStudio 0.5 creative components

MusicGen Small: Meta / facebookresearch AudioCraft. Code MIT, model weights CC-BY-NC 4.0 (non-commercial). Official model revision 4c8334b02c6ec4e8664a91979669a501ec497792. https://huggingface.co/facebook/musicgen-small and https://github.com/facebookresearch/audiocraft/blob/main/LICENSE_weights . Models are downloaded from their authors; no weights are included in the Windows release.

UVR MDX Karaoke 2: official TRvlvr/model_repo release, SHA-256 bf32e15105a09c0f7dddd2b67346146334d6f3ecb399ed7638eba2ab07cbf5f4. Model attribution and original terms remain with its authors; the application makes no ownership claim over the weights. https://github.com/TRvlvr/model_repo/releases/tag/all_public_uvr_models .

MDX spectrum packing and inference conventions adapted from python-audio-separator (MIT), Copyright (c) 2023 karaokenerds. https://github.com/nomadkaraoke/python-audio-separator .

MIT License

Copyright (c) 2023 karaokenerds

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

Transformers 4.44.2: Apache-2.0, Hugging Face. ONNX Runtime 1.19.2: MIT, Microsoft. SentencePiece 0.2.0: Apache-2.0, Google. Safetensors 0.4.5: Apache-2.0, Hugging Face. Their distribution license files are preserved in the isolated Python runtime.
