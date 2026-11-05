-- Optional link import; the URL stays in JSON, never in a shell command.
return function(ctx)
  local R, N = ctx.R, ctx.newsong
  local I = {}
  local function text(fr, en) return ctx.L.lang() == "en" and en or fr end
  local function allowed() return not ctx.require_edit or ctx.require_edit() end
  local function show(message) ctx.show_result(ctx.T("error_title"), message, false) end
  local function result()
    local status = ctx.last_job_result or R.json_decode(R.read(R.STATUS) or "") or {}
    return status.import_audio
  end
  function I.seconds(value)
    local n = tonumber(value)
    if n then return n end
    local m, s = tostring(value):match("^(%d+):(%d+%.?%d*)$")
    if m and tonumber(s) < 60 then return tonumber(m) * 60 + tonumber(s) end
    return nil
  end
  local function run(request, callback)
    if ctx.job or not allowed() then return false end
    local dir = reaper.GetResourcePath() .. ctx.SEP .. "ReaCueMCP"
    reaper.RecursiveCreateDirectory(dir, 0)
    local id = reaper.genGuid and reaper.genGuid():gsub("[^%w]", "") or tostring(os.time()) .. tostring(math.random(100000, 999999))
    local path = dir .. ctx.SEP .. "import_request_" .. id .. ".json"
    if not R.write_atomic(path, R.json_encode(request)) then
      show(text("Impossible d'enregistrer la demande d'import.", "Could not save the import request.")); return false
    end
    local quote = R.is_windows() and R.winq or R.shq
    local ok = ctx.start_cli("import-audio --job " .. quote(path), text("Import depuis un lien", "Import from a link"),
      function(state, message)
        if state ~= "done" then show(message or "Import interrompu") return end
        os.remove(path)
        local data = result()
        if type(data) ~= "table" or data.operation ~= request.operation then
          show(text("Résultat d'import introuvable. Réessayez.", "Import result missing. Try again.")); return
        end
        callback(data)
      end, false)
    if not ok then os.remove(path) end
    return ok
  end
  function I.download(meta)
    if not allowed() then return false end
    local title = N.ask_title(N.clean_title(meta.title .. ".x"))
    if not title then return false end
    local description = text(
      "Début (s ou m:ss),Fin (s ou m:ss),Format (best sans recompression ou mp3),extrawidth=240",
      "Start (s or m:ss),End (s or m:ss),Format (best no recompression or mp3),extrawidth=240")
    local defaults = "0," .. tostring(meta.duration) .. ",best"
    for _ = 1, 6 do
      local ok, values = reaper.GetUserInputs(text("Passage à importer", "Passage to import"), 3, description, defaults)
      if not ok then return false end
      local a, b, format = tostring(values):match("^([^,]*),([^,]*),([^,]*)$")
      local first, last = I.seconds(a), I.seconds(b)
      format = (format or ""):lower():gsub("%s", "")
      if first and last and first >= 0 and last > first and last <= meta.duration and (format == "best" or format == "mp3") then
        return run({operation="download", url=meta.url, root=ctx.L.projects_dir(), title=title,
                    start=first, ["end"]=last, format=format}, function(data)
          I.resume(data)
        end)
      end
      reaper.ShowMessageBox(text("Vérifie début < fin ≤ durée et le format best ou mp3.",
                                 "Check start < end ≤ duration and format best or mp3."), "ReaCue", 0)
      defaults = values
    end
    return false
  end
  -- Reopen a finished download from the durable jobs list without downloading or duplicating audio.
  function I.resume(data)
    if ctx.job or not allowed() then return false end
    if type(data) ~= "table" or data.operation ~= "download" or not data.file or not data.folder or
        not data.title or not ctx.L.exists(data.file) then
      show(text("Le fichier téléchargé est introuvable.", "Downloaded file not found.")); return false
    end
    local rpp = data.folder .. ctx.SEP .. N.safe(data.title) .. ".RPP"
    if ctx.L.exists(rpp) then
      if reaper.EnumProjects and reaper.SelectProjectInstance then
        local i = 0
        while true do
          local project, path = reaper.EnumProjects(i, "")
          if not project then break end
          if path:gsub("\\", "/") == rpp:gsub("\\", "/") then
            reaper.SelectProjectInstance(project)
            ctx.refresh(true); ctx.goto_tab("song"); return true
          end
          i = i + 1
        end
      end
      reaper.Main_OnCommand(40859, 0)
      reaper.Main_openProject("noprompt:" .. rpp)
      ctx.refresh(true)
      ctx.goto_tab("song")
      return true
    end
    local filename = data.file:match("([^/\\]+)$")
    return N.complete(data.folder, data.title, {filename}, true)
  end
  function I.start()
    if ctx.job or not allowed() then return false end
    local ok, url = reaper.GetUserInputs(text("Nouveau morceau — lien YouTube", "New song — YouTube link"), 1,
      text("Lien d'une vidéo publique,extrawidth=260", "Public video URL,extrawidth=260"), "")
    if not ok or not url or url == "" then return false end
    return run({operation="inspect", url=url}, function(meta)
      local message = string.format(text("%s\n\nDurée : %.1f s\n\nImporte uniquement un audio que tu es autorisé à utiliser.\nChoisis ensuite le passage et le format. Sans recompression, les limites suivent les paquets audio.",
        "%s\n\nDuration: %.1f s\n\nOnly import audio you are allowed to use.\nNext, choose the passage and format. Without recompression, cuts follow audio packet boundaries."), meta.title, meta.duration)
      if reaper.ShowMessageBox(message, text("Importer ce morceau", "Import this song"), 1) == 1 then I.download(meta) end
    end)
  end
  return I
end
