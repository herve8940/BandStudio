-- BandStudio local transport extension for REAPER. MIT.
-- Actions > New action > Load ReaScript. Open BandStudio > Prises > Relier BandPilot.
-- Commands affect BandStudio only; this is not an audio VST/AU or a second recorder.
local windows = reaper.GetOS():match('Win') ~= nil
local home = os.getenv(windows and 'APPDATA' or 'HOME') or ''
local folder = windows and (home .. '/BandStudio/Bridge/') or (home .. '/Library/Application Support/BandStudio/Bridge/')
local pending, state, message = nil, nil, 'Ouvre BandStudio et active la connexion locale dans Prises.'
local function read(path)
  local f=io.open(path,'rb');if not f then return nil end
  local data=f:read(1000000);f:close();return data
end
local function str(data,key) return data and data:match('"'..key..'"%s*:%s*"([^"\\]*)"') end
local function num(data,key) return tonumber(data and data:match('"'..key..'"%s*:%s*([%d%.%-]+)')) end
local function yes(data,key) return data and data:match('"'..key..'"%s*:%s*(true)')~=nil end
local function command(action)
  if pending or not state then return end
  local id=reaper.genGuid():gsub('[{}]',''):lower()
  local session,project=str(state,'session'),str(state,'projectID')
  if not session or not project or not id:match('^[%x%-]+$') then message='État BandStudio invalide';return end
  local path=folder..'request-'..id..'.json';local f=io.open(path..'.tmp','wb')
  if not f then message='Connexion locale inaccessible';return end
  f:write(string.format('{"id":"%s","session":"%s","projectID":"%s","created":%d,"args":{"action":"%s"}}',id,session,project,os.time(),action));f:close()
  if not os.rename(path..'.tmp',path) then message='Commande non transmise';return end
  pending={id=id,at=reaper.time_precise(),request=path};message='Commande envoyée…'
end
local buttons={{'|< Début','start'},{'< Repère','previous'},{'Lecture','play'},{'Pause','pause'},{'Repère >','next'},{'REC','record'},{'Arrêter','stop'},{'Repère +','marker'}}
gfx.init('BandStudio · télécommande',560,230,0)
local was_down=false
local function frame()
  state=read(folder..'state.json')
  if not state or math.abs(os.time()-(num(state,'updated') or 0))>4 then state=nil end
  if pending then
    local response=folder..'response-'..pending.id..'.json';local reply=read(response)
    if reply then
      message=yes(reply,'ok') and 'Commande acceptée. État réel affiché ci-dessous.' or (str(reply,'error') or 'Commande refusée : regarde BandStudio.')
      os.remove(response);pending=nil
    elseif reaper.time_precise()-pending.at>8 then
      os.remove(pending.request);pending=nil;message='Réponse perdue : vérifie BandStudio. Aucun renvoi automatique.'
    end
  end
  gfx.set(.06,.08,.12,1);gfx.rect(0,0,gfx.w,gfx.h)
  gfx.setfont(1,'Arial',17);gfx.set(.88,.92,1,1);gfx.x=16;gfx.y=16
  gfx.drawstr(state and ('BandStudio · '..(yes(state,'recording') and 'ENREGISTREMENT' or yes(state,'playing') and 'Lecture' or 'Prêt')) or 'BandStudio non relié')
  gfx.x=16;gfx.y=44;local at=num(state,'position') or 0;gfx.drawstr(string.format('%d:%05.2f',math.floor(at/60),at%60))
  local down=(gfx.mouse_cap&1)==1
  for i,b in ipairs(buttons) do
    local x=16+((i-1)%4)*136;local y=78+math.floor((i-1)/4)*44
    local hover=gfx.mouse_x>=x and gfx.mouse_x<x+128 and gfx.mouse_y>=y and gfx.mouse_y<y+36
    gfx.set(b[2]=='record' and .55 or .18,.22,.33,state and not pending and 1 or .4);gfx.rect(x,y,128,36)
    gfx.set(.95,.95,1,1);gfx.x=x+8;gfx.y=y+8;gfx.drawstr(b[1])
    if hover and down and not was_down then command(b[2]) end
  end
  was_down=down;gfx.setfont(1,'Arial',12);gfx.x=16;gfx.y=177;gfx.drawstr(message)
  gfx.x=16;gfx.y=199;gfx.drawstr('Pilote BandStudio. Le transport et les pistes REAPER restent indépendants.')
  gfx.update();if gfx.getchar()>=0 then reaper.defer(frame) end
end
reaper.atexit(function() if pending then os.remove(pending.request) end end)
frame()
