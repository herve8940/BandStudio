## BandStudio 1.1.0

- Stabilisation du bouton Play et de l’horloge audio au démarrage.
- Écoute solo/sans instrument pour tous les musiciens, conservée dans les exports.
- Logs locaux avec rotation, diagnostic exportable et formulaire GitHub.
- Mises à jour vérifiées depuis main après fermeture, sauvegarde et restauration sur erreur.
- Vérifications Windows/macOS, site GitHub Pages, guide et modèles de contribution.

# Changelog

## Unreleased — Windows optional installers

- Omit `-ExtraIndexUrl` when no CUDA index is selected: Windows PowerShell 5.1 otherwise drops the empty argument and prevents all five optional installers from starting.
- Keep forwarding the selected CUDA index on NVIDIA systems. Add Windows tests for CPU, automatic mode, CUDA 12.4/12.8, skipped components and child-process failures.
- Report a partial installation, list the installers to rerun and return a failure status when a selected optional component fails, while still attempting the remaining components.

## Unreleased — native REAPER Studio styling

- Apply the effective Studio graphite/orange/green palette to the native Lua window; prefer Studio font families with system fallbacks.
- Open at 920 px and add a project/playback/time/tempo banner with a narrow-window fallback; retain the dedicated Stage banner and compact dock.
- Refine large actions, panels and Stage titles; preserve existing commands and confirmation paths.
- Add bilingual native-window previews and installation instructions in docs/NATIVE_STUDIO.md.

## Unreleased — Studio design and stage controls

- Refine Studio console, concert/lighting and phone prompter to match the supplied Studio Pro references.
- Add persistent Stage/Details views and a browser fullscreen control.
- Add accessible keyboard fader/pan adjustment, touch-sized mute/solo targets and a live clipping indicator; correctly parse a 0 dB peak.
- Route Space to the active screen transport and ignore it in dialogs/editable controls; make concert sections keyboard accessible.
- Include three demo screenshots and design/use notes in docs/STUDIO_DESIGN.md.

## Unreleased — lyrics synchronization

- Preserve Whisper line timestamps alongside automatic lyric drafts instead of discarding them and estimating timing again. Repair older auto drafts once when the transcription matches their existing text; never overwrite edits.
- Validate timing against the vocal source and text, retain manual timing overrides, and invalidate lyric caches when timing or vocal audio changes.
- Report missing, failed or partial word alignment in publication results and warnings. Real-song validation is still required.

## Unreleased — macOS Metal/MPS

- Add explicit Standard/Fast performance profiles and CPU thread controls in advanced settings.
- Add SongFormer CPU calibration (warm-up and repeated inference, one model load) with a Mac launcher.
- Fast mode reduces Demucs overlap/random shifts, SongFormer automatic context and Whisper decoding work; quality tradeoffs are documented.
- Preserve selected stem models and invalidate profile-dependent structure/transcription caches.

- macOS: use available MPS for SongFormer, wav2vec2 inference and ADTOF; retain CPU outputs for CTC/NumPy.
- Retry failed Metal inference on CPU, including Demucs separation and installer benchmarks.
- Preserve explicit `PYTORCH_ENABLE_MPS_FALLBACK`; allow `REACUE_DEVICE=cpu` on Mac.
- Add simulated device, fallback and worker regression tests. Real Mac performance validation pending.

## 1.2.2 — 2026-10-27 — correction macOS (séparation de stems)

### Corrections
- macOS (Intel & Apple Silicon) : séparation de stems (Demucs) — correction du test de processus en vie (`pid_alive` dans `ReaCue_stems.lua`). L'appel REAPER `ExecProcess('/bin/kill -0 <pid>')` renvoyait une chaîne (`"0\n"`) et non un entier, ce qui faisait échouer la comparaison `r == 0` en Lua et provoquait l'affichage erroné d'une alerte de crash (« Le processus de séparation s'est arrêté de façon inattendue ») au bout de 3 secondes alors que Demucs tournait normalement en arrière-plan. / macOS (Intel & Apple Silicon): fixed stem separation alive-check (`pid_alive` in `ReaCue_stems.lua`) where REAPER `ExecProcess` returns string exit codes, falsely triggering a crash popup.

## 1.2.1 — 2026-10-26 — correction Windows (analyse de structure)

### Corrections
- Windows : analyse de structure (SongFormer) — PyTorch 2.4.1 au lieu de 2.4.0, dont `fbgemm.dll` ne se charge pas sous Windows (`OSError` WinError 126 « Le module spécifié est introuvable »). / Windows: structure analysis uses PyTorch 2.4.1 instead of 2.4.0 (fbgemm.dll WinError 126).

## 1.2.0 — 2026-10-24 — timecode automatique grandMA3, onglet Lumière, tutoriels complets

