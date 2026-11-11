-- ReaCue Desktop: separate mailbox, project-bound commands and no startup mutation.
-- Run once through Actions > Load ReaScript > Run. Keep the original MCP bridge.
local dir = debug.getinfo(1, "S").source:match("^@?(.*[/\\])") or ""
local R = dofile(dir .. "ReaCue_run.lua")
local D = reaper.GetResourcePath() .. "/ReaCueDesktop"
reaper.RecursiveCreateDirectory(D, 0)
if reaper.set_action_options then reaper.set_action_options(1 | 2 | 4) end
local H = {}
local generated = {CLICK=true,CUES=true,VOICE=true,VOIX=true,["TIMECODE LTC"]=true,["TIMECODE MTC"]=true}
local preview, previous_project
local previews = {}
local function read(path) local f=io.open(path,"rb"); if not f then return nil end; local s=f:read("a"); f:close(); return s end
local function current() local p,path=reaper.EnumProjects(-1,""); return p,path or "",tostring(p).."|"..(path or "") end
local function name(tr) return select(2,reaper.GetSetMediaTrackInfo_String(tr,"P_NAME","",false)) or "" end
local function number(v,a,b)
  v=tonumber(v); assert(v and v==v and v>=a and v<=b,"Valeur hors limites"); return v
end
local function editable()
  assert(not R.show_locked(),R.lock_message())
  assert(not R.active_job(),"Un traitement ReaCue est en cours. Attends sa fin.")
  assert((reaper.GetPlayState() & 4)==0,"Arrête l’enregistrement avant cette modification.")
end
local function desktop_rehearsal()
  editable()
  local alive=tonumber(reaper.GetExtState("ReaCue","win_alive")) or -100
  if reaper.time_precise()-alive<2 then
    assert(not reaper.GetExtState("ReaCue","rehearsal"):match("^1|"),"Désactive le mode Répétition des outils complets avant d’utiliser la boucle Desktop.")
  end
end
local function stopped()
  editable(); assert(reaper.GetPlayState()==0,"Arrête la lecture avant cette modification.")
end
local function track(guid)
  assert(type(guid)=="string","Piste manquante")
  for i=0,reaper.CountTracks(0)-1 do local tr=reaper.GetTrack(0,i); if reaper.GetTrackGUID(tr)==guid then return tr end end
  error("Cette piste n’existe plus. Actualise le projet.")
end
local function measure(t)
  local beats, bars, _, _, den = reaper.TimeMap2_timeToBeats(0,t)
  return (bars or 0)+1,math.floor(beats or 0)+1,den or 4
