# BandStudio

**Your song. Your way.** Local song preparation for every musician.

[💬 Discord · help & community](https://discord.gg/5UnQPdMUpR) · [Website](https://herve8940.github.io/BandStudio/en.html) · [Downloads](https://github.com/herve8940/BandStudio/releases/latest) · [Tutorial](docs/BANDSTUDIO_TUTORIAL_en.md) · [Français](README.md) · [Report a bug](https://github.com/herve8940/BandStudio/issues/new/choose)

BandStudio is free software for local stem separation and song practice: adjust tempo, work on chords and synchronized lyrics, then export the project and its media to REAPER. Vocals, guitar, bass, keyboards and drums share the same instrument selector, solo and backing-track controls.

- Local 4/6-stem separation, mixing and optional drum/vocal sub-stems.
- Tempo and key detection, speed adjustment, pitch shifting, loops and count-ins.
- Editable sections, chords, synchronized lyrics, cues and spoken guides.
- Audio, separate stems, LRC/SRT lyrics, PDF charts, drum MIDI and portable REAPER exports.
- Local rotating diagnostics and a user-reviewed GitHub bug reporting flow.
- Verified main-channel updates, downloaded in the background and applied after exit with file backups.

**Windows:** extract the complete ZIP and run `BandStudio.exe`. Python is included; WebView2 is required. Optional models are installed separately. **macOS:** native app for an existing prepared local runtime; initial source installation is described in the [guide](docs/BANDSTUDIO.md#macos). A complete new-machine macOS installer is not yet distributed.

Windows packaging, speech, WebView2 and offline audio are exercised in CI; actual audio devices and optional AI engines still need hardware testing. AI output needs musical review. Specialized separation models and cloud services from commercial products are not all reproduced.

**[BandPilot](https://herve8940.github.io/BandPilot/en.html)** complements BandStudio with mixer control, guided sound checks and rehearsals. Both applications work independently; REAPER receives the prepared music.

BandStudio grew from ReaCue. The [legacy REAPER documentation](README_REACUE.md) remains available. Code: [MIT](LICENSE). Optional models retain their own terms, including noncommercial restrictions for some structure/drum components: [third-party notices](THIRD_PARTY_NOTICES.md).

## What’s new on 23 November 2026

- **Écouter et corriger** opens after preparation. Use **Écoute ciblée** to hear a flagged word, chord or section and adjust its timing.
- Lyrics lookup tries the full title, a shortened title and several catalogues. BandStudio times words against the vocals in your recording and flags uncertain placements.
- In **Accords**, compare charts and choose one for your arrangement. Both the song sheet and teleprompter use your capo setting.
- The PDF sheet, count-in and REAPER project share the same beat grid. The sheet shows a pickup on the beat where the section actually begins.

![Targeted listening in BandStudio’s song editor with a demo song](site/assets/editor-review.jpg)

[From import to REAPER](https://herve8940.github.io/BandStudio/tutorial.html) · [From lyrics to a printable PDF](https://herve8940.github.io/BandStudio/song-sheet.html) · [Written guide](docs/BANDSTUDIO_TUTORIAL_en.md) · [Release notes FR / EN](docs/RELEASE_2026-11-23.md).

## Community & support

Join the [BandStudio Discord](https://discord.gg/5UnQPdMUpR), a separate server from BandPilot: help, getting started, news, bugs and ideas in French and English.

In **Aide & Discord**, describe the issue, optionally include the compact diagnostics, then copy the report and open Discord. Paste and send it in `#rapports-de-bugs`. No audio, project or raw log is attached. You can export, review and attach a detailed diagnostic file yourself. [Support](SUPPORT.md).
