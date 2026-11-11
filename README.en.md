# BandStudio

**Your song. Your way.** Local song preparation for every musician.

[Website](https://herve8940.github.io/BandStudio/en.html) · [Downloads](https://github.com/herve8940/BandStudio/releases/tag/bandstudio-main) · [Français](README.md) · [Report a bug](https://github.com/herve8940/BandStudio/issues/new/choose)

BandStudio is free software for local stem separation and song practice: adjust tempo, work on chords and synchronized lyrics, then export a reviewed project to REAPER. Vocals, guitar, bass, keyboards and drums share the same instrument selector, solo and backing-track controls.

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