### Docs
- Tutorials FR / EN: new chapter 20 “Composants facultatifs / Optional components” (installers, what each brings,
  download size and time, fallback, licences and “J'accepte”, removal) and chapter 21 appendix with every
  `reacue_settings.json` key (default, role, where to set it); PDF chart (10), lyrics word by word, automatic
  lyrics and `#` comments (12), prompter roles table with Stage control / Lighting, open hi-hat and highlighted
  word (13), engine settings (14), troubleshooting rows. README / LISEZMOI: features, optional components
  table, “PDF chart / Grille PDF” section, `drums_engine` setting, uninstall of every component.
  grandMA3 menu fixed everywhere in the docs: *Menu → Output Configuration → Connector Configuration*.

### Onglet Lumière de la fenêtre ReaCue / Lighting tab of the ReaCue window
- **New tab “Lumière / Lighting”** (`reaper/ReaCue_tab_lighting.lua`, between Stage and Settings, FR / EN,
  hover help): cues of the open song or concert (number, SMPTE timecode from `gma3_tc_start` / `gma3_fps`,
  name) read from the published prompter (`lighting` block) or computed from the regions, current cue
  highlighted while playing, current timecode (project time + start); clear message when nothing is exported
  or when settings / structure changed since the export.
- **Configuration** written to `reacue_settings.json` like the Settings tab (other keys kept): export, fps,
  start, TC Slot, LTC output (REAPER's audio outputs, mono or pair), MTC device (REAPER's MIDI outputs),
  concert gap and slot.
- **Actions**: *Create / update the timecode tracks* (new CLI command `timecode`, bridge 1.5.0 handler
  `timecode_tracks`: same code as the preparation, generator setting kept, rest of the project untouched),
  *Export now* (`publish` for a song, new CLI command `concert-lighting` for a built concert), *Open the
  grandMA3 folder*.
- **Communication test**: chips (LTC output exists, MIDI device found and enabled, `TIMECODE` tracks with a
  generator and current settings, generator setting remembered, with the one-time how-to) and **Send a 10 s
  test**: only the `TIMECODE` tracks play (solo; “solo defeat” tracks muted), then solo, mute, position and
  playback are restored exactly (after 10 s, second press, REAPER Stop, window closed); during playback it
  needs a second press. Concert auto-stop and instrument mutes are paused during the test.
- Window header: tab widths follow their labels when five uniform tabs do not fit.
- Fix: the Song tab's “Prompter published / Chords / Drums” chips ignored songs exported with a `lighting`
  block (`"concert": false` was taken for a concert prompter).
- An old bridge gets a clear explanation (“bridge too old: run the installer again, restart REAPER”).
  Tests: `tests/test_lighting_tab.py`; screenshots `window_lighting_fr.png` / `_en.png`.

### Timecode automatique vers grandMA3 / Automatic timecode to grandMA3
- **Timecode tracks / pistes timecode** (`reacue_mcp/timecode.py`, `ReaCue_Bridge.lua` 1.4.0): with
  `gma3_ltc_output` and/or `gma3_mtc_output`, each preparation creates `TIMECODE LTC` (REAPER's SMPTE
  LTC/MTC generator, action 40208, over the whole project, sent to a hardware audio output, mono `7` or pair
  `"7/8"`, never to the master) and `TIMECODE MTC` (same generator, track MIDI hardware output found by device
  name). Replaced at every preparation, never duplicated. Sent time = project time + `gma3_tc_start` at
  `gma3_fps`, like the Timecode XML. The generator's `<SOURCE LTC` fields are undocumented: ReaCue never
  writes them itself, it reapplies the block the user set **once** in *Source properties* (remembered per
  fps + start in `ReaCueMCP/timecode/`) and reminds the user until then.
- **Concert**: one timecode track per output over the whole concert (built from the remembered setting, or
  the first song's generator and routing), the songs' timecode tracks are never copied.
- Timecode tracks are ignored everywhere a generated track is (analysis, stems separation, Song tab, stage
  mute, rehearsal mute, concert audio lanes, region pick-up).
- **grandMA3 plugin “ReaCue”** written with every export: `gma3_library/datapools/plugins/ReaCue.xml` +
  `ReaCue.lua`, and copies of the XML files in `gma3_library/datapools/sequences/` and `…/timecodes/` (USB
  stick layout). One tap: imports the Sequences (keeps an existing Sequence of the same name), the Timecode
  (asks before replacing), sets TC Slot (`gma3_tc_slot`), Auto Start, Auto Stop; final message with the
  input setup. Defensive (pcall, several command forms, read-back). The validated Timecode XML is unchanged
  (`TCSlot="-1"`).
- **Prompter, Lighting role**: timecode outputs (LTC → output, MTC → device, TC Slot) and a 3-line setup
  reminder (FR / EN).
- Settings: `gma3_ltc_output` (null), `gma3_mtc_output` (null), `gma3_tc_slot` (1). Empty = no track,
  nothing changes. Docs (README / LISEZMOI, tutorials 16.9): console (LTC XLR), onPC on the same Mac (IAC),
  onPC on another computer (macOS Network MIDI / rtpMIDI), one-time setup. Tests: `tests/test_timecode.py`.

## 1.1.0 — 2026-10-24 — lumière grandMA3, paroles mot par mot et automatiques, accords et batterie par modèle, grille PDF

### Lumière grandMA3 / grandMA3 lighting export
- **grandMA3 export / export grandMA3** (`reacue_mcp/lighting.py`): one cue per section (named after the
  section) at the start of its region, in REAPER project time (count-in included). Song: `grandMA3/` next to
  the `.RPP` with `<Title>_Sequence.xml`, `<Title>_Timecode.xml`, `<Title>_conduite.csv`; concert:
  `Concerts/grandMA3/<concert>/` with one Sequence per song, one Timecode (one track per song) and the cue
  sheet. XML generators ported as is from the reference validated on a desk (DataVersion 2.4.2.2, UTF-8 BOM,
  OffCue + CueZero, 3-character `No`, `Target` without quotes, `Object="13.13.0.5.<track>"`,
  `ValCueDestination="0.5.<track>.<n×1000>"`, `CueDestination` = cue name). Cleaned sequence names (ASCII +
  `_`), unique cue names, suggested effect per section type (FR / EN) as XML comment and in the cue sheet.
  Written automatically at each preparation (where the prompter is published) and each concert build;
  never blocks them (warning only).
- **Prompter: Lighting role / rôle Lumière** (FR / EN): cue list with SMPTE time and suggested effect,
  current cue highlighted from the play position, countdown to the next cue, timecode, fps / start / slot,
  download links (files also written to `reaper_www_root`, prefix `reacue_gma3_`; no internet needed).
- **Settings / réglages**: `gma3_export` (true), `gma3_fps` (25), `gma3_tc_start` ("00:00:00:00"),
  `gma3_song_gap` (null = setlist gap, 4 s), `gma3_song_slot` (0 = off). Gap and slot change the **real**
  placement of the songs in the concert project (tempo map, regions, `.concert.lua`, prompter, timecode all
  agree): with a slot, each song starts on the next multiple, the gap being lengthened by whole bars at an
  adjusted tempo (the grid stays right); the placement is stored in the setlist (`layout`) and reused by the
  background prompter pass. Defaults keep the previous behaviour.
- Docs: lighting section in README / LISEZMOI, tutorials 16.9 (FR / EN), recommendation to have REAPER send
  MTC or LTC to the desk (the concert stops between songs). Tests: `tests/test_lighting.py`.
### Paroles mot par mot / Word-by-word lyrics (optional component)
- New optional component `.venv-words` (`Install ReaCue Words.command` / `.bat`, `install/install_words_*`,
  `requirements-words.txt`, `reacue_words.py`): forced alignment of the known lyrics on the vocal stem
  (`torchaudio.functional.forced_align`, wav2vec2 XLSR-53 fine-tuned in French / English by J. Grosman,
  Apache-2.0; same PyTorch versions as Demucs, no `transformers`). / Nouveau composant facultatif : chaque mot
  est placé à son vrai moment, à l'intérieur des lignes déjà calées (le calage par ligne reste l'ancrage et
  le repli).
- Lyrics entries get an optional `words: [{"w", "t", "end"}]` field (file time, converted to the REAPER
  timeline by `prompter.lyrics_on_timeline`); existing formats unchanged. Separate cache
  (`<cache>_words.json`); any failure keeps the line timing.
- Prompter (Vocals): the current word is highlighted, sung words are dimmed. / Prompteur : mot en cours
  surligné. PDF chart: each word goes in the bar where it is sung. / Grille PDF : vrais temps des mots.
- Settings `words_engine` (`auto` | `off`) and `words_language` (`auto` | `fr` | `en`, auto = guessed from
  the lyrics text).
- `tools/compare_words.py`: before / after on the last prepared song, never prints the lyrics.
### Paroles automatiques / Automatic lyrics (optional, Whisper)
- When the song folder has no lyrics file, ReaCue transcribes the vocal stem with **Whisper** (openai-whisper,
  code and weights MIT, `large-v3-turbo`, ≈ 1.6 GB, in `words/whisper/`) inside `.venv-words`
  (`reacue_transcribe.py`, `reacue_mcp/lyrics_auto.py`) and writes a draft **`paroles (auto).txt`** in the
  song folder, then used like a normal lyrics file (line timing, then word by word). / Sans fichier de
  paroles, brouillon automatique à corriger.
- The user's file (`paroles.txt`, `lyrics.txt`…) always wins; the draft is created once and never
  overwritten (correct it in place or rename it). Lines starting with `#` are now comments in lyrics files.
- Against hallucinations on singing: voice activity on the stem (only sung parts are transcribed),
  `condition_on_previous_text=False`, no-speech / log-prob thresholds, removal of typical captions and of
  looping repetitions; one line per sung phrase (long segments split), empty line between blocks.
- `Install ReaCue Words` also installs Whisper (`requirements-whisper.txt`, `--no-deps`; numba 0.62.1 /
  llvmlite 0.45.1 / tiktoken 0.9.0 wheels for Mac Intel) and downloads the model; re-running it completes an
  existing install (`REACUE_WHISPER=0` to skip). Fallback: official Hugging Face weights converted locally.
- ReaCue window: orange pill *Paroles : auto (N lignes)* / *Lyrics: auto (N lines)* (click: open the draft);
  PDF chart footer mentions automatic lyrics. Setting `lyrics_auto` (`auto` | `off`). Never blocking: any
  failure = no lyrics, as before (failure remembered, no retry at every publication).
- `tools/transcribe_lyrics.py`: transcription by hand, prints statistics only (never the text).
### Accords : modèle entraîné (facultatif) / Chords: trained model (optional)
- New optional component **chord recognition** (`Install ReaCue Chords.command` / `.bat`,
  `install/install_chords_{mac.sh,windows.ps1}`, `requirements-chords.txt`, separate `.venv-chords`):
  model of Jiang et al., *Large-Vocabulary Chord Transcription via Chord Structure Decomposition*
  (ISMIR 2019, Music X Lab, code **and weights MIT**), pinned revision downloaded from GitHub into
  `chords/model`. / Nouveau composant facultatif : reconnaissance d'accords par modèle entraîné.
- `reacue_chords.py` (runs in `.venv-chords`): ensemble of 5 CNN + BiLSTM networks (triad, bass, 7th, 9th,
  11th, 13th), HMM decoding **aligned on ReaCue's beats** (changes on beats, cheaper on beats 1 and 3),
  network probabilities cached (a grid change only re-decodes); `check` tests it on synthetic chords.
- `reacue_mcp/chord_model.py`: harmonic mix (stems without vocals or drums, else the single file),
  subprocess, per-song cache in `.reacue/`, failure remembered for 1 h; `chords.chords_from_segments` maps
  the model's chords onto the bars in the **same format** as before (≤ 2 chords per bar, `N.C.`,
  inversions `A/C#`, confidence); sharps / flats from the key (estimated from the chords when unknown),
  inversion basses spelled as chord tones (`E/G#`, `Ab/C`), 9/11/13 shown as the matching 7th.
