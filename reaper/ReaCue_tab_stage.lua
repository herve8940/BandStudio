-- ReaCue : onglet « Scène » / “Stage” tab : pilotage du concert (ou du morceau ouvert), instruments
-- (mute / solo / tout entendre / joué en live), répétition, Vérifier, QR, PIN de la Régie.
return function(ctx)
  local L, U, T = ctx.L, ctx.U, ctx.T
  local TXT = {
    fr = {
      no_project = "Aucun concert ni morceau ouvert", go_concert = "Préparer un concert", go_song = "Préparer le morceau",
      open_concert = "Ouvrir un concert (nouvel onglet) :", song_only = "Morceau seul",
      live_btn = "Joué en live…", live_none = "Ouvre ou construis d'abord un concert.",
      rebuilt = "Concert reconstruit.", song_hint = "Morceau seul : pas d'arrêt automatique ni de setlist.",
      lock = "Verrouiller la scène", unlock = "Déverrouiller…", locked = "Scène verrouillée · transport et mix disponibles",
      unlock_q = "Déverrouiller la scène et autoriser de nouveau les modifications ?",
      lock_reh = "Quitte la répétition et arrête le test timecode avant de verrouiller.",
      jobs = "Traitements",
    },
    en = {
      no_project = "No concert or song open", go_concert = "Prepare a concert", go_song = "Prepare the song",
      open_concert = "Open a concert (new tab):", song_only = "Single song",
      live_btn = "Played live…", live_none = "Open or build a concert first.",
      rebuilt = "Concert rebuilt.", song_hint = "Single song: no automatic stop and no setlist.",
      lock = "Lock the stage", unlock = "Unlock…", locked = "Stage locked · transport and mix available",
      unlock_q = "Unlock the stage and allow edits again?",
      lock_reh = "Exit rehearsal and stop the timecode test before locking.",
      jobs = "Tasks",
    },
  }
  local function t(k) return ctx.tr(TXT, k) end
  local M = {}
  local function can_edit()
    return not (ctx.require_edit and not ctx.require_edit()) and not (ctx.is_locked and ctx.is_locked())
  end
  function M.toggle_lock()
    local locked = ctx.is_locked and ctx.is_locked()
    if locked then
      if reaper.ShowMessageBox(t("unlock_q"), T("title"), 1) ~= 1 then return false end
    elseif (L.reh and L.reh.on) or ctx.tc_test then
      if ctx.show_result then ctx.show_result(T("error_title"), t("lock_reh"), false) end
      return false
    end
    return ctx.set_locked and ctx.set_locked(not locked) or false
  end
  function M.set_rehearsal(on)
    if not can_edit() then return false end
    L.set_rehearsal(on); ctx.reset_loop(); return true
  end
  function M.set_rate(rate)
    if not can_edit() then return false end
    return L.set_rate(rate)
  end
  local ROW = 26
  local keys = {}
  local secs_cache = { i = nil, t = 0, list = {} }
  local songs_open = reaper.GetExtState("ReaCue", "concert_list") ~= "0"
  local available = nil
  local STATE_COL = { play = U.LED, pause = U.LCD, stop = U.MUTED }

  function M.project_changed()
    keys = (ctx.is_concert and ctx.c) and L.song_keys(ctx.c) or {}
    secs_cache = { i = nil, t = 0, list = {} }
    available = nil
  end

  local function sections_of(i)
    local now = reaper.time_precise()
    if secs_cache.i ~= i or now - secs_cache.t > 2 then
      secs_cache = { i = i, t = now, list = L.song_sections(ctx.c, i) }
    end
    return secs_cache.list
  end
  function M.invalidate() secs_cache = { i = nil, t = 0, list = {} } end

  local function song_state(c)
    local tp = L.pos()
    local i = L.song_index(c, tp)
    local s = c.songs[i]
    local secs = sections_of(i)
    local si = L.section_at(secs, tp)
    local bar = L.bar_of(s, tp)
    return {
      t = tp, i = i, s = s, secs = secs, si = si, bar = bar, st = L.play_state(),
      dur = s.stop - s.start, el = math.max(0, math.min(tp, s.stop) - s.start), rest = math.max(0, s.stop - tp),
      total = c.songs[#c.songs].stop, key = keys[i] or s.key or nil,
    }
  end

  local function fmt_bpm(b) b = tonumber(b) or 0; return string.format("%.0f", b) end

  local function info_line(S)
    local p = { fmt_bpm(S.s.bpm) .. " BPM" }
    if S.key then p[#p + 1] = S.key end
    if S.si then p[#p + 1] = S.secs[S.si].name
    elseif S.t < (S.s.bar1 or S.s.start) and S.t >= S.s.start then p[#p + 1] = L.tr("count_in") end
    if S.bar and S.bar >= 1 and S.bar <= (S.s.bars or 0) then p[#p + 1] = string.format(L.tr("bar"), S.bar, S.s.bars) end
    return table.concat(p, " · ")
  end

  local function playing() return L.play_state() == "play" end
  local function do_prev(c) if U.confirm("prev", playing()) then L.prev(c) end end
  local function do_next(c) if U.confirm("next", playing()) then L.next(c) end end
  local function do_stop() if U.confirm("stop", playing()) then L.stop() end end

  -- reconstruction du concert ouvert (CLI ReaCue, en arrière-plan) -----------------------------
  function ctx.cli_setlist(path)
    local q = ctx.R.is_windows() and ctx.R.winq(path) or ctx.R.shq(path)
    return "concert --setlist " .. q
  end

  -- ouvre le concert construit : dans l'onglet en cours s'il y est déjà, sinon dans un nouvel onglet
  function ctx.open_built(rpp)
    if not can_edit() then return false end
    local cur = ctx.proj_file or ""
    if cur:lower() ~= tostring(rpp):lower() then reaper.Main_OnCommand(40859, 0) end
    reaper.Main_openProject(rpp)
    ctx.refresh(true)
  end

  function M.rebuild(no_confirm, target)
    if not can_edit() then return false end
    local d = target or (ctx.is_concert and ctx.c)
    if not d or not d.setlist then return end
    if not no_confirm then
      local ok = reaper.ShowMessageBox(L.tr("rebuild_q"), T("title"), 1)
      if ok ~= 1 then return end
    end
    local rpp = d.rpp
    ctx.start_cli(ctx.cli_setlist(d.setlist), L.tr("rebuild"), function(state, msg)
      if state == "done" then
        ctx.open_built(rpp)
        ctx.flash = { txt = t("rebuilt"), t = reaper.time_precise() }
      else
        ctx.show_result(T("error_title"), msg, false)
      end
    end)
  end

  -- code PIN ------------------------------------------------------------------------------
  function ctx.change_pin()
    if not can_edit() then return false end
    local ok, v = reaper.GetUserInputs(L.tr("pin_title"), 1, L.tr("pin_field") .. ",extrawidth=40", L.remote_pin())
    if not ok then return end
    if not can_edit() then return false end
    v = (v or ""):gsub("%s", "")
    if not L.set_remote_pin(v) then reaper.ShowMessageBox(L.tr("pin_bad"), T("title"), 0) end
  end

  -- instruments (stems) : mute / solo / tout entendre --------------------------------------------
  local function draw_instruments(c, S, x, y, w)
    local groups = L.instr_tracks()
    if #groups == 0 then return y end
    U.heading(L.tr("instruments") .. "  ·  " .. L.tr("solo_hint"), x, y)
    y = y + 18
    local gap = 6
    local n = #groups
    local per = math.max(1, math.min(n, math.floor((w + gap) / (78 + gap))))
    local bw = math.floor((w - (per - 1) * gap) / per)
    local bh = 40
    local col, row = 0, 0
    local play_guard = playing() and not L.reh.on
    for _, g in ipairs(groups) do
      local aud = L.mix_audible(c, S.i, g.role)
      local sub
      if L.mix.solo == g.role then sub = L.tr("mix_solo")
      else sub = aud and L.tr("mix_played") or L.tr("mix_cut") end
      if U.is_armed("mute_" .. g.role) then sub = T("again") end
      local bx, by = x + col * (bw + gap), y + row * (bh + gap)
      local r = U.press_button("mute_" .. g.role, g.label, bx, by, bw, bh, g.color, not aud, sub)
      if r == "click" then
        if U.confirm("mute_" .. g.role, play_guard) then L.mix_toggle(c, g.role) end
      elseif r == "long" then
        if U.confirm("solo_" .. g.role, false) then L.mix_solo(c, g.role) end
      end
      if L.mix.solo == g.role then U.frame(bx - 2, by - 2, bw + 4, bh + 4, U.INK); U.frame(bx - 1, by - 1, bw + 2, bh + 2, U.INK) end
      col = col + 1
      if col >= per then col = 0; row = row + 1 end
    end
    if col > 0 then row = row + 1 end
    y = y + row * (bh + gap) + 2
    local hw = U.text_w(L.tr("hear_all"), 13) + 22
    if U.button("hearall", L.tr("hear_all"), x, y, hw, 26, L.mix.hear_all and "on" or nil) then
      if U.confirm("hearall", play_guard) then L.mix_hear_all(c, not L.mix.hear_all) end
    end
    if U.is_armed("hearall") then U.text(T("again"), x + hw + 8, y + 6, 12, U.WARN, true) end
    if ctx.is_concert then
      local lw = U.text_w(t("live_btn"), 13) + 22
      if U.button("livebtn", t("live_btn"), x + w - lw, y, lw, 26) then ctx.open_live(c) end
    end
    return y + 34
  end

  -- vue « Joué en live » : profil du concert + exceptions par morceau ------------------------------
  local live_c = nil
  function ctx.open_live(c)
    if not can_edit() then return false end
    if not c or not c.setlist then ctx.show_result(T("error_title"), t("live_none"), false) return end
    live_c = c
    L.load_live(c, true)
    ctx.overlay = "live"
  end

  ctx.overlays.live = function(x, y, w)
    local c = live_c
    if not c then ctx.overlay = nil return y end
    U.text(L.tr("live_title"), x, y, 18, U.INK, true)
    if U.button("liveclose", T("close"), x + w - 90, y - 4, 90, 30) then ctx.overlay = nil return y + 30 end
    y = y + 30
    U.text(U.fit(L.tr("live_hint"), w, 12), x, y, 12, U.MUTED)
    y = y + 22
    -- rôles : ceux du concert ouvert, sinon tous
    local roles = {}
    if ctx.is_concert and ctx.c == c then
      for _, g in ipairs(L.instr_tracks()) do roles[#roles + 1] = g.role end
    end
    if #roles == 0 then for _, r in ipairs(L.ROLES) do if r[1] ~= "mix" then roles[#roles + 1] = r[1] end end end
    local gap = 6
    local per = math.max(1, math.min(#roles, math.floor((w + gap) / (96 + gap))))
    local bw = math.floor((w - (per - 1) * gap) / per)
    local col, row = 0, 0
    for _, role in ipairs(roles) do
      local on = L.mix.live[role] == true
      local bx, by = x + col * (bw + gap), y + row * 34
      if U.button("live_" .. role, (on and "✓ " or "") .. L.role_label(role), bx, by, bw, 28, on and "on" or nil, 13) and can_edit() then
        L.live_toggle(c, role)
        ctx.flash = { txt = L.tr("live_saved"), t = reaper.time_precise() }
      end
      col = col + 1
      if col >= per then col = 0; row = row + 1 end
    end
    if col > 0 then row = row + 1 end
    y = y + row * 34 + 10
    -- exceptions par morceau
    U.heading(L.tr("live_exc") .. "  ·  " .. L.tr("live_exc_hint"), x, y)
    y = y + 20
    local name_w = math.min(170, math.floor(w * 0.32))
    local cw = math.max(40, math.floor((w - name_w) / #roles))
    for k, r in ipairs(roles) do
      local lab = U.fit(L.role_label(r), cw - 4, 11)
      U.text(lab, x + name_w + (k - 1) * cw + 2, y, 11, U.MUTED)
    end
    y = y + 18
    for i, s in ipairs(c.songs) do
      U.text(U.fit(i .. ". " .. (s.title or "?"), name_w - 6, 13), x, y + 4, 13, U.INK)
      local e = L.mix.exc[s.title] or {}
      for k, r in ipairs(roles) do
        local m = e[r]
        local lab = m == "stem" and L.tr("live_exc_stem") or (m == "live" and L.tr("live_exc_live") or L.tr("live_exc_def"))
        local style = m and "warn" or "ghost"
        if U.button("exc_" .. i .. "_" .. r, lab, x + name_w + (k - 1) * cw, y, cw - 4, 24, style, 12) and can_edit() then
          L.live_exc_cycle(c, i, r)
        end
      end
      y = y + 28
    end
    if ctx.flash and reaper.time_precise() - ctx.flash.t < 2 then U.text(ctx.flash.txt, x, y + 4, 12, U.ACCENT, true) end
    return y + 24
  end

  -- vue détachée -----------------------------------------------------------------------------
  -- bandeau lecture (style « Studio pro ») : voyant + état, « MORCEAU n / N », titre en capitales condensées,
  -- afficheurs RESTE / CONCERT (jaunes) et SMPTE (bleu) ; étroit : afficheurs sur une 2e ligne
  local function smpte_now(t)
    local LT = ctx.tabs and ctx.tabs.lighting
    if not (LT and LT.smpte and LT.tc_start) then return nil end
    local _, off = LT.tc_start()
    return LT.smpte((off or 0) + math.max(0, t), LT.fps and LT.fps() or 25)
  end

  local function draw_banner(c, S, x, y, w)
    local s = S.s
    local scol = s.color and { s.color[1], s.color[2], s.color[3] } or U.SLATE
    local lcds = { { L.tr("rest_k"), L.fmt_time(S.rest), U.LCD } }
    if ctx.is_concert then lcds[#lcds + 1] = { L.tr("concert_k"), L.fmt_time(math.min(S.t, S.total)), U.LCD } end
    local tc = smpte_now(S.t)
    if tc then lcds[#lcds + 1] = { "SMPTE", tc, U.SMPTE } end
    local VS = 20
    local lw = {}
    local tot = 0
    for k, l in ipairs(lcds) do lw[k] = U.text_w(l[2], VS, false, "mono") + 22; tot = tot + lw[k] end
    local wide = w >= 600 and w - tot - 24 >= 300
    local hb = wide and 106 or 136
    U.panel(x, y, w, hb, U.INSET)
    U.set(scol); gfx.rect(x, y, w, 3, 1)                              -- couleur du morceau
    -- état
    local st = S.st
    local scol2 = STATE_COL[st]
    local slab = U.upper(L.tr("state")[st])
    U.set(scol2); gfx.circle(x + 18, y + 24, 6, 1, 1)
    U.text(slab, x + 30, y + 15, 17, scol2, true, "cond")
    -- rang + titre
    local tx = x + 14
    local ty = y + 38
    -- « MORCEAU 2 / 3 » en un seul texte (l'espace ne dépend plus de la mesure de la police)
    local rank = ctx.is_concert and (U.upper(L.tr("song_k")) .. " " .. string.format("%d / %d", S.i, #c.songs))
                 or U.upper(t("song_only"))
    local stw = U.text_w(slab, 17, true, "cond")
    U.text(rank, x + 30 + stw + 16, y + 19, 10, U.MUTED)
    local avail = (wide and (w - tot - 30) or (w - 24))
    local title_size = wide and 38 or 30
    U.text(U.fit(U.upper(s.title or ""), avail, title_size, true, "cond"), tx, ty, title_size, U.INK, true, "cond")
    -- afficheurs
    local lx, ly, lh
    if wide then
      lx, ly, lh = x + w - tot - 12, y + 14, 64
    else
      lx, ly, lh = x + 12, y + 78, 50
      local per = math.floor((w - 24) / #lcds)
      for k = 1, #lcds do lw[k] = per end
      lw[#lcds] = w - 24 - per * (#lcds - 1)
    end
    for k, l in ipairs(lcds) do
      U.lcd(l[1], l[2], lx, ly, lw[k], lh, l[3], VS)
      lx = lx + lw[k]
    end
    return y + hb
  end

  local function draw_main(x, y0, w)
    local c = ctx.c
    local S = song_state(c)
    local s = S.s
    local y = y0
    local scol = s.color and { s.color[1], s.color[2], s.color[3] } or U.ACCENT
    y = draw_banner(c, S, x, y, w)
    U.text(U.fit(info_line(S), w - 8, 13), x + 2, y + 8, 13, U.INK2)

    y = y + 30
    U.set(U.INSET); gfx.rect(x, y, w, 6, 1)
    local frac = S.dur > 0 and math.min(1, S.el / S.dur) or 0
    U.set(scol); gfx.rect(x, y, math.floor(w * frac), 6, 1)
    U.text(string.format("%s / %s · ", L.fmt_time(S.el), L.fmt_time(S.dur)) .. string.format(L.tr("rest"), L.fmt_time(S.rest)), x, y + 11, 11, U.MUTED, false, "mono")
    if ctx.is_concert then
      local ct = string.format(L.tr("concert_n"), L.fmt_time(math.min(S.t, S.total)), L.fmt_time(S.total))
      U.text(ct, x + w - U.text_w(ct, 11, false, "mono"), y + 11, 11, U.MUTED, false, "mono")
    end

    -- transport
    y = y + 36
    local gap = 8
    local bh = 56
    local AG = T("again")
    if ctx.is_concert then
      local bw = (w - 4 * gap) / 5
      if U.tbutton("prev", "prev", L.tr("prev"), x, y, bw, bh, U.armed_style("prev"), AG) then do_prev(c) end
      if U.tbutton("home", "home", L.tr("home"), x + (bw + gap), y, bw, bh, nil, AG) then L.song_home(c) end
      if U.tbutton("play", S.st == "play" and "pause" or "play", S.st == "play" and L.tr("pause") or L.tr("play"),
          x + 2 * (bw + gap), y, bw, bh, "primary", AG) then L.toggle_play() end
      if U.tbutton("stop", "stop", L.tr("stop"), x + 3 * (bw + gap), y, bw, bh, U.armed_style("stop"), AG) then do_stop() end
      if U.tbutton("next", "next", L.tr("next"), x + 4 * (bw + gap), y, bw, bh, U.armed_style("next"), AG) then do_next(c) end
    else
      local bw = (w - 2 * gap) / 3
      if U.tbutton("home", "home", L.tr("home"), x, y, bw, bh, nil, AG) then L.song_home(c) end
      if U.tbutton("play", S.st == "play" and "pause" or "play", S.st == "play" and L.tr("pause") or L.tr("play"),
          x + (bw + gap), y, bw, bh, "primary", AG) then L.toggle_play() end
      if U.tbutton("stop", "stop", L.tr("stop"), x + 2 * (bw + gap), y, bw, bh, U.armed_style("stop"), AG) then do_stop() end
    end

    -- répétition : bandeau, boucle, vitesse
    y = y + bh + 12
    local RH = L.reh
    if RH.on then
      local lp = RH.loop
      U.set(U.WARN, 0.2); gfx.rect(x, y, w, 26, 1)
      U.set(U.WARN); gfx.rect(x, y, 5, 26, 1)
      local msg = lp and (lp.a == lp.b and string.format(L.tr("reh_loop"), lp.a) or string.format(L.tr("reh_loop_range"), lp.a, lp.b))
        or L.tr("reh_noloop")
      U.text(U.fit(L.tr("reh_on") .. "  ·  " .. msg, w - 30, 13, true), x + 12, y + 6, 13, U.INK, true)
      y = y + 32
      local bx = x
      local lw = U.text_w(L.tr("loop_off"), 13) + 22
      if U.button("loopoff", L.tr("loop_off"), bx, y, lw, 26) and can_edit() then L.loop_off() end
      bx = bx + lw + 10
      for _, r in ipairs({ 1.0, 0.9, 0.8, 0.7 }) do
        local lab = string.format(L.tr("rate"), math.floor(r * 100 + 0.5))
        if U.button("rate" .. r, lab, bx, y, 54, 26, math.abs(RH.rate - r) < 0.001 and "primary" or nil) then M.set_rate(r) end
        bx = bx + 58
      end
      local qw = U.text_w(L.tr("reh_exit"), 13) + 20
      if U.button("rehexit", L.tr("reh_exit"), x + w - qw, y, qw, 26) then M.set_rehearsal(false) end
      y = y + 36
    end

    -- sections (clic = y aller ; en répétition : boucle) : blocs à bord supérieur coloré
    U.heading(L.tr("sections"), x, y)
    y = y + 18
    local sx = x
    local ph = 28
    for k, sec in ipairs(S.secs) do
      local lab = sec.name
      local cur = k == S.si
      local pw2 = U.text_w(lab, 12, cur) + 18
      if sx + pw2 > x + w and sx > x then sx = x; y = y + ph + 4 end
      local col = sec.color or U.SLATE
      local over = U.over(sx, y, pw2, ph)
      local done = S.si and k < S.si
      U.set(cur and U.NOW or (done and U.DONE or U.ROW)); gfx.rect(sx, y, pw2, ph, 1)
      if over then U.set(U.INK, 0.07); gfx.rect(sx, y, pw2, ph, 1) end
      U.set(col); gfx.rect(sx, y, pw2, 3, 1)
      if cur then U.frame(sx, y, pw2, ph, U.SIG) end
      local lp = RH.loop
      if lp and sec.start >= lp.start - 0.01 and sec.stop <= lp.stop + 0.01 then
        U.set(U.WARN); gfx.rect(sx, y + ph - 3, pw2, 3, 1)
      end
      U.text(lab, sx + 9, y + 9, 12, cur and U.INK or (done and U.MUTED or U.INK2), cur)
      if over then U.hover = "sec" .. k end
      if over and U.clicked then
        if RH.on then if can_edit() then L.loop_tap(c, sec.start); ctx.reset_loop() end else L.seek(c, sec.start) end
      end
      sx = sx + pw2 + 4
    end
    if #S.secs == 0 then U.text(L.tr("no_regions"), x, y + 4, 12, U.MUTED) end
    y = y + ph + 12

    -- instruments
    y = draw_instruments(c, S, x, y, w)

    -- ensuite + outils
    if ctx.is_concert then
      local nx = c.songs[S.i + 1]
      local nxt = nx and string.format(L.tr("next_song"), S.i + 1, nx.title, fmt_bpm(nx.bpm), L.fmt_time(nx.stop - nx.start))
        or L.tr("last_song")
      U.text(U.fit(nxt, w, 13), x, y, 13, U.INK)
    else
      U.text(U.fit(t("song_hint"), w, 12), x, y, 12, U.MUTED)
    end
    y = y + 22
    local lab
    if ctx.job then lab = string.format(T("running"), ctx.job.label or "", math.floor(reaper.time_precise() - ctx.job.t0))
    elseif not ctx.is_concert then lab = t("song_only")
    else lab = RH.on and L.tr("auto_off") or L.tr("auto_stop") end
    U.set((ctx.job or RH.on or not ctx.is_concert) and U.WARN or U.ACCENT); gfx.circle(x + 6, y + 7, 4, 1, 1)
    U.text(lab, x + 16, y, 12, U.MUTED)
    if ctx.flash and reaper.time_precise() - ctx.flash.t < 2.5 then
      U.text(ctx.flash.txt, x + 16 + U.text_w(lab, 12) + 14, y, 12, ctx.flash.bad and U.WARN or U.ACCENT, true)
    end
    y = y + 20
    local tb = 26
    local bx = x + w
    bx = bx - 50; if U.button("qr", "QR", bx, y, 50, tb) then ctx.open_qr() return y end
    local pinlab = string.format(L.tr("pin_btn"), L.remote_pin())
    local pinw = U.text_w(pinlab, 13) + 18
    bx = bx - 6 - pinw; if U.button("pin", pinlab, bx, y, pinw, tb) then ctx.change_pin() end
    if ctx.is_concert then
      local slab = L.tr("setlist") .. (songs_open and "  −" or "  +")
      local sw = U.text_w(slab, 13) + 20
      bx = bx - 6 - sw
      if U.button("list", slab, bx, y, sw, tb) then
        songs_open = not songs_open
        reaper.SetExtState("ReaCue", "concert_list", songs_open and "1" or "0", true)
      end
    end
    local rw = U.text_w(L.tr("reh"), 13) + 20
    bx = bx - 6 - rw
    if U.button("reh", L.tr("reh"), bx, y, rw, tb, RH.on and "on" or nil) then M.set_rehearsal(not RH.on) end
    local cw = U.text_w(L.tr("check"), 13) + 20
    bx = bx - 6 - cw
    if U.button("check", L.tr("check"), bx, y, cw, tb) then ctx.open_check() return y end
    y = y + tb + 10

    -- setlist : blocs à bord supérieur coloré (joué / en cours / à venir), clic = aller au morceau
    if ctx.is_concert and songs_open then
      local n = #c.songs
      local gap, bh = 3, 46
      local per = math.max(1, math.min(n, math.floor((w + gap) / (120 + gap))))
      local bw = math.floor((w - (per - 1) * gap) / per)
      local rows = math.ceil(n / per)
      U.panel(x - 4, y - 4, w + 8, rows * (bh + gap) - gap + 8, U.INSET)
      for k, so in ipairs(c.songs) do
        local col, row = (k - 1) % per, math.floor((k - 1) / per)
        local bx, by = x + col * (bw + gap), y + row * (bh + gap)
        local ww = (col == per - 1 or k == n) and (x + w - bx) or bw
        if k == n and col < per - 1 then ww = bw end
        local over = U.over(bx, by, ww, bh)
        local now, done = k == S.i, k < S.i
        U.set(now and U.NOW or (done and U.DONE or U.ROW)); gfx.rect(bx, by, ww, bh, 1)
        if over then U.set(U.INK, 0.07); gfx.rect(bx, by, ww, bh, 1) end
        local top = now and U.SIG or (done and U.PANEL or (so.color and { so.color[1], so.color[2], so.color[3] } or U.SLATE))
        U.set(top); gfx.rect(bx, by, ww, 3, 1)
        U.text(U.fit(U.upper(so.title), ww - 16, 14, true, "cond"), bx + 8, by + 8, 14, done and U.GREY or U.INK, true, "cond")
        local meta = string.format("%d · %.0f BPM · %s", k, so.bpm, L.fmt_time(so.stop - so.start))
        if U.is_armed("song" .. k) then U.text(T("again"), bx + 8, by + 28, 11, U.WARN, true)
        else U.text(U.fit(meta, ww - 16, 10, false, "mono"), bx + 8, by + 29, 10, U.MUTED, false, "mono") end
        if over then U.hover = "song" .. k end
        if over and U.clicked and U.confirm("song" .. k, playing()) then L.goto_song(c, k) end
      end
      local yb = y + rows * (bh + gap) + 8
      if U.button("rebuild", L.tr("rebuild"), x + w - 200, yb, 200, 24) and not ctx.job then M.rebuild(false) end
      y = yb + 34
    end
    return y
  end

  -- sans projet : raccourcis et concerts existants -----------------------------------------------
  local function draw_empty(x, y, w)
    U.text(t("no_project"), x, y, 18, U.INK, true)
    y = y + 34
    local b1 = U.text_w(t("go_concert"), 13) + 24
    if U.button("goconcert", t("go_concert"), x, y, b1, 28, "primary") then ctx.goto_tab("concert") return y end
    local cw = U.text_w(L.tr("check"), 13) + 20
    if U.button("check", L.tr("check"), x + w - 56 - 8 - cw, y, cw, 28) then ctx.open_check() return y end
    if U.button("qr", "QR", x + w - 56, y, 56, 28) then ctx.open_qr() return y end
    y = y + 40
    if not available then available = L.list_concerts() end
    if #available > 0 then
      U.heading(t("open_concert"), x, y)
      y = y + 20
      for k, d in ipairs(available) do
        if U.button("open" .. k, string.format(L.tr("n_songs"), d.name, #d.songs), x, y, w, ROW - 4) then
          if can_edit() then L.open_concert(d); ctx.refresh(true) end
        end
        y = y + ROW
      end
    end
    return y + 6
  end

  -- fenêtre ancrée basse ---------------------------------------------------------------------
  function M.compact()
    local c = ctx.c
    local S = song_state(c)
    local h = gfx.h
    U.set(S.s.color and { S.s.color[1], S.s.color[2], S.s.color[3] } or U.ACCENT)
    gfx.rect(0, 0, 6, h, 1)
    local bh = math.min(34, h - 8)
    local bw, gap = 44, 6
    local nb = ctx.is_concert and 5 or 3
    local bx = gfx.w - nb * (bw + gap) - 50 - 12
    local by = (h - bh) / 2
    local AG = T("again")
    local k = 0
    local function nextx() local v = bx + k * (bw + gap); k = k + 1; return v end
    if ctx.is_concert and U.tbutton("prev", "prev", "", nextx(), by, bw, bh, U.armed_style("prev"), AG) then do_prev(c) end
    if U.tbutton("home", "home", "", nextx(), by, bw, bh, nil, AG) then L.song_home(c) end
    if U.tbutton("play", S.st == "play" and "pause" or "play", "", nextx(), by, bw, bh, "primary", AG) then L.toggle_play() end
    if U.tbutton("stop", "stop", "", nextx(), by, bw, bh, U.armed_style("stop"), AG) then do_stop() end
    if ctx.is_concert and U.tbutton("next", "next", "", nextx(), by, bw, bh, U.armed_style("next"), AG) then do_next(c) end
    if U.button("qr", "QR", bx + nb * (bw + gap), by, 50, bh) then ctx.open_qr() end
    local locked = ctx.is_locked and ctx.is_locked()
    local lock_fits = ctx.set_locked and bx > 200
    if lock_fits and U.button("stage_lock_compact", locked and t("unlock") or t("lock"), bx-110, by, 104, bh, locked and "on" or nil, 11) then M.toggle_lock() end
    local left_w = bx - (lock_fits and 136 or 26)
    U.set(STATE_COL[S.st]); gfx.circle(20, h / 2 - (h >= 58 and 8 or 0), 5, 1, 1)
    local head = ctx.is_concert and string.format("%d / %d · %s", S.i, #c.songs, S.s.title) or S.s.title
    U.text(U.fit(head, left_w - 16, 17, true), 32, h / 2 - (h >= 58 and 17 or 9), 17, U.INK, true)
    if h >= 58 then
      local sub = (S.si and S.secs[S.si].name or L.tr("state")[S.st]) .. " · " .. string.format(L.tr("rest"), L.fmt_time(S.rest))
      if L.reh.on then sub = L.tr("reh_on") .. " · " .. sub end
      U.text(U.fit(sub, left_w - 16, 12), 32, h / 2 + 6, 12, U.MUTED)
    end
  end

  function M.enter() available = nil end

  function M.draw(x, y, w)
    if ctx.set_locked then
      local locked = ctx.is_locked and ctx.is_locked()
      local lab = locked and t("unlock") or t("lock")
      local bw = math.min(w, U.text_w(lab, 12) + 26)
      if U.button("stage_lock", lab, x, y, bw, 28, locked and "on" or nil, 12) then M.toggle_lock() end
      if ctx.jobs then
        local jw = math.min(w-bw-6, U.text_w(t("jobs"), 12) + 26)
        if U.button("stage_jobs", t("jobs"), x+w-jw, y, jw, 28, nil, 12) then ctx.overlay = "jobs" end
      end
      y = y+36
      if locked then
        y = y+U.para(t("locked"), x, y, w, 11, U.ACCENT)+8
      end
    end
    if ctx.job and not ctx.c then y = y + ctx.draw_job(x, y, w) end
    if not ctx.c then return draw_empty(x, y, w) end
    if ctx.job then y = y + ctx.draw_job(x, y, w) end
    return draw_main(x, y, w)
  end

  return M
end
