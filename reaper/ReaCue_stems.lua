-- ReaCue : séparation de stems (Demucs, en local) / stem separation (Demucs, local).
-- Code de l'action « ReaCue - Séparer les stems » (ReaCue_Separer_stems.lua).
--
--   1. item à séparer : l'item sélectionné, sinon le seul item audio du projet (hors CLICK/CUES/VOIX) ;
--   2. Demucs tourne en arrière-plan dans <installation>/.venv-demucs (reacue_stems.py), résultat dans
--      <dossier du fichier>/<nom>-stems/<modèle>/<nom>-<stem>.wav (gardé : une 2e fois, import immédiat) ;
--   3. les stems sont importés sur une piste chacun, calés comme l'item d'origine (position, longueur,
--      décalage, vitesse), et l'item d'origine est retiré du projet (un seul « Annuler » remet tout).
-- Modèle : réglage "stems_model" de reacue_settings.json (htdemucs par défaut ; 6s/ft sur choix explicite).

local S = {}
local SEP = package.config:sub(1, 1)
local TITLE = "ReaCue"

local function exists(p) local f = io.open(p, "rb"); if f then f:close() return true end return false end
local function read(p) local f = io.open(p, "rb"); if not f then return nil end local s = f:read("*a"); f:close(); return s end

S.MODELS = {
  htdemucs_6s = { "vocals", "drums", "bass", "guitar", "piano", "other" },
  htdemucs = { "vocals", "drums", "bass", "other" },
  htdemucs_ft = { "vocals", "drums", "bass", "other" },
}
S.DEFAULT_MODEL = "htdemucs"
-- pistes générées par ReaCue (jamais séparées), comme dans ReaCue_Bridge.lua
S.GENERATED = { CLICK = true, CUES = true, VOIX = true, VOICE = true, ["TIMECODE LTC"] = true, ["TIMECODE MTC"] = true }

local TXT = {
  fr = {
    title = "ReaCue - Séparer les stems",
    no_item = "Sélectionne l'item audio du morceau (le MP3 ou le WAV), puis relance l'action.",
    no_file = "Fichier audio introuvable pour cet item :\n%s\n\nSi l'item est marqué OFFLINE, REAPER n'a pas accès au fichier : déplace-le dans le dossier du projet (voir la FAQ).",
    not_installed = "La séparation de stems n'est pas installée :\n%s\n\nLance « Install ReaCue Stems » dans le dossier de ReaCue (ou relance l'installation de ReaCue et réponds oui à la séparation de stems).",
    busy = "Une séparation est déjà en cours pour ce morceau. Attends qu'elle se termine.",
    launch_failed = "Impossible de lancer la séparation :\n%s",
    no_start = "La séparation n'a pas démarré. Voir le journal :\n%s",
    failed = "La séparation a échoué :\n%s\n\nFin du journal :\n%s\n\n(%s)",
    crashed = "Le processus de séparation s'est arrêté de façon inattendue.\n\nFin du journal :\n%s\n\n(%s)",
    progress = "Séparation des stems : %d %%",
    starting = "Séparation des stems : démarrage…",
    hint = "%d min %02d s  ·  tu peux fermer cette fenêtre, l'import se fera à la fin",
    timeout = "Pas de fin après 1 h : voir %s",
    done = "Stems importés (%s) : %s\n\nFichiers : %s\n\nL'item d'origine a été retiré du projet (Annuler pour le remettre ; le fichier reste sur le disque).\nÉtape suivante : « Analyser et préparer » (fenêtre ReaCue).",
    undo = "ReaCue : séparer les stems",
    names = { vocals = "Chant", drums = "Batterie", bass = "Basse", guitar = "Guitare", piano = "Piano", other = "Autres" },
  },
  en = {
    title = "ReaCue - Separate stems",
    no_item = "Select the song's audio item (the MP3 or WAV), then run the action again.",
    no_file = "Audio file not found for this item:\n%s\n\nIf the item shows OFFLINE, REAPER cannot access the file: move it into the project folder (see the FAQ).",
    not_installed = "Stem separation is not installed:\n%s\n\nRun “Install ReaCue Stems” in the ReaCue folder (or run the ReaCue installer again and answer yes to stem separation).",
    busy = "A separation is already running for this song. Wait until it finishes.",
    launch_failed = "Could not start the separation:\n%s",
    no_start = "The separation did not start. See the log:\n%s",
    failed = "The separation failed:\n%s\n\nEnd of the log:\n%s\n\n(%s)",
    crashed = "The stem separation process terminated unexpectedly.\n\nEnd of the log:\n%s\n\n(%s)",
    progress = "Separating stems: %d %%",
    starting = "Separating stems: starting…",
    hint = "%d min %02d s  ·  you can close this window, the import will happen at the end",
    timeout = "Not finished after 1 h: see %s",
    done = "Stems imported (%s): %s\n\nFiles: %s\n\nThe original item was removed from the project (Undo to get it back; the file stays on disk).\nNext step: “Analyse and prepare” (ReaCue window).",
    undo = "ReaCue: separate stems",
    names = { vocals = "Vocals", drums = "Drums", bass = "Bass", guitar = "Guitar", piano = "Piano", other = "Other" },
  },
}