- `chords.cached_chords` uses the model when installed (setting **`chords_engine`**: `"auto"` | `"reacue"`,
  env `REACUE_CHORDS_ENGINE`), otherwise or on failure ReaCue's detection (unchanged, same cache key).
- `tools/compare_chords.py`: model vs ReaCue, bar by bar, on the user's songs.
### Batterie : transcription par modèle (ADTOF) / Drums: model-based transcription (ADTOF)
- **ADTOF** (optional component, `.venv-drums`, `Install ReaCue Drums.command` / `.bat`): trained drum
  transcription of the drum stem (kick, snare, toms, hi-hat, cymbals), run in a subprocess
  (`reacue_drums.py`), cached next to the stem; automatic fallback to ReaCue's rules if missing or failing
  (setting `drums_engine`: `auto` | `reacue`). / Transcription entraînée du stem batterie, repli automatique.
- Hits snapped to ReaCue's grid (bar times from the analysis, global latency estimated), **sixteenths or
  triplets** chosen per song; toms split by pitch (T1 / T2 / FT), **open hi-hat** (new `HO` lane, shown by
  the prompter), crash vs ride per section; same output format (patterns, fills, crashes). / Quantification
  sur la grille, double-croches ou triolets, charley ouvert, crash / ride.
- Licences: ADTOF weights CC BY-NC-SA 4.0 (non-commercial), explicit “J'accepte / I accept” in the
  installers; see THIRD_PARTY_NOTICES.md. Comparison tool: `tools/compare_drums.py`.

