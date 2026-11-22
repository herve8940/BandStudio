"""Public chord references with local, explicitly provisional grid alignment.

Only artist/title leave the computer. Read chord names from a matching public
chart; the complete arrangement remains on the publisher's page. A failed
lookup is explicit and never falls back to the former audio model.
"""
import copy
import codecs
import json
from html.parser import HTMLParser
from pathlib import Path
from queue import Queue, Empty
import re
import threading
import time
import unicodedata
from urllib.parse import urlsplit, urlencode, urljoin, parse_qs, quote
from urllib.error import HTTPError
from urllib.request import Request, HTTPRedirectHandler, build_opener

from chord_provider_defaults import PROVIDERS
CATALOG_VERSION = 9
NETWORK_BUDGET = 14.
CACHE_RETRY_SECONDS = 300.
HOSTS = {host for p in PROVIDERS if p.get('template') for host in (p['domain'],'www.'+p['domain'])} | {'www.cifraclub.com.br','cifraclub.com.br'}
MAX_BYTES = 1_500_000
SEARCH_ENDPOINT = 'https://html.duckduckgo.com/html/'
MAX_DISCOVERED_URLS = 3
MAX_CATALOG_BYTES = 8_000_000
_network = threading.local()
# Verified publisher spelling, not a change to the artist's musical identity.
ARTIST_SLUGS = {'cifraclub': {'noir desir': 'desir-noir'}}
CHORD = re.compile(r'^[A-G](?:#|b)?(?:m|maj|min|dim|aug|sus|add|M|\d|[b#()+\-°])*' r'(?:/[A-G](?:#|b)?)?$')


def normalized(value):
    text = unicodedata.normalize('NFKD', str(value).casefold())
    return ' '.join(''.join(c if c.isalnum() else ' ' for c in text if not unicodedata.combining(c)).split())


# Download tools and rips decorate file names: "Full_Oasis - Wonderwall (128kbit_AAC)",
# "01_The_Cranberries_-_Zombie (Official Music Video)". Sites only know "Oasis" / "Wonderwall".
NAME_TAG = re.compile(r'\s*[\[(](?:'
    r'official(?: (?:music|lyrics?|hd|4k))? (?:video|audio|clip)|(?:music |lyrics? )?video|lyrics?|visuali[sz]er|audio'
    r'|clip officiel|audio officiel|vid[ée]o officielle|video oficial|paroles?'
    r'|(?:\d{4} )?remaster(?:ed)?(?: (?:version|\d{4}))?|(?:hd|hq|4k)(?: video| audio)?'
    r'|[^\])\n]*\b(?:official|officiel(?:le)?|oficial|remaster(?:ed)?|kbit|kbps)\b[^\])\n]*'
    r'|\d{2,3} ?k(?:bit|bps)?s?(?:[ _-]?(?:aac|mp3|opus|ogg|m4a|vorbis|webm))?|aac|mp3|opus|m4a'
    r')[\])]', re.I)
NAME_PREFIX = re.compile(r'^(?:(?:full|mix|master|stereo|original)_+|\d{1,3}(?:[_.]+|\s+-\s+))', re.I)


def clean_name(value):
    text = re.sub(r'\s*\[[A-Za-z0-9_-]{11}\]\s*$', '', str(value))
    text = NAME_PREFIX.sub('', text.strip()).replace('_', ' ')
    previous = None
    while previous != text:previous, text = text, NAME_TAG.sub('', text)
    return ' '.join(text.split())[:200]


def section_kind(value):
    label=re.sub(r'\s+\d+$','',normalized(value))
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
    name = clean_name(project.get('name', ''))
    if title and artist:
        parts=re.split(r'\s+[-–—|]\s+',title,maxsplit=1)
        if len(parts)==2:
            if normalized(parts[0])==normalized(artist):title=parts[1]
            elif normalized(parts[1])==normalized(artist):title=parts[0]
            elif not meta.get('source') and normalized(title)==normalized(name):
                # Video tags can put the uploader in artist and the complete
                # "Artist - Title" filename in title. Require both independent
                # fields to agree; retain curated album identities and covers.
                return parts[1],parts[0]
        return title, artist
    parts = re.split(r'\s+[-–—|]\s+', name, maxsplit=1)
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
    if provider['id']=='ukuleletabs':
        return provider['template'].format(artist=quote(artist.replace(' ','+'),safe=''))
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
    artist_slug = ARTIST_SLUGS.get(provider['id'], {}).get(normalized(artist), slug(artist))
    return provider['template'].format(artist=artist_slug,title=slug(title))


