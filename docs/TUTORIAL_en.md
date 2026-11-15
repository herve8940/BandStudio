# ReaCue tutorial — step by step

> **Standalone BandStudio app:** see the [BandStudio tutorial](BANDSTUDIO_TUTORIAL_en.md) for manual editing, song sheets and PDFs. The tutorial below covers the legacy ReaCue scripts inside REAPER.

*[Version française : TUTORIEL_fr.md](TUTORIEL_fr.md)*

This tutorial takes you from installation to rehearsing with the band. It assumes you can start REAPER and
play a song, nothing more. Each step tells you **where to click**, **what you should see** and **what to do
if it does not work**.

At the end, for each song, you will have in REAPER:

- a tempo map locked to the song, named and coloured regions (Intro, Verse 1, Chorus…);
- a **CLICK** track with a 2-bar count-in, a **VOICE** track that says “Chorus” before each section and
  counts “one two three four”;
- a **prompter** on every musician's phone: structure, chords, lyrics (word by word when the component is
  installed), drums, plus **Stage control** (remote) and a **Lighting** role;
- a printable **PDF chart** (chords and lyrics, bar by bar) in the song's folder;
- the files of a show for a **grandMA3** lighting desk (one cue per section) and, if you want, tracks that
  send **timecode** to the desk.

Everything is done from **one window, “ReaCue”**, with five tabs: **Song** (prepare a song), **Concert**
(put a concert together and build it, prepare several songs at once), **Stage** (play: transport,
instruments, rehearsal, Stage control), **Lighting** (grandMA3 desk: cues, timecode, test) and **Settings**.

