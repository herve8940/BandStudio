-- ReaCue : onglet « Concert » / “Concert” tab : composer une setlist à partir des projets de morceaux,
-- la construire / reconstruire, l'ouvrir, régler « joué en live », retrouver les concerts existants,
-- préparer en lot (« Préparer tous les morceaux non préparés » ou la sélection cochée) : en arrière-plan,
-- un morceau après l'autre (onglet ouvert, « Tout faire », enregistré, onglet refermé), arrêtable.
return function(ctx)
  local L, U, T, R, SEP = ctx.L, ctx.U, ctx.T, ctx.R, ctx.SEP
  local TXT = {
    fr = {
      songs = "Morceaux (%s)", setlist = "Setlist « %s »", unnamed = "Nouveau concert",
      prepared = "✓", to_prepare = "à préparer", none_found = "Aucun projet trouvé dans %s",
      empty = "Ajoute des morceaux avec « + »", n_songs = "%d morceaux", total = "%d morceaux · %s",
      new = "Nouveau", rename = "Renommer", build = "Construire", rebuild = "Reconstruire", open = "Ouvrir",
      live = "Joué en live…", existing = "Concerts existants", load = "Modifier", open_one = "Ouvrir",
      not_built = "pas encore construit", refresh = "Actualiser",
      name_title = "ReaCue - Nom du concert", name_field = "Nom :",
      building = "Construction du concert", built = "Concert « %s » construit : ouvert dans un onglet.",
      unprepared_q = "Ces morceaux ne sont pas préparés (pas de sections ou pas de click) :\n%s\n\nConstruire quand même ?",
      batch_all = "Préparer tous les morceaux non préparés (%d)", batch_sel = "Préparer la sélection (%d)",
      batch_none = "Tous les morceaux sont prêts ✓", batch = "Préparation en lot", stop = "Arrêter",
      batch_progress = "%d / %d", batch_done = "Lot terminé : %d prêt(s), %d en échec", batch_stopping = "arrêt après ce morceau…",
      batch_q = "Préparer %d morceau(x) l'un après l'autre ?\n\nChaque projet est ouvert dans un onglet, préparé (« Tout faire »), enregistré puis refermé. Compte quelques minutes par morceau (plus avec la séparation de stems).",
      close = "Fermer",
      manage = "Gérer…", duplicate = "Dupliquer", archive = "Archiver", trash = "Corbeille", restore = "Restaurer…",
      portable = "Copie autonome…", manage_busy = "Arrête la lecture et attends la fin de la tâche.",
      manage_open = "Ferme d'abord ce concert dans tous les onglets REAPER.",
      destination = "Nouveau dossier de destination :", manage_title = "Gestion du concert",
      recover_none = "Aucun concert archivé ou dans la corbeille locale.",
      recover_q = "Déplacer ce concert dans un dossier de récupération ? Les morceaux sources sont conservés.",
      save_failed = "Impossible d'enregistrer la setlist : ",
    },
    en = {
      songs = "Songs (%s)", setlist = "Setlist “%s”", unnamed = "New concert",
      prepared = "✓", to_prepare = "to prepare", none_found = "No project found in %s",
      empty = "Add songs with “+”", n_songs = "%d songs", total = "%d songs · %s",
      new = "New", rename = "Rename", build = "Build", rebuild = "Rebuild", open = "Open",
      live = "Played live…", existing = "Existing concerts", load = "Edit", open_one = "Open",
      not_built = "not built yet", refresh = "Refresh",
      name_title = "ReaCue - Concert name", name_field = "Name:",
      building = "Building the concert", built = "Concert “%s” built: open in a tab.",
      unprepared_q = "These songs are not prepared (no sections or no click):\n%s\n\nBuild anyway?",
      batch_all = "Prepare all songs not prepared (%d)", batch_sel = "Prepare the selection (%d)",
      batch_none = "All songs are ready ✓", batch = "Batch preparation", stop = "Stop",
      batch_progress = "%d / %d", batch_done = "Batch finished: %d ready, %d failed", batch_stopping = "stopping after this song…",
      batch_q = "Prepare %d song(s) one after the other?\n\nEach project is opened in a tab, prepared (“Do everything”), saved and closed. Allow a few minutes per song (more with stem separation).",
      close = "Close",
      manage = "Manage…", duplicate = "Duplicate", archive = "Archive", trash = "Trash", restore = "Restore…",
      portable = "Portable copy…", manage_busy = "Stop playback and wait for the current task.",
      manage_open = "Close this concert in every REAPER project tab first.",
      destination = "New destination folder:", manage_title = "Manage concert",
      recover_none = "No concerts in the local archive or trash.",
      recover_q = "Move this concert to a recovery folder? Source song projects are kept.",
      save_failed = "Could not save the setlist: ",
    },
  }
  local function t(k) return ctx.tr(TXT, k) end
  local M = {}
  local projects = nil                 -- {path, name, prepared, bpm}
  local cache = {}                     -- path -> {size, prepared, bpm}
  local scroll = 0
  local concerts, setlists = nil, nil
  local ed = { name = nil, path = nil, songs = {}, extra = nil }
  local picked = {}                    -- path -> true : sélection pour la préparation en lot
  local ORDER = { "name", "gap_s", "songs", "live", "live_exceptions" }
  local function worker_busy()
    return ctx.job or (R.active_job and R.active_job())
      or (ctx.jobs and ctx.jobs.busy and ctx.jobs.busy())
  end

  -- un projet est « préparé » s'il a des régions et une piste CLICK ; tempo : 1er point de la carte
  local function tokens(line)
    local out, i, n = {}, 1, #line
    while i <= n do
      local c = line:sub(i, i)
      if c:match("%s") then i = i + 1
      elseif c == '"' then
        local j = line:find('"', i + 1, true) or n + 1
        out[#out + 1] = line:sub(i + 1, j - 1); i = j + 1
      else
        local j = line:find("%s", i) or n + 1
        out[#out + 1] = line:sub(i, j - 1); i = j
      end
    end
    return out
  end

  function M.inspect_rpp(src)
    local regions, click = false, false
    for line in src:gmatch("[^\r\n]+") do
      local l = line:match("^%s*(.*)$")
      if l:sub(1, 7) == "MARKER " and not regions then
        local tk = tokens(l)
        if tonumber(tk[5]) and (math.floor(tonumber(tk[5])) & 1) == 1 then regions = true end
      elseif l == 'NAME CLICK' or l == 'NAME "CLICK"' then click = true end
    end
    local bpm = tonumber(src:match("<TEMPOENVEX.-\n%s*PT%s+[%d%.]+%s+([%d%.]+)")) or tonumber(src:match("\n%s*TEMPO%s+([%d%.]+)"))
    return { prepared = regions and click, bpm = bpm }
  end

  local function add_dir(dir, out, skip)
    local i = 0
    while true do
      local f = reaper.EnumerateFiles(dir, i)
      if not f then break end
      if f:lower():match("%.rpp$") and not f:lower():match("%-bak%.rpp$") then
        local path = dir .. SEP .. f
        local src = L.read(path)
        if src then
          local c = cache[path]
          if not c or c.size ~= #src then c = M.inspect_rpp(src); c.size = #src; cache[path] = c end
          out[#out + 1] = { path = path, name = f:gsub("%.[Rr][Pp][Pp]$", ""), prepared = c.prepared, bpm = c.bpm }
        end
      end
      i = i + 1
    end
  end

  local SKIP = { concerts = true, backups = true, media = true, peaks = true }
  function M.scan()
    local dir = L.projects_dir()
    local out = {}
    add_dir(dir, out)
    local cdir = L.concert_dir():lower()
    local k = 0
    while reaper.EnumerateSubdirectories do
      local sd = reaper.EnumerateSubdirectories(dir, k)
      if not sd then break end
      local full = dir .. SEP .. sd
      if not SKIP[sd:lower()] and full:lower() ~= cdir and not sd:match("%-stems$") then add_dir(full, out) end
      k = k + 1
    end
    table.sort(out, function(a, b) return a.name:lower() < b.name:lower() end)
    projects = out
    concerts, setlists = L.list_concerts(), L.list_setlists()
    return out
  end

  -- setlist en cours d'édition ------------------------------------------------------------------
  function M.load_setlist(path)
    local d = R.json_decode(L.read(path) or "")
    if type(d) ~= "table" then return false end
    ed = { name = d.name or path:match("([^/\\]+)%.setlist%.json$"), path = path, songs = {}, extra = d }
    for _, e in ipairs(d.songs or {}) do
      if type(e) == "table" then
        ed.songs[#ed.songs + 1] = { project = e.project or e.path or e.name, title = e.title }
      else
        ed.songs[#ed.songs + 1] = { project = e, title = tostring(e):match("([^/\\]+)%.[Rr][Pp][Pp]$") or tostring(e) }
      end
    end
    return true
  end

  local function ed_paths()
    if ed.path then
      local stem = ed.path:gsub("%.setlist%.json$", "")
      return ed.path, stem .. ".RPP", stem .. ".concert.lua"
    end
    local name = ed.name or t("unnamed")
    local dir = L.concert_dir()
    local stem = ctx.slug(name)
    return dir .. SEP .. stem .. ".setlist.json", dir .. SEP .. stem .. ".RPP", dir .. SEP .. stem .. ".concert.lua"
  end

  function M.save()
    if ctx.require_edit and not ctx.require_edit() then return nil end
    if worker_busy() or (reaper.GetPlayState and reaper.GetPlayState() ~= 0) then
      ctx.show_result(T("error_title"), t("manage_busy"), false); return nil
    end
    local name = ed.name or t("unnamed")
    local path = ed_paths()
    reaper.RecursiveCreateDirectory(path:match("^(.*)[/\\]") or L.concert_dir(), 0)
    local d = {}
    for key, value in pairs(ed.extra or {}) do d[key] = value end
    -- profil « joué en live » : celui du fichier existant s'il y en a un
    local cur = R.json_decode(L.read(path) or "")
    if type(cur) == "table" then
      d.live = cur.live or d.live
      d.live_exceptions = cur.live_exceptions or d.live_exceptions
      d.gap_s = cur.gap_s or d.gap_s
    end
    d.name = name
    d.gap_s = d.gap_s or 4
    local songs = R.json_array({})
    for _, s in ipairs(ed.songs) do songs[#songs + 1] = { project = s.project, title = s.title } end
    d.songs = songs
    d.live = d.live or R.json_array({})
    if type(d.live) == "table" and #d.live == 0 then d.live = R.json_array({}) end
    d.live_exceptions = d.live_exceptions or {}
    if not R.write_atomic(path, R.json_encode(d, "  ", ORDER)) then
      ctx.show_result(T("error_title"), t("save_failed") .. path, false)
      return nil
    end
    ed.name, ed.extra, ed.path = name, d, path
    return path
  end

  local function built_concert()
    local _, rpp, side = ed_paths()
    if not L.exists(rpp) then return nil end
    return L.load_file(side)
  end

  function M.build()
    if #ed.songs == 0 or ctx.job then return false end
    local unprep = {}
    for _, s in ipairs(ed.songs) do
      local c = cache[s.project]
      if c and not c.prepared then unprep[#unprep + 1] = "· " .. (s.title or s.project) end
    end
    if #unprep > 0 and reaper.ShowMessageBox(string.format(t("unprepared_q"), table.concat(unprep, "\n")), T("title"), 1) ~= 1 then
      return false
    end
    local path = M.save()
    if not path then return false end
    local _, rpp = ed_paths()
    local name = ed.name
    return ctx.start_cli(ctx.cli_setlist(path), t("building"), function(state, msg)
      concerts, setlists = nil, nil
      if state == "done" then
        ctx.open_built(rpp)
        ctx.flash = { txt = string.format(t("built"), name), t = reaper.time_precise() }
      else
        ctx.show_result(T("error_title"), msg, false)
      end
    end)
  end

  -- Files are managed by the Python transaction; no moves/deletes in the UI.
  local function pathkey(p) return (p or ""):gsub("\\", "/"):lower() end
  function M.manage(operation, path, name, destination)
    if ctx.require_edit and not ctx.require_edit() then return false end
    if worker_busy() or (reaper.GetPlayState and reaper.GetPlayState() ~= 0) then
      ctx.show_result(T("error_title"), t("manage_busy"), false); return false
    end
    local rpp = path:gsub("%.setlist%.json$", ".RPP")
    local restore_rpp
    if operation == "restore" then
      local folder = path:match("^(.*)[/\\]")
      local recovery = R.json_decode(L.read(folder .. SEP .. "recovery.json") or "")
      if type(recovery) == "table" and recovery.original_directory then
        restore_rpp = (destination or recovery.original_directory) .. SEP .. path:match("([^/\\]+)$"):gsub("%.setlist%.json$", ".RPP")
      end
    end
    local seen = {}
    for i = 0, 1024 do
      local proj, file = reaper.EnumProjects(i, "")
      if not proj or seen[proj] then break end
      seen[proj] = true
      if pathkey(file) == pathkey(rpp) or (restore_rpp and pathkey(file) == pathkey(restore_rpp)) then
        ctx.show_result(T("error_title"), t("manage_open"), false); return false
      end
      if reaper.GetPlayStateEx and reaper.GetPlayStateEx(proj) ~= 0 then
        ctx.show_result(T("error_title"), t("manage_busy"), false); return false
      end
    end
    local quote = (reaper.GetOS() or ""):match("Win") and R.winq or R.shq
    local cmd = "concert-manage --operation " .. operation .. " --setlist " .. quote(path)
    if name then cmd = cmd .. " --name " .. quote(name) end
    if destination then cmd = cmd .. " --destination " .. quote(destination) end
    return ctx.start_cli(cmd, t("manage_title"), function(state, msg)
      if state == "done" then
        if ed.path == path then
          if operation == "rename" then
            ed.name = name
            ed.path = (destination or path:match("^(.*)[/\\]")) .. SEP .. ctx.slug(name) .. ".setlist.json"
            if ed.extra then ed.extra.name = name end
          elseif operation == "archive" or operation == "trash" then
            ed = { name = nil, path = nil, songs = {}, extra = nil }
          end
        end
        M.scan()
        ctx.flash = { txt = msg, t = reaper.time_precise() }
      else ctx.show_result(T("error_title"), msg, false) end
    end)
  end

  function M.recoveries()
    local out = {}
    for _, kind in ipairs({ ".reacue-archive", ".reacue-trash" }) do
      local root = L.concert_dir() .. SEP .. kind
      local i = 0
      while reaper.EnumerateSubdirectories do
        local folder = reaper.EnumerateSubdirectories(root, i)
        if not folder then break end
        local dir = root .. SEP .. folder
        local d = R.json_decode(L.read(dir .. SEP .. "recovery.json") or "")
        if type(d) == "table" and type(d.setlist) == "string" and not d.setlist:find("[/\\]") then
          out[#out + 1] = { name = d.name or d.setlist, path = dir .. SEP .. d.setlist, date = folder }
        end
        i = i + 1
      end
    end
    table.sort(out, function(a, b) return a.date > b.date end)
    return out
  end

  local function restore_menu()
    if ctx.require_edit and not ctx.require_edit() then return end
    if worker_busy() then ctx.show_result(T("error_title"), t("manage_busy"), false); return end
    local choices, labels = M.recoveries(), {}
    if #choices == 0 then ctx.show_result(t("manage_title"), t("recover_none"), false); return end
    for _, d in ipairs(choices) do labels[#labels + 1] = (d.name .. " · " .. d.date):gsub("[|<>#!]", " ") end
    local selected = gfx.showmenu(table.concat(labels, "|"))
    if choices[selected] then M.manage("restore", choices[selected].path) end
  end

  local function manage_menu(d)
    if worker_busy() then ctx.show_result(T("error_title"), t("manage_busy"), false); return end
    local choice = gfx.showmenu(table.concat({t("rename"), t("duplicate"), t("archive"), t("trash"), t("portable")}, "|"))
    local operation = ({"rename", "duplicate", "archive", "trash", "portable"})[choice]
    if not operation then return end
    if operation == "rename" or operation == "duplicate" then
      local initial = (d.name or "") .. (operation == "duplicate" and " - copie" or "")
      local ok, name = reaper.GetUserInputs(t("name_title"), 1, t("name_field") .. ",extrawidth=120", initial)
      if ok and name and name:match("%S") then M.manage(operation, d.setlist, name) end
    elseif operation == "portable" then
      local ok, dest = reaper.GetUserInputs(t("manage_title"), 1, t("destination") .. ",extrawidth=260",
                                           L.concert_dir() .. SEP .. ctx.slug(d.name or "Concert") .. " - portable")
      if ok and dest and dest:match("%S") then M.manage(operation, d.setlist, nil, dest) end
    elseif reaper.ShowMessageBox(t("recover_q"), t("manage_title"), 1) == 1 then
      M.manage(operation, d.setlist)
    end
  end

  -- préparation en lot ---------------------------------------------------------------------------
  function M.batch_list()
    local out, sel = {}, {}
    for _, p in ipairs(projects or {}) do
      if picked[p.path] then sel[#sel + 1] = { path = p.path, name = p.name } end
      if not p.prepared then out[#out + 1] = { path = p.path, name = p.name } end
    end
    if #sel > 0 then return sel, true end
    return out, false
  end

  function M.start_batch()
    local list = M.batch_list()
    if #list == 0 or ctx.job then return false end
    if reaper.ShowMessageBox(string.format(t("batch_q"), #list), T("title"), 1) ~= 1 then return false end
    picked = {}
    return ctx.flow.batch(list, function() cache = {}; M.rescan = true end)
  end

  local MARK = { done = "✓", running = "●", failed = "✗", pending = "○" }
  local function draw_batch(x, y, w)
    local F = ctx.flow
    local b = F.batch_run
    if b then
      U.set(U.PANEL2); gfx.rect(x - 4, y - 4, w + 8, 40 + #b.list * 24, 1)
      local done = b.n_ok + b.n_fail
      local head = t("batch") .. "  ·  " .. string.format(t("batch_progress"), math.min(done + (b.finished and 0 or 1), #b.list), #b.list)
      U.text(U.fit(head, w - 110, 14, true), x + 4, y + 4, 14, U.INK, true)
      if not b.finished then
        if U.button("bstop", t("stop"), x + w - 90, y, 90, 26, nil, 12) then F.stop_batch() end
      elseif U.button("bclose", t("close"), x + w - 90, y, 90, 26, "primary", 12) then F.batch_run = nil return y + 30 end
      -- barre globale
      U.set(U.PANEL); gfx.rect(x + 4, y + 30, w - 8, 4, 1)
      U.set(U.ACCENT); gfx.rect(x + 4, y + 30, math.floor((w - 8) * done / math.max(1, #b.list)), 4, 1)
      y = y + 40
      for _, p in ipairs(b.list) do
        local st = p.status or "pending"
        local col = (st == "done" and U.ACCENT) or (st == "running" and U.BLUE) or (st == "failed" and U.RED) or U.GREY
        U.text(MARK[st] or "○", x + 6, y + 1, 14, col, true)
        local right = ""
        if st == "running" then
          local s = F.run and F.run.steps[F.run.i]
          right = s and F.label(s.id) or ""
          if b.stop then right = t("batch_stopping") end
        elseif p.secs then right = string.format("%d s", math.floor(p.secs + 0.5)) end
        if st == "failed" and p.msg then right = p.msg end
        local rw = math.min(w * 0.55, U.text_w(right, 11))
        U.text(U.fit(p.name, w - rw - 40, 13), x + 26, y + 2, 13, st == "pending" and U.MUTED or U.INK)
        U.text(U.fit(right, w * 0.55, 11), x + w - rw - 4, y + 4, 11, st == "failed" and U.WARN or U.MUTED)
        y = y + 24
      end
      if b.finished then
        U.text(string.format(t("batch_done"), b.n_ok, b.n_fail), x, y + 2, 12, b.n_fail > 0 and U.WARN or U.ACCENT, true)
        y = y + 20
      end
      return y + 8
    end
    local list, is_sel = M.batch_list()
    if #list == 0 then
      U.text(t("batch_none"), x, y + 4, 12, U.ACCENT)
      return y + 26
    end
    local lab = string.format(is_sel and t("batch_sel") or t("batch_all"), #list)
    local bw = math.min(w, U.text_w(lab, 13) + 30)
    if U.button("batch", lab, x, y, bw, 30, nil, 13) and not ctx.job then M.start_batch() end
    return y + 40
  end

  function M.enter() M.scan() end
  function M.project_changed() concerts, setlists = nil, nil end

  -- dessin -----------------------------------------------------------------------------------
  -- « + Nouveau morceau » sous la liste (un MP3 ou un dossier de stems) ; clic sur un nom = l'ouvrir
  local function draw_new(x, y, w)
    local NS = ctx.newsong
    if not NS then return y end
    local nw = math.min(w, U.text_w(NS.t("button"), 12) + 22)
    if U.button("cnewsong", NS.t("button"), x, y + 2, nw, 24, nil, 12) and not ctx.job then NS.start() end
    return y + 32
  end

  local function draw_projects(x, y, w, maxrows)
    local dir = L.projects_dir()
    U.heading(U.fit(string.format(t("songs"), dir:match("([^/\\]+)$") or dir), w - 80, 12), x, y)
    local rw = U.text_w(t("refresh"), 11) + 14
    if U.button("rescan", t("refresh"), x + w - rw, y - 4, rw, 20, nil, 11) then M.scan() end
    y = y + 20
    if #projects == 0 then
      U.para(string.format(t("none_found"), dir), x, y, w, 12, U.MUTED, 3)
      return draw_new(x, y + 40, w)
    end
    local ROWH = 26
    local n = #projects
    local vis = math.min(n, maxrows)
    if U.over(x, y, w, vis * ROWH) and U.wheel ~= 0 then
      scroll = math.max(0, math.min(n - vis, scroll + (U.wheel > 0 and -1 or 1)))
    end
    scroll = math.max(0, math.min(math.max(0, n - vis), scroll))
    for k = 1, vis do
      local p = projects[k + scroll]
      local yy = y + (k - 1) * ROWH
      U.set(U.PANEL2); gfx.rect(x, yy, w, ROWH - 3, 1)
      local mark = p.prepared and t("prepared") or t("to_prepare")
      local right = (p.bpm and string.format("%.0f", p.bpm) or "") .. "  " .. mark
      local rwid = U.text_w(right, 11)
      local nover = U.over(x, yy, w - rwid - 68, ROWH - 3)
      U.text(U.fit(p.name, w - rwid - 68, 13), x + 6, yy + 4, 13, nover and U.BLUE or (p.prepared and U.INK or U.WARN))
      if nover and U.clicked then                      -- clic sur le nom : ouvrir le morceau (nouvel onglet)
        if (ctx.proj_file or ""):lower() ~= p.path:lower() then
          reaper.Main_OnCommand(40859, 0)
          reaper.Main_openProject(p.path)
        end
        ctx.refresh(true)
        ctx.goto_tab("song")
        return y
      end
      U.text(right, x + w - 30 - rwid - 30, yy + 6, 11, p.prepared and U.ACCENT or U.WARN)
      -- case à cocher : sélection pour la préparation en lot
      local cbx = x + w - 52
      local on = picked[p.path]
      local cov = U.over(cbx, yy + 3, 18, 18)
      if cov then U.hover = "bsel" .. k end
      U.set(U.INSET); gfx.rect(cbx, yy + 3, 17, 17, 1)
      U.set(on and U.SIG or U.MUTED, on and 1 or 0.7); gfx.rect(cbx, yy + 3, 17, 17, 0)
      if on then gfx.rect(cbx + 4, yy + 7, 10, 10, 1) end
      if cov and U.clicked then picked[p.path] = (not on) or nil end
      if U.ibutton("addp" .. k, "plus", x + w - 28, yy + 1, 26, ROWH - 5) then
        ed.songs[#ed.songs + 1] = { project = p.path, title = p.name }
      end
    end
    if n > vis then U.text(string.format("%d–%d / %d", scroll + 1, scroll + vis, n), x, y + vis * ROWH + 2, 11, U.MUTED) end
    y = y + vis * ROWH + (n > vis and 18 or 4)
    return draw_new(x, y, w)
  end

  local function draw_setlist(x, y, w)
    local name = ed.name or t("unnamed")
    local rw = U.text_w(t("rename"), 11) + 14
    U.heading(U.fit(string.format(t("setlist"), name), w - rw - 8, 12), x, y)
    if U.button("rename", t("rename"), x + w - rw, y - 4, rw, 20, nil, 11) then
      local ok, v = reaper.GetUserInputs(t("name_title"), 1, t("name_field") .. ",extrawidth=120", name)
      if ok and v and v:gsub("%s", "") ~= "" then
        if ed.path and L.exists(ed.path) then M.manage("rename", ed.path, v)
        else ed.name = v end
      end
    end
    y = y + 20
    if #ed.songs == 0 then
      U.text(t("empty"), x, y + 4, 12, U.MUTED)
      y = y + 26
    end
    local ROWH = 26
    for k, s in ipairs(ed.songs) do
      local yy = y
      U.set(U.PANEL2); gfx.rect(x, yy, w, ROWH - 3, 1)
      local c = cache[s.project]
      U.text(U.fit(k .. ". " .. (s.title or "?"), w - 96, 13), x + 6, yy + 4, 13, (c and not c.prepared) and U.WARN or U.INK)
      local bx = x + w - 3 * 26 - 4
      if U.ibutton("up" .. k, "up", bx, yy + 1, 24, ROWH - 5) and k > 1 then
        ed.songs[k], ed.songs[k - 1] = ed.songs[k - 1], ed.songs[k]
      end
      if U.ibutton("dn" .. k, "down", bx + 26, yy + 1, 24, ROWH - 5) and k < #ed.songs then
        ed.songs[k], ed.songs[k + 1] = ed.songs[k + 1], ed.songs[k]
      end
      if U.ibutton("rm" .. k, "x", bx + 52, yy + 1, 24, ROWH - 5) then table.remove(ed.songs, k) return y + ROWH end
      y = y + ROWH
    end
    local bc = built_concert()
    local foot
    if bc and #bc.songs > 0 then
      foot = string.format(t("total"), #ed.songs, L.fmt_time(bc.songs[#bc.songs].stop))
    else
      foot = string.format(t("n_songs"), #ed.songs) .. " · " .. t("not_built")
    end
    U.text(U.fit(foot, w, 11), x, y + 2, 11, U.MUTED)
    return y + 20
  end

  local function draw_existing(x, y, w)
    if not concerts then concerts, setlists = L.list_concerts(), L.list_setlists() end
    U.heading(t("existing"), x, y)
    local restore_w = U.text_w(t("restore"), 11) + 14
    if U.button("crestore", t("restore"), x + w - restore_w, y - 4, restore_w, 20, nil, 11) and not ctx.job then restore_menu() end
    y = y + 20
    local function row(k, d, built)
      local bw = U.text_w(t("load"), 12) + 16
      local ow = U.text_w(t("open_one"), 12) + 16
      local mw = U.text_w(t("manage"), 12) + 16
      U.set(U.PANEL2); gfx.rect(x, y, w, 23, 1)
      local lab = string.format(L.tr("n_songs"), d.name or "?", d.songs and #d.songs or 0)
      if not built then lab = (d.name or "?") .. "  ·  " .. t("not_built") end
      U.text(U.fit(lab, w - bw - ow - mw - 26, 13), x + 6, y + 4, 13, U.INK)
      if U.button("mg" .. k, t("manage"), x + w - bw - ow - mw - 12, y + 1, mw, 21, nil, 12) and not ctx.job then manage_menu(d) end
      if U.button("ld" .. k, t("load"), x + w - bw - ow - 6, y + 1, bw, 21, nil, 12) then
        M.load_setlist(d.setlist)
      end
      if built and U.button("op" .. k, t("open_one"), x + w - ow, y + 1, ow, 21, nil, 12) then
        L.open_concert(d)
        ctx.refresh(true)
      end
      y = y + 26
    end
    for k, d in ipairs(concerts) do row("c" .. k, d, true) end
    for k, d in ipairs(setlists) do row("s" .. k, d, false) end
    return y
  end

  function M.draw(x, y, w)
    if not projects or M.rescan then M.rescan = nil; M.scan() end
    if ctx.job and not ctx.flow.batch_active() then y = y + ctx.draw_job(x, y, w) end
    local two = w >= 500
    local y_end
    if two then
      local cw = math.floor((w - 16) / 2)
      local y1 = draw_projects(x, y, cw, 12)
      local y2 = draw_setlist(x + cw + 16, y, cw)
      y_end = math.max(y1, y2)
    else
      y_end = draw_projects(x, y, w, 8)
      y_end = draw_setlist(x, y_end + 10, w)
    end
    y = y_end + 10
    -- actions
    local bc = built_concert()
    local busy = ctx.job ~= nil
    local gap = 6
    local labels = { t("new"), bc and t("rebuild") or t("build"), t("open"), t("live") }
    local bw = (w - 3 * gap) / 4
    if U.button("cnew", labels[1], x, y, bw, 32, nil, 13) then ed = { name = nil, path = nil, songs = {}, extra = nil } end
    if U.button("cbuild", labels[2], x + (bw + gap), y, bw, 32, (#ed.songs > 0) and "primary" or nil, 13) and not busy then M.build() end
    if U.button("copen", labels[3], x + 2 * (bw + gap), y, bw, 32, nil, 13) and bc then
      L.open_concert(bc)
      ctx.refresh(true)
    end
    if U.button("clive", labels[4], x + 3 * (bw + gap), y, bw, 32, nil, 13) and #ed.songs > 0 then
      local path = M.save()
      if not path then return y end
      local c = bc or { setlist = path, songs = {} }
      if not bc then for _, s in ipairs(ed.songs) do c.songs[#c.songs + 1] = { title = s.title } end end
      c.setlist = path
      ctx.open_live(c)
    end
    y = y + 44
    y = draw_batch(x, y, w)
    if ctx.flash and reaper.time_precise() - ctx.flash.t < 3 then
      U.text(U.fit(ctx.flash.txt, w, 12), x, y - 6, 12, ctx.flash.bad and U.WARN or U.ACCENT, true)
      y = y + 14
    end
    y = draw_existing(x, y, w)
    return y + 6
  end

  return M
end
