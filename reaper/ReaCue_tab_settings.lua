-- ReaCue : onglet « Réglages » / “Settings” tab : reacue_settings.json sans éditer le fichier.
-- Remplacement protégé, champs inconnus gardés ; s'applique à la prochaine préparation.
-- Vue Modèles (stems, structure, paroles, accords, batterie), puis Live et système
-- (décompte, annonces, voix, sorties ; réglages avancés : volumes, tempo, dossiers, CPU…) ;
-- « Vérifier l'installation » ouvre l'assistant du premier lancement.
return function(ctx)
  local L, U, T, R, SEP = ctx.L, ctx.U, ctx.T, ctx.R, ctx.SEP
  local TXT = {
    fr = {
      performance = "Performances", standard = "Standard", fast = "Rapide", cpu_threads = "Threads CPU",
      fast_note = "Rapide : séparation moins lissée, contexte de structure réduit, transcription simplifiée. Qualité à vérifier.",
      general = "Général", cues = "Décompte et annonces", outputs = "Click et voix", other = "Performances et dossiers",
      models = "Modèles avant préparation", models_tab = "Modèles", live_tab = "Live et système",
      models_note = "Choix mémorisés. Les modèles avancés restent facultatifs, même installés.",
      lyrics = "Paroles", essential = "Essentiel", enhanced = "Avancé", disabled = "Désactivé", custom = "Personnalisé",
      lyrics_essential = "Whisper small · synchronisation par ligne",
      lyrics_enhanced = "Whisper large-v3-turbo · calage mot par mot",
      lyrics_disabled = "Transcription et calage mot par mot désactivés. Les paroles fournies restent utilisables.",
      lyrics_custom = "Choix personnalisés conservés : %s · %s",
      lines = "par ligne", words = "mot par mot", model_present = "Modèle présent", model_missing = "Modèle à installer",
      component_missing = "Moteur de paroles à installer", words_missing = "Calage mot par mot à installer",
      chords = "Accords", chords_auto = "Modèles installés / repli ReaCue", rules = "ReaCue seul",
      drums = "Batterie", drums_standard = "ADTOF · équilibré", drums_advanced = "ADT_STR · avancé", drums_auto = "Auto · ADTOF / ReaCue",
      language = "Langue", count_in = "Décompte avant le morceau", cue_lead = "Annonce avant la section",
      bars_n = "%d mes.", count_lang = "Décompte", voice_cues = "Annonces vocales", count_in_voice = "Décompte parlé",
      announce_voice = "Voix des annonces", count_voice = "Voix du décompte", auto = "auto",
      hw = "Sortie click + voix", hw_none = "sortie principale", hw_pair = "sorties %d/%d",
      to_master = "Aussi en façade", click_vol = "Volume du click", voice_vol = "Volume des voix",
      tempo = "Tempo", tempo_auto = "auto", tempo_constant = "fixe", tempo_beatmap = "variable",
      stems = "Séparation de stems", stems6 = "6 stems · guitare et piano", stems4_ft = "4 stems HQ · plus lent", stems4 = "4 stems · équilibré",
      structure = "Détection de structure", structure_auto = "auto (SongFormer)", structure_reacue = "ReaCue seul",
      structure_on = "SongFormer installé", structure_off = "SongFormer non installé",
      projects_dir = "Dossier des projets", concert_dir = "Dossier des concerts", default = "par défaut",
      dir_title = "ReaCue - Dossier", dir_field = "Dossier (vide = par défaut) :",
      pin = "Code PIN de la Régie", on = "oui", off = "non",
      note = "Les changements s'appliquent à la prochaine préparation (« Analyser et préparer », « Re-préparer » ou « Reconstruire » le concert).",
      version = "Version installée : %s", saved = "enregistré",
      save_failed = "Enregistrement impossible. Les réglages précédents sont conservés.",
      noncommercial = "Usage non commercial uniquement (MuQ : CC BY-NC 4.0)",
      licences = "Licences", licences_tip = "Composants tiers, licences et avertissements",
      simple = "Réglages simples", advanced = "Réglages avancés", check_install = "Vérifier l'installation",
      count_rate = "Débit du décompte", rate_n = "%d mots/min", announce = "Annonces", install_sf = "Installer",
    },
    en = {
      performance = "Performance", standard = "Standard", fast = "Fast", cpu_threads = "CPU threads",
      fast_note = "Fast: less separation smoothing, shorter structure context, simpler transcription. Check quality.",
      general = "General", cues = "Count-in and spoken cues", outputs = "Click and voice", other = "Performance and folders",
      models = "Models before preparation", models_tab = "Models", live_tab = "Live and system",
      models_note = "Choices are saved. Advanced models stay optional, even when installed.",
      lyrics = "Lyrics", essential = "Essential", enhanced = "Advanced", disabled = "Disabled", custom = "Custom",
      lyrics_essential = "Whisper small · line timing",
      lyrics_enhanced = "Whisper large-v3-turbo · word timing",
      lyrics_disabled = "Transcription and word timing disabled. Supplied lyrics can still be used.",
      lyrics_custom = "Custom choices preserved: %s · %s",
      lines = "line timing", words = "word timing", model_present = "Model present", model_missing = "Model to install",
      component_missing = "Lyrics engine to install", words_missing = "Word timing to install",
      chords = "Chords", chords_auto = "Installed models / ReaCue fallback", rules = "ReaCue only",
      drums = "Drums", drums_standard = "ADTOF · balanced", drums_advanced = "ADT_STR · advanced", drums_auto = "Auto · ADTOF / ReaCue",
      language = "Language", count_in = "Count-in before the song", cue_lead = "Cue before the section",
      bars_n = "%d bars", count_lang = "Count", voice_cues = "Spoken cues", count_in_voice = "Spoken count-in",
      announce_voice = "Cue voice", count_voice = "Count voice", auto = "auto",
      hw = "Click + voice output", hw_none = "main output", hw_pair = "outputs %d/%d",
      to_master = "Also to front of house", click_vol = "Click volume", voice_vol = "Voice volume",
      tempo = "Tempo", tempo_auto = "auto", tempo_constant = "fixed", tempo_beatmap = "variable",
      stems = "Stem separation", stems6 = "6 stems · guitar and piano", stems4_ft = "4 stems HQ · slower", stems4 = "4 stems · balanced",
      structure = "Structure detection", structure_auto = "auto (SongFormer)", structure_reacue = "ReaCue only",
      structure_on = "SongFormer installed", structure_off = "SongFormer not installed",
      projects_dir = "Projects folder", concert_dir = "Concerts folder", default = "default",
      dir_title = "ReaCue - Folder", dir_field = "Folder (empty = default):",
      pin = "Stage control PIN code", on = "yes", off = "no",
      note = "Changes apply at the next preparation (“Analyse and prepare”, “Prepare again” or “Rebuild” the concert).",
      version = "Installed version: %s", saved = "saved",
      save_failed = "Could not save. Previous settings are preserved.",
      noncommercial = "Non-commercial use only (MuQ: CC BY-NC 4.0)",
      licences = "Licences", licences_tip = "Third-party components, licences and disclaimers",
      simple = "Simple settings", advanced = "Advanced settings", check_install = "Check the installation",
      count_rate = "Count speed", rate_n = "%d words/min", announce = "Spoken cues", install_sf = "Install",
    },
  }
  local function t(k) return ctx.tr(TXT, k) end
  local M = {}
  local DEFAULTS = {
    language = "fr", announce_voice = nil, count_voice = nil, count_lang = "en", count_in_bars = 2, cue_lead_bars = 2,
    voice_cues = true, voice_count_in = true, voice_count_each = true, voice_volume = 0.8, click_volume = 0.5,
    click_to_master = true, click_hw_output = nil, tempo_mode = "auto", stems_model = "htdemucs",
    performance_profile = "standard", cpu_threads = 0,
    structure_engine = "auto", projects_dir = nil, concert_dir = nil, count_rate = 240,
    lyrics_auto = "auto", lyrics_model = "small", words_engine = "off", words_language = "auto",
    chords_engine = "auto", drums_engine = "adtof",
    -- lumière grandMA3 (onglet Lumière)
    gma3_export = true, gma3_fps = 25, gma3_tc_start = "00:00:00:00", gma3_tc_slot = 1, gma3_song_slot = 0,
  }
  local data = nil
  local voices = nil
  local saved_t = -1e9
  local save_failed = false

  local function path() return R.SETTINGS end

  function M.load()
    local d = R.json_decode(L.read(path()) or "")
    data = type(d) == "table" and d or {}
    return data
  end

  local function get(k)
    if not data then M.load() end
    local v = data[k]
    if v == nil then v = DEFAULTS[k] end
    return v
  end

  local function save()
    local order = { "language", "announce_voice", "count_voice", "count_lang", "count_in_bars", "cue_lead_bars",
      "voice_cues", "voice_count_in", "voice_count_each", "voice_volume", "click_volume", "click_to_master",
      "click_hw_output", "tempo_mode", "count_rate", "stems_model", "structure_engine", "performance_profile", "cpu_threads", "projects_dir", "concert_dir",
      "lyrics_auto", "lyrics_model", "words_engine", "words_language", "chords_engine", "drums_engine",
      "gma3_export", "gma3_fps", "gma3_tc_start", "gma3_song_gap", "gma3_song_slot", "gma3_ltc_output",
      "gma3_mtc_output", "gma3_tc_slot" }
    reaper.RecursiveCreateDirectory(reaper.GetResourcePath() .. SEP .. "ReaCueMCP", 0)
    local ok = R.write_atomic(path(), R.json_encode(data, "  ", order) .. "\n")
    save_failed = not ok
    if ok then saved_t = reaper.time_precise() end
    return ok
  end

  function M.set(k, v)
    if not data then M.load() end
    local old = data[k]
    data[k] = v
    if save() then return true end
    data[k] = old
    return false
  end

  function M.lyrics_profile()
    local auto, model, words = get("lyrics_auto"), get("lyrics_model"), get("words_engine")
    if auto == "off" and words == "off" then return "off" end
    if auto == "auto" and model == "small" and words == "off" then return "essential" end
    if auto == "auto" and model == "large-v3-turbo" and words == "auto" then return "advanced" end
    return "custom"
  end

  function M.set_lyrics_profile(profile)
    if profile ~= "essential" and profile ~= "advanced" and profile ~= "off" then return false end
    if not data then M.load() end
    local old_auto, old_model, old_words = data.lyrics_auto, data.lyrics_model, data.words_engine
    data.lyrics_auto = profile == "off" and "off" or "auto"
    data.words_engine = profile == "advanced" and "auto" or "off"
    if profile ~= "off" then data.lyrics_model = profile == "advanced" and "large-v3-turbo" or "small" end
    if save() then return true end -- le profil entier est écrit atomiquement
    data.lyrics_auto, data.lyrics_model, data.words_engine = old_auto, old_model, old_words
    return false
  end

  function M.model_summary()
    local stems = get("stems_model") == "htdemucs" and t("stems4") or
      (get("stems_model") == "htdemucs_ft" and t("stems4_ft") or t("stems6"))
    local p = M.lyrics_profile()
    local lyrics = ({ essential = t("essential"), advanced = t("enhanced"), off = t("disabled"), custom = t("custom") })[p]
    return stems .. " · " .. t("lyrics") .. " : " .. lyrics
  end

  function M.lyrics_status()
    local dir = R.install_dir(ctx.dir)
    local words_dir = os.getenv("REACUE_WORDS_DIR") or (dir .. SEP .. "words")
    local stem = words_dir .. SEP .. "whisper" .. SEP .. get("lyrics_model")
    if not L.exists(stem .. ".pt") and not L.exists(stem .. "-hf.pt") then return "model_missing" end
    local py = dir .. (R.is_windows() and "\\.venv-words\\Scripts\\python.exe" or "/.venv-words/bin/python")
    if not L.exists(py) or not L.exists(dir .. SEP .. "reacue_transcribe.py") then return "component_missing" end
    if get("words_engine") == "off" then return "model_present" end
    if not L.exists(dir .. SEP .. "reacue_words.py") then return "words_missing" end
    local function ctc_files(path)
      return L.exists(path .. SEP .. "config.json") and L.exists(path .. SEP .. "vocab.json") and
        (L.exists(path .. SEP .. "model.safetensors") or L.exists(path .. SEP .. "pytorch_model.bin"))
    end
    local caches = { words_dir .. SEP .. "hf" .. SEP .. "hub" }
    local hf_cache, hf_home = os.getenv("HF_HUB_CACHE"), os.getenv("HF_HOME")
    if hf_cache then caches[#caches + 1] = hf_cache end
    if hf_home then caches[#caches + 1] = hf_home .. SEP .. "hub" end
    local home_dir = os.getenv("HOME") or os.getenv("USERPROFILE")
    if home_dir then caches[#caches + 1] = home_dir .. SEP .. ".cache" .. SEP .. "huggingface" .. SEP .. "hub" end
    local function ctc_present(lang)
      if ctc_files(words_dir .. SEP .. "models" .. SEP .. lang) then return true end
      local model = "models--jonatasgrosman--wav2vec2-large-xlsr-53-" .. (lang == "fr" and "french" or "english")
      local revision = os.getenv("REACUE_WORDS_REVISION") or "main"
      for _, cache in ipairs(caches) do
        local base = cache .. SEP .. model
        local ref = L.read(base .. SEP .. "refs" .. SEP .. revision)
        ref = ref and ref:match("^%s*(%S+)") or revision
        if ctc_files(base .. SEP .. "snapshots" .. SEP .. ref) then return true end
      end
      return false
    end
    local lang = get("words_language")
    if lang == "auto" then
      if not ctc_present("fr") or not ctc_present("en") then return "words_missing" end
    elseif not ctc_present(lang) then return "words_missing" end
    return "model_present"
  end

  -- lecture d'un réglage (défaut si absent) ; instant du dernier enregistrement (« enregistré »)
  function M.get(k) return get(k) end
  function M.saved_at() return saved_t end

  function M.enter() M.load() end
  function M.project_changed() end

  -- voix système : macOS « say -v ? », Windows SAPI (PowerShell, sans fenêtre) ; sinon saisie libre
  local function list_voices()
    if voices then return voices end
    voices = {}
    if not reaper.ExecProcess then return voices end
    if R.is_windows() then
      local cmd = 'powershell -NoProfile -NonInteractive -Command "Add-Type -AssemblyName System.Speech; ' ..
        '(New-Object System.Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices() | % { $_.VoiceInfo.Name }"'
      local out = reaper.ExecProcess(cmd, 5000) or ""
      for line in out:gmatch("[^\r\n]+") do
        if not line:match("^%-?%d+$") and line:match("%S") then voices[#voices + 1] = { name = line:gsub("%s+$", ""), lang = "" } end
      end
    else
      local out = reaper.ExecProcess("/usr/bin/say -v ?", 5000) or ""
      for line in out:gmatch("[^\r\n]+") do
        local name, lang = line:match("^(.-)%s+([a-z][a-z][_%-]%a%a)%s+#")
        if name then voices[#voices + 1] = { name = name, lang = lang } end
      end
    end
    return voices
  end

  local function choose_voice(key, pref)
    local vs = list_voices()
    local items, map = { t("auto") }, { false }
    local first = {}
    for _, v in ipairs(vs) do if pref and v.lang:sub(1, 2) == pref then first[#first + 1] = v end end
    for _, v in ipairs(vs) do if not pref or v.lang:sub(1, 2) ~= pref then first[#first + 1] = v end end
    for _, v in ipairs(first) do
      items[#items + 1] = (v.name:gsub("[|&<>!#]", "")) .. (v.lang ~= "" and ("  (" .. v.lang .. ")") or "")
      map[#map + 1] = v.name
    end
    if #vs == 0 then
      local ok, v = reaper.GetUserInputs(t(key), 1, t(key) .. ",extrawidth=120", get(key) or "")
      if ok then M.set(key, (v and v ~= "") and v or nil) end
      return
    end
    gfx.x, gfx.y = gfx.mouse_x, gfx.mouse_y
    local c = gfx.showmenu(table.concat(items, "|"))
    if not c or c < 1 then return end
    M.set(key, map[c] or nil)
  end

  local function choose_hw()
    local n = reaper.GetNumAudioOutputs and reaper.GetNumAudioOutputs() or 2
    local items, vals = { t("hw_none") }, { false }
    for ch = 0, math.max(2, n) - 1, 2 do
      items[#items + 1] = string.format(t("hw_pair"), ch + 1, ch + 2)
      vals[#vals + 1] = ch
    end
    gfx.x, gfx.y = gfx.mouse_x, gfx.mouse_y
    local c = gfx.showmenu(table.concat(items, "|"))
    if not c or c < 1 then return end
    M.set("click_hw_output", vals[c] or nil)
  end

  local function choose_dir(key)
    local cur = get(key) or ""
    local v
    if reaper.JS_Dialog_BrowseForFolder then
      local ok, d = reaper.JS_Dialog_BrowseForFolder(t(key), cur)
      if ok ~= 1 then return end
      v = d
    else
      local ok, d = reaper.GetUserInputs(t("dir_title"), 1, t("dir_field") .. ",extrawidth=260", cur)
      if not ok then return end
      v = d
    end
    v = (v or ""):gsub("^%s+", ""):gsub("%s+$", "")
    M.set(key, v ~= "" and v or nil)
  end

  local function version()
    local src = L.read(L.install_dir() .. SEP .. "reacue_mcp" .. SEP .. "__init__.py") or ""
    return src:match('__version__%s*=%s*"([^"]+)"') or "?"
  end

  -- une ligne : libellé à gauche, contrôles à droite ; renvoie y suivant
  local LW = 0.46
  local function label(s, x, y, w) U.text(U.fit(s, w * LW - 8, 13), x, y + 5, 13, U.INK) end

  local function seg(id, x, y, w, opts, cur, size)
    local n = #opts
    local gap = 4
    local bw = (w - (n - 1) * gap) / n
    for k, o in ipairs(opts) do
      if U.button(id .. k, o[2], x + (k - 1) * (bw + gap), y, bw, 26, (cur == o[1]) and "on" or nil, size or 12) then
        return o[1], true
      end
    end
    return cur, false
  end

  local function stepper(id, x, y, w, val, txt, step, lo, hi)
    if U.ibutton(id .. "m", "left", x, y, 30, 26) then val = math.max(lo, val - step); return val, true end
    U.set(U.PANEL2); gfx.rect(x + 34, y, w - 68, 26, 1)
    local tw = U.text_w(txt, 13, true)
    U.text(txt, x + 34 + (w - 68 - tw) / 2, y + 5, 13, U.INK, true)
    if U.ibutton(id .. "p", "right", x + w - 30, y, 30, 26) then val = math.min(hi, val + step); return val, true end
    return val, false
  end

  -- contrôles partagés avec l'onglet Lumière (même mise en page)
  M.ui = { label = label, seg = seg, stepper = stepper, LW = LW }

  local function choice(id, key, x, y, w, opts)
    local cur = get(key)
    local shown = tostring(cur or "")
    for _, o in ipairs(opts) do if cur == o[1] then shown = o[2] end end
    local clicked = U.button(id, U.fit(shown, w - 24, 12), x, y, w, 26, nil, 12)
    U.set(U.MUTED); gfx.triangle(x + w - 15, y + 11, x + w - 7, y + 11, x + w - 11, y + 15)
    if not clicked then return end
    local items = {}
    for _, o in ipairs(opts) do items[#items + 1] = (cur == o[1] and "!" or "") .. o[2] end
    gfx.x, gfx.y = gfx.mouse_x, gfx.mouse_y
    local selected = gfx.showmenu(table.concat(items, "|"))
    if opts[selected] then M.set(key, opts[selected][1]) end
  end

  function M.draw_models(x, y, w)
    local cx, cw = x + math.floor(w * LW), w - math.floor(w * LW)
    local row = 32
    U.heading(t("models"), x, y); y = y + 20
    label(t("stems"), x, y, w)
    choice("stems", "stems_model", cx, y, cw, {
      { "htdemucs", t("stems4") }, { "htdemucs_6s", t("stems6") }, { "htdemucs_ft", t("stems4_ft") } })
    y = y + row
    label(t("structure"), x, y, w)
    local v, ch = seg("structure", cx, y, cw, { { "auto", t("structure_auto") }, { "reacue", t("structure_reacue") } },
      get("structure_engine"), 11)
    if ch then M.set("structure_engine", v) end
    y = y + row - 6
    local dir = R.install_dir(ctx.dir)
    local inst = R.structure_installed and R.structure_installed(dir)
    if inst then
      U.text(U.fit(t("structure_on"), cw, 11), cx, y, 11, U.ACCENT)
    else
      local ib = U.text_w(t("install_sf"), 11) + 16
      U.text(U.fit(t("structure_off"), cw - ib - 6, 11), cx, y + 2, 11, U.MUTED)
      if U.button("install_sf", t("install_sf"), cx + cw - ib, y - 2, ib, 20, nil, 11) then ctx.do_action("structure") end
      y = y + 4
    end
    y = y + 16
    y = y + U.para(t("noncommercial"), cx, y, cw, 11, U.WARN, 2) + 6
    label(t("lyrics"), x, y, w)
    v, ch = seg("lyrics_profile", cx, y, cw, {
      { "essential", t("essential") }, { "advanced", t("enhanced") }, { "off", t("disabled") } }, M.lyrics_profile(), 12)
    if ch then M.set_lyrics_profile(v) end
    y = y + row - 4
    local profile = M.lyrics_profile()
    local detail = profile == "custom" and string.format(t("lyrics_custom"), get("lyrics_model"),
      get("words_engine") == "off" and t("lines") or t("words")) or
      t(({ essential = "lyrics_essential", advanced = "lyrics_enhanced", off = "lyrics_disabled" })[profile])
    y = y + U.para(detail, cx, y, cw, 11, U.MUTED) + 4
    if get("lyrics_auto") ~= "off" then
      local status = M.lyrics_status()
      local present = status == "model_present"
      U.text(t(status), cx, y, 11, present and U.ACCENT or U.WARN)
      if not present then
        local ib = U.text_w(t("install_sf"), 11) + 16
        if U.button("install_words", t("install_sf"), cx + cw - ib, y - 2, ib, 20, nil, 11) then ctx.do_action("words") end
      end
      y = y + 24
    end
    label(t("chords"), x, y, w)
    choice("chords", "chords_engine", cx, y, cw, {
      { "auto", t("chords_auto") }, { "reacue", t("rules") }, { "off", t("disabled") } })
    y = y + row
    label(t("drums"), x, y, w)
    choice("drums", "drums_engine", cx, y, cw, {
      { "adtof", t("drums_standard") }, { "adt-str", t("drums_advanced") },
      { "auto", t("drums_auto") }, { "reacue", t("rules") }, { "off", t("disabled") } })
    y = y + row
    return y + U.para(t("models_note"), x, y, w, 11, U.MUTED) + 10
  end

  function M.advanced() return reaper.GetExtState("ReaCue", "settings_adv") == "1" end
  function M.set_advanced(on) reaper.SetExtState("ReaCue", "settings_adv", on and "1" or "", true) end
  function M.page() return reaper.GetExtState("ReaCue", "settings_page") == "live" and "live" or "models" end
  function M.set_page(page) reaper.SetExtState("ReaCue", "settings_page", page == "live" and "live" or "models", true) end

  local function footer(x, y, w)
    if save_failed then y = y + U.para(t("save_failed"), x, y, w, 12, U.RED) + 4 end
    local h = U.para(t("note"), x, y, w, 12, U.MUTED)
    y = y + h + 4
    local st = (reaper.time_precise() - saved_t < 2) and t("saved") or ""
    U.text(U.fit(string.format(t("version"), version()), w - 200, 11), x, y, 11, U.MUTED)
    if U.button("licences", t("licences"), x + w - 190, y - 5, 96, 22, nil, 11) then M.open_licences() end
    if st ~= "" then U.text(st, x + w - U.text_w(st, 12, true), y, 12, U.ACCENT, true) end
    return y + 20
  end

  function M.draw(x, y, w)
    if not data then M.load() end
    local adv = M.advanced()
    local cx = x + math.floor(w * LW)
    local cw = w - math.floor(w * LW)
    local row = 32
    local v, ch

    v, ch = seg("settings_page", x, y, w, { { "models", t("models_tab") }, { "live", t("live_tab") } }, M.page(), 13)
    if ch then M.set_page(v) end
    y = y + 36

    -- vue simple / avancée, vérification de l'installation
    local b1 = U.text_w(t("check_install"), 12) + 22
    local b2 = U.text_w(adv and t("simple") or t("advanced"), 12) + 22
    if U.button("checkinst", t("check_install"), x, y - 2, b1, 26, nil, 12) then ctx.assistant.open(false) return y end
    if M.page() == "live" and U.button("adv", adv and t("simple") or t("advanced"), x + w - b2, y - 2, b2, 26, adv and "on" or nil, 12) then
      M.set_advanced(not adv) return y
    end
    y = y + 36

    if M.page() == "models" then return footer(x, M.draw_models(x, y, w), w) end

    U.heading(t("general"), x, y); y = y + 20
    label(t("language"), x, y, w)
    v, ch = seg("lang", cx, y, cw, { { "fr", "Français" }, { "en", "English" } }, get("language"))
    if ch then M.set("language", v) end
    y = y + row
    if adv then
      label(t("pin"), x, y, w)
      if U.button("setpin", L.remote_pin(), cx, y, cw, 26, nil, 13) then ctx.change_pin() end
      y = y + row
    end
    y = y + 6

    U.heading(t("cues"), x, y); y = y + 20
    label(t("count_in"), x, y, w)
    local n = math.floor(tonumber(get("count_in_bars")) or 2)
    v, ch = stepper("cin", cx, y, cw, n, string.format(t("bars_n"), n), 1, 0, 4)
    if ch then M.set("count_in_bars", v) end
    y = y + row
    label(t("voice_cues"), x, y, w)
    v, ch = seg("vcues", cx, y, cw, { { true, t("on") }, { false, t("off") } }, get("voice_cues") ~= false)
    if ch then M.set("voice_cues", v) end
    y = y + row
    label(t("count_in_voice"), x, y, w)
    v, ch = seg("vcount", cx, y, cw, { { true, t("on") }, { false, t("off") } }, get("voice_count_in") ~= false)
    if ch then M.set("voice_count_in", v) end
    y = y + row
    label(t("announce_voice"), x, y, w)
    if U.button("avoice", get("announce_voice") or t("auto"), cx, y, cw, 26, nil, 12) then choose_voice("announce_voice", get("language")) end
    y = y + row
    if adv then
      label(t("cue_lead"), x, y, w)
      n = math.floor(tonumber(get("cue_lead_bars")) or 2)
      v, ch = stepper("cue", cx, y, cw, n, string.format(t("bars_n"), n), 1, 1, 4)
      if ch then M.set("cue_lead_bars", v) end
      y = y + row
      label(t("count_lang"), x, y, w)
      v, ch = seg("clang", cx, y, cw, { { "en", "one two three four" }, { "fr", "un deux trois quatre" } }, get("count_lang"), 11)
      if ch then M.set("count_lang", v) end
      y = y + row
      label(t("count_voice"), x, y, w)
      if U.button("cvoice", get("count_voice") or t("auto"), cx, y, cw, 26, nil, 12) then choose_voice("count_voice", get("count_lang")) end
      y = y + row
      label(t("count_rate"), x, y, w)
      local cr = math.floor(tonumber(get("count_rate")) or 240)
      v, ch = stepper("count_rate", cx, y, cw, cr, string.format(t("rate_n"), cr), 20, 120, 360)
      if ch then M.set("count_rate", v) end
      y = y + row
    end
    y = y + 6

    U.heading(t("outputs"), x, y); y = y + 20
    label(t("hw"), x, y, w)
    local hw = tonumber(get("click_hw_output"))
    local hwtxt = hw and string.format(t("hw_pair"), hw + 1, hw + 2) or t("hw_none")
    if U.button("hw", hwtxt, cx, y, cw, 26, nil, 12) then choose_hw() end
    y = y + row
    label(t("to_master"), x, y, w)
    v, ch = seg("master", cx, y, cw, { { true, t("on") }, { false, t("off") } }, get("click_to_master") ~= false)
    if ch then M.set("click_to_master", v) end
    y = y + row
    if adv then
      for _, k in ipairs({ { "click_volume", "click_vol" }, { "voice_volume", "voice_vol" } }) do
        label(t(k[2]), x, y, w)
        local vol = tonumber(get(k[1])) or 0.5
        v, ch = stepper(k[1], cx, y, cw, vol, string.format("%d %%", math.floor(vol * 100 + 0.5)), 0.1, 0, 1)
        if ch then M.set(k[1], math.floor(v * 10 + 0.5) / 10) end
        y = y + row
      end
    end
    y = y + 6

    if adv then
      U.heading(t("other"), x, y); y = y + 20
      label(t("performance"), x, y, w)
      v, ch = seg("performance_profile", cx, y, cw, { { "standard", t("standard") }, { "fast", t("fast") } }, get("performance_profile"), 11)
      if ch then M.set("performance_profile", v) end
      y = y + row
      if get("performance_profile") == "fast" then
        y = y + U.para(t("fast_note"), cx, y, cw, 11, U.WARN, 4) + 4
      end
      label(t("cpu_threads"), x, y, w)
      v, ch = seg("cpu_threads", cx, y, cw, { { 0, t("auto") }, { 1, "1" }, { 2, "2" }, { 4, "4" }, { 8, "8" } }, get("cpu_threads"), 11)
      if ch then M.set("cpu_threads", v) end
      y = y + row
      label(t("tempo"), x, y, w)
      v, ch = seg("tempo", cx, y, cw, { { "auto", t("tempo_auto") }, { "constant", t("tempo_constant") }, { "beatmap", t("tempo_beatmap") } },
        get("tempo_mode"), 11)
      if ch then M.set("tempo_mode", v) end
      y = y + row
      for _, k in ipairs({ "projects_dir", "concert_dir" }) do
        label(t(k), x, y, w)
        local cur = get(k)
        local shown = cur and U.fit_path("", cur, cw - 12, 11) or
          U.fit_path(t("default") .. " · ", k == "projects_dir" and L.projects_dir() or L.concert_dir(), cw - 12, 11)
        if U.button("dir_" .. k, shown, cx, y, cw, 26, nil, 11) then choose_dir(k) end
        y = y + row
      end
    end
    y = y + 4
    return footer(x, y, w)
  end

  -- « Licences » : THIRD_PARTY_NOTICES.md du dossier d'installation, sinon la page GitHub
  M.LICENCES_URL = "https://github.com/herve8940/reacue/blob/main/THIRD_PARTY_NOTICES.md"
  function M.licences_target()
    local dir = R.install_dir and R.install_dir(ctx.dir) or nil
    local f = dir and (dir .. SEP .. "THIRD_PARTY_NOTICES.md")
    if f and L.exists(f) then return f end
    return M.LICENCES_URL
  end
  function M.open_licences()
    local target = M.licences_target()
    if R.is_windows() then
      reaper.ExecProcess('cmd.exe /C start "" ' .. R.winq(target), -1)
    elseif (reaper.GetOS and reaper.GetOS() or ""):match("^OSX") or (reaper.GetOS and reaper.GetOS() or ""):match("^macOS") then
      os.execute("open " .. R.shq(target))
    else
      os.execute("xdg-open " .. R.shq(target) .. " &")
    end
    return target
  end

  return M
end