**Optional components**, which also run on your computer, improve the analysis: stem separation (Demucs),
structure analysis (SongFormer), chords and drums by a trained model, word-by-word lyrics and automatic lyrics
(Whisper). Without them, everything works with ReaCue's own detection
([chapter 20](#20-optional-components)).

**For each song it comes down to two clicks**: **+ New song**, then **Do everything**. A big button always
gives the next step, a line at the bottom of the window explains the button under the mouse, and an error
tells you what to do with a button that does it.

Timing depends on the computer and optional components. First downloads and AI processing can take
several minutes or longer per song, especially on Intel Macs.

> **Studio Pro web interfaces:** console [17.3](#173-reacue-studio-the-practice-screen),
> show/lighting [17.5](#175-reacue-studio-the-show-and-lights-screens), prompter [13.1](#131-prompter-stage-view-and-details).
> After updating the repository, rerun the installer to copy web assets, then reload the pages.
> The native ReaCue windows in REAPER and the Studio/Prompter web pages are separate interfaces.

---

## Contents

1. [What you need](#1-what-you-need)
2. [Download ReaCue](#2-download-reacue)
3. [Get REAPER ready for the installation](#3-get-reaper-ready-for-the-installation)
4. [Run the installer](#4-run-the-installer)
5. [Check in REAPER](#5-check-in-reaper)
6. [Enable REAPER's web interface (once)](#6-enable-reapers-web-interface-once)
7. [Create a project for a song](#7-create-a-project-for-a-song)
8. [Import the audio: stems or a single MP3](#8-import-the-audio-stems-or-a-single-mp3)
9. [Split an MP3 into stems](#9-split-an-mp3-into-stems)
10. [Prepare the song](#10-prepare-the-song-with-do-everything)
11. [Check the structure](#11-check-the-structure)
12. [Add the lyrics](#12-add-the-lyrics)
13. [Open the prompter on the phones](#13-open-the-prompter-on-the-phones)
14. [Set up the click, the spoken cues and the in-ears](#14-set-up-the-click-the-spoken-cues-and-the-in-ears)
15. [Link Claude Desktop (optional)](#15-link-claude-desktop-optional)
16. [Concert mode: several songs in one project](#16-concert-mode-several-songs-in-one-project)
17. [At rehearsal](#17-at-rehearsal)
18. [Troubleshooting](#18-troubleshooting)
19. [Cheat sheet: a new song, a concert](#19-cheat-sheet-a-new-song-a-concert)
20. [Optional components](#20-optional-components)
21. [Appendix: all settings](#21-appendix-all-settings)

---

## 1. What you need

| Item | Details |
|---|---|
| Computer | Mac (macOS 12 or later, Intel or Apple Silicon) or Windows 10/11 PC (Windows: beta) |
| REAPER | Version 7 or later, already installed ([reaper.fm](https://www.reaper.fm/)) |
| Disk space | 1.5 GB for ReaCue; more for each optional component you install (from a few hundred MB to about 5 GB, see [chapter 20](#20-optional-components)) |
| Internet | Only during installation |
| Audio | The stems of a song (one file per instrument), **or** a single MP3/WAV |
| Phones | On the **same Wi-Fi** as the computer, with a browser (Safari, Chrome…) |

> Stems give the best results. If you only have the MP3, ReaCue can split it into stems on your computer
> (step 9).

---

## 2. Download ReaCue

1. On the project's GitHub page, click the green **Code** button, then **Download ZIP**.
2. Open the downloaded ZIP file: a `reacue-main` folder appears.
3. **Move this folder to its final place**, for example in *Documents*, and rename it `ReaCue`.

**You should see** in the `ReaCue` folder: `README.md`, `LISEZMOI.md`, the folders `reacue_mcp`, `reaper`,
`install`, `docs`, and the installers (`.command` for Mac, `.bat` for Windows):

| File | What it does |
|---|---|
| `Install ReaCue` | ReaCue itself; also offers stem separation and structure analysis (step 4) |
| `Install ReaCue Stems` | splitting an MP3 into stems (Demucs) |
| `Install ReaCue Structure` | structure analysis (SongFormer) |
| `Install ReaCue Chords` | chords by a trained model |
| `Install ReaCue Drums` | drums by a trained model (ADTOF) |
| `Install ReaCue Words` | word-by-word lyrics and automatic lyrics (Whisper) |
| `Uninstall ReaCue` | uninstall |

The five optional components are described in [chapter 20](#20-optional-components).

> ⚠️ Do not move this folder after installation. If you have to, run the installer again from the new place.

---

## 3. Get REAPER ready for the installation

1. **Start REAPER once**, then **quit it** (macOS: *REAPER → Quit REAPER*; Windows: *File → Quit*).

Why: on its first start REAPER creates its settings folder, and the installer can only register the ReaCue
actions while REAPER is **closed**.

---

## 4. Run the installer

### On a Mac

1. In the `ReaCue` folder, **double-click `Install ReaCue.command`**.
2. If macOS says it cannot be opened because it is from an unidentified developer: click **OK**, then
   **right-click** (or Ctrl-click) `Install ReaCue.command` → **Open** → **Open**.
   On recent macOS versions you may have to go to *System Settings → Privacy & Security*, scroll down and
   click **Open Anyway**.
3. A Terminal window opens.

### On Windows

1. In the `ReaCue` folder, **double-click `Install ReaCue.bat`**.
2. If Windows shows “Windows protected your PC” (SmartScreen): click **More info**, then **Run anyway**.
3. A black console window opens.

### The questions (Mac and Windows)

| Question | What to answer |
|---|---|
| `Langue / Language [fr/en]` | `en` then Enter |
| `Register ReaCue in Claude Desktop …? [y/N]` | `n` if you don't use Claude Desktop (you can do it later) |
| `Install stem separation …? [y/N]` | `y` if you have songs as MP3 only (about 1 GB to download, 5 to 15 minutes); otherwise `n` |
| `Install structure analysis …? [Y/n]` | **Enter** (= yes, offered by default): better sections with SongFormer (AI, about 3 GB to download, 10 to 40 minutes, 8 GB of RAM recommended, **non-commercial use**); `n` to go without |
| `To install, type exactly “I accept”` (after the licence summary) | Read the summary: the MuQ model weights are for **non-commercial use only** (CC BY-NC 4.0). If that suits you, type `I accept` then Enter; otherwise just Enter (nothing is installed). Details: [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) |

**You should see** 6 steps scroll by (`== 1/6 Checks` … `== 6/6 Structure analysis`):

- at the end of step 4: a line `Likely IP address(es) of this computer: …` → **write this address down**
  (e.g. `192.168.1.20`), you will need it for the phones; then `Installation complete. Restart REAPER…`
  (ReaCue is installed);
- in step 5, if you answered `y`: PyTorch and Demucs being downloaded, two `model … ready` lines, two
  `speed … about N min for a 4-minute song` lines, then `Stem separation installed`;
- in step 6 (unless you answered `n`): the licence summary and the “I accept” prompt, then SongFormer, MuQ
  and MusicFM being downloaded, then PyTorch; `model reused: …` for each model already on the computer (for
  example in `Documents/ReaCue-labo` or the Hugging Face cache: not downloaded again), then the missing
  models (up to 2 GB), a line `speed: about N min for a 4-minute song`, `STRUCTURE_OK` and `Structure analysis installed`.

Press Enter to close the window.

**If it does not work:**

| Message | Solution |
|---|---|
| `REAPER folder not found` | Start REAPER once, quit it, run the installer again |
| `could not install uv (internet?)` | Check the internet connection, run the installer again |
| `REAPER is running: the actions cannot be registered` | No problem: quit REAPER and run the installer again, or load the actions by hand (step 5) |
| `stem separation not installed` | The rest of ReaCue works. Try again later with `Install ReaCue Stems.command` / `.bat` |
| `structure analysis not installed` | ReaCue keeps its own detection. Try again later with `Install ReaCue Structure.command` / `.bat` (it resumes where it stopped) |

> You can run the installer as many times as you like: it repairs the installation and keeps your settings.

**Complete AI Model Suite:** In **Automatic Mode** (choice 1 or *Enter*), the installer automatically installs all models suited for your hardware (Demucs stems, SongFormer structure, ISMIR chords, ADTOF drums, and Whisper lyrics). In **Custom Mode**, each model is presented with full details. Each component also retains its standalone installer (`Install ReaCue Chords`, `Install ReaCue Drums`, `Install ReaCue Words`), which can be rerun at any time.

---

## 5. Check in REAPER

1. Start REAPER.
2. Menu **Actions → Show action list…**
3. In the **Filter** box at the top, type `ReaCue`.

**You should see** seven actions:

- `Custom: ReaCue` — **the main window**, the one you will use all the time
- `Custom: ReaCue - Prepare the song`
- `Custom: ReaCue - Republish the prompter`
- `Custom: ReaCue - Separate stems`
- `Custom: ReaCue - Concert` (the same window, opened on the Stage tab)
- `Custom: ReaCue - Next song` and `Custom: ReaCue - Previous song`

**Put the “ReaCue” action on the toolbar.** Right-click the main toolbar (top left) → **Customize
toolbar…** → **Add…** → filter `ReaCue` → pick **`ReaCue`** → **Select/close** → **Save**. One click on that
button opens the ReaCue window (a 2nd click closes it).

**On first launch**, the ReaCue window opens an **assistant** that checks everything: bridge, web interface
(port), IP address, ReaCue program, stem separation, structure analysis, projects folder. Each green dot is
ready; for an orange or red one, the button on the right sets it up (*Start*, *Preferences*, *Install*,
*Create*…). **Finish** closes the assistant; it is also in *Settings → Check the installation*.

<img src="images/window_assistant_en.png" width="420">

**The ReaCue window** opens on the right tab by itself: **Stage** if the project is a concert, **Song** if it
is a song, otherwise the last one used. Right-click in the window: dock it in REAPER or undock it (docked at
the bottom, it becomes a compact transport bar). Top right, two dots: **bridge** (ReaCue answers in REAPER)
and **web** (prompter available) — green when all is well. At the bottom, the **help line** explains what the
element under the mouse does.

<img src="images/window_song_en.png" width="420">

**If the actions are missing** (REAPER was open during installation):

1. In the action list, click **New action… → Load ReaScript…**
2. Go to the scripts folder: menu *Options → Show REAPER resource path in explorer/finder*, then
   `Scripts` → `ReaCue`.
3. Pick `ReaCue.lua` → **Open**. Do the same with `ReaCue_Preparer.lua`, `ReaCue_Republier_prompteur.lua`,
   `ReaCue_Separer_stems.lua`, `ReaCue_Concert.lua`, `ReaCue_Morceau_suivant.lua` and `ReaCue_Morceau_precedent.lua`.

---

## 6. Enable REAPER's web interface (once)

The phones' prompter goes through the small web server built into REAPER.

1. Mac: menu **REAPER → Settings…**; Windows: menu **Options → Preferences…**
2. In the list on the left, at the bottom: **Control/OSC/web**.
3. Click **Add**.
4. **Control surface mode**: choose **Web browser interface**.
5. **Port**: `8080` (keep this value if you can).
6. Leave everything else as is, click **OK**, then **OK** to close the preferences.

**To check:** on the computer, open a browser at `http://localhost:8080/`: a REAPER page should appear.

**If it does not work:** another program may be using port 8080 → start again with `8081` (and use that
port everywhere below). On Windows, if the firewall asks about REAPER, tick **Private networks** and click
**Allow**.

---

## 7. Create a project for a song

**One REAPER project per song.** ReaCue replaces the regions, the tempo map and the CLICK / CUES / VOICE
tracks every time it prepares a song: do not put several songs in the same project.

### The easy way: “+ New song”

1. Open the **ReaCue** window (action **ReaCue**). The **+ New song** button is at the top of the **Song**
   tab (and under the list of songs in the **Concert** tab).
2. Click it and choose:
   - **One file (MP3, WAV…)**: pick the song's file;
   - **Stems (a folder)**: pick **one of the stem files** — every audio file in the same folder is used (with
     the *js_ReaScriptAPI* extension installed, you pick the folder directly).
3. ReaCue suggests a **title** from the name (without “-Bass-”, the key, the BPM, “Official Video”…): fix it
   if needed, **OK**. If a song with that title already exists, ReaCue asks for another title: nothing is
   ever overwritten.
4. ReaCue **copies** the files to `Documents/REAPER Media/<Title>/` (progress in the tab; file names are
   kept), opens a **new project tab** (your open project is not touched), puts **one file per track** at the
   start, and **saves** the project `<Title>/<Title>.RPP`.

**You should see** the new project's **Song** tab with the banner **“Song created. Prepare everything now?”**:
click **Do everything** (step 10) — or **Later**. The big button shows the next step: **Split stems** (single
file, step 9) or **Analyse and prepare** (stems). The song also appears in the **Concert** tab's list
(orange until it is prepared; click its name to open it).

<img src="images/window_newsong_en.png" width="420">

> Copying the files avoids the “OFFLINE” problem with files left in *Downloads* on a Mac. After a successful
> **Do everything**, **Split stems**, **Analyse and prepare** or **Apply** from the window, the song's project
> is **saved automatically** (“Saved ✓” pill): the concert always finds its sections and tempo.

### Other way (by hand)

1. Create a folder for the song, for example `Documents/REAPER Media/Demo Song/`.
2. **Copy the song's audio files into it** (stems or MP3).
   > ⚠️ On a Mac, avoid leaving the files in *Downloads*: macOS may prevent REAPER from reading them (the
   > item then shows “OFFLINE”).
3. In REAPER: **File → New project**.
4. **File → Save project as…**, pick the song's folder, name the project (`Demo Song`) and tick **Copy all
   media into project directory** if the option is offered. **Save**.
5. Import the audio (step 8).

---

## 8. Import the audio: stems or a single MP3

*Not needed if you used **+ New song** (step 7): just read the file-name table.*

### Case A: you have the stems

1. Select all the stem files in the Finder / File Explorer.
2. **Drag them together** into REAPER's track area, at the very beginning (left).
3. If REAPER asks how to place several files, choose **“One per track”**.

**You should see** one track per stem, all items starting at the same place.

File names matter: ReaCue recognises the role of each stem from words in the name:

| Role | Words recognised in the file name |
|---|---|
| Drums | `drum`, `batterie`, `kick`, `perc` |
| Bass | `bass`, `basse` |
| Guitar | `guitar`, `guitare`, `gtr` (`lead` or `solo` = lead guitar) |
| Vocals | `vocal`, `voice`, `vox`, `chant`, `voix` |
| Other | anything else (keys…) |

> Bonus: the key and tempo in the name (e.g. `Demo Song-A minor-112bpm-drums.wav`) improve the chords and
> avoid double/half tempo mistakes.

Go straight to **step 10**.

### Case B: you only have an MP3 (or a WAV)

1. Drag the file into REAPER's track area, at the very beginning.

You can prepare the song right away (step 10), but with less detail (no drum view, no per-instrument
entries/rests, less reliable chords and sections). **Better: split it into stems first (step 9).**

---

## 9. Split an MP3 into stems

*Needs stem separation installed (answer `y` in step 4, or `Install ReaCue Stems`).*

1. **Click the MP3 item** in REAPER to select it (it becomes lighter).
2. In the **ReaCue** window, **Song** tab, click the big **Split stems** button (or run the action **ReaCue -
   Separate stems**). *Do everything* (step 10) does it too, then carries on.
3. The tab shows **“Separating stems: N %”** with a progress bar.
   - Count **5 to 8 minutes for a 4-minute song** on an Intel Mac, less on a recent Mac.
   - You can switch tabs and keep working: the import happens by itself at the end.
   - Do not quit REAPER during the separation.
4. At the end, a **“Stems imported”** message appears.

**You should see** six new tracks below the original track: **Vocals, Drums, Bass, Guitar, Piano, Other**,
aligned exactly like the MP3. The MP3 item was removed from the project (the file itself is still on disk;
*Edit → Undo* brings it back).

The stem files are stored next to the MP3, in `<song name>-stems/htdemucs_6s/`.
> 💡 **Complete Stems & Hardware Guide:** For an in-depth breakdown of Demucs models (`htdemucs_6s`, `htdemucs_ft`, `htdemucs`), hardware performance (NVIDIA RTX 50 Blackwell, Apple Silicon, CPU), and band routing best practices, see the **[Best Practices & Hardware Guide](BEST_PRACTICES_AND_HARDWARE.md)**.
 If you run the action again
on the same MP3, the import is immediate (no new separation).

> Listen to the tracks solo (**S** button): vocals, drums and bass are usually very clean; guitar and piano
> may keep a bit of the other instruments. That is normal and good enough for ReaCue. An almost empty track
> (for example Piano in a song without keys) is not a problem.

**If it does not work:**

| Message | Solution |
|---|---|
| “Select the song's audio item” | Click the MP3 item, then run the action again |
| “Audio file not found… OFFLINE” | The file cannot be read: see [Troubleshooting](#18-troubleshooting) |
| “Stem separation is not installed” | Double-click `Install ReaCue Stems.command` / `.bat` in the ReaCue folder |
| “The separation failed” | Read the end of the log shown; the full log is `…-stems/demucs.log` |
| The progress stays at 0 % for a while | Normal during the first minute (model loading) |

---

## 10. Prepare the song with Do everything

1. **ReaCue** window, **Song** tab: click **Do everything** (right of the big button). No need to select
   anything.
2. A list shows the steps and their time:

   | Step | What it does |
   |---|---|
   | Split stems | only for a single MP3/WAV (“already done” otherwise) |
   | Analyse and prepare | tempo, bars, **structure** (SongFormer when installed), regions, click, cues, prompter |
   | Update the phones | lyrics, chords, drums and structure for the prompter |
   | Save the project | so that the concert finds sections and tempo |

   **Stop** stops after the current step. If a step fails, the cause and **what to do** show with a button
   (e.g. *Start the bridge*); **Resume** starts again at the failed step.
3. At the end: **“Song ready ✓”** (*Summary*: tempo, bars, structure, what was published). **Close**. The big
   button now says **Ready ✓** and the **pills** are green: Stems ✓ · Structure: SongFormer ✓ · 120 BPM ·
   Chords ✓ · Drums ✓ · Lyrics · PDF chart ✓ · Prompter published ✓ · Saved ✓.

<img src="images/window_doall_en.png" width="420">

Step by step, the big button does the same (**Split stems** → **Analyse and prepare** → **Ready ✓**); below
it: *Prepare again* (rebuilds everything keeping your structure), *Re-analyse from scratch* (tempo and
structure computed again, your fixes are replaced), *Update the phones*. The action **ReaCue - Prepare the
song** does *Analyse and prepare*.

**You should see** in the project:

- coloured **regions** at the top (Intro, Verse 1, Chorus 1…);
- **“→ Chorus”** markers before each section;
- three new tracks: **CUES**, **VOICE**, **CLICK**;
- the audio moved by 2 bars to make room for the count-in.

> **With SongFormer** (structure analysis, installed by default): the first preparation of a song takes a
> few minutes more; the list shows **“Structure analysis (SongFormer)… N s”**. The next preparations of the
> same song are immediate (result remembered). If SongFormer fails, the message says “SongFormer analysis
> failed: … → ReaCue structure used” and the pill shows **Structure: ReaCue**. To compare: *Settings* →
> *Structure detection* → **ReaCue only**, then *Re-analyse from scratch*.

> **Chords, drums, lyrics**: during the preparation or *Update the phones*, the list may show **“Chords
> (model)… N s”**, **“Word-by-word lyrics… N s”** or **“Automatic lyrics (Whisper)… N s”**: these are the
> optional components of [chapter 20](#20-optional-components), used automatically when they are installed
> (ADTOF drums has no line of its own). Each costs this time only once per song (result remembered). If one
> fails, the *Summary* says so (e.g. “Chord model unavailable: … → ReaCue's chord detection used”) and the song
> is ready anyway.

Press **Space**: you hear 2 bars of click with “one two three four”, then the song, the click and the cues.

**If it does not work:** the window shows the cause, what to do and a button. In short:

| Message | Solution |
|---|---|
| “The ReaCue bridge is not running in REAPER” | **Start the bridge** button; otherwise restart REAPER, or run the installer again (REAPER closed) |
| “ReaCue program not found” | The ReaCue folder was moved: run the installer again from its new place |
| “A preparation is already running” | Wait for the previous one to finish (1 minute max) |
| The tempo is double or half the real one | Put the tempo in the file names (e.g. `-94bpm`) and *Re-analyse from scratch* |

### The song's PDF chart

Each time the prompter is published (*Analyse and prepare*, *Prepare again*, *Do everything*, *Update the
phones*, *Apply*), ReaCue also writes a **printable chart** (A4) in the **song's folder**: the folder of the
audio files, or the folder of the original MP3 when the stems are in `…-stems/`. It is called **`Chart -
<Title>.pdf`** (`Grille - <Title>.pdf` when the language is French) and is replaced at each publication.

| It shows | Details |
|---|---|
| Header | title, tempo, time signature (4/4…), count-in, key (“estimated” when guessed from the chords) |
| One row per group of 4 bars | each section with its name, colour and number of bars |
| Chords | the chord of each bar; a box split in two when there are two |
| Lyrics | the words sung in each bar (coloured box); with word-by-word lyrics, each word is in the bar where it is really sung; without lyrics, the coloured boxes show the bars where the voice sings |
| Footer | “chords and lyrics detected automatically, please check” (or “lyrics transcribed automatically (draft)” with automatic lyrics), page number |

In the **Song** tab, the **PDF chart ✓** pill opens it (**PDF chart —**: click = create it by updating the
phones). The chart never blocks the preparation: if something goes wrong, a warning “PDF chart not created:
…” shows and everything else is ready. A concert has no chart of its own: print those of its songs.

---

## 11. Check the structure

Read the structure in the **Song** tab: the **coloured band** (one box per section, width proportional to
its number of bars) and the list below (first bar, length). **Orange** boxes are **to check** — hover them,
the help line says why:

- **unusual length**: a section that is not 4, 8 or 16 bars long is often a mistake (two sections glued
  together, or one section cut in two);
- **boundary moved when aligning on bars** or **between two bars**: SongFormer hesitated on the start.

Also look at **the names** (verse and chorus swapped, pre-chorus glued to the chorus) and the ending (a long
“Outro” may contain a last chorus or a solo).

Listen: **click a box** of the band (or a name in the list) — the section is selected and playback starts at
its beginning.

**To fix it, three ways (you can mix them):**

**Way 1 — in the Song tab** (the easiest)

<img src="images/window_structure_en.png" width="420">

Select a section (click its box); its tools show under the band:

| Button | Effect |
|---|---|
| **Rename** (or **Name** in the list) | rename (“Pre-chorus”, “Solo”…) |
| **◀** / **▶** | move the start one **bar** earlier / later (the end of the previous section follows) |
| **Merge →** | join the section with the next one |
| **Split in two** | split the section in the middle (on a bar); you name the 2nd part |
| **Delete** (or **✕**) | delete (the previous section extends to the next one) |
| **+ Section at cursor** | add a section starting at the edit cursor's bar |
| **Undo** / **Redo** | go back / redo, as many times as you like |

The big button becomes **Apply the changes** (and a “Structure changed” banner offers **Apply**): click it.
Click, cues, colours and prompter follow; the pill shows **Structure: manual**.

**Way 2 — by hand in REAPER, then “Apply”**

1. Fix the regions in the region lane (top of the window):
   - **rename** or **change the start**: double-click the region → change *Name* or *Start* → **OK**;
   - **move the start**: you can also drag the region's left edge;
   - **add**: make a time selection (drag in the ruler) starting where the new section starts, then menu
     *Markers → Insert region from time selection* (default shortcut Shift+R), and name it;
   - **delete**: right-click the region → *Remove region*.
2. Click **Apply the changes** / **Prepare again** in the Song tab (or run **ReaCue - Prepare the song**).
3. The final window starts with **“Structure taken from your REAPER regions”**, with the new table. The
   regions are recoloured, and the “→” markers, the cues, the click and the prompter follow.

Good to know:

- only the **start** of each region counts: a section lasts until the next region starts (no need to fix
  the ends);
- a start placed between two bars is moved to the nearest bar line (a warning tells you if it was more than
  a quarter of a bar away);
- the name sets the colour and the cue: “Chorus 2” or “Refrain 2” makes a chorus, “Solo” a solo…;
- a region before bar 1, after the end of the song or on the same bar as another one is ignored (warning);
- if you changed nothing, *Prepare again* keeps the saved structure, as before;
- *Update the phones* does not take edited regions: a warning asks you to click *Apply*.

**Way 3 — with Claude Desktop** (optional, see [step 15](#15-link-claude-desktop-optional))

Just say “chorus 1 starts at bar 37” or “rename section 6 to Solo”: everything is rebuilt (regions, click,
cues, prompter). What you tell Claude replaces regions edited by hand.

---

## 12. Add the lyrics

ReaCue never downloads lyrics: **you provide the text**.

1. Open a text editor:
   - Mac: **TextEdit**, then menu **Format → Make Plain Text** (important: plain text);
   - Windows: **Notepad**.
2. Type (or paste) the lyrics: **one line = one sung phrase**, an empty line between blocks (verse,
   chorus…). Lines like `[Chorus]` or `Verse 2:` are ignored, and so are lines starting with `#` (comments).
   `(x2)` or `bis` at the end of a line repeats it. A chorus written only once is found automatically when it
   is sung again (vocal stem needed).
3. Save the file as **`lyrics.txt`** (**UTF-8** encoding), **in the stems folder**. Any name starting with
   `lyrics`, `paroles` or `parole`, as `.txt` or `.rtf`, works too. For an MP3 split by ReaCue, you can put it
   **next to the original MP3** (or in the `…-stems/htdemucs_6s/` folder).
4. **Song** tab: the pill shows **Lyrics: N lines** (click it, or **Open folder**, to see where). Click
   **Update the phones** (or the action **ReaCue - Republish the prompter**): nothing in the project is changed.

**You should see** in the result: `Prompter published: … N lyric lines`. On the phone, in the
**Vocals** view, the lines scroll with the song.

The lines are aligned automatically on the vocal stem. If a line is off, you can place it by hand with a
timing file `lyrics_timing.json` (see the *Lyrics* section of the README).

**Word by word** (optional component `Install ReaCue Words`, [chapter 20.5](#205-word-by-word-lyrics-and-automatic-lyrics)):
each word is placed at its real moment, inside the lines already timed. On the phone (**Vocals** view), the
**current word is highlighted** and the words already sung are dimmed; in the PDF chart, each word goes in its
bar. A badly recognised line simply keeps its line timing.

**No text at hand?** If *automatic lyrics* are installed (Whisper, with the same `Install ReaCue Words`) and
the song has a **vocal stem**, ReaCue transcribes that stem and writes a draft **`paroles (auto).txt`** in the
song folder; the pill turns orange: **Lyrics: auto (N lines)**. Click it to open the draft, correct it by ear
(in place, or rename it `lyrics.txt`), then **Update the phones**. The lines at the top starting with `#` are
comments (ignored).

| Rule | Details |
|---|---|
| Your file first | a `lyrics.txt` (or `paroles.txt`…) of your own always wins: the draft is then no longer used |
| Only once | the draft is created once and **never overwritten**; to get a new one, delete it |
| It is a draft | singing recognition makes mistakes: read it before rehearsal; the PDF chart says so in its footer |
| Never blocking | if the transcription fails or finds no singing, the song is ready without lyrics, as before |
| Turn off | setting `lyrics_auto` = `"off"` ([appendix](#21-appendix-all-settings)) |

### 12.1 Preserve automatic lyric timestamps

When Whisper generates lyrics, ReaCue now keeps line start/end timestamps in
**`paroles (auto).timing.json`**, next to the text draft. Publication uses those times instead of
estimating line placement again from syllables. Manual timing corrections retain priority.
Changed text or vocal audio cannot reuse stale timestamps.

For an older draft without this file: open the song, keep the Lyrics/Whisper component installed,
then **republish the prompter**. ReaCue may transcribe once more to recover timestamps when text
matches; allow several minutes. The existing draft is never overwritten. Edited text that no
longer matches follows the line-alignment workflow.

An imported `lyrics.txt` is not a Whisper transcription and retains its own alignment workflow.
Publication warnings now distinguish a missing word-timing component, an error and partially
aligned lyrics. Listen back and check those lines: automatic output is not a guarantee of perfect
synchronization for every vocal performance.

---

## 13. Open the prompter on the phones

1. Connect the phone to the **same Wi-Fi** as the computer.
2. Find the computer's IP address (if you did not write it down in step 4):
   - Mac: *System Settings → Wi-Fi → Details…* (next to the connected network) → **IP address**;
   - Windows: *Settings → Network & Internet → Wi-Fi → network properties* → **IPv4 address**.
3. On the phone, open the browser and type: **`http://<IP address>:8080/prompteur.html`**
   (example: `http://192.168.1.20:8080/prompteur.html`). Careful: `http`, not `https`.
4. Pick your role: **Drums**, **Bass**, **Rhythm gtr**, **Lead gtr**, **Vocals**, **Overview**, **Stage
   control** or **Lighting** (the choice is remembered on this phone; the **Role** button changes it).
5. Start playback in REAPER: the prompter follows the position (section, bar, beat).

**You should see** the green LED at the top right (link with REAPER alive; red = link lost), the three displays
**BAR · TEMPO · KEY**, the current section (green LEDs = beats of the bar, “3/16” = bar within the section) and,
at the bottom, **NEXT / IN n bars** above the song's structure strip (tap it to show or hide the section list).

<img src="images/prompter_drums_en.png" width="200"> <img src="images/prompter_vocals_en.png" width="200">

<img src="images/prompter_vocals_en_tablet.png" width="600">

| Role | What it shows |
|---|---|
| **Drums** | groove of the section, grid of the current bar (16 steps, or triplets for a shuffle song), fills, crashes, stops and re-entries; one lane per piece: Crash, Ride, Hi-hat, **Open hi-hat**, Snare, Tom 1, Tom 2, Floor tom, Kick |
| **Bass**, **Rhythm gtr** | current chord (light card; Bass: bass note) and next chord with a count-down, chord chart of the section (current bar in orange), key, entries and exits; transposed when the stems are in ReaCue Studio |
| **Lead gtr** | solos, chords, entries |
| **Vocals** | scrolling lyrics, next line and count-down before each entry; with word-by-word lyrics, the **current word highlighted** |
| **Overview** | structure and chords |
| **Stage control** | concert remote, protected by a PIN code ([16.5](#165-drive-the-concert-from-a-phone-stage-control)) |
| **Lighting** | grandMA3 cues, current cue, timecode, files to import ([16.9](#169-lighting-grandma3)) |

When a section has a **note** (`notes` field of the published data, editable later in ReaCue Studio), it is
shown in a pink frame under the chart, for every role.

On a tablet in landscape, the Drums view puts the position (section, bar, coming fill) and the grid of the bar
side by side; only the lanes of the pieces played are shown:

<img src="images/prompter_drums_en_tablet.png" width="600">

The Drums view is more accurate when the **ADTOF transcription** is installed, the chords when the **chord
model** is ([chapter 20](#20-optional-components)); otherwise ReaCue uses its own rules.

Tips:

- **Home screen**: iPhone: *Share → Add to Home Screen*; Android: menu **⋮ → Add to Home screen**. The page
  then opens full screen, like an app.
- **Screen sleep**: tap the **⛶** button (full screen), which asks the phone to stay awake. If the screen
  still turns off, disable auto-lock during rehearsal (iPhone: *Settings → Display & Brightness → Auto-Lock →
  Never*; Android: *Display → Screen timeout*).
- **Changing address**: the router may give the computer a different IP address from one day to the next,
  and the phones' bookmarks stop working. In your router's settings, look for **“DHCP reservation”** (or
  “static lease”, “fixed IP”) and reserve the current address for the computer. At gigs, a small travel
  router dedicated to the band avoids any surprise.
- The **FR/EN** button switches the prompter language on that phone.

### 13.1 Prompter: Stage view and details

<img src="images/design_prompter_en.png" width="300" alt="Guitar prompter in Stage view">

Tap **STAGE** on the prompter to hide the detailed section list and secondary controls while keeping
the current section, role-specific chords/lyrics/drums, notes and next change. **DETAILS** restores
the full view. The role and connection indicator remain visible; this choice is remembered on the
device. Stage view does not change audio or timing.

Return to **DETAILS** to change language or use the fullscreen button. Fullscreen and keeping the
screen awake depend on browser support; test the phone before the show. The layout was checked in
Chromium at 390 × 844; Safari/iPhone still need real-device verification.

---

## 14. Set up the click, the spoken cues and the in-ears

**ReaCue** window, **Settings** tab. Each change is saved at once (“saved” shows) and **applies at the
next preparation**: click **Prepare again** in the Song tab (the validated structure is kept), or **Rebuild
the concert**. The view is **simple** by default (language, count-in, cues, voices, outputs, structure
detection, licences); **Advanced settings** adds PIN, cue lead, count language / voice / speed, volumes,
tempo, separation model and folders.

<img src="images/window_settings_en.png" width="420">

Common examples:

| I want… | In the Settings tab | Key in the file |
|---|---|---|
| A single bar of count-in | *Count-in before the song*: ◀ down to **1** | `"count_in_bars": 1` |
| The count in French | *Count*: **un deux trois quatre** | `"count_lang": "fr"` |
| No spoken cues, only the click | *Spoken cues*: **no** | `"voice_cues": false` |
| A louder click | *Click volume*: ▶ | `"click_volume": 0.8` |
| Click and voice only in the in-ears (outputs 3/4), not front of house | *Click + voice output*: **outputs 3/4**, *Also to front of house*: **no** | `"click_hw_output": 2` and `"click_to_master": false` |
| 4 stems instead of 6 | *Stem separation*: **4 stems** | `"stems_model": "htdemucs"` |
| Sections by ReaCue only (not SongFormer) | *Structure detection*: **ReaCue only** | `"structure_engine": "reacue"` |
| Chords by ReaCue's detection, even with the model installed | (file only) | `"chords_engine": "reacue"` |
| Drums by ReaCue's rules, even with ADTOF installed | (file only) | `"drums_engine": "reacue"` |
| Lyrics timed by line only (not word by word) | (file only) | `"words_engine": "off"` |
| Force the sung language (word by word, automatic lyrics) | (file only) | `"words_language": "en"` |
| No automatic lyrics draft | (file only) | `"lyrics_auto": "off"` |

<img src="images/window_settings_advanced_en.png" width="420">

The tab also shows the **installed version**. The settings live in the file **`reacue_settings.json`**
(REAPER's resource folder, menu *Options → Show REAPER resource path in explorer/finder* → folder
**`ReaCueMCP`**): you can also edit it with TextEdit or Notepad, keeping the JSON syntax. For
`click_hw_output`: `0` = outputs 1/2, `2` = outputs 3/4, `4` = outputs 5/6, and so on.

For the cue voices (`announce_voice`), see the *Settings* section of the README. The full list of keys, with
their default values, is in the [appendix (chapter 21)](#21-appendix-all-settings); the lighting settings are
in the **Lighting** tab ([16.9](#169-lighting-grandma3)).

### 14.1 Performance: Standard, Fast and CPU threads

In **Settings → Advanced settings**, choose **Standard** to preserve existing quality settings or
**Fast** to reduce Demucs, SongFormer and Whisper work. Fast can change output quality: compare stems,
structure and lyrics before validating a song. The selected stem model is preserved. **CPU threads**
offers auto / 1 / 2 / 4 / 8; more threads are not necessarily faster.

On Mac, after installing Structure, double-click **Optimize ReaCue Mac.command**. It compares actual
SongFormer CPU inference (one model load, warm-up, then two timings per setting) and saves the fastest
thread count on that sample. Allow several minutes. It does not change the quality profile, and the
result is not a guarantee for other models. To use representative audio instead of 20s synthetic input:

```bash
.venv-structure/bin/python reacue_structure.py benchmark --input "/path/excerpt.wav" --threads 1,2,4 --save
```

Macs without working MPS use CPU. Compatible Apple Silicon Macs use Metal/MPS in the adapted engines,
with CPU retry on failure; this calibration forces CPU, but normal analyses retain MPS. Select
**Standard** and **auto** to restore the original settings.

---

## 15. Link Claude Desktop (optional)

All of ReaCue works without Claude. Linking [Claude Desktop](https://claude.ai/download) also lets you drive
ReaCue in plain English: fix the structure, change a setting, move around the song.

**Requirements**

- Claude Desktop installed on **the same computer** as REAPER and signed in to your Claude account (a paid
  plan may be needed depending on the offer: check the current terms on claude.ai);
- ReaCue installed (step 4) and REAPER open, with the bridge running.

**Link ReaCue to Claude Desktop**

1. If you answered `y` to “Register ReaCue in Claude Desktop” in step 4, it is already done. Otherwise
   **run the installer again** (`Install ReaCue.command` / `.bat`) and answer `y` to that question. The
   installer adds the `reacue` server to Claude Desktop's configuration (a backup of the previous
   configuration is kept).
2. **Quit Claude Desktop completely** and start it again (Mac: menu *Claude → Quit*, not just closing the
   window; Windows: right-click the Claude icon near the clock → *Quit*, if it is there).
3. **Start a new conversation.**

**Check that the ReaCue tools are there**

Depending on your version of Claude Desktop, the tools of linked servers are behind a tools icon or a
“connectors” / “tools” menu near the message box. You should see **reacue** with its tools (`prepare_song`,
`set_sections`, `reaper_status`…). The simplest test: type “check that REAPER is responding”. Claude uses
`reaper_status` (it may ask for permission the first time) and should answer that REAPER and the bridge are
connected.

**Example requests**

| You say | What happens |
|---|---|
| “Prepare the song open in REAPER” | New song: full analysis. Already prepared song whose regions you edited: your regions are taken. Already prepared song with no edit: **new analysis** (the validated structure is replaced) — to only rebuild, use the *Prepare again* button instead |
| “Chorus 1 starts at bar 37” | Structure fixed, everything rebuilt |
| “Rename section 6 to Solo” | Region renamed, recoloured, cue changed |
| “Only republish the prompter” | Prompter updated, nothing changes in REAPER |
| “Go to chorus 2” | REAPER's cursor jumps to the start of the region |
| “Just one bar of count-in” | Setting changed, click and cues rebuilt |

**What updates by itself**: after each of these requests, the regions, markers, CUES / VOICE / CLICK tracks
in REAPER and the phones' prompter (which reloads its data every 2 seconds). Nothing to restart.

**If it does not work**

| Problem | Solution |
|---|---|
| reacue does not show in the tools | Run the installer again answering `y`, then quit Claude Desktop completely and start it again |
| Claude says REAPER is not responding | REAPER must be open; restart it to restart the bridge; a dialog left open in REAPER also blocks the bridge |
| ReaCue's new features are not visible | Tools are loaded when a conversation starts: after updating ReaCue, **start a new conversation** (and restart Claude Desktop) |
| “the project open in REAPER no longer contains the tracks of the last prepared song” | You switched projects (or consolidated): ask “prepare the song open in REAPER” to analyse it |

---

## 16. Concert mode: several songs in one project

For a gig (or a full run-through), ReaCue chains your **already prepared** songs in one REAPER project. Each
song keeps everything you validated: stems, tempo, structure, spoken cues, click.

**Before you start:** each song must have been prepared (step 10) **and its project saved** (**Cmd+S** /
**Ctrl+S**). A project saved before the preparation goes into the concert without sections.

### 16.1 Build the concert

**In the ReaCue window, Concert tab:**

<img src="images/window_concert_en.png" width="420">

1. On the left, **Songs**: the projects found in `Documents/REAPER Media` (setting *Projects folder*), with
   their tempo; **✓** = prepared, *to prepare* in orange otherwise. **Refresh** reads the folder again.
2. Click **+** on each song, in the concert's order: they are added on the right, in the **Setlist**.
   **▲ ▼** change the order, **✕** removes a song.
3. **Rename**: give the concert a name (e.g. “Saturday 15”).
4. **Build**. A song that is not prepared is reported first (you can build anyway). Building takes a few
   seconds; the concert **opens by itself in a new REAPER project tab**.

**Several songs to prepare?** Below the buttons, **Prepare all songs not prepared** (or tick songs in the
list → **Prepare the selection**). ReaCue prepares them **one after the other in the background**: each
project is opened in a tab, *Do everything*, saved, then the tab is closed. The progress shows (✓ ready, ●
running with the step, ✗ failed with the reason); **Stop** stops after the current song.

<img src="images/window_batch_en.png" width="420">

From the **Song** tab, the **Add to a concert** button adds the open song to a setlist (new or existing)
without leaving the song.

At the bottom of the Concert tab, **Existing concerts**: **Edit** loads its setlist into the editor, **Open**
opens it in a new tab. After a change, the button becomes **Rebuild**.

**With Claude Desktop** (step 15): type for example

> Build a concert “Saturday 15” with: Demo Song, Second Demo, Third Demo

Claude finds the projects by name in `Documents/REAPER Media` (setting `projects_dir`) and answers with the
concert table: start, tempo, bars and sections of each song. Warnings (song without regions…) show in its
answer.

**Without Claude** (command line, from the `ReaCue` folder):

- Mac: `.venv/bin/python -m reacue_mcp.cli concert --name "Saturday 15" --songs "Demo Song" "Second Demo"`
- Windows: `.venv\Scripts\python reacue_cli.py concert --name "Saturday 15" --songs "Demo Song" "Second Demo"`

**You should see** in `Documents/REAPER Media/Concerts/` (setting `concert_dir`): `Saturday 15.RPP`,
`Saturday 15.setlist.json`, `Saturday 15.concert.lua` and `Saturday 15.prompteur.json`. Don't edit them by hand.

Building takes a few seconds; the prompter's chords, lyrics and drums are then computed in the background
(a few minutes the first time, then kept).

### 16.2 Open the concert

1. **ReaCue** window, **Concert** tab → **Existing concerts** → **Open** next to **Saturday 15** (right after
   building, it is already open).
2. The concert opens in a **new project tab** (your current project stays open in its own tab), and the
   window switches to the **Stage** tab by itself.

**You should see** one track per instrument for the whole concert (Vocals, Drums, Bass, Guitars…), one colour
per song, the CLICK / VOICE / CUES tracks at the bottom, regions “Demo Song · Chorus 1”, and at the top a
**Songs** lane with “1 · Demo Song”, “2 · Second Demo”… The Stage tab shows **1 / 3 · Demo Song**.

<img src="images/window_stage_en.png" width="420">

> Tip: **right-click in the window** to dock it at the bottom of REAPER (it becomes a compact transport bar)
> or to undock it.

### 16.3 Play

1. Press **Space** (or the big green **Play** button of the window): count-in, then the song.
2. At the end of the song, playback **stops by itself** and the cursor goes to the next song's count-in. The
   window shows **2 / 3 · Second Demo**.
3. When the band is ready: **Space**.

The Stage tab shows the current section, “bar x / N”, the time left in the song and the concert, and the
next song. Its buttons:

| Button | Effect |
|---|---|
| **Previous** | start of the current song; at the start, previous song |
| **Start** | back to the current song's count-in |
| **Play / Pause** | plays or pauses |
| **Stop** | stops |
| **Next** | goes to the next song's count-in |
| **Section** pills | go to the start of the section (playback continues) |
| **Setlist** | list of songs: one click = go to the song; **Rebuild the concert** |

During playback, **Stop**, **Previous**, **Next** and changing song need a **double tap**: the first tap shows
“again?” in orange, the second one (within 2 seconds) runs it.

For a pedal or a keyboard shortcut: the actions **ReaCue - Next song** and **ReaCue - Previous song**
(*Actions → Show action list* → select the action → **Add…** under *Shortcuts for selected action*).

> ⚠️ The automatic stop, the phone remote and the instrument profile only work while the **ReaCue** window
> is open (any tab, even docked). Don't close it during the gig.

### 16.4 QR code for the musicians

1. In the Stage tab, click **QR**.
2. The QR code shows large with the address underneath (e.g. `http://192.168.1.20:8080/prompteur.html`) and
   the Stage control PIN code.
3. Each musician, on the **same Wi-Fi**, opens the phone's camera, points it at the QR code and taps the link:
   the prompter opens; they choose their role.
4. Click **Close** (or the QR, or Escape) to go back.

<img src="images/window_qr_en.png" width="300">

The address is computed at each click: if the computer's address changed, the QR is still right. If
“Computer IP address not found” shows: the computer is not connected to any network.

### 16.5 Drive the concert from a phone (Stage control)

1. On the phone of the person in charge: open the prompter (QR code), tap **Role** then **Stage control**.
2. Tap a button (e.g. **Play**): the phone asks for the **PIN code**. It is shown in the Stage tab (button
   **PIN 1234**, and under the QR code) and in the Settings tab. Type it, **OK**.
3. The button gets a green outline when REAPER has run the command.

<img src="images/prompter_regie_en.png" width="200"> <img src="images/prompter_regie2_en.png" width="200">

Stage control offers Play/Pause, Stop, Previous, Start, Next, the setlist, the sections and the
**instruments** (16.8), with the same double tap during playback. The PIN is remembered on the phone; **Change code** to type it again. To change
the PIN: **PIN** button of the Stage tab (4 digits).

> ⚠️ The PIN prevents mistakes, **not attacks**: anyone on the same network can drive REAPER through its web
> interface. At gigs, use a Wi-Fi reserved for the band.

### 16.6 Change a song of the concert

1. Open **the song's project** (not the concert), fix it (structure, settings…), **Apply** or **Prepare again** (saved by itself).
2. Back in the concert: Stage tab → **Rebuild the concert** → **OK** (or Concert tab → **Edit** →
   **Rebuild**).

Changes made directly in the concert project are **overwritten** by the rebuild.

### 16.7 Check before playing

Before the soundcheck or the show, click **Check** in the Stage tab.

<img src="images/window_check_en.png" width="420">

1. A list appears, with a summary at the top: **All set ✓** (green), **N thing(s) to watch** (orange) or
   **N problem(s)** (red).
2. Each line has a dot and a short detail:

| Line | What is checked | If it is not green |
|---|---|---|
| Audio files | every file of the concert is readable (not “OFFLINE”) | **Fix** sets all media online; otherwise see Troubleshooting (OFFLINE) |
| Spoken cues | the cue files are present | **Fix** rebuilds the concert |
| Prepared songs | each song has a structure and a tempo | prepare the song in its project, save, rebuild |
| Concert up to date | no song project changed since the build | **Fix** rebuilds the concert |
| ReaCue bridge | REAPER answers ReaCue | restart REAPER |
| Web interface | the prompter is served (port) | step 6 |
| Network address | the computer has an address (for the QR) | connect it to the band's Wi-Fi |
| Audio device | REAPER plays on an audio device | *Preferences → Audio → Device* |
| Click and cue outputs | the outputs chosen for CLICK / VOICE exist, tracks not muted | plug the right audio device or change `click_hw_output` (step 14) |
| Phones' prompter | the page and the concert are published | **Fix** republishes them |
| Stage control phones | a Stage control phone was seen recently | (information only) |
| Muted stems | the instruments muted (“played live” profile or by hand) | (information only) |

3. **Check again** runs the list again; **Close** (or Esc) goes back to the Stage tab.

> With no concert open, **Check** only covers the system part (bridge, web interface, address, audio
> device).

### 16.8 Instruments: muting a stem, “played live”

Below the sections, the Stage tab has an **Instruments (stems)** row: one button per instrument track of the
concert (Vocals, Drums, Bass, Guitars, Lead guitar, Keys, Other, Mix — never CLICK, VOICE or CUES). Under
each name: **playing** or **muted**.

| Gesture | Effect |
|---|---|
| **Click** | mute / unmute that stem (during playback outside rehearsal: **double tap**) |
| **Long press** | **solo**: only that one is heard (another long press = back) |
| **Hear everything** | unmutes all stems (again = back to the profile) |

These manual choices last until the next song.

**“Played live”: the concert's profile.** If the band really plays drums and bass, their stems must be muted
for the whole concert. Click **Played live…**:

<img src="images/window_live_en.png" width="420">

1. Tick what the band plays for real (e.g. **Drums**, **Bass**): those stems are muted at the start of every
   song.
2. **Per-song exceptions**: click a cell to turn it from **·** (profile) to **stem** (keep the stem on that
   song) then **live** (mute it on that song only). Example: the bass player switches to keys on one song →
   Bass cell of that song = **stem**.
3. **Close**.

The profile is saved with the concert (in `Saturday 15.setlist.json`) and **kept when you rebuild**. It is
also reachable from the Concert tab (**Played live…**). The rehearsal count-in bar does not overwrite your
choices.

On the phones, each musician sees at the top **“your stem is muted”** (orange) or **“your stem is playing”**
(green). In **Stage control**, the same buttons: tap = mute / unmute, long press = solo, **Hear everything**.

<img src="images/prompter_concert_en.png" width="200"> <img src="images/prompter_concert_vocals_en.png" width="200">

With Claude: “in the Saturday 15 concert, drums and bass are played live, except the bass on Second Demo”
(tool `set_live_profile`, no rebuild).

### 16.9 Lighting: grandMA3

At each preparation and each concert build, ReaCue writes one cue per section for a grandMA3 desk (folder
`grandMA3/` next to the project, or `Concerts/grandMA3/<concert>/`): one Sequence per song, one Timecode and
a cue sheet (CSV with a suggested effect per section).

1. On a phone or the lighting computer, open the prompter and choose the **Lighting** role: cue list,
   current cue highlighted, links to download the three files.
2. On the desk: import the Sequence, then the Timecode.
3. **REAPER sends the timecode** (MTC or LTC): the concert stops between songs, the desk follows.

**First setup (once).**

1. In the **Lighting** tab of the ReaCue window (or in `reacue_settings.json`), choose the output(s):
   - **console with LTC**: `"gma3_ltc_output": 7` (sound card output 7 → the desk's LTC XLR input);
   - **grandMA3 onPC on the same Mac**: `"gma3_mtc_output": "IAC Driver Bus 1"` (Audio MIDI Setup → Window →
     Show MIDI Studio → IAC Driver → tick *Device is online*);
   - **onPC on another computer**: `"gma3_mtc_output": "Network Session 1"` (Audio MIDI Setup → MIDI Network
     Setup: create a session, connect the PC; on Windows, rtpMIDI);
   - optionally `"gma3_tc_slot": 1`, `"gma3_tc_start": "01:00:00:00"`, `"gma3_fps": 25`.
2. REAPER: *Preferences → Audio → MIDI Devices*: enable that MIDI output (MTC only).
3. Prepare a song: tracks `TIMECODE LTC` / `TIMECODE MTC` appear. Double-click the generator item →
   *Source properties*: frame rate = `gma3_fps`, start = `gma3_tc_start`, *Send MIDI (MTC)* ticked on the
   MTC track only. OK, then **Prepare** again (or, Lighting tab, **Create / update the timecode tracks**):
   ReaCue remembers this for every song and concert. The **Lighting** tab chips turn green (LTC output, MIDI
   device enabled, tracks, generator set).
4. Desk: copy the contents of the export folder (`grandMA3/` next to the project, or
   `Concerts/grandMA3/<concert>/`) into `grandMA3/` at the root of a USB stick, import the plugin
   `ReaCue.xml` (Plugins pool → Import) and run it: Sequences, Timecode and TC Slot in one tap.
5. Desk input (once): *Menu → Output Configuration → Connector Configuration*: SMPTE Mode = In and SMPTE TC = slot
   (LTC), or MIDI TC Mode = In and MIDI TC = slot (MTC).

<img src="images/window_lighting_en.png" width="420">

Test: **Lighting** tab → **Send a 10 s test**: only the `TIMECODE` tracks play (the audience hears nothing),
then everything is restored; on the desk, the TC Slot turns green (LTC / MTC goes one way: ReaCue cannot
check it itself). Then play in REAPER → the desk's timecode runs and the cues fire; stop → the timecode show stops; play
again → it restarts. Useful settings: `gma3_song_slot` (e.g. `600`: each song starts on a round 10-minute
mark). Rebuild the concert after a change.

---

## 17. At rehearsal

### 17.1 The concert's rehearsal mode (loop and slow-down)

In an open concert, with the **ReaCue** window (**Stage** tab):

1. Click **Rehearsal** (or, on the Stage control phone, tap **Rehearsal**). An orange **REHEARSAL** banner
   appears; the automatic stop between songs is off.
2. **Loop a section**: tap its pill (in the window or on the phone). Playback starts **one bar before** the
   section: during that bar you only hear the **click and the spoken cues** (“one two three four”), then the
   section plays, and at its end it **starts again with the same count-in bar**, endlessly.
3. **Loop several sections**: tap a 2nd section of the same song (e.g. *Verse 2* then *Chorus 2*): the loop
   goes from the start of one to the end of the other. Looped sections are underlined in orange. A 3rd tap
   starts a single-section loop again.
4. **Slow down**: buttons **100 %**, **90 %**, **80 %**, **70 %**. The pitch does not change; the click, the
   cues and the prompter follow.
5. **Loop off** stops looping (playback goes on). **Exit** (in the window) or **Rehearsal ✓** (on the phone)
   leaves the mode: speed 100 %, automatic stop back on, REAPER settings restored.

> During the count-in bar, the instrument tracks are muted and then restored automatically. If you stop
> playback during that bar, they are restored too.

### 17.2 Rehearsing a single song (no concert)

Open the song's project; in the ReaCue window, **Stage** tab (“Single song”):

- **Start**, **Play**, **Stop**; the musicians hear (or see on the prompter) the count-in, then the cues
  before each section;
- the **section** pills: one click = go there;
- the **instruments** (mute, solo, hear everything), as in 16.8;
- **Rehearsal**: loop a section or a range, with the count-in bar before each repeat and the slow-down,
  exactly as in 17.1;
- **Stage control** on a phone works too.

There is no automatic stop and no setlist (a single song). Only REAPER (and the ReaCue window for the loop)
needs to run during rehearsal: Claude is not needed.

### 17.3 ReaCue Studio: the Practice screen

ReaCue Studio is a web page served by REAPER (like the prompter), made to work on a song on the computer or a
tablet.

1. Prepare the song (chapter 10): publishing also creates the stems' **waveforms**.
2. Open the **ReaCue** window in REAPER (it runs the loop, the ramp, transpose and export).
3. In the browser: **`http://localhost:8080/studio.html`** on the computer, or
   `http://<computer's IP>:8080/studio.html` on a tablet (the address is shown under the QR code).
4. The first time you use a loop, a ramp, transpose or export, the page asks for the **PIN** (ReaCue window,
   **Stage** tab): it is remembered on the device.

![ReaCue Studio, Practice screen](images/design_console_en.png)

| Area | What it does |
|---|---|
| Displays (top) | POSITION bar.beat.sixteenth · TIME · TEMPO and speed in % · KEY (± transpose) · SMPTE |
| Structure | click = go to the section; double-click = loop it (with the count-in bar, as in 17.1) |
| Chords | scroll under the play head; click = go to the chord |
| Stem rows | waveform (played part in colour), **M** (mute), **S** (solo), volume; click = go there |
| Console (right) | pan (drag; double-click = centre), meter, fader (double-click = 0 dB), CLICK and VOICE included |
| Footer | Start, Stop, Play/Pause (space bar), Loop, Next section; LOOP · RAMP · CLICK · VOICE; LEDs |
| My instrument | the chosen track is muted automatically (you play your part over the rest) |
| KEY − / + | transposes the stems by a semitone; double-click the KEY display = back to 0 |

**Speed ramp**: put the play head in the section to practise, click **RAMP**, set for example **from 85 % to
100 % over 8 passes**, then **START**. The section loops; at each repeat the speed goes up one step (pitch
kept); the counter shows “LOOP CHORUS 1 · 4/8”. After the last pass the loop goes on at the final speed.
**STOP** (or the Loop button) brings back 100 %.

> The **REAPER** LED is green when REAPER and the ReaCue window answer, orange when the window is closed
> (mute, volume, transport still work; loop, ramp, transpose and export do not). Transpose stays clean up to
> about ±2 semitones; beyond that, vocals and drums sound artificial. It changes the stem items: Ctrl/Cmd+Z
> in REAPER undoes it.

### 17.3.1 Stage view and precise controls

The **STAGE** button in Studio hides secondary controls and enlarges the live display. **EXIT STAGE**
restores the full view. This choice is remembered in that browser. The four-corner icon enters
**fullscreen** when supported by the browser; neither presentation control starts playback.

| Control | Mouse / touch | Keyboard after focusing with Tab |
|---|---|---|
| Volume fader | drag; double-click = 0 dB | ↑ / ↓: 1 dB; Shift: 0.1 dB; Home: 0 dB; End: −60 dB |
| Pan | drag; double-click = centre | ← / →: 5%; Shift: 1%; Home: centre |
| M / S | mute / solo; larger touch targets | Enter or Space on the button |

**CLIP** appears when REAPER reports a peak at or above 0 dB during playback. Reduce the level and
check the mix in REAPER. This indicates the received track peak, not a measurement of the whole audio
chain. **Space** follows the active screen (Practice, Show or Band); it no longer controls hidden
Practice transport from Library or Lights. It is ignored while typing, in a modal, on a slider,
or for repeated keydown events.

### 17.4 Export stems and ranges (WAV / MP3)

In ReaCue Studio, **EXPORT** button:

1. **Instruments**: tick the ones to export (ALL / NONE), and **with the click** if you want a click
   synthesised on the song's grid.
2. **Range**: whole song, a **section** (list), **bars** “from → to”, or **REAPER's time selection**.
3. **Files**: one file per instrument, or everything **mixed** into one file (brought down to -1 dBFS when it
   would clip: never any clipping; track volume and pan applied to the mix).
4. **Format**: **MP3** (128, 192, 256 or 320 kbit/s; 320 by default) or 24-bit **WAV**.
5. **EXPORT**: progress is shown, then the download links. The files are also in the **`exports/`** folder next
   to the project, named `<Title> - <Instrument> - <Section>.mp3`.

Examples: the bass alone in the chorus as an MP3 to revise on the bus; “everything but the guitar” mixed with
the click, bars 33 to 48, to practise your part; every stem as WAV for another program.


### 17.5 ReaCue Studio: the Show and Lights screens

On show night, `studio.html` also works as a **control desk** on the computer or a tablet.

1. Open the concert in REAPER (chapter 16) and the **ReaCue** window (it runs the commands).
2. In ReaCue Studio, click **SHOW** (or open `studio.html#concert` directly). The first time you press a
   command, enter the **PIN** (ReaCue window, Stage tab).

![ReaCue Studio, Show screen](images/design_concert_en.png)

| Area | What it does |
|---|---|
| Banner | LED + PLAYING / PAUSED / STOPPED, “SONG n / N”, title; LEFT (end of the song), SHOW (elapsed time), SMPTE · LTC |
| Setlist | one block per song (width = length): played greyed, current in orange; click = go to the song |
| Sections | start bar, name, PLAYED / NOW 3/16 / NEXT; click = go to the section |
| ◀ PREV · PLAY · NEXT ▶ | previous song (or start of the song), play / pause (space bar), next song |
| Lighting | the song's cues (number, timecode, section, effect), current cue highlighted, LTC / MTC / export LEDs, TEST 10 S |

While playing, **PREV**, **NEXT**, a setlist block and **TEST 10 S** need **two taps** (“AGAIN?”), like the
ReaCue window. With no concert open, the screen shows the single song (PREV / NEXT move between sections) with
a message.

3. Click **LIGHTS** (`studio.html#lumiere`) for the grandMA3 console:

![ReaCue Studio, Lights screen](images/studio_lumiere_en.png)

- **Current cue** in large type, then every cue (per song): click = go to the cue.
- **Timecode outputs**: LTC output, MTC device, TC Slot, fps and start (Lighting tab settings at export time);
  **EXPORT UP TO DATE** LED (otherwise: *Export now* in the Lighting tab).
- **TEST 10 S**: only the TIMECODE tracks play for 10 s (the audience hears nothing), then everything is
  restored; the button shows the countdown, a 2nd tap stops. Check on the console that the TC Slot turns green.
- **grandMA3 files**: download the Sequences, the Timecode and the cue sheet.

> The effects shown are the suggestions per section type (read-only); editing them comes in a later version.

### 17.5.1 Stage view for show control

Click **STAGE** to put the song, remaining time and lighting cues first, as in the screenshot above.
**EXIT STAGE** restores the tabs without stopping playback. Setlist and Previous/Next protections
remain active; Stage view does not grant additional commands. To select a section with the keyboard,
Tab to its row, then press Enter or Space.

### 17.6 ReaCue Studio: the Library and Band screens

**Library** (`studio.html#biblio`): the list of all your songs (projects folder + shows).

![ReaCue Studio, Library screen](images/studio_biblio_en.png)

1. Open the **ReaCue** window in REAPER (it publishes the library and runs the commands).
2. In ReaCue Studio, click **LIBRARY**. Filter by stage (counters at the top) or search a title.
3. Click a song: it opens in REAPER (new tab) and the screen switches to **PRACTICE**. A song “TO PREPARE” also
   opens, but prepare it first (Song tab of the window).
4. **STAGE** column: computed by itself (AUTO) from the time played alone or as a band; click a box to set it by
   hand (MANUAL), “auto” to go back to the computation.

| Stage | Automatic computation |
|---|---|
| Discovered | nothing measured |
| Practised alone | 5 min of playback |
| Rehearsed as a band | 3 min of playback with at least 2 musicians' prompters connected |
| Ready for the stage | prepared + rehearsed as a band on 2 days (at least 2 min each day) |

**Band** (`studio.html#groupe`): the rehearsal screen.

![ReaCue Studio, Band screen](images/studio_groupe_en.png)

1. Each musician opens the prompter on their phone, picks their role and may type their first name.
2. **Notes**: type “stop on 4” next to the section, Enter: the note shows in pink on every prompter (2–3 s).
3. **Ready**: everyone taps “Ready?” at the top of the prompter; the Band screen shows “READY 3 / 4” and who is
   missing. **RESET** before the next song.
4. **Take it from…**: click “Chorus 2”: playback restarts one bar before.

> Connected musicians, notes and manual stage go through the ReaCue window: keep it open.

---

## 18. Troubleshooting

| Symptom | Likely cause | Solution |
|---|---|---|
| The item shows **OFFLINE** (Mac) | REAPER is not allowed to read the file, often in *Downloads* | Copy the file into the project folder, then drag it into REAPER again (or right-click the item → *Item properties…* → *Choose new file*). Alternatively: *System Settings → Privacy & Security → Files and Folders → REAPER*, enable the folder, restart REAPER |
| “The ReaCue bridge is not running” | The bridge did not start | Restart REAPER; a dialog left open in REAPER can also block it |
| The prompter says “REAPER is not responding” | Wrong Wi-Fi, wrong address, web interface not enabled, firewall | Check step 6 and step 13; try `http://localhost:8080/` on the computer |
| The phones cannot find the page any more | The computer's IP address changed | New address (step 13), then a DHCP reservation |
| No spoken cues | Voice missing | Mac: *System Settings → Accessibility → Spoken Content*; Windows: *Settings → Time & language → Speech* |
| Stem separation very slow | Busy processor | Close other applications; count 1.5 to 2 times the song length |
| Wrong structure | Automatic detection is not perfect | Step 11: structure band (orange boxes), fix then *Apply*, or ask Claude; wrong tempo: tempo in the file names |
| “Structure: ReaCue” pill in orange | SongFormer is not installed | Click the pill → installer; or *Settings → Check the installation* |
| Summary: “Chord model unavailable…”, “Drum transcription by model (ADTOF) failed…”, “Word-by-word timing failed…” | Optional component missing, broken or too slow | Nothing is lost: ReaCue used its own method. Run the component's installer again ([chapter 20](#20-optional-components)); after a chord failure, ReaCue does not retry on the same audio for 1 h |
| No `paroles (auto).txt` | No vocal stem, Whisper not installed, `lyrics_auto` = `"off"`, or you already have a lyrics file | Split the stems, run `Install ReaCue Words` again; a failure is remembered for that song (no new attempt at every publication) |
| No PDF chart | The song's folder was not found, or writing failed (warning “PDF chart not created”) | Click the **PDF chart —** pill; check that the song's folder exists and is not read-only |
| Stage tab: “No concert or song open” | The current project tab is empty | **Concert** tab → **Open** a concert, or open a song's project |
| A song of the concert has no sections | Its project was saved before the preparation | Open its project, *Do everything*, then *Rebuild the concert* |
| Phone (Stage control): “Open the ReaCue window…” | ReaCue window closed | Run the **ReaCue** action on the computer |
| Stage control: “Wrong PIN code” | Wrong code | Type the code shown by the **PIN** button of the Stage tab |
| Playback no longer stops between songs | ReaCue window closed, or rehearsal mode on | Open **ReaCue** again (even docked); otherwise **Exit** rehearsal |
| A stem stays muted | “Played live” profile or a manual choice | Stage tab: **Hear everything**, or **Played live…** to change the profile |
| **Check** shows red | See the line concerned | Table of step 16.7; **Fix** when the button is offered |
| After a rehearsal, some tracks stay muted | REAPER was closed during the count-in bar | Unmute the tracks (**M** button); the window normally restores them by itself |
| Logs | — | Preparation: `ReaCueMCP/cli.log` (REAPER resource folder); separation: `…-stems/demucs.log` next to the song |

---

## 19. Cheat sheet: a new song, a concert

1. **ReaCue** window → **+ New song** → one file **or** a folder of stems → title → **OK** (copied to
   `Documents/REAPER Media/<Title>/`, new tab, project saved).
2. **Do everything** (stems for a single MP3, structure, click, cues, phones, save).
3. Check the structure (orange boxes of the band, names); if needed **Rename** / **◀ ▶** / **Merge** /
   **Split** / **Delete** / **+ Section** (**Undo** if needed), then **Apply**.
4. Optional: `lyrics.txt` next to the files → **Update the phones** (no file, with Whisper installed: correct
   the draft `paroles (auto).txt`). The chart `Chart - <Title>.pdf` is in the song's folder.
5. Several songs: **Concert** tab → **Prepare all songs not prepared**.
6. Phones: `http://<IP>:8080/prompteur.html`, pick your role.

**A concert:**

1. Each song prepared **and saved** in its own project.
2. **Concert** tab: **+** on each song, **Rename**, **Build** (or Claude: “Build a concert “Saturday” with: …”).
3. The concert opens in a new tab; the window switches to **Stage**.
4. Optional: **Played live…** → tick what the band plays for real.
5. **Check** → everything should be green (otherwise **Fix**).
6. **QR** → the musicians scan it; the person in charge picks **Stage control** and types the PIN.
7. **Space** for each song; playback stops by itself at the end of each one.
8. At rehearsal: **Rehearsal**, then a section to loop it (2nd section = range), speed if needed.

---

## 20. Optional components

ReaCue works on its own. Each optional component improves one part of the analysis, **runs on your
computer** (nothing is uploaded, internet only during its installation), installs into its **own Python
environment** inside the `ReaCue` folder (ReaCue's `.venv` is never touched), and can be installed, run again
or removed at any time.

| Component | Installer | What it brings | Download | Installation | Computing per song (Intel Mac, once) | Licence |
|---|---|---|---|---|---|---|
| Stem separation | `Install ReaCue Stems` (or the question in step 4) | one MP3 → 6 stems (Demucs) | ≈ 1 GB | 5 to 15 min | 5 to 8 min | MIT |
| Structure analysis | `Install ReaCue Structure` (or the question in step 4, yes by default) | more accurate sections (SongFormer) | ≈ 3 GB | 10 to 40 min | several minutes | **non-commercial** (MuQ: CC BY-NC 4.0); “I accept” |
| Chords | `Install ReaCue Chords` | chords by a trained model | ≈ 800 MB (PyTorch, already cached if stems are installed) + 60 MB | 2 to 10 min | 1 to 2 min | MIT |
| Drums | `Install ReaCue Drums` | ADTOF transcription of the drum stem | ≈ 300 MB (PyTorch, same) + 16 MB | 3 to 10 min | 20 to 60 s | **non-commercial** (CC BY-NC-SA 4.0); “I accept” |
| Word-by-word and automatic lyrics | `Install ReaCue Words` | each word at its real moment; lyrics draft by Whisper | ≈ 1 GB (PyTorch, nothing if stems are installed) + 1.3 GB per language (French, English) + 1.6 GB (Whisper) | several minutes (≈ 5 GB in all, depending on the connection) | 1 to 3 min (word by word), about 3 to 6 min (Whisper) | Apache-2.0 (wav2vec2), MIT (Whisper) |

**To install**: ReaCue first (step 4), then double-click the installer in the `ReaCue` folder (Mac:
`.command`; Windows: `.bat`), language `en`, then follow the window. On a Mac, the first time, same trick as in
step 4 if macOS blocks the file (right-click → **Open**). Each installer ends with a short test (e.g.
`CHORDS_OK`, `WORDS_OK`, `STRUCTURE_OK`); if it fails it says why, and **running it again resumes where it
stopped**. REAPER may stay open: the component is used from the next preparation on (*Prepare again* or
*Update the phones* for a song already ready).

**Automatic fallback, always.** If a component is not installed, is turned off by its setting, fails or
exceeds its time limit, ReaCue uses its own method and says so in the *Summary*: the preparation is never
blocked.

**Licences.** The models are not in the repository: each installer downloads them from their authors, at a
pinned version. Two components are for **non-commercial use only** (structure analysis, drums): their
installer shows the licence summary and installs nothing until you type exactly **`I accept`** (remembered,
not asked again on updates). Details: [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) (this is not legal
advice).

### 20.1 Stem separation (Demucs)

- **Brings**: a single MP3/WAV becomes six stems (Vocals, Drums, Bass, Guitar, Piano, Other), which gives the
  drum view, per-instrument entries, better chords and the vocal stem needed for lyrics. How to use it:
  [step 9](#9-split-an-mp3-into-stems).
- **Installs**: `.venv-demucs`; Demucs models in PyTorch's cache (`~/.cache/torch/hub/checkpoints`). The
  installer measures your computer's speed.
- **Setting**: `stems_model` = `"htdemucs_6s"` (6 stems, default) or `"htdemucs"` (4 stems; guitar and keys
  stay in “other”). *Settings* tab → *Stem separation*.
- **Without it**: prepare the song straight from the MP3 (less detail), or provide your own stems.

### 20.2 Structure analysis (SongFormer)

- **Brings**: more accurate section boundaries and names. ReaCue keeps its grid (tempo, bars, count-in):
  SongFormer only says where the sections are and what they are, each boundary is snapped to the nearest bar;
  the orange boxes of the Song tab flag the doubts ([step 11](#11-check-the-structure)).
- **Installs**: `.venv-structure` and `structure/` (SongFormer, MuQ, MusicFM). Models already on the computer
  (Hugging Face cache, another copy of SongFormer) are reused instead of downloaded again.
- **Memory**: 8 GB of RAM recommended; with 15 GB or more the model looks at the song in 420 s windows (more
  accurate), otherwise 120 s.
- **Setting**: *Settings* tab → *Structure detection*: **auto (SongFormer)** or **ReaCue only**
  (`structure_engine`). Result remembered per song (`.reacue/` next to the audio).
- **Fallback**: not installed or “ReaCue only” → ReaCue's detection (pill **Structure: ReaCue**); error or more
  than 30 min → “SongFormer analysis failed: … → ReaCue structure used”.
- Installation without questions (licence agreement): variable `REACUE_STRUCTURE_ACCEPT=yes`.

### 20.3 Chords by a trained model

- **Brings**: more accurate chords for the prompter and the PDF chart (major / minor, 7th, maj7, m7, sus, dim,
  aug, inversions like `D/F#`). Model by Jiang et al. (ISMIR 2019, Music X Lab), **code and weights under the
  MIT licence**.
- **How**: it listens to the stems **without vocals or drums** (otherwise the single file), follows the beats
  of ReaCue's grid (at most two chords per bar, `N.C.` when nothing plays), spells sharps / flats from the
  key; 9ths, 11ths and 13ths are shown as the matching 7th (`G9` → `G7`).
- **Installs**: `.venv-chords` and `chords/model` (≈ 60 MB, pinned version from GitHub).
- **Setting**: `chords_engine` = `"auto"` (the model when installed, default) or `"reacue"`.
- **Fallback**: not installed, `"reacue"`, error or more than 10 min → ReaCue's detection (“Chord model
  unavailable: …”); after a failure, no new attempt on the same audio for 1 h. The result is remembered in the
  song's `.reacue` folder (a grid change only re-runs the decoding).
- **Compare** on your songs: `.venv/bin/python tools/compare_chords.py <song folder or audio file>` (Windows:
  `.venv\Scripts\python tools\compare_chords.py …`), which prints both charts bar by bar and how often they
  agree.

### 20.4 Drums by a trained model (ADTOF)

- **Brings**: a much more reliable **Drums** view of the prompter on snare and cymbals. ADTOF (M. Zehren et
  al.) is trained on 359 hours of real music; ReaCue then tells high / mid / floor tom, closed / **open**
  hi-hat (lane **Open hi-hat**, `HO`), crash or ride per section, and snaps each hit to its grid in
  **sixteenths**, or **triplets** for a shuffle song (chosen per song). Same patterns, fills and crashes as
  before, more accurate.
- **Needs** a drum stem (stems you provide, or stem separation).
- **Licence**: ADTOF weights under **CC BY-NC-SA 4.0** (non-commercial); the PyTorch port used (ADTOF-pytorch)
  states no licence. The installer asks you to type **`I accept`** (`J'accepte` in French); otherwise nothing
  is downloaded. Installation without questions: `REACUE_DRUMS_ACCEPT=yes`.
- **Installs**: `.venv-drums` and `drums/` (code and weights, 16 MB, pinned version).
- **Setting**: `drums_engine` = `"auto"` (ADTOF when installed, default) or `"reacue"` (ReaCue's rules).
- **Fallback**: not installed, `"reacue"`, error or more than 15 min → ReaCue's rules (“Drum transcription by
  model (ADTOF) failed: … → ReaCue method used”). Result remembered next to the stem, in `.reacue/`.
- **Compare**: `.venv/bin/python tools/compare_drums.py <drum stem>`.

### 20.5 Word-by-word lyrics and automatic lyrics

A single installer, **`Install ReaCue Words`**, installs both (environment `.venv-words`, models in `words/`).
Running it again on an existing installation only adds what is missing.

**Word-by-word lyrics** (wav2vec2 XLSR-53 fine-tuned in French and English by J. Grosman, Apache-2.0):

- **Brings**: each word of **your** lyrics placed at its real moment on the vocal stem, inside the lines
  already timed (line timing and `lyrics_timing.json` remain the anchor). Vocals prompter: current word
  highlighted, sung words dimmed; PDF chart: each word in its bar.
- **Language**: guessed from the lyrics text; `words_language` = `"fr"` or `"en"` to force it. A single model
  language at installation: variable `REACUE_WORDS_LANGS=en` (or `fr`).
- **Setting**: `words_engine` = `"auto"` (default) or `"off"` (lines only).
- **Fallback**: error or more than 15 min → lyrics timed by line (“Word-by-word timing failed: …”); a badly
  recognised line keeps its line timing.
- **Compare**: `.venv/bin/python tools/compare_words.py` (last prepared song) shows the positions before /
  after without ever printing the text.

**Automatic lyrics** (OpenAI's Whisper `large-v3-turbo`, code and weights MIT, ≈ 1.6 GB in `words/whisper/`):

- **Brings**: without a lyrics file, a draft **`paroles (auto).txt`** in the song's folder, transcribed from
  the vocal stem, then timed like a normal file (by line, then word by word). Rules and orange pill:
  [step 12](#12-add-the-lyrics).
- **Against made-up text**: only the parts where the voice sings are transcribed; looping repetitions and
  typical captions are removed; one line per sung phrase, an empty line between two blocks.
- **Setting**: `lyrics_auto` = `"auto"` (default) or `"off"`; language detected, or forced by
  `words_language`. Installation without Whisper: variable `REACUE_WHISPER=0`.
- **Fallback**: error, no singing recognised or more than 20 min → no lyrics, as before; the failure is
  remembered for that song (no new attempt at every publication).
- **Try it by hand**: `.venv/bin/python tools/transcribe_lyrics.py` (last prepared song) prints statistics
  only, never the text; `--write` writes the draft if there is none.

### 20.6 Removing a component

- **Put it aside without deleting anything**: its setting (`structure_engine` / `chords_engine` /
  `drums_engine` = `"reacue"`, `words_engine` / `lyrics_auto` = `"off"`), then *Prepare again*.
- **Delete it**: delete its folders inside the `ReaCue` folder (`.venv-demucs`; `.venv-structure` and
  `structure`; `.venv-chords` and `chords`; `.venv-drums` and `drums`; `.venv-words` and `words`). ReaCue goes
  back to its own method automatically. The Demucs models stay in PyTorch's cache
  (`~/.cache/torch/hub/checkpoints`, a few hundred MB): delete them too if you like.
- **Uninstall everything**: double-click `Uninstall ReaCue.command` / `.bat`, REAPER closed (scripts, actions,
  bridge start-up, Claude Desktop entry). Run with `--purge`, the script also deletes your settings,
  `.venv-demucs`, `.venv-structure` and `structure`. Then delete the `ReaCue` folder: all components go with
  it. Your songs, stems, lyrics and PDF charts stay next to your projects.

---

## 21. Appendix: all settings

File **`reacue_settings.json`**, in the `ReaCueMCP` folder of REAPER's resources (menu *Options → Show REAPER
resource path in explorer/finder*). The **Settings** and **Lighting** tabs write it for you; you can also edit
it (TextEdit as plain text, Notepad), keeping the JSON syntax. A missing key takes its default value; an
unknown key is ignored. Changes apply at the next preparation (*Prepare again*, *Rebuild the concert*).

| Key | Default | Role | Where to set it |
|---|---|---|---|
| `performance_profile` | `"standard"` | `"standard"` or `"fast"`: explicit compute/quality tradeoff | Advanced settings |
| `cpu_threads` | `0` | `0` = auto; otherwise PyTorch threads, capped at logical CPU count | Advanced settings / Mac calibration |
| `language` | `"fr"` | `"fr"` or `"en"`: region names, spoken cues, prompter, messages | Settings |
| `count_in_bars` | `2` | bars of click before bar 1 | Settings |
| `cue_lead_bars` | `2` | spoken cue N bars before the section (2 = second-to-last bar) | Advanced settings |
| `voice_cues` | `true` | spoken section cues (“Chorus”) | Settings |
| `voice_count_in` | `true` | “one two three four” on the last bar of the count-in | Settings |
| `voice_count_each` | `true` | “one two three four” on the last bar of each section | file |
| `count_lang` | `"en"` | count language: `"en"` (one two…) or `"fr"` (un deux…) | Advanced settings |
| `announce_voice` | `null` | system voice for the cues; `null` = automatic | Settings |
| `count_voice` | `null` | count voice; `null` = automatic | Advanced settings |
| `count_rate` | `240` | count speed (words per minute) | Advanced settings |
| `voice_volume` | `0.8` | volume of the VOICE track | Advanced settings |
| `click_volume` | `0.5` | volume of the CLICK track | Advanced settings |
| `click_to_master` | `true` | `false` = click and voice only on `click_hw_output` (in-ears), not front of house | Settings |
| `click_hw_output` | `null` | hardware output for click and voice: `0` = 1/2, `2` = 3/4…; `null` = none | Settings |
| `tempo_mode` | `"auto"` | `"auto"`, `"constant"` (fixed tempo) or `"beatmap"` (one tempo per bar) | Advanced settings |
| `stems_model` | `"htdemucs_6s"` | separation: `"htdemucs_6s"` (6 stems) or `"htdemucs"` (4 stems) | Advanced settings |
| `structure_engine` | `"auto"` | sections: `"auto"` (SongFormer when installed) or `"reacue"` | Settings |
| `chords_engine` | `"auto"` | chords: `"auto"` (model when installed) or `"reacue"` | file |
| `drums_engine` | `"auto"` | drums: `"auto"` (ADTOF when installed) or `"reacue"` | file |
| `words_engine` | `"auto"` | lyrics: `"auto"` (word by word when installed) or `"off"` (lines only) | file |
| `words_language` | `"auto"` | sung language (word by word, Whisper): `"auto"`, `"fr"` or `"en"` | file |
| `lyrics_auto` | `"auto"` | without a lyrics file: `"auto"` (Whisper draft when installed) or `"off"` | file |
| `projects_dir` | `null` | folder of the songs' projects; `null` = `<Documents>/REAPER Media` | Advanced settings |
| `concert_dir` | `null` | folder of the concerts; `null` = `<projects folder>/Concerts` | Advanced settings |
| `gma3_export` | `true` | write the grandMA3 files at each preparation / concert build | Lighting |
| `gma3_fps` | `25` | timecode frames per second (24, 25, 29.97, 30) | Lighting |
| `gma3_tc_start` | `"00:00:00:00"` | timecode of the start of the project (e.g. `"01:00:00:00"`) | Lighting |
| `gma3_song_gap` | `null` | concert: minimum gap between two songs (s); `null` = the setlist's (4 s) | Lighting |
| `gma3_song_slot` | `0` | concert: each song starts at the next multiple of this time (s, e.g. `600`); `0` = off | Lighting |
| `gma3_ltc_output` | `null` | `TIMECODE LTC` track: audio output (`7`, or `"7/8"` for a pair); `null` = no track | Lighting |
| `gma3_mtc_output` | `null` | `TIMECODE MTC` track: MIDI device name (`"IAC Driver Bus 1"`…); `null` = no track | Lighting |
| `gma3_tc_slot` | `1` | grandMA3 TC Slot (1 to 8) set by the ReaCue plugin | Lighting |

The **Stage control PIN code** is not in this file: REAPER keeps it, and you change it with the **PIN** button
of the Stage tab (or in *Advanced settings*).