def matches_heading(heading,title,artist):
    """Compare complete title/artist fields, never an artist-name substring."""
    fields=re.split(r'\s+(?:[-–—|]|by|por|par)\s+',heading,flags=re.I)
    cleaned=[]
    for field in fields:
        field=re.sub(r'\s*[\[(](?:acordes|chords|cifras?|tabs?|tablatura)[\])]','',field,flags=re.I)
        field=re.split(r':\s*(?:acordes|chords|cifras)\b',field,flags=re.I)[0]
        field=re.sub(r'\s+(?:uke tab|chords|tabs|acordes|cifras)(?:\s+and\s+tabs)?\s*$','',field,flags=re.I)
        cleaned.append(clean_name(field))
    def title_key(value):return normalized(re.sub(r"['’`′]",'',value))
    def artist_key(value):return re.sub(r'^the\s+','',normalized(value.replace('/','').replace('⧸','').replace('.','')))
    return any(title_key(f)==title_key(title) for f in cleaned) and any(artist_key(f)==artist_key(artist) for f in cleaned)


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


def request_timeout():
    remaining = getattr(_network, 'deadline', float('inf')) - time.monotonic()
    if remaining <= 0:raise TimeoutError('Délai de recherche des grilles dépassé.')
    return min(4., remaining)


def fetch(url):
    if not safe_url(url):raise ValueError('Adresse de grille invalide.')
    request = Request(url, headers={'User-Agent':'BandStudio/1.1 (chord reference reader)', 'Accept':'text/html'})
    with build_opener(Redirects()).open(request, timeout=request_timeout()) as response:
        if response.status != 200 or not safe_url(response.url) or not same_publisher(url,response.url):raise ValueError('Grille indisponible.')
        data = response.read(MAX_BYTES+1)
        if len(data)>MAX_BYTES:raise ValueError('Page de grille trop volumineuse.')
        return data.decode('utf-8', errors='replace'), response.url


class SearchRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not search_address(newurl):raise ValueError('Redirection de recherche refusée.')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def search_address(url):
    try:
        p = urlsplit(url)
        return (p.scheme == 'https' and p.hostname == 'html.duckduckgo.com'
                and not p.username and not p.password and p.port in (None,443)
                and p.path.rstrip('/') == '/html')
    except ValueError:return False


def fetch_discovery(query):
    """Public non-JavaScript search; send only the song identity and publisher."""
    request = Request(SEARCH_ENDPOINT+'?'+urlencode({'q':query}),
                      headers={'User-Agent':'BandStudio/1.1 (chord reference reader)', 'Accept':'text/html'})
    with build_opener(SearchRedirects()).open(request, timeout=request_timeout()) as response:
        if response.status != 200 or not search_address(response.url):
            raise ValueError('Recherche de grilles indisponible.')
        data = response.read(MAX_BYTES+1)
        if len(data)>MAX_BYTES:raise ValueError('Réponse de recherche trop volumineuse.')
        return data.decode('utf-8', errors='replace')


class SearchLinks(HTMLParser):
    """Search results supply addresses only; never trust their chord snippets."""
    def __init__(self, provider):
        super().__init__();self.provider=provider;self.urls=[];self.recognized=False

    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs);classes=(attrs.get('class') or '').split()
        if 'no-results' in classes:self.recognized=True
        if tag!='a' or 'result__a' not in classes:return
        self.recognized=True
        try:
            url=urljoin(SEARCH_ENDPOINT,attrs.get('href') or '')
            parsed=urlsplit(url)
            if parsed.hostname in ('duckduckgo.com','www.duckduckgo.com','html.duckduckgo.com') and parsed.path=='/l/':
                url=parse_qs(parsed.query).get('uddg',[''])[0]
            if not safe_url(url) or not same_publisher(url,'https://'+self.provider['domain']):return
            url=urlsplit(url)._replace(fragment='').geturl()
        except ValueError:return
        if url not in self.urls and len(self.urls)<MAX_DISCOVERED_URLS:self.urls.append(url)


def discover_urls(provider,title,artist):
    # A publisher can use a legacy, reordered or entirely different artist slug.
    # Resolve the actual address instead of trying permutations of the name.
    query='site:'+provider['domain']+' '+ ' '.join('"'+value.replace('"','')+'"' for value in (artist,title))
    results=SearchLinks(provider);results.feed(fetch_discovery(query))
    if not results.recognized:raise ValueError('Le moteur de recherche n’a pas fourni de résultats lisibles.')
    return results.urls


