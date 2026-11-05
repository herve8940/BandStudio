-- Retrait de pistes du projet uniquement : aucun fichier audio n'est effacé.
return function(ctx)
  local L, U = ctx.L, ctx.U
  local M = { selected = {}, protect = true, page = 1 }
  local function tr(fr, en) return L.lang() == "fr" and fr or en end
  local GENERATED = { CLICK = true, CUES = true, VOIX = true, VOICE = true, ["TIMECODE LTC"] = true, ["TIMECODE MTC"] = true }
  local function protected(name)
    local upper = (name or ""):gsub("[a-z]", function(c) return string.char(c:byte()-32) end)
    upper = upper:gsub("^[ \t]+", ""):gsub("[ \t]+$", ""):gsub("[ \t]+%d+$", "")
    return GENERATED[upper] or upper:match("^TIMECODE ") ~= nil
  end
  local function project() local p, f = reaper.EnumProjects(-1, ""); return p, f or "" end
  local function guard()
    if ctx.require_edit and not ctx.require_edit() then return false end
    if ctx.is_locked and ctx.is_locked() then return false end
    if ctx.job or (ctx.flow and ctx.flow.run and not ctx.flow.run.finished) or
      (ctx.flow and ctx.flow.batch_active and ctx.flow.batch_active()) or
      (ctx.jobs and ctx.jobs.busy and ctx.jobs.busy()) or (ctx.R.active_job and ctx.R.active_job()) or
      (reaper.GetPlayState and reaper.GetPlayState() ~= 0) then
      return false, tr("Arrête la lecture et attends la fin de la préparation.", "Stop playback and wait for preparation to finish.")
    end
    return true
  end
  function M.scan()
    local p, file = project()
    M.project, M.file, M.rows = p, file, {}
    M.selected, M.page = {}, 1
    for i = 0, reaper.CountTracks(p) - 1 do
      local ptr = reaper.GetTrack(p, i)
      local _, name = reaper.GetTrackName(ptr)
      local role = L.role_of_track and L.role_of_track(name) or nil
      M.rows[#M.rows+1] = { ptr = ptr, name = name or "", index = i + 1,
        guid = reaper.GetTrackGUID and reaper.GetTrackGUID(ptr), generated = protected(name), role = role }
    end
    return M.rows
  end
  function M.open() M.visible = true; M.protect = true; M.message = nil; M.scan() end
  function M.close() M.visible = false; M.selected = {} end
  function M.toggle(index)
    local row = M.rows and M.rows[index]
    if row and not (M.protect and row.generated) then M.selected[index] = not M.selected[index] end
  end
  function M.set_protect(on)
    M.protect = on
    if on then for i, row in ipairs(M.rows or {}) do if row.generated then M.selected[i] = nil end end end
  end
  local function chosen()
    local out = {}
    for i, row in ipairs(M.rows or {}) do if M.selected[i] then out[#out+1] = row end end
    return out
  end
  local function validate(rows)
    local p, file = project()
    if p ~= M.project or file ~= M.file then return false, tr("Le projet a changé. Actualise la liste.", "The project changed. Refresh the list.") end
    for _, row in ipairs(rows) do
      local found = false
      for i = 0, reaper.CountTracks(p)-1 do if reaper.GetTrack(p, i) == row.ptr then found = true break end end
      if not found then return false, tr("Une piste a été retirée. Actualise la liste.", "A track was removed. Refresh the list.") end
      if (reaper.ValidatePtr2 and not reaper.ValidatePtr2(p, row.ptr, "MediaTrack*")) or
        (reaper.GetTrackGUID and reaper.GetTrackGUID(row.ptr) ~= row.guid) then
        return false, tr("Une piste a changé. Actualise la liste.", "A track changed. Refresh the list.")
      end
      local _, name = reaper.GetTrackName(row.ptr)
      if name ~= row.name then return false, tr("Une piste a été renommée. Actualise la liste.", "A track was renamed. Refresh the list.") end
      if M.protect and protected(name) then return false, tr("Click, voix et timecode sont protégés.", "Click, cues and timecode are protected.") end
    end
    return true
  end
  function M.remove()
    local ok, err = guard(); if not ok then return false, err end
    local rows = chosen()
    if #rows == 0 then return false, tr("Sélectionne au moins une piste.", "Select at least one track.") end
    ok, err = validate(rows); if not ok then return false, err end
    local names, generated = {}, false
    for _, row in ipairs(rows) do names[#names+1] = tostring(row.index) .. ". " .. row.name; generated = generated or row.generated end
    local question = tr("Retirer ces pistes du projet ?\nLes fichiers audio restent sur le disque. Annulable avec Annuler dans REAPER.",
      "Remove these tracks from the project?\nAudio files stay on disk. Undo is available in REAPER.")
    if generated then question = question .. "\n\n" .. tr("ATTENTION : le click, les annonces ou le timecode sélectionnés ne seront plus joués.",
      "WARNING: selected click, cues or timecode will no longer play.") end
    if reaper.ShowMessageBox(question .. "\n\n" .. table.concat(names, "\n"), "ReaCue", 1) ~= 1 then return false end
    ok, err = guard(); if not ok then return false, err end
    ok, err = validate(rows); if not ok then return false, err end -- revalider après la confirmation
    local proj = M.project
    local label = tr("ReaCue : retirer des pistes (fichiers conservés)", "ReaCue: remove tracks (files kept)")
    local begin = reaper.Undo_BeginBlock2 or function() reaper.Undo_BeginBlock() end
    local finish = reaper.Undo_EndBlock2 or function(_, text, flags) reaper.Undo_EndBlock(text, flags) end
    local before_count = reaper.CountTracks(proj)
    begin(proj)
    reaper.PreventUIRefresh(1)
    local success, failure = pcall(function()
      -- De bas en haut pour conserver les indices des pistes restantes.
      for i = #rows, 1, -1 do
        local count = reaper.CountTracks(proj)
        reaper.DeleteTrack(rows[i].ptr)
        if reaper.CountTracks(proj) ~= count - 1 then error("Track removal failed") end
      end
      if reaper.SetProjExtState then reaper.SetProjExtState(proj, "ReaCue", "publication_dirty", "1") end
    end)
    reaper.PreventUIRefresh(-1)
    finish(proj, label, -1)
    if not success then
      local modified = reaper.CountTracks(proj) ~= before_count
      if modified and reaper.Undo_DoUndo2 then reaper.Undo_DoUndo2(proj) end
      M.scan()
      local msg = not modified and tr("Aucune piste retirée. ", "No tracks removed. ") or
        (reaper.Undo_DoUndo2 and tr("Retrait interrompu ; modification annulée. ", "Removal interrupted; change undone. ") or
          tr("Retrait interrompu : utilise Annuler dans REAPER. ", "Removal interrupted: use Undo in REAPER. "))
      return false, msg .. tostring(failure)
    end
    if reaper.TrackList_AdjustWindows then reaper.TrackList_AdjustWindows(false) end
    reaper.UpdateArrange()
    local song = ctx.tabs and ctx.tabs.song
    if song and song.tracks_changed then song.tracks_changed() end
    local stage = ctx.tabs and ctx.tabs.stage
    if stage and stage.invalidate then stage.invalidate() end
    if L.mix then L.mix.song, L.mix.src, L.mix.t = nil, nil, -1e9 end
    M.scan()
    return true, tr("Pistes retirées. Fichiers conservés. Mets à jour les téléphones ; Annuler dans REAPER restaure les pistes.",
      "Tracks removed. Files kept. Update the phones; Undo in REAPER restores the tracks.")
  end
  function M.draw(x, y, w)
    U.heading(tr("Pistes du projet", "Project tracks"), x, y); y = y + 22
    y = y + U.para(tr("Sélection multiple · retrait du projet uniquement · fichiers conservés", "Multiple selection · remove from project only · files kept"),
      x, y, w, 12, U.MUTED) + 6
    local hw = (w-6)/2
    if U.button("tracks_back", tr("Retour au morceau", "Back to song"), x, y, hw, 26, nil, 12) then M.close() return y+32 end
    if U.button("tracks_refresh", tr("Actualiser", "Refresh"), x+hw+6, y, hw, 26, nil, 12) then M.scan() end
    y = y + 34
    if U.button("tracks_protect", (M.protect and "✓ " or "") .. tr("Protéger click / voix / timecode", "Protect click / cues / timecode"), x, y, w, 28,
      M.protect and "on" or nil, 12) then
      if not M.protect then M.set_protect(true)
      elseif reaper.ShowMessageBox(tr("Autoriser la sélection des pistes générées ? Retirer ces pistes peut couper le click, les annonces et la lumière.",
        "Allow selecting generated tracks? Removing them can stop click, cues and lighting."), "ReaCue", 1) == 1 then M.set_protect(false) end
    end
    y = y + 36
    local rows = M.rows or M.scan()
    local size = 8
    local pages = math.max(1, math.ceil(#rows/size)); M.page = math.min(M.page, pages)
    local labels = { vocals = tr("Voix", "Vocals"), drums = tr("Batterie", "Drums"), bass = tr("Basse", "Bass"),
      guitars = tr("Guitares", "Guitars"), keys = tr("Claviers", "Keys"), other = tr("Autres", "Other") }
    for i = (M.page-1)*size+1, math.min(M.page*size, #rows) do
      local row = rows[i]
      local label = (M.selected[i] and "✓ " or "○ ") .. row.index .. ". " .. (row.name ~= "" and row.name or tr("Sans nom", "Unnamed"))
      local role = row.generated and tr("générée", "generated") or labels[row.role]
      if role then label = label .. " · " .. role end
      if M.protect and row.generated then label = label .. " · " .. tr("protégée", "protected") end
      if U.button("track_select_" .. i, U.fit(label, w-20, 12), x, y, w, 25, M.selected[i] and "on" or nil, 12) then M.toggle(i) end
      y = y + 29
    end
    if U.button("tracks_prev", "←", x, y, 40, 26, nil, 12) then M.page = math.max(1, M.page-1) end
    U.text(tostring(M.page) .. " / " .. pages, x+50, y+5, 12, U.MUTED)
    if U.button("tracks_next", "→", x+w-40, y, 40, 26, nil, 12) then M.page = math.min(pages, M.page+1) end
    y = y + 34
    if U.button("tracks_clear", tr("Tout désélectionner", "Clear selection"), x, y, hw, 28, nil, 12) then M.selected = {} end
    local lab = tr("Retirer", "Remove") .. " (" .. #chosen() .. ")"
    if U.button("tracks_remove", lab, x+hw+6, y, hw, 28, nil, 12) then
      local ok, message = M.remove(); M.message, M.bad = message, not ok
    end
    y = y + 36
    if M.message then y = y + U.para(M.message, x, y, w, 12, M.bad and U.RED or U.ACCENT) + 8 end
    return y
  end
  return M
end
