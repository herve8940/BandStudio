"""Optional MusicBrainz / Cover Art Archive lookup. Audio never leaves the computer.

Artwork.json is a portable sidecar: it cannot race with project/analysis saves.
Only exact title + artist matches are applied automatically; other results need
the musician's choice. Existing artwork is never replaced by a background scan.
"""
import json
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import time
import unicodedata
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener
import uuid

import catalog
from platform_tools import executable, creation_flags

USER_AGENT='BandStudio/1.1 (https://github.com/herve8940/BandStudio)'
_gate=threading.Lock()
_last_request=0.0


def allowed(url):
    p=urlsplit(url);host=p.hostname or ''
    return (p.scheme=='https' and not p.username and not p.password and p.port in (None,443)
            and (host in ('musicbrainz.org','coverartarchive.org','archive.org') or host.endswith('.archive.org')))


class Redirects(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        if not allowed(newurl):raise ValueError('Redirection de pochette non autorisée.')
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def _fetch(url,image=False):
    """Bound requests, downloads and redirects; identify the client and rate-limit."""
    global _last_request
    if not allowed(url):raise ValueError('Adresse de pochette non autorisée.')
    # This gate is shared by all requests in the Windows host. macOS serializes
    # one helper at a time, with an additional 1.1 s gap between helper launches.
    with _gate:
        time.sleep(max(0,1.1-(time.monotonic()-_last_request)))
        _last_request=time.monotonic()
        req=Request(url,headers={'User-Agent':USER_AGENT,'Accept':'image/*' if image else 'application/json'})
        with build_opener(Redirects()).open(req,timeout=10) as response:
            kind=response.headers.get_content_type()
            if image and kind not in ('image/jpeg','image/png','image/webp'):
                raise ValueError('Le service n’a pas renvoyé une image.')
            limit=2_000_000 if image else 1_500_000
            data=response.read(limit+1)
            if len(data)>limit:raise ValueError('Pochette ou réponse trop volumineuse.')
    return data if image else json.loads(data)


def fetch(url,image=False):
    for attempt in range(2):
        try:return _fetch(url,image)
        except HTTPError as error:
            if attempt or error.code not in (429,503):raise
            try:delay=max(2,float(error.headers.get('Retry-After','2')))
            except (ValueError,TypeError):raise error
            if delay>5:raise error
            time.sleep(delay)


def read(project):
    path=Path(project)/'Artwork.json'
    try:
        if path.is_symlink() or path.stat().st_size>128_000:return {}
        value=json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value,dict) else {}
    except (OSError,ValueError):return {}


def write(project,value):
    # Do not recreate a project removed while the network request was running.
    project=Path(project)
    if project.is_symlink() or not (project/'project.json').is_file():raise ValueError('Ce morceau a été déplacé.')
    temp=project/('artwork-'+uuid.uuid4().hex+'.json')
    try:
        temp.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
        temp.replace(project/'Artwork.json')
    finally:temp.unlink(missing_ok=True)


def clean(value):
    return ' '.join(str(value or '').replace('_',' ').split())[:200]


def normalized(value):
    value=unicodedata.normalize('NFKD',clean(value).casefold())
    return ' '.join(''.join(c if c.isalnum() else ' ' for c in value if not unicodedata.combining(c)).split())


def guesses(name):
    name=clean(name)
    name=re.sub(r'^(?:full\s+|\d{1,2}[.\s-]+)','',name,flags=re.I)
    name=re.sub(r'\s*[\[(](?:official (?:music )?(?:video|audio)|lyrics?|hd|hq)[\])]','',name,flags=re.I).strip()
    parts=re.split(r'\s+[-–—]\s+',name,maxsplit=1)
    # Both common filename conventions are supported, without assuming that
    # the right-hand part is always the title.
    if len(parts)==2:return [(parts[1],parts[0]),(parts[0],parts[1])]
    return [(name,'')]


def seed(project,source,engine,metadata=None):
    """Keep tags before decoding discards them. No internet access at import."""
    tags={}
    try:
        proc=subprocess.run([str(executable(engine,'ffmpeg')),'-nostdin','-hide_banner','-loglevel','error',
            '-protocol_whitelist','file,pipe,crypto,data','-i',str(source),'-map_metadata','0','-f','ffmetadata','-'],
            capture_output=True,timeout=10,creationflags=creation_flags())
        if not proc.returncode:
            for line in proc.stdout.decode('utf-8',errors='replace').splitlines():
                key,sep,value=line.partition('=')
                if sep and key.lower() in ('title','artist','album'):tags[key.lower()]=clean(value)
    except (OSError,subprocess.TimeoutExpired):pass
    tags.update({k:clean(v) for k,v in (metadata or {}).items() if k in ('title','artist','album') and v})
    if tags:write(project,tags)


