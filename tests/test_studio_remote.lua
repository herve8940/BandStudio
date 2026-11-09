-- Run with lua 5.3+ or fengari: test_studio_remote.lua path/to/BandStudio_Remote.lua
local source=arg[1]
local files={},now
now=os.time()
local folder='/synthetic/Library/Application Support/BandStudio/Bridge/'
files[folder..'state.json']=string.format('{"updated":%d,"session":"session-a","projectID":"project-a","position":12.5,"recording":false,"playing":true}',now)
os.getenv=function()return '/synthetic' end
io.open=function(path,mode)
 if mode=='rb' then if not files[path] then return nil end;return {read=function()return files[path] end,close=function()end} end
 if mode=='wb' then return {write=function(_,text)files[path]=text end,close=function()end} end
 error('unexpected file mode')
end
os.rename=function(from,to)files[to]=files[from];files[from]=nil;return true end
os.remove=function(path)files[path]=nil;return true end
reaper={GetOS=function()return 'OSX64' end,genGuid=function()return '{00000000-0000-4000-8000-000000000001}' end,time_precise=function()return now end,atexit=function()end,defer=function()end}
gfx={w=560,h=230,mouse_cap=1,mouse_x=160,mouse_y=130,init=function()end,set=function()end,rect=function()end,setfont=function()end,drawstr=function()end,update=function()end,getchar=function()return -1 end}
dofile(source)
local request=files[folder..'request-00000000-0000-4000-8000-000000000001.json']
assert(request and request:find('"action":"record"',1,true),'REC did not emit an explicit recording command')
assert(request:find('"projectID":"project%-a"'),'command is not bound to the displayed project')
assert(request:find('"session":"session%-a"'),'command is not bound to the active session')
print('PASS REAPER Lua remote: explicit REC, project/session binding, atomic request')
