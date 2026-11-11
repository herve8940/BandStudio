"""Desktop integration: real HTTP/auth/mailbox and Lua command guards; no live REAPER."""
import json
import threading
import time
from http.client import HTTPConnection
from pathlib import Path

import pytest

from reacue_mcp.desktop import Desktop, DesktopBridge, DesktopError, Server, atomic_json

ROOT = Path(__file__).resolve().parents[1]


class FakeBridge:
    def __init__(self):
        self.calls = []
        self.connected = True
        self.state = dict(project='/tmp/Desktop test.RPP',project_id='project-A',title='Morceau test',
                          dirty=False,playing=False,recording=False,paused=False,position=0,measure=1,beat=1,
                          numerator=4,denominator=4,bpm=120,rate=1,length=32,repeat_on=False,
                          loop_start=0,loop_end=0,listen_mode='original',locked=False,
                          inputs=[dict(id=0,name='Entrée 1')],takes=[],
                          tracks=[dict(id=i+1,guid=f'{{{i}}}',name=name,volume=1,pan=0,mute=False,
                                       solo=False,record=False,input=0,generated=name=='CLICK',record_track=False,peak=0)
                                  for i,name in enumerate(['Batterie','Basse','Guitares','CLICK'])],
                          regions=[dict(id=i+1,name=name,start=i*8,finish=(i+1)*8,first=i*4+1,last=(i+1)*4,color=0)
                                   for i,name in enumerate(['Intro','Couplet','Refrain','Final'])])
    def alive(self): return self.connected
    def call(self, command, args=None, project_id=None, **kwargs):
        self.calls.append((command,args,project_id))
        if command == 'state': return dict(self.state)
        if command == 'web_api': return 'TRANSPORT\t0\t0\t0\n'
        assert project_id == self.state['project_id']
        if command == 'listen': self.state['listen_mode'] = args['mode']
        if command == 'seek': self.state['position'] = args.get('position',0)
        if command == 'loop': self.state['repeat_on'] = args.get('enabled',True)
        return {'ok':True}


@pytest.fixture
def host(tmp_path):
    bridge = FakeBridge()
    desktop = Desktop(tmp_path,bridge)
    server = Server(desktop)
    thread = threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    yield desktop,bridge,server
    server.shutdown();server.server_close();thread.join(2)


def request(server,path,method='GET',body=None,authorized=True,headers=None):
    conn=HTTPConnection('127.0.0.1',server.server_port,timeout=3)
    h={'Content-Type':'application/json','X-ReaCue-Desktop':'1'}
    if authorized:h['Cookie']='reacue_desktop='+server.desktop.token
    h.update(headers or {})
    conn.request(method,path,json.dumps(body) if body is not None else None,h)
    response=conn.getresponse();data=response.read();code=response.status;response_headers=dict(response.getheaders());conn.close()
    return code,data,response_headers


def test_http_auth_and_read_only_open(host):
    d,b,s=host
    assert request(s,'/api/status',authorized=False)[0]==403
    code,_,headers=request(s,'/?token='+d.token,authorized=False)
    assert code==303 and 'HttpOnly' in headers['Set-Cookie'] and 'SameSite=Strict' in headers['Set-Cookie']
    assert request(s,'/app/')[0]==200
    assert request(s,'/api/status')[0]==200
    assert all(c[0]=='state' for c in b.calls)
    for headers in ({'Origin':'https://evil.example'},{'Host':'evil.example'},{'Sec-Fetch-Site':'cross-site'}):
        assert request(s,'/api/control','POST',{'command':'transport','project_id':'project-A','args':{'action':'record'}},headers=headers)[0]==403
    assert request(s,'/api/control','POST',{},headers={'X-ReaCue-Desktop':'0'})[0]==403
    assert request(s,'/app/%2e%2e/%2e%2e/desktop.py')[0]==404


def test_controls_need_project_and_legacy_preserves_encoded_delimiters(host):
    d,b,s=host
    assert request(s,'/api/control','POST',{'command':'transport','args':{'action':'record'}})[0]==400
    assert request(s,'/api/control','POST',{'command':'execute','project_id':'project-A'})[0]==400
    code,data,_=request(s,'/legacy/studio.html')
    assert code==200 and b'name="reacue-project" content="project-A"' in data and b'legacy-bridge.js' in data
    command='SET/EXTSTATE/ReaCue/remote/note%7Ccouplet%3Bfinal'
    assert request(s,'/_/'+command,headers={'X-ReaCue-Project':'project-A'})[0]==200
    assert b.calls[-1]==('web_api',{'commands':command},'project-A')


