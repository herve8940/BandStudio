# BandStudio · preparation and editing tutorial

[Français](BANDSTUDIO_TUTORIEL_fr.md) · [Installation guide](BANDSTUDIO.md) · [Website](https://herve8940.github.io/BandStudio/en.html)

Updated 15 November 2026. This tutorial covers the standalone BandStudio app on macOS and Windows. Button names below match the French labels currently displayed in the app.

## 1. Import and prepare

Open an audio file from your computer. For several songs, use **File de préparation**, add the files and click **Démarrer la file**. The queue never starts by itself after opening the app.

In **Séparer & analyser**, choose installed engines or **Tout préparer**. Existing results are reused and protected edits are retained. Local analysis caching avoids repeating identical calculations; changing the audio, model or settings may require another calculation.

On import, BandStudio attempts to calibrate the grid before preparing the guides. Timing settings from another song are reset. A status saying “à vérifier” means you still need to listen, especially to confirm the first downbeat.

## 2. Check the downbeat and count-in

Open **Click & cues** and listen to the beginning with the metronome. Check the first beat, beats per bar and grid mode: detected keeps the song’s timing variations; fixed imposes a constant tempo. Adjust the settings if beat one is misplaced.

The count-in follows the saved grid, including tempo changes. It can overlap the initial silence and accompany a pickup without cutting the song’s audio. Also check a restart in the middle of the song. If an automatic intro has been aligned, listen to its entrance; manually edited or reviewed sections remain protected.

## 3. Adjust sections and cues

In **Pistes & structure**:

1. Use **＋**, **−** and **Tout** to zoom. **Parcourir le morceau** moves the visible window; **Suivre la lecture** follows playback.
2. Choose **Mesure** (bar) or **Temps** (beat) snapping, then drag a section boundary or cue. You can also use the **−1 mesure**, **+1 mesure**, **−1 temps** and **+1 temps** buttons in **Un repère à la fois**.
3. Click **Écouter autour** to hear the announcement and entrance. Click the marker’s name to edit it.
4. Click **Valider et suivant** to review the next marker. The counter shows progress. Moving a marker clears its reviewed status.

Shared boundaries keep adjoining sections continuous. Changes are saved with the song and support undo/redo. Reviewing individual markers does not replace the final review before REAPER export.

## 4. Balance the guides

**Métronome**, **Appels**, **Cues** and **Décompte** have separate levels. **Muet** mutes or restores each guide’s level. Changing levels or marking a cue as reviewed does not rerun AI analysis or rebuild guides. Moving a marker may require guide regeneration.

## 5. Edit the song sheet

Open **Fiche morceau**. The sheet brings together song identity, available artwork, tempo, key, sections, chords and lyrics, bar by bar. Select a passage from the list; click a bar or section title to move the listening cursor.

- Click a chord or lyric line to edit its text and timing. **Détails** shows additional position information.
- Use the start/end bar and beat fields, nudge buttons or **Placer au curseur**. Moving a lyric line preserves the relative timing of its synchronized words.
- **+ Accord** and **+ Paroles** add annotations. Replacing chords over a selected interval preserves their portions outside that interval.
- **Importer des paroles** uses your own file. **Annuler** and **Rétablir** undo and redo edits.
- Chord/lyric reference buttons open a browser search using the song title and artist. Compare the version and key, then edit manually; nothing from those sites is imported automatically.

The sheet edits the open song’s existing annotations. Estimated chords and transcription still need listening checks. A lyric line without word timing remains whole at its starting position.

## 6. Export the PDF and project

Click **Exporter la fiche PDF**. The printable chart includes sections, bars, chords, lyrics, cues and notes. It follows the saved grid, transposition and capo for displayed chords. Choose a filename and destination for the copy; the PDF then opens in your system viewer. Cancelling the copy keeps the generated PDF in the song’s **Exports** folder. **Afficher l’export** helps locate it if automatic opening fails.

Finally, in **Valider & envoyer**, listen and confirm the mix, grid and guides, then export to REAPER. Export again to apply the corrected count-in to an older REAPER export.

## Update or get help

Use **Vérifier maintenant** in **Réglages**. With automatic updates enabled, the verified package is applied after exit. Windows packages and macOS updates are published only after the GitHub checks pass.

Still hearing a timing issue? In **Aide & Discord**, describe the passage, tempo and expected behavior. Review the report before posting it in the bug channel. [Join the community](https://discord.gg/5UnQPdMUpR).
