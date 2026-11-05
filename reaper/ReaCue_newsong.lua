-- ReaCue : « + Nouveau morceau » / “+ New song” : un fichier (MP3, WAV…) ou un dossier de stems.
--   1. choix des fichiers (boîtes de dialogue de REAPER ; dossier : js_ReaScriptAPI si installée, sinon
--      un des fichiers de stems → tous les fichiers audio de son dossier) ;
--   2. titre proposé à partir du nom (sans « -Bass- », tonalité, BPM, « _Official … Video_ »…), confirmé ;
--      un projet existant n'est jamais écrasé ;
--   3. copie des fichiers dans <dossier des projets>/<Titre>/ (noms d'origine gardés : ils portent le rôle,
--      la tonalité, le BPM), en arrière-plan avec progression, taille vérifiée ;
--   4. nouvel onglet de projet (le projet ouvert n'est pas touché), un fichier par piste à 0 s, projet
--      enregistré dans <dossier des projets>/<Titre>/<Titre>.RPP, puis onglet « Morceau ».
return function(ctx)
  local L, U, T, R, SEP = ctx.L, ctx.U, ctx.T, ctx.R, ctx.SEP
  local TXT = {
    fr = {
      button = "+ Nouveau morceau", menu = "Un fichier (MP3, WAV…)|Des stems (un dossier)|Depuis un lien YouTube…",
      pick_file = "ReaCue - Fichier du nouveau morceau (MP3, WAV…)",
      pick_folder = "ReaCue - Dossier des stems du nouveau morceau",
      pick_one_stem = "Choisis UN des fichiers de stems : tous les fichiers audio de son dossier seront importés.",
      pick_stem = "ReaCue - Un des fichiers de stems",
      not_audio = "Ce fichier n'est pas un fichier audio reconnu :\n%s",
      no_audio = "Aucun fichier audio dans ce dossier :\n%s",
      title_title = "ReaCue - Nouveau morceau", title_field = "Titre du morceau :",
      exists = "Un morceau « %s » existe déjà :\n%s\n\nChoisis un autre titre (rien n'est écrasé).",
      copying = "Copie des fichiers (%d / %d)", copy_failed = "Copie impossible :\n%s\n→ %s",
      copy_size = "Copie incomplète (taille différente) :\n%s",
      no_save = "Le projet n'a pas pu être enregistré automatiquement.\nEnregistre-le sous :\n%s",
      created = "Nouveau morceau « %s » : %d fichier(s) copié(s) dans %s",
    },
    en = {
      button = "+ New song", menu = "One file (MP3, WAV…)|Stems (a folder)|From a YouTube link…",
      pick_file = "ReaCue - File of the new song (MP3, WAV…)",
      pick_folder = "ReaCue - Stems folder of the new song",
      pick_one_stem = "Choose ONE of the stem files: every audio file in its folder will be imported.",
      pick_stem = "ReaCue - One of the stem files",
      not_audio = "This is not a recognised audio file:\n%s",
      no_audio = "No audio file in this folder:\n%s",
      title_title = "ReaCue - New song", title_field = "Song title:",
      exists = "A song “%s” already exists:\n%s\n\nChoose another title (nothing is overwritten).",
      copying = "Copying the files (%d / %d)", copy_failed = "Could not copy:\n%s\n→ %s",
      copy_size = "Incomplete copy (size differs):\n%s",
      no_save = "The project could not be saved automatically.\nSave it as:\n%s",
      created = "New song “%s”: %d file(s) copied to %s",
    },
  }
  local function t(k) return ctx.tr(TXT, k) end
  local N = {}
  N.t = t

  N.AUDIO = { wav = true, mp3 = true, aif = true, aiff = true, flac = true, ogg = true, m4a = true, wv = true }
  function N.is_audio(name)
    local ext = tostring(name):match("%.([^./\\]+)$")
    return ext ~= nil and N.AUDIO[ext:lower()] == true and not tostring(name):match("^%.") and
      not tostring(name):match("[/\\]%.[^/\\]*$")
  end

  -- titre --------------------------------------------------------------------------------------
  local ROLE_SEG = {
    vocals = 1, vocal = 1, voice = 1, voix = 1, chant = 1, ["backing vocals"] = 1, choeurs = 1, ["chœurs"] = 1,
    drums = 1, drum = 1, batterie = 1, percussion = 1, percussions = 1,
    bass = 1, basse = 1,
    guitar = 1, guitars = 1, guitare = 1, guitares = 1, ["lead guitar"] = 1, ["lead guitars"] = 1,
    ["rhythm guitar"] = 1, ["rhythm guitars"] = 1,
    other = 1, others = 1, autre = 1, autres = 1, piano = 1, keys = 1, claviers = 1, synth = 1,
    instrumental = 1, accompaniment = 1, mix = 1, click = 1, metronome = 1,
  }
  local function trim(s) return (tostring(s):gsub("^[%s%-_%.]+", ""):gsub("[%s%-_%.]+$", "")) end

  local function cut_segment(seg)
    local s = trim(seg):lower()
    if s == "" then return false end
    if ROLE_SEG[s] then return true end
    if s:match("^[a-g][#b]?%s*major$") or s:match("^[a-g][#b]?%s*minor$") or s:match("^[a-g][#b]?%s*maj$")
      or s:match("^[a-g][#b]?%s*min$") or s:match("^[a-g][#b]?m$") then return true end
    if s:match("^%d+[%.,]?%d*%s*bpm$") or s:match("^%d+%s*k?hz$") then return true end
    if s:match("consolidated$") then return true end
    return false
  end

  -- « Luke - La sentinelle _Clip officiel_-Bass-E minor-188bpm-441hz » → « Luke - La sentinelle »
  function N.clean_title(name)
    local s = tostring(name or ""):gsub("^.*[/\\]", ""):gsub("%.[%w]+$", "")
    -- coupe au premier segment « -Rôle- », « -tonalité- », « -188bpm- », « -441hz- »
    local parts, cur = {}, ""
    for ch in (s .. "-"):gmatch(".") do
      if ch == "-" then parts[#parts + 1] = cur; cur = "" else cur = cur .. ch end
    end
    local keep = {}
    for i, p in ipairs(parts) do
      if i > 1 and cut_segment(p) then break end
      keep[#keep + 1] = p
    end
    s = table.concat(keep, "-")
    -- « _Official HD Video_ », « (Clip officiel) », « [Lyrics] »…
    local WORDS = { "official", "officiel", "officielle", "clip", "lyric", "lyrics", "video", "vidéo", "audio",
                    "remaster", "remastered", "visualizer", "live", "hd", "4k" }
    local function noisy(inner)
      local l = inner:lower()
      for _, w in ipairs(WORDS) do if l:find(w, 1, true) then return true end end
      return false
    end
    s = s:gsub("%s*(%b())", function(b) return noisy(b) and "" or nil end)
    s = s:gsub("%s*(%b[])", function(b) return noisy(b) and "" or nil end)
    s = s:gsub("%s*_([^_]+)_", function(b) return noisy(b) and "" or nil end)
    s = s:gsub("_", " "):gsub("%s+", " ")
    s = trim(s)
    if s == "" then s = trim(tostring(name or ""):gsub("^.*[/\\]", ""):gsub("%.[%w]+$", "")) end
    return s
  end

  -- nom de fichier / dossier sûr (Windows et macOS)
  function N.safe(title)
    local s = tostring(title):gsub('[\\/:*?"<>|]+', "-"):gsub("%s+", " ")
    s = trim(s)
    return s ~= "" and s or "Morceau"
  end

  -- titre commun de plusieurs stems : le dossier s'il est parlant, sinon le préfixe commun
  function N.stems_title(dir, files)
    local d = tostring(dir):match("([^/\\]+)[/\\]?$") or ""
    local cand = N.clean_title(d .. ".x")
    if cand ~= "" and not ROLE_SEG[cand:lower()] and cand:lower() ~= "stems" then return cand end
    return N.clean_title(files[1] or "")
  end

  -- piste : nom du rôle (« Bass » → Basse / Bass) ou nom d'origine
  local ROLE_WORDS = {
    { "vocals", { "vocals", "vocal", "voice", "voices", "voix", "chant", "vox", "backing vocals", "choeurs", "chœurs" } },
    { "drums", { "drums", "drum", "batterie", "percussion", "percussions", "perc", "kick", "batt" } },
    { "bass", { "bass", "basse" } },
    { "lead_guitar", { "lead guitar", "lead guitars", "lead gtr", "guitare solo", "solo guitar" } },
    { "guitars", { "guitars", "guitar", "guitares", "guitare", "gtr", "rhythm guitar" } },
    { "keys", { "piano", "keys", "clavier", "claviers", "synth", "synthesizer", "organ", "orgue" } },
    { "other", { "other", "others", "autre", "autres" } },
  }
  local ROLE_NAMES = {
    fr = { vocals = "Chant", drums = "Batterie", bass = "Basse", lead_guitar = "Guitare solo", guitars = "Guitares",
           keys = "Claviers", other = "Autres" },
    en = { vocals = "Vocals", drums = "Drums", bass = "Bass", lead_guitar = "Lead guitar", guitars = "Guitars",
           keys = "Keys", other = "Other" },
  }
  function N.role_of(file)
    local n = tostring(file):gsub("^.*[/\\]", ""):gsub("%.[%w]+$", ""):lower()
    local norm = " " .. n:gsub("[^%w\128-\255]+", " ") .. " "
    for _, rw in ipairs(ROLE_WORDS) do
      for _, w in ipairs(rw[2]) do
        if norm:find(" " .. w .. " ", 1, true) then return rw[1] end
      end
    end
    return nil
  end
  -- ⚠ le nom de piste garde le mot du rôle : ReaCue reconnaît les stems d'après le nom du FICHIER
  function N.track_name(file, single)
    local r = N.role_of(file)
    if r and not single then return (ROLE_NAMES[L.lang()] or ROLE_NAMES.fr)[r] end
    local base = tostring(file):gsub("^.*[/\\]", ""):gsub("%.[%w]+$", "")
    return single and N.clean_title(base) or base
  end

  -- fichiers audio d'un dossier (triés)
  function N.audio_files(dir)
    local out, i = {}, 0
    while true do
      local f = reaper.EnumerateFiles(dir, i)
      if not f then break end
      if N.is_audio(f) then out[#out + 1] = f end
      i = i + 1
    end
    table.sort(out, function(a, b) return a:lower() < b:lower() end)
    return out
  end

  local function dir_exists(p)
    if reaper.EnumerateFiles(p, 0) or (reaper.EnumerateSubdirectories and reaper.EnumerateSubdirectories(p, 0)) then
      return true
    end
    local ok = os.rename(p, p)
    return ok == true
  end

  -- un morceau de ce titre existe-t-il déjà ? renvoie le chemin trouvé
  function N.existing(title)
    local root = L.projects_dir()
    local s = N.safe(title)
    for _, p in ipairs({ root .. SEP .. s, root .. SEP .. s .. ".RPP", root .. SEP .. s .. ".rpp" }) do
      if p:lower():match("%.rpp$") then
        if L.exists(p) then return p end
      elseif dir_exists(p) then return p end
    end
    return nil
  end

  -- dialogues ----------------------------------------------------------------------------------
  local function pick_file(title)
    if not reaper.GetUserFileNameForRead then return nil end
    local ok, fn = reaper.GetUserFileNameForRead("", title, "")
    if not ok or not fn or fn == "" then return nil end
    return fn
  end

  -- renvoie dir, {fichiers}, single
  function N.choose(kind)
    if kind == "file" then
      local fn = pick_file(t("pick_file"))
      if not fn then return nil end
      if not N.is_audio(fn) then reaper.ShowMessageBox(string.format(t("not_audio"), fn), T("title"), 0) return nil end
      local d, b = fn:match("^(.*)[/\\]([^/\\]+)$")
      return d or ".", { b or fn }, true
    end
    local dir
    if reaper.JS_Dialog_BrowseForFolder then
      local rv, folder = reaper.JS_Dialog_BrowseForFolder(t("pick_folder"), L.projects_dir())
      if rv ~= 1 or not folder or folder == "" then return nil end
      dir = folder:gsub("[/\\]$", "")
    else
      reaper.ShowMessageBox(t("pick_one_stem"), T("title"), 0)
      local fn = pick_file(t("pick_stem"))
      if not fn then return nil end
      dir = fn:match("^(.*)[/\\][^/\\]+$") or "."
    end
    local files = N.audio_files(dir)
    if #files == 0 then reaper.ShowMessageBox(string.format(t("no_audio"), dir), T("title"), 0) return nil end
    return dir, files, false
  end

  function N.ask_title(proposal)
    local cur = proposal
    for _ = 1, 6 do
      local ok, v = reaper.GetUserInputs(t("title_title"), 1, t("title_field") .. ",extrawidth=220", cur)
      if not ok or not v then return nil end
      v = trim(v:gsub("%s+", " "))
      if v ~= "" then
        local ex = N.existing(v)
        if not ex then return v end
        reaper.ShowMessageBox(string.format(t("exists"), v, ex), T("title"), 0)
        cur = v .. " 2"
      end
    end
    return nil
  end

  -- copie en arrière-plan (par blocs, quelques dizaines de ms par image) ------------------------
  local BLOCK = 1024 * 1024
  local function fsize(f) local cur = f:seek(); local n = f:seek("end"); f:seek("set", cur) return n end

  function N.copy_task(src_dir, files, dst_dir)
    local job = { i = 0, src = nil, dst = nil, done_b = 0, total = 0, sizes = {}, files = files,
                  src_dir = src_dir, dst_dir = dst_dir }
    for k, f in ipairs(files) do
      local h = io.open(src_dir .. SEP .. f, "rb")
      job.sizes[k] = h and fsize(h) or 0
      if h then h:close() end
      job.total = job.total + job.sizes[k]
    end
    -- step(budget_s) → "running", pct | "done" | "error", message
    function job.step(budget)
      local t0 = reaper.time_precise()
      while true do
        if not job.src then
          job.i = job.i + 1
          if job.i > #files then return "done" end
          local sp, dp = src_dir .. SEP .. files[job.i], dst_dir .. SEP .. files[job.i]
          job.src = io.open(sp, "rb")
          job.dst = job.src and io.open(dp, "wb")
          if not job.src or not job.dst then
            if job.src then job.src:close() end
            job.src = nil
            return "error", string.format(t("copy_failed"), sp, dp)
          end
        end
        local chunk = job.src:read(BLOCK)
        if chunk then
          job.dst:write(chunk)
          job.done_b = job.done_b + #chunk
        else
          job.src:close(); job.dst:close(); job.src, job.dst = nil, nil
          local dp = dst_dir .. SEP .. files[job.i]
          local h = io.open(dp, "rb")
          local n = h and fsize(h) or -1
          if h then h:close() end
          if n ~= job.sizes[job.i] then return "error", string.format(t("copy_size"), dp) end
        end
        if reaper.time_precise() - t0 > (budget or 0.04) then break end
      end
      local pct = job.total > 0 and math.floor(100 * job.done_b / job.total) or 0
      return "running", pct, string.format(t("copying"), math.min(job.i, #files), #files)
    end
    return job
  end

  -- projet : nouvel onglet, une piste par fichier, enregistré ------------------------------------
  function N.make_project(dir, title, files, single)
    if ctx.require_edit and not ctx.require_edit() then return false end
    reaper.Main_OnCommand(40859, 0)                        -- nouvel onglet de projet
    reaper.PreventUIRefresh(1)
    for _, f in ipairs(files) do
      local nt = reaper.CountTracks(0)
      if nt > 0 and reaper.SetOnlyTrackSelected then reaper.SetOnlyTrackSelected(reaper.GetTrack(0, nt - 1)) end
      reaper.SetEditCurPos(0, false, false)
      reaper.InsertMedia(dir .. SEP .. f, 1)               -- 1 = sur une nouvelle piste
      local tr = reaper.GetTrack(0, reaper.CountTracks(0) - 1)
      if tr then reaper.GetSetMediaTrackInfo_String(tr, "P_NAME", N.track_name(f, single), true) end
    end
    reaper.SetEditCurPos(0, true, false)
    reaper.PreventUIRefresh(-1)
    reaper.UpdateArrange()
    local rpp = dir .. SEP .. N.safe(title) .. ".RPP"
    local saved = false
    if reaper.Main_SaveProjectEx then
      reaper.Main_SaveProjectEx(0, rpp, 0)
      saved = L.exists(rpp)
    end
    if saved then
      reaper.Main_openProject("noprompt:" .. rpp)          -- l'onglet porte maintenant ce fichier
    else
      reaper.ShowMessageBox(string.format(t("no_save"), rpp), T("title"), 0)
      reaper.Main_OnCommand(40022, 0)                      -- Enregistrer le projet sous…
    end
    return rpp, saved
  end

  -- Common completion for a local copy or an explicitly requested download.
  function N.complete(dst, title, files, single)
    if ctx.require_edit and not ctx.require_edit() then return false end
    local rpp = N.make_project(dst, title, files, single)
    if not rpp then return false end
    ctx.refresh(true)
    ctx.goto_tab("song")
    if ctx.tabs.concert.project_changed then ctx.tabs.concert.project_changed() end
    ctx.tabs.concert.rescan = true
    ctx.flash = { txt = string.format(t("created"), title, #files, dst), t = reaper.time_precise() + 6 }
    ctx.last_new = { rpp = rpp, single = single }
    ctx.propose_all = ctx.proj_key -- propose « Tout faire » ; ne lance jamais une analyse ici
    return true
  end

  -- enchaînement complet (bouton « + Nouveau morceau ») -----------------------------------------
  function N.start(kind)
    if (R.active_job and R.active_job()) or (ctx.jobs and ctx.jobs.busy()) then
      ctx.last_error=R.tr("busy"); if ctx.show_result then ctx.show_result("ReaCue",ctx.last_error,false) end; return false
    end
    if ctx.job or (ctx.require_edit and not ctx.require_edit()) then return false end
    if not kind then
      gfx.x, gfx.y = gfx.mouse_x, gfx.mouse_y
      local c = gfx.showmenu(t("menu"))
      if not c or c < 1 then return false end
      kind = (c == 1) and "file" or (c == 2 and "stems" or "link")
    end
    if kind == "link" then
      if not ctx.audio_import then ctx.audio_import = dofile(ctx.dir .. "ReaCue_import.lua")(ctx) end
      return ctx.audio_import.start()
    end
    local src, files, single = N.choose(kind)
    if not src then return false end
    local proposal = single and N.clean_title(files[1]) or N.stems_title(src, files)
    local title = N.ask_title(proposal)
    if not title then return false end
    local dst = L.projects_dir() .. SEP .. N.safe(title)
    reaper.RecursiveCreateDirectory(dst, 0)
    local job = N.copy_task(src, files, dst)
    ctx.job = { kind = "task", label = string.format(t("copying"), 0, #files), t0 = reaper.time_precise(),
                step = job.step, pct = 0,
                on_done = function(state, msg)
                  if state ~= "done" then ctx.show_result(T("error_title"), msg, false) return end
                  N.complete(dst, title, files, single)
                end }
    return true
  end

  return N
end
