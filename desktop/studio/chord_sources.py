"""Public chord references with local, explicitly provisional grid alignment.

Only artist/title leave the computer. Read chord names from a matching public
chart; the complete arrangement remains on the publisher's page. A failed
lookup is explicit and never falls back to the former audio model.
"""
import copy
import json
from html.parser import HTMLParser
from pathlib import Path
from queue import Queue, Empty
import re
import threading
import time
import unicodedata
from urllib.parse import urlsplit, urlencode
from urllib.error import HTTPError
from urllib.request import Request, HTTPRedirectHandler, build_opener

from chord_provider_defaults import PROVIDERS
CATALOG_VERSION = 2
NETWORK_BUDGET = 8.
HOSTS = {host for p in PROVIDERS if p.get('template') for host in (p['domain'],'www.'+p['domain'])} | {'www.cifraclub.com.br','cifraclub.com.br'}
MAX_BYTES = 1_500_000
CHORD = re.compile(r'^[A-G](?:#|b)?(?:m|maj|min|dim|aug|sus|add|M|\d|[b#()+\-°])*' r'(?:/[A-G](?:#|b)?)?$')


def normalized(value):
    text = unicodedata.normalize('NFKD', str(value).casefold())
    return ' '.join(''.join(c if c.isalnum() else ' ' for c in text if not unicodedata.combining(c)).split())


def clean_name(value):
    text = re.sub(r'\s*\[[A-Za-z0-9_-]{11}\]\s*$', '', str(value))
    text = re.sub(r'\s*[\[(](?:official (?:music )?(?:video|audio)|lyrics?|hd|hq)[\])]', '', text, flags=re.I)
    return ' '.join(text.split())[:200]


def section_kind(value):
    label=normalized(value)
    if 'pre' in label.split() and any(x in label for x in ('chorus','refrain','refrao','estribillo')):return 'prechorus'
    if label in ('intro','introduction'):return 'intro'
    if label in ('verse','couplet','primeira parte','segunda parte','terceira parte','primera parte','tercera parte'):return 'verse'
    if label in ('chorus','refrain','refrao','estribillo'):return 'chorus'
    if label in ('bridge','pont','ponte','puente'):return 'bridge'
    if label in ('solo','instrumental'):return 'instrumental'
    if label in ('outro','final','coda'):return 'outro'
    return None


def identity(project):
    from artwork import read
    meta = read(project['_root']) if project.get('_root') else {}
    title, artist = clean_name(meta.get('title', '')), clean_name(meta.get('artist', ''))
    if title and artist:
        parts=re.split(r'\s+[-–—]\s+',title,maxsplit=1)
        if len(parts)==2 and normalized(parts[0])==normalized(artist):title=parts[1]
        return title, artist
    name = clean_name(project.get('name', ''))
    parts = re.split(r'\s+[-–—]\s+', name, maxsplit=1)
    return (parts[1], parts[0]) if len(parts) == 2 else (name, '')


def safe_url(url):
    try:
        p = urlsplit(url)
        return p.scheme == 'https' and p.hostname in HOSTS and not p.username and not p.password and p.port in (None,443)
    except ValueError:return False


def public_catalog():
    return [{k:p[k] for k in ('id','publisher','domain')} | {'automatic':bool(p.get('template'))} for p in PROVIDERS]


def search_url(query,kind='chords',provider=''):
    site=''
    if provider:
        entry=next((p for p in PROVIDERS if p['id']==provider),None)
        if not entry:raise ValueError('Source de recherche inconnue.')
        site=' site:'+entry['domain']
    return 'https://www.google.com/search?'+urlencode({'q':query[:300]+(' chords accords' if kind=='chords' else ' lyrics paroles')+site})


def provider_url(provider,title,artist):
    if provider['id'] in ('echords','acordesweb'):artist=artist.replace('/','').replace('⧸','')
    # Most catalogs collapse initials; GuitarTabsExplorer retains their dots.
    if provider['id']!='explorer':artist=artist.replace('.','')
    def slug(value):
        value=re.sub(r"['’`′]",'',value)
        if provider['id']=='explorer':
            value=unicodedata.normalize('NFKD',value.casefold())
            value=''.join(c if c.isalnum() or c=='.' else '-' for c in value if not unicodedata.combining(c))
            return re.sub(r'-+','-',value.replace('..','-')).strip('-')
        return normalized(value).replace(' ','-')
    return provider['template'].format(artist=slug(artist),title=slug(title))


def matches_heading(heading,title,artist):
    """Compare complete title/artist fields, never an artist-name substring."""
    fields=re.split(r'\s+(?:[-–—|]|by|por|par)\s+',heading,flags=re.I)
    cleaned=[]
    for field in fields:
        field=re.sub(r'\s*[\[(](?:acordes|chords|cifras?|tabs?|tablatura)[\])]','',field,flags=re.I)
        field=re.split(r':\s*(?:acordes|chords|cifras)\b',field,flags=re.I)[0]
        field=re.sub(r'\s+(?:chords|tabs|acordes|cifras)(?:\s+and\s+tabs)?\s*$','',field,flags=re.I)
        cleaned.append(clean_name(field))
    def artist_key(value):return normalized(value.replace('/','').replace('⧸','').replace('.',''))
    return any(normalized(f)==normalized(title) for f in cleaned) and any(artist_key(f)==artist_key(artist) for f in cleaned)


class Redirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not safe_url(newurl) or not same_publisher(req.full_url,newurl):
            raise ValueError('Redirection de grille refusée.')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def same_publisher(a,b):
    def publisher(url):
        host=urlsplit(url).hostname or ''
        return host.removeprefix('www.').replace('cifraclub.com.br','cifraclub.com')
    return publisher(a)==publisher(b)


def fetch(url):
    if not safe_url(url):raise ValueError('Adresse de grille invalide.')
    request = Request(url, headers={'User-Agent':'BandStudio/1.1 (chord reference reader)', 'Accept':'text/html'})
    with build_opener(Redirects()).open(request, timeout=4) as response:
        if response.status != 200 or not safe_url(response.url) or not same_publisher(url,response.url):raise ValueError('Grille indisponible.')
        data = response.read(MAX_BYTES+1)
        if len(data)>MAX_BYTES:raise ValueError('Page de grille trop volumineuse.')
        return data.decode('utf-8', errors='replace'), response.url


class Chart(HTMLParser):
    def __init__(self,provider='cifraclub'):
        super().__init__();self.provider=provider;self.title='';self.chords=[];self.transitions=[];self.sections={};self.section=None;self.previous=None;self.stack=[];self.capo=0
    def handle_starttag(self,tag,attrs):
        if tag not in ('br','hr','meta','link','img','input','source','wbr'):self.stack.append((tag,dict(attrs)))
    def handle_endtag(self,tag):
        for i in range(len(self.stack)-1,-1,-1):
            if self.stack[i][0]==tag:self.stack=self.stack[:i];break
    def handle_data(self,text):
        if any(tag=='title' for tag,_ in self.stack):self.title+=text
        token=text.strip()
        if not self.stack:return
        tag,attrs=self.stack[-1]
        in_pre=any(t=='pre' for t,_ in self.stack)
        in_chart=in_pre or (self.provider=='chordsworld' and any('chord-short-code-wrap' in a.get('class','').split() for _,a in self.stack))
        in_chord=in_chart and ((self.provider=='cifraclub' and tag=='b') or
            (self.provider in ('echords','explorer') and tag=='span' and 'data-chord' in attrs) or
            (self.provider=='acordesweb' and tag=='a' and any(t=='pre' and a.get('id')=='chordsPre' for t,a in self.stack)) or
            (self.provider=='chordsworld' and tag=='c-2'))
        if self.provider=='chordsworld' and 'capo--Value' in attrs.get('class','').split() and token.isdigit():self.capo=min(12,int(token))
        if in_chart and tag=='music-part':
            kind=section_kind(re.sub(r'\s+\d+$','',token))
            if kind:self.section=kind;self.sections.setdefault(kind,[])
        if in_chart and not in_chord:
            for heading in re.findall(r'\[([^\]\n]{1,70})\]',text):
                kind=section_kind(heading)
                if kind:self.section=kind;self.sections.setdefault(kind,[])
        if in_chord and len(token)<=24 and CHORD.fullmatch(token):
            if token not in self.chords and len(self.chords)<60:self.chords.append(token)
            if self.section and token not in self.sections[self.section] and token in self.chords:self.sections[self.section].append(token)
            pair=[self.previous,token]
            if self.previous and token!=self.previous and pair not in self.transitions and len(self.transitions)<360:
                self.transitions.append(pair)
            self.previous=token


def _read_provider(provider,title,artist):
    status='not_found';source=None
    try:
        page,url=fetch(provider_url(provider,title,artist));chart=Chart(provider['id']);chart.feed(page)
        if matches_heading(chart.title,title,artist) and chart.chords:
            source=dict(title=title+' — '+artist,publisher=provider['publisher'],url=url,chords=chart.chords,transitions=chart.transitions,sections=chart.sections)
            if chart.capo:
                names=['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'];pcs=dict(C=0,D=2,E=4,F=5,G=7,A=9,B=11)
                def transpose(chord):return re.sub(r'(^|/)([A-G])([#b]?)',lambda m:m[1]+names[(pcs[m[2]]+{'':0,'#':1,'b':-1}[m[3]]+chart.capo)%12],chord)
                source['chords']=[transpose(c) for c in chart.chords]
                source['transitions']=[[transpose(c) for c in pair] for pair in chart.transitions]
                source['sections']={key:[transpose(c) for c in values] for key,values in chart.sections.items()}
                source['note']=f'Grille écrite avec capo {chart.capo} : accords convertis en tonalité entendue.'
            status='found'
    except HTTPError as error:status='not_found' if error.code==404 else 'unavailable'
    except (OSError,ValueError):status='unavailable'
    return provider['id'],status,source