def info(project,name=''):
    data=read(project);title,artist=guesses(name or Path(project).stem)[0]
    return {k:str(data.get(k) or default) for k,default in
            [('title',title),('artist',artist),('album',''),('artworkStatus',''),('artworkMessage','')]}


def phrase(value):
    return '"'+re.sub(r'([+\-!(){}\[\]^"~*?:\\/|&])',r'\\\1',value)+'"'


def artist_matches(query,credits):
    for credit in credits:
        artist=credit.get('artist',{})
        names=[credit.get('name',''),artist.get('name','')]+[a.get('name','') for a in artist.get('aliases',[])]
        for name in names:
            if normalized(query)==normalized(name):return True
            # Common initialisms (RHCP, ELO…) still need an exact song title.
            words=normalized(name).split()
            if len(words)>=3 and normalized(query)==''.join(w[0] for w in words):return True
    return False


def candidates(title,artist,album=''):
    query='recording:'+phrase(title)+' AND status:official'
    if artist:query+=' AND artist:'+phrase(artist)
    data=fetch('https://musicbrainz.org/ws/2/recording/?'+urlencode({'query':query,'fmt':'json','limit':20}))
    if not data.get('recordings') and artist:
        # The recording index does not search artist aliases (e.g. RHCP).
        # Resolve an exact alias in the artist index, then search by artist ID.
        artists=fetch('https://musicbrainz.org/ws/2/artist/?'+urlencode({'query':phrase(artist),'fmt':'json','limit':5}))
        ids=[];names=[]
        for item in artists.get('artists',[]):
            if artist_matches(artist,[{'artist':item}]):
                try:ids.append(str(uuid.UUID(item['id'])));names.append(clean(item['name']))
                except (ValueError,KeyError,TypeError,AttributeError):pass
        if ids:
            query='recording:'+phrase(title)+' AND status:official AND '+('artist:'+phrase(names[0]) if len(ids)==1 else '('+' OR '.join('arid:'+x for x in ids)+')')
            data=fetch('https://musicbrainz.org/ws/2/recording/?'+urlencode({'query':query,'fmt':'json','limit':20}))
    found={}
    for recording in data.get('recordings',[]):
        credits=recording.get('artist-credit',[])
        performer=''.join(c.get('name',c.get('artist',{}).get('name',''))+c.get('joinphrase','') for c in credits)
        exact=bool(artist and normalized(title)==normalized(recording.get('title','')) and artist_matches(artist,credits))
        for release in recording.get('releases',[]):
            group=release.get('release-group',{});ident=group.get('id')
            try:ident=str(uuid.UUID(ident))
            except (ValueError,TypeError,AttributeError):continue
            secondary=group.get('secondary-types',[])
            official=release.get('status')=='Official'
            primary=group.get('primary-type','')
            suitable=official and primary=='Album' and not secondary
            item=dict(id=ident,title=clean(recording.get('title')),artist=clean(performer),album=clean(release.get('title')),
                      date=clean(release.get('date')),exact=exact,automatic=exact and suitable,
                      rank=[int(exact),int(bool(album) and normalized(album)==normalized(release.get('title'))),
                            int(suitable),int(official),int(primary=='Album'),int(recording.get('score',0))])
            if ident not in found or item['rank']>found[ident]['rank']:found[ident]=item
    return sorted(found.values(),key=lambda x:([-v for v in x['rank']],x['date'] or '9999',x['album']))[:12]


def save_image(library,project,engine,item,replace=False):
    ident=str(uuid.UUID(item['id']))
    try:raw=fetch('https://coverartarchive.org/release-group/'+ident+'/front-500',image=True)
    except HTTPError as error:
        if error.code==404:return False
        raise
    with tempfile.TemporaryDirectory(prefix='bandstudio-artwork-') as folder:
        source=Path(folder)/'download';source.write_bytes(raw)
        if not catalog.extract(source,folder,engine):return False
        project=catalog.member(library,project)
        if catalog.cover(project) and not replace:return True
        # Write into the existing directory only. Moving/removing it during
        # lookup cannot resurrect it or leave a half-written Artwork.jpg.
        target=project/('artwork-'+uuid.uuid4().hex+'.jpg')
        try:
            target.write_bytes((Path(folder)/'Artwork.jpg').read_bytes())
            target.replace(project/'Artwork.jpg')
        finally:target.unlink(missing_ok=True)
    return True