## 1.0.1 — 2026-10-22 — docs : captures mises à jour / updated screenshots

Documentation: every screenshot regenerated with the current code, in French **and** English, with made-up
content only (demo songs, address 192.168.1.20, PIN 1234). / Toutes les captures régénérées avec le code
actuel, en français **et** en anglais, contenu entièrement fictif.

### Documentation
- **Gallery at the top of README / LISEZMOI / Galerie en tête** (window, prompter, Stage control / fenêtre,
  prompteur, Régie); the window table now shows every view (Song, Do everything, structure editing,
  + New song, Concert, batch preparation, Stage, Played live, Check, QR, assistant, simple and advanced
  settings). Tutorials FR / EN: same views, plus the prompter roles, concert mode (“your stem is muted”) and
  Stage control.
- New captures / nouvelles captures: `window_{check,newsong,qr}_{fr,en}`, all `window_*_en`,
  `prompter_concert*`, `prompter_regie*` (top and bottom of Stage control). Rendering ×2 (sharper).
- `tests/test_doc_screenshots.py` renders every window view in FR and EN and **fails on any cut label**
  (`U.fit`, extra lines of `U.para`) or text overflowing the window; `REACUE_SHOTS=docs/images` writes the
  PNG files. `tools/make_screenshots.py` adds a made-up three-song concert, the instruments state, Stage
  control (remote alive, rehearsal, PIN) and checks the concert rank.

### Fixed / Corrections (labels cut in the window or on the phones / libellés coupés)
- Window / fenêtre: `U.on_cut` hook; long folder paths keep their end (`…/REAPER Media/Concerts`,
  `U.fit_path`); the setlist heading uses the room left by *Rename*; the non-commercial notice wraps on two
  lines; shorter texts « SongFormer non installé » (settings) and « non installée : détection simple (moins
  précise) » (assistant); English colon without space (“Structure: SongFormer ✓”, “Solution:”);
  paragraphs never start a line with « » », « : », « ; », « ! », « ? ».
- Prompter / prompteur: long section and song names shrink (down to 60 %) instead of ending in « … »
  (current / next section, drummer view, Stage control title); on phones, the top title wraps on two lines
  without the key, and moves to its own line when « ton stem est coupé / joué » is shown; non-breaking
  « 2e section = plage ».

## 1.0.0 — 2026-10-22

First stable release / Première version stable. Contents of the 0.12.0 development cycle below.
Première version stable : contenu du cycle 0.12.0 ci-dessous.


