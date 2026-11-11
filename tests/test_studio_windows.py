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
    assert api._plan()==['key','guides']


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