def test_published_audio_never_crosses_projects(host):
    d,b,s=host
    d.published.mkdir()
    atomic_json(d.published/'reacue_song.json',{'project':'/tmp/another.RPP','id':'old'})
    assert d.published_data('reacue_song.json')['stale']
    atomic_json(d.published/'reacue_song.json',{'project':b.state['project'],'id':'new'})
    atomic_json(d.published/'reacue_peaks.json',{'song_id':'old'})
    assert d.published_data('reacue_peaks.json')['stale']
    atomic_json(d.published/'reacue_peaks.json',{'song_id':'new'})
    assert d.published_data('reacue_peaks.json')['song_id']=='new'


def test_mailbox_timeout_removes_pending_mutation(tmp_path):
    bridge=DesktopBridge(tmp_path)
    atomic_json(bridge.directory/'heartbeat.json',{})
    with pytest.raises(DesktopError,match='ne répond pas'):
        bridge.call('transport',{'action':'record'},'project-A',timeout=.06)
    assert not (bridge.directory/'request.json').exists()


def test_two_clients_serialize_one_mailbox(tmp_path):
    a,b=DesktopBridge(tmp_path),DesktopBridge(tmp_path)
    atomic_json(a.directory/'heartbeat.json',{})
    results=[];done=threading.Event()
    def reaper():
        while not done.is_set():
            path=a.directory/'request.json'
            if path.exists():
                req=json.loads(path.read_text());path.unlink();time.sleep(.05)
                atomic_json(a.directory/'response.json',{'id':req['id'],'ok':True,'result':req['args']['n']})
            time.sleep(.005)
    responder=threading.Thread(target=reaper,daemon=True);responder.start()
    clients=[threading.Thread(target=lambda br,n:results.append(br.call('test',{'n':n},timeout=2)),args=(br,n)) for n,br in enumerate((a,b))]
    for t in clients:t.start()
    for t in clients:t.join(3)
    done.set();responder.join(1)
    assert sorted(results)==[0,1]


def test_native_file_dialog_is_waiting_not_new_installation(host):
    d,b,s=host
    assert d.status()['connected']
    atomic_json(d.resource/'ReaCueDesktop/heartbeat.json',{})
    b.connected=False
    assert d.status()['waiting'] and not d.status()['connected']