### Added / Ajouts
- **SongFormer by default / SongFormer par défaut**: the main installers (macOS / Windows) offer the
  structure analysis by default at step 6/6 (`[O/n]` / `[Y/n]`, Enter = yes); the explicit licence
  acceptance “J'accepte” / “I accept” is still required. New `reacue_structure.py reuse`, run by the
  structure installers before the test: models already on the computer are **copied or hard-linked** instead
  of downloaded again — SongFormer checkpoints from `~/Documents/ReaCue-labo/SongFormer/src/SongFormer/ckpts`
  (or `REACUE_REUSE_DIRS`, checked against SongFormer's `md5sum.txt`) and the default Hugging Face cache
  (`~/.cache/huggingface/hub`, `$HF_HOME`, `$XDG_CACHE_HOME`, `%USERPROFILE%\.cache\huggingface\hub`: MuQ,
  wav2vec2-conformer; only complete snapshots); sources are never changed or deleted. Clear fallback message
  « Analyse SongFormer impossible : … → structure ReaCue utilisée ». Snapping: two consecutive parts of the
  same kind stay separate when both are ≥ 8 bars (8 + 8 = two verses); Instrumental / Solo / Intro / Outro
  no longer numbered. Doubtful section starts (`moved` ≥ ¾ bar, `unsure` 0.3–0.75 bar) passed to the window.
  Real-case test (a French song at 105.12 BPM, boundaries on bars 9/17/25/33/41/49/57/73).
- **Easier ReaCue window / Fenêtre ReaCue plus intuitive** (FR / EN):
  - Song tab: a **big contextual button** follows the song's state (« Séparer les stems » → « Analyser et
    préparer » → « Prêt ✓ », « Appliquer les modifications » after an edit) with secondary « Re-préparer »,
    « Réanalyser depuis zéro », « Mettre à jour les téléphones »;
  - **« Tout faire » / “Do everything”** (`reaper/ReaCue_flow.lua`): split stems if needed, analyse and
    prepare, update the phones, save; checklist with state and time, *Stop* (after the current step),
    *Resume* at the failed step; offered right after « + Nouveau morceau »;
  - **status pills**: Stems · Structure (SongFormer | ReaCue | manuelle, kept in the project) · Tempo ·
    Accords · Batterie · Paroles N lignes · Prompteur publié · Enregistré — a click does the useful action;
  - **structure band**: one coloured box per section (width ∝ bars), orange = to check (length not 4/8/16,
    boundary moved by snapping or between two bars), hover details, click = select and listen; *Renommer*,
    ±1 bar, *Fusionner →*, *Couper en deux*, *Supprimer*, **Annuler / Rétablir** (history), *Appliquer*;
  - **help line** at the bottom for the element under the mouse; **errors explained** (`reaper/ReaCue_guide.lua`):
    cause, what to do and an action button (start the bridge, set media online, run an installer, save, open
    the log, REAPER preferences); *Vérifier*: *Corriger* also for the bridge and the web interface;
  - Concert tab: **batch preparation** « Préparer tous les morceaux non préparés » / « Préparer la sélection »
    (tick boxes): one song after the other in the background (opened in a tab, *Tout faire*, saved, tab
    closed), global progress, stop;
  - **first-launch assistant** (`reaper/ReaCue_assistant.lua`, also *Réglages → Vérifier l'installation*):
    bridge, web interface and port, IP, program, stems, SongFormer, projects folder, each with a fix button;
  - Settings: **simple view** + **Réglages avancés** (PIN, cue lead, count language / voice / speed, volumes,
    tempo, separation model, folders); new `count_rate` control;
  - plain words everywhere (window, messages, prompter page, docs): « Analyser et préparer », « Mettre à jour
    les téléphones », « Réanalyser depuis zéro »… REAPER action names are unchanged (shortcuts kept).
  - Tutorials FR / EN rewritten around « + Nouveau morceau » → « Tout faire »; new screenshots.
- **Licences, responsibilities and disclaimers / Licences, responsabilités et avertissements**:
  new `THIRD_PARTY_NOTICES.md` (every third-party component and downloaded model, code and weights licences,
  checked on 22/10/2026: SongFormer CC BY 4.0, **MuQ weights CC BY-NC 4.0 — non-commercial**, MusicFM MSD
  checkpoint licence not clearly stated, Demucs MIT, luaqrcode BSD-3, Python packages from PyPI…), new
  `CITATION.cff` (ReaCue + SongFormer, MuQ, MusicFM, Demucs), new section in README / LISEZMOI linked from the
  top (MIT “as is”, no weights redistributed, non-commercial structure analysis, user responsible for the
  rights on audio/stems/lyrics, trademarks: not affiliated with Cockos / Anthropic, not legal advice).
  The structure installers (macOS / Windows, main installer step 6/6 and `Install ReaCue Structure`) show the
  licence summary and install **only if the user types exactly “J'accepte” / “I accept”** (typographic
  apostrophe accepted); unattended: `REACUE_STRUCTURE_ACCEPT=yes`; acceptance remembered in
  `structure/.licenses_accepted`. Stem installers show a short licence note (Demucs MIT). Settings tab:
  **Licences** button (opens `THIRD_PARTY_NOTICES.md`, or the GitHub page) and “non-commercial use only”
  under *Structure detection*. `.gitignore`: model weight files (`*.safetensors`, `*.pt`, `*.pth`,
  `*.ckpt`, `*.onnx`, `*.th`, `ckpts/`). Tests `tests/test_licences.py` (refusal, typed and environment
  acceptance, memory, PowerShell, internal links, no weights tracked).
- **Structure analysis with SongFormer (optional) / Analyse de structure avec SongFormer (facultative)**:
  new optional component installed by the main installer (new step 6/6, `REACUE_STRUCTURE=yes|no` /
  `-Structure yes|no|ask`) or by **`Install ReaCue Structure.command` / `.bat`**
  (`install/install_structure_mac.sh`, `install/install_structure_windows.ps1`): separate `.venv-structure`
  with versions pinned per platform (`requirements-structure.txt`; Intel Mac: torch 2.2.2), SongFormer, MuQ
  and MusicFM downloaded at fixed commits into `structure/`, models downloaded once (`HF_HOME` inside the
  install folder), `STRUCTURE_OK` check with the speed; no weights in the repository. Launcher
  `reacue_structure.py` (mix or sum of stems → JSON segments; window 420 s with ≥ 15 GB of RAM, else 120 s;
  status file read by REAPER). `reacue_mcp/structure.py`: *Prepare* / *Re-analyse* / `prepare_song` use it
  when installed and keep ReaCue's grid — boundaries snapped to the nearest bar (4-bar phrase preferred
  within 1 bar), pieces < 2 bars merged, silence at the ends ignored, FR/EN numbered names, *inst* → Solo
  when the guitar stands out and the voice is low, letters per group; cache per song
  `.reacue/<song>_structure.json` invalidated when the audio changes; any failure → ReaCue's detection with a
  warning; hand-edited regions and `set_sections` keep priority. Progress “Structure analysis…” in the Song
  tab; setting **Structure detection** (`structure_engine`: `auto` / `reacue`) with the installed status in
  the Settings tab. Uninstall keeps it unless `--purge`; `status` reports `structure`. Bench:
  `tools/struct_eval.py --songformer` compares ReaCue v3 and SongFormer + snapping. Licences: SongFormer
  CC BY 4.0 (arXiv:2510.02797); **MuQ weights CC BY-NC 4.0 → non-commercial use**; MusicFM code MIT.
