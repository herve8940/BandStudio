-- ReaCue : onglet « Morceau » / “Song” tab : le projet ouvert.
--   Un grand bouton suit l'état du morceau : « Séparer les stems » (un seul MP3) → « Analyser et préparer »
--   → « Prêt ✓ » (+ « Re-préparer », « Réanalyser depuis zéro », « Mettre à jour les téléphones »).
--   « Tout faire » : séparer (si besoin), analyser et préparer, mettre à jour les téléphones, enregistrer
--   (liste d'étapes, annulable, reprise à l'étape en échec) ; proposé après « + Nouveau morceau ».
--   Pastilles d'état : Stems · Structure (SongFormer | ReaCue | manuelle) · Tempo · Accords · Batterie ·
--   Paroles · Prompteur · Enregistré (clic = action utile).
--   Structure : bande colorée (largeur ∝ mesures ; orange = à vérifier) + liste ; écouter, renommer,
--   déplacer d'une mesure, fusionner, couper en deux, supprimer, ajouter ; Annuler / Rétablir ;
--   « Appliquer » (ReaCue reprend les régions modifiées à la main).
return function(ctx)
  local L, U, T, R, SEP = ctx.L, ctx.U, ctx.T, ctx.R, ctx.SEP
  local TXT = {
    fr = {
      no_song = "Ouvre le projet d'un morceau, ou crée-en un avec « + Nouveau morceau » (un MP3 ou un dossier de stems).",
      bars = "%d mesures",
      separate = "Séparer les stems", prepare = "Analyser et préparer", ready = "Prêt ✓", doall = "Tout faire",
      reprepare = "Re-préparer", reanalyse = "Réanalyser depuis zéro", publish = "Mettre à jour les téléphones",
      apply_big = "Appliquer les modifications",
      tip_separate = "Étape suivante : séparer le MP3 en stems (voix, batterie, basse…), puis « Analyser et préparer ».",
      tip_prepare = "Étape suivante : tempo, structure (SongFormer), click, annonces et prompteur.",
      tip_ready = "Le morceau est prêt : clic pour passer à l'onglet Scène.",
      tip_apply = "Tu as modifié la structure : click, annonces et prompteur vont la suivre.",
      reanalyse_q = "Réanalyser depuis zéro ?\n\nTempo et structure sont recalculés : tes corrections de sections seront remplacées.",
      structure = "Structure", structure_hint = "clic : écouter",
      no_regions = "Pas encore de sections : « Analyser et préparer ».",
      bar_n = "m. %d", len_n = "%d mes.", odd = "longueur inhabituelle (pas 4, 8 ou 16)",
      moved = "frontière déplacée par le calage sur les mesures", unsure = "frontière entre deux mesures",
      add = "+ Section au curseur", applied_hint = "Structure modifiée : « Appliquer » met à jour click, annonces et prompteur.",
      apply = "Appliquer", undo = "Annuler", redo = "Rétablir", rename_btn = "Nom",
      merge = "Fusionner →", split = "Couper en deux", delete = "Supprimer", rename = "Renommer",
      sel_line = "%s · m. %d · %d mes.",
      rename_title = "ReaCue - Renommer la section", rename_field = "Nom :",
      add_title = "ReaCue - Nouvelle section", add_field = "Nom de la section :", add_default = "Pont",
      split_title = "ReaCue - Couper la section", split_field = "Nom de la 2e partie :",
      add_here = "Une section commence déjà à cette mesure.", add_outside = "Place le curseur dans une section existante.",
      del_last = "Il faut garder au moins une section.", split_short = "Section trop courte pour être coupée (2 mesures minimum).",
      undo_rename = "ReaCue : renommer une section", undo_move = "ReaCue : déplacer une section",
      undo_add = "ReaCue : ajouter une section", undo_del = "ReaCue : supprimer une section",
      undo_merge = "ReaCue : fusionner deux sections", undo_split = "ReaCue : couper une section",
      undo_restore = "ReaCue : annuler / rétablir la structure",
      p_stems = "Stems", p_structure = "Structure", p_songformer = "SongFormer", p_reacue = "ReaCue", p_manual = "manuelle",
      p_chords = "Accords", p_drums = "Batterie", p_lyrics = "Paroles : %d lignes", p_lyrics_none = "Paroles",
      p_lyrics_auto = "Paroles : auto (%d lignes)",
      p_sheet = "Grille PDF",
      p_prompter = "Prompteur publié", p_prompter_none = "Prompteur", p_saved = "Enregistré", p_unsaved = "Non enregistré",
      p_tempo_none = "Tempo",
      lyrics_none = "Pas de paroles : dépose paroles.txt dans le dossier du morceau.",
      open_dir = "Ouvrir le dossier",
      add_concert = "Ajouter à un concert", new_concert = "Nouveau concert…", new_name_title = "ReaCue - Nouveau concert",
      new_name_field = "Nom du concert :", added = "« %s » ajouté au concert « %s » Construis-le dans l'onglet Concert.",
      not_saved = "Enregistre d'abord le projet du morceau (Cmd+S / Ctrl+S).",
      after_stems = "",
      analysis_options = "Options d'analyse", tracks = "Pistes…", publication_dirty = "Pistes modifiées : mets à jour les téléphones.",
      propose = "Morceau créé. Tout préparer maintenant (stems, structure, click, téléphones) ?", later = "Plus tard",
      steps = "Tout faire", cancel = "Arrêter", resume = "Reprendre", close = "Fermer", summary = "Résumé",
      st_skipped = "déjà fait", st_cancelled = "annulé", st_pending = "", ready_in = "Morceau prêt ✓  (%s)",
      stopped_at = "Arrêté à l'étape « %s »", cancelling = "arrêt après cette étape…",
      structure_install = "SongFormer non installé : détection simple de ReaCue",
    },
    en = {
      no_song = "Open a song's project, or create one with “+ New song” (an MP3 or a folder of stems).",
      bars = "%d bars",
      separate = "Split stems", prepare = "Analyse and prepare", ready = "Ready ✓", doall = "Do everything",
      reprepare = "Prepare again", reanalyse = "Re-analyse from scratch", publish = "Update the phones",
      apply_big = "Apply the changes",
      tip_separate = "Next step: split the MP3 into stems (vocals, drums, bass…), then “Analyse and prepare”.",
      tip_prepare = "Next step: tempo, structure (SongFormer), click, cues and prompter.",
      tip_ready = "The song is ready: click to go to the Stage tab.",
      tip_apply = "You changed the structure: click, cues and prompter will follow it.",
      reanalyse_q = "Re-analyse from scratch?\n\nTempo and structure are computed again: your section fixes will be replaced.",
      structure = "Structure", structure_hint = "click: listen",
      no_regions = "No sections yet: “Analyse and prepare”.",
      bar_n = "bar %d", len_n = "%d bars", odd = "unusual length (not 4, 8 or 16)",
      moved = "boundary moved when aligning on bars", unsure = "boundary between two bars",
      add = "+ Section at cursor", applied_hint = "Structure changed: “Apply” updates the click, cues and prompter.",
      apply = "Apply", undo = "Undo", redo = "Redo", rename_btn = "Name",
      merge = "Merge →", split = "Split in two", delete = "Delete", rename = "Rename",
      sel_line = "%s · bar %d · %d bars",
      rename_title = "ReaCue - Rename the section", rename_field = "Name:",
      add_title = "ReaCue - New section", add_field = "Section name:", add_default = "Bridge",
      split_title = "ReaCue - Split the section", split_field = "Name of the 2nd part:",
      add_here = "A section already starts at this bar.", add_outside = "Put the cursor inside an existing section.",
      del_last = "At least one section must stay.", split_short = "Section too short to split (2 bars minimum).",
      undo_rename = "ReaCue: rename a section", undo_move = "ReaCue: move a section",
      undo_add = "ReaCue: add a section", undo_del = "ReaCue: delete a section",
      undo_merge = "ReaCue: merge two sections", undo_split = "ReaCue: split a section",
      undo_restore = "ReaCue: undo / redo the structure",
      p_stems = "Stems", p_structure = "Structure", p_songformer = "SongFormer", p_reacue = "ReaCue", p_manual = "manual",
      p_chords = "Chords", p_drums = "Drums", p_lyrics = "Lyrics: %d lines", p_lyrics_none = "Lyrics",
      p_lyrics_auto = "Lyrics: auto (%d lines)",
      p_sheet = "PDF chart",
      p_prompter = "Prompter published", p_prompter_none = "Prompter", p_saved = "Saved", p_unsaved = "Not saved",
      p_tempo_none = "Tempo",
      lyrics_none = "No lyrics: drop lyrics.txt in the song's folder.",
      open_dir = "Open folder",
      add_concert = "Add to a concert", new_concert = "New concert…", new_name_title = "ReaCue - New concert",
      new_name_field = "Concert name:", added = "“%s” added to the concert “%s”. Build it in the Concert tab.",
      not_saved = "Save the song's project first (Cmd+S / Ctrl+S).",
      after_stems = "",
      analysis_options = "Analysis options", tracks = "Tracks…", publication_dirty = "Tracks changed: update the phones.",
      propose = "Song created. Prepare everything now (stems, structure, click, phones)?", later = "Later",
      steps = "Do everything", cancel = "Stop", resume = "Resume", close = "Close", summary = "Summary",
      st_skipped = "already done", st_cancelled = "cancelled", st_pending = "", ready_in = "Song ready ✓  (%s)",
      stopped_at = "Stopped at step “%s”", cancelling = "stopping after this step…",
      structure_install = "SongFormer not installed: ReaCue's simple detection",
    },
  }
  local function t(k) return ctx.tr(TXT, k) end
  local M = {}
  local info = nil          -- {regions, bpm, bars, key, prepared, dirs, titles, lyrics, …}
  local dirty = false
  local sel = nil           -- section choisie (bande / liste)
  local hist, redo = {}, {} -- historique de la structure (instantanés des régions)
  local last_summary = nil  -- message de la dernière préparation (bouton « Résumé »)
  local GEN = { CLICK = true, CUES = true, VOIX = true, VOICE = true, ["TIMECODE LTC"] = true, ["TIMECODE MTC"] = true }
  local function can_edit()
    return not (ctx.require_edit and not ctx.require_edit()) and not (ctx.is_locked and ctx.is_locked())
  end
  function M.tracks()
    if not M.track_manager then M.track_manager = dofile(ctx.dir .. "ReaCue_tracks.lua")(ctx) end
    return M.track_manager
  end
  function M.tracks_changed()
    info = nil
    if not ctx.is_concert then ctx.c = M.pseudo_concert() end
  end

  -- projet ---------------------------------------------------------------------------------
  -- état gardé dans le projet (.RPP) : moteur de structure, débuts de sections douteux
  function M.proj_get(k)
    if not reaper.GetProjExtState then return nil end
    local _, v = reaper.GetProjExtState(0, "ReaCue", k)
    return (v and v ~= "") and v or nil
  end
  function M.proj_set(k, v)
    if reaper.SetProjExtState then reaper.SetProjExtState(0, "ReaCue", k, v or "") end
  end
  local function measure_of(tp)
    if not reaper.TimeMap2_timeToBeats then return 0 end
    local _, m = reaper.TimeMap2_timeToBeats(0, tp + 1e-6)
    return math.floor(m or 0)
  end
  local function bar_time(m)
    if reaper.TimeMap2_beatsToTime then return reaper.TimeMap2_beatsToTime(0, 0, m) end
    return nil
  end

  local function list_regions()
    local out, k = {}, 0
    while true do
      local ok, isrgn, pos, rend, name, idx, color = reaper.EnumProjectMarkers3(0, k)
      if not ok or ok == 0 then break end
      if isrgn then out[#out + 1] = { idx = idx, name = name or "", start = pos, stop = rend, color = color or 0 } end
      k = k + 1
    end
    table.sort(out, function(a, b) return a.start < b.start end)
    return out
  end

  local function track_name(tr) local _, n = reaper.GetTrackName(tr); return n or "" end

  local function key_from(names)
    for _, n in ipairs(names) do
      local root, acc, mode = n:match("%f[%a]([A-G])%s?([#b]?)%s?([Mm][ai][jn]%a*)")
      if root then
        mode = mode:lower()
        return root .. acc .. ((mode:sub(1, 3) == "min") and "m" or "")
      end
    end
    return nil
  end

  local function source_file(it)
    local tk = it and reaper.GetActiveTake(it)
    if not tk or (reaper.TakeIsMIDI and reaper.TakeIsMIDI(tk)) then return nil end
    local src = reaper.GetMediaItemTake_Source(tk)
    local parent = src and reaper.GetMediaSourceParent and reaper.GetMediaSourceParent(src)
    while parent do src = parent; parent = reaper.GetMediaSourceParent(src) end
    local fn = src and reaper.GetMediaSourceFileName(src, "") or ""
    return fn ~= "" and fn or nil
  end

  -- Paroles de l'utilisateur (paroles*.txt|rtf, parole*, lyrics*), sinon brouillon automatique « paroles (auto).txt »
  -- (Whisper, lyrics_auto.py) : { n = lignes chantées, file, dir, auto = true si brouillon }.
  -- Comme read_lyrics de lyrics.py : lignes vides, étiquettes « [ … ] » et commentaires « # » non comptés.
  local AUTO_NAME = "paroles (auto).txt"
  local function read_lyrics(dirs)
    local function count(d, f, lf)
      local src = L.read(d .. SEP .. f) or ""
      local n = 0
      if lf:match("%.rtf$") then
        for _ in src:gmatch("\\par[^d]") do n = n + 1 end
      else
        for line in (src .. "\n"):gmatch("(.-)\r?\n") do
          local s = line:gsub("^%s+", ""):gsub("%s+$", "")
          if s ~= "" and not s:match("^%[") and not s:match("^#") then n = n + 1 end
        end
      end
      return n
    end
    local auto = nil
    for _, d in ipairs(dirs) do
      local i = 0
      while true do
        local f = reaper.EnumerateFiles(d, i)
        if not f then break end
        local lf = f:lower()
        if lf == AUTO_NAME then
          auto = auto or { file = f, dir = d }
        elseif (lf:match("^paroles") or lf:match("^parole") or lf:match("^lyrics")) and (lf:match("%.txt$") or lf:match("%.rtf$")) then
          return { n = count(d, f, lf), file = f, dir = d }
        end
        i = i + 1
      end
    end
    if auto then
      return { n = count(auto.dir, auto.file, AUTO_NAME), file = auto.file, dir = auto.dir, auto = true }
    end
    return nil
  end

  -- Titre publié par ReaCue : nom du fichier seul, ou, pour des stems, le début commun de leurs noms
  -- (« Song-vocals », « Song-drums » -> « Song »). Accepté s'il est le nom d'un des fichiers du projet
  -- ou le début d'un de ces noms (au moins 3 caractères, suivi d'un séparateur ou de la fin).
  local function title_matches(title, titles)
    if titles[title] then return true end
    if #title < 3 then return false end
    local pre = nil                     -- même calcul que _common_title côté serveur
    for name in pairs(titles) do
      if not pre then pre = name
      else
        local n = 0
        while n < #pre and n < #name and pre:byte(n + 1) == name:byte(n + 1) do n = n + 1 end
        pre = pre:sub(1, n)
      end
    end
    if pre and pre:gsub("[%s%-_%.]+$", "") == title then return true end
    for name in pairs(titles) do
      if name:sub(1, #title) == title then
        local nxt = name:sub(#title + 1, #title + 1)
        if nxt == "" or nxt:match("[%s%-_%.]") then return true end
      end
    end
    return false
  end

  local function published(titles)
    local src = L.read(reaper.GetResourcePath() .. SEP .. "reaper_www_root" .. SEP .. "reacue_song.json")
    if not src or src:find('"concert"%s*:%s*{') then return nil end   -- concert : objet ; lighting.concert = false
    local title = R.jfield(src, "title")
    if not title or not title_matches(title, titles) then return nil end
    local chords = src:find('"chords"%s*:%s*%[%s*{') ~= nil
    local drums = src:find('"drums"%s*:%s*{') ~= nil
    return { chords = chords, drums = drums, title = title }
  end

  -- grille PDF écrite par le serveur à chaque publication (sheet.py : « Grille - <titre>.pdf »)
  local function find_sheet(dirs, title)
    local safe = title:gsub('[\\/:*?"<>|]+', " "):gsub("^%s+", ""):gsub("%s+$", "")
    for k = #dirs, 1, -1 do
      for _, pre in ipairs({ "Grille - ", "Chart - " }) do
        local p = dirs[k] .. SEP .. pre .. safe .. ".pdf"
        local f = io.open(p, "rb")
        if f then f:close(); return p end
      end
    end
    return nil
  end

  local function scan()
    local regs = list_regions()
    local names, dirs, seen_d, titles = {}, {}, {}, {}
    local has_click = false
    local audio_tracks, seen_tr = 0, {}
    for i = 0, (reaper.CountTracks and reaper.CountTracks(0) or 0) - 1 do
      if track_name(reaper.GetTrack(0, i)) == "CLICK" then has_click = true end
    end
    for i = 0, (reaper.CountMediaItems and reaper.CountMediaItems(0) or 0) - 1 do
      local it = reaper.GetMediaItem(0, i)
      local tr = reaper.GetMediaItem_Track and reaper.GetMediaItem_Track(it)
      if not (tr and GEN[track_name(tr)]) then
        if tr and not seen_tr[tr] then
          seen_tr[tr] = true
          audio_tracks = audio_tracks + 1
        end
        local fn = source_file(it)
        if fn then
          local d, base = fn:match("^(.*)[/\\]([^/\\]+)$")
          names[#names + 1] = base or fn
          titles[(base or fn):gsub("%.[^.]+$", "")] = true
          if d and not seen_d[d] then
            seen_d[d] = true
            dirs[#dirs + 1] = d
            local up = d:match("^(.*)[/\\][^/\\]+%-stems[/\\][^/\\]+$")     -- stems séparés par ReaCue
            if up and not seen_d[up] then seen_d[up] = true; dirs[#dirs + 1] = up end
          end
        end
      end
    end
    local bpm = nil
    local t0 = regs[1] and regs[1].start or 0
    if reaper.TimeMap2_GetDividedBpmAtTime then bpm = reaper.TimeMap2_GetDividedBpmAtTime(0, t0 + 0.01)
    elseif reaper.Master_GetTempo then bpm = reaper.Master_GetTempo() end
    local bars = 0
    if #regs > 0 then bars = measure_of(regs[#regs].stop - 0.001) - measure_of(regs[1].start) + 1 end
    local m0 = regs[1] and measure_of(regs[1].start) or 0
    for _, r in ipairs(regs) do
      r.bar = measure_of(r.start) - m0 + 1
      r.len = measure_of(r.stop - 0.001) - measure_of(r.start) + 1
    end
    local roles = 0
    for _, n in ipairs(names) do if ctx.newsong and ctx.newsong.role_of(n) then roles = roles + 1 end end
    info = {
      regions = regs, bpm = bpm, bars = bars, key = key_from(names), prepared = (#regs > 0 and has_click),
      dirs = dirs, titles = titles, has_audio = #names > 0, m0 = m0,
      single_mix = (#names == 1 or audio_tracks == 1),        -- un seul mix / une seule piste audio : séparer d'abord
      stems_ok = (audio_tracks > 1 or #names > 1),
      engine = M.proj_get("structure_engine"), doubts = {},
    }
    for b, why in (M.proj_get("doubts") or ""):gmatch("(%d+):(%a+)") do info.doubts[tonumber(b)] = why end
    for _, r in ipairs(regs) do r.doubt = info.doubts[r.bar] end
    info.lyrics = read_lyrics(dirs)
    info.pub = M.proj_get("publication_dirty") ~= "1" and published(titles) or nil
    info.sheet = info.pub and find_sheet(dirs, info.pub.title) or nil
    info.t = reaper.time_precise()
    return info
  end

  -- concert « fictif » d'un seul morceau : transport, sections et répétition dans l'onglet Scène
  function M.pseudo_concert()
    local i = scan()
    if not i.has_audio then return nil end
    local regs = i.regions
    local stop = (#regs > 0 and regs[#regs].stop) or (reaper.GetProjectLength and reaper.GetProjectLength(0)) or 0
    if reaper.GetProjectLength then stop = math.max(stop, reaper.GetProjectLength(0)) end
    return {
      pseudo = true,
      songs = { { title = ctx.proj_name ~= "" and ctx.proj_name or "?", start = 0, stop = stop, next = stop,
                  bar1 = regs[1] and regs[1].start or 0, bars = i.bars, bpm = i.bpm or 120, key = i.key,
                  sections = #regs } },
    }
  end

  -- prompteur publié pour ce morceau ({chords, drums, title}) ou nil ; relu toutes les 2 s (onglet Lumière)
  function M.published_info()
    if not info or reaper.time_precise() - (info.t or 0) > 2 then scan() end
    return info.pub
  end

  function M.project_changed()
    info = nil; dirty = false; sel = nil; hist, redo = {}, {}; last_summary = nil
    if M.track_manager then M.track_manager.close() end
  end
  function M.enter() info = nil end

  -- état pour « Tout faire » et le lot
  function M.state()
    local i = info or scan()
    return { single_mix = i.single_mix and not i.prepared, prepared = i.prepared, dirty = dirty, has_audio = i.has_audio }
  end

  local function changed()
    dirty = true
    info = nil
    M.proj_set("structure_engine", "manual")
    if ctx.tabs.stage.invalidate then ctx.tabs.stage.invalidate() end
    reaper.UpdateTimeline()
  end

  -- édition des régions (avec historique Annuler / Rétablir) --------------------------------------
  local function set_region(r, start, stop, name)
    reaper.SetProjectMarker4(0, r.idx, true, start, stop, name or r.name, r.color or 0, (name == "") and 1 or 0)
  end

  local function snapshot()
    local out = {}
    for _, r in ipairs(list_regions()) do out[#out + 1] = { start = r.start, stop = r.stop, name = r.name, color = r.color } end
    return out
  end

  -- remplace toutes les régions du projet par un instantané
  local function restore(snap)
    local regs = list_regions()
    table.sort(regs, function(a, b) return a.idx > b.idx end)
    reaper.Undo_BeginBlock()
    for _, r in ipairs(regs) do reaper.DeleteProjectMarker(0, r.idx, true) end
    for _, r in ipairs(snap) do reaper.AddProjectMarker2(0, true, r.start, r.stop, r.name, -1, r.color or 0) end
    reaper.Undo_EndBlock(t("undo_restore"), -1)
  end

  -- à appeler avant chaque modification
  local function push()
    hist[#hist + 1] = snapshot()
    if #hist > 50 then table.remove(hist, 1) end
    redo = {}
  end

  function M.undo()
    if not can_edit() then return false end
    if #hist == 0 then return false end
    redo[#redo + 1] = snapshot()
    restore(table.remove(hist))
    changed()
    return true
  end

  function M.redo()
    if not can_edit() then return false end
    if #redo == 0 then return false end
    hist[#hist + 1] = snapshot()
    restore(table.remove(redo))
    changed()
    return true
  end

  function M.can_undo() return #hist > 0 end
  function M.can_redo() return #redo > 0 end

  local function rename(k)
    if not can_edit() then return false end
    local r = info.regions[k]
    local ok, v = reaper.GetUserInputs(t("rename_title"), 1, t("rename_field") .. ",extrawidth=120", r.name)
    if not ok or not v or v == r.name then return end
    if not can_edit() then return false end
    v = v:gsub("^%s+", ""):gsub("%s+$", "")
    if v == "" then return end
    push()
    reaper.Undo_BeginBlock()
    set_region(r, r.start, r.stop, v)
    reaper.Undo_EndBlock(t("undo_rename"), -1)
    changed()
  end

  local function move(k, d)
    if not can_edit() then return false end
    local regs = info.regions
    local r, prev = regs[k], regs[k - 1]
    local nt = bar_time(measure_of(r.start) + d)
    if not nt or nt >= r.stop - 0.01 then return end
    if prev and nt <= prev.start + 0.01 then return end
    if nt < 0 then return end
    push()
    reaper.Undo_BeginBlock()
    if prev and math.abs(prev.stop - r.start) < 0.02 then set_region(prev, prev.start, nt) end
    set_region(r, nt, r.stop)
    reaper.Undo_EndBlock(t("undo_move"), -1)
    changed()
  end

  local function delete(k)
    if not can_edit() then return false end
    local regs = info.regions
    if #regs <= 1 then reaper.ShowMessageBox(t("del_last"), T("title"), 0) return end
    local r, prev, nx = regs[k], regs[k - 1], regs[k + 1]
    push()
    reaper.Undo_BeginBlock()
    if prev and math.abs(prev.stop - r.start) < 0.02 then set_region(prev, prev.start, r.stop)
    elseif nx and math.abs(nx.start - r.stop) < 0.02 then set_region(nx, r.start, nx.stop) end
    reaper.DeleteProjectMarker(0, r.idx, true)
    reaper.Undo_EndBlock(t("undo_del"), -1)
    if sel and sel >= #regs then sel = #regs - 1 end
    changed()
  end

  -- fusionner la section k avec la suivante (le nom de la 1re est gardé)
  local function merge(k)
    if not can_edit() then return false end
    local regs = info.regions
    local r, nx = regs[k], regs[k + 1]
    if not nx then return end
    push()
    reaper.Undo_BeginBlock()
    set_region(r, r.start, nx.stop)
    reaper.DeleteProjectMarker(0, nx.idx, true)
    reaper.Undo_EndBlock(t("undo_merge"), -1)
    changed()
  end

  -- couper la section k en deux, sur la mesure du milieu
  local function split(k)
    if not can_edit() then return false end
    local r = info.regions[k]
    if r.len < 2 then reaper.ShowMessageBox(t("split_short"), T("title"), 0) return end
    local mid = bar_time(measure_of(r.start) + math.floor(r.len / 2))
    if not mid or mid <= r.start + 0.01 or mid >= r.stop - 0.01 then return end
    local ok, v = reaper.GetUserInputs(t("split_title"), 1, t("split_field") .. ",extrawidth=120", r.name)
    if not ok or not v or v:gsub("%s", "") == "" then return end
    if not can_edit() then return false end
    push()
    reaper.Undo_BeginBlock()
    local stop = r.stop
    set_region(r, r.start, mid)
    reaper.AddProjectMarker2(0, true, mid, stop, v, -1, r.color or 0)
    reaper.Undo_EndBlock(t("undo_split"), -1)
    changed()
  end

  local function add_at_cursor()
    if not can_edit() then return false end
    local regs = info.regions
    local tb = bar_time(measure_of(reaper.GetCursorPosition()))
    if not tb then return end
    local host = nil
    for _, r in ipairs(regs) do
      if math.abs(r.start - tb) < 0.02 then reaper.ShowMessageBox(t("add_here"), T("title"), 0) return end
      if r.start < tb and tb < r.stop then host = r end
    end
    if not host then reaper.ShowMessageBox(t("add_outside"), T("title"), 0) return end
    local ok, v = reaper.GetUserInputs(t("add_title"), 1, t("add_field") .. ",extrawidth=120", t("add_default"))
    if not ok or not v or v:gsub("%s", "") == "" then return end
    if not can_edit() then return false end
    push()
    reaper.Undo_BeginBlock()
    local stop = host.stop
    set_region(host, host.start, tb)
    reaper.AddProjectMarker2(0, true, tb, stop, v, -1, 0)
    reaper.Undo_EndBlock(t("undo_add"), -1)
    changed()
  end

  local function listen(r)
    reaper.SetEditCurPos(r.start, true, true)
    if L.play_state() ~= "play" then reaper.OnPlayButton() end
  end

  -- ajouter à un concert --------------------------------------------------------------------
  local function slug(name)
    local s = tostring(name):gsub('[\\/:*?"<>|]+', "-"):gsub("^[%s%.]+", ""):gsub("[%s%.]+$", "")
    return s ~= "" and s or "Concert"
  end
  ctx.slug = slug

  -- ajoute le projet à la setlist <dossier des concerts>/<nom>.setlist.json (créée si besoin)
  function ctx.add_to_setlist(name, project, title)
    if not can_edit() then return false end
    local dir = L.concert_dir()
    reaper.RecursiveCreateDirectory(dir, 0)
    local path = dir .. SEP .. slug(name) .. ".setlist.json"
    local raw = L.read(path)
    local d = raw and R.json_decode(raw) or nil
    if (raw and (type(d) ~= "table" or R.is_array(d))) or (not raw and L.exists(path)) then
      ctx.show_result(T("error_title"), L.lang() == "fr" and "Setlist illisible : fichier conservé." or "Unreadable setlist: file kept.", false)
      return false
    end
    d = d or {}
    d.name = d.name or name
    d.gap_s = d.gap_s or 4
    d.songs = d.songs or R.json_array({})
    setmetatable(d.songs, getmetatable(R.json_array({})))
    d.songs[#d.songs + 1] = { project = project, title = title }
    d.live = d.live or R.json_array({})
    d.live_exceptions = d.live_exceptions or {}
    if not R.write_atomic(path, R.json_encode(d, "  ", { "name", "gap_s", "songs", "live", "live_exceptions" })) then
      ctx.show_result(T("error_title"), L.lang() == "fr" and "Setlist non enregistrée : fichier précédent conservé." or "Setlist not saved: previous file kept.", false)
      return false
    end
    return path
  end

  local function add_to_concert()
    if not can_edit() then return false end
    if (ctx.proj_file or "") == "" then reaper.ShowMessageBox(t("not_saved"), T("title"), 0) return end
    local names = {}
    local dir = L.concert_dir()
    local i = 0
    while true do
      local f = reaper.EnumerateFiles(dir, i)
      if not f then break end
      local stem = f:match("^(.*)%.setlist%.json$")
      if stem then names[#names + 1] = stem end
      i = i + 1
    end
    table.sort(names)
    local menu = t("new_concert")
    if #names > 0 then menu = menu .. "||" .. table.concat(names, "|") end
    gfx.x, gfx.y = gfx.mouse_x, gfx.mouse_y
    local choice = gfx.showmenu(menu)
    if not choice or choice < 1 then return end
    local name
    if choice == 1 then
      local ok, v = reaper.GetUserInputs(t("new_name_title"), 1, t("new_name_field") .. ",extrawidth=120", "")
      if not ok or not v or v:gsub("%s", "") == "" then return end
      name = v
    else
      name = names[choice - 1]
    end
    if not name then return end
    local path = ctx.add_to_setlist(name, ctx.proj_file, ctx.proj_name)
    if not path then return false end
    if ctx.tabs.concert.load_setlist then ctx.tabs.concert.load_setlist(path) end
    ctx.show_result(T("done_title"), string.format(t("added"), ctx.proj_name, name), true)
  end

  local function open_dir(d)
    if ctx.R.is_windows() then reaper.ExecProcess('explorer.exe ' .. ctx.R.winq(d), -1)
    elseif (reaper.GetOS and reaper.GetOS() or ""):match("^OSX") or (reaper.GetOS and reaper.GetOS() or ""):match("^macOS") then
      os.execute("open " .. ctx.R.shq(d))
    else os.execute("xdg-open " .. ctx.R.shq(d) .. " &") end
  end

  -- lancement des traitements ---------------------------------------------------------------
  -- après une préparation / séparation réussie lancée depuis la fenêtre : le projet du morceau est
  -- enregistré (sinon le concert ne retrouve ni sections ni tempo) ; jamais un projet concert
  local saved_t = nil
  function M.autosave(key)
    if not can_edit() then return false end
    if ctx.is_concert or key ~= ctx.proj_key or (ctx.proj_file or "") == "" then return false end
    if not reaper.Main_SaveProject then return false end
    reaper.Main_SaveProject(0, false)
    saved_t = reaper.time_precise()
    return true
  end

  -- fin d'une commande de la CLI (bouton ou « Tout faire ») : moteur des sections et débuts douteux
  -- (lus dans cli_status.json), gardés dans le projet
  function M.cli_done(cmd, state, msg)
    if (cmd == "publish" or cmd == "prepare") and state == "done" then M.proj_set("publication_dirty", ""); info = nil end
    if cmd ~= "prepare" then return end
    if state == "done" then
      dirty = false
      last_summary = msg
      local src = L.read(R.STATUS) or ""
      local eng = R.jfield(src, "engine")
      if eng == "songformer" or eng == "reacue" then
        M.proj_set("structure_engine", eng)
        M.proj_set("doubts", R.jfield(src, "doubts") or "")
        hist, redo = {}, {}
      end
      M.structure_missing = R.jfield(src, "structure_missing") == true
    end
    info = nil
  end

  local function done_cb(after)
    local key = ctx.proj_key
    return function(state, msg)
      info = nil
      if ctx.tabs.stage.invalidate then ctx.tabs.stage.invalidate() end
      if state == "done" then
        dirty = false
        M.autosave(key)
        ctx.show_result(T("done_title"), (msg or "") .. (after or ""), true)
      else
        ctx.show_result(T("error_title"), msg, false)
      end
      ctx.refresh(true)
    end
  end

  function M.prepare() if not can_edit() then return false end; return ctx.start_cli("prepare", R.tr("prepare"), done_cb()) end
  function M.reanalyse()
    if not can_edit() then return false end
    if reaper.ShowMessageBox(t("reanalyse_q"), T("title"), 1) ~= 1 then return false end
    return ctx.start_cli("prepare --reanalyse", R.tr("prepare"), done_cb())
  end
  function M.publish() if not can_edit() then return false end; return ctx.start_cli("publish", R.tr("publish"), done_cb()) end
  function M.separate() if not can_edit() then return false end; return ctx.start_stems(done_cb(t("after_stems"))) end
  function M.do_all()
    if not can_edit() then return false end
    ctx.propose_all = nil
    return ctx.flow.start(M.state(), function()
      info = nil
      if ctx.tabs.stage.invalidate then ctx.tabs.stage.invalidate() end
    end)
  end

  -- dessin ------------------------------------------------------------------------------------
  local function fmt_bpm(b) return b and string.format("%.0f BPM", b) or "? BPM" end
  local function fmt_secs(s)
    s = math.floor((s or 0) + 0.5)
    if s >= 60 then return string.format("%d min %02d s", s // 60, s % 60) end
    return string.format("%d s", s)
  end
  local function region_col(r)
    if r.color and r.color ~= 0 then local rr, gg, bb = reaper.ColorFromNative(r.color & 0xFFFFFF); return { rr, gg, bb } end
    return U.GREY
  end
  local function odd_len(r) return r.len ~= 4 and r.len ~= 8 and r.len ~= 16 end
  local function doubt_text(r)
    local bits = {}
    if odd_len(r) then bits[#bits + 1] = t("odd") end
    if r.doubt then bits[#bits + 1] = t(r.doubt) end
    return #bits > 0 and table.concat(bits, " · ") or nil
  end

  -- pastilles d'état (retour à la ligne si besoin) ; renvoie y suivant
  local function draw_pills(i, x, y, w)
    local saved = (ctx.proj_file or "") ~= "" and not (reaper.IsProjectDirty and reaper.IsProjectDirty(0) == 1)
    local eng = i.engine
    local eng_lab = (eng == "songformer" and t("p_songformer")) or (eng == "reacue" and t("p_reacue"))
      or ((eng == "manual" or eng == "regions") and t("p_manual")) or nil
    local sf = R.structure_installed and R.structure_installed(R.install_dir(ctx.dir))
    local p = i.pub
    local ly = i.lyrics
    local pills = {
      { "pill_stems", t("p_stems") .. (i.stems_ok and " ✓" or " —"), i.stems_ok or (i.single_mix and "warn" or false), "stems" },
      { "pill_structure", t("p_structure") .. (#i.regions > 0 and (ctx.colon() .. (eng_lab or t("p_reacue")) .. " ✓") or " —"),
        #i.regions > 0 and ((eng == "reacue" and not sf) and "warn" or true) or false, "structure" },
      { "pill_tempo", i.prepared and fmt_bpm(i.bpm) or (t("p_tempo_none") .. " —"), i.prepared or false, "tempo" },
      { "pill_chords", t("p_chords") .. ((p and p.chords) and " ✓" or " —"), (p and p.chords) or false, "publish" },
      { "pill_drums", t("p_drums") .. ((p and p.drums) and " ✓" or " —"), (p and p.drums) or false, "publish" },
      ly and ly.auto and { "pill_lyrics_auto", string.format(t("p_lyrics_auto"), ly.n), "warn", "lyrics" }
        or { "pill_lyrics", ly and string.format(t("p_lyrics"), ly.n) or (t("p_lyrics_none") .. " —"), ly and true or false, "lyrics" },
      { "pill_sheet", t("p_sheet") .. (i.sheet and " ✓" or " —"), i.sheet and true or false, "sheet" },
      { "pill_prompter", p and (t("p_prompter") .. " ✓") or (t("p_prompter_none") .. " —"), p and true or false, "prompter" },
      { "pill_saved", saved and (t("p_saved") .. " ✓") or t("p_unsaved"), saved or "warn", "save" },
    }
    local px, row_h = x, 26
    for _, pl in ipairs(pills) do
      local pw = U.text_w(pl[2], 12, true) + 26
      if px > x and px + pw > x + w then px = x; y = y + row_h end
      local _, clk = U.chip(pl[1], pl[2], pl[3], px, y)
      if pl[1] == "pill_structure" and eng == "reacue" and not sf and U.hover == pl[1] then U.hover_tip = t("structure_install") end
      if clk and not ctx.job then
        local a = pl[4]
        if a == "stems" and not i.stems_ok then M.separate()
        elseif a == "structure" and not sf and can_edit() then ctx.do_action("structure")
        elseif a == "publish" then M.publish()
        elseif a == "lyrics" then
          if ly and ly.auto then ctx.guide.open_path(ly.dir .. SEP .. ly.file)   -- brouillon : l'ouvrir pour le corriger
          else
            local d = (ly and ly.dir) or i.dirs[#i.dirs] or i.dirs[1]
            if d then ctx.guide.open_path(d) end
          end
        elseif a == "prompter" then if p then ctx.open_qr() else M.publish() end
        elseif a == "sheet" then if i.sheet then ctx.guide.open_path(i.sheet) else M.publish() end
        elseif a == "save" and can_edit() then ctx.guide.save_project(); saved_t = reaper.time_precise() end
        return y + row_h, true
      end
      px = px + pw + 6
    end
    return y + row_h + 4
  end

  -- liste d'étapes de « Tout faire »
  local MARK = { done = "✓", running = "●", failed = "✗", pending = "○", skipped = "–", cancelled = "–" }
  local function draw_flow(x, y, w)
    local F = ctx.flow
    local run = F.run
    U.set(U.PANEL2); gfx.rect(x - 4, y - 4, w + 8, 4 + 30 + #run.steps * 26 + 10, 1)
    U.text(t("steps"), x + 4, y + 4, 15, U.INK, true)
    local bx = x + w
    local function btn(id, lab, style)
      local bw = U.text_w(lab, 12) + 22
      bx = bx - bw
      local c = U.button(id, lab, bx, y, bw, 26, style, 12)
      bx = bx - 6
      return c
    end
    if not run.finished then
      if btn("flow_cancel", t("cancel")) then F.cancel() end
    else
      if btn("flow_close", t("close"), run.ok and "primary" or nil) then F.close() return y end
      if not run.ok and btn("flow_resume", t("resume"), "primary") and not ctx.job then F.resume() end
      if run.ok and last_summary and btn("flow_summary", t("summary")) then ctx.show_result(T("done_title"), last_summary, true) end
    end
    y = y + 34
    for k, s in ipairs(run.steps) do
      local col = (s.status == "done" and U.ACCENT) or (s.status == "running" and U.BLUE) or (s.status == "failed" and U.RED) or U.GREY
      U.text(MARK[s.status] or "○", x + 6, y + 2, 15, col, true)
      local lab = F.label(s.id)
      if s.status == "running" and ctx.job and ctx.job.label and s.id ~= "save" then
        lab = lab .. "  ·  " .. ctx.job.label
      end
      local right = ""
      if s.status == "skipped" then right = t("st_skipped")
      elseif s.status == "cancelled" then right = t("st_cancelled")
      elseif s.status == "running" then right = fmt_secs(reaper.time_precise() - (s.t0 or reaper.time_precise()))
        if run.cancel then right = t("cancelling") end
      elseif s.secs and (s.status == "done" or s.status == "failed") then right = fmt_secs(s.secs) end
      local rw = U.text_w(right, 12)
      U.text(U.fit(lab, w - rw - 40, 13, s.status == "running"), x + 28, y + 3, 13,
        (s.status == "pending" or s.status == "skipped" or s.status == "cancelled") and U.MUTED or U.INK, s.status == "running")
      U.text(right, x + w - rw - 4, y + 4, 12, U.MUTED)
      if s.status == "running" and ctx.job and ctx.job.pct and ctx.job.pct > 0 then
        U.set(U.PANEL); gfx.rect(x + 28, y + 21, w - 32, 3, 1)
        U.set(U.ACCENT); gfx.rect(x + 28, y + 21, math.floor((w - 32) * ctx.job.pct / 100), 3, 1)
      end
      y = y + 26
    end
    y = y + 10
    if run.finished then
      if run.ok then
        U.text(string.format(t("ready_in"), fmt_secs((run.t_end or 0) - (run.t0 or 0))), x, y, 14, U.ACCENT, true)
        y = y + 24
      else
        local fs = run.failed and run.steps[run.failed]
        if fs then
          U.text(U.fit(string.format(t("stopped_at"), F.label(fs.id)), w, 14, true), x, y, 14, U.RED, true)
          y = y + 22
          local why = ctx.explain(fs.msg)
          if why.cause then y = y + U.para(why.cause, x, y, w, 12, U.INK, 3) + 4 end
          if why.kind == "generic" and fs.msg then y = y + U.para(fs.msg, x, y, w, 12, U.MUTED, 6) + 4 end
          local h, acted = ctx.draw_solution(why, x, y, w, "err_action")
          y = y + h + 6
          if acted then return y end
        end
      end
    end
    return y + 4
  end

  -- bande de structure : une case par section, largeur proportionnelle aux mesures
  local function draw_band(i, x, y, w)
    local regs = i.regions
    local total = 0
    for _, r in ipairs(regs) do total = total + math.max(1, r.len) end
    if total == 0 then return y end
    local H = 34
    local cur = L.pos()
    local bx = x
    for k, r in ipairs(regs) do
      local bw = (k == #regs) and (x + w - bx) or math.max(6, math.floor(w * math.max(1, r.len) / total + 0.5))
      local col = region_col(r)
      local dt = doubt_text(r)
      local over = U.over(bx, y, bw, H)
      U.set(col, over and 0.95 or 0.72); gfx.rect(bx, y, bw - 2, H, 1)
      if dt then
        U.set(U.WARN); gfx.rect(bx, y, bw - 2, 5, 1)
        U.frame(bx, y, bw - 2, H, U.WARN)
      end
      if sel == k then
        U.frame(bx, y, bw - 2, H, U.INK); U.frame(bx + 1, y + 1, bw - 4, H - 2, U.INK)
      end
      if bw > 22 then
        local nm = U.fit(r.name, bw - 8, 11, true)
        U.text(nm, bx + 4, y + 7, 11, U.DARK, true)
        U.text(U.fit(tostring(r.len), bw - 8, 10), bx + 4, y + 20, 10, U.DARK)
      end
      local tip = string.format(t("sel_line"), r.name, r.bar, r.len) .. (dt and ("  —  " .. dt) or "")
      U.tip(bx, y, bw - 2, H, tip, "band" .. k)
      if over and U.clicked then sel = k; listen(r) end
      bx = bx + bw
    end
    -- tête de lecture
    local t0, t1 = regs[1].start, regs[#regs].stop
    if cur >= t0 and cur <= t1 and t1 > t0 then
      local px = x + math.floor(w * (cur - t0) / (t1 - t0))
      U.set(U.INK); gfx.rect(px, y - 3, 2, H + 6, 1)
    end
    return y + H + 8
  end

  function M.draw(x, y, w)
    if not info or reaper.time_precise() - (info.t or 0) > 2 then scan() end
    local i = info
    local F = ctx.flow
    local run = F.run and F.run.key == ctx.proj_key and F.run or nil
    if ctx.job and not (run and not run.finished) then y = y + ctx.draw_job(x, y, w) end
    -- titre
    local title = ctx.proj_name ~= "" and ctx.proj_name or "?"
    local NS = ctx.newsong
    local nw = NS and (U.text_w(NS.t("button"), 13) + 22) or 0
    local tw = U.text_w(t("tracks"), 12) + 22
    U.text(U.fit(title, math.max(0, w - nw - tw - 20), 18, true), x, y, 18, U.INK, true)
    if U.button("tracks", t("tracks"), x + w - nw - tw - 6, y - 3, tw, 26, nil, 12) then M.tracks().open() end
    if NS and U.button("newsong", NS.t("button"), x + w - nw, y - 3, nw, 26, (not i.has_audio) and "primary" or nil, 13)
      and not ctx.job then NS.start() return y end
    y = y + 26
    if M.track_manager and M.track_manager.visible then return M.track_manager.draw(x, y, w) end
    if M.proj_get("publication_dirty") == "1" then y = y + U.para(t("publication_dirty"), x, y, w, 12, U.WARN) + 6 end
    if ctx.flash and reaper.time_precise() - ctx.flash.t < 3 then
      y = y + (U.para(ctx.flash.txt, x, y, w, 12, ctx.flash.bad and U.WARN or U.ACCENT, 3) or 0) + 6
    end
    if not i.has_audio then
      U.para(t("no_song"), x, y, w, 13, U.MUTED)
      return y + 40
    end
    local sub = {}
    if i.bars > 0 then sub[#sub + 1] = string.format(t("bars"), i.bars) end
    if i.key then sub[#sub + 1] = i.key end
    if #sub > 0 then U.text(U.fit(table.concat(sub, " · "), w, 12), x, y - 4, 12, U.MUTED); y = y + 14 end
    local ny, acted = draw_pills(i, x, y, w)
    if acted then return ny end
    y = ny + 4
    local busy = ctx.job ~= nil

    -- Les moteurs se choisissent avant le premier calcul (aucune analyse à l'ouverture).
    if not busy and not (run and not run.finished) then
      local settings = ctx.tabs.settings
      local bw = U.text_w(t("analysis_options"), 12) + 24
      if U.button("analysis_options", t("analysis_options"), x, y, bw, 26, nil, 12) then
        settings.set_page("models")
        ctx.goto_tab("settings")
        return y
      end
      U.text(U.fit(settings.model_summary(), math.max(0, w - bw - 12), 11), x + bw + 12, y + 6, 11, U.MUTED)
      y = y + 34
    end

    -- proposé après « + Nouveau morceau »
    if ctx.propose_all and ctx.propose_all == ctx.proj_key and not run then
      U.set(U.ACCENT, 0.18); gfx.rect(x, y, w, 40, 1)
      U.set(U.ACCENT); gfx.rect(x, y, 4, 40, 1)
      local b1 = U.text_w(t("doall"), 13) + 26
      local b2 = U.text_w(t("later"), 12) + 22
      U.para(t("propose"), x + 12, y + 4, w - b1 - b2 - 30, 12, U.INK, 2)
      if U.button("later", t("later"), x + w - b2 - 4, y + 7, b2, 26, nil, 12) then ctx.propose_all = nil end
      if U.button("doall", t("doall"), x + w - b2 - b1 - 10, y + 7, b1, 26, "primary", 13) and not busy then M.do_all() return y end
      y = y + 48
    end

    -- étape suivante (grand bouton) + « Tout faire »
    if run then
      y = draw_flow(x, y, w)
    else
      local state, lab, tip
      if dirty and i.prepared then state, lab, tip = "apply", t("apply_big"), t("tip_apply")
      elseif i.single_mix and not i.prepared then state, lab, tip = "separate", t("separate"), t("tip_separate")
      elseif not i.prepared then state, lab, tip = "prepare", t("prepare"), t("tip_prepare")
      else state, lab, tip = "ready", t("ready"), t("tip_ready") end
      local dw = math.max(120, math.floor(w * 0.3))
      local pw = w - dw - 8
      if U.button("primary", lab, x, y, pw, 46, state == "ready" and "on" or "primary", 17) and not busy then
        if state == "apply" then M.prepare()
        elseif state == "separate" then M.separate()
        elseif state == "prepare" then M.prepare()
        else ctx.goto_tab("stage") end
        return y
      end
      if U.hover == "primary" then U.hover_tip = tip end
      if U.button("doall", t("doall"), x + pw + 8, y, dw, 46, nil, 15) and not busy then M.do_all() return y end
      y = y + 54
      -- actions secondaires
      local sec = {}
      if state == "separate" then sec = { { "prep", t("prepare") } }
      elseif state == "prepare" then sec = {}
      else sec = { { "prep", t("reprepare") }, { "rean", t("reanalyse") }, { "pub", t("publish") } } end
      if i.single_mix and state ~= "separate" then sec[#sec + 1] = { "sep", t("separate") } end
      if #sec > 0 then
        local gap, bx = 6, x
        for _, b in ipairs(sec) do
          local bw = U.text_w(b[2], 12) + 26
          if bx > x and bx + bw > x + w then bx = x; y = y + 34 end
          if U.button(b[1], b[2], bx, y, bw, 28, "ghost", 12) and not busy then
            if b[1] == "prep" then M.prepare() elseif b[1] == "rean" then M.reanalyse()
            elseif b[1] == "pub" then M.publish() elseif b[1] == "sep" then M.separate() end
            return y
          end
          bx = bx + bw + gap
        end
        y = y + 38
      end
    end

    -- structure
    U.heading(t("structure") .. "  —  " .. t("structure_hint"), x, y)
    local hx = x + w
    local aw = U.text_w(t("add"), 12) + 18
    hx = hx - aw
    if #i.regions > 0 and U.button("addsec", t("add"), hx, y - 4, aw, 22, nil, 12) then add_at_cursor() return y end
    local rw2 = U.text_w(t("redo"), 12) + 16
    hx = hx - rw2 - 6
    if U.button("redo", t("redo"), hx, y - 4, rw2, 22, M.can_redo() and nil or "ghost", 12) and M.can_redo() then M.redo() return y end
    local uw = U.text_w(t("undo"), 12) + 16
    hx = hx - uw - 4
    if U.button("undo", t("undo"), hx, y - 4, uw, 22, M.can_undo() and nil or "ghost", 12) and M.can_undo() then M.undo() return y end
    y = y + 22
    if dirty then
      U.set(U.WARN, 0.2); gfx.rect(x, y, w, 30, 1)
      U.set(U.WARN); gfx.rect(x, y, 4, 30, 1)
      local bw2 = U.text_w(t("apply"), 13) + 24
      U.text(U.fit(t("applied_hint"), w - bw2 - 24, 12), x + 12, y + 8, 12, U.INK)
      if U.button("apply", t("apply"), x + w - bw2 - 4, y + 3, bw2, 24, "primary", 13) and not busy then M.prepare() end
      y = y + 36
    end
    if #i.regions == 0 then
      U.text(t("no_regions"), x, y + 4, 13, U.MUTED)
      y = y + 26
    else
      if sel and not i.regions[sel] then sel = nil end
      y = draw_band(i, x, y, w)
      -- outils de la section choisie
      if sel then
        local r = i.regions[sel]
        local tools = { { "ren", t("rename") }, { "mvl", nil, "left" }, { "mvr", nil, "right" } }
        if sel < #i.regions then tools[#tools + 1] = { "merge", t("merge") } end
        tools[#tools + 1] = { "split", t("split") }
        tools[#tools + 1] = { "del", t("delete") }
        local tw = 0
        for _, b in ipairs(tools) do b.w = b[2] and (U.text_w(b[2], 12) + 18) or 28; tw = tw + b.w + 4 end
        local lw = w - tw - 6
        if lw < 200 then                          -- fenêtre étroite : libellé sur sa propre ligne
          U.text(U.fit(string.format(t("sel_line"), r.name, r.bar, r.len), w, 13, true), x, y, 13, U.INK, true)
          y = y + 20
          lw = 0
        else
          U.text(U.fit(string.format(t("sel_line"), r.name, r.bar, r.len), lw, 13, true), x, y + 4, 13, U.INK, true)
        end
        local bx = (lw == 0) and x or (x + w - tw + 4)
        for _, b in ipairs(tools) do
          local clk
          if b[2] then clk = U.button(b[1] .. "_sel", b[2], bx, y, b.w, 24, nil, 12)
          else clk = U.ibutton(b[1] .. "_sel", b[3], bx, y, b.w, 24) end
          if clk then
            if b[1] == "ren" then rename(sel) elseif b[1] == "mvl" then move(sel, -1) elseif b[1] == "mvr" then move(sel, 1)
            elseif b[1] == "merge" then merge(sel) elseif b[1] == "split" then split(sel) elseif b[1] == "del" then delete(sel) end
            return y
          end
          bx = bx + b.w + 4
        end
        y = y + 32
      end
    end
    local cur = L.pos()
    for k, r in ipairs(i.regions) do
      local rh = 26
      local inside = cur >= r.start - 0.01 and cur < r.stop - 0.01
      if inside or sel == k then U.set(U.PANEL); gfx.rect(x - 4, y, w + 8, rh - 2, 1) end
      U.set(region_col(r)); gfx.rect(x - 4, y + 3, 4, rh - 8, 1)
      local dt = doubt_text(r)
      local right = string.format(t("bar_n"), r.bar) .. "  ·  " .. string.format(t("len_n"), r.len)
      local nbw = U.text_w(t("rename_btn"), 12) + 16
      local tools_w = nbw + 3 * 26 + 3 * 4
      local rw = U.text_w(right, 12)
      local name_w = w - tools_w - rw - 24
      local over = U.over(x, y, name_w, rh)
      U.text(U.fit(r.name, name_w, 14, inside), x + 6, y + 4, 14, over and U.INK or U.INK2, inside)
      if over then U.hover_tip = string.format(t("sel_line"), r.name, r.bar, r.len) .. (dt and ("  —  " .. dt) or "") end
      if over and U.clicked then sel = k; listen(r) end
      U.text(right, x + w - tools_w - rw - 10, y + 5, 12, dt and U.WARN or U.MUTED)
      local tx = x + w - tools_w
      if U.button("ren" .. k, t("rename_btn"), tx, y + 1, nbw, 22, nil, 12) then rename(k) return y end
      tx = tx + nbw + 4
      if U.ibutton("mvl" .. k, "left", tx, y + 1, 26, 22) then move(k, -1) return y end
      tx = tx + 30
      if U.ibutton("mvr" .. k, "right", tx, y + 1, 26, 22) then move(k, 1) return y end
      tx = tx + 30
      if U.ibutton("del" .. k, "x", tx, y + 1, 26, 22) then delete(k) return y end
      y = y + rh
    end
    y = y + 10

    -- dossier, concert
    if not i.lyrics then
      U.text(U.fit(t("lyrics_none"), w, 12), x, y, 12, U.MUTED)
      y = y + 20
    end
    local ow = U.text_w(t("open_dir"), 12) + 22
    local cw = U.text_w(t("add_concert"), 12) + 24
    local d = (i.lyrics and i.lyrics.dir) or i.dirs[#i.dirs] or i.dirs[1]
    if d and U.button("opendir", t("open_dir"), x, y, ow, 28, nil, 12) then open_dir(d) end
    if U.button("addconcert", t("add_concert"), x + ow + 8, y, cw, 28, nil, 12) then add_to_concert() return y end
    return y + 36
  end

  return M
end