LUA_FAKE=r'''
REACUE_DESKTOP_TEST=true
PROJECT='A'; PLAY=0; MUTATIONS=0; REPEAT=0; LOOP={0,0}; RATE=1; CURSOR=0
TRACKS={{name='Drums',guid='drums',B_MUTE=0,I_SOLO=0,D_VOL=1},{name='Bass',guid='bass',B_MUTE=1,I_SOLO=2,D_VOL=.7},{name='CLICK',guid='click',B_MUTE=0}}
REGIONS={{1,0,8,'Intro'},{2,8,20,'Refrain'}}
reaper.EnumProjects=function()return PROJECT,'/tmp/'..PROJECT..'.RPP'end
reaper.GetPlayState=function()return PLAY end
reaper.GetPlayPosition=function()return CURSOR end
reaper.GetCursorPosition=function()return CURSOR end
reaper.CountTracks=function()return #TRACKS end
reaper.GetTrack=function(_,i)return TRACKS[i+1]end
reaper.GetTrackGUID=function(t)return t.guid end
reaper.GetTrackColor=function()return 0 end
reaper.GetMediaTrackInfo_Value=function(t,k)return t[k] or 0 end
reaper.SetMediaTrackInfo_Value=function(t,k,v)t[k]=v;MUTATIONS=MUTATIONS+1 end
reaper.GetSetMediaTrackInfo_String=function(t,k,v,set)if set then t.name=v end;return true,t.name end
reaper.GetNumAudioInputs=function()return 2 end
reaper.GetInputChannelName=function(i)return 'Input '..i end
reaper.CountTrackMediaItems=function()return 0 end
reaper.CountProjectMarkers=function()return #REGIONS,0,#REGIONS end
reaper.EnumProjectMarkers3=function(_,i)local r=REGIONS[i+1];return 1,true,r[2],r[3],r[4],r[1],0 end
reaper.TimeMap2_timeToBeats=function(_,t)local bar=t<8 and t/2 or 4+(t-8)/3;return (bar%1)*4,math.floor(bar),4,bar*4,4 end
reaper.TimeMap2_beatsToTime=function(_,beat,bar)return bar<4 and bar*2 or 8+(bar-4)*3 end
reaper.TimeMap_GetTimeSigAtTime=function()return 4,4,120 end
reaper.GetSet_LoopTimeRange2=function(_,set,loop,a,b)if set then LOOP={a,b};MUTATIONS=MUTATIONS+1 end;return LOOP[1],LOOP[2]end
reaper.GetSetRepeat=function(v)if v>=0 then REPEAT=v;MUTATIONS=MUTATIONS+1 end;return REPEAT end
reaper.Master_GetPlayRate=function()return RATE end
reaper.GetProjectLength=function()return 20 end
reaper.IsProjectDirty=function()return 0 end
reaper.OnPlayButton=function()PLAY=1;MUTATIONS=MUTATIONS+1 end
reaper.OnStopButton=function()PLAY=0;MUTATIONS=MUTATIONS+1 end
reaper.OnPauseButton=function()PLAY=2;MUTATIONS=MUTATIONS+1 end
reaper.CSurf_OnRecord=function()PLAY=5;MUTATIONS=MUTATIONS+1 end
reaper.SetEditCurPos=function(t)CURSOR=t;MUTATIONS=MUTATIONS+1 end
reaper.TrackList_AdjustWindows=function()end
reaper.UpdateArrange=function()end
reaper.GetToggleCommandState=function()return 1 end
reaper.CSurf_OnPlayRateChange=function(v)RATE=v;MUTATIONS=MUTATIONS+1 end
reaper.SetProjectMarker3=function(_,id,isr,a,b,n)for _,r in ipairs(REGIONS)do if r[1]==id then r[2]=a;r[3]=b;r[4]=n;MUTATIONS=MUTATIONS+1;return true end end end
reaper.Undo_BeginBlock=function()end;reaper.Undo_EndBlock=function()end
reaper.InsertTrackAtIndex=function()TRACKS[#TRACKS+1]={guid='new',name=''};MUTATIONS=MUTATIONS+1 end
reaper.time_precise=function()return 100 end
'''


@pytest.fixture
def lua(tmp_path):
    from test_lua import runtime
    L=runtime(tmp_path);L.execute(LUA_FAKE)
    module=L.eval(f'dofile([[{ROOT / "reaper/ReaCue_Desktop_Bridge.lua"}]])')
    codec=L.eval(f'dofile([[{ROOT / "reaper/ReaCue_run.lua"}]])')
    def call(command,args=None,project='A|/tmp/A.RPP',expires=None):
        req=dict(id='test',expires=expires or time.time()+10,command=command,args=args or {},project_id=project)
        return json.loads(codec.json_encode(module.handle(codec.json_decode(json.dumps(req)))))
    return L,call


def test_lua_read_only_state_and_stale_or_expired_commands(lua):
    L,call=lua
    assert call('state')['ok'] and L.globals().MUTATIONS==0
    assert not call('track',{'guid':'drums','field':'mute','value':True},project='B|/tmp/B.RPP')['ok']
    assert not call('transport',{'action':'record'},expires=1)['ok']
    assert not call('web_api',{'commands':'1007'},project=None)['ok']
    assert call('web_api',{'commands':'TRANSPORT;TRACK'},project=None)['ok']
    assert L.globals().MUTATIONS==0


def test_lua_real_tempo_map_and_bounds(lua):
    L,call=lua
    assert call('loop',{'first':5,'last':6})['ok']
    assert (L.globals().LOOP[1],L.globals().LOOP[2])==(8,14)
    assert not call('loop',{'first':6,'last':4})['ok']
    assert not call('rate',{'rate':8})['ok']
    assert not call('region',{'operation':'update','id':1,'name':'Intro','first':1,'last':5})['ok']
    assert call('region',{'operation':'update','id':1,'name':'Intro courte','first':1,'last':3})['ok']


