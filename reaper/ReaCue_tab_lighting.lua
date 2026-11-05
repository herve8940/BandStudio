-- ReaCue : onglet « Lumière » / “Lighting” tab : console grandMA3 pilotée par le timecode de REAPER.
--   Infos         : cues lumière du morceau ou du concert ouvert (n°, timecode SMPTE, nom), lus dans le
--                   prompteur publié (bloc « lighting » de l'export) ou recalculés depuis les régions ;
--                   cue en cours surligné pendant la lecture ; timecode actuel (temps projet + départ).
--   Configuration : réglages gma3_* de reacue_settings.json (écrits comme l'onglet Réglages : autres clés
--                   gardées) : export, i/s, départ, TC Slot, sortie LTC, périphérique MTC, blanc / créneau.
--   Actions       : pistes TIMECODE (CLI « timecode », même code que la préparation), export (CLI
--                   « publish » pour un morceau, « concert-lighting » pour un concert), dossier grandMA3.
--   Test          : pastilles (sortie LTC, périphérique MIDI activé, pistes TIMECODE + générateur, générateur
--                   réglé) et « Envoyer 10 s de test » : seules les pistes TIMECODE jouent (solo), puis
--                   solo / mute / position / lecture sont rétablis à l'identique (fin, 2e appui, Stop, fermeture).
-- Le LTC / MTC va dans un seul sens : rien ne revient de la console, c'est elle qui montre si elle reçoit.
return function(ctx)
  local L, U, T, R, SEP = ctx.L, ctx.U, ctx.T, ctx.R, ctx.SEP
  local TXT = {
    fr = {
      infos = "Cues lumière", src_export = "exportés", src_regions = "calculés depuis les régions",
      tc_now = "Timecode", tc_sub = "temps projet %s + départ %s · %s i/s",
      none_project = "Ouvre un morceau ou un concert préparé : ses cues lumière s'affichent ici.",
      none_regions = "Pas encore de sections : prépare d'abord le morceau (onglet Morceau).",
      not_exported = "Rien n'est encore exporté : cues calculés depuis les régions. « Exporter maintenant » écrit les fichiers grandMA3.",
      export_off = "Export grandMA3 désactivé (Configuration) : aucun fichier lumière n'est écrit.",
      stale = "Réglages ou structure modifiés depuis l'export : « Exporter maintenant ».",
      col_n = "n°", col_tc = "Timecode", col_name = "Cue", rows = "%d–%d / %d",
      config = "Configuration", export = "Export grandMA3", fps = "Images par seconde", tc_start = "Départ du timecode",
      slot = "TC Slot de la console", slot_n = "Slot %d", ltc = "Sortie LTC (audio)", mtc = "Périphérique MTC (MIDI)",
      none_f = "aucune", none_m = "aucun", out_n = "sortie %s", absent = "%s (absent)", disabled = "%s (désactivé)",
      concert = "Concert", gap = "Blanc entre morceaux", gap_default = "celui de la setlist", secs = "%s s",
      song_slot = "Créneau de départ", slot_off = "non", on = "oui", off = "non",
      tc_title = "ReaCue - Départ du timecode", tc_field = "HH:MM:SS:FF :",
      tc_bad = "Timecode illisible : écris HH:MM:SS:FF (ex. 01:00:00:00), images < %s.",
      gap_title = "ReaCue - Blanc entre morceaux", gap_field = "Secondes (vide = setlist) :",
      sslot_title = "ReaCue - Créneau de départ", sslot_field = "Secondes (0 = non) :",
      num_bad = "Nombre de secondes attendu (0 ou plus).",
      note = "Les changements s'appliquent au prochain export, à la prochaine préparation ou reconstruction du concert.",
      saved = "enregistré",
      actions = "Actions", make_tracks = "Créer / mettre à jour les pistes timecode", export_now = "Exporter maintenant",
      open_folder = "Ouvrir le dossier grandMA3", job_tracks = "Pistes timecode", job_export = "Export lumière",
      no_folder = "Pas encore de dossier grandMA3 : « Exporter maintenant » (projet enregistré) le crée à côté du projet.",
      export_disabled = "Active d'abord « Export grandMA3 » (Configuration).",
      test = "Test de communication", from_cursor = "depuis le curseur", from_start = "depuis le début",
      send_test = "Envoyer 10 s de test", stop_test = "Arrêter le test (%d s)",
      oneway = "Le LTC / MTC va dans un seul sens : ReaCue ne peut pas savoir si la console le reçoit. Pendant le test, regarde sur la console que le TC Slot %d passe au vert et que le temps défile ; seules les pistes TIMECODE jouent (le public n'entend rien), puis tout est rétabli.",
      p_ltc_off = "LTC non réglé", p_ltc_ok = "Sortie LTC %s ✓", p_ltc_bad = "Sortie LTC %s absente",
      p_mtc_off = "MTC non réglé", p_mtc_ok = "MTC ✓", p_mtc_dis = "MTC non activé", p_mtc_bad = "MTC introuvable",
      p_tr_off = "Pistes TIMECODE —", p_tr_ok = "Pistes TIMECODE ✓", p_tr_old = "Pistes à mettre à jour",
      p_tr_bad = "Pistes TIMECODE absentes",
      p_gen_off = "Générateur —", p_gen_ok = "Générateur réglé ✓", p_gen_todo = "Générateur à régler",
      d_ltc_off = "Aucune sortie LTC : choisis-la dans Configuration (ex. sortie 7 vers l'entrée LTC de la console).",
      d_ltc_ok = "Sortie %s de la carte son (%s) : %d sorties disponibles.",
      d_ltc_bad = "La carte son n'a que %d sorties : sortie %s absente (autre carte son ? audio arrêté ?).",
      d_mtc_off = "Aucun périphérique MTC : choisis-le dans Configuration (ex. IAC Driver, réseau MIDI).",
      d_mtc_ok = "« %s » trouvé et activé dans les préférences MIDI de REAPER.",
      d_mtc_dis = "« %s » existe mais n'est pas activé : Préférences > Audio > MIDI Devices, active la sortie. Clic : ouvrir les préférences.",
      d_mtc_bad = "« %s » introuvable dans les sorties MIDI de REAPER. Clic : ouvrir les préférences.",
      d_tr_off = "Aucune sortie timecode réglée : pas de piste TIMECODE à créer.",
      d_tr_ok = "Pistes présentes avec leur générateur : %s.",
      d_tr_old = "Réglages changés depuis la création des pistes (ou piste en trop) : clic pour les mettre à jour.",
      d_tr_bad = "Il manque : %s. Clic : créer les pistes timecode.",
      d_gen_off = "Pas de générateur à régler.",
      d_gen_ok = "Réglage du générateur mémorisé (%s i/s, départ %s) : réappliqué à chaque préparation.",
      d_gen_todo = "Réglage à faire une seule fois. Clic : comment faire.",
      memo_title = "Régler le générateur (une seule fois)",
      memo_ltc = "%s : double-clic sur l'item du générateur → Propriétés de la source : %s i/s, départ %s, « Send MIDI (MTC) » décoché ; OK.",
      memo_mtc = "%s : double-clic sur l'item du générateur → Propriétés de la source : %s i/s, départ %s, cocher « Send MIDI (MTC) » ; OK.",
      memo_end = "Puis « Créer / mettre à jour les pistes timecode » : ReaCue mémorise ce réglage pour tous les morceaux.",
      no_tracks = "Pas de piste TIMECODE dans le projet : « Créer / mettre à jour les pistes timecode » d'abord.",
      t_rec = "Enregistrement en cours : test impossible.", t_reh = "Quitte d'abord la répétition (onglet Scène).",
      t_done = "Test terminé : tout est rétabli.", t_stopped = "Test arrêté : tout est rétabli.",
      t_playing = "La lecture en cours s'arrête pendant le test (10 s), puis reprend.",
    },
    en = {
      infos = "Lighting cues", src_export = "exported", src_regions = "computed from the regions",
      tc_now = "Timecode", tc_sub = "project time %s + start %s · %s fps",
      none_project = "Open a prepared song or concert: its lighting cues show here.",
      none_regions = "No sections yet: prepare the song first (Song tab).",
      not_exported = "Nothing exported yet: cues computed from the regions. “Export now” writes the grandMA3 files.",
      export_off = "grandMA3 export disabled (Configuration): no lighting file is written.",
      stale = "Settings or structure changed since the export: “Export now”.",
      col_n = "#", col_tc = "Timecode", col_name = "Cue", rows = "%d–%d / %d",
      config = "Configuration", export = "grandMA3 export", fps = "Frames per second", tc_start = "Timecode start",
      slot = "Console TC Slot", slot_n = "Slot %d", ltc = "LTC output (audio)", mtc = "MTC device (MIDI)",
      none_f = "none", none_m = "none", out_n = "output %s", absent = "%s (missing)", disabled = "%s (disabled)",
      concert = "Concert", gap = "Gap between songs", gap_default = "the setlist's", secs = "%s s",
      song_slot = "Start slot", slot_off = "no", on = "yes", off = "no",
      tc_title = "ReaCue - Timecode start", tc_field = "HH:MM:SS:FF:",
      tc_bad = "Unreadable timecode: type HH:MM:SS:FF (e.g. 01:00:00:00), frames < %s.",
      gap_title = "ReaCue - Gap between songs", gap_field = "Seconds (empty = setlist):",
      sslot_title = "ReaCue - Start slot", sslot_field = "Seconds (0 = no):",
      num_bad = "A number of seconds is expected (0 or more).",
      note = "Changes apply at the next export, the next preparation or when the concert is rebuilt.",
      saved = "saved",
      actions = "Actions", make_tracks = "Create / update the timecode tracks", export_now = "Export now",
      open_folder = "Open the grandMA3 folder", job_tracks = "Timecode tracks", job_export = "Lighting export",
      no_folder = "No grandMA3 folder yet: “Export now” (saved project) creates it next to the project.",
      export_disabled = "Turn on “grandMA3 export” first (Configuration).",
      test = "Communication test", from_cursor = "from the cursor", from_start = "from the start",
      send_test = "Send a 10 s test", stop_test = "Stop the test (%d s)",
      oneway = "LTC / MTC goes one way only: ReaCue cannot know whether the console receives it. During the test, check on the console that TC Slot %d turns green and the time runs; only the TIMECODE tracks play (the audience hears nothing), then everything is restored.",
      p_ltc_off = "LTC not set", p_ltc_ok = "LTC output %s ✓", p_ltc_bad = "LTC output %s missing",
      p_mtc_off = "MTC not set", p_mtc_ok = "MTC ✓", p_mtc_dis = "MTC not enabled", p_mtc_bad = "MTC not found",
      p_tr_off = "TIMECODE tracks —", p_tr_ok = "TIMECODE tracks ✓", p_tr_old = "Tracks to update",
      p_tr_bad = "TIMECODE tracks missing",
      p_gen_off = "Generator —", p_gen_ok = "Generator set ✓", p_gen_todo = "Generator to set",
      d_ltc_off = "No LTC output: choose it in Configuration (e.g. output 7 to the console's LTC input).",
      d_ltc_ok = "Audio interface output %s (%s): %d outputs available.",
      d_ltc_bad = "The audio interface only has %d outputs: output %s missing (other interface? audio stopped?).",
      d_mtc_off = "No MTC device: choose it in Configuration (e.g. IAC Driver, network MIDI).",
      d_mtc_ok = "“%s” found and enabled in REAPER's MIDI preferences.",
      d_mtc_dis = "“%s” exists but is not enabled: Preferences > Audio > MIDI Devices, enable the output. Click: open preferences.",
      d_mtc_bad = "“%s” not found in REAPER's MIDI outputs. Click: open preferences.",
      d_tr_off = "No timecode output set: no TIMECODE track to create.",
      d_tr_ok = "Tracks present with their generator: %s.",
      d_tr_old = "Settings changed since the tracks were created (or extra track): click to update them.",
      d_tr_bad = "Missing: %s. Click: create the timecode tracks.",
      d_gen_off = "No generator to set.",
      d_gen_ok = "Generator setting remembered (%s fps, start %s): applied again at each preparation.",
      d_gen_todo = "One-time setting. Click: how to do it.",
      memo_title = "Set the generator (once)",
      memo_ltc = "%s: double-click the generator item → Source properties: %s fps, start %s, “Send MIDI (MTC)” unticked; OK.",
      memo_mtc = "%s: double-click the generator item → Source properties: %s fps, start %s, tick “Send MIDI (MTC)”; OK.",
      memo_end = "Then “Create / update the timecode tracks”: ReaCue remembers this setting for every song.",
      no_tracks = "No TIMECODE track in the project: “Create / update the timecode tracks” first.",
      t_rec = "Recording: test not possible.", t_reh = "Leave rehearsal first (Stage tab).",
      t_done = "Test finished: everything restored.", t_stopped = "Test stopped: everything restored.",
      t_playing = "Playback stops during the test (10 s), then resumes.",
    },
  }
  local function t(k) return ctx.tr(TXT, k) end
  local M = {}
  local function can_edit()
    return not (ctx.require_edit and not ctx.require_edit()) and not (ctx.is_locked and ctx.is_locked())
  end
  M.TEST_S = 10
  local TRACK_LTC, TRACK_MTC = "TIMECODE LTC", "TIMECODE MTC"
  local TC_NAMES = { [TRACK_LTC] = "ltc", [TRACK_MTC] = "mtc" }
  local DEF = { gma3_export = true, gma3_fps = 25, gma3_tc_start = "00:00:00:00", gma3_tc_slot = 1, gma3_song_slot = 0 }

  -- réglages : ceux de l'onglet Réglages (même fichier, mêmes règles d'écriture) -----------------------
  local function ST() return ctx.tabs and ctx.tabs.settings end
  local function get(k)
    local st = ST()
    local v
    if st and st.get then v = st.get(k) end
    if v == nil then v = DEF[k] end
    return v
  end
  local function set(k, v)
    if not can_edit() then return false end
    local st = ST(); if st and st.set then return st.set(k, v) end return false
  end
  M.get, M.set = get, set

  -- validation : comme reacue_mcp/lighting.py et timecode.py ---------------------------------------------
  M.FPS = { 24, 25, 29.97, 30 }
  local function jsround(x) return math.floor(x + 0.5) end

  function M.fps()
    local f = tonumber(get("gma3_fps"))
    for _, c in ipairs(M.FPS) do if f and math.abs(f - c) < 0.01 then return c end end
    return 25
  end
  function M.fps_label(f, lang)
    f = f or M.fps()
    local s = (f == math.floor(f)) and string.format("%d", f) or string.format("%g", f)
    if (lang or L.lang()) == "fr" then s = s:gsub("%.", ",") end
    return s
  end

  -- « HH:MM:SS:FF » (« ; » ou « . » acceptés, images facultatives) -> secondes ; nil si illisible
  function M.parse_tc(s, fps)
    fps = fps or M.fps()
    local str = tostring(s or "")
    local h, mi, se, fr = str:match("^%s*(%d%d?)[:;%.](%d%d?)[:;%.](%d%d?)[:;%.](%d%d?)%s*$")
    if not h then h, mi, se = str:match("^%s*(%d%d?)[:;%.](%d%d?)[:;%.](%d%d?)%s*$"); fr = "0" end
    if not h then return nil end
    h, mi, se, fr = tonumber(h), tonumber(mi), tonumber(se), tonumber(fr)
    if mi > 59 or se > 59 or fr >= jsround(fps) then return nil end
    return h * 3600 + mi * 60 + se + fr / fps
  end

  -- départ du timecode (texte) et décalage en secondes ; illisible : 00:00:00:00
  function M.tc_start()
    local tc = tostring(get("gma3_tc_start") or "00:00:00:00")
    if tc == "" then tc = "00:00:00:00" end
    local off = M.parse_tc(tc, M.fps())
    if not off then return "00:00:00:00", 0 end
    return tc, off
  end

  -- port de seconds_to_smpte (lighting.py) : HH:MM:SS:FF, non drop-frame
  function M.smpte(sec, fps)
    fps = fps or M.fps()
    sec = math.max(0, tonumber(sec) or 0)
    local total = jsround(sec * fps)
    local fr = total % jsround(fps)
    local ts = math.floor(total / fps)
    return string.format("%02d:%02d:%02d:%02d", ts // 3600, (ts // 60) % 60, ts % 60, fr)
  end

  function M.slot()
    local n = math.floor(tonumber(get("gma3_tc_slot")) or 1)
    return (n >= 1 and n <= 8) and n or 1
  end

  -- gma3_ltc_output : 7 (sortie 7, mono) ou "7/8" (paire) -> {a, b, label} ; nil = aucune
  function M.parse_ltc(v)
    if v == nil or type(v) == "boolean" then return nil end
    local s = tostring(v):gsub("^%s+", ""):gsub("%s+$", "")
    local low = s:lower()
    if s == "" or low == "none" or low == "null" or low == "off" or low == "no" or s == "0" then return nil end
    local a, b = s:match("^(%d%d?%d?)%s*[/+%-]%s*(%d%d?%d?)$")
    if not a then a = s:match("^(%d%d?%d?)$") end
    if not a then
      local f = tonumber(s)
      if not f or f ~= math.floor(f) or f < 1 then return nil end
      a = string.format("%d", f)
    end
    a, b = tonumber(a), b and tonumber(b)
    if a < 1 or a > 512 then return nil end
    if not b or b == a then return { a = a, label = tostring(a) } end
    if b ~= a + 1 then return nil end
    return { a = a, b = b, label = a .. "/" .. b }
  end

  function M.mtc_name()
    local v = get("gma3_mtc_output")
    if v == nil or type(v) == "boolean" then return nil end
    local s = tostring(v):gsub("^%s+", ""):gsub("%s+$", "")
    local low = s:lower()
    if s == "" or low == "none" or low == "null" or low == "off" or low == "no" then return nil end
    return s
  end

  -- clé du réglage mémorisé du générateur (timecode.template_key) : ltc_25_01-00-00-00
  function M.template_key(kind)
    local fps = M.fps()
    local fs = (fps == math.floor(fps)) and string.format("%d", fps) or string.format("%g", fps)
    local tc = M.tc_start()
    tc = tc:gsub("[^0-9]+", "-"):gsub("^%-+", ""):gsub("%-+$", "")
    return kind .. "_" .. fs .. "_" .. tc
  end
  function M.template_path(kind)
    return reaper.GetResourcePath() .. SEP .. "ReaCueMCP" .. SEP .. "timecode" .. SEP .. M.template_key(kind) .. ".txt"
  end
  function M.template_ok(kind)
    local src = L.read(M.template_path(kind)) or ""
    return src:match("^%s*<SOURCE LTC") ~= nil
  end

  -- carte son et MIDI -------------------------------------------------------------------------------
  function M.audio_outputs()
    local n = reaper.GetNumAudioOutputs and reaper.GetNumAudioOutputs() or 0
    local out = {}
    for i = 0, n - 1 do
      local name = reaper.GetOutputChannelName and reaper.GetOutputChannelName(i) or nil
      out[#out + 1] = (name and name ~= "") and name or string.format(t("out_n"), i + 1)
    end
    return out
  end

  -- sorties MIDI : {i, name, enabled} ; enabled = GetMIDIOutputName vrai (périphérique activé dans REAPER)
  function M.midi_outputs()
    local out = {}
    if not reaper.GetMIDIOutputName then return out end
    local n = reaper.GetMaxMIDIOutputs and reaper.GetMaxMIDIOutputs() or 64
    for i = 0, n - 1 do
      local ok, name = reaper.GetMIDIOutputName(i, "")
      if type(name) == "string" and name ~= "" then out[#out + 1] = { i = i, name = name, enabled = ok and true or false } end
    end
    return out
  end

  -- même recherche que le pont (nom exact, sinon contenu, sans tenir compte de la casse)
  function M.find_midi(want, list)
    want = tostring(want or ""):lower()
    if want == "" then return nil end
    list = list or M.midi_outputs()
    local function pick(only_enabled)
      local partial
      for _, d in ipairs(list) do
        if not only_enabled or d.enabled then
          local low = d.name:lower()
          if low == want then return d end
          if not partial and low:find(want, 1, true) then partial = d end
        end
      end
      return partial
    end
    return pick(true) or pick(false)
  end

  -- pistes TIMECODE du projet : {nom = {tr, gen, key}}
  local function track_name(tr) local _, n = reaper.GetTrackName(tr); return n or "" end
  local function has_generator(tr)
    local n = reaper.CountTrackMediaItems and reaper.CountTrackMediaItems(tr) or 0
    for i = 0, n - 1 do
      local it = reaper.GetTrackMediaItem(tr, i)
      if it and reaper.GetItemStateChunk then
        local ok, chunk = reaper.GetItemStateChunk(it, "", false)
        if ok and chunk and chunk:find("<SOURCE LTC", 1, true) then return true end
      end
      local tk = it and reaper.GetActiveTake and reaper.GetActiveTake(it)
      local src = tk and reaper.GetMediaItemTake_Source and reaper.GetMediaItemTake_Source(tk)
      if src and reaper.GetMediaSourceType then
        local ty = reaper.GetMediaSourceType(src, "")
        if ty == "LTC" then return true end
      end
    end
    return false
  end
  function M.tc_tracks()
    local out = {}
    for i = 0, (reaper.CountTracks and reaper.CountTracks(0) or 0) - 1 do
      local tr = reaper.GetTrack(0, i)
      local name = track_name(tr)
      if TC_NAMES[name] then
        local key = ""
        if reaper.GetSetMediaTrackInfo_String then
          local _, k = reaper.GetSetMediaTrackInfo_String(tr, "P_EXT:reacue_tc_key", "", false)
          key = k or ""
        end
        local e = out[name]
        if e then e.n = e.n + 1 else out[name] = { tr = tr, gen = has_generator(tr), key = key, n = 1 } end
      end
    end
    return out
  end

  -- test de communication : état de chaque point -> {st = true | false | "warn" | "bad", lab, detail} ------
  function M.check_ltc()
    local o = M.parse_ltc(get("gma3_ltc_output"))
    if not o then return { st = false, lab = t("p_ltc_off"), detail = t("d_ltc_off") } end
    local outs = M.audio_outputs()
    local hi = o.b or o.a
    if hi > #outs then
      return { st = "bad", lab = string.format(t("p_ltc_bad"), o.label), detail = string.format(t("d_ltc_bad"), #outs, o.label) }
    end
    local name = outs[o.a] .. (o.b and (" / " .. outs[o.b]) or "")
    return { st = true, lab = string.format(t("p_ltc_ok"), o.label), detail = string.format(t("d_ltc_ok"), o.label, name, #outs) }
  end

  function M.check_mtc()
    local want = M.mtc_name()
    if not want then return { st = false, lab = t("p_mtc_off"), detail = t("d_mtc_off") } end
    local d = M.find_midi(want)
    if not d then return { st = "bad", lab = t("p_mtc_bad"), detail = string.format(t("d_mtc_bad"), want), prefs = true } end
    if not d.enabled then return { st = "warn", lab = t("p_mtc_dis"), detail = string.format(t("d_mtc_dis"), d.name), prefs = true } end
    return { st = true, lab = t("p_mtc_ok"), detail = string.format(t("d_mtc_ok"), d.name) }
  end

  -- pistes voulues par les réglages : {{name, kind}}
  function M.wanted()
    local w = {}
    if M.parse_ltc(get("gma3_ltc_output")) then w[#w + 1] = { name = TRACK_LTC, kind = "ltc" } end
    if M.mtc_name() then w[#w + 1] = { name = TRACK_MTC, kind = "mtc" } end
    return w
  end

  function M.check_tracks(tracks)
    tracks = tracks or M.tc_tracks()
    local want = M.wanted()
    if #want == 0 then
      if next(tracks) then return { st = "warn", lab = t("p_tr_old"), detail = t("d_tr_old"), fix = "tracks" } end
      return { st = false, lab = t("p_tr_off"), detail = t("d_tr_off") }
    end
    local missing, names, old = {}, {}, false
    local seen = {}
    for _, w in ipairs(want) do
      local e = tracks[w.name]
      seen[w.name] = true
      if not e or not e.gen then missing[#missing + 1] = w.name
      else
        names[#names + 1] = w.name
        if e.n > 1 or (e.key ~= "" and e.key ~= M.template_key(w.kind)) then old = true end
      end
    end
    for name in pairs(tracks) do if not seen[name] then old = true end end
    if #missing > 0 then
      return { st = "bad", lab = t("p_tr_bad"), detail = string.format(t("d_tr_bad"), table.concat(missing, ", ")), fix = "tracks" }
    end
    if old then return { st = "warn", lab = t("p_tr_old"), detail = t("d_tr_old"), fix = "tracks" } end
    return { st = true, lab = t("p_tr_ok"), detail = string.format(t("d_tr_ok"), table.concat(names, ", ")) }
  end

  function M.memo()
    local tc = M.tc_start()
    local fps = M.fps_label()
    local lines = {}
    for _, w in ipairs(M.wanted()) do
      if not M.template_ok(w.kind) then
        lines[#lines + 1] = string.format(t(w.kind == "mtc" and "memo_mtc" or "memo_ltc"), w.name, fps, tc)
      end
    end
    if #lines == 0 then return nil end
    lines[#lines + 1] = ""
    lines[#lines + 1] = t("memo_end")
    return table.concat(lines, "\n")
  end

  function M.check_generator()
    local want = M.wanted()
    if #want == 0 then return { st = false, lab = t("p_gen_off"), detail = t("d_gen_off") } end
    for _, w in ipairs(want) do
      if not M.template_ok(w.kind) then return { st = "warn", lab = t("p_gen_todo"), detail = t("d_gen_todo"), memo = true } end
    end
    return { st = true, lab = t("p_gen_ok"), detail = string.format(t("d_gen_ok"), M.fps_label(), (M.tc_start())) }
  end

  local checks, checks_t = nil, -1e9
  function M.checks(force)
    local now = reaper.time_precise()
    if force or not checks or now - checks_t > 1.0 then
      local tr = M.tc_tracks()
      checks = { ltc = M.check_ltc(), mtc = M.check_mtc(), tracks = M.check_tracks(tr), gen = M.check_generator() }
      checks_t = now
    end
    return checks
  end

  -- cues : bloc « lighting » publié (export) ou régions -----------------------------------------------
  local function list_regions()
    local out, k = {}, 0
    while reaper.EnumProjectMarkers3 do
      local ok, isrgn, pos, rend, name = reaper.EnumProjectMarkers3(0, k)
      if not ok or ok == 0 then break end
      if isrgn then out[#out + 1] = { start = pos, stop = rend, name = name or "" } end
      k = k + 1
    end
    table.sort(out, function(a, b) return a.start < b.start end)
    return out
  end

  -- « Refrain », « Refrain » -> « Refrain », « Refrain (2) » (lighting.unique)
  local function unique(names)
    local used, out = {}, {}
    for _, n in ipairs(names) do
      local cand, k = n, 2
      while used[cand] do cand = string.format("%s (%d)", n, k); k = k + 1 end
      used[cand] = true
      out[#out + 1] = cand
    end
    return out
  end

  function M.cues_from_regions(c, concert)
    local regs = list_regions()
    local out, by_song, order = {}, {}, {}
    for _, r in ipairs(regs) do
      local si, song = 1, nil
      if concert and c and c.songs then
        si = L.song_index(c, r.start)
        song = c.songs[si] and c.songs[si].title
      end
      local name = r.name
      if song then name = name:gsub("^" .. song:gsub("%p", "%%%0") .. "%s*·%s*", "") end
      name = name:gsub("^%s+", ""):gsub("%s+$", "")
      if name == "" then name = "Cue" end
      if not by_song[si] then by_song[si] = {}; order[#order + 1] = si end
      table.insert(by_song[si], { name = name, t = r.start, song = song, track = si - 1 })
    end
    for _, si in ipairs(order) do
      local list = by_song[si]
      local names = {}
      for _, q in ipairs(list) do names[#names + 1] = q.name end
      names = unique(names)
      for k, q in ipairs(list) do q.n = k; q.name = names[k]; out[#out + 1] = q end
    end
    return out
  end

  local data = { key = nil, t = -1e9 }
  local function decode_lighting(src)
    local d = src and R.json_decode(src)
    local lg = type(d) == "table" and d.lighting or nil
    if type(lg) ~= "table" or type(lg.cues) ~= "table" then return nil end
    return lg
  end

  -- {cues = {{n, name, t, song, track}}, source = "export" | "regions" | nil, lighting = bloc publié, stale}
  function M.load(force)
    local now = reaper.time_precise()
    if not force and data.info and now - data.t < 2 then return data.info end
    data.t = now
    local c, concert = ctx.c, ctx.is_concert
    local src, path
    if concert and c then
      path = c.prompter
      src = path and L.read(path)
    else
      path = reaper.GetResourcePath() .. SEP .. "reaper_www_root" .. SEP .. "reacue_song.json"
      local pub = ctx.tabs and ctx.tabs.song and ctx.tabs.song.published_info and ctx.tabs.song.published_info()
      src = pub and L.read(path) or nil
      if src and src:find('"concert"%s*:%s*{') then src = nil end
    end
    if src ~= data.src then data.src = src; data.lg = decode_lighting(src) end
    local info = { concert = concert and c ~= nil }
    local regs = M.cues_from_regions(c, concert)
    local lg = data.lg
    if lg and #lg.cues > 0 then
      info.source, info.lighting = "export", lg
      local cues = {}
      for _, q in ipairs(lg.cues) do
        cues[#cues + 1] = { n = tonumber(q.n) or #cues + 1, name = tostring(q.name or ""), t = tonumber(q.t) or 0,
                            song = q.song, track = tonumber(q.track) or 0 }
      end
      info.cues = cues
      local fps_f = tonumber(lg.fps)
      info.stale = (fps_f and math.abs(fps_f - M.fps()) > 0.001) or (lg.tc_start and lg.tc_start ~= (M.tc_start()))
        or (#regs > 0 and #regs ~= #cues)
    elseif #regs > 0 then
      info.source, info.cues = "regions", regs
    else
      info.cues = {}
    end
    data.info = info
    return info
  end

  -- cue en cours : le dernier dont le temps est passé
  function M.current(cues, pos)
    local k = nil
    for i, q in ipairs(cues) do if q.t <= pos + 1e-3 then k = i end end
    return k
  end

  -- dossier grandMA3 ------------------------------------------------------------------------------
  -- nom de Sequence grandMA3 (lighting.clean_name) : ASCII, lettres / chiffres et « _ »
  local ASCII = {}
  for cp, a in pairs({ [0xC0] = "A", [0xC1] = "A", [0xC2] = "A", [0xC3] = "A", [0xC4] = "A", [0xC5] = "A", [0xC7] = "C",
    [0xC8] = "E", [0xC9] = "E", [0xCA] = "E", [0xCB] = "E", [0xCC] = "I", [0xCD] = "I", [0xCE] = "I", [0xCF] = "I",
    [0xD1] = "N", [0xD2] = "O", [0xD3] = "O", [0xD4] = "O", [0xD5] = "O", [0xD6] = "O", [0xD9] = "U", [0xDA] = "U",
    [0xDB] = "U", [0xDC] = "U", [0xDD] = "Y" }) do ASCII[cp] = a; ASCII[cp + 32] = a:lower() end
  ASCII[0xFF] = "y"
  function M.clean_name(name, default)
    local s = tostring(name or "")
    local ok, out = pcall(function()
      local b = {}
      for _, cp in utf8.codes(s) do
        if cp < 128 then b[#b + 1] = utf8.char(cp) elseif ASCII[cp] then b[#b + 1] = ASCII[cp] end
      end
      return table.concat(b)
    end)
    s = (ok and out or s):gsub("[^A-Za-z0-9]+", "_"):gsub("^_+", ""):gsub("_+$", "")
    if s == "" then s = default or "Song" end
    if s:match("^%d") then s = "Seq_" .. s end
    return s
  end

  local function dir_exists(d)
    if not d or d == "" then return false end
    if reaper.EnumerateFiles and reaper.EnumerateFiles(d, 0) then return true end
    if reaper.EnumerateSubdirectories and reaper.EnumerateSubdirectories(d, 0) then return true end
    return false
  end

  -- dossier de l'export : <dossier du .RPP>/grandMA3 (morceau) ou …/grandMA3/<Concert> ; nil s'il n'existe pas
  function M.folder()
    local file = (ctx.is_concert and ctx.c and ctx.c.rpp) or ctx.proj_file or ""
    local dir = file:match("^(.*)[/\\][^/\\]+$")
    if not dir then return nil end
    local base = dir .. SEP .. "grandMA3"
    if ctx.is_concert and ctx.c then
      local sub = base .. SEP .. M.clean_name(ctx.c.name, "Concert")
      if dir_exists(sub) then return sub end
    end
    if dir_exists(base) then return base end
    return nil
  end

  -- actions ------------------------------------------------------------------------------------
  local function done_cb()
    return function(state, msg)
      data.t, checks = -1e9, nil
      ctx.show_result(state == "done" and T("done_title") or T("error_title"), msg, state == "done")
    end
  end

  function M.make_tracks()
    if not can_edit() then return false end
    return ctx.start_cli("timecode", t("job_tracks"), done_cb())
  end

  function M.export_now()
    if not can_edit() then return false end
    if get("gma3_export") == false then ctx.show_result(T("error_title"), t("export_disabled"), true) return false end
    if ctx.is_concert and ctx.c and ctx.c.setlist then
      local q = R.is_windows() and R.winq(ctx.c.setlist) or R.shq(ctx.c.setlist)
      return ctx.start_cli("concert-lighting --setlist " .. q, t("job_export"), done_cb())
    end
    return ctx.start_cli("publish", t("job_export"), done_cb())
  end

  function M.open_folder()
    local d = M.folder()
    if not d then ctx.show_result(t("open_folder"), t("no_folder"), true) return nil end
    ctx.guide.open_path(d)
    return d
  end

  -- envoi de 10 s de test : pistes TIMECODE seules (solo), état rétabli à l'identique -----------------
  local test = nil
  local from_start = reaper.GetExtState("ReaCue", "light_from") == "start"
  function M.test_active() return test ~= nil end
  function M.test_state() return test end

  local function valid(tr, proj)
    if reaper.ValidatePtr2 then return reaper.ValidatePtr2(proj, tr, "MediaTrack*") end
    return true
  end
  local function setv(tr, k, v)
    if reaper.GetMediaTrackInfo_Value(tr, k) ~= v then reaper.SetMediaTrackInfo_Value(tr, k, v) end
  end

  -- from_start : début du morceau (concert : du morceau en cours), sinon position actuelle
  function M.test_start(from_start)
    if test then return M.test_stop("user") end
    if not can_edit() then return false end
    local st = reaper.GetPlayState()
    if (st & 4) == 4 then return false, t("t_rec") end
    if L.reh and L.reh.on then return false, t("t_reh") end
    local n_tc = 0
    for i = 0, reaper.CountTracks(0) - 1 do if TC_NAMES[track_name(reaper.GetTrack(0, i))] then n_tc = n_tc + 1 end end
    if n_tc == 0 then return false, t("no_tracks") end
    local proj = reaper.EnumProjects(-1, "")
    local was = ((st & 2) == 2 and "pause") or ((st & 1) == 1 and "play") or "stop"
    test = { t0 = reaper.time_precise(), proj = proj, play = was, cursor = reaper.GetCursorPosition(),
             pos = (was ~= "stop") and reaper.GetPlayPosition() or nil, tracks = {} }
    local start
    if from_start then
      start = 0
      if ctx.is_concert and ctx.c then
        local s = ctx.c.songs[L.song_index(ctx.c, L.pos())]
        start = s and s.start or 0
      end
    else
      start = L.pos()
    end
    test.start = start
    for i = 0, reaper.CountTracks(0) - 1 do
      local tr = reaper.GetTrack(0, i)
      local e = { tr = tr, solo = reaper.GetMediaTrackInfo_Value(tr, "I_SOLO"), mute = reaper.GetMediaTrackInfo_Value(tr, "B_MUTE") }
      test.tracks[#test.tracks + 1] = e
      if TC_NAMES[track_name(tr)] then
        setv(tr, "I_SOLO", 1)
        setv(tr, "B_MUTE", 0)
      else
        setv(tr, "I_SOLO", 0)
        -- piste qui ignore le solo (« solo defeat ») : coupée le temps du test
        if reaper.GetMediaTrackInfo_Value(tr, "B_SOLO_DEFEAT") == 1 then setv(tr, "B_MUTE", 1) end
      end
    end
    ctx.tc_test = true
    if was ~= "stop" then reaper.OnStopButton() end
    reaper.SetEditCurPos(start, false, false)
    reaper.OnPlayButton()
    return true
  end

  -- why : "done" (10 s écoulées), "user" (2e appui), "stopped" (Stop dans REAPER), "exit" (fermeture)
  function M.test_stop(why)
    local s = test
    if not s then return false end
    test = nil
    ctx.tc_test = nil
    local same = reaper.EnumProjects(-1, "") == s.proj
    if same and L.play_state() ~= "stop" then reaper.OnStopButton() end
    for _, e in ipairs(s.tracks) do
      if valid(e.tr, s.proj) then
        setv(e.tr, "I_SOLO", e.solo)
        setv(e.tr, "B_MUTE", e.mute)
      end
    end
    if same then
      if s.play == "play" then
        reaper.SetEditCurPos(s.pos, false, false)
        reaper.OnPlayButton()
        reaper.SetEditCurPos(s.cursor, false, false)
      elseif s.play == "pause" then
        reaper.SetEditCurPos(s.pos, false, false)
        reaper.OnPlayButton()
        reaper.OnPauseButton()
        reaper.SetEditCurPos(s.cursor, false, false)
      else
        reaper.SetEditCurPos(s.cursor, false, false)
      end
    end
    if why ~= "exit" then
      ctx.flash = { txt = why == "done" and t("t_done") or t("t_stopped"), t = reaper.time_precise() }
    end
    return true
  end

  -- secondes restantes du test en cours (nil : pas de test) ; publié pour ReaCue Studio (ExtState ReaCue/tctest)
  function M.test_left(now)
    if not test then return nil end
    return math.max(0, math.ceil(M.TEST_S - ((now or reaper.time_precise()) - test.t0)))
  end

  -- télécommande (ReaCue Studio, écran Lumière / Concert : « TEST 10 S ») : lance ou arrête le test ;
  -- arg "start" (début du morceau), "cursor" (position actuelle) ou "" (choix de l'onglet Lumière)
  function M.remote_test(arg)
    if test then return M.test_stop("user") end
    local fs = from_start
    if arg == "start" then fs = true elseif arg == "cursor" then fs = false end
    local ok, why = M.test_start(fs)
    if not ok and why then ctx.flash = { txt = why, t = reaper.time_precise(), bad = true } end
    return ok and true or false
  end

  -- appelé à chaque image, quel que soit l'onglet
  function M.tick(now)
    if not test then return end
    now = now or reaper.time_precise()
    if reaper.EnumProjects(-1, "") ~= test.proj then M.test_stop("stopped") return end
    if now - test.t0 >= M.TEST_S then M.test_stop("done") return end
    if now - test.t0 > 0.3 and L.play_state() == "stop" then M.test_stop("stopped") end
  end

  function M.enter()
    data.t, checks = -1e9, nil
    local st = ST()
    if st and st.load then st.load() end
  end
  function M.project_changed() data = { t = -1e9 }; checks = nil end

  -- dessin -------------------------------------------------------------------------------------
  local scroll = 0
  local function ui() return ST() and ST().ui end

  local function draw_infos(x, y, w)
    local info = M.load()
    local fps = M.fps()
    local tc, off = M.tc_start()
    local head = t("infos")
    if info.source then head = head .. "  ·  " .. t(info.source == "export" and "src_export" or "src_regions") end
    U.heading(U.fit(head, w, 12), x, y)
    y = y + 20
    -- timecode actuel
    local pos = L.pos()
    local playing = L.playing()
    local now_tc = M.smpte(off + pos, fps)
    U.panel(x, y, w, 40, U.INSET)
    U.set(playing and U.LED or U.GREY); gfx.circle(x + 10, y + 9, 3, 1, 1)
    U.text(U.upper(t("tc_now")), x + 18, y + 4, 9, U.MUTED)
    U.text(now_tc, x + 12, y + 15, 20, playing and U.SMPTE or U.INK2, false, "mono")
    local sub = string.format(t("tc_sub"), L.fmt_time(pos), tc, M.fps_label(fps))
    local tw = U.text_w(now_tc, 20, false, "mono") + 30
    local sw = w - tw - 18
    if sw > 120 then
      local sub_f = U.fit(sub, sw, 11)
      U.text(sub_f, x + w - U.text_w(sub_f, 11) - 10, y + 22, 11, U.MUTED)
      y = y + 48
    else
      y = y + 44
      U.text(U.fit(sub, w, 11), x, y, 11, U.MUTED)
      y = y + 18
    end
    -- messages
    local msg, col
    if get("gma3_export") == false then msg, col = t("export_off"), U.WARN
    elseif info.source == "regions" then msg, col = t("not_exported"), U.WARN
    elseif info.source == "export" and info.stale then msg, col = t("stale"), U.WARN end
    if #info.cues == 0 then
      local m = (ctx.c or (ctx.proj_file or "") ~= "") and t("none_regions") or t("none_project")
      y = y + U.para(m, x, y, w, 12, U.MUTED, 3) + 6
      if msg and get("gma3_export") == false then y = y + U.para(msg, x, y, w, 12, col, 3) + 6 end
      return y
    end
    if msg then y = y + U.para(msg, x, y, w, 12, col, 3) + 4 end
    -- liste
    local cues = info.cues
    local cur = M.current(cues, pos)
    local ROWH = 22
    local maxrows = w >= 500 and 8 or 6
    local n = #cues
    local vis = math.min(n, maxrows)
    if playing and cur and (cur <= scroll or cur > scroll + vis) then scroll = cur - 1 end
    if U.over(x, y, w, vis * ROWH + 18) and U.wheel ~= 0 then scroll = scroll + (U.wheel > 0 and -1 or 1) end
    scroll = math.max(0, math.min(math.max(0, n - vis), scroll))
    local cn = U.text_w("000", 12, false, "mono") + 10
    local ctc = U.text_w("00:00:00:00", 12, false, "mono") + 16
    U.text(U.upper(t("col_n")), x + 6, y, 10, U.MUTED)
    U.text(U.upper(t("col_tc")), x + 6 + cn, y, 10, U.MUTED)
    U.text(U.upper(t("col_name")), x + 6 + cn + ctc, y, 10, U.MUTED)
    y = y + 16
    local last_song = nil
    for k = 1, vis do
      local i = k + scroll
      local q = cues[i]
      local yy = y + (k - 1) * ROWH
      local here = i == cur
      local past = cur and i < cur
      if here then U.set(playing and U.NOW or U.PANEL)
      else U.set(U.PANEL2) end
      gfx.rect(x, yy, w, ROWH - 3, 1)
      if here then U.set(playing and U.SIG or U.BLUE); gfx.rect(x, yy, 3, ROWH - 3, 1) end
      U.text(tostring(q.n), x + 6, yy + 3, 12, here and U.SIG or U.MUTED, false, "mono")
      U.text(M.smpte(off + q.t, fps), x + 6 + cn, yy + 3, 12, here and U.LCD or (past and U.GREY or U.INK2), false, "mono")
      local nm = q.name
      if info.concert and q.song and q.song ~= last_song then nm = q.song .. "  ·  " .. nm end
      last_song = q.song
      U.text(U.fit(nm, w - cn - ctc - 12, 12, here), x + 6 + cn + ctc, yy + 3, 12, here and U.INK or U.INK2, here)
      U.tip(x, yy, w, ROWH - 3, string.format("Cue %d · %s · %s", q.n, M.smpte(off + q.t, fps), q.name), "lcue" .. i)
    end
    y = y + vis * ROWH
    if n > vis then U.text(string.format(t("rows"), scroll + 1, scroll + vis, n), x, y, 11, U.MUTED); y = y + 16 end
    return y + 6
  end

  local function choose_ltc()
    local outs = M.audio_outputs()
    local cur = M.parse_ltc(get("gma3_ltc_output"))
    local items, vals = { (cur and "" or "!") .. t("none_f") }, { false }
    local function clean(s) return (tostring(s):gsub("[|&<>!#]", "")) end
    for i, name in ipairs(outs) do
      local on = cur and not cur.b and cur.a == i
      items[#items + 1] = (on and "!" or "") .. string.format("%d · %s", i, clean(name))
      vals[#vals + 1] = i
    end
    if #outs >= 2 then
      items[#items] = items[#items] .. "|"                 -- séparateur avant les paires (non compté)
      for i = 1, #outs - 1, 2 do
        local on = cur and cur.b and cur.a == i
        items[#items + 1] = (on and "!" or "") .. string.format("%d/%d · %s / %s", i, i + 1, clean(outs[i]), clean(outs[i + 1]))
        vals[#vals + 1] = string.format("%d/%d", i, i + 1)
      end
    end
    gfx.x, gfx.y = gfx.mouse_x, gfx.mouse_y
    local c = gfx.showmenu(table.concat(items, "|"))
    if not c or c < 1 or vals[c] == nil then return end
    set("gma3_ltc_output", vals[c] or nil)
    checks = nil
  end

  local function choose_mtc()
    local list = M.midi_outputs()
    local cur = M.mtc_name()
    local items, vals = { (cur and "" or "!") .. t("none_m") }, { false }
    for _, d in ipairs(list) do
      local nm = d.name:gsub("[|&<>!#]", "")
      if not d.enabled then nm = string.format(t("disabled"), nm) end
      items[#items + 1] = ((cur and cur:lower() == d.name:lower()) and "!" or "") .. nm
      vals[#vals + 1] = d.name
    end
    gfx.x, gfx.y = gfx.mouse_x, gfx.mouse_y
    local c = gfx.showmenu(table.concat(items, "|"))
    if not c or c < 1 or vals[c] == nil then return end
    set("gma3_mtc_output", vals[c] or nil)
    checks = nil
  end

  local function ask_tc()
    local cur = M.tc_start()
    local ok, v = reaper.GetUserInputs(t("tc_title"), 1, t("tc_field") .. ",extrawidth=60", cur)
    if not ok then return end
    local fps = M.fps()
    local s = M.parse_tc(v, fps)
    if not s then reaper.ShowMessageBox(string.format(t("tc_bad"), jsround(fps)), T("title"), 0) return end
    local h, mi, se, fr = v:match("^%s*(%d+)[:;%.](%d+)[:;%.](%d+)[:;%.]?(%d*)%s*$")
    set("gma3_tc_start", string.format("%02d:%02d:%02d:%02d", tonumber(h), tonumber(mi), tonumber(se), tonumber(fr) or 0))
    checks = nil
  end

  local function ask_secs(key, title, field, allow_empty)
    local cur = get(key)
    local ok, v = reaper.GetUserInputs(t(title), 1, t(field) .. ",extrawidth=40", cur and tostring(cur) or "")
    if not ok then return end
    v = (v or ""):gsub("%s", ""):gsub(",", ".")
    if v == "" and allow_empty then set(key, nil) return end
    local n = tonumber(v)
    if not n or n < 0 or n ~= n or n == math.huge then reaper.ShowMessageBox(t("num_bad"), T("title"), 0) return end
    if n == math.floor(n) then n = math.floor(n) end
    set(key, n)
  end

  local function fmt_secs(n)
    local s = (n == math.floor(n)) and string.format("%d", n) or string.format("%g", n)
    if L.lang() == "fr" then s = s:gsub("%.", ",") end
    return string.format(t("secs"), s)
  end

  local function draw_config(x, y, w)
    local K = ui()
    if not K then return y end
    local cx = x + math.floor(w * K.LW)
    local cw = w - math.floor(w * K.LW)
    local row = 32
    local v, ch
    U.heading(t("config"), x, y); y = y + 20
    K.label(t("export"), x, y, w)
    v, ch = K.seg("l_export", cx, y, cw, { { true, t("on") }, { false, t("off") } }, get("gma3_export") ~= false)
    if ch then set("gma3_export", v); data.t = -1e9 end
    y = y + row
    K.label(t("fps"), x, y, w)
    local opts = {}
    for _, f in ipairs(M.FPS) do opts[#opts + 1] = { f, M.fps_label(f) } end
    v, ch = K.seg("l_fps", cx, y, cw, opts, M.fps(), 12)
    if ch then set("gma3_fps", v); checks = nil end
    y = y + row
    K.label(t("tc_start"), x, y, w)
    if U.button("l_tcstart", (M.tc_start()), cx, y, cw, 26, nil, 13) then ask_tc() end
    y = y + row
    K.label(t("slot"), x, y, w)
    local sl = M.slot()
    v, ch = K.stepper("l_slot", cx, y, cw, sl, string.format(t("slot_n"), sl), 1, 1, 8)
    if ch then set("gma3_tc_slot", v) end
    y = y + row
    K.label(t("ltc"), x, y, w)
    local o = M.parse_ltc(get("gma3_ltc_output"))
    local lt = t("none_f")
    if o then
      local outs = M.audio_outputs()
      lt = o.label .. ((outs[o.a] and not o.b) and ("  ·  " .. outs[o.a]) or "")
      if (o.b or o.a) > #outs then lt = string.format(t("absent"), o.label) end
    end
    if U.button("l_ltc", U.fit(lt, cw - 12, 12), cx, y, cw, 26, nil, 12) then choose_ltc() end
    y = y + row
    K.label(t("mtc"), x, y, w)
    local mn = M.mtc_name()
    local mt = t("none_m")
    if mn then
      local d = M.find_midi(mn)
      mt = (not d and string.format(t("absent"), mn)) or (not d.enabled and string.format(t("disabled"), d.name)) or d.name
    end
    if U.button("l_mtc", U.fit(mt, cw - 12, 12), cx, y, cw, 26, nil, 12) then choose_mtc() end
    y = y + row
    -- concert : placement des morceaux (concert.py)
    K.label(t("gap"), x, y, w)
    local gap = tonumber(get("gma3_song_gap"))
    if U.button("l_gap", gap and fmt_secs(gap) or t("gap_default"), cx, y, cw, 26, nil, 12) then
      ask_secs("gma3_song_gap", "gap_title", "gap_field", true)
    end
    y = y + row
    K.label(t("song_slot"), x, y, w)
    local ss = tonumber(get("gma3_song_slot")) or 0
    if U.button("l_songslot", ss > 0 and fmt_secs(ss) or t("slot_off"), cx, y, cw, 26, nil, 12) then
      ask_secs("gma3_song_slot", "sslot_title", "sslot_field", false)
    end
    y = y + row
    y = y + U.para(t("note"), x, y, w, 11, U.MUTED, 3) + 2
    local st = ST()
    if st and st.saved_at and reaper.time_precise() - st.saved_at() < 2 then
      U.text(t("saved"), x + w - U.text_w(t("saved"), 12, true), y, 12, U.ACCENT, true)
      y = y + 16
    end
    return y + 6
  end

  local function draw_actions(x, y, w)
    U.heading(t("actions"), x, y); y = y + 20
    local busy = ctx.job ~= nil
    local list = { { "l_tracks", t("make_tracks") }, { "l_export_now", t("export_now") }, { "l_folder", t("open_folder") } }
    local bx = x
    for _, b in ipairs(list) do
      local bw = math.min(w, U.text_w(b[2], 12) + 26)
      if bx > x and bx + bw > x + w then bx = x; y = y + 34 end
      local style = (b[1] == "l_export_now" and get("gma3_export") == false) and "ghost" or nil
      if U.button(b[1], b[2], bx, y, bw, 28, style, 12) and not busy then
        if b[1] == "l_tracks" then M.make_tracks()
        elseif b[1] == "l_export_now" then M.export_now()
        else M.open_folder() end
        return y + 34, true
      end
      bx = bx + bw + 6
    end
    return y + 40
  end

  local function draw_test(x, y, w)
    U.heading(t("test"), x, y); y = y + 20
    local C = M.checks()
    local px = x
    for _, k in ipairs({ "ltc", "mtc", "tracks", "gen" }) do
      local c = C[k]
      local lab = c.lab
      local pw = U.text_w(lab, 12, true) + 26
      if px > x and px + pw > x + w then px = x; y = y + 28 end
      local _, clk = U.chip("lpill_" .. k, lab, c.st, px, y)
      if U.hover == "lpill_" .. k then U.hover_tip = c.detail end
      if clk and not ctx.job then
        if k == "ltc" then choose_ltc()
        elseif k == "mtc" and c.prefs then reaper.Main_OnCommand(40016, 0)      -- Préférences
        elseif k == "mtc" and c.st == false then choose_mtc()
        elseif k == "tracks" and c.fix then M.make_tracks()
        elseif k == "gen" and c.memo then ctx.show_result(t("memo_title"), M.memo() or "", true) end
        return y + 28
      end
      px = px + pw + 6
    end
    y = y + 32
    local K = ui()
    local active = M.test_active()
    local sw = math.min(math.floor(w * 0.5), 260)
    if K and not active then
      local v, ch = K.seg("l_from", x, y, sw, { { false, t("from_cursor") }, { true, t("from_start") } }, from_start, 11)
      if ch then from_start = v; reaper.SetExtState("ReaCue", "light_from", v and "start" or "", true) end
    end
    local lab
    if active then
      lab = string.format(t("stop_test"), math.max(0, math.ceil(M.TEST_S - (reaper.time_precise() - test.t0))))
    else
      lab = t("send_test")
    end
    if U.is_armed("l_test") then lab = T("again") end
    local bw = math.max(U.text_w(lab, 13) + 30, 150)
    local bx = active and x or (x + sw + 8)
    if bx + bw > x + w then bx = x; y = y + 32 end
    local style = active and "armed" or (U.is_armed("l_test") and "armed" or "primary")
    if U.button("l_test", lab, bx, y, math.min(bw, w), 28, style, 13) then
      if active then M.test_stop("user")
      elseif U.confirm("l_test", L.play_state() ~= "stop") then
        local ok, why = M.test_start(from_start)
        if not ok and why then ctx.show_result(T("error_title"), why, true) end
      end
    end
    if U.hover == "l_test" and not active and L.play_state() ~= "stop" then U.hover_tip = t("t_playing") end
    y = y + 36
    y = y + U.para(string.format(t("oneway"), M.slot()), x, y, w, 12, U.MUTED, 5) + 4
    if ctx.flash and reaper.time_precise() - ctx.flash.t < 3 then
      U.text(U.fit(ctx.flash.txt, w, 12), x, y, 12, ctx.flash.bad and U.WARN or U.ACCENT, true)
      y = y + 18
    end
    return y
  end

  function M.draw(x, y, w)
    if ctx.job then y = y + ctx.draw_job(x, y, w) end
    y = draw_infos(x, y, w) + 4
    y = draw_config(x, y, w) + 2
    local acted
    y, acted = draw_actions(x, y, w)
    if acted then return y end
    return draw_test(x, y, w) + 4
  end

  return M
end