class ArtistLinks(HTMLParser):
    """Read exact display names from the publisher's alphabetical artist index."""
    def __init__(self,base,artist):
        super().__init__();self.base=base;self.artist=normalized(artist);self.urls=[];self.anchor=None

    def handle_starttag(self,tag,attrs):
        if tag=='a':self.anchor=[dict(attrs).get('href') or '',[]]

    def handle_data(self,text):
        if self.anchor is not None:self.anchor[1].append(text)

    def handle_endtag(self,tag):
        if tag!='a' or self.anchor is None:return
        href,text=self.anchor;self.anchor=None
        if normalized(''.join(text))!=self.artist:return
        try:
            url=urljoin(self.base,href);parts=urlsplit(url)
            if (safe_url(url) and same_publisher(self.base,url) and not parts.query
                    and len(parts.path.strip('/').split('/'))==1 and parts.path.strip('/')):
                url=parts._replace(fragment='').geturl().rstrip('/')+'/'
                if url not in self.urls:self.urls.append(url)
        except ValueError:pass


def catalog_urls(provider,title,artist):
    if provider['id']!='cifraclub':return []
    name=normalized(artist)
    # Cifra Club sorts names such as "The …" and "Os …" without their article.
    without_article=re.sub(r'^(?:the|os|as|o|a|les|le|la|los|las)\s+','',name)
    initials=list(dict.fromkeys(value[:1].upper() for value in (without_article,name)))
    for initial in initials:
        if not re.fullmatch('[A-Z]',initial):continue
        url='https://www.cifraclub.com/letra/'+initial+'/lista/'
        parser=ArtistLinks(url,artist)
        request=Request(url,headers={'User-Agent':'BandStudio/1.1 (chord reference reader)', 'Accept':'text/html'})
        with build_opener(Redirects()).open(request,timeout=request_timeout()) as response:
            if response.status!=200 or not safe_url(response.url) or not same_publisher(url,response.url):
                raise ValueError('Catalogue d’artistes indisponible.')
            # These indexes can exceed a normal chart's size. Stream them and
            # stop at the matching name; never retain the whole directory.
            decoder=codecs.getincrementaldecoder('utf-8')('replace');size=0
            while size<MAX_CATALOG_BYTES:
                request_timeout()
                chunk=response.read(min(32_768,MAX_CATALOG_BYTES-size))
                if not chunk:break
                size+=len(chunk);parser.feed(decoder.decode(chunk))
                if parser.urls:
                    song_slug=urlsplit(provider_url(provider,title,artist)).path.strip('/').split('/')[-1]
                    return [base+song_slug+'/' for base in parser.urls[:MAX_DISCOVERED_URLS]]
    return []