-- R = module ReaCue_run.lua (langue, dossier d'installation, guillemets)
function S.tr(R, key)
  return TXT[R.lang()][key] or TXT.fr[key]
end

function S.model(R)
  local m = R.jfield(read(reaper.GetResourcePath() .. SEP .. "ReaCueMCP" .. SEP .. "reacue_settings.json"),
    "stems_model")
  if type(m) == "string" and S.MODELS[m] then return m end
  return S.DEFAULT_MODEL
end

-- chemins dérivés du fichier source (séparateur / ou \ selon le chemin donné)
function S.paths(file, model)
  local dir, name = file:match("^(.*)[/\\]([^/\\]+)$")
  if not dir then dir, name = ".", file end
  local sep = file:find("\\", 1, true) and not file:find("/", 1, true) and "\\" or "/"
  local base = name:gsub("%.[^.]+$", "")
  local outroot = dir .. sep .. base .. "-stems"
  local p = { dir = dir, base = base, sep = sep, outroot = outroot, outdir = outroot .. sep .. model,
              log = outroot .. sep .. "demucs.log", status = outroot .. sep .. "demucs_status.json", stems = {} }
  for _, s in ipairs(S.MODELS[model]) do
    p.stems[#p.stems + 1] = { stem = s, file = p.outdir .. sep .. base .. "-" .. s .. ".wav" }
  end
  return p
end

function S.ready(p)
  for _, s in ipairs(p.stems) do if not exists(s.file) then return false end end
  return true
end

function S.python(dir, windows)
  if windows then
    local pyw = dir .. "\\.venv-demucs\\Scripts\\pythonw.exe"
    if exists(pyw) then return pyw end
    return dir .. "\\.venv-demucs\\Scripts\\python.exe"
  end
  return dir .. "/.venv-demucs/bin/python"
end

function S.command(R, dir, py, windows, file, outroot, model)
  if windows then
    return table.concat({ R.winq(py), R.winq(dir .. "\\reacue_stems.py"), "separate", "--input", R.winq(file),
      "--out", R.winq(outroot), "--model", model }, " ")
  end
  return string.format("cd %s && nohup %s reacue_stems.py separate --input %s --out %s --model %s > /dev/null 2>&1 &",
    R.shq(dir), R.shq(py), R.shq(file), R.shq(outroot), model)
end

-- pourcentage de la dernière barre tqdm du journal (« 37%|█▌ … »)
function S.progress(log)
  local pct = 0
  for p in (log or ""):gmatch("(%d+)%%|") do pct = tonumber(p) end
  return math.min(pct, 100)
end

local function source_file(take)
  local src = reaper.GetMediaItemTake_Source(take)
  local parent = reaper.GetMediaSourceParent(src)
  while parent do src = parent; parent = reaper.GetMediaSourceParent(src) end
  return reaper.GetMediaSourceFileName(src, "")
end

local function track_name(tr)
  local _, n = reaper.GetSetMediaTrackInfo_String(tr, "P_NAME", "", false)
  return n
end

-- item à séparer : sélectionné, sinon le seul item audio hors pistes générées
function S.pick_item()
  local it = reaper.GetSelectedMediaItem(0, 0)
  if it then
    local tr = reaper.GetMediaItem_Track(it)
    if not (tr and S.GENERATED[track_name(tr)]) then return it end
  end
  local cands = {}
  for i = 0, reaper.CountMediaItems(0) - 1 do
    local x = reaper.GetMediaItem(0, i)
    local tk = reaper.GetActiveTake(x)
    if tk and not (reaper.TakeIsMIDI and reaper.TakeIsMIDI(tk)) and not S.GENERATED[track_name(reaper.GetMediaItem_Track(x))] then
      cands[#cands + 1] = x
    end
  end
  if #cands == 1 then return cands[1] end
  return nil
end

-- import des stems sous la piste d'origine, calés comme l'item ; retrait de l'item d'origine
function S.import(R, item, p)
  local take = reaper.GetActiveTake(item)
  local pos = reaper.GetMediaItemInfo_Value(item, "D_POSITION")
  local len = reaper.GetMediaItemInfo_Value(item, "D_LENGTH")
  local offs = reaper.GetMediaItemTakeInfo_Value(take, "D_STARTOFFS")
  local rate = reaper.GetMediaItemTakeInfo_Value(take, "D_PLAYRATE")
  local tr0 = reaper.GetMediaItem_Track(item)
  local idx = math.floor(reaper.GetMediaTrackInfo_Value(tr0, "IP_TRACKNUMBER"))   -- 1-based : sous la piste
  local names = S.tr(R, "names")
  local made = {}
  reaper.Undo_BeginBlock()
  reaper.PreventUIRefresh(1)
  for i, s in ipairs(p.stems) do
    reaper.InsertTrackAtIndex(idx + i - 1, true)
    local tr = reaper.GetTrack(0, idx + i - 1)
    reaper.GetSetMediaTrackInfo_String(tr, "P_NAME", names[s.stem] or s.stem, true)
    local it = reaper.AddMediaItemToTrack(tr)
    reaper.SetMediaItemInfo_Value(it, "C_BEATATTACHMODE", 0)
    reaper.SetMediaItemInfo_Value(it, "D_POSITION", pos)
    reaper.SetMediaItemInfo_Value(it, "D_LENGTH", len)
    local tk = reaper.AddTakeToMediaItem(it)
    reaper.SetMediaItemTake_Source(tk, reaper.PCM_Source_CreateFromFile(s.file))
    reaper.SetMediaItemTakeInfo_Value(tk, "D_STARTOFFS", offs)
    reaper.SetMediaItemTakeInfo_Value(tk, "D_PLAYRATE", rate)
    reaper.GetSetMediaItemTakeInfo_String(tk, "P_NAME", p.base .. "-" .. s.stem, true)
    made[#made + 1] = names[s.stem] or s.stem
  end
  reaper.DeleteTrackMediaItem(tr0, item)
  reaper.PreventUIRefresh(-1)
  reaper.UpdateArrange()
  reaper.Undo_EndBlock(S.tr(R, "undo"), -1)
  return made
end

-- séparation sans fenêtre (fenêtre ReaCue) : renvoie un « job », ou nil + message
--   job.ready = true : stems déjà séparés (import immédiat avec S.finish)
function S.start(R, script_dir, item)
  item = item or S.pick_item()
  if not item then return nil, S.tr(R, "no_item") end
  local take = reaper.GetActiveTake(item)
  local file = take and source_file(take) or ""
  if file == "" or not exists(file) then return nil, string.format(S.tr(R, "no_file"), file) end
  local model = S.model(R)
  local p = S.paths(file, model)
  local job = { item = item, p = p, model = model, t0 = reaper.time_precise and reaper.time_precise() or os.clock() }
  if S.ready(p) then job.ready = true return job end
  local windows = R.is_windows()
  local dir = R.install_dir(script_dir)
  local py = S.python(dir, windows)
  if not exists(py) then return nil, string.format(S.tr(R, "not_installed"), py) end
  local st = read(p.status)
  if st and R.jfield(st, "state") == "running" and os.time() - (R.jfield(st, "time") or 0) < 3600 then
    return nil, S.tr(R, "busy")
  end
  reaper.RecursiveCreateDirectory(p.outroot, 0)
  os.remove(p.status)
  local line = S.command(R, dir, py, windows, file, p.outroot, model)
  if windows then
    if reaper.ExecProcess(line, -1) == nil then return nil, string.format(S.tr(R, "launch_failed"), line) end
  else
    os.execute(line)
  end
  return job
end

local function pid_alive(pid, windows)
  if not pid or pid == 0 then return true end
  if not reaper.ExecProcess then return true end
  if windows then
    local out = reaper.ExecProcess('tasklist /FI "PID eq ' .. tostring(pid) .. '" /NH', 1000)
    if not out then return true end
    if out:find("aucun") or out:find("No tasks") or out:find("INFO:") then return false end
    return out:find(tostring(pid)) ~= nil
  else
    local r = reaper.ExecProcess('/bin/kill -0 ' .. tostring(pid), 500)
    if not r then return true end
    local code = tonumber(r:match("^(%-?%d+)"))
    if code == nil then return true end
    return code == 0
  end
end
S.pid_alive = pid_alive

-- état du job : "running", pct | "ready" | "error", message
function S.poll(R, job)
  local p = job.p
  if job.ready then return "ready" end
  local now = reaper.time_precise and reaper.time_precise() or os.clock()
  local el = now - job.t0
  local s = read(p.status)
  local state = s and R.jfield(s, "state")
  if state == "done" and S.ready(p) then job.ready = true return "ready" end
  if state == "error" or state == "done" then
    local lg = read(p.log) or ""
    return "error", string.format(S.tr(R, "failed"), R.jfield(s, "message") or "?", lg:sub(-700), p.log)
  end
  if not s and el > 90 then return "error", string.format(S.tr(R, "no_start"), p.log) end
  if el > 3600 then return "error", string.format(S.tr(R, "timeout"), p.log) end

  local pid = s and tonumber(R.jfield(s, "pid"))
  job.last_alive_check = job.last_alive_check or now
  if pid and (now - job.last_alive_check >= 3) then
    job.last_alive_check = now
    if not pid_alive(pid, R.is_windows()) then
      s = read(p.status)
      state = s and R.jfield(s, "state")
      if state == "done" and S.ready(p) then job.ready = true return "ready" end
      local lg = read(p.log) or ""
      return "error", string.format(S.tr(R, "crashed"), lg:sub(-700), p.log)
    end
  end

  return "running", S.progress(read(p.log))
end

-- import des stems séparés ; renvoie le message de fin
function S.finish(R, job)
  local made = S.import(R, job.item, job.p)
  return string.format(S.tr(R, "done"), job.model, table.concat(made, ", "), job.p.outdir)
end

function S.run(script_dir)
  local R = dofile(script_dir .. "/ReaCue_run.lua")
  local title = S.tr(R, "title")
  local function box(msg) reaper.ShowMessageBox(msg, title, 0) end
  local job, err = S.start(R, script_dir)
  if not job then box(err) return end
  if job.ready then box(S.finish(R, job)) return end
  local win = true
  gfx.init(title, 500, 120)
  local function close() if win then gfx.quit(); win = false end end
  local function loop()
    local el = reaper.time_precise() - job.t0
    local state, v = S.poll(R, job)
    if state == "ready" then close() box(S.finish(R, job)) return end
    if state == "error" then close() box(v) return end
    if win then
      if gfx.getchar() < 0 then win = false else
        local pct = v or 0
        gfx.set(0.08, 0.09, 0.11, 1); gfx.rect(0, 0, gfx.w, gfx.h, 1)
        gfx.set(1, 1, 1, 1); gfx.setfont(1, "Arial", 20)
        gfx.x, gfx.y = 20, 18
        gfx.drawstr(pct > 0 and string.format(S.tr(R, "progress"), pct) or S.tr(R, "starting"))
        gfx.set(0.25, 0.27, 0.3, 1); gfx.rect(20, 52, gfx.w - 40, 12, 1)
        gfx.set(0.3, 0.75, 0.45, 1); gfx.rect(20, 52, math.floor((gfx.w - 40) * pct / 100), 12, 1)
        gfx.set(0.6, 0.65, 0.72, 1); gfx.setfont(1, "Arial", 14)
        gfx.x, gfx.y = 20, 80
        gfx.drawstr(string.format(S.tr(R, "hint"), math.floor(el / 60), math.floor(el % 60)))
        gfx.update()
      end
    end
    reaper.defer(loop)
  end
  loop()
end

return S