def test_lua_rename_preserves_off_grid_edges_and_play_without_countin(lua):
    L,call=lua
    L.execute('REGIONS[1][2]=.2;REGIONS[1][3]=7.9')
    assert call('region',{'operation':'update','id':1,'name':'Nouvelle intro','first':1,'last':4})['ok']
    assert L.globals().REGIONS[1][2]==.2 and L.globals().REGIONS[1][3]==7.9
    assert call('transport',{'action':'play','start':5.43,'count_in':0})['ok']
    assert L.globals().CURSOR==5.43


def test_lua_drum_listening_does_not_silence_parent_folder(lua):
    L,call=lua
    L.execute("table.insert(TRACKS,1,{name='Groupe',guid='group',I_FOLDERDEPTH=1,B_MUTE=1,I_SOLO=2})")
    assert call('listen',{'mode':'drums'})['ok']
    assert L.globals().TRACKS[1].B_MUTE==0
    assert call('listen',{'mode':'original'})['ok']
    assert L.globals().TRACKS[1].B_MUTE==1 and L.globals().TRACKS[1].I_SOLO==2


def test_lua_record_guard_and_input_configuration(lua):
    L,call=lua
    assert not call('transport',{'action':'record'})['ok']
    assert not call('record_track',{'name':'Drums','input':99})['ok']
    assert call('record_track',{'name':'Batterie','input':1})['ok']
    tr=L.globals().TRACKS[4]
    assert tr.name=='PRISE Batterie' and tr.I_RECINPUT==1 and tr.I_RECARM==1 and tr.I_RECMON==0
    assert call('transport',{'action':'record'})['ok']
    assert L.globals().PLAY==5
    assert not call('region',{'operation':'delete','id':1})['ok']
    assert call('transport',{'action':'stop'})['ok']


def test_lua_listening_restores_original_mute_solo_across_projects(lua):
    L,call=lua
    call('state')
    assert call('listen',{'mode':'drums'})['ok']
    assert L.globals().TRACKS[2].I_SOLO==0
    L.globals().PROJECT='B';call('state')
    L.globals().PROJECT='A';call('state')
    assert call('listen',{'mode':'original'})['ok']
    assert L.globals().TRACKS[2].I_SOLO==2 and L.globals().TRACKS[2].B_MUTE==1


def test_lua_legacy_encoded_value_and_allowlist(lua):
    L,call=lua
    L.globals().reaper.SetExtState('ReaCue','desktop_ready','1')
    assert call('web_api',{'commands':'SET/EXTSTATE/ReaCue/remote/note%7Ccouplet%3Bfinal'})['ok']
    assert L.globals().reaper.GetExtState('ReaCue','remote')=='note|couplet;final'
    assert not call('web_api',{'commands':'SET/EXTSTATE/ReaCue/install_dir/evil'})['ok']
    assert not call('web_api',{'commands':'40006'})['ok']
    assert call('web_api',{'commands':'SET/EXTSTATE/ReaCue/hb2/test;SET/EXTSTATE/ReaCue/remote_seen/1'})['ok']


def test_lua_queued_legacy_command_cannot_follow_project_switch(lua):
    L,call=lua
    L.globals().reaper.SetExtState('ReaCue','desktop_ready','1')
    codec=L.eval(f'dofile([[{ROOT / "reaper/ReaCue_run.lua"}]])')
    assert call('web_api',{'commands':'SET/EXTSTATE/ReaCue/remote/play%7C'})['ok']
    L.globals().PROJECT='B'
    codec.guard_desktop_commands()
    assert L.globals().reaper.GetExtState('ReaCue','remote')==''
    # A later phone command must not be removed by the old Desktop guard.
    L.globals().PROJECT='A'
    call('web_api',{'commands':'SET/EXTSTATE/ReaCue/remote/play%7C'})
    L.globals().reaper.SetExtState('ReaCue','remote','stop|phone')
    L.globals().PROJECT='B';codec.guard_desktop_commands()
    assert L.globals().reaper.GetExtState('ReaCue','remote')=='stop|phone'