- **“+ New song” / « + Nouveau morceau »** (Song tab header, under the Concert tab's song list): one file
  (MP3, WAV, AIFF, FLAC, OGG, M4A) or a folder of stems (REAPER's file dialog: pick one stem and its folder is
  used; with js_ReaScriptAPI, `JS_Dialog_BrowseForFolder`). Title suggested from the name (no “-Bass-”, key,
  BPM, “441hz”, “Official … Video”), confirmed, never overwrites an existing song. Files copied (block by
  block in the background, size checked) to `<projects folder>/<Title>/` with their original names, new
  project tab, one file per track at 0 s, project saved as `<Title>/<Title>.RPP`, then the Song tab shows the
  next step (*Split stems* for a single file, otherwise *Prepare*). New `reaper/ReaCue_newsong.lua`.
  Claude: new tool `new_song(files, title)` (`reacue_mcp/newsong.py`: same copy and project file).
  Ajouter un nouveau morceau (MP3 ou stems) depuis la fenêtre.
- **Automatic save of the song's project** after a successful *Split stems*, *Prepare*, *Apply* or
  *Re-analyse* started from the window (never a concert project); “saved ✓” / “not saved” in the Song tab.
  Concert tab: click a song's name to open it in a new tab.
- **The ReaCue window / la fenêtre ReaCue** (new main action **ReaCue**, `reaper/ReaCue.lua`): one window with
  four tabs — **Song** (status; *Split stems*, *Prepare*, *Re-analyse*, *Republish* with the progress in the
  tab; structure list with first bar and length, odd lengths in orange, click = go and listen, rename, move
  the start by ±1 bar, delete, add at cursor, each with an Undo point, then *Apply*; lyrics file and line
  count, *Open folder*, chords / drums published; *Add to a concert*), **Concert** (song projects of the
  projects folder with prepared ✓ / to prepare, setlist editor with +, reorder, remove, rename and total
  duration, *Build* / *Rebuild* in the background then open in a new tab, *Open*, *Played live…*, existing
  concerts), **Stage** (the former Concert window plus the instruments, rehearsal, Check, QR, PIN; a simple
  transport for a single song with sections, instruments, rehearsal loop and Stage control; message and
  shortcuts when nothing is open), **Settings** (`reacue_settings.json` written atomically, other keys kept:
  language, count-in, cue lead, count language, cues, voices from the system list, click output, front of
  house, volumes, tempo mode, separation model, folders, PIN; installed version). The tab is chosen
  automatically (concert → Stage, song → Song, otherwise the last one). Docked low: compact transport bar.
  The background jobs (automatic stop, rehearsal loop, Stage control, live profile) run on every tab. The
  action **ReaCue - Concert** opens the same window on the Stage tab (a second action hands over to the
  window already open instead of opening another one). FR/EN everywhere. Lua split into modules:
  `ReaCue_ui.lua` (drawing, buttons, long press, confirmations) and `ReaCue_tab_song.lua`,
  `ReaCue_tab_concert.lua`, `ReaCue_tab_stage.lua`, `ReaCue_tab_settings.lua`.
  Une seule fenêtre en quatre onglets pour préparer, composer le concert, jouer et régler.
- **Instruments: mute, solo, “played live” / Instruments : couper, solo, « joué en live »**: a row of
  Mute/Solo buttons for the concert's instrument tracks (Vocals, Drums, Bass, Guitars, Lead guitar, Keys,
  Other, Mix; never CLICK / VOICE / CUES): click = mute / unmute (double tap during playback outside
  rehearsal), long press = solo, *Hear everything*; manual choices last until the next song. A **“played
  live” profile** saved with the concert (`live`, `live_exceptions` in `<name>.setlist.json`, kept on
  rebuild) mutes the stems the band plays for real, with **per-song exceptions** (stem / live), applied when
  each song starts and re-read when the file changes (no rebuild). The rehearsal count-in bar keeps the
  chosen state. State published in `ReaCue/mix` (`role=1|0[L],…;solo;hear-all;song`). Check view: “Muted
  stems” information line. Stage control: same buttons (commands `mute|role`, `solo|role`, `hearall|1/0`,
  PIN). Prompter: each musician sees “your stem is muted / playing”. Claude: `build_concert(…, live=[…],
  live_exceptions={…})`, `set_sections([{"concert": {…, "live": …}}])`, new tool
  `set_live_profile(concert, live, exceptions, replace_exceptions)` and
  `set_sections([{"concert_live": {…}}])` to change an existing concert's profile without rebuilding.
- Tests: `tests/test_reacue_window.py` (tabs, automatic tab and hand-over between the two actions, Song tab:
  Prepare / Re-analyse commands and progress, rename / move / delete / add a region, lyrics count, add to a
  concert; Concert tab: scan, +, reorder, rename, Build command then open in a new tab, live profile kept;
  Settings tab: values written, other keys kept, language switch; instruments: profile, exceptions, solo,
  hear everything, remote commands with PIN, profile edited by Python and by the window, Check line,
  rehearsal count-in bar; Lua JSON round trip; FR and EN; renders the tabs to PNG with
  `REACUE_SHOTS=<folder>`), `tests/test_concert.py` (live profile kept on rebuild, edited without rebuild,
  MCP), Stage control page extended (instruments, “your stem” note per role).
- **Check / Vérifier** (pre-show check) in the *ReaCue - Concert* window: audio files readable (not offline),
  spoken cue files present, songs prepared (structure and tempo), concert up to date (fingerprint — size and
  Adler-32 — of each song project stored at build time and compared), ReaCue bridge, REAPER web interface,
  network address, audio device running, click / cue outputs (existing hardware outputs, not muted, routed
  somewhere), prompter published, Stage control phones seen (the Stage control page writes
  `ReaCue/remote_seen` every few seconds). Green / orange / red summary; **Fix** buttons: set all media online,
  rebuild the concert, republish the prompter. Also available with no concert open (system part).
  Contrôle avant concert avec corrections en un clic.
