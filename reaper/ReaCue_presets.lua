-- Presets utilisateur : périmètres explicites, stockage séparé, aucune préparation automatique.
return function(ctx, settings)
  local R, L, U = ctx.R, ctx.L, ctx.U
  local M = { scopes = { live = true, models = false, lighting = false } }
  local function tr(fr, en) return L.lang() == "fr" and fr or en end
  local GROUPS = {
    live = { "language", "announce_voice", "count_voice", "count_lang", "count_in_bars", "cue_lead_bars",
      "voice_cues", "voice_count_in", "voice_count_each", "voice_volume", "click_volume", "click_to_master", "click_hw_output", "count_rate" },
    models = { "tempo_mode", "stems_model", "structure_engine", "lyrics_auto", "lyrics_model", "words_engine",
      "words_language", "chords_engine", "drums_engine", "performance_profile", "cpu_threads" },
    lighting = { "gma3_export", "gma3_fps", "gma3_tc_start", "gma3_tc_slot", "gma3_song_gap", "gma3_song_slot",
      "gma3_ltc_output", "gma3_mtc_output" },
  }
  M.path = R.SETTINGS:gsub("[^/\\]+$", "reacue_presets.json")
  local function guard()
    if ctx.require_edit and not ctx.require_edit() then return false end
    if ctx.is_locked and ctx.is_locked() then return false end
    if ctx.job or (ctx.flow and ctx.flow.run and not ctx.flow.run.finished) or
      (ctx.flow and ctx.flow.batch_active and ctx.flow.batch_active()) or
      (ctx.jobs and ctx.jobs.busy and ctx.jobs.busy()) or (R.active_job and R.active_job()) or
      (reaper.GetPlayState and reaper.GetPlayState() ~= 0) then
      return false, tr("Arrête la lecture et attends la fin de la préparation.", "Stop playback and wait for preparation to finish.")
    end
    return true
  end
  local function load()
    local raw = L.read(M.path)
    if not raw then
      if L.exists(M.path) then return nil, tr("Presets illisibles : fichier conservé.", "Cannot read presets: file kept.") end
      return { version = 1, presets = {}, trash = {} }
    end
    local d = R.json_decode(raw)
    if type(d) ~= "table" or d.version ~= 1 or type(d.presets) ~= "table" or type(d.trash) ~= "table" then
      return nil, tr("Fichier de presets invalide : aucune modification.", "Invalid presets file: nothing changed.")
    end
    local function valid(p)
      return type(p) == "table" and type(p.scopes) == "table" and type(p.values) == "table" and type(p.unset) == "table"
        and (p.outputs == nil or type(p.outputs) == "table")
    end
    for name, p in pairs(d.presets) do
      if type(name) ~= "string" or not valid(p) then return nil, tr("Preset invalide : fichier conservé.", "Invalid preset: file kept.") end
    end
    for _, p in pairs(d.trash) do
      if type(p) ~= "table" or type(p.name) ~= "string" or not valid(p.preset) then return nil, tr("Corbeille invalide : fichier conservé.", "Invalid trash: file kept.") end
    end
    return d
  end
  local function save(d)
    reaper.RecursiveCreateDirectory(reaper.GetResourcePath() .. ctx.SEP .. "ReaCueMCP", 0)
    if not R.write_atomic(M.path, R.json_encode(d, "  ") .. "\n") then
      return false, tr("Enregistrement impossible. Les presets précédents sont conservés.", "Could not save. Previous presets are kept.")
    end
    return true
  end
  local function name_ok(name)
    return type(name) == "string" and name ~= "" and #name <= 120 and not name:find("[%z\1-\31\127]")
      and name == name:gsub("^[ \t]+", ""):gsub("[ \t]+$", "")
  end
  local function keys(scopes)
    local out = {}
    for group, enabled in pairs(scopes or {}) do
      if enabled and GROUPS[group] then for _, key in ipairs(GROUPS[group]) do out[key] = true end end
    end
    return out
  end
  local function names(d)
    local out = {}; for name in pairs(d.presets) do out[#out + 1] = name end; table.sort(out); return out
  end
  function M.list() local d, err = load(); return d and names(d) or {}, err end
  function M.describe(name)
    local d, err = load(); if not d then return nil, err end
    local p = d.presets[name]; if type(p) ~= "table" then return nil, tr("Preset introuvable.", "Preset not found.") end
    local labels = {}
    for _, g in ipairs({ "live", "models", "lighting" }) do
      if p.scopes and p.scopes[g] then labels[#labels + 1] = ({live = tr("Click, voix et routage", "Click, cues and routing"),
        models = tr("Modèles", "Models"), lighting = tr("Lumière", "Lighting")})[g] end
    end
    return table.concat(labels, " · "), p
  end
  function M.preview(name)
    local desc, p = M.describe(name); if not desc then return nil end
    local out, v = {name, desc, ""}, p.values
    if p.scopes.live then
      local ch = tonumber(v.click_hw_output)
      out[#out+1] = tr("Sortie click/voix : ", "Click/cue output: ") .. (ch and (ch+1).."/"..(ch+2) or tr("principale", "main"))
      out[#out+1] = tr("Aussi en façade : ", "Also to master: ") .. (v.click_to_master and tr("oui", "yes") or tr("non", "no"))
      out[#out+1] = tr("Décompte : ", "Count-in: ") .. tostring(v.count_in_bars or 2) .. tr(" mesures", " bars")
      out[#out+1] = tr("Annonces : ", "Cues: ") .. (v.voice_cues and tr("oui", "yes") or tr("non", "no")) .. " · " .. tostring(v.language or "fr")
    end
    if p.scopes.models then
      out[#out+1] = "Stems : " .. tostring(v.stems_model)
      out[#out+1] = "Structure : " .. tostring(v.structure_engine)
      out[#out+1] = tr("Paroles : ", "Lyrics: ") .. tostring(v.lyrics_model) .. " · " .. tostring(v.lyrics_auto)
    end
    if p.scopes.lighting then
      out[#out+1] = "LTC : " .. tostring(v.gma3_ltc_output or "—") .. " · MTC : " .. tostring(v.gma3_mtc_output or "—")
      out[#out+1] = tostring(v.gma3_fps or 25) .. " fps · " .. tostring(v.gma3_tc_start or "00:00:00:00")
    end
    return table.concat(out, "\n")
  end
  local function remember_outputs(p)
    p.outputs = {}
    local function channel(i)
      local name = reaper.GetOutputChannelName and reaper.GetOutputChannelName(i)
      if name and name ~= "" then p.outputs[tostring(i)] = name end
    end
    local v = p.values
    if type(v.click_hw_output) == "number" then channel(v.click_hw_output); channel(v.click_hw_output + 1) end
    if v.gma3_ltc_output then
      for n in tostring(v.gma3_ltc_output):gmatch("%d+") do channel(tonumber(n) - 1) end
    end
  end
  function M.create(name, scopes)
    local ok, err = guard(); if not ok then return false, err end
    if not name_ok(name) then return false, tr("Nom vide, trop long ou invalide.", "Empty, too long or invalid name.") end
    local d; d, err = load(); if not d then return false, err end
    if d.presets[name] then return false, tr("Ce nom existe déjà.", "This name already exists.") end
    local chosen = {}; for g in pairs(GROUPS) do if scopes and scopes[g] then chosen[g] = true end end
    if not next(chosen) then return false, tr("Choisis au moins un périmètre.", "Choose at least one scope.") end
    if settings.reload_checked then ok, err = settings.reload_checked(); if not ok then return false, err end end
    local p = { scopes = chosen, values = {}, unset = {} }
    for key in pairs(keys(chosen)) do
      local v = settings.get(key)
      if v == nil then p.unset[#p.unset + 1] = key else p.values[key] = v end
    end
    remember_outputs(p)
    d.presets[name] = p
    ok, err = save(d); if ok then M.selected = name end; return ok, err
  end
  function M.rename(old, name, duplicate)
    local ok, err = guard(); if not ok then return false, err end
    if not name_ok(name) then return false, tr("Nom invalide.", "Invalid name.") end
    local d; d, err = load(); if not d then return false, err end
    if not d.presets[old] then return false, tr("Preset introuvable.", "Preset not found.") end
    if d.presets[name] then return false, tr("Ce nom existe déjà.", "This name already exists.") end
    d.presets[name] = d.presets[old]; if not duplicate then d.presets[old] = nil end
    ok, err = save(d); if ok then M.selected = name end; return ok, err
  end
  function M.delete(name)
    local ok, err = guard(); if not ok then return false, err end
    local d; d, err = load(); if not d then return false, err end
    if not d.presets[name] then return false, tr("Preset introuvable.", "Preset not found.") end
    d.trash[#d.trash + 1] = { name = name, preset = d.presets[name] }; d.presets[name] = nil
    ok, err = save(d); if ok then M.selected = nil end; return ok, err
  end
  function M.restore()
    local ok, err = guard(); if not ok then return false, err end
    local d; d, err = load(); if not d then return false, err end
    local p = d.trash[#d.trash]
    if not p then return false, tr("Aucun preset à restaurer.", "No preset to restore.") end
    local name, n = p.name, 2
    while d.presets[name] do name = p.name .. " (" .. n .. ")"; n = n + 1 end
    d.presets[name] = p.preset; table.remove(d.trash)
    ok, err = save(d); if ok then M.selected = name end; return ok, err
  end
  local function outputs_ok(p)
    local v, count = p.values, reaper.GetNumAudioOutputs and reaper.GetNumAudioOutputs() or 0
    local function channel(i)
      if type(i) ~= "number" or i % 1 ~= 0 or i < 0 or i >= count then return false end
      local expected = p.outputs and p.outputs[tostring(i)]
      return not expected or (reaper.GetOutputChannelName and reaper.GetOutputChannelName(i) == expected)
    end
    local click = v.click_hw_output
    if click ~= nil and (not channel(click) or not channel(click + 1)) then
      return false, tr("Sorties click/voix absentes ou carte son différente. Vérifie le routage avant d'appliquer.",
        "Click/cue outputs missing or audio interface changed. Check routing before applying.")
    end
    if v.gma3_ltc_output then
      local light = ctx.tabs and ctx.tabs.lighting
      local out = light and light.parse_ltc(v.gma3_ltc_output)
      if not out or not channel(out.a - 1) or (out.b and not channel(out.b - 1)) then
        return false, tr("Sortie LTC absente ou différente.", "LTC output missing or changed.")
      end
    end
    if v.gma3_mtc_output and v.gma3_mtc_output ~= "" then
      local found = false
      for i = 0, (reaper.GetMaxMIDIOutputs and reaper.GetMaxMIDIOutputs() or 64) - 1 do
        if reaper.GetMIDIOutputName then
          local enabled, name = reaper.GetMIDIOutputName(i, "")
          if enabled and name == v.gma3_mtc_output then found = true break end
        end
      end
      if not found then return false, tr("Sortie MTC absente ou désactivée.", "MTC output missing or disabled.") end
    end
    return true
  end
  function M.apply(name)
    local ok, err = guard(); if not ok then return false, err end
    local _, p = M.describe(name)
    if type(p) ~= "table" or type(p.values) ~= "table" or type(p.unset) ~= "table" then
      return false, tr("Preset invalide ou introuvable.", "Invalid or missing preset.")
    end
    local allowed = keys(p.scopes)
    local enums = {
      language = "fr|en", count_lang = "fr|en", tempo_mode = "auto|constant|beatmap", stems_model = "htdemucs|htdemucs_6s|htdemucs_ft",
      structure_engine = "auto|reacue", lyrics_auto = "auto|off", lyrics_model = "small|large-v3-turbo", words_engine = "auto|off",
      words_language = "auto|fr|en", chords_engine = "auto|reacue|off", drums_engine = "auto|reacue|adtof|adt-str|off", performance_profile = "standard|fast",
    }
    local booleans = { voice_cues=true, voice_count_in=true, voice_count_each=true, click_to_master=true, gma3_export=true }
    local numbers = { count_in_bars={0,16}, cue_lead_bars={1,16}, voice_volume={0,1}, click_volume={0,1}, click_hw_output={0,511},
      count_rate={80,600}, cpu_threads={0,256}, gma3_fps={24,30}, gma3_tc_slot={1,8}, gma3_song_gap={0,86400}, gma3_song_slot={0,86400} }
    local fractional = { voice_volume=true, click_volume=true, gma3_fps=true, gma3_song_gap=true, gma3_song_slot=true }
    local strings = { announce_voice=true, count_voice=true, gma3_tc_start=true, gma3_mtc_output=true }
    for key, v in pairs(p.values) do
      local range = numbers[key]
      local enum_ok = not enums[key]
      if enums[key] then for choice in enums[key]:gmatch("[^|]+") do if choice == v then enum_ok = true end end end
      if not allowed[key] or (type(v) ~= "number" and type(v) ~= "string" and type(v) ~= "boolean") or
        not enum_ok or (strings[key] and type(v) ~= "string") or
        (booleans[key] and type(v) ~= "boolean") or
        (range and (type(v) ~= "number" or v ~= v or v < range[1] or v > range[2] or (not fractional[key] and v%1 ~= 0))) or
        (key == "gma3_fps" and v ~= 24 and v ~= 25 and v ~= 29.97 and v ~= 30) then
        return false, tr("Contenu du preset invalide.", "Invalid preset contents.")
      end
    end
    for _, key in ipairs(p.unset) do if not allowed[key] then return false, tr("Preset invalide.", "Invalid preset.") end end
    ok, err = outputs_ok(p); if not ok then return false, err end
    return settings.apply_values(p.values, p.unset)
  end
  local function report(ok, err)
    M.message = ok and tr("Enregistré. Les réglages s'appliquent à la prochaine préparation.",
      "Saved. Settings apply at the next preparation.") or err or tr("Action indisponible.", "Action unavailable.")
    M.bad = not ok
  end
  local function ask(default)
    local ok, name = reaper.GetUserInputs(tr("ReaCue - Nom du preset", "ReaCue - Preset name"), 1,
      tr("Nom :,extrawidth=180", "Name:,extrawidth=180"), default or "")
    return ok and name or nil
  end
  function M.draw(x, y, w)
    U.heading(tr("Presets personnels", "Personal presets"), x, y); y = y + 24
    y = y + U.para(tr("Enregistre les réglages actuels avec les périmètres cochés. Les autres réglages restent inchangés.",
      "Save the current settings for the checked scopes. Other settings stay unchanged."), x, y, w, 12, U.MUTED) + 8
    local bw = (w - 12) / 3
    for i, g in ipairs({ "live", "models", "lighting" }) do
      local label = ({live = tr("Click / voix", "Click / cues"), models = tr("Modèles", "Models"), lighting = tr("Lumière", "Lighting")})[g]
      if U.button("preset_scope_" .. g, (M.scopes[g] and "✓ " or "") .. label, x + (i-1)*(bw+6), y, bw, 28,
        M.scopes[g] and "on" or nil, 12) then M.scopes[g] = not M.scopes[g] end
    end
    y = y + 36
    if U.button("preset_create", tr("+ Enregistrer un preset", "+ Save a preset"), x, y, w, 28, nil, 12) then
      local name = ask(); if name then report(M.create(name, M.scopes)) end
    end
    y = y + 40
    local list, err = M.list()
    if err then y = y + U.para(err, x, y, w, 12, U.RED) + 8 end
    if U.button("preset_select", U.fit(M.selected or tr("Choisir un preset…", "Choose a preset…"), w-20, 13), x, y, w, 30, nil, 13) then
      local menu = {}; for _, name in ipairs(list) do menu[#menu+1] = name:gsub("[|<>!#]", " ") end
      if #menu > 0 then gfx.x, gfx.y = gfx.mouse_x, gfx.mouse_y; M.selected = list[gfx.showmenu(table.concat(menu, "|"))] or M.selected end
    end
    y = y + 38
    if M.selected then
      local desc = M.describe(M.selected)
      y = y + U.para(desc or "", x, y, w, 12, U.MUTED) + 8
      local actions = { {"apply", tr("Appliquer", "Apply")}, {"rename", tr("Renommer", "Rename")},
        {"duplicate", tr("Dupliquer", "Duplicate")}, {"delete", tr("Supprimer", "Delete")} }
      for i, a in ipairs(actions) do
        local col, row = (i-1)%2, math.floor((i-1)/2)
        if U.button("preset_" .. a[1], a[2], x+col*(w+6)/2, y+row*34, (w-6)/2, 28, a[1]=="apply" and "primary" or nil, 12) then
          if a[1] == "apply" then
            if reaper.ShowMessageBox((M.preview(M.selected) or M.selected) .. "\n\n" .. tr("Remplacer ces réglages ? Aucun calcul ne sera lancé.",
              "Replace these settings? No processing will start."), "ReaCue", 1) == 1 then report(M.apply(M.selected)) end
          elseif a[1] == "delete" then
            if reaper.ShowMessageBox(tr("Supprimer ce preset ? Il pourra être restauré.", "Delete this preset? It can be restored.") .. "\n\n" .. M.selected, "ReaCue", 1) == 1 then report(M.delete(M.selected)) end
          else local name = ask(a[1] == "duplicate" and (M.selected .. " (2)") or M.selected)
            if name then report(M.rename(M.selected, name, a[1] == "duplicate")) end
          end
        end
      end
      y = y + 76
    end
    if U.button("preset_restore", tr("Restaurer le dernier preset supprimé", "Restore the last deleted preset"), x, y, w, 28, nil, 12) then report(M.restore()) end
    y = y + 36
    if M.message then y = y + U.para(M.message, x, y, w, 12, M.bad and U.RED or U.ACCENT) + 8 end
    return y
  end
  return M
end
