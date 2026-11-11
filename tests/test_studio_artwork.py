"""Artwork matching, offline behavior and project isolation; no live API in CI."""
import json
from pathlib import Path
import sys
import threading
import subprocess
import time
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'desktop/studio'))
import artwork
import catalog

ALBUM='19181d75-deda-366e-ace5-622293be9ef0'
LIVE='11111111-2222-3333-4444-555555555555'


def response():
    return {'recordings':[{'title':'Dani California','score':100,'artist-credit':[{'name':'Red Hot Chili Peppers','artist':{'name':'Red Hot Chili Peppers','aliases':[{'name':'RHCP'}]}}],
        'releases':[{'title':'Live in Paris','status':'Official','release-group':{'id':LIVE,'primary-type':'Album','secondary-types':['Live']}},
                    {'title':'Stadium Arcadium','status':'Official','date':'2006-05-05','release-group':{'id':ALBUM,'primary-type':'Album'}}]}]}


def project(tmp_path,name='FULL_Dani California - RHCP'):
    p=tmp_path/'Song.bandstudio';p.mkdir();(p/'project.json').write_text(json.dumps({'name':name,'tracks':[],'notes':'Do not change'}));return p


def image_writer(library,p,engine,item,replace=False):
    (p/'Artwork.jpg').write_bytes(b'image');return True


def test_matching_prefers_studio_album_and_accepts_artist_alias(monkeypatch):
    monkeypatch.setattr(artwork,'fetch',lambda url:response())
    results=artwork.candidates('Dani California','RHCP')
    assert results[0]['id']==ALBUM and results[0]['automatic']
    assert results[1]['id']==LIVE and not results[1]['automatic']
    assert not any(c['automatic'] for c in artwork.candidates('Dani California',''))
    assert not any(c['automatic'] for c in artwork.candidates('Dani Californi','RHCP'))
    assert not any(c['automatic'] for c in artwork.candidates('Dani California','Another band'))


@pytest.mark.parametrize('name',['FULL_Dani California - RHCP','RHCP - Dani California'])
def test_existing_imports_try_both_filename_orders_and_keep_audio_project(tmp_path,monkeypatch,name):
    p=project(tmp_path,name);original=(p/'project.json').read_bytes();calls=[]
    def fetch(url):
        query=parse_qs(urlsplit(url).query)['query'][0];calls.append(query)
        return response() if 'recording:"Dani California"' in query else {'recordings':[]}
    monkeypatch.setattr(artwork,'fetch',fetch);monkeypatch.setattr(artwork,'save_image',image_writer)
    result=artwork.run(tmp_path,tmp_path,{'path':str(p)})
    assert result['message']=='Pochette enregistrée.'
    assert (p/'project.json').read_bytes()==original
    row=catalog.entries(tmp_path)[0];assert row['artist']=='Red Hot Chili Peppers' and row['album']=='Stadium Arcadium'
    assert row['artwork'].startswith('data:image/jpeg;base64,')
    assert 1<=len(calls)<=3
    # No network, even if explicitly retrying all missing covers.
    monkeypatch.setattr(artwork,'fetch',lambda *a:pytest.fail('Existing artwork must be retained'))
    artwork.run(tmp_path,tmp_path,{'path':str(p),'force':True})


def test_ambiguous_title_requires_explicit_choice_and_valid_cached_id(tmp_path,monkeypatch):
    p=project(tmp_path,'Dani California');monkeypatch.setattr(artwork,'fetch',lambda *a:response())
    monkeypatch.setattr(artwork,'save_image',image_writer)
    artwork.run(tmp_path,tmp_path,{'path':str(p)})
    assert not (p/'Artwork.jpg').exists()
    results=artwork.run(tmp_path,tmp_path,{'path':str(p),'action':'search','title':'Dani California','artist':'RHCP'})
    assert results['candidates'][0]['album']=='Stadium Arcadium'
    assert not (p/'Artwork.jpg').exists() # Manual search never silently changes the chosen album.
    artwork.run(tmp_path,tmp_path,{'path':str(p),'action':'apply','id':'../bad'})
    assert not (p/'Artwork.jpg').exists()
    artwork.run(tmp_path,tmp_path,{'path':str(p),'action':'apply','id':ALBUM})
    assert (p/'Artwork.jpg').exists()


def test_cache_offline_failure_and_explicit_retry(tmp_path,monkeypatch):
    p=project(tmp_path,'Dani California');calls=[]
    def unavailable(*a):calls.append(1);raise OSError('offline')
    monkeypatch.setattr(artwork,'fetch',unavailable)
    artwork.run(tmp_path,tmp_path,{'path':str(p)})
    assert artwork.read(p)['artworkStatus']=='offline' and len(calls)==1
    artwork.run(tmp_path,tmp_path,{'path':str(p)});assert len(calls)==1
    artwork.run(tmp_path,tmp_path,{'path':str(p),'force':True});assert len(calls)==2
    monkeypatch.setattr(artwork,'fetch',lambda *a:{'recordings':[]})
    artwork.run(tmp_path,tmp_path,{'path':str(p),'force':True})
    assert artwork.read(p)['artworkStatus']=='missing'
    monkeypatch.setattr(artwork,'fetch',lambda *a:pytest.fail('Empty result must be cached'))
    artwork.run(tmp_path,tmp_path,{'path':str(p)})