- **Rehearsal mode / Mode répétition** (window and Stage control phone): automatic stop off; tap a section to
  **loop** it, a 2nd section of the same song to loop the range; **one bar of count-in** (click and spoken
  cues only, the other tracks muted during that bar) before the loop starts and before each repeat, at the
  tempo of that point (bar length from REAPER's tempo map); speed 100 / 90 / 80 / 70 % (master playrate,
  pitch preserved); *Loop off*; leaving the mode restores speed, automatic stop, REAPER's repeat, time
  selection and preserve-pitch option. Remote commands `reh`, `loop`, `loopoff`, `rate`; state published in
  `ReaCue/rehearsal` for the phones.
  Boucle avec une mesure de décompte avant chaque reprise, ralenti.
- Tests: `tests/test_check_rehearsal.py` (checks with offline / missing media, missing outputs, stale or old
  concert, unprepared song, fixes, window check view FR/EN; loop on a section and a range, count-in bar at the
  right tempo, muting, restart, stop during the count-in, speed, exit, remote commands, no auto stop in
  rehearsal), Stage control page extended (rehearsal, loop, speed, `remote_seen`) in FR and EN.

### Changed / Modifications
- Concert sidecar `.concert.lua` version 2: build time and a fingerprint of each song project.
- Concert window: tool row on its own line (status, then Check / Rehearsal / Setlist / PIN / QR); text
  truncation now cuts whole UTF-8 characters.
- `ReaCue_run.lua` exposes `bridge_alive`, a small JSON encoder / decoder, atomic writes and a
  start / status API for background CLI jobs; `ReaCue_stems.lua` exposes start / poll / finish (progress shown
  inside the ReaCue window).
- Installers register the **ReaCue** action (first) and copy the new Lua modules.
- Settings: the click output menu now offers outputs 1/2 as well.
- Stage control page and docs: “ReaCue - Concert window” is now “the ReaCue window (Stage tab)”.
- Docs: README / LISEZMOI and both tutorials reorganised around the window tabs, with screenshots of a
  made-up concert.
- Package version `1.0.0`.

## 0.11.0-beta — 2026-10

