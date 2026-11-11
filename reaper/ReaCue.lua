-- ReaCue : fenêtre principale, en 5 onglets / main window, 5 tabs (French / English).
--   Morceau  : grand bouton « étape suivante » (Séparer les stems → Analyser et préparer → Prêt ✓),
--              « Tout faire » (liste d'étapes), pastilles d'état, structure en bande colorée (écouter,
--              renommer, déplacer, fusionner, couper, supprimer, annuler / rétablir), paroles, concert
--   Concert  : composer une setlist avec les projets préparés, construire / reconstruire, ouvrir,
--              « joué en live » (stems coupés), concerts existants, préparation en lot
--   Scène    : pilotage (transport, sections, setlist), instruments (mute / solo / tout entendre),
--              répétition (boucle avec 1 mesure de décompte, ralenti), Vérifier, QR, PIN de la Régie
--   Lumière  : console grandMA3 : cues et timecode, réglages gma3_*, pistes TIMECODE, export, test d'envoi
--              (10 s, pistes TIMECODE seules, état rétabli)
--   Réglages : reacue_settings.json sans éditer le fichier, vue simple / avancée, « Vérifier
--              l'installation » (assistant du premier lancement), version, licences
-- Ligne d'aide en bas : rôle de l'élément survolé. Erreurs : cause, solution et bouton d'action.
-- Tant que la fenêtre est ouverte (quel que soit l'onglet, même ancrée) : arrêt automatique en fin de
-- morceau (concert), boucle de répétition, télécommande Régie des téléphones, profil « joué en live ».
-- Clic droit : ancrer / détacher. Échap : fermer une vue (QR, Vérifier…) puis la fenêtre.

local script_dir = debug.getinfo(1, "S").source:match("^@?(.*[/\\])") or ""
local SCRIPT = script_dir .. "ReaCue.lua"
if reaper.get_action_context then SCRIPT = select(2, reaper.get_action_context()) or SCRIPT end
local START_TAB = REACUE_START_TAB          -- « ReaCue - Concert » ouvre la même fenêtre sur l'onglet Scène

-- une seule fenêtre : si une autre action ReaCue l'a déjà ouverte, on lui demande de changer d'onglet
do
  local alive = tonumber(reaper.GetExtState("ReaCue", "win_alive"))
  local who = reaper.GetExtState("ReaCue", "win_script")
  if alive and reaper.time_precise() - alive < 1.5 and who ~= "" and who ~= SCRIPT then
    reaper.SetExtState("ReaCue", "win_goto", START_TAB or "auto", false)
    return
  end
end
-- relancer l'action redémarre la fenêtre (pas de question « terminate instances ») ; bouton allumé
if reaper.set_action_options then reaper.set_action_options(1 | 2 | 4) end

local L = dofile(script_dir .. "ReaCue_concert_lib.lua")
local U = dofile(script_dir .. "ReaCue_ui.lua")
local S = dofile(script_dir .. "ReaCue_stems.lua")
local R = L.R
U.init(R.is_windows())
local SEP = package.config:sub(1, 1)

local TXT = {
  fr = {
    title = "ReaCue", tabs = { song = "Morceau", concert = "Concert", stage = "Scène", lighting = "Lumière", settings = "Réglages" },
    clock = "Temps", tempo = "Tempo", project = "Aucun projet",
    bridge = "pont", web = "web", close = "Fermer", ok = "OK", running = "%s… %d s", again = "encore ?",
    working = "en cours", done_title = "Terminé", error_title = "Erreur",
  },
  en = {
    title = "ReaCue", tabs = { song = "Song", concert = "Concert", stage = "Stage", lighting = "Lighting", settings = "Settings" },
    clock = "Time", tempo = "Tempo", project = "No project",
    bridge = "bridge", web = "web", close = "Close", ok = "OK", running = "%s… %d s", again = "again?",
    working = "running", done_title = "Done", error_title = "Error",
  },
}
local function T(k)
  local l = TXT[L.lang()] or TXT.fr
  local v = l[k]
  if v == nil then v = L.tr(k) end
  return v
end

-- contexte partagé par les onglets -------------------------------------------------------
local ctx = {
  L = L, U = U, R = R, S = S, T = T, dir = script_dir, SEP = SEP,
  tab = nil, overlay = nil, job = nil, result = nil,
  c = nil, is_concert = false, proj_key = nil, proj_file = "", proj_name = "",
  layout_h = nil, W = 920, overlays = {},
}
REACUE_CTX = ctx                       -- tests (état partagé de la fenêtre)
function ctx.lang() return L.lang() end
function ctx.colon() return L.lang() == "fr" and " : " or ": " end   -- « Solution : » / “Solution:”
function ctx.tr(tbl, k)       -- textes d'un module : tbl = {fr = {...}, en = {...}}
  local l = tbl[L.lang()] or tbl.fr
  local v = l[k]
  if v == nil then v = tbl.fr[k] end
  if v == nil then v = T(k) end
  return v
end

function ctx.is_locked() return R.show_locked() end
function ctx.require_edit()
  if not ctx.is_locked() then return true end
  ctx.last_error = R.lock_message()
  if ctx.show_result then ctx.show_result(T("error_title"), ctx.last_error, false) end
  return false
end
function ctx.set_locked(on)
  if on and (ctx.job or ctx.tc_test or L.reh.on or R.active_job() or (ctx.jobs and ctx.jobs.busy())) then
    ctx.last_error = ctx.lang() == "fr" and "Termine les traitements et quitte la répétition avant de verrouiller."
      or "Finish active tasks and leave rehearsal before locking."
    if ctx.show_result then ctx.show_result(T("error_title"), ctx.last_error, false) end
    return false
  end
  reaper.RecursiveCreateDirectory(R.DIR, 0)
  if not R.write_atomic(R.DIR .. SEP .. "show_lock.json", R.json_encode({locked=on==true, time=os.time()})) then
    ctx.last_error = ctx.lang() == "fr" and "Impossible d’enregistrer le verrou." or "Could not save the show lock."
    return false
  end
  return true
end

local TAB_ORDER = { "song", "concert", "stage", "lighting", "settings" }
ctx.guide = dofile(script_dir .. "ReaCue_guide.lua")(ctx)          -- aide au survol, erreurs expliquées
local tabs = {}
for _, k in ipairs(TAB_ORDER) do
  tabs[k] = dofile(script_dir .. "ReaCue_tab_" .. k .. ".lua")(ctx)
end
ctx.tabs = tabs
ctx.newsong = dofile(script_dir .. "ReaCue_newsong.lua")(ctx)      -- « + Nouveau morceau »
ctx.jobs = dofile(script_dir .. "ReaCue_jobs.lua")(ctx)
ctx.overlays.jobs = ctx.jobs.draw
ctx.flow = dofile(script_dir .. "ReaCue_flow.lua")(ctx)            -- « Tout faire », lot
dofile(script_dir .. "ReaCue_assistant.lua")(ctx)                  -- assistant (ctx.assistant)

function ctx.goto_tab(t)
  if not tabs[t] then return end
  ctx.tab = t
  ctx.overlay = nil
  reaper.SetExtState("ReaCue", "tab", t, true)
  if tabs[t].enter then tabs[t].enter() end
end

-- projet ouvert : concert (fichier .concert.lua) ou morceau (concert « fictif » d'un seul morceau) -------
local function has_audio()
  for i = 0, (reaper.CountMediaItems and reaper.CountMediaItems(0) or 0) - 1 do
    local it = reaper.GetMediaItem(0, i)
    local tk = it and reaper.GetActiveTake(it)
    if tk and not (reaper.TakeIsMIDI and reaper.TakeIsMIDI(tk)) then return true end
  end
  return false
end

function ctx.refresh(force)
  local proj, fn = reaper.EnumProjects(-1, "")
  fn = fn or ""
  local key = tostring(proj) .. "|" .. fn
  if not force and key == ctx.proj_key then return false end
  local first = ctx.proj_key == nil
  ctx.proj_key = key
  ctx.proj_file = fn
  ctx.proj_name = (fn:match("([^/\\]+)%.[Rr][Pp][Pp]$")) or ""
  local c = L.load_concert()
  ctx.is_concert = c ~= nil
  if c then
    L.publish_prompter(c)
  else
    c = tabs.song.pseudo_concert and tabs.song.pseudo_concert() or nil
  end
  ctx.c = c
  L.mix.song, L.mix.src, L.mix.t = nil, nil, -1e9
  for _, k in ipairs(TAB_ORDER) do if tabs[k].project_changed then tabs[k].project_changed() end end
  -- onglet choisi automatiquement : concert → Scène, morceau → Morceau (sinon le dernier utilisé)
  local want
  if ctx.flow and ctx.flow.batch_active() then return true end      -- lot en cours : on reste sur Concert
  if first and START_TAB then want = START_TAB
  elseif ctx.is_concert then want = "stage"
  elseif has_audio() then want = "song"
  else want = ctx.tab or reaper.GetExtState("ReaCue", "tab") end
  if not tabs[want] then want = "concert" end
  if want ~= ctx.tab then ctx.goto_tab(want) end
  return true
end

-- tâches en arrière-plan (CLI ReaCue, séparation de stems) : une à la fois ---------------------
-- on_done(state, message) ; la fenêtre affiche la progression dans l'onglet
-- quiet : en cas d'échec au lancement, pas de message (ctx.last_error ; « Tout faire » l'affiche)
function ctx.start_cli(cmd, label, on_done, quiet)
  if not ctx.require_edit() then return false end
  if ctx.job then ctx.last_error = R.tr("busy") return false end
  local ok, err, data = R.start(cmd, script_dir, not cmd:match("^concert") and not cmd:match("^import%-audio"))
  if not ok then
    ctx.last_error = err
    if not quiet then ctx.show_result(T("error_title"), err, false) end
    return false
  end
  ctx.job = { kind = "cli", id = data and data.id, project = ctx.proj_file, cmd = cmd:match("^(%S+)"),
    label = label, t0 = reaper.time_precise(), on_done = on_done }
  return true
end

function ctx.start_stems(on_done, quiet)
  if not ctx.require_edit() then return false end
  if ctx.job then ctx.last_error = R.tr("busy") return false end
  local job, err = S.start(R, script_dir)
  if not job then
    ctx.last_error = err
    if not quiet then ctx.show_result(T("error_title"), err, false) end
    return false
  end
  if job.ready then
    local msg, finish_err = S.finish(R, job)
    if on_done then on_done(msg and "done" or "error", msg or finish_err) end
    return true
  end
  ctx.job = { kind = "stems", id=job.id, sj = job, label = S.tr(R, "starting"), t0 = reaper.time_precise(), on_done = on_done }
  return true
end

local function poll_job()
  local j = ctx.job
  if not j then return end
  local now = reaper.time_precise()
  if j.kind == "task" then                       -- tâche Lua par étapes (copie d'un nouveau morceau)
    local st, v, lab = j.step(0.04)
    if st == "running" then
      j.pct = v or 0
      if lab then j.label = lab end
      return
    end
    ctx.job = nil
    if j.on_done then j.on_done(st == "done" and "done" or "error", v) end
    return
  end
  if j.kind == "stems" then
    local st, v = S.poll(R, j.sj)
    if st == "running" then
      j.pct = v or 0
      j.label = (v or 0) > 0 and string.format(S.tr(R, "progress"), v) or S.tr(R, "starting")
      return
    end
    ctx.job = nil
    if st == "ready" then
      local msg, finish_err = S.finish(R, j.sj)
      if j.on_done then j.on_done(msg and "done" or "error", msg or finish_err) end
    else
      if j.on_done then j.on_done("error", v) end
    end
    return
  end
  local state, msg, cmd, step, _, data = R.status(j.id)
  if j.id and data and data.id and data.id ~= j.id then return end
  -- The concert can open as soon as its RPP is ready; expensive extras keep their
  -- durable running record and worker lease, visible from Tasks.
  if state=="running" and j.cmd=="concert" and data and data.reported_state=="done" then state="done" end
  if state == "running" and data and now - (j.alive_checked or -1e9) > 3 then
    j.alive_checked=now; j.alive=R.job_active(data)
  end
  if state == "running" and data and j.alive==false then
    state, msg = "error", ctx.lang() == "fr" and "Traitement interrompu. Tu peux reprendre cette étape." or "Task interrupted. You can resume this step."
  end
  if (state == "done" or state == "error" or state == "cancelled") and (cmd == nil or cmd == j.cmd) then
    ctx.job = nil
    ctx.last_job_result = data
    if tabs.song.cli_done then tabs.song.cli_done(j.cmd, state, msg) end
    if j.on_done then j.on_done(state, msg) end
  elseif state == "running" and step and step ~= "" and (cmd == nil or cmd == j.cmd) then
    j.label = step                               -- étape en cours (« Analyse de structure… »)
    if now - j.t0 > (R.TIMEOUT or 2400) then
      ctx.job = nil
      if j.on_done then j.on_done("error", string.format(R.tr("timeout"), "cli.log")) end
    end
  elseif now - j.t0 > (R.TIMEOUT or 2400) then
    ctx.job = nil
    if j.on_done then j.on_done("error", string.format(R.tr("timeout"), "cli.log")) end
  end
end

-- ligne de progression d'une tâche ; renvoie la hauteur
function ctx.draw_job(x, y, w)
  local j = ctx.job
  if not j then return 0 end
  local el = math.floor(reaper.time_precise() - j.t0)
  U.panel(x, y, w, 30, U.INSET)
  U.set(U.BLUE); gfx.rect(x, y, 3, 30, 1)
  local spin = ({ "|", "/", "-", "\\" })[(math.floor(reaper.time_precise() * 4) % 4) + 1]
  U.text(U.fit(string.format(T("running"), j.label or T("working"), el) .. "  " .. spin, w - 20, 13, true),
    x + 12, y + 8, 13, U.INK, true)
  if j.pct and j.pct > 0 then
    U.set(U.PANEL); gfx.rect(x + 3, y + 26, w - 3, 4, 1)
    U.set(U.SIG); gfx.rect(x + 3, y + 26, math.floor((w - 3) * j.pct / 100), 4, 1)
  end
  return 38
end

-- résultat (message de fin d'une tâche) ----------------------------------------------------
function ctx.show_result(title, text, ok)
  ctx.result = { title = title, text = tostring(text or ""), ok = ok ~= false }
  if not ctx.result.ok then ctx.result.why = ctx.explain(ctx.result.text) end
  ctx.overlay = "result"
end

-- encadré « Que faire » d'une erreur (cause + solution + bouton) ; renvoie la hauteur
function ctx.draw_solution(why, x, y, w, id)
  if not why or not why.solution then return 0 end
  local E = ctx.guide.E
  local bw = why.action_label and (U.text_w(why.action_label, 13) + 26) or 0
  local tw = w - 24 - (bw > 0 and bw + 8 or 0)
  local h1 = U.para(E("solution") .. ctx.colon() .. why.solution, x + 12, y + 8, tw, 13, U.INK, 3)
  local h = math.max(h1 + 14, bw > 0 and 44 or 0)
  U.panel(x, y, w, h, U.INSET)
  U.set(U.WARN); gfx.rect(x, y, 3, h, 1)
  U.para(E("solution") .. ctx.colon() .. why.solution, x + 12, y + 8, tw, 13, U.INK, 3)
  if bw > 0 and U.button(id or "err_action", why.action_label, x + w - bw - 6, y + (h - 30) / 2, bw, 30, "primary", 13) then
    ctx.do_action(why.action)
    return h, true
  end
  return h
end

local function draw_result(x, y, w)
  local r = ctx.result
  U.text(r.title, x, y, 18, r.ok and U.INK or U.RED, true)
  if U.button("resok", T("ok"), x + w - 90, y - 4, 90, 30, "primary") then ctx.overlay = nil; ctx.result = nil return y + 40 end
  y = y + 36
  if r.why and r.why.kind ~= "generic" and r.why.cause then
    U.text(U.fit(r.why.cause, w, 14, true), x, y, 14, U.INK, true)
    y = y + 22
  end
  local h = U.para(r.text, x, y, w, 13, r.why and U.MUTED or U.INK, r.why and 12 or 34)
  y = y + h + 8
  if r.why then
    local hh, acted = ctx.draw_solution(r.why, x, y, w, "err_action")
    if acted then ctx.overlay = nil; ctx.result = nil end
    y = y + hh + 8
  end
  return y + 2
end

-- QR code du prompteur -----------------------------------------------------------------
local QR_W, QR_H = 460, 664
local qr = nil

function ctx.open_qr()
  local ips = L.local_ips()
  local port, found = L.web_port()
  local v = { ips = ips, port = port, found = found, dock = gfx.dock(-1) }
  if #ips > 0 then
    v.url = L.prompter_url(ips[1], port)
    v.studio = L.studio_url(ips[1], port)
    v.m, v.err = L.qr_matrix(v.url, script_dir)
  end
  qr = v
  ctx.overlay = "qr"
  if v.dock > 0 then gfx.dock(0) end
  gfx.init("", QR_W, QR_H)
end

local function close_qr()
  local d = qr and qr.dock or 0
  qr = nil
  ctx.overlay = nil
  if d > 0 then gfx.dock(d) else gfx.init("", ctx.W, gfx.h) end
end

local function draw_qr()
  local w, h = gfx.w, gfx.h
  U.text(L.tr("qr_title"), 18, 14, 18, U.INK, true)
  U.text(L.tr("qr_sub"), 18, 40, 13, U.MUTED)
  if U.button("qrclose", T("close"), w - 104, 12, 90, 30) then close_qr() return end
  local foot, top = 126, 66
  if not qr.url then
    U.text(L.tr("no_ip"), 18, top + 10, 15, U.INK, true)
    U.text(L.tr("no_ip2"), 18, top + 36, 13, U.MUTED)
    U.text(L.tr("no_ip3"), 18, top + 54, 13, U.MUTED)
    return
  end
  if not qr.m then
    U.text(string.format(L.tr("qr_fail"), tostring(qr.err)), 18, top + 10, 13, U.INK)
    return
  end
  local n = #qr.m
  local avail = math.min(w - 28, h - top - foot)
  local mod = math.max(1, math.floor(avail / (n + 8)))
  local size = mod * (n + 8)
  local x0 = math.floor((w - size) / 2)
  local y0 = top
  gfx.set(1, 1, 1, 1); gfx.rect(x0, y0, size, size, 1)
  gfx.set(0, 0, 0, 1)
  for x = 1, n do
    local col = qr.m[x]
    for y = 1, n do
      if col[y] > 0 then gfx.rect(x0 + (x + 3) * mod, y0 + (y + 3) * mod, mod, mod, 1) end
    end
  end
  if U.clicked and U.over(x0, y0, size, size) then close_qr() return end
  local y = y0 + size + 10
  local uw = U.text_w(qr.url, 16, true)
  U.text(qr.url, math.max(10, (w - uw) / 2), y, 16, U.INK, true)
  local note = L.tr("same_wifi")
  if #qr.ips > 1 then note = note .. string.format(L.tr("other_ip"), qr.ips[2]) end
  local nw = U.text_w(note, 13)
  U.text(note, math.max(10, (w - nw) / 2), y + 26, 13, U.MUTED)
  local pin = string.format(L.tr("pin_line"), L.remote_pin())
  local pw = U.text_w(pin, 14, true)
  U.text(pin, math.max(10, (w - pw) / 2), y + 48, 14, U.INK, true)
  local sl = string.format(L.tr("studio_line"), qr.studio or "")
  local sw = U.text_w(sl, 12)
  U.text(sl, math.max(6, (w - sw) / 2), y + 72, 12, U.MUTED)
  if not qr.found then
    local warn = L.tr("no_web")
    local ww = U.text_w(warn, 12)
    U.text(warn, math.max(6, (w - ww) / 2), y + 92, 12, U.WARN)
  end
end

-- contrôle avant concert (« Vérifier ») ---------------------------------------------------
local chk = nil
local CK_COL = { ok = U.ACCENT, warn = U.WARN, bad = U.RED, info = U.GREY }

local function run_checks()
  chk.list = L.run_checks(ctx.is_concert and ctx.c or nil)
  chk.recheck_at = nil
end

function ctx.open_check()
  chk = {}
  ctx.overlay = "check"
  run_checks()
end

local function draw_check(x, y, w)
  U.text(L.tr("check_title"), x, y, 18, U.INK, true)
  if U.button("ckclose", T("close"), x + w - 90, y - 4, 90, 30) then ctx.overlay = nil; chk = nil return y + 30 end
  if U.button("ckagain", L.tr("recheck"), x + w - 90 - 8 - 120, y - 4, 120, 30) then run_checks() end
  if chk.recheck_at and reaper.time_precise() >= chk.recheck_at then run_checks() end
  local bad, warn = L.check_summary(chk.list)
  y = y + 36
  local sum, col
  if bad > 0 then sum, col = string.format(L.tr("n_problems"), bad), CK_COL.bad
  elseif warn > 0 then sum, col = string.format(L.tr("n_warnings"), warn), CK_COL.warn
  else sum, col = L.tr("all_ready") .. "  ✓", CK_COL.ok end
  U.panel(x, y, w, 34, U.INSET)
  U.set(col); gfx.rect(x, y, 3, 34, 1); gfx.circle(x + 16, y + 17, 5, 1, 1)
  U.text(sum, x + 28, y + 8, 16, U.INK, true)
  y = y + 46
  for k, it in ipairs(chk.list) do
    local c = CK_COL[it.status] or U.GREY
    local fx = it.fix and (it.fix ~= "rebuild" or ctx.is_concert) and it.status ~= "ok"
    local tw = w - 26 - (fx and 90 or 4)
    U.set(c); gfx.circle(x + 10, y + 10, 6, 1, 1)
    U.text(U.fit(it.label, tw, 14, true), x + 24, y + 2, 14, U.INK, true)
    U.text(U.fit(it.detail, tw, 12), x + 24, y + 21, 12, it.status == "bad" and U.INK or U.MUTED)
    if fx and U.button("fix" .. k, L.tr("fix"), x + w - 78, y + 6, 78, 26) then
      if it.fix == "rebuild" then ctx.overlay = nil; chk = nil; tabs.stage.rebuild(true) return y
      elseif it.fix == "bridge" or it.fix == "web" then ctx.do_action(it.fix); chk.recheck_at = reaper.time_precise() + 0.8
      else L.apply_fix(ctx.c, it.fix); chk.recheck_at = reaper.time_precise() + 0.6 end
    end
    y = y + 42
  end
  return y + 6
end

-- en-tête : marque, onglets (barre encastrée, onglet actif clair), voyants pont / web --------------------
local function draw_brand(x, y)
  U.set(U.SIG); gfx.rect(x, y, 22, 22, 1)
  U.set(U.DARK)                                   -- tracé « pouls » du logo
  local px = { 3, 7, 9, 13, 15, 19 }
  local py = { 11, 11, 5, 17, 11, 11 }
  for i = 1, #px - 1 do
    for d = 0, 1 do gfx.line(x + px[i], y + py[i] + d, x + px[i + 1], y + py[i + 1] + d) end
  end
  local lab = U.upper(T("title"))
  U.text(lab, x + 30, y + 2, 19, U.INK, true, "cond")
  return 30 + U.text_w(lab, 19, true, "cond")
end

local function draw_header(w)
  U.set(U.PANEL2); gfx.rect(0, 0, w, 44, 1)
  U.set(U.EDGE); gfx.rect(0, 44, w, 1, 1)
  local x = 14 + draw_brand(14, 11) + 12
  local names = T("tabs")
  -- état : pont, interface web (à droite) : voyants
  local bridge = R.bridge_alive and R.bridge_alive()
  local _, web = L.web_port()
  local st = {}
  st[#st + 1] = { T("bridge"), bridge }
  st[#st + 1] = { T("web"), web }
  local sx = w - 12
  for k = #st, 1, -1 do
    local lab = st[k][1]
    local lw = U.text_w(lab, 11)
    sx = sx - lw
    U.text(lab, sx, 16, 11, U.MUTED)
    U.set(st[k][2] and U.LED or U.RED); gfx.circle(sx - 8, 22, 3.5, 1, 1)
    sx = sx - 20
  end
  local avail = sx - x - 6
  -- onglets de même largeur s'il y a la place, sinon à la largeur de leur nom (réduits si besoin)
  local n, gap = #TAB_ORDER, 2
  local tw = math.min(104, math.floor((avail - 6 - (n - 1) * gap) / n))
  local ws, tot, widest = {}, 0, 0
  for i, k in ipairs(TAB_ORDER) do
    ws[i] = U.text_w(names[k], 12, true) + 18
    tot = tot + ws[i]
    widest = math.max(widest, ws[i])
  end
  local room = avail - 6 - (n - 1) * gap
  for i = 1, n do
    if tw >= widest then ws[i] = tw
    elseif tot > room then ws[i] = math.max(36, math.floor(ws[i] * room / tot)) end
  end
  local full = 6 + (n - 1) * gap
  for i = 1, n do full = full + ws[i] end
  U.set(U.WELL); gfx.rect(x, 7, full, 30, 1)
  U.frame(x, 7, full, 30)
  x = x + 3
  for i, k in ipairs(TAB_ORDER) do
    local on = ctx.tab == k
    local over = U.over(x, 10, ws[i], 24)
    if over then U.hover = "tab_" .. k end
    if on then U.set(U.INK); gfx.rect(x, 10, ws[i], 24, 1)
    elseif over then U.set(U.INK, 0.08); gfx.rect(x, 10, ws[i], 24, 1) end
    local lab = U.fit(names[k], ws[i] - 8, 12, true)
    local lw = U.text_w(lab, 12, true)
    U.text(lab, x + (ws[i] - lw) / 2, 16, 12, on and U.DARK or (over and U.INK or U.MUTED), true)
    if over and U.clicked then ctx.goto_tab(k) end
    x = x + ws[i] + gap
  end
  if ctx.tab == "stage" then return 45 end -- Stage already has its own live banner.
  -- Studio-style project/readout strip; it reports state without changing transport.
  local by, bh = 54, 64
  local available = w - 28
  U.panel(14, by, available, bh, U.INSET)
  local state = L.play_state()
  local statecol = state == "play" and U.LED or (state == "pause" and U.LCD or U.MUTED)
  local caption = U.upper(L.tr("state")[state] or state)
  U.led(30, by + 17, 4, statecol, true)
  U.text(caption, 42, by + 10, 10, statecol, true)
  local tasks_label = ctx.lang() == "fr" and "Traitements" or "Tasks"
  if U.button("activity", tasks_label, w - 124, by + 5, 100, 24) then ctx.overlay = "jobs" end
  if ctx.is_locked() then U.text(ctx.lang() == "fr" and "VERROUILLÉ" or "LOCKED", 126, by + 10, 10, U.WARN, true) end
  local pos = math.max(0, L.pos())
  local bpm = reaper.TimeMap2_GetDividedBpmAtTime and reaper.TimeMap2_GetDividedBpmAtTime(0, pos)
  local readouts = available >= 700 and 352 or 0
  local title = ctx.proj_name ~= "" and ctx.proj_name or T("project")
  U.title(U.fit(U.upper(title), math.max(40, available - readouts - 32), 24, true, "cond"), 28, by + 30, 24)
  if readouts > 0 then
    local lx = w - 14 - readouts
    U.lcd(T("clock"), L.fmt_time(pos), lx, by + 1, 130, bh - 2, U.LCD, 24)
    U.lcd(T("tempo"), bpm and string.format("%.1f", bpm) or "—", lx + 130, by + 1, 110, bh - 2, U.LCD, 24)
  end
  return by + bh
end

-- fenêtre ancrée basse : barre compacte ------------------------------------------------------
local function draw_docked()
  if ctx.c and tabs.stage.compact then return tabs.stage.compact() end
  U.text(U.fit(T("title") .. " · " .. ctx.proj_name, gfx.w - 20, 15, true), 14, gfx.h / 2 - 9, 15, U.INK, true)
end

-- tâches de fond (tous onglets) ----------------------------------------------------------------
local CMD_TXT = L.tr("cmd")
local last_alive, last_pos, loop_last = 0, nil, nil
local last_tctest = nil
-- ReaCue Studio (Lumière, Concert) : « TEST 10 S » = test d'envoi du timecode de l'onglet Lumière
L.remote_ext.tctest = function(_, arg) return tabs.lighting.remote_test(arg) end
-- ReaCue Studio, BIBLIO : ouvrir un morceau ou un concert de la bibliothèque (chemin urlencodé du .RPP) ;
-- morceau seul : son prompteur est publié (CLI « open-song ») pour que Studio et téléphones le suivent
L.remote_ext.open = function(_, arg)
  local p = L.url_decode(arg)
  if not L.open_project(p) then return false end
  ctx.refresh(true)
  if not ctx.is_concert then L.run_cli("open-song", p, "--project") end
  return true
end

-- état du test timecode pour ReaCue Studio : secondes restantes, "" sans test
local function publish_tctest(now)
  local left = tabs.lighting.test_left and tabs.lighting.test_left(now)
  local v = left and tostring(left) or ""
  if v ~= last_tctest then reaper.SetExtState("ReaCue", "tctest", v, false); last_tctest = v end
end
ctx.flash = nil

local function poll_remote(now)
  if now - last_alive > 0.4 then L.remote_alive(now); last_alive = now end
  L.poll_seen(now)
  local cmd, res = L.remote_poll(ctx.c)
  if res and res ~= "dup" then
    if res == "ok" then
      ctx.flash = { txt = string.format(L.tr("phone"), CMD_TXT[cmd] or cmd), t = now }
      last_pos = nil
    elseif res == "badpin" then
      ctx.flash = { txt = L.tr("phone_badpin"), t = now, bad = true }
    end
  end
end

local function background(now)
  ctx.refresh(false)
  poll_job()
  ctx.flow.restore()
  if not ctx.job and now - (ctx.recovery_checked or -1e9) > 3 then
    ctx.recovery_checked=now
    local job=R.active_job()
    if job and job.project==ctx.proj_file and job.project~="" and not (job.cmd=="concert" and job.reported_state=="done") then
      ctx.job={kind="cli",id=job.id,cmd=job.cmd,project=job.project,label=job.step or job.cmd,
        t0=now-math.max(0,os.time()-(job.started or os.time())),recovered=true,
        on_done=function(state,msg)
          -- Rebuild the recovery offer from the completed durable job, without launching another stage.
          if ctx.flow.run and ctx.flow.run.finished then ctx.flow.run=nil; ctx.flow.checked=nil end
          ctx.flow.restore()
        end}
    end
  end
  ctx.flow.tick()
  R.guard_desktop_commands()
  poll_remote(now)
  local c = ctx.c
  if c and L.playing() then
    local p = reaper.GetPlayPosition()
    if L.reh.on then
      if L.loop_tick(loop_last, p) == "restart" then loop_last = nil else loop_last = p end
      last_pos = nil
    elseif ctx.is_concert and not ctx.tc_test then      -- test timecode (onglet Lumière) : pas d'arrêt auto
      local k = L.crossed_stop(c, last_pos, p)
      if k then L.after_stop(c, k); last_pos = nil else last_pos = p end
    end
  else
    if L.reh.on and c then L.loop_tick(nil, L.pos()) end
    last_pos, loop_last = nil, nil
  end
  for _, k in ipairs(TAB_ORDER) do if tabs[k].tick then tabs[k].tick(now) end end   -- test timecode : fin, Stop
  if c and not ctx.tc_test then L.mix_tick(c, now) end   -- pendant le test : mutes des instruments laissés tels quels
  publish_tctest(now)
  L.band_poll(now)                                        -- prompteurs connectés, « Prêt » (écran GROUPE)
  L.practice_tick(c, now, L.playing() and not ctx.tc_test, L.musicians(now))   -- temps de lecture (BIBLIO)
  L.studio_c = c
  L.studio_publish(false, c)                              -- ReaCue Studio : vitesse, transposition, rampe
  local g = reaper.GetExtState("ReaCue", "win_goto")
  if g ~= "" then
    reaper.SetExtState("ReaCue", "win_goto", "", false)
    if g == "auto" then ctx.refresh(true) else ctx.goto_tab(g) end
  end
  -- Typed requests from the independent local Desktop bridge. Expiring and
  -- project-bound: an old click must never act on a newly opened song.
  local desktop_action = reaper.GetExtState("ReaCue", "desktop_action")
  if desktop_action ~= "" then
    reaper.SetExtState("ReaCue", "desktop_action", "", false)
    local request = R.json_decode(desktop_action)
    local project, path = reaper.EnumProjects(-1, "")
    local key = tostring(project) .. "|" .. (path or "")
    if request and request.project_id == key and (tonumber(request.expires) or 0) >= os.time() then
      local actions = {
        new_file=function()ctx.newsong.start("file")end,
        new_stems=function()ctx.newsong.start("stems")end,
        new_link=function()ctx.newsong.start("link")end,
        prepare=tabs.song.prepare,publish=tabs.song.publish,separate=tabs.song.separate,
        do_all=tabs.song.do_all,reanalyse=tabs.song.reanalyse,
        jobs=function()ctx.overlay="jobs"end,qr=ctx.open_qr,check=ctx.open_check,
      }
      local fn = actions[request.action]
      if fn then local ok, err = pcall(fn); if not ok then ctx.show_result("ReaCue Desktop",tostring(err),false) end end
    end
  end
  reaper.SetExtState("ReaCue", "desktop_ready", "1", false)
  reaper.SetExtState("ReaCue", "win_alive", string.format("%.3f", now), false)
end

function ctx.reset_loop() loop_last = nil; last_pos = nil end

-- ligne d'aide (bas de la fenêtre) : rôle de l'élément survolé -------------------------------------
local HELP_H = 26
local function draw_help(y, w)
  local txt = ctx.help_text(U.hover) or ctx.guide.default_help()
  local h = U.text_w(txt, 12) > w - 28 and HELP_H + 16 or HELP_H     -- texte long : 2 lignes
  U.set(U.PANEL2); gfx.rect(0, y, w, h, 1)
  U.set(U.EDGE); gfx.rect(0, y, w, 1, 1)
  local hov = U.hover ~= nil or U.hover_tip ~= nil
  U.para(txt, 14, y + 6, w - 28, 12, hov and U.INK or U.MUTED, 2)
  return y + h
end

-- boucle ---------------------------------------------------------------------------------------
local dock = tonumber(reaper.GetExtState("ReaCue", "concert_dock")) or 0
gfx.init(T("title"), ctx.W, 420, dock)
reaper.SetExtState("ReaCue", "win_script", SCRIPT, false)
L.remote_pin()
pcall(L.publish_page)
L.publish_reh()
pcall(L.run_cli, "library")                  -- ReaCue Studio, BIBLIO : reacue_library.json à jour

local function loop()
  local ch = gfx.getchar()
  if ch < 0 then return end
  local now = reaper.time_precise()
  if ch == 27 then
    if ctx.overlay == "qr" then close_qr()
    elseif ctx.overlay then ctx.overlay = nil; chk = nil
    else gfx.quit() return end
  end
  U.frame_begin(now)
  background(now)
  if U.right then                                  -- clic droit : ancrer / détacher
    local d = gfx.dock(-1)
    gfx.dock(d > 0 and 0 or 1)
    reaper.SetExtState("ReaCue", "concert_dock", tostring(gfx.dock(-1)), true)
  end
  U.tick_armed()

  ctx.W = gfx.w > 0 and gfx.w or ctx.W
  local w = ctx.W
  U.set(U.BG); gfx.rect(0, 0, gfx.w, gfx.h, 1)
  local docked_low = gfx.dock(-1) > 0 and gfx.h < 130
  if ctx.overlay == "qr" and qr then
    draw_qr()
  elseif docked_low then
    draw_docked()
  else
    local y = draw_header(w) + 12
    if ctx.overlay == "result" and ctx.result then
      y = draw_result(14, y + 4, w - 28)
    elseif ctx.overlay == "check" and chk then
      y = draw_check(14, y + 4, w - 28)
    elseif ctx.overlay and ctx.overlays[ctx.overlay] then
      y = ctx.overlays[ctx.overlay](14, y + 4, w - 28) or y
    else
      y = tabs[ctx.tab].draw(14, y, w - 28) or y
    end
    y = draw_help(math.max(y + 6, (gfx.dock(-1) > 0) and (gfx.h - HELP_H) or 0), gfx.w)
    ctx.layout_h = math.max(160, math.floor(y))
    if gfx.dock(-1) == 0 and math.abs(gfx.h - ctx.layout_h) > 2 then gfx.init("", w, ctx.layout_h) end
  end
  gfx.update()
  reaper.defer(loop)
end

reaper.atexit(function()
  if reaper.set_action_options then reaper.set_action_options(8) end
  if tabs.lighting and tabs.lighting.test_stop then pcall(tabs.lighting.test_stop, "exit") end   -- solo / mute rétablis
  if L.reh.on then pcall(L.set_rehearsal, false) end
  reaper.SetExtState("ReaCue", "rehearsal", "", false)
  reaper.SetExtState("ReaCue", "studio", "", false)
  reaper.SetExtState("ReaCue", "tctest", "", false)
  reaper.SetExtState("ReaCue", "band", "", false)
  pcall(L.practice_flush)
  reaper.SetExtState("ReaCue", "win_alive", "", false)
  reaper.SetExtState("ReaCue", "win_script", "", false)
  reaper.SetExtState("ReaCue", "desktop_ready", "", false)
  reaper.SetExtState("ReaCue", "desktop_action", "", false)
  L.remote_off()
  reaper.SetExtState("ReaCue", "concert_dock", tostring(gfx.dock(-1)), true)
end)

ctx.refresh(true)
ctx.assistant.maybe_first()                  -- premier lancement : assistant d'installation (une fois)
loop()