def test_metadata_tags_survive_decode_without_overwriting_project(tmp_path,monkeypatch):
    p=project(tmp_path);before=(p/'project.json').read_bytes()
    monkeypatch.setattr(artwork,'executable',lambda *a:Path('ffmpeg'))
    monkeypatch.setattr(artwork.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0,stdout=b';FFMETADATA1\ntitle=Dani California\nartist=RHCP\nalbum=Stadium Arcadium\n'))
    artwork.seed(p,'source.flac',tmp_path)
    assert artwork.read(p)['artist']=='RHCP'
    assert (p/'project.json').read_bytes()==before
    artwork.seed(p,'link.wav',tmp_path,{'title':'Other title','artist':'Other artist','audio':'not transmitted'})
    assert artwork.read(p)=={'title':'Other title','artist':'Other artist','album':'Stadium Arcadium'}


def test_request_limits_and_redirect_allowlist(monkeypatch):
    assert artwork.allowed('https://coverartarchive.org/release-group/'+ALBUM+'/front-500')
    assert artwork.allowed('https://ia800100.us.archive.org/image.jpg')
    for url in ['http://archive.org/x','https://archive.org.evil.test/x','https://127.0.0.1/x','file:///tmp/a','https://me@archive.org/x','https://archive.org:444/x']:
        assert not artwork.allowed(url)
    with pytest.raises(ValueError):artwork.Redirects().redirect_request(None,None,307,'',{},'http://localhost/audio')
    class Response:
        headers=SimpleNamespace(get_content_type=lambda:'image/jpeg')
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def read(self,n):return b'x'*n
    monkeypatch.setattr(artwork,'build_opener',lambda *a:SimpleNamespace(open=lambda *a,**k:Response()))
    monkeypatch.setattr(artwork.time,'sleep',lambda *a:None)
    with pytest.raises(ValueError,match='volumineuse'):artwork.fetch('https://coverartarchive.org/test',True)


def test_retry_is_bounded_and_respects_retry_after(monkeypatch):
    calls=[];sleeps=[]
    def unavailable(*a):calls.append(1);raise HTTPError('https://musicbrainz.org/',503,'busy',{'Retry-After':'3'},None)
    monkeypatch.setattr(artwork,'_fetch',unavailable);monkeypatch.setattr(artwork.time,'sleep',sleeps.append)
    with pytest.raises(HTTPError):artwork.fetch('https://musicbrainz.org/')
    assert len(calls)==2 and sleeps==[3]


def test_deleted_project_is_not_resurrected_by_pending_lookup(tmp_path,monkeypatch):
    p=project(tmp_path);monkeypatch.setattr(artwork,'fetch',lambda *a:response())
    def deleted(*a,**k):
        catalog.remove(tmp_path,p);raise OSError('moved')
    monkeypatch.setattr(artwork,'save_image',deleted)
    artwork.run(tmp_path,tmp_path,{'path':str(p)})
    assert not p.exists() and len(catalog.trashed(tmp_path))==1


def test_artist_alias_resolves_to_canonical_recording_query(monkeypatch):
    calls=[]
    def fetch(url):
        query=parse_qs(urlsplit(url).query)['query'][0];calls.append(query)
        if '/artist/' in url:return {'artists':[{'id':ALBUM,'name':'Red Hot Chili Peppers','aliases':[{'name':'RHCP'}]}]}
        return response() if 'artist:"Red Hot Chili Peppers"' in query else {'recordings':[]}
    monkeypatch.setattr(artwork,'fetch',fetch)
    assert artwork.candidates('Dani California','RHCP')[0]['automatic']
    assert len(calls)==3 and calls[1]=='"RHCP"'


def test_image_commit_checks_project_after_download(tmp_path,monkeypatch):
    p=project(tmp_path)
    def fetch(*a,**k):catalog.remove(tmp_path,p);return b'fake-download'
    def extract(source,dest,engine):(Path(dest)/'Artwork.jpg').write_bytes(b'converted');return True
    monkeypatch.setattr(artwork,'fetch',fetch);monkeypatch.setattr(catalog,'extract',extract)
    with pytest.raises(ValueError,match='bibliothèque'):artwork.save_image(tmp_path,p,tmp_path,{'id':ALBUM})
    assert not p.exists()


def test_helper_preserves_unicode_row_identifier(tmp_path):
    p=tmp_path/'Été répété.bandstudio';p.mkdir();(p/'project.json').write_text('{"name":"Example"}')
    artwork.write(p,dict(checkedAt=time.time(),artworkStatus='missing',artworkMessage='No image'))
    result=subprocess.run([sys.executable,str(ROOT/'desktop/studio/artwork.py'),str(tmp_path),str(tmp_path),json.dumps({'path':str(p)})],capture_output=True,text=True,check=True)
    assert json.loads(result.stdout)['entry']['path']==str(p)


def test_host_artwork_does_not_block_playback_or_analysis(tmp_path,monkeypatch):
    from windows.host import Api
    p=project(tmp_path);api=Api(tmp_path,tmp_path);api._busy=True
    entered=threading.Event();finish=threading.Event();done=threading.Event();sent=[]
    def run(*args):entered.set();assert finish.wait(3);return {'message':'ok'}
    def send(value):sent.append(value);done.set()
    monkeypatch.setattr(artwork,'run',run);api._send=send
    api._command({'command':'artwork','args':{'path':str(p)}})
    assert entered.wait(3) and api._busy and api._artwork_busy
    finish.set();assert done.wait(3)
    assert sent[0]['type']=='artworkResult' and sent[0]['entry']['path']==str(p)
    assert api._busy and not api._artwork_busy
