-- ReaCue : « Tout faire » et préparation en lot / “Do everything” and batch preparation.
--   F.start()   : enchaîne pour le projet ouvert : séparer les stems (si un seul fichier), analyser et
--                 préparer (structure SongFormer ou ReaCue, click, annonces, prompteur), mettre à jour les
--                 téléphones, enregistrer. Liste d'étapes avec état et durée ; annulable (après l'étape en
--                 cours) ; reprise à l'étape qui a échoué (F.resume).
--   F.batch(list) : prépare l'un après l'autre des projets de morceaux : ouvre chacun dans un onglet,
--                 « Tout faire », enregistre, ferme l'onglet qu'il a ouvert ; progression globale, arrêt.
-- Les traitements tournent en arrière-plan (ctx.start_cli / ctx.start_stems), quel que soit l'onglet.
return function(ctx)
  local L, R = ctx.L, ctx.R
  local TXT = {
    fr = {
      stems = "Séparer les stems", prepare = "Analyser et préparer", publish = "Mettre à jour les téléphones",
      save = "Enregistrer le projet", skipped = "déjà fait", cancelled = "annulé",
      title = "Tout faire", done = "Morceau prêt ✓", failed = "Arrêté à l'étape « %s »", stopped = "Arrêté",
      batch_title = "Préparation en lot", batch_line = "%d / %d · %s", batch_done = "Lot terminé : %d prêts, %d en échec",
      batch_stopped = "Lot arrêté : %d prêts, %d en échec",
    },
    en = {
      stems = "Split stems", prepare = "Analyse and prepare", publish = "Update the phones",
      save = "Save the project", skipped = "already done", cancelled = "cancelled",
      title = "Do everything", done = "Song ready ✓", failed = "Stopped at step “%s”", stopped = "Stopped",
      batch_title = "Batch preparation", batch_line = "%d / %d · %s", batch_done = "Batch finished: %d ready, %d failed",
      batch_stopped = "Batch stopped: %d ready, %d failed",
    },
  }
  local function t(k) return ctx.tr(TXT, k) end
  local F = { run = nil, batch_run = nil }
  F.t = t

  -- étapes ----------------------------------------------------------------------------------------
  -- run = {key, steps = {{id, status, t0, secs, msg}}, i, cancel, finished, ok, on_finish}
  local function now() return reaper.time_precise() end

  local function checkpoint_path(project)
    if not R.DIR or not project or project == "" then return nil end
    local hash = 2166136261
    for i=1,#project do hash = ((hash ~ project:byte(i)) * 16777619) & 0xffffffff end
    return R.DIR .. (ctx.SEP or "/") .. "flow-" .. string.format("%08x",hash) .. ".json"
  end
  local function persist(run)
    local path = checkpoint_path(run.project)
    if not path or not R.write_atomic then return end
    local steps = R.json_array({})
    for _,s in ipairs(run.steps) do steps[#steps+1] = {id=s.id,status=s.status,msg=s.msg,secs=s.secs,job_id=s.job_id} end
    R.write_atomic(path,R.json_encode({project=run.project,steps=steps,i=run.i,failed=run.failed,
      finished=run.finished,ok=run.ok,time=os.time()}))
  end
  local function completed_record(step)
    if not R.DIR or not step.job_id or not tostring(step.job_id):match("^[%w_-]+$") then return nil end
    local d=R.json_decode(R.read(R.DIR .. (ctx.SEP or "/") .. "jobs" .. (ctx.SEP or "/") .. step.job_id .. ".json"))
    return d
  end
  local function reconcile_project(run)
    local song=ctx.tabs and ctx.tabs.song
    local st=song and song.state and song.state()
    if not st then return end
    -- A saved checkpoint can outlive unsaved REAPER edits after an application restart.
    if st.single_mix and run.steps[1].status~="skipped" then run.steps[1].status="pending" end
    if not st.prepared then
      run.steps[2].status="pending"; run.steps[3].status="pending"; run.steps[4].status="pending"
    end
    for i,step in ipairs(run.steps) do
      if step.status~="done" and step.status~="skipped" then run.i,run.failed=i,i; break end
    end
  end
  function F.restore()
    if F.run and F.run.finished and F.run.project~=ctx.proj_file and not ctx.job then F.run=nil end
    if F.run or F.batch_active() then return false end
    local path=checkpoint_path(ctx.proj_file)
    if not path or not R.read then return false end
    if F.checked == ctx.proj_file then return false end
    F.checked = ctx.proj_file
    local d=R.json_decode(R.read(path))
    if type(d)~="table" or d.project~=ctx.proj_file or type(d.steps)~="table" or d.ok then return false end
    if #d.steps~=4 then return false end
    for i,id in ipairs({"stems","prepare","publish","save"}) do
      if type(d.steps[i])~="table" or d.steps[i].id~=id then return false end
    end
    d.key,d.finished,d.ok,d.t0=ctx.proj_key,true,false,now()
    d.i=1
    for i,step in ipairs(d.steps) do
      local job=completed_record(step)
      if step.id~="stems" and job and job.cmd==step.id and job.project==d.project and job.state=="done" then
        step.status="done"
        if step.id=="prepare" and job.prompter_published==true and d.steps[3].status~="done" then d.steps[3].status="skipped" end
      end
      if step.status=="done" or step.status=="skipped" then d.i=i+1 else break end
    end
    reconcile_project(d)
    if d.i>#d.steps then return false end
    d.failed=d.i
    F.run=d
    return true
  end

  local function finish(run, ok)
    run.finished, run.ok = true, ok
    run.t_end = now()
    persist(run)
    if run.on_finish then run.on_finish(ok, run) end
  end

  local next_step
  local function step_done(run, s, state, msg)
    s.secs = now() - (s.t0 or now())
    s.msg = msg
    if state == "done" then
      s.status = "done"
      run.i = run.i + 1
      persist(run)
      next_step(run)
    else
      s.status = "failed"
      run.failed = run.i
      finish(run, false)
    end
  end

  next_step = function(run)
    if run.finished then return end
    if run.key ~= ctx.proj_key then
      local s=run.steps[run.i]
      if s then s.msg=ctx.lang and ctx.lang()=="fr" and "Reviens au projet de départ pour reprendre." or "Return to the original project to resume." end
      run.failed=run.i; finish(run,false); return
    end
    if run.cancel then
      for k = run.i, #run.steps do if run.steps[k].status == "pending" then run.steps[k].status = "cancelled" end end
      finish(run, false)
      return
    end
    local s = run.steps[run.i]
    if not s then finish(run, true) return end
    if s.status == "skipped" or s.status == "done" then run.i = run.i + 1 return next_step(run) end
    s.status, s.t0, s.msg = "running", now(), nil
    persist(run)
    local cb = function(state, msg) step_done(run, s, state, msg) end
    local ok = true
    if s.id == "stems" then ok = ctx.start_stems(function(state, msg)
        if state == "done" and ctx.refresh then ctx.refresh(true) end
        cb(state, msg)
      end, true)
    elseif s.id == "prepare" then ok = ctx.start_cli("prepare", R.tr("prepare"), function(state, msg)
        -- New CLI versions report publication explicitly. Older versions or a failed
        -- publication retain the existing publish/retry step.
        local st, _, cmd, _, published = R.status()
        if state == "done" and st == "done" and cmd == "prepare" and published == true then
          for _, step in ipairs(run.steps) do
            if step.id == "publish" and step.status == "pending" then step.status = "skipped" end
          end
        end
        cb(state, msg)
      end, true)
    elseif s.id == "publish" then ok = ctx.start_cli("publish", R.tr("publish"), cb, true)
    elseif s.id == "save" then
      if (ctx.proj_file or "") == "" then cb("error", "not_saved") return end
      if ctx.tabs.song.autosave(ctx.proj_key)==false then cb("error", "Impossible d’enregistrer le projet.") return end
      cb("done", nil)
      return
    end
    if not ok then cb("error", ctx.last_error or "?")
    elseif ctx.job then s.job_id=ctx.job.id; persist(run) end
  end

  -- st : état du morceau (onglet Morceau) : {single_mix, prepared, dirty}
  function F.plan(st)
    local steps = {}
    steps[#steps + 1] = { id = "stems", status = st.single_mix and "pending" or "skipped" }
    steps[#steps + 1] = { id = "prepare", status = "pending" }
    steps[#steps + 1] = { id = "publish", status = "pending" }
    steps[#steps + 1] = { id = "save", status = "pending" }
    return steps
  end

  function F.start(st, on_finish)
    if ctx.require_edit and not ctx.require_edit() then return false end
    if ctx.job then return false end
    F.run = { key = ctx.proj_key, project=ctx.proj_file, steps = F.plan(st or {}), i = 1, on_finish = on_finish, t0 = now() }
    next_step(F.run)
    return true
  end

  function F.resume()
    if ctx.require_edit and not ctx.require_edit() then return false end
    local run = F.run
    if not run or not run.finished or run.ok or ctx.job then return false end
    if run.project and run.project~=ctx.proj_file then return false end
    run.key=ctx.proj_key
    for k = run.failed or run.i, #run.steps do
      local job=completed_record(run.steps[k])
      if run.steps[k].id~="stems" and job and job.cmd==run.steps[k].id and job.project==run.project and job.state=="done" then
        run.steps[k].status="done"
        if run.steps[k].id=="prepare" and job.prompter_published==true and run.steps[3].status~="done" then run.steps[3].status="skipped" end
      end
      if run.steps[k].status ~= "done" and run.steps[k].status ~= "skipped" then run.steps[k].status = "pending" end
    end
    reconcile_project(run)
    run.i, run.finished, run.ok, run.cancel, run.failed = run.failed or run.i, false, nil, false, nil
    next_step(run)
    return true
  end

  function F.cancel()
    if F.run and not F.run.finished then F.run.cancel = true end
    if F.batch_run and not F.batch_run.finished then F.batch_run.stop = true end
  end

  function F.stop_batch() if F.batch_run and not F.batch_run.finished then F.batch_run.stop = true end end
  function F.close()
    if F.run and F.run.finished then
      local p=checkpoint_path(F.run.project); if p then os.remove(p) end
      F.run = nil
    end
  end
  function F.active() return F.run ~= nil and not F.run.finished end
  function F.label(id) return t(id) end
  function F.failed_step()
    local r = F.run
    return r and r.failed and r.steps[r.failed] or nil
  end

  -- lot -------------------------------------------------------------------------------------------
  -- list : {{path, name}} ; ouvre chaque projet dans un nouvel onglet (sauf s'il est déjà le projet ouvert)
  local function batch_next(b)
    if b.finished then return end
    if b.stop or b.i > #b.list then
      b.finished, b.t_end = true, now()
      if b.on_finish then b.on_finish(b) end
      return
    end
    local p = b.list[b.i]
    p.status, p.t0 = "running", now()
    local opened = false
    if (ctx.proj_file or ""):lower() ~= p.path:lower() then
      reaper.Main_OnCommand(40859, 0)              -- nouvel onglet de projet
      reaper.Main_openProject("noprompt:" .. p.path)
      opened = true
    end
    ctx.refresh(true)
    local st = ctx.tabs.song.state()
    local ok = F.start(st, function(okk, run)
      p.status = okk and "done" or "failed"
      p.secs = now() - p.t0
      if not okk then
        local fs = run.failed and run.steps[run.failed]
        p.msg = fs and (t(fs.id) .. ctx.colon() .. tostring(fs.msg or "")) or t("stopped")
        b.n_fail = b.n_fail + 1
      else
        b.n_ok = b.n_ok + 1
      end
      F.run = nil
      if opened then reaper.Main_OnCommand(40860, 0) end     -- fermer l'onglet ouvert par le lot
      ctx.refresh(true)
      b.i = b.i + 1
      b.wait = now() + 0.3                         -- laisse REAPER fermer l'onglet
    end)
    if not ok then
      p.status, p.msg = "failed", ctx.last_error or "?"
      b.n_fail = b.n_fail + 1
      if opened then reaper.Main_OnCommand(40860, 0) end
      b.i = b.i + 1
      b.wait = now() + 0.3
    end
  end

  function F.batch(list, on_finish)
    if ctx.require_edit and not ctx.require_edit() then return false end
    if ctx.job or #list == 0 then return false end
    F.batch_run = { list = list, i = 1, n_ok = 0, n_fail = 0, t0 = now(), on_finish = on_finish }
    for _, p in ipairs(list) do p.status = "pending" end
    batch_next(F.batch_run)
    return true
  end

  -- appelé à chaque image (ReaCue.lua) : enchaîne le morceau suivant du lot
  function F.tick()
    local b = F.batch_run
    if b and not b.finished and b.wait and now() >= b.wait and not ctx.job then
      b.wait = nil
      batch_next(b)
    end
  end

  function F.batch_active() return F.batch_run ~= nil and not F.batch_run.finished end

  return F
end
