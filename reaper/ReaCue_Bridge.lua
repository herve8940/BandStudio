-- ReaCue Bridge ---------------------------------------------------------------
-- Pont entre REAPER et le programme ReaCue (boutons REAPER ou serveur MCP pour Claude).
-- Lancé automatiquement au démarrage de REAPER (Scripts/__startup.lua, ajouté par l'installateur) ;
-- sinon : Actions > Load ReaScript > Run. Il tourne en tâche de fond et exécute les commandes
-- (données pures, jamais de code) déposées dans :
--   <dossier ressources REAPER>/ReaCueMCP/
-- Pour l'arrêter : relancer l'action, REAPER propose "Terminate instances".
-------------------------------------------------------------------------------

local VERSION   = "1.5.0"
local SEP       = package.config:sub(1, 1)
local DIR       = reaper.GetResourcePath() .. SEP .. "ReaCueMCP"
local REQ       = DIR .. SEP .. "request.lua"
local RES       = DIR .. SEP .. "response.json"
local HEARTBEAT = DIR .. SEP .. "heartbeat.txt"
local POLL      = 0.15 -- secondes

reaper.RecursiveCreateDirectory(DIR, 0)

-- Langue des messages (réglage "language" de reacue_settings.json) ------------
local LANG = "fr"
do
  local f = io.open(DIR .. SEP .. "reacue_settings.json", "rb")
  if f then
    local s = f:read("a"); f:close()
    local l = s and s:match('"language"%s*:%s*"(%a%a)')
    if l and l:lower() == "en" then LANG = "en" end
  end
end
local MSG = {
  no_audio = { fr = "Aucun item audio dans le projet. Importe d'abord le morceau (glisser-déposer).",
               en = "No audio item in the project. Import the song first (drag and drop)." },
  import_failed = { fr = "Import impossible : ", en = "Import failed: " },
  bad_voice = { fr = "Fichier vocal illisible : ", en = "Unreadable voice file: " },
  no_click = { fr = "Aucune source click insérée (action 40013 indisponible ?)",
               en = "No click source inserted (action 40013 unavailable?)" },
  item_missing = { fr = "Item audio introuvable (GUID ", en = "Audio item not found (GUID " },
  region_missing = { fr = "Région introuvable", en = "Region not found" },
  unknown_action = { fr = "action inconnue", en = "unknown action" },
  undo_fail = { fr = "ReaCue : échec", en = "ReaCue: failed" },
  undo_ok = { fr = "ReaCue : régions, cues et click", en = "ReaCue: regions, cues and click" },
  tc_chunk = { fr = "réglages mémorisés du générateur non appliqués", en = "remembered generator settings not applied" },
  undo_tc = { fr = "ReaCue : pistes timecode", en = "ReaCue: timecode tracks" },
}
local function T(k) return MSG[k][LANG] end

-- pistes créées par ReaCue (toutes langues) : jamais prises pour des stems, effacées à chaque préparation
local GENERATED = { CLICK = true, CUES = true, VOIX = true, VOICE = true,
                    ["TIMECODE LTC"] = true, ["TIMECODE MTC"] = true }
local TIMECODE = { ["TIMECODE LTC"] = true, ["TIMECODE MTC"] = true }
local TC_KEY = "P_EXT:reacue_tc_key"     -- réglages ReaCue (sorte, fps, départ) du générateur de la piste

-- JSON (encodeur minimal) ----------------------------------------------------
local function json_str(s)
  s = s:gsub('[%c"\\]', function(c)
    local map = { ['"'] = '\\"', ['\\'] = '\\\\', ['\n'] = '\\n', ['\r'] = '\\r', ['\t'] = '\\t' }
    return map[c] or string.format("\\u%04x", c:byte())
  end)
  return '"' .. s .. '"'
end

local function json(v)
  local t = type(v)
  if t == "nil" then return "null"
  elseif t == "boolean" then return v and "true" or "false"
  elseif t == "number" then
    if v ~= v or v == math.huge or v == -math.huge then return "null" end
    if math.type and math.type(v) == "integer" then return tostring(v) end
    return string.format("%.9g", v)
  elseif t == "string" then return json_str(v)
  elseif t == "table" then
    if next(v) == nil then return (getmetatable(v) == "object") and "{}" or "[]" end
    if #v > 0 then
      local out = {}
      for i = 1, #v do out[i] = json(v[i]) end
      return "[" .. table.concat(out, ",") .. "]"
    end
    local out = {}
    for k, val in pairs(v) do out[#out + 1] = json_str(tostring(k)) .. ":" .. json(val) end
    return "{" .. table.concat(out, ",") .. "}"
  end
  return json_str(tostring(v))
end

-- Utilitaires fichiers -------------------------------------------------------
local function read_file(p)
  local f = io.open(p, "rb"); if not f then return nil end
  local s = f:read("a"); f:close(); return s
end

local function write_atomic(p, s)
  local tmp = p .. ".tmp"
  local f = assert(io.open(tmp, "wb")); f:write(s); f:close()
  os.remove(p)
  assert(os.rename(tmp, p))
end

-- Helpers REAPER -------------------------------------------------------------
local function track_name(tr)
  local _, n = reaper.GetSetMediaTrackInfo_String(tr, "P_NAME", "", false)
  return n
end

local function find_track(name)
  for i = 0, reaper.CountTracks(0) - 1 do
    local tr = reaper.GetTrack(0, i)
    if track_name(tr) == name then return tr end
  end
end

local function new_track(name, at_top)
  local idx = at_top and 0 or reaper.CountTracks(0)
  reaper.InsertTrackAtIndex(idx, true)
  local tr = reaper.GetTrack(0, idx)
  reaper.GetSetMediaTrackInfo_String(tr, "P_NAME", name, true)
  return tr
end

local function item_guid(it)
  local _, g = reaper.GetSetMediaItemInfo_String(it, "GUID", "", false)
  return g
end

local function find_item(guid)
  for i = 0, reaper.CountMediaItems(0) - 1 do
    local it = reaper.GetMediaItem(0, i)
    if item_guid(it) == guid then return it end
  end
end

local function color(c)
  if not c then return 0 end
  return reaper.ColorToNative(c[1], c[2], c[3]) | 0x1000000
end

local function describe_item(it)
  local take = reaper.GetActiveTake(it)
  if not take then return nil end
  local src = reaper.GetMediaItemTake_Source(take)
  -- remonter aux sources "section"/"reverse" éventuelles
  local parent = reaper.GetMediaSourceParent and reaper.GetMediaSourceParent(src)
  while parent do src = parent; parent = reaper.GetMediaSourceParent(src) end
  local file = reaper.GetMediaSourceFileName(src, "")
  local tr = reaper.GetMediaItem_Track(it)
  return {
    guid      = item_guid(it),
    file      = file,
    position  = reaper.GetMediaItemInfo_Value(it, "D_POSITION"),
    length    = reaper.GetMediaItemInfo_Value(it, "D_LENGTH"),
    offset    = reaper.GetMediaItemTakeInfo_Value(take, "D_STARTOFFS"),
    rate      = reaper.GetMediaItemTakeInfo_Value(take, "D_PLAYRATE"),
    track     = track_name(tr),
    track_idx = math.floor(reaper.GetMediaTrackInfo_Value(tr, "IP_TRACKNUMBER")),
  }
end

-- Commandes ------------------------------------------------------------------
local H = {}

function H.ping()
  local _, proj_fn = reaper.EnumProjects(-1, "")
  return { bridge = VERSION, reaper = reaper.GetAppVersion(), project = proj_fn,
           items = reaper.CountMediaItems(0), tracks = reaper.CountTracks(0) }
end

-- Item audio à traiter : sélectionné, sinon premier item audio du projet.
function H.get_audio_item()
  local it = reaper.GetSelectedMediaItem(0, 0)
  local d = it and describe_item(it)
  if d and d.file ~= "" then d.selected = true; return d end
  for i = 0, reaper.CountMediaItems(0) - 1 do
    d = describe_item(reaper.GetMediaItem(0, i))
    if d and d.file ~= "" then d.selected = false; return d end
  end
  error(T("no_audio"))
end

-- Tous les items audio du projet (morceau en plusieurs stems, un par piste).
-- Les pistes générées par ReaCue (CLICK, CUES, VOIX) sont ignorées.
function H.get_audio_items()
  local skip = GENERATED
  local items, sel = {}, {}
  for i = 0, reaper.CountMediaItems(0) - 1 do
    local d = describe_item(reaper.GetMediaItem(0, i))
    if d and d.file ~= "" and not skip[d.track] then items[#items + 1] = d end
  end
  local listed = {}
  for _, d in ipairs(items) do listed[d.guid] = true end
  for i = 0, reaper.CountSelectedMediaItems(0) - 1 do
    local g = item_guid(reaper.GetSelectedMediaItem(0, i))
    if listed[g] then sel[#sel + 1] = g end
  end
  return { items = items, selected_guids = sel }
end

-- Importer un fichier sur une nouvelle piste (si l'utilisateur donne un chemin).
function H.import_file(a)
  local tr = find_track(a.track_name or "AUDIO") or new_track(a.track_name or "AUDIO", true)
  reaper.SetOnlyTrackSelected(tr)
  reaper.SetEditCurPos(a.position or 0, false, false)
  local ok = reaper.InsertMedia(a.file, 0)
  if ok == 0 then error(T("import_failed") .. a.file) end
  local it = reaper.GetTrackMediaItem(tr, reaper.CountTrackMediaItems(tr) - 1)
  return describe_item(it)
end

function H.get_state()
  local s = { markers = {}, regions = {}, tempo = {}, tracks = {} }
  local _, nm, nr = reaper.CountProjectMarkers(0)
  for i = 0, nm + nr - 1 do
    local _, isrgn, pos, rgnend, name, idx = reaper.EnumProjectMarkers(i)
    if isrgn then s.regions[#s.regions + 1] = { idx = idx, start = pos, ["end"] = rgnend, name = name }
    else s.markers[#s.markers + 1] = { idx = idx, pos = pos, name = name } end
  end
  for i = 0, reaper.CountTempoTimeSigMarkers(0) - 1 do
    local _, t, meas, beat, bpm, num, den = reaper.GetTempoTimeSigMarker(0, i)
    s.tempo[#s.tempo + 1] = { time = t, measure = meas, bpm = bpm, num = num, den = den }
  end
  for i = 0, reaper.CountTracks(0) - 1 do s.tracks[#s.tracks + 1] = track_name(reaper.GetTrack(0, i)) end
  return s
end

-- Générateur SMPTE LTC/MTC : bloc `<SOURCE LTC` … `>` d'un état d'item (GetItemStateChunk) ------------
-- Les champs de ce bloc ne sont pas documentés : ReaCue ne les écrit jamais lui-même, il recopie le
-- bloc réglé par l'utilisateur dans « Propriétés de la source ».
local function split_lines(s)
  local out = {}
  for line in (s .. "\n"):gmatch("(.-)\r?\n") do out[#out + 1] = line end
  return out
end

local function source_span(lines)
  local i0
  for i, l in ipairs(lines) do
    if l:match("^%s*<SOURCE LTC") then i0 = i; break end
  end
  if not i0 then return nil end
  local depth = 0
  for j = i0, #lines do
    local l = lines[j]:match("^%s*(.-)%s*$")
    if l:sub(1, 1) == "<" then depth = depth + 1 elseif l == ">" then depth = depth - 1 end
    if depth == 0 then return i0, j end
  end
  return nil
end

local function tc_source_block(chunk)
  local lines = split_lines(chunk or "")
  local a, b = source_span(lines)
  if not a then return nil end
  local out = {}
  for k = a, b do out[#out + 1] = lines[k]:match("^%s*(.-)%s*$") end
  return table.concat(out, "\n")
end

local function tc_replace_block(chunk, block)
  local lines = split_lines(chunk or "")
  local a, b = source_span(lines)
  local blk = split_lines(block or "")
  if not a or not blk[1] or not blk[1]:match("^%s*<SOURCE LTC") or not source_span(blk) then return nil end
  local out = {}
  for k = 1, a - 1 do out[#out + 1] = lines[k] end
  for _, l in ipairs(blk) do if l:match("%S") then out[#out + 1] = l end end
  for k = b + 1, #lines do out[#out + 1] = lines[k] end
  return table.concat(out, "\n")
end

-- pistes timecode existantes : {nom = {key, block}} (avant effacement), pour garder le réglage fait à la main
local function capture_timecode()
  local out = {}
  for i = 0, reaper.CountTracks(0) - 1 do
    local tr = reaper.GetTrack(0, i)
    local name = track_name(tr)
    if TIMECODE[name] and not out[name] then
      local _, key = reaper.GetSetMediaTrackInfo_String(tr, TC_KEY, "", false)
      local it = reaper.CountTrackMediaItems(tr) > 0 and reaper.GetTrackMediaItem(tr, 0)
      local block = nil
      if it then
        local ok, chunk = reaper.GetItemStateChunk(it, "", false)
        if ok then block = tc_source_block(chunk) end
      end
      out[name] = { key = key or "", block = block }
    end
  end
  return out
end

local function clear(plan)
  local _, nm, nr = reaper.CountProjectMarkers(0)
  for i = nm + nr - 1, 0, -1 do reaper.DeleteProjectMarkerByIndex(0, i) end
  for i = reaper.CountTempoTimeSigMarkers(0) - 1, 0, -1 do reaper.DeleteTempoTimeSigMarker(0, i) end
  local names = { [plan.click and plan.click.track_name or "CLICK"] = true,
                  [plan.cues and plan.cues.track_name or "CUES"] = true,
                  [plan.voice and plan.voice.track_name or "VOIX"] = true }
  for k in pairs(GENERATED) do names[k] = true end
  for i = reaper.CountTracks(0) - 1, 0, -1 do
    local tr = reaper.GetTrack(0, i)
    if names[track_name(tr)] then reaper.DeleteTrack(tr) end
  end
end

-- volume + sortie : master et/ou sortie physique dédiée (ex : 2 = sorties 3/4) pour les in-ears
local function route(tr, c, default_vol)
  reaper.SetMediaTrackInfo_Value(tr, "D_VOL", c.volume or default_vol)
  reaper.SetMediaTrackInfo_Value(tr, "B_MAINSEND", c.to_master == false and 0 or 1)
  if c.hw_output and c.hw_output >= 0 then
    reaper.CreateTrackSend(tr, nil)
    reaper.SetTrackSendInfo_Value(tr, 1, 0, "I_DSTCHAN", c.hw_output)
  end
end

local function build_voice(v, warnings)
  local tr = new_track(v.track_name or "VOIX")
  route(tr, v, 0.8)
  local n = 0
  for _, q in ipairs(v.items or {}) do
    local src = reaper.PCM_Source_CreateFromFile(q.file)
    local len = src and reaper.GetMediaSourceLength(src) or 0
    if src and len > 0 then
      local it = reaper.AddMediaItemToTrack(tr)
      reaper.SetMediaItemInfo_Value(it, "C_BEATATTACHMODE", 0)
      reaper.SetMediaItemInfo_Value(it, "D_POSITION", q.pos)
      reaper.SetMediaItemInfo_Value(it, "D_LENGTH", len)
      local take = reaper.AddTakeToMediaItem(it)
      reaper.SetMediaItemTake_Source(take, src)
      reaper.GetSetMediaItemTakeInfo_String(take, "P_NAME", q.name, true)
      n = n + 1
    else
      warnings[#warnings + 1] = T("bad_voice") .. tostring(q.file)
    end
  end
  return n
end

local function build_click(c, warnings)
  local tr = new_track(c.track_name or "CLICK")
  route(tr, c, 0.5)
  local ts, te = reaper.GetSet_LoopTimeRange(false, false, 0, 0, false)
  local cur = reaper.GetCursorPosition()
  for _, r in ipairs(c.ranges or {}) do
    reaper.SetOnlyTrackSelected(tr)
    reaper.GetSet_LoopTimeRange(true, false, r[1], r[2], false)
    reaper.SetEditCurPos(r[1], false, false)
    reaper.Main_OnCommand(40013, 0) -- Insert > Click source
  end
  if reaper.CountTrackMediaItems(tr) == 0 then
    warnings[#warnings + 1] = T("no_click")
  end
  reaper.GetSet_LoopTimeRange(true, false, ts, te, false)
  reaper.SetEditCurPos(cur, false, false)
  return reaper.CountTrackMediaItems(tr)
end

-- périphérique MIDI de sortie par son nom (exact, sinon contenu dans le nom ; sans tenir compte de la casse)
local function midi_out_index(want)
  want = tostring(want or ""):lower()
  if want == "" or not reaper.GetMIDIOutputName then return nil end
  local n = reaper.GetMaxMIDIOutputs and reaper.GetMaxMIDIOutputs() or 64
  local partial
  for i = 0, n - 1 do
    local ok, name = reaper.GetMIDIOutputName(i, "")
    if ok and name and name ~= "" then
      local low = name:lower()
      if low == want then return i, name end
      if not partial and low:find(want, 1, true) then partial = { i, name } end
    end
  end
  if partial then return partial[1], partial[2] end
  return nil
end

-- piste TIMECODE LTC / TIMECODE MTC : un générateur (action 40208) de 0 à `len`, pas de master ;
-- LTC -> sortie audio matérielle, MTC -> sortie MIDI matérielle
local function build_timecode(spec, len, captured, warnings)
  local tr = new_track(spec.name)
  reaper.SetMediaTrackInfo_Value(tr, "B_MAINSEND", 0)
  reaper.SetMediaTrackInfo_Value(tr, "D_VOL", spec.volume or 1.0)
  reaper.GetSetMediaTrackInfo_String(tr, TC_KEY, spec.key or "", true)
  local info = { name = spec.name, kind = spec.kind, key = spec.key, label = spec.label,
                 midi_out = spec.midi_out, length = len }
  local ts, te = reaper.GetSet_LoopTimeRange(false, false, 0, 0, false)
  local cur = reaper.GetCursorPosition()
  reaper.SetOnlyTrackSelected(tr)
  reaper.GetSet_LoopTimeRange(true, false, 0, len, false)
  reaper.SetEditCurPos(0, false, false)
  reaper.Main_OnCommand(40208, 0) -- Insert > SMPTE LTC/MTC Timecode Generator
  reaper.GetSet_LoopTimeRange(true, false, ts, te, false)
  reaper.SetEditCurPos(cur, false, false)
  local it = reaper.CountTrackMediaItems(tr) > 0 and reaper.GetTrackMediaItem(tr, 0)
  if not it then
    info.item = false
  else
    info.item = true
    reaper.SetMediaItemInfo_Value(it, "C_BEATATTACHMODE", 0)
    reaper.SetMediaItemInfo_Value(it, "D_POSITION", 0)
    reaper.SetMediaItemInfo_Value(it, "D_LENGTH", len)
    reaper.SetMediaItemInfo_Value(it, "B_LOOPSRC", 0)
    reaper.SetMediaItemInfo_Value(it, "D_FADEINLEN", 0)
    reaper.SetMediaItemInfo_Value(it, "D_FADEOUTLEN", 0)
    -- réglage du générateur : celui fait à la main sur cette piste (mêmes réglages ReaCue), sinon le
    -- bloc mémorisé, sinon les valeurs par défaut de REAPER
    local old = captured[spec.name]
    local block, origin = nil, "default"
    if old and old.block and old.key == spec.key then block, origin = old.block, "kept"
    elseif spec.template then block, origin = spec.template, "template" end
    if block then
      local ok, chunk = reaper.GetItemStateChunk(it, "", false)
      local new = ok and tc_replace_block(chunk, block)
      if not (new and reaper.SetItemStateChunk(it, new, false)) then
        warnings[#warnings + 1] = spec.name .. " : " .. T("tc_chunk")
        origin = "default"
      end
    end
    local ok, chunk = reaper.GetItemStateChunk(it, "", false)
    info.block = ok and tc_source_block(chunk) or nil
    info.origin = origin
  end
  if spec.kind == "ltc" and spec.audio_dst then
    local k = reaper.CreateTrackSend(tr, nil)
    if k and k >= 0 then
      reaper.SetTrackSendInfo_Value(tr, 1, k, "I_SRCCHAN", spec.audio_src or 0)
      reaper.SetTrackSendInfo_Value(tr, 1, k, "I_DSTCHAN", spec.audio_dst)
    end
  end
  if spec.kind == "mtc" then
    local dev, name = midi_out_index(spec.midi_out)
    info.midi_found = dev ~= nil
    if dev then
      reaper.SetMediaTrackInfo_Value(tr, "I_MIDIHWOUT", dev << 5)   -- 5 bits bas : canal (0 = tous)
      info.midi_out = name
    end
  end
  return info
end

local function build_cues(c)
  local tr = new_track(c.track_name or "CUES")
  for _, q in ipairs(c.items or {}) do
    local it = reaper.AddMediaItemToTrack(tr)
    reaper.SetMediaItemInfo_Value(it, "D_POSITION", q.pos)
    reaper.SetMediaItemInfo_Value(it, "D_LENGTH", q.len)
    reaper.GetSetMediaItemInfo_String(it, "P_NOTES", q.name, true)
    if q.color then reaper.SetMediaItemInfo_Value(it, "I_CUSTOMCOLOR", color(q.color)) end
  end
  return #(c.items or {})
end

-- toutes les pistes du bloc « timecode » du plan ; renvoie {tracks, warnings, length}
local function build_timecode_all(tc, len, captured)
  local tcw, tracks = {}, {}
  for _, spec in ipairs(tc.tracks or {}) do
    local ok_tc, info = pcall(build_timecode, spec, len, captured, tcw)
    if ok_tc then tracks[#tracks + 1] = info
    else tcw[#tcw + 1] = tostring(spec.name) .. " : " .. tostring(info) end
  end
  return { tracks = tracks, warnings = tcw, length = len }
end

function H.apply_plan(plan)
  local warnings = {}
  reaper.Undo_BeginBlock()
  reaper.PreventUIRefresh(1)

  local captured = {}
  local ok, err = pcall(function()
    if plan.clear ~= false then
      captured = capture_timecode()
      clear(plan)
    end

    -- 1. caler le ou les items audio (base de temps "temps" pour qu'ils ne soient pas étirés)
    local moves = {}
    for _, m in ipairs(plan.items or {}) do moves[#moves + 1] = m end
    if plan.item then moves[#moves + 1] = plan.item end
    local found = {}
    for _, m in ipairs(moves) do           -- vérifier tout avant de déplacer quoi que ce soit
      local it = find_item(m.guid)
      if not it then error(T("item_missing") .. tostring(m.guid) .. ")") end
      found[#found + 1] = it
    end
    for i, m in ipairs(moves) do
      reaper.SetMediaItemInfo_Value(found[i], "C_BEATATTACHMODE", 0)
      reaper.SetMediaItemInfo_Value(found[i], "D_POSITION", m.position)
    end

    -- 2. carte de tempo
    for i, t in ipairs(plan.tempo or {}) do
      local num, den = 0, 0
      if i == 1 or t.sig_change then num, den = t.num, t.den end
      reaper.SetTempoTimeSigMarker(0, -1, t.time, -1, -1, t.bpm, num, den, false)
    end
    reaper.UpdateTimeline()

    -- 3. régions et marqueurs de cue
    for _, r in ipairs(plan.regions or {}) do
      reaper.AddProjectMarker2(0, true, r.start, r["end"], r.name, -1, color(r.color))
    end
    for _, m in ipairs(plan.markers or {}) do
      reaper.AddProjectMarker2(0, false, m.pos, 0, m.name, -1, color(m.color))
    end
  end)
  if not ok then
    reaper.PreventUIRefresh(-1)
    reaper.Undo_EndBlock(T("undo_fail"), -1)
    error(err)
  end

  local result = { warnings = warnings }
  if plan.cues and plan.cues.enabled ~= false then result.cue_items = build_cues(plan.cues) end
  if plan.voice and plan.voice.enabled ~= false then result.voice_items = build_voice(plan.voice, warnings) end
  if plan.click and plan.click.enabled ~= false then result.click_items = build_click(plan.click, warnings) end
  if plan.timecode then
    local len = math.max(tonumber(plan.timecode.min_len) or 0, reaper.GetProjectLength(0))
    result.timecode = build_timecode_all(plan.timecode, len, captured)
  end

  reaper.PreventUIRefresh(-1)
  reaper.UpdateArrange()
  reaper.UpdateTimeline()
  reaper.Undo_EndBlock(T("undo_ok"), -1)
  result.state = H.get_state()
  return result
end

-- pistes TIMECODE seules (pont ≥ 1.5, onglet Lumière de la fenêtre ReaCue) : même code que la préparation
-- (réglage du générateur gardé ou réappliqué) ; le reste du projet n'est pas touché. tc = bloc « timecode »
-- du plan + tail : le timecode couvre le projet (sans les anciennes pistes timecode) + tail secondes.
function H.timecode_tracks(tc)
  reaper.Undo_BeginBlock()
  reaper.PreventUIRefresh(1)
  local ok, res = pcall(function()
    local captured = capture_timecode()
    for i = reaper.CountTracks(0) - 1, 0, -1 do
      local tr = reaper.GetTrack(0, i)
      if TIMECODE[track_name(tr)] then reaper.DeleteTrack(tr) end
    end
    local len = math.max(tonumber(tc.min_len) or 0, reaper.GetProjectLength(0) + (tonumber(tc.tail) or 0))
    return build_timecode_all(tc, len, captured)
  end)
  reaper.PreventUIRefresh(-1)
  reaper.UpdateArrange()
  reaper.Undo_EndBlock(ok and T("undo_tc") or T("undo_fail"), -1)
  if not ok then error(res) end
  return { timecode = res }
end

function H.goto_region(a)
  local _, nm, nr = reaper.CountProjectMarkers(0)
  for i = 0, nm + nr - 1 do
    local _, isrgn, pos, _, name, idx = reaper.EnumProjectMarkers(i)
    if isrgn and (idx == a.index or (a.name and name:lower() == a.name:lower())) then
      reaper.SetEditCurPos(pos, true, true)
      return { pos = pos, name = name }
    end
  end
  error(T("region_missing"))
end

function H.transport(a)
  local cmds = { play = 1007, stop = 1016, pause = 1008 }
  reaper.Main_OnCommand(assert(cmds[a.action], T("unknown_action")), 0)
  return { action = a.action }
end

-- Boucle -----------------------------------------------------------------------
local last_beat = 0

local lock_reader
local function handle(src)
  local chunk, perr = load("return " .. src, "request", "t", {}) -- données pures, aucun accès à l'API
  if not chunk then return { ok = false, error = "requête illisible : " .. tostring(perr) } end
  local okr, req = pcall(chunk)
  if not okr or type(req) ~= "table" then return { ok = false, error = "requête invalide" } end
  if req.expected_project and req.expected_project ~= "" then
    local _, current = reaper.EnumProjects(-1, "")
    if current ~= req.expected_project then
      return { id = req.id, ok = false, error = "Le projet a changé. Reviens au projet qui a lancé le traitement." }
    end
  end
  if req.cmd == "import_file" or req.cmd == "apply_plan" or req.cmd == "timecode_tracks" then
    local lock = read_file(reaper.GetResourcePath() .. "/ReaCueMCP/show_lock.json")
    if lock and not lock_reader then
      local base=debug.getinfo(1,"S").source:match("^@?(.*[/\\])") or ""
      local ok,module=pcall(dofile,base .. "ReaCue_run.lua")
      if ok then lock_reader=module end
    end
    if lock and (not lock_reader or lock_reader.show_locked()) then
      return { id = req.id, ok = false, error = "Concert verrouillé : modifications désactivées." }
    end
  end
  local fn = H[req.cmd]
  if not fn then return { id = req.id, ok = false, error = "commande inconnue : " .. tostring(req.cmd) } end
  local ok, res = pcall(fn, req.args or {})
  if ok then return { id = req.id, ok = true, result = res } end
  return { id = req.id, ok = false, error = tostring(res) }
end

local function loop()
  local now = reaper.time_precise()
  if now - last_beat > 2 then
    last_beat = now
    pcall(write_atomic, HEARTBEAT, tostring(os.time()))
  end
  local src = read_file(REQ)
  if src then
    os.remove(REQ)
    pcall(write_atomic, RES, json(handle(src)))
  end
  reaper.defer(loop)
end

reaper.atexit(function() os.remove(HEARTBEAT) end)
loop()