### Added / Ajouts
- **Concert mode / Mode concert**: several already prepared songs chained in one REAPER project, without
  re-analysis (stems, tempo map — fixed or beatmap —, validated structure, spoken cues and click taken from
  each song's own project, read-only). One track per instrument shared by all songs (localized names), one
  colour per song, regions “Song · Section”, a “Songs” ruler lane, a whole number of bars between songs.
  New `reacue_mcp/concert.py`; MCP tool `build_concert`, also reachable as
  `set_sections([{"concert": {"name": …, "songs": [...]}}])`; CLI `concert --name … --songs …` /
  `concert --setlist …` and `concert-extras` (chords, lyrics, drums per song, cached next to each song, in the
  background). Files `<name>.RPP`, `.setlist.json`, `.concert.lua`, `.prompteur.json` in the concerts folder.
  New settings `projects_dir` (default `<Documents>/REAPER Media`) and `concert_dir` (default
  `<projects folder>/Concerts`).
  Plusieurs morceaux préparés enchaînés dans un seul projet, sans réanalyse.
- **ReaCue - Concert window / fenêtre** (`reaper/ReaCue_Concert.lua`, `ReaCue_concert_lib.lua`): song x/N,
  tempo, key, section, bar, Playing/Paused/Stopped, progress and time left, concert time, next song; big
  Previous / Start / Play-Pause / Stop / Next buttons with a double tap during playback; clickable sections;
  setlist and *Rebuild the concert*; list of concerts to open in a new tab; compact docked view; **automatic
  stop at the end of each song** with the cursor on the next count-in. Actions *ReaCue - Next song* /
  *Previous song* for pedals and shortcuts. Registered by the installers (and removed on uninstall).
- **QR code** of the prompter address in the Concert window: IP computed on click (macOS `ipconfig getifaddr`,
  Windows `ipconfig` without console window, Linux `hostname -I`), port read from `reaper.ini`. Encoder:
  [luaqrcode](https://github.com/speedata/luaqrcode) (BSD, `reaper/ReaCue_qrcode.lua`, unchanged).
- **Stage control / Régie** role in the prompter (French and English): phone remote for the concert
  (Play/Pause, Stop, Previous / Start / Next, setlist, sections), 4-digit PIN generated on the first launch of
  the Concert window (changeable), replay protection, acknowledgement. Commands go through REAPER's web
  interface (`/_/SET/EXTSTATE/ReaCue/remote/…`) and are executed by the Concert window. The PIN guards against
  mistakes, not attacks.
- Prompter: concert files (`concert` + `songs`) — the page follows the current song, shows x/N and the next song.
- Tests: `tests/test_concert.py` (build, English names and VOICE track, settings folders, setlist rebuild,
  per-song caches, CLI, MCP and `set_sections`), `tests/test_concert_lua.py` (Lua 5.4 with a simulated REAPER:
  transport, double tap, sections, auto stop, remote PIN/nonce, IP parsing macOS/Windows/Linux, CLI launch
  macOS/Windows, window FR/EN, **QR decoded** with zxing-cpp, docked view, next/previous actions),
  `tests/test_regie_web.py` (real page in headless Chromium + fake REAPER web server running the real Lua
  library, FR and EN), installer test for the new actions. Demo projects are generated by
  `tools/concert_demo.py` (fictional songs, synthetic audio).
- Tutorials: new chapter 16 *Concert mode* (build, open, play, QR, Stage control, rebuild) and troubleshooting.

### Changed / Modifications
- `prompter.stem_activity(cache=…)`: one cache file per song in concert mode.
- Package version `0.11.0b1`.

## 0.10.0-beta — 2026-10

### Added / Ajouts
- **Stem separation inside REAPER** (optional): new action **ReaCue - Separate stems / Séparer les stems**.
  Splits the selected MP3/WAV into 6 stems (vocals, drums, bass, guitar, piano, other) with Demucs 4.0.1,
  locally, in the background with a progress bar; the stems are imported on one track each, aligned with the
  original item (position, length, offset, rate), and the original item is removed (one Undo). Results are
  cached next to the song (`<song>-stems/<model>/`): running it again imports immediately. Model chosen with
  the new `stems_model` setting (`htdemucs_6s` default, or `htdemucs` for 4 stems).
  Séparation de stems dans REAPER, en local, sans abonnement.
- Separate Python environment `.venv-demucs` (Demucs needs other torch/numpy versions than ReaCue), installed
  by `install/install_stems_mac.sh` / `install/install_stems_windows.ps1`: offered at the end of the main
  installers (`REACUE_STEMS=yes|no`, `-Stems yes|no|ask`), or later with `Install ReaCue Stems.command` /
  `.bat`. Downloads both models and measures the computer's speed. Pre-built packages only (except Demucs,
  pure Python). Pinned versions: Mac Intel torch/torchaudio 2.2.2 + numpy < 2 (last PyTorch for Intel Macs);
  elsewhere torch/torchaudio 2.5.1.
- `reacue_stems.py`: launcher run by the action (`separate`, status JSON + log read by REAPER) and installer
  check (`check`); `--repo` for offline/local models.
- Lyrics: for stems separated by ReaCue, the lyrics file can also sit next to the original song file.
- **Hand-edited regions are read back**: when the song is already prepared (same audio items), *Prepare*
  (and, with Claude, `prepare_song`, `update_options`, `rename_section`) reads the project's regions and,
  if they differ from the saved structure, adopts them: start → nearest bar (¼-bar tolerance, otherwise
  rounded with a warning), names kept (section type deduced from the name, FR/EN), added/deleted regions
  taken into account, regions before bar 1 / after the end / on a taken bar ignored with a warning. The
  final window says “Structure taken from your REAPER regions”. *Republish the prompter* does not adopt
  them (warning instead). `set_sections` / `set_grid` still win. Other projects (consolidated, other song)
  are never read. New `reacue_mcp/regions.py`, `prepare_song(reanalyse=…)`.
  Les régions modifiées à la main dans REAPER sont reprises à la préparation suivante.
- Step-by-step beginner tutorials: `docs/TUTORIEL_fr.md`, `docs/TUTORIAL_en.md` (including linking
  Claude Desktop and both ways of correcting the structure).
- Tests: `tests/test_regions.py` (moved, renamed, added, deleted, off-grid, out-of-song regions, publish
  only, Claude tools, other project protected), `tests/test_stems.py` (launcher with a fake Demucs, Lua action: paths, quoting macOS/Windows,
  progress, import and alignment, cache, messages), installer and script syntax tests extended.

### Changed / Modifications
- Installers in 5 steps; `--purge` on uninstall also deletes `.venv-demucs`; `status` reports it.
- README / LISEZMOI: stem separation section, OFFLINE files on macOS (Downloads folder), limitations.
- Package version `0.10.0b1`.

## 0.9.0-beta — 2026-10

First public (private-repository) release / Première version publique (dépôt privé).

### Added / Ajouts
- **Windows support (beta, not yet tested on real hardware)**: SAPI voices through PowerShell (no console
  window), background launch from REAPER with `reaper.ExecProcess` and `pythonw.exe`, `%APPDATA%\REAPER`
  paths, `.venv\Scripts` interpreter, `Install ReaCue.bat` / `Uninstall ReaCue.bat`.
  Support Windows (bêta, non testé sur machine réelle).
- **French / English**: `language` setting; region names, spoken cues, end-of-preparation window, REAPER
  bridge messages, main warnings and the web prompter (FR/EN button, remembered on each phone). Section
  names are recognised in both languages (colours, cue text, prompter roles).
  Bilingue français / anglais.
- **One-click installers** for macOS (`Install ReaCue.command`) and Windows: uv + Python 3.12, pre-built
  packages only, REAPER scripts, bridge auto-start, actions registered in `reaper-kb.ini` when REAPER is
  closed, settings file, optional Claude Desktop entry (with backup). Idempotent; uninstallers included.
  Installateurs clé en main, désinstallation.
- `reacue_settings.json` user settings (language, voices, count-in, cue lead, volumes, routing, tempo mode).
  Settings changed after a preparation are applied the next time the song is prepared (structure kept).
- `lyrics_timing.json` accepted as an alias of `paroles_calage.json`; `lyrics*.txt` files.
- Linux: spoken cues through `espeak-ng` when available; without any speech engine, a clear warning and
  everything else still works.
- Test suite (`tests/`): i18n, voices (macOS/Windows mocked), Windows paths, CLI with a fake REAPER bridge,
  Lua scripts run with Lua 5.4 (status JSON parsing, command quoting, bridge requests), installer,
  shell/PowerShell syntax, prompter page without console errors in FR and EN.
- Documentation (README / LISEZMOI), screenshots of a fictional demo song, migration note.

### Changed / Modifications
- REAPER bridge 1.3.0: VOICE track (English) recognised as generated, localized messages.
- `ReaCue_run.lua`: the install folder is found from the ExtState, the `reacue_install.txt` file written by
  the installer, or the script location; no more hard-coded `~/Documents/reacue-mcp` (kept as last resort).
- `textutil` (RTF) only used on macOS.
- Development tools moved to `tools/` (no private paths; `struct_eval.py` reads its songs from a private JSON).
- Package version `0.9.0b1`.

### Optional ADT_STR drum transcription

- Added isolated advanced drum installer for macOS and Windows, pinned pretrained
  weights, real inference installation check and automatic fallback to ADTOF/rules.
- Preserved raw GM notes, measured timing and velocity in advanced MIDI exports;
  existing prompter lanes remain a simplified view.
- CPU smoke inference verified with PyTorch 2.8.0 and Intel-compatible 2.2.2 on Linux.
  Actual Mac/Windows validation and musical accuracy comparison remain pending.
