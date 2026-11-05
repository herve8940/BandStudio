-- ReaCue : aide et erreurs de la fenêtre ReaCue / help and errors of the ReaCue window.
--   ctx.help_text(id)   : ligne d'aide (bas de la fenêtre) pour l'élément survolé
--   ctx.explain(msg)    : message d'erreur compréhensible : {cause, solution, actions = {{id, label}}}
--   ctx.do_action(id)   : action d'un bouton de solution (démarrer le pont, installer, enregistrer…)
-- Vocabulaire commun (FR / EN), le même que dans les tutoriels :
--   « Analyser et préparer », « Tout faire », « Mettre à jour les téléphones », « Réanalyser depuis zéro »,
--   « Séparer les stems », « Appliquer », « Prêt ✓ ».
return function(ctx)
  local L, U, R, SEP = ctx.L, ctx.U, ctx.R, ctx.SEP
  local G = {}

  -- aide au survol ----------------------------------------------------------------------------
  local HELP = {
    fr = {
      default = "Survole un bouton : son rôle s'affiche ici.  ·  Clic droit : ancrer / détacher la fenêtre.",
      tab_song = "Morceau : préparer le projet ouvert (stems, structure, click, annonces, téléphones).",
      tab_concert = "Concert : composer une setlist avec les morceaux prêts, la construire, préparer des morceaux en lot.",
      tab_stage = "Scène : jouer (transport, sections, instruments, répétition) et vérifier avant le concert.",
      tab_settings = "Réglages : langue, décompte, annonces, sorties, analyse de structure, licences.",
      tab_lighting = "Lumière : cues et timecode pour la console grandMA3, sorties LTC / MTC, export, test d'envoi.",
      l_export = "Écrire les fichiers grandMA3 (Sequence, Timecode, conduite, plugin) à chaque préparation.",
      l_fps = "Images par seconde du timecode (la même valeur que sur la console).",
      l_tcstart = "Timecode du début du projet (ex. 01:00:00:00), ajouté à tous les temps.",
      l_slot = "TC Slot de la console (1 à 8), réglé par le plugin ReaCue de grandMA3.",
      l_ltc = "Sortie audio de la carte son reliée à l'entrée LTC de la console (piste TIMECODE LTC).",
      l_mtc = "Sortie MIDI qui envoie le MTC à la console (piste TIMECODE MTC).",
      l_gap = "Concert : blanc minimum entre deux morceaux (vide = celui de la setlist).",
      l_songslot = "Concert : chaque morceau démarre au prochain multiple de ce créneau (0 = non).",
      l_tracks = "Créer ou recréer les pistes TIMECODE LTC / MTC du projet ouvert (réglage du générateur gardé).",
      l_export_now = "Écrire maintenant les fichiers grandMA3 du morceau ou du concert ouvert.",
      l_folder = "Ouvrir le dossier grandMA3 (fichiers à copier sur la clé USB de la console).",
      l_from = "Le test part de la position actuelle ou du début du morceau.",
      l_test = "Jouer 10 s avec seulement les pistes TIMECODE (solo), puis tout rétablir. 2e appui : arrêter.",
      lcue = "Cue lumière : numéro, timecode envoyé à la console, nom.",
      newsong = "Créer un morceau à partir d'un MP3 ou d'un dossier de stems (copiés dans le dossier des projets).",
      cnewsong = "Créer un morceau à partir d'un MP3 ou d'un dossier de stems (copiés dans le dossier des projets).",
      primary = "L'étape suivante pour ce morceau.",
      doall = "Tout faire : séparer les stems si besoin, analyser et préparer, mettre à jour les téléphones, enregistrer.",
      sep = "Séparer les stems : découpe un MP3 en voix, batterie, basse, guitares… (Demucs, en local).",
      prep = "Re-préparer : refait click, annonces et prompteur en gardant ta structure (tes régions).",
      rean = "Réanalyser depuis zéro : tempo et structure recalculés ; tes corrections de sections sont remplacées.",
      pub = "Mettre à jour les téléphones : renvoie paroles, accords, batterie et structure au prompteur.",
      apply = "Appliquer : click, annonces et prompteur suivent ta structure modifiée.",
      addsec = "Ajouter une section qui commence à la mesure du curseur d'édition.",
      ren = "Renommer la section (le nom est annoncé à voix haute).",
      mvl = "Avancer le début de la section d'une mesure (la section précédente raccourcit).",
      mvr = "Reculer le début de la section d'une mesure (la section précédente s'allonge).",
      del = "Supprimer la section : elle rejoint sa voisine.",
      merge = "Fusionner la section choisie avec la suivante.",
      split = "Couper la section choisie en deux, au milieu (sur une mesure).",
      undo = "Annuler la dernière modification de la structure.",
      redo = "Rétablir la modification annulée.",
      band = "Clic : choisir la section et l'écouter.  Orange = à vérifier (longueur inhabituelle ou frontière incertaine).",
      row = "Clic sur le nom : écouter la section.",
      opendir = "Ouvrir le dossier du morceau (paroles.txt, stems).",
      addconcert = "Ajouter ce morceau à la setlist d'un concert (nouveau ou existant).",
      flow_cancel = "Arrêter après l'étape en cours.",
      flow_resume = "Reprendre à l'étape qui a échoué.",
      flow_close = "Fermer la liste des étapes.",
      later = "Garder le morceau tel quel ; « Tout faire » reste disponible.",
      pill_stems = "Stems : pistes séparées (voix, batterie…). Clic sur « — » : les séparer.",
      pill_structure = "Qui a trouvé les sections : SongFormer (IA), ReaCue (détection simple) ou toi (manuelle).",
      pill_tempo = "Tempo du morceau dans REAPER.",
      pill_chords = "Accords envoyés au prompteur. Clic : mettre à jour les téléphones.",
      pill_drums = "Partition de batterie envoyée au prompteur. Clic : mettre à jour les téléphones.",
      pill_lyrics = "Paroles trouvées dans le dossier du morceau. Clic : ouvrir le dossier.",
      pill_lyrics_auto = "Paroles transcrites automatiquement (Whisper) : « paroles (auto).txt » est un brouillon. Corrige-le sur place, ou renomme-le paroles.txt après correction, puis mets à jour les téléphones. Clic : ouvrir le fichier.",
      pill_sheet = "Grille du morceau à imprimer (accords, paroles), dans le dossier du morceau. Clic : l'ouvrir (ou la créer).",
      pill_prompter = "Prompteur des téléphones. Clic : QR code (ou mise à jour s'il n'est pas publié).",
      pill_saved = "Projet enregistré. Clic : enregistrer maintenant.",
      rescan = "Relire le dossier des projets.",
      addp = "Ajouter ce morceau à la setlist.",
      bsel = "Cocher / décocher ce morceau pour la préparation en lot.",
      batch = "Préparer l'un après l'autre les morceaux cochés (ou tous ceux qui ne sont pas prêts), en arrière-plan.",
      bstop = "Arrêter le lot après le morceau en cours.",
      rename = "Renommer la setlist.",
      up = "Monter le morceau dans la setlist.", dn = "Descendre le morceau dans la setlist.", rm = "Retirer de la setlist.",
      cnew = "Commencer une nouvelle setlist.",
      cbuild = "Construire le projet concert (tous les morceaux à la suite, sections, click, annonces).",
      copen = "Ouvrir le projet concert déjà construit.",
      clive = "Instruments joués en vrai : leurs stems sont coupés pendant le concert.",
      ld = "Charger cette setlist pour la modifier.", op = "Ouvrir ce concert dans un onglet.",
      lang = "Langue de la fenêtre, des annonces et des messages.",
      setpin = "Code à 4 chiffres demandé par la Régie des téléphones.",
      cin = "Nombre de mesures de décompte avant le début du morceau.",
      cue = "L'annonce vocale tombe ce nombre de mesures avant la section.",
      clang = "Langue du décompte parlé.",
      vcues = "Annoncer le nom de chaque section à voix haute.",
      vcount = "Compter à voix haute la dernière mesure avant chaque section.",
      avoice = "Voix des annonces (voix système).", cvoice = "Voix du décompte (voix système).",
      hw = "Sortie de la carte son pour le click et les voix (casques, in-ears).",
      master = "Envoyer aussi click et voix en façade (sortie principale).",
      click_volume = "Volume du click.", voice_volume = "Volume des voix.",
      tempo = "auto : fixe si le morceau est quantisé ; fixe ; variable (suit le batteur).",
      stems = "Nombre de stems séparés (6 : avec guitare et piano).",
      count_rate = "Vitesse du décompte parlé (mots par minute).",
      structure = "Détection des sections : SongFormer (IA, si installé) ou la détection simple de ReaCue.",
      dir_projects_dir = "Dossier où ReaCue cherche et crée les projets de morceaux.",
      dir_concert_dir = "Dossier des setlists et des projets concert.",
      licences = "Composants tiers, licences et avertissements.",
      adv = "Afficher / masquer les réglages avancés.",
      checkinst = "Vérifier l'installation : pont, interface web, adresse IP, stems, structure, dossiers.",
      as_fix = "Corriger ce point.", as_again = "Refaire les vérifications.", as_done = "Fermer l'assistant (il reste dans Réglages).",
      play = "Lecture / pause.", stop = "Stop.", prev = "Morceau précédent.", next = "Morceau suivant.",
      home = "Revenir au début du morceau.", reh = "Répétition : boucle sur une section avec une mesure de décompte.",
      rate = "Ralentir pour répéter (100, 90, 80, 70 %).", check = "Vérifier avant le concert.",
      qr = "QR code du prompteur pour les téléphones.", hearall = "Tout entendre (annule les coupures).",
      mute_ = "Clic : couper / remettre.  Appui long : solo.", livebtn = "Instruments joués en vrai.",
      rebuild = "Reconstruire le concert avec les derniers morceaux préparés.",
      fix = "Corriger ce point.", ckagain = "Refaire les vérifications.",
      resok = "Fermer ce message.", err_action = "Appliquer la solution proposée.",
    },
    en = {
      default = "Hover a button: what it does shows here.  ·  Right-click: dock / undock the window.",
      tab_song = "Song: prepare the open project (stems, structure, click, cues, phones).",
      tab_concert = "Concert: build a setlist from ready songs, build it, prepare songs in batch.",
      tab_stage = "Stage: play (transport, sections, instruments, rehearsal) and check before the show.",
      tab_settings = "Settings: language, count-in, cues, outputs, structure analysis, licences.",
      tab_lighting = "Lighting: cues and timecode for the grandMA3 console, LTC / MTC outputs, export, send test.",
      l_export = "Write the grandMA3 files (Sequence, Timecode, cue sheet, plugin) at each preparation.",
      l_fps = "Timecode frames per second (the same value as on the console).",
      l_tcstart = "Timecode of the project start (e.g. 01:00:00:00), added to every time.",
      l_slot = "Console TC Slot (1 to 8), set by the ReaCue grandMA3 plugin.",
      l_ltc = "Audio interface output wired to the console's LTC input (TIMECODE LTC track).",
      l_mtc = "MIDI output sending MTC to the console (TIMECODE MTC track).",
      l_gap = "Concert: minimum gap between two songs (empty = the setlist's).",
      l_songslot = "Concert: each song starts at the next multiple of this slot (0 = no).",
      l_tracks = "Create or recreate the open project's TIMECODE LTC / MTC tracks (generator setting kept).",
      l_export_now = "Write the grandMA3 files of the open song or concert now.",
      l_folder = "Open the grandMA3 folder (files to copy to the console's USB stick).",
      l_from = "The test starts from the current position or from the start of the song.",
      l_test = "Play 10 s with only the TIMECODE tracks (solo), then restore everything. Press again: stop.",
      lcue = "Lighting cue: number, timecode sent to the console, name.",
      newsong = "Create a song from an MP3 or a folder of stems (copied into the projects folder).",
      cnewsong = "Create a song from an MP3 or a folder of stems (copied into the projects folder).",
      primary = "The next step for this song.",
      doall = "Do everything: split stems if needed, analyse and prepare, update the phones, save.",
      sep = "Split stems: splits an MP3 into vocals, drums, bass, guitars… (Demucs, local).",
      prep = "Prepare again: rebuilds click, cues and prompter keeping your structure (your regions).",
      rean = "Re-analyse from scratch: tempo and structure computed again; your section fixes are replaced.",
      pub = "Update the phones: sends lyrics, chords, drums and structure to the prompter again.",
      apply = "Apply: click, cues and prompter follow your edited structure.",
      addsec = "Add a section starting at the edit cursor's bar.",
      ren = "Rename the section (the name is spoken aloud).",
      mvl = "Move the section's start one bar earlier (the previous section gets shorter).",
      mvr = "Move the section's start one bar later (the previous section gets longer).",
      del = "Delete the section: it joins its neighbour.",
      merge = "Merge the selected section with the next one.",
      split = "Split the selected section in two, in the middle (on a bar).",
      undo = "Undo the last structure change.",
      redo = "Redo the undone change.",
      band = "Click: select the section and listen.  Orange = to check (unusual length or uncertain boundary).",
      row = "Click the name: listen to the section.",
      opendir = "Open the song's folder (lyrics.txt, stems).",
      addconcert = "Add this song to a concert's setlist (new or existing).",
      flow_cancel = "Stop after the current step.",
      flow_resume = "Resume at the step that failed.",
      flow_close = "Close the list of steps.",
      later = "Keep the song as it is; “Do everything” stays available.",
      pill_stems = "Stems: separate tracks (vocals, drums…). Click “—”: split them.",
      pill_structure = "Who found the sections: SongFormer (AI), ReaCue (simple detection) or you (manual).",
      pill_tempo = "The song's tempo in REAPER.",
      pill_chords = "Chords sent to the prompter. Click: update the phones.",
      pill_drums = "Drum chart sent to the prompter. Click: update the phones.",
      pill_lyrics = "Lyrics found in the song's folder. Click: open the folder.",
      pill_lyrics_auto = "Lyrics transcribed automatically (Whisper): “paroles (auto).txt” is a draft. Correct it in place, or rename it lyrics.txt once corrected, then update the phones. Click: open the file.",
      pill_sheet = "Printable song chart (chords, lyrics) in the song's folder. Click: open it (or create it).",
      pill_prompter = "Phones' prompter. Click: QR code (or update if not published).",
      pill_saved = "Project saved. Click: save now.",
      rescan = "Read the projects folder again.",
      addp = "Add this song to the setlist.",
      bsel = "Tick / untick this song for batch preparation.",
      batch = "Prepare the ticked songs (or all songs not ready) one after the other, in the background.",
      bstop = "Stop the batch after the current song.",
      rename = "Rename the setlist.",
      up = "Move the song up.", dn = "Move the song down.", rm = "Remove from the setlist.",
      cnew = "Start a new setlist.",
      cbuild = "Build the concert project (all songs in a row, sections, click, cues).",
      copen = "Open the concert project already built.",
      clive = "Instruments played for real: their stems are muted during the show.",
      ld = "Load this setlist to edit it.", op = "Open this concert in a tab.",
      lang = "Language of the window, cues and messages.",
      setpin = "4-digit code asked by the phones' stage control.",
      cin = "Number of count-in bars before the song starts.",
      cue = "The spoken cue comes this many bars before the section.",
      clang = "Language of the spoken count.",
      vcues = "Speak each section's name aloud.",
      vcount = "Count aloud the last bar before each section.",
      avoice = "Cue voice (system voice).", cvoice = "Count voice (system voice).",
      hw = "Audio interface output for click and voices (headphones, in-ears).",
      master = "Also send click and voices to front of house (main output).",
      click_volume = "Click volume.", voice_volume = "Voice volume.",
      tempo = "auto: fixed when the song is quantised; fixed; variable (follows the drummer).",
      stems = "Number of separated stems (6: with guitar and piano).",
      count_rate = "Speed of the spoken count (words per minute).",
      structure = "Section detection: SongFormer (AI, if installed) or ReaCue's simple detection.",
      dir_projects_dir = "Folder where ReaCue looks for and creates song projects.",
      dir_concert_dir = "Folder of setlists and concert projects.",
      licences = "Third-party components, licences and disclaimers.",
      adv = "Show / hide the advanced settings.",
      checkinst = "Check the installation: bridge, web interface, IP address, stems, structure, folders.",
      as_fix = "Fix this item.", as_again = "Run the checks again.", as_done = "Close the assistant (it stays in Settings).",
      play = "Play / pause.", stop = "Stop.", prev = "Previous song.", next = "Next song.",
      home = "Back to the start of the song.", reh = "Rehearsal: loop a section with one count-in bar.",
      rate = "Slow down to rehearse (100, 90, 80, 70 %).", check = "Check before the show.",
      qr = "Prompter QR code for the phones.", hearall = "Hear everything (cancels the mutes).",
      mute_ = "Click: mute / unmute.  Long press: solo.", livebtn = "Instruments played for real.",
      rebuild = "Rebuild the concert with the latest prepared songs.",
      fix = "Fix this item.", ckagain = "Run the checks again.",
      resok = "Close this message.", err_action = "Apply the suggested solution.",
    },
  }

  function G.help_text(id)
    local l = HELP[L.lang()] or HELP.fr
    if U.hover_tip then return U.hover_tip end
    if not id then return nil end
    local function look(k) return l[k] or HELP.fr[k] end
    local v = look(id)
    if v then return v end
    local base = id:gsub("%d+$", "")
    v = look(base)
    if v then return v end
    base = base:gsub("[mp]$", "")                -- pas à pas des réglages : cinm / cinp
    v = look(base)
    if v then return v end
    local pre = id:match("^([%a]+_)")             -- mute_Chant, live_drums…
    if pre then return look(pre) end
    return nil
  end
  function G.default_help() return (HELP[L.lang()] or HELP.fr).default end

  -- erreurs : cause + solution + bouton d'action ---------------------------------------------
  local ERR = {
    fr = {
      bridge = { "Le pont ReaCue ne tourne pas dans REAPER.", "Démarre le pont (ou redémarre REAPER : il démarre tout seul).", "Démarrer le pont" },
      install = { "Le programme ReaCue est introuvable.", "Relance l'installation (« Install ReaCue », REAPER fermé).", "Ouvrir le dossier" },
      old_bridge = { "Le pont ReaCue de REAPER est trop ancien pour cette fonction.", "Relance l'installation (« Install ReaCue », REAPER fermé), puis redémarre REAPER.", "Ouvrir le dossier" },
      stems = { "La séparation de stems n'est pas installée.", "Installe-la (environ 1 Go, 5 à 15 min).", "Installer" },
      structure = { "L'analyse de structure SongFormer n'est pas installée.", "Installe-la (environ 3 Go) ; en attendant, ReaCue utilise sa détection simple.", "Installer" },
      structure_failed = { "SongFormer n'a pas pu analyser le morceau : ReaCue a utilisé sa détection simple.", "Vérifie les sections (orange = à vérifier) ou réanalyse plus tard.", nil },
      offline = { "Un fichier audio est hors ligne ou introuvable.", "Remets les médias en ligne (ou retrouve le fichier déplacé).", "Corriger" },
      unsaved = { "Le projet du morceau n'est pas encore enregistré.", "Enregistre-le : le concert lit le fichier du projet.", "Enregistrer" },
      busy = { "Une préparation est déjà en cours.", "Attends qu'elle se termine (la progression s'affiche en haut).", nil },
      timeout = { "Pas de réponse de ReaCue dans le temps prévu.", "Regarde le journal (cli.log) puis recommence.", "Ouvrir le journal" },
      web = { "L'interface web de REAPER n'est pas activée.", "Préférences > Contrôle/OSC/web > Ajouter > Interface web (port 8080, page prompteur.html).", "Ouvrir les préférences" },
      generic = { nil, "Recommence ; si ça se reproduit, regarde le journal (cli.log).", "Ouvrir le journal" },
      cause = "Cause", solution = "Que faire",
    },
    en = {
      bridge = { "The ReaCue bridge is not running in REAPER.", "Start the bridge (or restart REAPER: it starts by itself).", "Start the bridge" },
      install = { "The ReaCue program cannot be found.", "Run the installer again (“Install ReaCue”, REAPER closed).", "Open the folder" },
      old_bridge = { "REAPER's ReaCue bridge is too old for this feature.", "Run the installer again (“Install ReaCue”, REAPER closed), then restart REAPER.", "Open the folder" },
      stems = { "Stem separation is not installed.", "Install it (about 1 GB, 5 to 15 min).", "Install" },
      structure = { "SongFormer structure analysis is not installed.", "Install it (about 3 GB); meanwhile ReaCue uses its simple detection.", "Install" },
      structure_failed = { "SongFormer could not analyse the song: ReaCue used its simple detection.", "Check the sections (orange = to check) or re-analyse later.", nil },
      offline = { "An audio file is offline or missing.", "Set the media online again (or find the moved file).", "Fix" },
      unsaved = { "The song's project is not saved yet.", "Save it: the concert reads the project file.", "Save" },
      busy = { "A preparation is already running.", "Wait until it finishes (progress shows at the top).", nil },
      timeout = { "No answer from ReaCue in time.", "Look at the log (cli.log) and try again.", "Open the log" },
      web = { "REAPER's web interface is not enabled.", "Preferences > Control/OSC/web > Add > Web browser interface (port 8080, page prompteur.html).", "Open preferences" },
      generic = { nil, "Try again; if it happens again, look at the log (cli.log).", "Open the log" },
      cause = "Cause", solution = "What to do",
    },
  }
  local function E(k) local l = ERR[L.lang()] or ERR.fr; return l[k] or ERR.fr[k] end
  G.E = E

  local PATTERNS = {
    { "old_bridge", { "pont REAPER trop ancien", "REAPER bridge too old" } },
    { "bridge", { "pont ReaCue ne tourne pas", "bridge is not running", "no_bridge" } },
    { "stems", { "séparation de stems n'est pas installée", "Stem separation is not installed", ".venv-demucs" } },
    { "structure", { "SongFormer introuvable", "SongFormer not found", "structure_missing" } },
    { "structure_failed", { "Analyse SongFormer impossible", "SongFormer analysis failed" } },
    { "install", { "Programme ReaCue introuvable", "ReaCue program not found" } },
    { "unsaved", { "Enregistre d'abord le projet", "Save the song's project first", "not_saved", "pas encore enregistré", "not saved yet" } },
    { "offline", { "hors ligne", "offline", "introuvable :", "not found:", "No such file", "FileNotFoundError" } },
    { "busy", { "déjà en cours", "already running" } },
    { "timeout", { "Pas de réponse après", "No answer after" } },
    { "web", { "interface web", "web interface" } },
  }

  -- msg : texte d'erreur (ou clé directe) ; renvoie {kind, cause, solution, action}
  function G.explain(msg)
    msg = tostring(msg or "")
    local kind = "generic"
    for _, p in ipairs(PATTERNS) do
      for _, pat in ipairs(p[2]) do
        if msg == p[1] or msg:find(pat, 1, true) then kind = p[1] break end
      end
      if kind ~= "generic" then break end
    end
    local e = E(kind)
    return { kind = kind, cause = e[1] or msg, solution = e[2], action = e[3] and kind or nil, action_label = e[3] }
  end

  -- actions -------------------------------------------------------------------------------------
  local function open_path(p)
    if R.is_windows() then reaper.ExecProcess('cmd.exe /C start "" ' .. R.winq(p), -1)
    elseif (reaper.GetOS and reaper.GetOS() or ""):match("^OSX") or (reaper.GetOS and reaper.GetOS() or ""):match("^macOS") then
      os.execute("open " .. R.shq(p))
    else os.execute("xdg-open " .. R.shq(p) .. " &") end
    return p
  end
  G.open_path = open_path

  function G.installer(kind)          -- "main" | "stems" | "structure" | "words"
    if ctx.require_edit and not ctx.require_edit() then return false end
    local dir = R.install_dir(ctx.dir)
    local base = ({ main = "Install ReaCue", stems = "Install ReaCue Stems", structure = "Install ReaCue Structure",
      words = "Install ReaCue Words" })[kind]
    local f = dir .. SEP .. base .. (R.is_windows() and ".bat" or ".command")
    if L.exists(f) then return open_path(f) end
    return open_path(dir)
  end

  function G.start_bridge()
    local f = reaper.GetResourcePath() .. SEP .. "Scripts" .. SEP .. "ReaCue" .. SEP .. "ReaCue_Bridge.lua"
    if not L.exists(f) then f = ctx.dir .. "ReaCue_Bridge.lua" end
    if reaper.AddRemoveReaScript then
      local id = reaper.AddRemoveReaScript(true, 0, f, true)
      if id and id ~= 0 then reaper.Main_OnCommand(id, 0) return true end
    end
    return false
  end

  function G.save_project()
    if ctx.require_edit and not ctx.require_edit() then return false end
    if (ctx.proj_file or "") == "" then reaper.Main_OnCommand(40022, 0)       -- Enregistrer sous…
    elseif reaper.Main_SaveProject then reaper.Main_SaveProject(0, false) end
    return true
  end

  function G.do_action(kind)
    if kind~="timeout" and kind~="generic" and kind~="install" and ctx.require_edit and not ctx.require_edit() then return false end
    if kind == "bridge" then return G.start_bridge()
    elseif kind == "install" then return open_path(R.install_dir(ctx.dir))
    elseif kind == "old_bridge" then return G.installer("main")
    elseif kind == "stems" or kind == "structure" or kind == "words" then return G.installer(kind)
    elseif kind == "offline" then reaper.Main_OnCommand(40101, 0) return true      -- médias en ligne
    elseif kind == "unsaved" then return G.save_project()
    elseif kind == "timeout" or kind == "generic" then
      return open_path(reaper.GetResourcePath() .. SEP .. "ReaCueMCP" .. SEP .. "cli.log")
    elseif kind == "web" then reaper.Main_OnCommand(40016, 0) return true          -- Préférences
    end
    return false
  end

  ctx.help_text, ctx.explain, ctx.do_action = G.help_text, G.explain, G.do_action
  return G
end