end
local function time_of_bar(bar) return reaper.TimeMap2_beatsToTime(0,0,number(bar,1,100000)-1) end
local function regions()
  local out=R.json_array()
  local _,nm,nr=reaper.CountProjectMarkers(0)
  for i=0,nm+nr-1 do
    local ok,isr,a,b,n,id,c=reaper.EnumProjectMarkers3(0,i)
    if ok and isr then
      local first=measure(a); local final=measure(math.max(a,b-0.00001))
      out[#out+1]={id=id,name=n,start=a,finish=b,first=first,last=final,color=c}
    end
  end
  table.sort(out,function(a,b)return a.start<b.start end)
  return out
end
local function region(id)
  for _,r in ipairs(regions()) do if r.id==id then return r end end
  error("Section introuvable.")
end
local function undo(label,fn)
  reaper.Undo_BeginBlock(); local ok,result=pcall(fn); reaper.Undo_EndBlock("ReaCue Desktop : "..label,-1)
  reaper.UpdateArrange(); if not ok then error(result) end; return result or {ok=true}
end

function H.state()
  local p,path,key=current()
  if previous_project~=key then
    if previous_project then previews[previous_project]=preview end
    preview=previews[key]; previous_project=key
  end
  local ps=reaper.GetPlayState()
  local pos=(ps & 1)==1 and reaper.GetPlayPosition() or reaper.GetCursorPosition()
  local bar,beat,den=measure(pos)
  local tracks,takes,inputs=R.json_array(),R.json_array(),R.json_array()
  for i=0,reaper.CountTracks(0)-1 do
    local tr=reaper.GetTrack(0,i); local nm=name(tr); local guid=reaper.GetTrackGUID(tr)
    local rec=reaper.GetMediaTrackInfo_Value(tr,"I_RECARM")==1
    local is_take=nm:match("^PRISE ")~=nil
    local input=reaper.GetMediaTrackInfo_Value(tr,"I_RECINPUT")
    tracks[#tracks+1]={id=i+1,guid=guid,name=nm,mute=reaper.GetMediaTrackInfo_Value(tr,"B_MUTE")==1,
      solo=reaper.GetMediaTrackInfo_Value(tr,"I_SOLO")>0,volume=reaper.GetMediaTrackInfo_Value(tr,"D_VOL"),
      pan=reaper.GetMediaTrackInfo_Value(tr,"D_PAN"),record=rec,input=input,record_track=is_take,
      folder=reaper.GetMediaTrackInfo_Value(tr,"I_FOLDERDEPTH")>0,
      generated=generated[nm] or false,color=reaper.GetTrackColor(tr),
      peak=reaper.Track_GetPeakInfo and math.max(reaper.Track_GetPeakInfo(tr,0),reaper.Track_GetPeakInfo(tr,1)) or 0}
    if is_take or rec then
      for j=0,math.min(reaper.CountTrackMediaItems(tr)-1,199) do
        local item=reaper.GetTrackMediaItem(tr,j)
        for k=0,reaper.CountTakes(item)-1 do
          local tk=reaper.GetTake(item,k)
          if tk and not reaper.TakeIsMIDI(tk) then
            local src=reaper.GetMediaItemTake_Source(tk)
            takes[#takes+1]={name=reaper.GetTakeName(tk),track=nm,track_guid=guid,
              guid=reaper.GetSetMediaItemTakeInfo_String and select(2,reaper.GetSetMediaItemTakeInfo_String(tk,"GUID","",false)) or "",
              start=reaper.GetMediaItemInfo_Value(item,"D_POSITION"),duration=reaper.GetMediaItemInfo_Value(item,"D_LENGTH"),
              file=reaper.GetMediaSourceFileName(src,""),active=reaper.GetActiveTake(item)==tk}
          end
        end
      end
    end
  end
  for i=0,math.min((reaper.GetNumAudioInputs() or 0)-1,255) do inputs[#inputs+1]={id=i,name=reaper.GetInputChannelName(i)} end
  local a,b=reaper.GetSet_LoopTimeRange2(0,false,true,0,0,false)
  local numerator,_,bpm=reaper.TimeMap_GetTimeSigAtTime(0,pos)
  return {version="1.0.0",project=path,project_id=key,title=path:match("([^/\\]+)%.[Rr][Pp][Pp]$") or "Projet sans nom",
    dirty=reaper.IsProjectDirty(0)==1,playing=(ps & 1)==1,recording=(ps & 4)==4,paused=(ps & 2)==2,
    position=pos,measure=bar,beat=beat,numerator=numerator,denominator=den,bpm=bpm,rate=reaper.Master_GetPlayRate(0),
    length=reaper.GetProjectLength(0),repeat_on=reaper.GetSetRepeat(-1)==1,loop_start=a,loop_end=b,
    tracks=tracks,regions=regions(),takes=takes,inputs=inputs,locked=R.show_locked(),
    native_alive=tonumber(reaper.GetExtState("ReaCue","win_alive")) or 0,
    native_desktop=reaper.GetExtState("ReaCue","desktop_ready"),listen_mode=preview and preview.mode or "original"}
end

function H.transport(a)
  if a.action=="stop" then reaper.OnStopButton()
  elseif a.action=="pause" then reaper.OnPauseButton()
  elseif a.action=="play" then
    editable()
    if a.start~=nil then
      local at=number(a.start,0,10000000); local bars=number(a.count_in or 0,0,8)
      local bar=measure(at)
      reaper.SetEditCurPos(bars==0 and at or time_of_bar(math.max(1,bar-bars)),true,false)
    end
    reaper.OnPlayButton()
  elseif a.action=="record" then
    stopped(); local armed=false
    for i=0,reaper.CountTracks(0)-1 do
      local tr=reaper.GetTrack(0,i)
      if reaper.GetMediaTrackInfo_Value(tr,"I_RECARM")==1 then
        assert(not generated[name(tr)],"Désarme les pistes générées avant d’enregistrer."); armed=true
      end
    end
    assert(armed,"Arme au moins une piste d’entrée dans Mes prises.")
    reaper.CSurf_OnRecord()
  else error("Transport inconnu.") end
  return {ok=true}
end
function H.seek(a)
  editable()
  local at=a.bar and time_of_bar(a.bar) or number(a.position,0,10000000)
  reaper.SetEditCurPos(at,true,true); return {ok=true}
end
function H.loop(a)
  desktop_rehearsal()
  if a.enabled==false then reaper.GetSetRepeat(0); return {ok=true} end
  local first=a.first and time_of_bar(a.first) or number(a.start,0,10000000)
  local last=a.last and time_of_bar(number(a.last,1,100000)+1) or number(a.finish,0,10000000)
  assert(last>first,"La fin doit suivre le début de la boucle.")
  reaper.GetSet_LoopTimeRange2(0,true,true,first,last,false); reaper.GetSetRepeat(1); return {ok=true}
end
function H.rate(a)
  desktop_rehearsal(); local rate=number(a.rate,.5,1.5)
  -- Same preserve-pitch action as the existing rehearsal engine.
  if reaper.GetToggleCommandState(40671)==0 then reaper.Main_OnCommand(40671,0) end
  reaper.CSurf_OnPlayRateChange(rate); return {ok=true}
end
function H.track(a)
  editable(); local tr=track(a.guid)
  local fields={mute="B_MUTE",solo="I_SOLO",volume="D_VOL",pan="D_PAN",record="I_RECARM"}
  local field=assert(fields[a.field],"Réglage de piste inconnu."); local value
  if a.field=="mute" or a.field=="record" then assert(type(a.value)=="boolean","Booléen requis"); value=a.value and 1 or 0
  elseif a.field=="solo" then assert(type(a.value)=="boolean","Booléen requis"); value=a.value and 2 or 0
  elseif a.field=="volume" then value=number(a.value,0,2)
  else value=number(a.value,-1,1) end
  if a.field=="record" then stopped(); assert(not generated[name(tr)],"Cette piste est générée par ReaCue.") end
  if preview and (a.field=="mute" or a.field=="solo") then preview=nil end
  reaper.SetMediaTrackInfo_Value(tr,field,value); reaper.TrackList_AdjustWindows(false); reaper.UpdateArrange(); return {ok=true}
end
function H.listen(a)
  desktop_rehearsal(); local mode=a.mode
  assert(mode=="original" or mode=="drums" or mode=="minus","Mode inconnu.")
  local music,drums={},{}
  for i=0,reaper.CountTracks(0)-1 do local tr=reaper.GetTrack(0,i); local n=name(tr); local lower=n:lower()
    if not generated[n] and not n:match("^PRISE ") then
      music[#music+1]=tr
      if lower:find("drum",1,true) or lower:find("batter",1,true) then drums[tr]=true end
    end
  end
  if mode~="original" then assert(next(drums),"Aucune piste Batterie/Drums. Sépare les stems ou renomme la piste.") end
  if mode=="original" then
    if preview then for guid,v in pairs(preview.tracks) do
      local ok,tr=pcall(track,guid); if ok then reaper.SetMediaTrackInfo_Value(tr,"B_MUTE",v.mute);reaper.SetMediaTrackInfo_Value(tr,"I_SOLO",v.solo) end
    end end
    preview=nil
  else
    if not preview then preview={tracks={}};for _,tr in ipairs(music) do preview.tracks[reaper.GetTrackGUID(tr)]={mute=reaper.GetMediaTrackInfo_Value(tr,"B_MUTE"),solo=reaper.GetMediaTrackInfo_Value(tr,"I_SOLO")} end end
    preview.mode=mode
    for _,tr in ipairs(music) do
      local folder=reaper.GetMediaTrackInfo_Value(tr,"I_FOLDERDEPTH")>0
      -- A muted parent folder silences its children, including the wanted drums.
      local audible=folder or (mode=="drums" and drums[tr]) or (mode=="minus" and not drums[tr])
      reaper.SetMediaTrackInfo_Value(tr,"B_MUTE",audible and 0 or 1);reaper.SetMediaTrackInfo_Value(tr,"I_SOLO",0)
    end
  end
  reaper.UpdateArrange(); return {ok=true}
end
function H.region(a)
  stopped(); local list=regions(); local r=a.id and region(a.id) or nil
  local operation=a.operation
  if operation=="update" then
    assert(r,"Section manquante"); assert(type(a.name)=="string" and #a.name>0 and #a.name<=120,"Nom invalide")
    -- Renaming must retain exact (possibly off-grid) boundaries.
    local start=a.first and a.first~=r.first and time_of_bar(a.first) or r.start
    local finish=a.last and a.last~=r.last and time_of_bar(number(a.last,1,100000)+1) or r.finish
    assert(finish>start,"La section doit contenir au moins une mesure.")
    for _,other in ipairs(list) do if other.id~=r.id then assert(finish<=other.start+.001 or start>=other.finish-.001,"Cette section chevauche une autre section.") end end
    return undo("modifier une section",function()assert(reaper.SetProjectMarker3(0,r.id,true,start,finish,a.name,r.color),"Modification refusée") end)
  elseif operation=="split" then
    assert(r and r.last>r.first,"Il faut au moins deux mesures."); local at=time_of_bar(math.floor((r.first+r.last+1)/2))
    return undo("couper une section",function()
      reaper.SetProjectMarker3(0,r.id,true,r.start,at,r.name,r.color)
      reaper.AddProjectMarker2(0,true,at,r.finish,r.name.." · suite",-1,r.color)
    end)
  elseif operation=="merge" then
    local next_region
    for i,x in ipairs(list) do if x.id==a.id then next_region=list[i+1] end end
    assert(r and next_region,"Aucune section suivante.")
    return undo("fusionner deux sections",function()
      reaper.SetProjectMarker3(0,r.id,true,r.start,next_region.finish,r.name,r.color)
      reaper.DeleteProjectMarker(0,next_region.id,true)
    end)
  elseif operation=="delete" then
    assert(r and #list>1,"Il faut garder au moins une section.")
    return undo("supprimer une section",function() reaper.DeleteProjectMarker(0,r.id,true) end)
  else error("Modification de structure inconnue.") end
end
function H.record_track(a)
  stopped(); local input=number(a.input,0,(reaper.GetNumAudioInputs() or 0)-1)
  assert(input==math.floor(input),"Entrée entière requise")
  local label=tostring(a.name or "Batterie"):sub(1,80)
  return undo("créer une piste d’enregistrement",function()
    local n=reaper.CountTracks(0);reaper.InsertTrackAtIndex(n,true);local tr=reaper.GetTrack(0,n)
    reaper.GetSetMediaTrackInfo_String(tr,"P_NAME","PRISE "..label,true)
    reaper.SetMediaTrackInfo_Value(tr,"I_RECINPUT",input)
    reaper.SetMediaTrackInfo_Value(tr,"I_RECMON",0)
    reaper.SetMediaTrackInfo_Value(tr,"I_RECARM",1)
    reaper.TrackList_AdjustWindows(false)
    return {ok=true,guid=reaper.GetTrackGUID(tr)}
  end)
end
function H.save() reaper.Main_OnCommand(40026,0); return {ok=true} end
function H.undo() stopped(); reaper.Undo_DoUndo2(0); return {ok=true} end
function H.redo() stopped(); reaper.Undo_DoRedo2(0); return {ok=true} end
function H.transpose(a)
  stopped(); local L=dofile(dir.."ReaCue_concert_lib.lua"); local ok=L.transpose(nil,tostring(a.delta)); assert(ok,"Transposition indisponible ou hors limites (±12).")
  return {ok=true}
end
function H.open_project(a)
  stopped(); assert(type(a.path)=="string" and a.path:lower():match("%.rpp$"),"Projet invalide")
  -- New tab preserves the current project and its unsaved changes.
  reaper.Main_OnCommand(40859,0); reaper.Main_openProject(a.path); return {ok=true}
end
function H.native(a)
  local tab=a.tab or "song"
  assert(({song=true,concert=true,stage=true,lighting=true,settings=true})[tab],"Onglet inconnu")
  local actions={new_file=true,new_stems=true,new_link=true,prepare=true,publish=true,separate=true,do_all=true,reanalyse=true,jobs=true,qr=true,check=true}
  assert(a.action==nil or actions[a.action],"Action inconnue")
  local alive=tonumber(reaper.GetExtState("ReaCue","win_alive")) or -100
  local ready=reaper.GetExtState("ReaCue","desktop_ready")
  if a.action and reaper.time_precise()-alive<2 and ready~="1" then
    error("Ferme l’ancienne fenêtre ReaCue dans REAPER puis réessaie. Le projet reste ouvert.")
  end
  if reaper.time_precise()-alive>=2 then
    local id=reaper.AddRemoveReaScript(true,0,dir.."ReaCue.lua",false)
    assert(id and id~=0,"Impossible d’ouvrir les outils ReaCue."); reaper.Main_OnCommand(id,0)
  end
  reaper.SetExtState("ReaCue","win_goto",tab,false)
  if a.action then
    reaper.SetExtState("ReaCue","desktop_action",R.json_encode({action=a.action,project_id=select(3,current()),expires=os.time()+8}),false)
  end
  return {ok=true,native=true}
end

-- Compatibility for every existing Studio/prompter screen, on the same private
-- desktop origin. No generic action/script execution is accepted from HTTP.
function H.web_api(a)
  assert(type(a.commands)=="string" and #a.commands<16000,"Requête invalide")
  local lines=R.json_array()
  local actions={ [1007]="play",[1008]="pause",[1016]="stop",[40073]="toggle" }
  for cmd in a.commands:gmatch("[^;]+") do
    if cmd=="TRANSPORT" then
      local s=H.state();lines[#lines+1]=table.concat({"TRANSPORT",reaper.GetPlayState(),s.position,s.repeat_on and 1 or 0},"\t")
    elseif cmd=="TRACK" then
      for _,t in ipairs(H.state().tracks) do
        local flags=(t.mute and 8 or 0)+(t.solo and 16 or 0)
        local peak=t.peak>0 and 200*math.log(t.peak,10) or -1500
        local safe=t.name:gsub("\\","\\\\"):gsub("\t","\\t"):gsub("\n","\\n")
        lines[#lines+1]=table.concat({"TRACK",t.id,safe,flags,t.volume,t.pan,peak,0,0,0,0,0,0,t.color},"\t")
      end
    elseif cmd:match("^GET/EXTSTATE/ReaCue/[%w_]+$") then
      local key=cmd:match("/([%w_]+)$");lines[#lines+1]="EXTSTATE\tReaCue\t"..key.."\t"..reaper.GetExtState("ReaCue",key)
    elseif cmd:match("^SET/EXTSTATE/ReaCue/") then
      local key,value=cmd:match("^SET/EXTSTATE/ReaCue/([%w_]+)/(.*)$")
      assert(key and (({remote=true,export_req=true,remote_seen=true,band_hello=true,band_ready=true,band_note=true})[key] or key:match("^hb%d+$")),"Clé de commande non autorisée")
      value=(value or ""):gsub("%%(%x%x)",function(hex)return string.char(tonumber(hex,16))end)
      if key=="remote" or key=="export_req" then
        assert(reaper.GetExtState("ReaCue","desktop_ready")=="1","Ouvre les Outils complets de cette version Desktop pour utiliser les commandes avancées.")
        reaper.SetExtState("ReaCue","desktop_guard_"..key,R.json_encode({value=value,project_id=select(3,current()),expires=os.time()+8}),false)
      end
      reaper.SetExtState("ReaCue",key,value or "",false)
    elseif cmd:match("^SET/POS/") then H.seek({position=cmd:sub(9)})
    elseif cmd:match("^SET/TRACK/") then
      local idx,field,value=cmd:match("^SET/TRACK/(%d+)/(%u+)/(.*)$")
      local tr=reaper.GetTrack(0,(tonumber(idx) or 0)-1);assert(tr,"Piste introuvable")
      local f=({MUTE="mute",SOLO="solo",VOL="volume",PAN="pan"})[field];assert(f,"Réglage inconnu")
      local val=tonumber(value);assert(val,"Valeur invalide")
      if f=="mute" or f=="solo" then val=val~=0 end
      H.track({guid=reaper.GetTrackGUID(tr),field=f,value=val})
    elseif actions[tonumber(cmd)] then
      local action=actions[tonumber(cmd)];if action=="toggle" then action=reaper.GetPlayState()==1 and "pause" or "play" end
      H.transport({action=action})
    else error("Commande Studio non prise en charge : "..cmd) end
  end
  return table.concat(lines,"\n").."\n"
end

local function handle(req)
  if type(req)~="table" or type(req.id)~="string" then return {ok=false,error="Requête invalide"} end
  if not tonumber(req.expires) or req.expires<os.time() then return {id=req.id,ok=false,error="Commande expirée, réessaie."} end
  if req.args~=nil and type(req.args)~="table" then return {id=req.id,ok=false,error="Arguments invalides"} end
  local readonly=req.command=="state"
  if req.command=="web_api" then
    readonly=true
    for cmd in tostring((req.args or {}).commands or ""):gmatch("[^;]+") do
      if cmd~="TRANSPORT" and cmd~="TRACK" and not cmd:match("^GET/EXTSTATE/ReaCue/[%w_]+$") then readonly=false end
    end
  end
  if not readonly and req.project_id~=select(3,current()) then return {id=req.id,ok=false,error="Le projet a changé. Actualise avant cette action."} end
  local fn=H[req.command]
  if not fn then return {id=req.id,ok=false,error="Commande inconnue"} end
  local ok,result=pcall(fn,req.args or {})
  return ok and {id=req.id,ok=true,result=result} or {id=req.id,ok=false,error=tostring(result)}
end
local last=0
local function loop()
  local now=reaper.time_precise()
  if now-last>1 then last=now;R.write_atomic(D.."/heartbeat.json",R.json_encode({version="1.0.0",time=os.time(),source=dir})) end
  local raw=read(D.."/request.json")
  if raw then
    os.remove(D.."/request.json")
    R.write_atomic(D.."/response.json",R.json_encode(handle(R.json_decode(raw))))
  end
  reaper.defer(loop)
end
reaper.atexit(function()os.remove(D.."/heartbeat.json")end)
-- Exposed only to Lua unit tests; network commands still use the allowlist above.
if REACUE_DESKTOP_TEST then return {handlers=H,handle=handle} end
loop()
