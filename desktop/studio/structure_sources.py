"""Small, attributed section references. No lyrics or complete scores are stored.

Timed maps, ordered chart headings and unordered section examples are distinct:
an untimed page is never interpreted as a timeline. Existing chart discovery
handles publisher-specific artist addresses and its bounded network budget.
"""
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.parse import urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener

import chord_sources
from services import atomic

MAX_BYTES = 800_000
MAX_ENTRIES = 128


def hook_address(url):
    try:
        p=urlsplit(url)
        return (p.scheme=='https' and p.hostname in ('www.hooktheory.com','hooktheory.com')
                and not p.username and not p.password and p.port in (None,443)
                and re.fullmatch(r'/theorytab/view/[a-z0-9-]+/[a-z0-9-]+/?',p.path) is not None
                and not p.query)
    except ValueError:return False


class HookRedirects(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        if not hook_address(newurl):raise ValueError('Adresse de référence refusée.')
        return super().redirect_request(req,fp,code,msg,headers,newurl)


class HookSections(HTMLParser):
    def __init__(self):
        super().__init__();self.title='';self.in_title=False;self.in_head=False;self.tab=None;self.names=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='head':self.in_head=True
        if tag=='title' and self.in_head:self.in_title=True
        if tag=='a' and 'tb-section-tab' in attrs.get('class','').split():
            self.tab='' if attrs.get('href','').startswith('#') and attrs['href']!='#' else None
    def handle_data(self,text):
        if self.in_title:self.title+=text
        if self.tab is not None:self.tab+=text
    def handle_endtag(self,tag):
        if tag=='title':self.in_title=False
        if tag=='head':self.in_head=False
        if tag=='a' and self.tab is not None:
            name=' '.join(self.tab.split());self.tab=None
            if 0<len(name)<=70 and name not in self.names and len(self.names)<MAX_ENTRIES:self.names.append(name)


def hook_lookup(project):
    title,artist=chord_sources.identity(project)
    check=dict(publisher='Hooktheory',status='unavailable',format='types')
    if not title or not artist:return None,{**check,'status':'identity_missing'}
    slug=lambda s:chord_sources.normalized(re.sub(r"['’`′]",'',s)).replace(' ','-')
    url='https://www.hooktheory.com/theorytab/view/'+slug(artist)+'/'+slug(title)
    check['url']=url
    key=hashlib.sha256((title+'\n'+artist).encode()).hexdigest()
    cache=Path(project['_root'])/'References'/('structure-hook-'+key+'.json')
    try:
        req=Request(url,headers={'User-Agent':'BandStudio/1.1 (structure reference reader)','Accept':'text/html'})
        with build_opener(HookRedirects()).open(req,timeout=6) as response:
            if response.status!=200 or not hook_address(response.url):raise ValueError('Page indisponible.')
            data=response.read(MAX_BYTES+1)
            if len(data)>MAX_BYTES:raise ValueError('Page trop volumineuse.')
            parser=HookSections();parser.feed(data.decode('utf-8',errors='replace'))
            heading=re.sub(r'\s+Chords,\s*Melody,\s*and\s*Music Theory Analysis\s*[-–—]\s*Hooktheory.*$','',parser.title,flags=re.I)
            if not chord_sources.matches_heading(heading,title,artist):raise ValueError('Morceau différent.')
            if not parser.names:return None,{**check,'status':'no_sections'}
            result=dict(title=title+' — '+artist,publisher='Hooktheory',url=response.url,
                        format='types',entries=parser.names,identity=[title,artist],retrievedAt=time.time())
            atomic(cache,result);return result,{**check,'status':'found'}
    except (OSError,ValueError):
        try:
            saved=json.loads(cache.read_text())
            if (saved['identity']==[title,artist] and saved['format']=='types' and saved['publisher']=='Hooktheory'
                    and saved['title']==title+' — '+artist and hook_address(saved['url']) and isinstance(saved['entries'],list)
                    and 0<len(saved['entries'])<=MAX_ENTRIES
                    and all(isinstance(s,str) and 0<len(s)<=70 for s in saved['entries'])):
                return saved,{**check,'status':'cached'}
        except (OSError,ValueError,KeyError,TypeError):pass
        return None,check


def chart_references(reference):
    """Old cached chord lists are examples, never a complete section order."""
    sources=[];checks=[]
    for source in (reference or {}).get('sources',[]):
        if not chord_sources.safe_url(source.get('url','')):continue
        names=source.get('sectionOrder')
        ordered=isinstance(names,list) and len(names)>=3 and all(isinstance(s,str) and 0<len(s)<=70 for s in names)
        if not isinstance(names,list):names=[]
        if not names:
            names=list(dict.fromkeys(s.get('kind','') for s in source.get('sectionSequences',[])))
            if not names:names=list(source.get('sections',{}))
        names=[s for s in (names or [])[:MAX_ENTRIES] if isinstance(s,str) and 0<len(s)<=70]
        shape='order' if ordered else 'types'
        checks.append(dict(publisher=source['publisher'],url=source['url'],format=shape,
                           status='found' if names else 'no_sections'))
        if names:sources.append({k:source[k] for k in ('title','publisher','url')}|dict(format=shape,entries=names))
    seen={c['publisher'] for c in checks}
    providers={p['id']:p for p in chord_sources.PROVIDERS}
    for check in (reference or {}).get('checks',[]):
        provider=providers.get(check.get('id'))
        if provider and provider['publisher'] not in seen:
            checks.append(dict(publisher=provider['publisher'],status=check['status'],format='order'))
    return sources,checks


def collect(project,timed_lookup):
    # Separate helpers read the immutable snapshot; their caches have distinct
    # names. Each reader has its own bounded timeout and byte budget.
    with ThreadPoolExecutor(max_workers=3) as pool:
        timed_job=pool.submit(timed_lookup,project)
        chord_job=pool.submit(chord_sources.lookup,project)
        hook_job=pool.submit(hook_lookup,project)
        timed,note=timed_job.result()
        chord_result=chord_job.result();chart=chord_result['reference']
        hook,hook_check=hook_job.result()
    sources,checks=chart_references(chart)
    if chord_result.get('cachedAfterFailure'):
        checks=[{**c,'status':'cached'} if c['status']=='found' else c for c in checks]
    if timed:sources.insert(0,{**timed,'format':'timed'})
    checks.insert(0,dict(publisher='DRUMY',status=('cached' if note else 'found') if timed else 'unavailable',format='timed',
                         **({'url':timed['url']} if timed else {})))
    if hook:sources.append(hook)
    checks.append(hook_check)
    return dict(timed=timed,note=note,chart=chart,sources=sources,checks=checks)