class Chart(HTMLParser):
    def __init__(self,provider='cifraclub'):
        super().__init__();self.provider=provider;self.title='';self.chords=[];self.transitions=[];self.sections={};self.section=None;self.previous=None;self.stack=[];self.capo=0
        self.sectionSequences=[];self.sequence=None;self.sectionOrder=[];self.chordSequence=[];self.hasTab=False
    def heading(self,kind,name=None):
        self.section=kind;self.sections.setdefault(kind,[])
        if len(self.sectionOrder)<128:self.sectionOrder.append((name or kind).strip()[:70])
        self.sequence=dict(kind=kind,chords=[],repeat=1)
        if len(self.sectionSequences)<128:self.sectionSequences.append(self.sequence)
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if self.provider=='khmerchords' and attrs.get('id')=='lc-content':
            capo=attrs.get('data-capo','')
            if capo.isdigit():self.capo=min(12,int(capo))
        if tag not in ('br','hr','meta','link','img','input','source','wbr'):self.stack.append((tag,attrs))
    def handle_endtag(self,tag):
        for i in range(len(self.stack)-1,-1,-1):
            if self.stack[i][0]==tag:self.stack=self.stack[:i];break
    def handle_data(self,text):
        if any(tag=='title' for tag,_ in self.stack):self.title+=text
        token=text.strip()
        if not self.stack:return
        tag,attrs=self.stack[-1]
        in_pre=any(t=='pre' for t,_ in self.stack)
        in_chart=in_pre or (self.provider=='chordsworld' and any('chord-short-code-wrap' in a.get('class','').split() for _,a in self.stack)) or (self.provider=='khmerchords' and any(a.get('id')=='lc-content' for _,a in self.stack)) or (self.provider=='chordsandtabs' and any(t=='div' and 'song' in a.get('class','').split() for t,a in self.stack))
        in_chord=in_chart and ((self.provider=='cifraclub' and tag=='b') or
            (self.provider in ('echords','explorer') and tag=='span' and 'data-chord' in attrs) or
            (self.provider=='acordesweb' and tag=='a' and any(t=='pre' and a.get('id')=='chordsPre' for t,a in self.stack)) or
            (self.provider=='chordsworld' and tag=='c-2') or
            (self.provider=='khmerchords' and tag=='span' and 'c' in attrs.get('class','').split()) or
            (self.provider=='ukuleletabs' and tag=='a' and 'chord' in attrs.get('class','').split()) or
            (self.provider=='chordsandtabs' and tag=='sup'))
        if self.provider=='chordsworld' and 'capo--Value' in attrs.get('class','').split() and token.isdigit():self.capo=min(12,int(token))
        if in_chart and tag=='music-part':
            kind=section_kind(re.sub(r'\s+\d+$','',token))
            if kind:self.heading(kind,token)
            else:self.sequence=None;self.section=None
        if in_chart and not in_chord:
            if re.search(r'(?:^|\n)\s*[eEBGDA]\|[-0-9]',text):self.hasTab=True
            for heading in re.findall(r'\[([^\]\n]{1,70})\]',text):
                kind=section_kind(heading)
                if kind:self.heading(kind,heading)
                else:self.sequence=None;self.section=None
            repeat=re.fullmatch(r'\s*\(?\s*(?:[x×]\s*(\d{1,2})|(\d{1,2})\s*[x×])\s*\)?\s*',text,re.I)
            if repeat and self.sequence and self.sequence['chords']:
                self.sequence['repeat']=min(16,max(1,int(repeat[1] or repeat[2])))
        if in_chord and len(token)<=24 and CHORD.fullmatch(token):
            if len(self.chordSequence)<512:self.chordSequence.append(token)
            if token not in self.chords and len(self.chords)<60:self.chords.append(token)
            if self.sequence is not None and len(self.sequence['chords'])<256:self.sequence['chords'].append(token)
            if self.section and token not in self.sections[self.section] and token in self.chords:self.sections[self.section].append(token)
            pair=[self.previous,token]
            if self.previous and token!=self.previous and pair not in self.transitions and len(self.transitions)<360:
                self.transitions.append(pair)
            self.previous=token


class SongLinks(HTMLParser):
    """Resolve numbered Ukulele Tabs pages from their public artist index."""
    def __init__(self,base,title):
        super().__init__();self.base=base;self.title=normalized(title);self.anchor=None;self.urls=[]
    def handle_starttag(self,tag,attrs):
        if tag=='a':self.anchor=[dict(attrs).get('href',''),[]]
    def handle_data(self,text):
        if self.anchor is not None:self.anchor[1].append(text)
    def handle_endtag(self,tag):
        if tag!='a' or self.anchor is None:return
        href,text=self.anchor;self.anchor=None
        url=urljoin(self.base,href)
        if (normalized(''.join(text))==self.title and safe_url(url) and same_publisher(self.base,url)
                and re.search(r'-uke-tab-\d+\.html$',urlsplit(url).path)
                and url not in self.urls and len(self.urls)<MAX_DISCOVERED_URLS):self.urls.append(url)


