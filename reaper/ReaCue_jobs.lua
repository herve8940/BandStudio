-- Durable background activity, including jobs started before this window opened.
return function(ctx)
  local R, U = ctx.R, ctx.U
  local J = { rows = {}, scanned = -1e9 }
  local function text(fr, en) return ctx.lang() == "fr" and fr or en end
  local function record(path)
    local d = R.json_decode(R.read(path))
    if type(d) ~= "table" or type(d.cmd) ~= "string" then return nil end
    if d.state == "running" and not R.job_active(d) then d.state = "interrupted" end
    return d
  end
  function J.scan(force)
    local now = reaper.time_precise()
    if not force and now - J.scanned < 2 then return J.rows end
    J.scanned = now
    local rows, seen, i = {}, {}, 0
    local dir = R.DIR .. ctx.SEP .. "jobs"
    while reaper.EnumerateFiles do
      local name = reaper.EnumerateFiles(dir, i)
      if not name then break end
      if name:match("^[%w_-]+%.json$") then
        local d = record(dir .. ctx.SEP .. name)
        if d then rows[#rows+1] = d; seen[d.id or name] = true end
      end
      i = i + 1
    end
    local d = record(R.STATUS)
    if d and not seen[d.id or ""] then rows[#rows+1] = d end
    if ctx.job and ctx.job.kind == "stems" and not seen[ctx.job.id or ""] then
      local s = ctx.job.sj
      local data = R.json_decode(R.read(s.p.status)) or {}
      rows[#rows+1] = {cmd="stems", state="running", step=ctx.job.label, time=data.time,
        project=ctx.proj_file, started=data.started or data.time, id="stems", pid=data.pid}
    end
    table.sort(rows, function(a,b) return (a.time or 0) > (b.time or 0) end)
    J.rows = rows
    return rows
  end
  function J.busy()
    for _, d in ipairs(J.scan(true)) do if d.state == "running" then return true end end
    return false
  end
  function J.cancel(d)
    if not d or not d.cancellable or not d.id or not tostring(d.id):match("^[%w_-]+$") then return false end
    local path = R.DIR .. ctx.SEP .. "jobs" .. ctx.SEP .. d.id .. ".cancel"
    return R.write_atomic(path, "cancel\n")
  end
  local commands={prepare={"Préparation du morceau","Song preparation"},prepare_song={"Préparation du morceau","Song preparation"},
    publish={"Publication du prompteur","Prompter publication"},stems={"Séparation des stems","Stem separation"},
    concert={"Construction du concert","Concert build"},build_concert={"Construction du concert","Concert build"},
    ["concert-extras"]={"Compléments du concert","Concert details"},["concert-manage"]={"Gestion du concert","Concert management"},
    ["import-audio"]={"Import depuis un lien","Import from a link"},export={"Export audio","Audio export"},
    timecode={"Pistes timecode","Timecode tracks"},["concert-lighting"]={"Lumière du concert","Concert lighting"}}
  local labels = {running={"En cours","Running"},done={"Terminé","Done"},error={"Échec","Failed"},
    cancelled={"Annulé","Cancelled"},interrupted={"Interrompu","Interrupted"}}
  function J.draw(x,y,w)
    U.heading(text("TRAITEMENTS", "TASKS"),x,y)
    if U.button("jobsclose", text("Fermer","Close"),x+w-90,y-4,90,28) then ctx.overlay=nil end
    y=y+32
    if ctx.job then y=y+ctx.draw_job(x,y,w) end
    local rows=J.scan()
    if #rows==0 then U.text(text("Aucun traitement enregistré.","No recorded tasks."),x,y,13,U.MUTED); return y+28 end
    for i,d in ipairs(rows) do
      if i>30 then break end
      local lab=labels[d.state] or {d.state or "?",d.state or "?"}
      local command=commands[d.cmd]
      local title=(command and text(command[1],command[2]) or d.cmd:gsub("_"," ")) .. " · " .. text(lab[1],lab[2])
      U.panel(x,y,w,78,U.INSET)
      U.text(U.fit(title,w-140,14,true),x+10,y+8,14,d.state=="error" and U.RED or U.INK,true)
      local detail=d.step or d.message or ""
      if d.state=="error" or d.state=="interrupted" then detail=d.step or text("Le traitement s’est arrêté.","The task stopped.") end
      U.text(U.fit(detail,w-20,12),x+10,y+32,12,U.MUTED)
      U.text(U.fit(d.project or "",w-20,11),x+10,y+55,11,U.MUTED)
      if d.state=="running" and d.cancellable then
        if U.button("canceljob_"..i,text("Annuler","Cancel"),x+w-100,y+5,90,26,"warn") then J.cancel(d) end
      elseif d.state=="done" and d.import_audio and d.import_audio.operation=="download" then
        if U.button("importresume_"..i,text("Ouvrir","Open"),x+w-100,y+5,90,26) and ctx.require_edit() then
          ctx.audio_import=ctx.audio_import or dofile(ctx.dir.."ReaCue_import.lua")(ctx)
          ctx.audio_import.resume(d.import_audio)
        end
      end
      if d.state=="error" or d.state=="interrupted" then
        local h=U.para(d.message or text("Le processus est arrêté. Reprends le morceau avec Tout faire.",
          "The process stopped. Resume the song using Do everything."),x+10,y+80,w-20,12,U.WARN,5)
        y=y+h+8
      end
      y=y+86
    end
    return y
  end
  return J
end
