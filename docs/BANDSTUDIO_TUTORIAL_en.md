# BandStudio · preparation and editing tutorial

[Français](BANDSTUDIO_TUTORIEL_fr.md) · [Installation guide](BANDSTUDIO.md) · [Website](https://herve8940.github.io/BandStudio/en.html)

Updated 21 November 2026. This tutorial covers the standalone BandStudio app on macOS and Windows. Button names below match the French labels currently displayed in the app.

## 1. Import and prepare

Open an audio file from your computer. For several songs, use **Préparer une série**, add the files and click **Démarrer la file**. The queue never starts by itself after opening the app.

In **Pistes & structure**, click **Tout préparer** (Prepare all). Installed engines process instruments, detailed drums, lead/backing vocals, tempo, sections, key and lyrics. Final review looks up online chord charts, compares stems and references, and saves automatic improvements before generating the click and spoken guides. Missing engines can be installed under **Réglages → Analyses locales**. **Préparation détaillée** lets you rerun an individual step.

The result shows **Ton morceau, préparé** with **Avant / Préparée** (Before / Prepared) timelines. Select a change to see its details, **Cadrer le changement** to zoom both timelines, and **Écouter ce passage** to audition the entrance. Completed work is reused after interruptions or a second click; protected edits remain intact. Automatic preparation does not mark a human listening check as completed. Uncertain passages remain flagged. **Exporter le morceau** opens final validation in **Projet REAPER**.

On import, BandStudio attempts to calibrate the grid before preparing the guides. Timing settings from another song are reset. A status saying “à vérifier” means you still need to listen, especially to confirm the first downbeat.

## 2. Check the downbeat and count-in

Open **Click & repères** and listen to the beginning with the metronome. Check the first beat, beats per bar and grid mode: detected keeps the song’s timing variations; fixed imposes a constant tempo. Adjust the settings if beat one is misplaced.

The count-in follows the saved grid, including tempo changes. It can overlap the initial silence and accompany a pickup without cutting the song’s audio. Also check a restart in the middle of the song. If an automatic intro has been aligned, listen to its entrance; manually edited or reviewed sections remain protected.

New analyses repair isolated weak or doubled opening detections when a stable rhythm follows. This applies across compatible songs. Listen at the beginning, middle and end: a constant offset suggests checking the first downbeat; growing drift suggests checking tempo or the grid. Avoid imposing a fixed tempo on a recording that varies. Once the grid sounds right, enable **Protéger le calage contre une nouvelle analyse**. An update does not overwrite a protected grid.

## 3. Adjust sections and cues

In **Pistes & structure**, choose **Pistes** for mixing or **Structure** for the section list. Structure shows start/end positions, length and review status; **Modifier** opens a section and **↻** loops it. Use the coloured overview to jump to a passage.

Search filters the current view. In Pistes, filter instruments, original audio or guides; **Compact** reduces track height and **Masquer l’inspecteur** gives the timeline more room. These controls do not change the mix.

To refine a marker:

1. Use **＋**, **−** and **Tout** to zoom. **Sélection** (**F**) fits the selected section; **L** toggles looping and **Alt + ← / →** navigates markers outside text fields. **Parcourir le morceau** moves the visible window; **Suivre la lecture** follows playback.
2. Choose **Mesure** (bar) or **Temps** (beat) snapping, then drag a section boundary or cue. You can also use the **−1 mesure**, **+1 mesure**, **−1 temps** and **+1 temps** buttons in **Un repère à la fois**.
3. Click **Écouter autour** to hear the announcement and entrance. Click the marker’s name to edit it.
4. Click **Valider et suivant** to review the next marker. The counter shows progress. Moving a marker clears its reviewed status.

Shared boundaries keep adjoining sections continuous. Changes are saved with the song and support undo/redo. Reviewing individual markers does not replace the final review before REAPER export.

### Use “Vérifier et compléter”

In the same **Pistes & structure** screen, click **Vérifier et compléter** to compare available references with the audio and existing markers. Missing preparation steps may take time. Suggested sections and chords replace the current preparation only after approval.

1. Compare **Actuelle / Proposée** (Current / Proposed) and expand **Sources consultées** if needed. Unlike the completed Prepare all workflow, this proposal waits for **Appliquer au projet** or explicit validation/export. A chord chart may be available even when timed DRUMY markers cannot be retrieved. An untimed section list does not locate those sections in your recording.
2. Click **Écouter les passages** when excerpts are available. Check chords, timing and suggested entrances. “0 passages à écouter” does not certify the whole song; also listen to the mix, grid and guides.
3. Choose **Garder le parcours actuel** to keep your preparation. Once the proposal and final listening check are satisfactory, **Valider et exporter vers REAPER** applies the proposal and creates the project in one action. Use **Afficher l’export** to locate the `.rpp` file.

**Aucune amélioration proposée — préparation actuelle conservée** means no change was proposed. The button becomes **Exporter la préparation actuelle vers REAPER**. Recalled preparations for the same recording also require approval before export. This assistance does not mark every individual marker as listened to; the classic workflow remains available.

Compatible new SongFormer analyses receive a learned fine timing adjustment: at most 250 ms, with abstention when the learned proposals disagree. It does not rename sections or insert missing transitions. Manual and reviewed sections remain protected. Activation requires verified weights, a 60-second analysis window and a 2–10-minute recording; other configurations keep the original proposals. This corrects section boundaries, not tempo or spoken-cue anticipation. [Evaluation and protocol (FR)](CUE_CORRECTOR_TRAINING.md#résultats-du-lot-réservé-et-distribution).

## 4. Balance the guides

The **Métronome**, **Appels de régions**, **Cues** and **Décompte des régions** tracks have **M** (mute), **S** (solo) and volume controls like the instruments. **Mix des guides** groups their settings. Solo respects the other tracks and count-in voices. Changing levels or marking a cue as reviewed does not rerun AI analysis or rebuild guides. Moving a marker may require guide regeneration. Use **Réduire le menu** to collapse the left navigation and **Afficher le menu** to restore it.

## 5. Edit the song sheet

[Visual song sheet → PDF tutorial](https://herve8940.github.io/BandStudio/song-sheet.html) · [Visual preparation tutorial](https://herve8940.github.io/BandStudio/tutorial.html)

Open **Fiche morceau**. The sheet brings together song identity, available artwork, tempo, key, sections, chords and lyrics, bar by bar. Select a passage from the list; click a bar or section title to move the listening cursor.

- Click a chord or lyric line to edit its text and timing. **Détails** shows additional position information.
- Use the start/end bar and beat fields, nudge buttons or **Placer au curseur**. Moving a lyric line preserves the relative timing of its synchronized words.
- **+ Accord** and **+ Paroles** add annotations. Replacing chords over a selected interval preserves their portions outside that interval.
- **Importer des paroles** uses your own file. **Annuler** and **Rétablir** undo and redo edits.
- Search for an Internet chord chart in **Préparation détaillée** or **Paroles & accords**, after checking the song title and artist. Found sources stay separate: **Ouvrir la grille** opens the original page; **Utiliser cette grille** selects it for alignment. Internet access is required and some publishers may be unavailable.
- Chords from the chosen source are proposed on the song’s beat grid. Listen and correct their placement; proposals do not guarantee the right arrangement or chord. **Caler sur le temps / contretemps** helps place a change. Manual edits remain protected.
- **Tout préparer** also looks up free lyric references without an account, corrects sufficiently supported words and aligns them locally to the vocal audio. To rerun it, use **Paroles & accords → Corriger ou importer les paroles → Corriger avec Internet et recaler**. Incompatible references, insufficient alignment and manual lines keep the previous text. **Autres sources sur Internet** remains a supplementary browser search.
- Automatic chord selection prioritizes agreement with your recording. Published song ratings are only a secondary criterion when available; an explicitly selected chart is retained.

If no chart is found, check that the artist is the musician or band, rather than a video uploader, then retry. BandStudio removes labels such as “HD Video” and recognizes several artist/title separators. For partial results, a new search after five minutes retries missing sources while retaining available charts. **Référence non récupérée** means that particular source could not be accessed; it does not mean there are no chords anywhere online. Always check that the chart matches your recording’s version.

The sheet edits the open song’s existing annotations. Estimated chords and transcription still need listening checks. A lyric line without word timing remains whole at its starting position.

## 6. Export the PDF and project

Click **Exporter la fiche PDF**. The printable chart includes sections, bars, chords, lyrics, cues and notes. It follows the saved grid, transposition and capo for displayed chords. Choose a filename and destination for the copy; the PDF then opens in your system viewer. Cancelling the copy keeps the generated PDF in the song’s **Exports** folder. **Afficher l’export** helps locate it if automatic opening fails.

For the classic workflow, use **Valider & envoyer** to listen and confirm the mix, grid and guides, then export to REAPER. If you used **Valider et exporter vers REAPER** in the structure assistant, the export already exists: find it with **Afficher l’export**. Keep the `.rpp` and its **Audio** folder together. Export again to apply corrections to an older REAPER project.

## Update or get help

Use **Vérifier maintenant** in **Réglages**. With automatic updates enabled, the verified package is applied after exit. Windows packages and macOS updates are published only after the GitHub checks pass.

On **Windows x64**, extract the entire ZIP before opening `BandStudio.exe`; WebView2 is required. On **macOS Intel or Apple Silicon**, update archives are for prepared installations; new users should follow the [installation guide](BANDSTUDIO.md#macos). After updating, retry chord searches in older projects with missing sources. Manual edits and protected grids are preserved.

Still hearing a timing issue? In **Aide & Discord**, describe the passage, tempo and expected behavior. Review the report before posting it in the bug channel. [Join the community](https://discord.gg/5UnQPdMUpR).