def _read_chart(provider,title,artist,url):
    status='not_found';source=None
    try:
        if not safe_url(url) or not same_publisher(url,'https://'+provider['domain']):
            raise ValueError('Adresse de grille invalide.')
        page,url=fetch(url)
        if not safe_url(url) or not same_publisher(url,'https://'+provider['domain']):
            raise ValueError('Adresse de grille invalide.')
        chart=Chart(provider['id']);chart.feed(page)
        if provider['id']=='ukuleletabs' and urlsplit(url).path.endswith('-uke-tabs.html') and not chart.chords:
            links=SongLinks(url,title);links.feed(page)
            for candidate in links.urls:
                request_timeout()
                result=_read_chart(provider,title,artist,candidate)
                if result[1]!='not_found':return result
            return provider['id'],'not_found',None
        from chart_sections import extract as section_anchors,SCHEMA as ANCHOR_SCHEMA
        if matches_heading(chart.title,title,artist) and chart.chords:
            source=dict(title=title+' — '+artist,publisher=provider['publisher'],url=url,chords=chart.chords,transitions=chart.transitions,sections=chart.sections,
                        sectionSequences=[s for s in chart.sectionSequences if s['chords']],sectionOrder=chart.sectionOrder,
                        sectionAnchors=section_anchors(page),anchorSchema=ANCHOR_SCHEMA,
                        chordSequence=chart.chordSequence if not chart.sectionOrder and not chart.hasTab else [])
            from chord_choice import reputation
            source.update(reputation(page,title))
            if chart.capo:
                names=['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'];pcs=dict(C=0,D=2,E=4,F=5,G=7,A=9,B=11)
                def transpose(chord):return re.sub(r'(^|/)([A-G])([#b]?)',lambda m:m[1]+names[(pcs[m[2]]+{'':0,'#':1,'b':-1}[m[3]]+chart.capo)%12],chord)
                source['chords']=[transpose(c) for c in chart.chords]
                source['chordSequence']=[transpose(c) for c in source['chordSequence']]
                source['transitions']=[[transpose(c) for c in pair] for pair in chart.transitions]
                source['sections']={key:[transpose(c) for c in values] for key,values in chart.sections.items()}
                source['sectionSequences']=[{**s,'chords':[transpose(c) for c in s['chords']]} for s in source['sectionSequences']]
                source['note']=f'Grille écrite avec capo {chart.capo} : accords convertis en tonalité entendue.'
            status='found'
    except HTTPError as error:status='not_found' if error.code==404 else 'unavailable'
    except (OSError,ValueError):status='unavailable'
    return provider['id'],status,source


def _discover_provider(provider,title,artist):
    direct=provider_url(provider,title,artist)
    seen={direct}
    try:
        # Some publishers file "The …" under the name without its article.
        # Still validate both complete display fields on the resulting page.
        short=re.sub(r'^the\s+','',artist,flags=re.I)
        if short!=artist:
            alternate=provider_url(provider,title,short)
            if alternate not in seen:
                seen.add(alternate);request_timeout()
                result=_read_chart(provider,title,artist,alternate)
                if result[1]!='not_found':return result
        request_timeout()
        for url in catalog_urls(provider,title,artist):
            if url in seen:continue
            seen.add(url);request_timeout()
            result=_read_chart(provider,title,artist,url)
            if result[1]!='not_found':return result
        request_timeout()
        candidates=discover_urls(provider,title,artist)
    except (OSError,ValueError):return provider['id'],'unavailable',None
    for url in candidates:
        if url in seen:continue
        seen.add(url)
        try:request_timeout()
        except TimeoutError:return provider['id'],'unavailable',None
        result=_read_chart(provider,title,artist,url)
        if result[1]!='not_found':return result
    return provider['id'],'not_found',None


def _read_provider(provider,title,artist):
    result=_read_chart(provider,title,artist,provider_url(provider,title,artist))
    # A 403, rate limit or network error must not cause repeated publisher requests.
    return _discover_provider(provider,title,artist) if result[1]=='not_found' else result