def run(library,engine,args):
    project=catalog.member(library,args['path']);action=args.get('action','sync');data=read(project)
    if action not in ('sync','search','apply'):raise ValueError('Action de pochette inconnue.')
    if action=='sync' and catalog.cover(project):return dict(message='Pochette conservée.')
    if action=='sync' and not args.get('force'):
        delay=3600 if data.get('artworkStatus')=='offline' else 7*86400
        if time.time()-float(data.get('checkedAt',0))<delay:return dict(message=data.get('artworkMessage',''))
    try:
        if action=='apply':
            item=next((c for c in data.get('candidates',[]) if c['id']==args.get('id')),None)
            if not item:raise ValueError('Relance la recherche avant de choisir cet album.')
            choices=[item]
        else:
            name=json.loads((project/'project.json').read_text(encoding='utf-8')).get('name') or project.stem
            if action=='search':
                title,artist=clean(args.get('title')),clean(args.get('artist'))
                if not title:raise ValueError('Renseigne le titre du morceau.')
                data.update(title=title,artist=artist,album='')
                queries=[(title,artist)]
            else:queries=[(data.get('title') or name,data.get('artist',''))] if data.get('title') or data.get('artist') else guesses(name)
            choices=[];search_error=None
            for title,artist in queries:
                try:found=candidates(title,artist,data.get('album',''))
                except OSError as error:search_error=error;continue
                merged={c['id']:c for c in choices}
                for candidate in found:
                    if candidate['id'] not in merged or candidate['rank']>merged[candidate['id']]['rank']:
                        merged[candidate['id']]=candidate
                choices=list(merged.values())
                if any(c['exact'] for c in found):break
            if not choices and search_error:raise search_error
            choices=sorted(choices,key=lambda x:[-v for v in x['rank']])[:12]
            data.update(candidates=choices,checkedAt=time.time(),artworkStatus='choice' if choices else 'missing',
                        artworkMessage='Choisis un album ou précise le titre et l’artiste.' if choices else 'Aucune pochette trouvée. Vérifie le titre et l’artiste.')
        if action!='search':
            eligible=[c for c in choices if c['automatic']]
            # If the same query matches different performers, let the user choose.
            if len({normalized(c['artist']) for c in eligible})>1:eligible=[]
            for item in (choices if action=='apply' else eligible[:3]):
                if save_image(library,project,engine,item,replace=action=='apply'):
                    data.update(title=item['title'],artist=item['artist'],album=item['album'],
                                source='https://musicbrainz.org/release-group/'+item['id'],
                                artworkStatus='found',artworkMessage='Pochette enregistrée.');break
            else:
                if action=='apply':data.update(artworkStatus='missing',artworkMessage='Cet album n’a pas de pochette disponible. Essaie une autre édition.')
        catalog.member(library,project);write(project,data)
    except (OSError,ValueError,KeyError,TypeError) as error:
        import diagnostics
        diagnostics.event('artwork.lookup',kind=type(error).__name__,error=str(error)[:300])
        data.update(checkedAt=time.time(),artworkStatus='offline',artworkMessage='Recherche indisponible. Tu peux réessayer plus tard ou choisir une image.')
        # A concurrent delete is normal: never restore the old directory.
        try:catalog.member(library,project);write(project,data)
        except (OSError,ValueError):pass
    return dict(message=data.get('artworkMessage',''),candidates=data.get('candidates',[]) if action=='search' else [])


if __name__=='__main__':
    import sys
    library,engine,payload=sys.argv[1:4];args=json.loads(payload)
    try:
        result=run(library,engine,args)
        catalog.member(library,args['path'])
        # Preserve the caller's spelling (macOS may enumerate a different
        # Unicode normalization); it is also the UI's stable row identifier.
        result['entry']=catalog.entry(args['path'])
    except Exception:result={'message':'Ce morceau n’est plus disponible.'}
    print(json.dumps(result,ensure_ascii=True))