def _search(title,artist):
    """At most three requests in flight, eight seconds total, no model loading.

    Daemon readers only return immutable results. A slow site cannot hold up the
    worker on exit; late results never mutate the project or its selected chart.
    """
    pending=Queue();completed=Queue();deadline=time.monotonic()+NETWORK_BUDGET
    automatic=[p for p in PROVIDERS if p.get('template')]
    for provider in automatic:pending.put(provider)
    def read():
        while time.monotonic()<deadline:
            try:provider=pending.get_nowait()
            except Empty:return
            completed.put(_read_provider(provider,title,artist))
    for _ in range(min(3,len(automatic))):threading.Thread(target=read,daemon=True).start()
    results={}
    from analysis_progress import emit
    while len(results)<len(automatic):
        remaining=deadline-time.monotonic()
        if remaining<=0:break
        try:identifier,status,source=completed.get(timeout=remaining)
        except Empty:break
        results[identifier]=(status,source)
        emit(progressLabel=f'Recherche de grilles · {len(results)} sources sur {len(automatic)}',indeterminate=True)
    return results


def lookup(project, *, reanalyze=False):
    title, artist = identity(project)
    query = ' '.join((artist,title)).strip()
    previous = project.get('chordReference')
    if not reanalyze and previous and previous.get('query')==query and previous.get('status')=='found' and previous.get('catalogVersion')==CATALOG_VERSION:
        return dict(engine='web-reference',segments=[],reference=copy.deepcopy(previous),cacheHit=True)
    reference = dict(query=query,status='not_found',sources=[],checkedAt=time.time(),catalogVersion=CATALOG_VERSION,checks=[],
        message='Aucune grille correspondante trouvée. Recherche une autre source sur Internet ; aucun accord n’a été inventé.')
    if artist and title:
        results=_search(title,artist)
        for provider in PROVIDERS:
            if not provider.get('template'):continue
            status,source=results.get(provider['id'],('unavailable',None))
            reference['checks'].append(dict(id=provider['id'],status=status))
            if source:reference['sources'].append(source)
        if reference['sources']:
            preferred=(previous or {}).get('selectedURL') or next(iter((previous or {}).get('sources',[])),{}).get('url')
            reference.update(status='found',selectedURL=next((s['url'] for s in reference['sources'] if s['url']==preferred),reference['sources'][0]['url']),
                message=f"{len(reference['sources'])} grille(s) trouvée(s). Les versions restent séparées ; choisis la source à caler.")
        elif any(c['status']=='unavailable' for c in reference['checks']):
            reference.update(status='unavailable',message='Aucune grille récupérée : certaines sources sont indisponibles. Tu peux ouvrir les recherches ciblées ou réessayer.')
    if reference['status']=='unavailable' and previous and previous.get('query')==query and previous.get('status')=='found':
        return dict(engine='web-reference',segments=[],reference=copy.deepcopy(previous),cacheHit=True,cachedAfterFailure=True)
    return dict(engine='web-reference',segments=[],reference=reference,cacheHit=False)


def apply(project, result):
    if result.get('engine')!='web-reference':raise ValueError('La détection audio des accords est désactivée. Recherche une grille Internet.')
    project['chordReference']=copy.deepcopy(result['reference'])
    from windows.project import ident,duration
    manual=[entry for entry in project.get('chords',[]) if entry.get('manual')]
    entries=[]
    for row in result.get('segments',[]):
        a,b=row['start'],min(row['end'],duration(project))
        if 0<=a<b and not any(c['start']<b and c['end']>a for c in manual):
            entries.append(dict(id=ident(),start=a,end=b,text=row['label'],manual=False,
                sourceURL=row['sourceURL'],confidence=row['confidence']))
    project['chords']=sorted(manual+entries,key=lambda x:x['start'])


def analyze(project,audio,*,reanalyze=False,source_url=''):
    result=lookup(project,reanalyze=reanalyze and not source_url)
    sources=result['reference']['sources']
    if source_url and not any(s['url']==source_url for s in sources):raise ValueError('Cette grille ne fait pas partie des sources trouvées pour le morceau.')
    if sources:
        chosen=next((s for s in sources if s['url']==(source_url or result['reference'].get('selectedURL'))),sources[0])
        result['reference']['selectedURL']=chosen['url']
        from advanced import media_path
        from chord_alignment import place
        offset=0
        if project.get('_root'):
            track=next((t for role in ('guitar','other','source') for t in project.get('tracks',[]) if t['role']==role),None)
            if track:
                audio=media_path(project['_root'],track['file']);offset=track.get('offset',0)
        result['segments'],alignment=place(project,audio,chosen['chords'],chosen['url'],offset,chosen.get('transitions'),chosen.get('sections'))
        result['reference']['message']=f"{len(sources)} grille(s) trouvée(s) · source utilisée : {chosen['publisher']}. "+alignment['message']
        if result.get('cachedAfterFailure'):result['reference']['message']='Internet indisponible : utilisation de la source déjà enregistrée. '+alignment['message']
        result['reference']['alignment']=alignment
    return result