def _search(title,artist,only=None):
    """At most three requests in flight, bounded total time, no model loading.

    Daemon readers only return immutable results. A slow site cannot hold up the
    worker on exit; late results never mutate the project or its selected chart.
    """
    pending=Queue();completed=Queue();deadline=time.monotonic()+NETWORK_BUDGET
    automatic=[p for p in PROVIDERS if p.get('template') and (only is None or p['id'] in only)]
    for provider in automatic:pending.put((provider,False))
    def read():
        _network.deadline=deadline
        while time.monotonic()<deadline:
            try:provider,discover=pending.get_nowait()
            except Empty:return
            if discover:
                result=_discover_provider(provider,title,artist)
            else:
                result=_read_chart(provider,title,artist,provider_url(provider,title,artist))
                # Give every publisher its direct attempt before spending the
                # remaining budget discovering alternatives for missing charts.
                if result[1]=='not_found':
                    pending.put((provider,True));continue
            completed.put(result)
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
    matching=previous and previous.get('query')==query and previous.get('status')=='found' and previous.get('catalogVersion')==CATALOG_VERSION
    retry=None
    if not reanalyze and matching:
        retry={c['id'] for c in previous.get('checks',[]) if c.get('status') in ('unavailable','not_found')}
        if not retry or time.time()-previous.get('checkedAt',0)<CACHE_RETRY_SECONDS:
            return dict(engine='web-reference',segments=[],reference=copy.deepcopy(previous),cacheHit=True)
    reference = dict(query=query,status='not_found',sources=[],checkedAt=time.time(),catalogVersion=CATALOG_VERSION,checks=[],
        message='Aucune grille correspondante trouvée. Recherche une autre source sur Internet ; aucun accord n’a été inventé.')
    if artist and title:
        results=_search(title,artist,only=retry)
        for provider in PROVIDERS:
            if not provider.get('template'):continue
            if retry is not None and provider['id'] not in retry:
                source=next((copy.deepcopy(s) for s in previous['sources'] if s['publisher']==provider['publisher']),None)
                status='found' if source else 'not_found'
            else:status,source=results.get(provider['id'],('unavailable',None))
            reference['checks'].append(dict(id=provider['id'],status=status))
            if source:reference['sources'].append(source)
        if reference['sources']:
            preferred=(previous or {}).get('selectedURL') or next(iter((previous or {}).get('sources',[])),{}).get('url')
            reference.update(status='found',selectedURL=next((s['url'] for s in reference['sources'] if s['url']==preferred),reference['sources'][0]['url']),
                selectionMode=(previous or {}).get('selectionMode','manual' if (previous or {}).get('selectedURL') else 'automatic'),
                message=f"{len(reference['sources'])} grille(s) trouvée(s). Les versions restent séparées ; choisis la source à caler.")
        elif any(c['status']=='unavailable' for c in reference['checks']):
            reference.update(status='unavailable',message='Aucune grille récupérée : certaines sources sont indisponibles. Tu peux ouvrir les recherches ciblées ou réessayer.')
    if reference['status']=='unavailable' and previous and previous.get('query')==query and previous.get('status')=='found':
        return dict(engine='web-reference',segments=[],reference=copy.deepcopy(previous),cacheHit=True,cachedAfterFailure=True)
    return dict(engine='web-reference',segments=[],reference=reference,cacheHit=False)


def apply(project, result):
    if result.get('engine')!='web-reference':raise ValueError('La détection audio des accords est désactivée. Recherche une grille Internet.')
    project['chordReference']=copy.deepcopy(result['reference'])
    if not result.get('segments'):return  # A failed lookup/alignment is not an instruction to erase music.
    from windows.project import ident,duration
    manual=[entry for entry in project.get('chords',[]) if entry.get('manual')]
    entries=[]
    for row in result.get('segments',[]):
        a,b=row['start'],min(row['end'],duration(project))
        if 0<=a<b and not any(c['start']<b and c['end']>a for c in manual):
            entries.append(dict(id=ident(),start=a,end=b,text=row['label'],manual=False,
                sourceURL=row['sourceURL'],confidence=row['confidence']))
    project['chords']=sorted(manual+entries,key=lambda x:x['start'])


def analyze(project,audio,*,reanalyze=False,source_url='',ordered=False,phrase_groups=None):
    result=lookup(project,reanalyze=reanalyze and not source_url)
    sources=result['reference']['sources']
    if source_url and not any(s['url']==source_url for s in sources):raise ValueError('Cette grille ne fait pas partie des sources trouvées pour le morceau.')
    if sources:
        if source_url:
            chosen=next(s for s in sources if s['url']==source_url)
            result['reference']['selectionMode']='manual';result['reference']['selectionReason']='Ta grille choisie est conservée.'
        else:
            from chord_choice import choose
            chosen,reason=choose({**project,'chordReference':result['reference']},sources)
            result['reference']['selectionReason']=reason
        result['reference']['selectedURL']=chosen['url']
        from advanced import media_path
        from chord_alignment import place
        offset=0
        if project.get('_root'):
            track=next((t for role in ('guitar','other','source') for t in project.get('tracks',[]) if t['role']==role),None)
            if track:
                audio=media_path(project['_root'],track['file']);offset=track.get('offset',0)
        arguments=(project,audio,chosen['chords'],chosen['url'],offset,chosen.get('transitions'),chosen.get('sections'))
        extra={'phrase_groups':phrase_groups} if phrase_groups else {}
        if chosen.get('chordSequence'):extra['written_chart']=chosen['chordSequence']
        result['segments'],alignment=place(*arguments,sequences=chosen.get('sectionSequences'),**extra) if ordered else place(*arguments)
        result['reference']['message']=f"{len(sources)} grille(s) trouvée(s) · source utilisée : {chosen['publisher']}. "+alignment['message']
        result['reference']['message']+=' '+result['reference']['selectionReason']
        if result.get('cachedAfterFailure'):result['reference']['message']='Internet indisponible : utilisation de la source déjà enregistrée. '+alignment['message']
        result['reference']['alignment']=alignment
    return result
