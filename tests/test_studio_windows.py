"""Portable document edits and real offline audio mixing for the Windows host."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import numpy as np
import pytest
import soundfile as sf

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'desktop/studio'))
from windows import project as model
from windows.audio import Audio
from windows.host import Api

ENGINE=Path(os.environ.get('BANDSTUDIO_TEST_ENGINE',str(ROOT/'desktop-build/standalone/Engine')))


def fixture(root):
    (root/'Audio').mkdir(parents=True,exist_ok=True);p=model.fresh('Essai Windows');p['settings'].update(countBars=0,callsEnabled=False,countVoice=False,regionCountEnabled=False)
    for role,hz in [('source',440),('drums',880),('bass',220)]:
        x=(.15*np.sin(np.arange(2*44100)*2*np.pi*hz/44100)).astype('float32');path=root/'Audio'/(role+'.wav');sf.write(path,np.column_stack((x,x)),44100,subtype='FLOAT');p['tracks'].append(model.track(path,root,role,role))
    p['sections']=[dict(id='one',name='Intro',start=0,end=2,locked=True,origin='manual')];model.save(p,root);return p


def strength(x,hz):
    x=x[4410:22050,0];n=np.arange(len(x));return abs(np.sum(x*np.exp(-2j*np.pi*hz*n/44100)))/len(x)


def test_portable_modes_mute_and_stereo_pan(tmp_path):
    p=fixture(tmp_path);a=Audio(ENGINE);a.load(p,tmp_path)
    for mode,present,absent in [('original',[440],[880,220]),('mix',[880,220],[440]),('drums',[880],[440,220]),('minus',[220],[440,880]),('solo:bass',[220],[440,880]),('minus:bass',[880],[440,220])]:
        a.mode=mode;x=a.mix(0,44100)
        assert all(strength(x,hz)>.04 for hz in present)
        assert all(strength(x,hz)<.0001 for hz in absent)
    a.mode='drums';a.project['tracks'][1]['pan']=-1;x=a.mix(0,44100);assert np.max(abs(x[:,1]))==0 and np.max(abs(x[:,0]))>.1


def test_loop_has_exact_boundaries_and_preserves_position(tmp_path):
    p=fixture(tmp_path);a=Audio(ENGINE);a.load(p,tmp_path);a.loop=True;a.loopStart=.4;a.loopEnd=.9;a.position=.4;a.play(hardware=False)
    x=a.block(44100);assert a.laps==2 and a.position==pytest.approx(.4,abs=1/44100)
    assert np.max(abs(x))>.05
    a.pause();assert not a.running


def test_native_document_roundtrip_and_path_validation(tmp_path):
    p=fixture(tmp_path);assert model.load(tmp_path)['id']==p['id'];p['tracks'][0]['file']='../private.wav'
    with pytest.raises(ValueError):model.validate(p,tmp_path)


def test_host_edits_reject_stale_project_and_keep_manual_sections(tmp_path):
    p=fixture(tmp_path/'song.bandstudio');api=Api(ENGINE,tmp_path);api._project=p;api._root=tmp_path/'song.bandstudio';api._audio.load(p,api._root)
    api.command(dict(command='notes',args={'value':'bad'},projectID='wrong'));assert p['notes']==''
    api.command(dict(command='splitSection',args={'id':'one','time':.75},projectID=p['id']));assert [s['end'] for s in api._project['sections']]==[.75,2]
    model.apply_sections(api._project,[dict(start=0,end=2,name='Automatic',locked=False,origin='analysis')]);assert len(api._project['sections'])==2
    api.command(dict(command='track',args={'id':p['tracks'][0]['id'],'pan':3},projectID=p['id']));assert api._project['tracks'][0]['pan']==0
    assert model.load(api._root)['sections'][0]['end']==.75


def test_installer_paths_are_not_the_users_reaper_directory():
    source=(ROOT/'desktop/studio/windows/host.py').read_text()
    assert "REAPER_RESOURCE_PATH=str(self._engine/'worker-state')" in source
    assert 'js_api=api' in (ROOT/'desktop/studio/windows/launcher.py').read_text()


@pytest.mark.parametrize('installation',['x64','standard','user'])
@pytest.mark.parametrize('open_reaper',[True,False])
def test_send_export_reuses_reaper_and_preserves_the_complete_path(tmp_path,monkeypatch,installation,open_reaper):
    from windows import host
    program_files=tmp_path/'Program Files';local=tmp_path/'Local AppData'
    monkeypatch.setenv('ProgramFiles',str(program_files));monkeypatch.setenv('LOCALAPPDATA',str(local))
    app={'x64':program_files/'REAPER (x64)/reaper.exe',
         'standard':program_files/'REAPER/reaper.exe',
         'user':local/'Programs/REAPER (x64)/reaper.exe'}[installation]
    app.parent.mkdir(parents=True);app.touch()
    song=tmp_path/'song.bandstudio';p=fixture(song)
    api=Api(ENGINE,tmp_path);api._root=song;api._project=p;api._audio.project=p
    exported=tmp_path/'Exports/Été & répétition [live].rpp'
    events=[];launches=[]
    monkeypatch.setattr(api,'_op',lambda name,run:run())
    monkeypatch.setattr(api,'_guides',lambda:events.append('guides'))
    def export(kind):
        events.append(kind);exported.parent.mkdir(exist_ok=True)
        exported.write_text('<REAPER_PROJECT 0.1 7.0 1\n>\n',encoding='utf-8')
        return None,{'path':str(exported)}
    monkeypatch.setattr(api,'_work',export)
    def launch(argv,**kwargs):
        # Check the process boundary: the RPP exists and remains one argument.
        assert Path(argv[-1]).is_file()
        launches.append(argv)
    monkeypatch.setattr(host.subprocess,'Popen',launch)
    api._command(dict(command='reaper',args={'open':open_reaper},projectID=p['id']))
    assert events==['guides','reaper'] and api._last_export==str(exported)
    if open_reaper:
        assert len(launches)==1
        argv=launches[0]
        assert argv[0]==str(app) and argv[-1]==str(exported)
        assert '-nonewinst' in argv and '-newinst' not in argv
        assert len(argv)==3
    else:assert not launches


def test_second_play_during_guide_preparation_does_not_start_another_job(tmp_path,monkeypatch):
    p=fixture(tmp_path/'song.bandstudio');api=Api(ENGINE,tmp_path)
    api._project=p;api._root=tmp_path/'song.bandstudio';api._audio.load(p,api._root)
    api._busy=True
    monkeypatch.setattr(api,'_op',lambda *args:pytest.fail('Duplicate preparation'))
    assert api.command(dict(command='play',projectID=p['id']))['ok']
    assert api._busy and not api._audio.running


def test_optional_component_installations_cannot_modify_same_runtime_concurrently(tmp_path):
    api=Api(ENGINE,tmp_path);api._components['stems']=object()
    with pytest.raises(ValueError,match='déjà ouverte'):api._install('rhythm')
    with pytest.raises(ValueError,match='Termine l’installation'):api._work('smartgrid')


def test_slowdown_preserves_pitch_when_ffmpeg_is_available(tmp_path):
    from platform_tools import executable
    if not executable(ENGINE,'ffmpeg').exists():pytest.skip('Prepared engine required')
    p=fixture(tmp_path);a=Audio(ENGINE);a.rate=.75;a.load(p,tmp_path);a.mode='drums';a.render(tmp_path/'slow.wav',0,1.5,False)
    x,sr=sf.read(tmp_path/'slow.wav');assert len(x)==88200 and strength(x,880)>.02 and strength(x,660)<.002


def test_long_waveforms_do_not_overflow_windows_int32_and_legacy_cache_is_repaired(tmp_path,monkeypatch):
    # Reproduce NumPy 1.x's Windows default integer type, including on macOS CI.
    arange=np.arange
    monkeypatch.setattr(np,'arange',lambda *args,**kwargs:arange(*args,**({'dtype':np.int32}|kwargs)))
    p=model.fresh('Long');path=tmp_path/'long.wav'
    with sf.SoundFile(path,'w',samplerate=44100,channels=1,subtype='FLOAT') as f:
        for _ in range(202):f.write(np.full(65536,.25,dtype=np.float32))
    track=model.track(path,tmp_path,'Original','source');p['tracks']=[track]
    assert min(track['peaks'])==pytest.approx(.25)
    track['peaks']=[0.0]*720;track.pop('peaksVersion');model.save(p,tmp_path)
    stamp=(path.stat().st_size,path.stat().st_mtime_ns)
    restored=model.load(tmp_path)['tracks'][0]
    assert min(restored['peaks'])==pytest.approx(.25) and restored['peaksVersion']==2
    assert stamp==(path.stat().st_size,path.stat().st_mtime_ns)


def test_library_remove_loaded_song_is_reversible_and_rejects_external_paths(tmp_path):
    import catalog
    root=tmp_path/'Songs';root.mkdir();song=root/'song.bandstudio';p=fixture(song)
    api=Api(ENGINE,root);api._project=p;api._root=song;api._audio.load(p,song)
    assert api.command(dict(command='deleteProject',args={'path':str(song)}))['ok']
    assert api._root is None and not api._audio.data and not song.exists()
    assert api._list()==[] and len(catalog.trashed(root))==1
    assert api.command(dict(command='restoreProject'))['ok']
    assert model.load(song)['id']==p['id'] and len(api._list())==1
    outside=tmp_path/'external.bandstudio';fixture(outside)
    assert not api.command(dict(command='deleteProject',args={'path':str(outside)}))['ok']
    assert (outside/'Audio/source.wav').is_file()
    catalog.remove(root,song);fixture(song)
    restored=Path(catalog.restore(root));assert restored!=song and restored.is_dir() and song.is_dir()


@pytest.mark.parametrize('failure',['none','error','cancel'])
def test_prepare_all_runs_serially_and_preserves_completed_steps(tmp_path,monkeypatch,failure):
    from windows import advanced_host
    root=tmp_path/'song.bandstudio';p=fixture(root);api=Api(ENGINE,tmp_path);api._root=root;api._project=p
    events=[];monkeypatch.setattr(api,'_plan',lambda:['separate','grid','structure','key','guides'])
    monkeypatch.setattr(api,'_state',lambda:None);monkeypatch.setattr(api,'_reload',lambda:None)
    def analyze(kind,args):
        events.append(kind)
        if kind=='structure' and failure=='error':
            api._project['notes']='partial';raise ValueError('model failed')
        api._project['notes']=kind;api._save()
        if kind=='grid' and failure=='cancel':api._cancelled.set()
    monkeypatch.setattr(api,'_analysis',analyze)
    monkeypatch.setattr(advanced_host,'advanced_task',lambda *a:events.append('key'))
    monkeypatch.setattr(api,'_guides',lambda:events.append('guides'))
    if failure=='none':
        api._prepare_all({});assert events==['separate','grid','structure','key','guides']
    else:
        with pytest.raises(RuntimeError,match='étapes terminées sont conservées'):api._prepare_all({})
        assert events==(['separate','grid','structure'] if failure=='error' else ['separate','grid'])
        assert model.load(root)['notes']=='grid'
    assert api._project['sections']==p['sections']


def test_prepare_plan_preserves_existing_stems_and_locked_grid(tmp_path):
    api=Api(tmp_path/'no-components',tmp_path/'library');api._project=fixture(tmp_path/'song.bandstudio');api._project['gridLocked']=True
    # Chord discovery/alignment belongs to the final review after the sections.
    assert api._plan()==['key','prepareReview','guides']
    api._project['key']='Dm';assert api._plan()==['prepareReview','guides']
    assert not {'separate','grid','smartgrid'}.intersection(api._plan())


def test_catalog_extracts_embedded_artwork_and_keeps_existing_cover_on_failure(tmp_path):
    import catalog
    from platform_tools import executable
    import subprocess
    if not executable(ENGINE,'ffmpeg').is_file():pytest.skip('Prepared engine required')
    folder=tmp_path/'song.bandstudio';fixture(folder)
    mp3=tmp_path/'tagged.mp3'
    subprocess.run([str(executable(ENGINE,'ffmpeg')),'-v','error','-y','-i',str(folder/'Audio/source.wav'),'-i',str(ROOT/'desktop/studio/assets/BandStudio.png'),'-map','0:a','-map','1:v','-c:a','libmp3lame','-c:v','mjpeg','-id3v2_version','3','-disposition:v','attached_pic',str(mp3)],check=True)
    assert catalog.extract(mp3,folder,ENGINE)
    assert catalog.entries(tmp_path)[0]['artwork'].startswith('data:image/jpeg;base64,')
    original=(folder/'Artwork.jpg').read_bytes()
    assert not catalog.extract(folder/'Audio/source.wav',folder,ENGINE)
    assert (folder/'Artwork.jpg').read_bytes()==original


@pytest.mark.skipif(os.name!='nt',reason='Actual Windows voices')
def test_windows_announcements_use_requested_language_or_explain_missing_voice(tmp_path):
    import subprocess
    script=ROOT/'desktop/studio/windows/speak.ps1'
    for language,text in [('en','Chorus in four, three, two, one.'),('fr','Refrain dans quatre, trois, deux, un.')]:
        wave=tmp_path/(language+'.wav');request=tmp_path/(language+'.json')
        request.write_text(json.dumps(dict(voice='Système',language=language,rate=180,text=text,output=str(wave))),encoding='utf-8')
        result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(script),'-RequestFile',str(request)],capture_output=True,timeout=60)
        log=(result.stdout+result.stderr).decode(errors='replace')
        if language=='fr' and result.returncode:
            assert 'Voix fr absente' in log,log
        else:
            assert result.returncode==0,log
            data,sr=sf.read(wave);assert len(data)>sr*.2 and np.max(abs(data))>.01
            assert ('['+language+'-') in log,log
            # A valid installed OneCore voice must not silently fail into SAPI.
            assert 'OneCore unavailable:' not in log,log


def test_setlist_keeps_working_after_a_listed_song_is_deleted(tmp_path):
    root=tmp_path/'Songs';root.mkdir();kept=root/'kept.bandstudio';gone=root/'gone.bandstudio'
    p=fixture(kept);fixture(gone);api=Api(ENGINE,root)
    paths=[x['path'] for x in api._list()];assert len(paths)==2
    assert api.command(dict(command='setlist',args={'name':'Concert','paths':paths},projectID=api._project['id']))['ok']
    assert api.command(dict(command='deleteProject',args={'path':str(gone)}))['ok']
    item=api._setlists[0]
    assert api.command(dict(command='setlist',args={**item,'name':'Concert samedi'},projectID=api._project['id']))['ok']
    assert api._setlists==[dict(id=item['id'],name='Concert samedi',paths=[str(kept.resolve())])]
    assert not api.command(dict(command='setlist',args={**item,'name':' '},projectID=api._project['id']))['ok']


@pytest.mark.parametrize('name',['Kyo - Mon époque (Chap. II) [BsBRDkd5z7U]', 'Autre titre', 'Été [mix]'])
@pytest.mark.parametrize('active',[True,False])
def test_locked_song_removal_is_selective_persistent_and_restorable(tmp_path,monkeypatch,name,active):
    import catalog
    song=tmp_path/(name+'.bandstudio');p=fixture(song)
    other=tmp_path/'Conserver.bandstudio';other_project=fixture(other)
    original={f.relative_to(song):f.read_bytes() for f in song.rglob('*') if f.is_file()}
    rename=Path.rename
    def locked(path,target):
        if path==song:raise PermissionError(13,'Windows refuses an open directory')
        return rename(path,target)
    monkeypatch.setattr(Path,'rename',locked)
    api=Api(ENGINE,tmp_path);api._root=song if active else other;api._project=p if active else other_project
    api._audio.load(api._project,api._root)
    assert api.command(dict(command='deleteProject',args={'path':str(song)}))['ok']
    assert api._root==(None if active else other)
    assert [e['path'] for e in api._list()]==[str(other)]
    assert catalog.trashed(tmp_path)==[song]
    assert original=={f.relative_to(song):f.read_bytes() for f in song.rglob('*') if f.is_file()}
    restarted=Api(ENGINE,tmp_path)
    assert [e['path'] for e in restarted._list()]==[str(other)]
    with pytest.raises(ValueError,match='corbeille'):restarted._load(song,prepare_guides=False)
    catalog.remove(tmp_path,song)
    assert len(catalog.trash_records(tmp_path))==1
    assert restarted.command(dict(command='restoreProject'))['ok']
    assert len(restarted._list())==2 and catalog.trashed(tmp_path)==[]
    assert model.load(song)['id']==p['id']
    assert model.load(other)['id']==other_project['id']
    api._audio.close()


def test_trash_receipt_never_hides_a_replacement_project(tmp_path,monkeypatch):
    import catalog
    song=tmp_path/'Reused.bandstudio';fixture(song)
    def locked(*args):raise PermissionError('locked')
    monkeypatch.setattr(Path,'rename',locked);catalog.remove(tmp_path,song)
    assert catalog.entries(tmp_path)==[]
    replacement=fixture(song)
    assert len(catalog.entries(tmp_path))==1
    assert model.load(song)['id']==replacement['id'] and not catalog.trashed(tmp_path)


def test_trash_receipt_failure_leaves_the_project_visible(tmp_path,monkeypatch):
    import catalog,services
    song=tmp_path/'Keep.bandstudio';fixture(song)
    def no_write(*args):raise PermissionError('library is read only')
    monkeypatch.setattr(services,'atomic',no_write)
    with pytest.raises(PermissionError):catalog.remove(tmp_path,song)
    assert len(catalog.entries(tmp_path))==1 and not catalog.trashed(tmp_path)
    assert (song/'Audio/source.wav').is_file()


def test_mixed_physical_and_pending_trash_restore_in_order(tmp_path,monkeypatch):
    import catalog
    first=tmp_path/'First.bandstudio';fixture(first);catalog.remove(tmp_path,first)
    second=tmp_path/'Second.bandstudio';fixture(second)
    rename=Path.rename
    def locked(path,target):
        if path==second:raise PermissionError('locked')
        return rename(path,target)
    monkeypatch.setattr(Path,'rename',locked);catalog.remove(tmp_path,second)
    assert catalog.trashed(tmp_path)[0]==second
    assert Path(catalog.restore(tmp_path))==second
    assert Path(catalog.restore(tmp_path))==first
    assert not catalog.trashed(tmp_path) and len(catalog.entries(tmp_path))==2


@pytest.mark.parametrize('name',['../Outside.bandstudio','..\\Outside.bandstudio','/Outside.bandstudio'])
def test_trash_receipts_cannot_target_outside_the_library(tmp_path,name):
    import catalog
    root=tmp_path/'Songs';root.mkdir();outside=tmp_path/'Outside.bandstudio';p=fixture(outside)
    receipt=root/'.Trash'/'entry';receipt.mkdir(parents=True)
    (receipt/'removal.json').write_text(json.dumps(dict(name=name,projectID=p['id'])))
    assert not catalog.trashed(root)
    assert (outside/'Audio/source.wav').is_file()


def test_audio_releases_mappings_on_reload_close_and_partial_load_failure(tmp_path,monkeypatch):
    from windows import audio
    p=fixture(tmp_path);a=Audio(ENGINE);a.load(p,tmp_path)
    old=[x._mmap for x in a.data.values()]
    a.load(p,tmp_path)
    assert all(x.closed for x in old)
    current=[x._mmap for x in a.data.values()];opened=[];read=audio.pcm
    def failing(path):
        if opened:raise OSError('unreadable second track')
        data=read(path);opened.append(data._mmap);return data
    monkeypatch.setattr(audio,'pcm',failing)
    with pytest.raises(OSError):a.prepare()
    assert not a.data and all(x.closed for x in current+opened)
    monkeypatch.setattr(audio,'pcm',read);a.load(p,tmp_path)
    current=[x._mmap for x in a.data.values()];a.close();a.close()
    assert not a.data and all(x.closed for x in current)


@pytest.mark.skipif(os.name!='nt',reason='Real Windows handle sharing semantics')
def test_windows_external_audio_handle_cannot_block_library_removal(tmp_path):
    import catalog,ctypes
    from ctypes import wintypes
    song=tmp_path/'Locked elsewhere.bandstudio';p=fixture(song)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
    kernel.CreateFileW.restype=wintypes.HANDLE
    kernel.CloseHandle.argtypes=[wintypes.HANDLE];kernel.CloseHandle.restype=wintypes.BOOL
    # Allow reading/writing, but no FILE_SHARE_DELETE: just like another DAW.
    handle=kernel.CreateFileW(str(song/'Audio/source.wav'),0x80000000,3,None,3,0,None)
    assert handle!=wintypes.HANDLE(-1).value,ctypes.get_last_error()
    try:
        with pytest.raises(PermissionError):song.rename(tmp_path/'blocked.bandstudio')
        catalog.remove(tmp_path,song)
        assert not catalog.entries(tmp_path) and catalog.trashed(tmp_path)==[song]
        assert Path(catalog.restore(tmp_path))==song and model.load(song)['id']==p['id']
    finally:kernel.CloseHandle(handle)
