"""Account-free lyric references, checked against local vocals before correction.

Remote timestamps are never copied: different releases can have different edits.
Only title/artist leave the machine. Confirmed reference text replaces ASR guesses;
manual edits survive, while text confidence and timing confidence stay separate.
"""
from ui_language import ui_text, using_english
import copy
from difflib import SequenceMatcher
import hashlib
from html.parser import HTMLParser
import json
import math
from pathlib import Path
import re
import time
import unicodedata
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlsplit, urljoin, parse_qs
from urllib.request import Request, HTTPRedirectHandler, build_opener

from chord_sources import identity, normalized, chart_titles

WEB_SOURCES = {'Paroles.net': 'www.paroles.net', 'Paroles2Chansons': 'paroles2chansons.lemonde.fr'}
SEARCH_ENDPOINT = 'https://html.duckduckgo.com/html/'
HOSTS = {'lrclib.net', 'api.lyrics.ovh', 'html.duckduckgo.com', *WEB_SOURCES.values()}
MAX_BYTES = 1_000_000
MAX_WORDS = 1800
LOOKUP_VERSION = 3
NETWORK_BUDGET = 30.


def tokens(text):
    return re.findall(r"[^\W_]+(?:['’−-][^\W_]+)*", text, re.UNICODE)


def key(word):
    return normalized(word).replace(' ', '')


def safe_url(url):
    try:
        p = urlsplit(url)
        return (p.scheme == 'https' and p.hostname in HOSTS and not p.username and not p.password and p.port in (None, 443)
                and (p.hostname != 'html.duckduckgo.com' or p.path.rstrip('/') == '/html'))
    except ValueError:
        return False


class Redirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not safe_url(newurl) or urlsplit(req.full_url).hostname != urlsplit(newurl).hostname:
            raise ValueError(ui_text('Redirection de paroles refusée.', 'Lyrics redirect refused.'))
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url):
    if not safe_url(url):
        raise ValueError(ui_text('Source de paroles invalide.', 'Invalid lyrics source.'))
    html = urlsplit(url).hostname not in {'lrclib.net','api.lyrics.ovh'}
    request = Request(url, headers={'User-Agent': 'BandStudio/1.1 (https://github.com/herve8940/BandStudio)',
                                   'Accept': 'text/html' if html else 'application/json'})
    with build_opener(Redirects()).open(request, timeout=6) as response:
        if response.status != 200 or not safe_url(response.url):
            raise ValueError(ui_text('Source de paroles indisponible.', 'Lyrics source unavailable.'))
        data = response.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError(ui_text('Réponse de paroles trop volumineuse.', 'Lyrics response too large.'))
        return data.decode('utf-8') if html else json.loads(data)


def clean_text(value):
    if not isinstance(value, str) or len(value) > 50_000:
        return ''
    rows = []
    # Some community copies contain visually identical Cyrillic letters in
    # Latin words. They otherwise break word matching and French alignment.
    lookalikes = str.maketrans('аАеЕоОрРсСхХуУіІјЈ', 'aAeEoOpPcCxXyYiIjJ')
    for row in value.splitlines():
        row = re.sub(r'\[[^\]\n]*\]', '', row).strip()
        row = re.sub(r"[^\W_]+(?:['’−-][^\W_]+)*",lambda m:m[0].translate(lookalikes)
                     if re.search(r'[a-zA-ZÀ-ž]',m[0]) else m[0],row)
        if not row or re.match(r'^(Paroles de la chanson|Lyrics of|Lyrics for)\b', row, re.I):
            continue
        rows.append(row)
    return '\n'.join(rows)


class LyricsPage(HTMLParser):
    """Read only the publisher's lyric container; scripts/ads are never text."""
    VOID = {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
    OMIT = {'script','style','noscript','iframe','tonefuse','h2','button','aside','nav'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = dict(tag='', attrs={}, children=[])
        self.stack = [self.root]
        self.nodes = []

    def handle_starttag(self, tag, attrs):
        node = dict(tag=tag, attrs=dict(attrs), children=[])
        self.stack[-1]['children'].append(node)
        self.nodes.append(node)
        if tag not in self.VOID:self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, 0, -1):
            if self.stack[i]['tag'] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        self.stack[-1]['children'].append(data)

    def text(self, node):
        if isinstance(node, str):return node
        if node['tag'] in self.OMIT:return ''
        if node['tag'] == 'br':return '\n'
        value = ''.join(self.text(child) for child in node['children'])
        return value + ('\n' if node['tag'] in {'p','div'} else '')


def page_lyrics(payload, publisher, titles, artist):
    if not isinstance(payload, str) or len(payload) > MAX_BYTES:return ''
    page = LyricsPage()
    page.feed(payload)
    headings = {normalized(page.text(n)) for n in page.nodes if n['tag'] == 'h1'}
    expected = {normalized(f'Paroles de la chanson {title} par {artist}') if publisher == 'Paroles.net'
                else normalized(f'{artist} - {title} LYRICS') for title in titles}
    if not headings.intersection(expected):return ''
    candidates = []
    for node in page.nodes:
        classes = (node['attrs'].get('class') or '').split()
        if publisher == 'Paroles.net':
            if node['tag'] == 'article' and 'lyrics' in classes:
                blocks = [n for n in node['children'] if isinstance(n,dict) and n['tag']=='div' and not n['attrs']]
                candidates.append(dict(tag='div', attrs={}, children=blocks))
            elif 'song-text' in classes:candidates.append(node)
        elif node['tag'] == 'p' and 'text-center' in classes:
            candidates.append(node)
    valid = []
    for node in candidates:
        text = clean_text(page.text(node))
        if len(text.splitlines()) >= 3 and 12 <= len(tokens(text)) <= MAX_WORDS:
            valid.append(text)
    return max(valid, key=len, default='')


def web_requests(title, artist):
    slug = lambda value: normalized(value).replace(' ', '-')
    return [('Paroles.net', f'https://www.paroles.net/{slug(artist)}/paroles-{slug(title)}'),
            ('Paroles2Chansons', f'https://paroles2chansons.lemonde.fr/paroles-{slug(artist)}/paroles-{slug(title)}.html')]


def title_variants(title):
    """Strip release labels, not meaningful parenthetical parts of a song title."""
    edition = (r'(?:live(?:\s+[^)\]]*)?|acoustic(?:\s+version)?|acoustique|radio\s+edit|'
               r'album\s+version|single\s+version|extended(?:\s+(?:mix|version))?|'
               r'official(?:\s+music)?\s+video|clip\s+officiel)')
    values = list(chart_titles(unicodedata.normalize('NFC', title)))
    for value in list(values):
        base = re.sub(r'\s*(?:[\[(]'+edition+r'[\])]|\s[-–—]\s'+edition+r')\s*$', '', value, flags=re.I).strip()
        if base and base not in values:values.append(base)
    return values[:3]


def discovery_urls(payload):
    """Search snippets are addresses only, never a source of lyric text."""
    if not isinstance(payload,str) or len(payload)>MAX_BYTES:return []
    page=LyricsPage();page.feed(payload);urls=[]
    publishers={host:name for name,host in WEB_SOURCES.items()}
    for node in page.nodes:
        if node['tag']!='a' or 'result__a' not in (node['attrs'].get('class') or '').split():continue
        try:
            url=urljoin(SEARCH_ENDPOINT,node['attrs'].get('href') or '')
            parts=urlsplit(url)
            if parts.hostname in ('duckduckgo.com','www.duckduckgo.com','html.duckduckgo.com') and parts.path=='/l/':
                url=parse_qs(parts.query).get('uddg',[''])[0]
            if not safe_url(url):continue
            parts=urlsplit(url);publisher=publishers.get(parts.hostname)
            if not publisher or '/paroles-' not in parts.path:continue
            item=(publisher,parts._replace(fragment='').geturl())
            if item not in urls:urls.append(item)
        except ValueError:continue
        if len(urls)>=4:break
    return urls


def catalog_urls(payload, base, titles):
    """Resolve publisher-specific song slugs from the artist's own index."""
    if not isinstance(payload,str) or len(payload)>MAX_BYTES:return []
    page=LyricsPage();page.feed(payload);urls=[]
    accepted={key(title) for title in titles}
    for node in page.nodes:
        if node['tag']!='a' or key(page.text(node).strip()) not in accepted:continue
        try:
            url=urljoin(base,node['attrs'].get('href') or '')
            parts=urlsplit(url)
            if not safe_url(url) or parts.hostname!=urlsplit(base).hostname or '/paroles-' not in parts.path:continue
            url=parts._replace(fragment='').geturl()
            if url not in urls:urls.append(url)
        except ValueError:continue
        if len(urls)>=3:break
    return urls


def lookup(project, duration, fetcher=fetch, now=None):
    title, artist = identity(project)
    if not title or not artist:
        return [], ui_text('Renseigne le titre et l’artiste pour chercher les paroles.', 'Enter the title and artist to search for lyrics.')
    # A reference explicitly chosen for this song is durable and works offline.
    # Bind it to the musical identity, never merely the renamed folder.
    if project.get('_root'):
        try:
            selected=json.loads((Path(project['_root'])/'References/lyrics-selected.json').read_text())
            if (selected.get('confirmed') is True and key(selected.get('title',''))==key(title)
                    and key(selected.get('artist',''))==key(artist) and clean_text(selected.get('text'))):
                return [dict(publisher=selected.get('publisher',ui_text('Référence choisie', 'Selected reference')),
                             url=selected.get('url',''),text=clean_text(selected['text']),confirmed=True)], ''
        except (OSError,ValueError,TypeError):pass
    now = time.time() if now is None else now
    titles = title_variants(title)
    title_keys = {key(value) for value in titles}
    signature = hashlib.sha256(json.dumps([title, artist, round(duration, 1), LOOKUP_VERSION]).encode()).hexdigest()
    cache = Path(project['_root'])/'Cache/lyrics-reference.json' if project.get('_root') else None
    previous = []
    if cache:
        try:
            saved = json.loads(cache.read_text())
            if saved['key'] == signature:
                previous = [{**s,'text':clean_text(s.get('text'))} for s in saved['sources'] if isinstance(s,dict)] if isinstance(saved['sources'], list) else []
                for source in previous:
                    if source.get('lineTimes'):
                        source['lineTimes']=[[key(clean_text(label)),stamp] for label,stamp in source['lineTimes']]
                if saved.get('lineTimeSchema')==1 and 0 <= now - saved['time'] < saved['ttl']:
                    return previous, saved['message']
        except (OSError, ValueError, KeyError, TypeError):
            pass
    sources, errors, retry_delay = [], set(), 300.
    deadline = time.monotonic() + NETWORK_BUDGET
    seen_urls = set()

    def request(publisher, url):
        nonlocal retry_delay
        if publisher in errors or url in seen_urls:return
        if time.monotonic() >= deadline:
            errors.add(publisher)
            return
        seen_urls.add(url)
        try:
            return fetcher(url)
        except HTTPError as error:
            if error.code in (404,410):return
            errors.add(publisher)
            if error.code in (429,503):
                try:retry_delay = max(retry_delay, min(86400., float((error.headers or {}).get('Retry-After',300))))
                except (ValueError,TypeError):pass
        except (OSError,ValueError,TypeError):errors.add(publisher)

    def retrieve(publisher, url):
        payload = request(publisher,url)
        if payload is None:return
        try:
            if publisher == 'LRCLIB':
                if not isinstance(payload, list):
                    raise ValueError(ui_text('Réponse LRCLIB invalide.', 'Invalid LRCLIB response.'))
                for row in payload[:20]:
                    if not isinstance(row, dict) or row.get('instrumental'):
                        continue
                    if not title_keys.intersection(key(t) for t in title_variants(row.get('trackName', ''))) or key(row.get('artistName', '')) != key(artist):
                        continue
                    try:length = float(row.get('duration') or 0)
                    except (TypeError,ValueError):length = 0
                    same_duration = math.isfinite(length) and length > 0 and abs(length-duration) <= max(8., duration*.04)
                    # Different releases can share words. Confirm their text
                    # against local vocals; use remote timing only for matching edits.
                    text = clean_text(row.get('plainLyrics') or row.get('syncedLyrics'))
                    if text and isinstance(row.get('id'), int):
                        source=dict(publisher=publisher,url=f"https://lrclib.net/api/get/{row['id']}",text=text)
                        if same_duration and isinstance(row.get('syncedLyrics'),str):
                            from advanced import parse_lyrics
                            try:
                                lines=parse_lyrics(row['syncedLyrics'],length)
                                source['lineTimes']=[[key(clean_text(line['text'])),line['start']] for line in lines]
                            except (ValueError,OverflowError):pass
                        sources.append(source)
            elif publisher in WEB_SOURCES:
                text = page_lyrics(payload, publisher, titles, artist)
                if text:sources.append(dict(publisher=publisher,url=url,text=text))
            elif isinstance(payload, dict):
                text = clean_text(payload.get('lyrics'))
                if text:
                    sources.append(dict(publisher=publisher, url=url, text=text))
        except (OSError, ValueError, TypeError):
            errors.add(publisher)

    # Exhaust title variants before giving up. A throttled/offline publisher
    # gets one attempt per lookup; other publishers can still answer.
    for candidate in titles:
        retrieve('LRCLIB', 'https://lrclib.net/api/search?' + urlencode({'track_name': candidate, 'artist_name': artist}))
        retrieve('lyrics.ovh', 'https://api.lyrics.ovh/v1/' + quote(artist, safe='') + '/' + quote(candidate, safe=''))
        if sources:break
    if not sources:
        for candidate in titles:
            for publisher, url in web_requests(candidate, artist):retrieve(publisher, url)
            if sources:break
    if not sources:
        slug=normalized(artist).replace(' ','-')
        indexes=[('Paroles.net',f'https://www.paroles.net/{slug}'),
                 ('Paroles2Chansons',f'https://paroles2chansons.lemonde.fr/paroles-{slug}')]
        for publisher,url in indexes:
            for candidate in catalog_urls(request(publisher,url),url,titles):retrieve(publisher,candidate)
    if not sources and any(name not in errors for name in WEB_SOURCES) and time.monotonic()<deadline:
        query = artist+' '+titles[-1]+' paroles ('+' OR '.join('site:'+host for host in WEB_SOURCES.values())+')'
        for publisher,url in discovery_urls(request(ui_text('Recherche web', 'Web search'),SEARCH_ENDPOINT+'?'+urlencode({'q':query}))):
            retrieve(publisher,url)
    message = '' if sources else (ui_text('Sources indisponibles, réessaie plus tard.', 'Sources unavailable. Try again later.') if errors else ui_text('Aucune référence trouvée pour cette version.', 'No reference found for this version.'))
    if errors:
        # Keep locally identified editions when their publisher is temporarily offline.
        # A confirmed absence, a different recording or a different song starts fresh.
        sources.extend({**s,'cachedCopy':True} for s in previous if isinstance(s,dict)
                       and s.get('publisher') in errors and safe_url(s.get('url','')) and clean_text(s.get('text')))
        if any(s.get('cachedCopy') for s in sources):
            message=ui_text('Certaines références proviennent de la dernière recherche réussie.', 'Some references come from the last successful search.')
    ttl=retry_delay if errors or not sources else 86400.
    if cache:
        from services import atomic
        try:atomic(cache, dict(key=signature, time=now, ttl=ttl, sources=sources, message=message,lineTimeSchema=1))
        except OSError:pass
    return sources, message


def matched_line_reference(segments, sources):
    """Identify a synchronized edition from distributed acoustic line onsets."""
    from difflib import SequenceMatcher
    from statistics import median
    located=[s for s in segments if not s.get('manual') and s.get('words') and math.isfinite(s['t'])]
    if len(located)<5:return None
    labels=[key(s['text']) for s in located]
    span=located[-1]['t']-located[0]['t']
    if span<=0:return None
    best=None
    for source in sources:
        times=source.get('lineTimes') or []
        if not times:continue
        matches=SequenceMatcher(None,labels,[text for text,_ in times],autojunk=False).get_matching_blocks()
        pairs=[(i+k,located[i+k]['t']-times[j+k][1]) for i,j,count in matches for k in range(count)]
        if len(pairs)<max(5,len(located)*.4):continue
        offset=median(delta for _,delta in pairs)
        # Allow video pre-roll. A consistent offset throughout the
        # recording distinguishes a matching edition from a different arrangement.
        agree=[i for i,delta in pairs if abs(delta-offset)<=.65]
        if (len(agree)<max(4,len(pairs)*.75) or len({labels[i] for i in agree})<3
                or located[agree[-1]]['t']-located[agree[0]]['t']<span*.55):continue
        error=median(abs(delta-offset) for _,delta in pairs)
        rank=(len(agree),-error)
        if best is None or rank>best[0]:
            best=(rank,source,pairs,offset)
    return (best,located) if best is not None else None


def check_line_starts(segments, sources):
    """Compare ordered, acoustically located lines with one synchronized edition."""
    match=matched_line_reference(segments,sources)
    if match is None:return None
    best,located=match
    (consistent,_),source,pairs,offset=best
    for i,delta in pairs:
        if abs(delta-offset)>1.5:
            located[i]['timingReview']=True
            located[i]['words'][0]['timingReview']=True
    return dict(publisher=source['publisher'],url=source['url'],compared=len(pairs),
                consistent=consistent,offsetSeconds=round(offset,3))


def recover_line_windows(audio, segments, sources, duration, language, folder, aligner=None):
    """Recover missed repetitions using verified LRC as search windows only."""
    from lyrics_alignment import acoustic_align
    match=matched_line_reference(segments,sources)
    if match is None:return 0
    best,_=match
    _,source,_,offset=best
    times=source['lineTimes']
    automatic=[s for s in segments if not s.get('manual')]
    labels=[key(s['text']) for s in automatic]
    blocks=SequenceMatcher(None,labels,[label for label,_ in times],autojunk=False).get_matching_blocks()
    jobs=[]
    for i,j,count in blocks:
        for k in range(count):
            row=automatic[i+k];target=times[j+k][1]+offset
            if row.get('words') and abs(row['t']-target)<=1.5:continue
            following=times[j+k+1][1]+offset if j+k+1<len(times) else duration
            # Never search a whole instrumental break for a short response.
            end=min(duration,following+.15,target+max(8.,len(tokens(row['text']))*.65))
            start=max(0.,target-.5)
            following_row=automatic[i+k+1] if i+k+1<len(automatic) else None
            if following_row and following_row.get('words') and abs(following_row['t']-following)<=1.5:
                end=min(end,following_row['t'])
            previous_row=automatic[i+k-1] if i+k else None
            if previous_row and previous_row.get('words') and previous_row['end']<target+1:
                start=max(start,previous_row['end'])
            if end-start>=.2:
                jobs.append(dict(id=str(i+k),text=row['text'],t0=start,t1=end))
    if not jobs:return 0
    try:aligned=(aligner or acoustic_align)(audio,jobs,language,folder)
    except (OSError,ValueError,RuntimeError,ImportError):return 0
    by_id={str(item.get('id')):item for item in aligned};recovered=0
    for job in jobs:
        item=by_id.get(job['id'],{});words=item.get('words',[])
        expected=tokens(job['text'])
        if (item.get('error') or [key(w.get('w','')) for w in words]!=list(map(key,expected))
                or not all(all(isinstance(w.get(field),(int,float)) and math.isfinite(w[field]) for field in ('t','end','score'))
                           and job['t0']<=w['t']<w['end']<=job['t1']+.001 for w in words)
                or not all(a['end']<=b['t'] for a,b in zip(words,words[1:]))):continue
        row=automatic[int(job['id'])]
        if any(s.get('manual') and s['t']<words[-1]['end'] and s['end']>words[0]['t'] for s in segments):continue
        weak=not math.isfinite(item.get('score',0)) or item.get('score',0)<.15
        row.update(t=words[0]['t'],end=words[-1]['end'],words=[{**w,'w':word,'timingReview':weak or w['score']<.08}
                   for w,word in zip(words,expected)],confidence=min(w['score'] for w in words),
                   timingReview=weak or any(w['score']<.08 for w in words))
        recovered+=1
    # Preserve real acoustic word positions; flag any remaining boundary conflict.
    for left,right in zip(segments,segments[1:]):
        if left['end']>right['t']:
            for row in (left,right):
                if not row.get('manual'):row['timingReview']=True
    return recovered


def match_words(observed, reference):
    """Global monotonic edit alignment; repeated refrains cannot reorder lines."""
    import numpy as np
    n, m = len(observed), len(reference)
    if not n or not m or max(n, m) > MAX_WORDS:
        return [], 0.
    a, b = list(map(key, observed)), list(map(key, reference))
    back = np.zeros((n+1, m+1), dtype=np.uint8)
    back[0, 1:] = 2
    previous = np.arange(m+1, dtype=float)
    for i in range(1, n+1):
        current = np.empty(m+1); current[0] = i
        for j in range(1, m+1):
            substitution = 0. if a[i-1] == b[j-1] else 1.5
            choices = (previous[j-1]+substitution, previous[j]+1., current[j-1]+1.)
            direction = min(range(3), key=choices.__getitem__)
            current[j], back[i, j] = choices[direction], direction
        previous = current
    i, j, pairs = n, m, []
    while i or j:
        direction = back[i, j] if i and j else (1 if i else 2)
        if direction == 0:pairs.append((i-1, j-1)); i -= 1; j -= 1
        elif direction == 1:pairs.append((i-1, None)); i -= 1
        else:pairs.append((None, j-1)); j -= 1
    exact = sum(a[i] == b[j] for i, j in pairs if i is not None and j is not None)
    return pairs[::-1], 2*exact/(n+m)


def proposals(segments, text):
    observed, owners = [], []
    for i, row in enumerate(segments):
        words = tokens(row.get('text', ''))
        observed.extend(words); owners.extend([i]*len(words))
    reference = tokens(text)
    pairs, agreement = match_words(observed, reference)
    if agreement < .45:
        return [], agreement
    mapped = [[] for _ in segments]
    for k, (i, j) in enumerate(pairs):
        if j is None:continue
        if i is None:
            # An inserted word needs a known line on BOTH sides. Do not invent
            # missing verses or borrow a neighbouring chorus's timestamps.
            left = next((a for a, _ in reversed(pairs[:k]) if a is not None), None)
            right = next((a for a, _ in pairs[k+1:] if a is not None), None)
            if left is None or right is None or owners[left] != owners[right]:continue
            i = left
        mapped[owners[i]].append(reference[j])
    result = []
    for i, (row, words) in enumerate(zip(segments, mapped)):
        old = tokens(row.get('text', ''))
        if row.get('manual') or not old or not words or list(map(key, old)) == list(map(key, words)):
            continue
        shared = sum(block.size for block in SequenceMatcher(None, list(map(key, old)), list(map(key, words)), autojunk=False).get_matching_blocks())
        if shared < 2 or 2*shared/(len(old)+len(words)) < .4 or not .45 <= len(words)/len(old) <= 2:
            continue
        start=row.get('t', row.get('start', 0))
        before=segments[i-1]['end'] if i else 0
        after=segments[i+1].get('t',segments[i+1].get('start',row['end'])) if i+1<len(segments) else row['end']+.75
        # Whisper can trim an initial consonant or a sustained final vowel.
        # Use only the available silence; never overlap an adjacent line.
        a,b=max(0,before,start-.35),min(after,row['end']+.75)
        if b-a<.2 or b-a>30:continue
        result.append(dict(id=str(i), text=' '.join(words), t0=a, t1=b))
    return result, agreement


def local_align(audio, jobs, language, folder):
    import reacue_words
    import torch
    # Resolve existing weights only. A correction never starts a model download.
    files=reacue_words.model_files(language, download=False)
    model,vocab,blank,normalize=reacue_words.load_model(language,files)
    wav=reacue_words._load_audio(str(audio))
    job_path, result_path = Path(folder)/'alignment-jobs.json', Path(folder)/'alignment-result.json'
    job_path.write_text(json.dumps(jobs, ensure_ascii=False))
    lines=[];previous=None;em=None
    with torch.inference_mode():
        for job in jobs:
            try:
                window=(max(0,round(job['t0']*reacue_words.SR)),min(len(wav),round(job['t1']*reacue_words.SR)))
                if not .2*reacue_words.SR<=window[1]-window[0]<=30*reacue_words.SR:
                    raise ValueError(ui_text('Fenêtre vocale invalide.', 'Invalid vocal window.'))
                if window!=previous:
                    em,step=reacue_words.emissions(model,wav[window[0]:window[1]],normalize)
                    previous=window
                words,score=reacue_words.align_words(em,step,reacue_words.tokenize(job['text'],vocab),blank,
                    vocab.get('|'),offset=window[0]/reacue_words.SR)
                lines.append(dict(id=job['id'],words=words,score=score))
            except (ValueError,RuntimeError) as error:
                lines.append(dict(id=job['id'],error=str(error)))
    result_path.write_text(json.dumps(dict(lines=lines),ensure_ascii=False))
    return lines


def existing_transcription(project, offset=0, language='auto'):
    rows = []
    for entry in project.get('lyrics', []):
        row = dict(text=entry['text'], t=entry['start']-offset, end=entry['end']-offset,
                   manual=bool(entry.get('manual')), words=[dict(w=w['text'], t=w['start']-offset,
                   end=w['end']-offset) for w in entry.get('words', [])])
        if entry.get('sourceURL'):row['sourceURL']=entry['sourceURL']
        rows.append(row)
    if language == 'auto':
        language = (project.get('lyricsReference') or {}).get('language', 'auto')
    if language == 'auto':
        words = [key(w) for row in rows for w in tokens(row['text'])]
        en = sum(w in {'the','we','my','your','you','and','when','with','im','ive','dont'} for w in words)
        fr = sum(w in {'le','la','les','je','tu','des','une','est','dans','que','pas'} for w in words)
        language = 'en' if en >= max(4, fr*2) else 'fr' if fr >= max(4, en*2) else 'auto'
    return dict(language=language, segments=rows)


def select_reference(ranked, audio, segments, language, folder, scorer=None):
    """Use the transcript as evidence, not as a ceiling on reference coverage."""
    from lyrics_alignment import reference_scores
    if ranked[0][1].get('confirmed'):return ranked[0],''
    best=ranked[0][0]
    candidates=[item for item in ranked if item[2]['confirmed'] and item[0]>=best-.10]
    # Keep bounded acoustic work, favouring supported content over a ratio that
    # can reward missing verses. Identical provider copies were deduplicated.
    candidates=sorted(candidates,key=lambda item:(item[2]['supported'],item[0]),reverse=True)[:6]
    if len(candidates)==1:return candidates[0],''
    print((f'Comparing {len(candidates)} references with the transcription and vocals…' if using_english() else f'Comparaison de {len(candidates)} références avec la transcription et le chant…'),flush=True)
    try:
        scores=(scorer or reference_scores)(audio,[item[2] for item in candidates],segments,language,folder)
    except (OSError,ValueError,RuntimeError,ImportError):scores=[]
    measured=[(float(score),item) for score,item in zip(scores,candidates)
              if isinstance(score,(int,float)) and math.isfinite(score)]
    if len(measured)==len(candidates):
        measured.sort(key=lambda value:value[0],reverse=True)
        if measured[0][0]-measured[1][0]>=.015:
            return measured[0][1],ui_text('Référence sélectionnée automatiquement avec la transcription et le chant. ', 'Reference selected automatically using the transcription and vocals. ')
    # Even without a decisive acoustic score, matching references do not need
    # to block text import. Prefer the one explaining the most recognised
    # content; timing uncertainty is assessed independently below.
    return candidates[0],ui_text('Référence sélectionnée automatiquement d’après les mots reconnus. ', 'Reference selected automatically from the recognized words. ')


def correction_audio(project, audio, fallback_offset=0):
    """Use the complete vocal stem for reference alignment, including backing vocals."""
    root=Path(project['_root']).resolve() if project.get('_root') else None
    current=Path(audio).resolve();matched={}
    if root:
        for track in project.get('tracks',[]):
            path=(root/track.get('file','')).resolve()
            if path.is_relative_to(root) and path==current:matched=track
        for track in project.get('tracks',[]):
            if track.get('role')!='vocals':continue
            relative=Path(track.get('file',''))
            if relative.is_absolute() or '..' in relative.parts:continue
            path=(root/relative).resolve()
            if path.is_relative_to(root) and path.is_file():return str(path),track.get('offset',0)
    return str(current),matched.get('offset',fallback_offset)


def correct(project, transcription, audio, folder, *, fetcher=fetch, aligner=None, reference_scorer=None):
    from analysis_progress import emit
    from lyrics_alignment import plan, windows, reconstruct, align_reference
    result = copy.deepcopy(transcription)
    segments = result.get('segments', [])
    reference = dict(status='unavailable', message='', sources=[], corrected=0, review=0, timingReview=0, alignmentVersion=1,
                     language=result.get('language', 'auto'))
    result['lyricsReference'] = reference
    if not segments:
        reference['message'] = ui_text('Transcris d’abord le chant pour retrouver la version et ses points d’ancrage.', 'Transcribe the vocals first to identify the version and its anchors.')
        return result
    duration = max((t.get('duration', 0) for t in project.get('tracks', []) if t.get('role') == 'source'), default=0)
    if duration <= 0:duration=max(s['end'] for s in segments)
    emit(progress=100/3, progressBasis='steps', progressLabel=ui_text('Recherche de paroles sur Internet', 'Searching for lyrics online'), indeterminate=True)
    sources, message = lookup(project, duration, fetcher)
    ranked, seen = [], set()
    for source in sources:
        digest = hashlib.sha256(' '.join(map(key, tokens(source['text']))).encode()).hexdigest()
        if digest in seen:continue
        seen.add(digest)
        proposal=plan(segments,source['text'])
        if not proposal['words'] or len(proposal['words'])>MAX_WORDS:continue
        ranked.append((proposal['agreement'],source,proposal))
    ranked=[item for item in ranked if item[2]['confirmed'] or item[1].get('confirmed')]
    ranked.sort(key=lambda item:(bool(item[1].get('confirmed')),item[0]), reverse=True)
    reference['sources'] = list(dict.fromkeys(s['publisher'] for s in sources))
    if not ranked:
        reference['message'] = (message or ui_text('La référence ne peut pas être confirmée avec les mots reconnus.', 'The recognized words could not confirm the reference.')) + ui_text(' Transcription non vérifiée.', ' Transcription unverified.')
        return result
    emit(progressLabel=(f'Comparing with vocals · {len(ranked)} version(s)' if using_english() else f'Comparaison avec le chant · {len(ranked)} version(s)'), indeterminate=True)
    (_,source,proposal),selection=select_reference(ranked,audio,segments,result.get('language','auto'),folder,reference_scorer)
    reference['sources']=[source['publisher']]
    emit(progress=200/3, progressBasis='steps', progressLabel=ui_text('Recalage des paroles sur le chant', 'Aligning lyrics to vocals'), indeterminate=True)
    jobs,position=windows(segments,proposal,duration)
    try:
        if aligner is not None:aligned=aligner(audio,jobs,result.get('language','auto'),folder)
        else:proposal,jobs,aligned,position=align_reference(audio,segments,proposal,duration,result.get('language','auto'),folder)
    except (OSError, ValueError, RuntimeError, ImportError):
        aligned=[]
    result['segments'],review=reconstruct(segments,proposal,jobs,aligned,position,source)
    if aligner is None:
        recovered=recover_line_windows(audio,result['segments'],sources,duration,result.get('language','auto'),folder)
        if recovered:reference['recoveredLines']=recovered
        review=sum(bool(s.get('timingReview')) for s in result['segments'] if not s.get('manual'))
    timing=check_line_starts(result['segments'],sources)
    if timing:
        reference['lineTimingCheck']=timing
        review=sum(bool(s.get('timingReview')) for s in result['segments'] if not s.get('manual'))
    automatic=[s for s in result['segments'] if not s.get('manual')]
    reference.update(status='corrected',corrected=len(automatic),review=0,timingReview=review)
    reference['message']=(selection+(f'Reference lyrics applied: {len(automatic)} line(s). ' if using_english() else f"Texte de référence appliqué : {len(automatic)} ligne(s). ")
        + (ui_text('Copie locale utilisée pendant l’indisponibilité du site. ', 'Using a local copy while the site is unavailable. ') if source.get('cachedCopy') else '')
        + (ui_text('Répétitions adaptées à cette version audio. ', 'Repeats adapted to this recording. ') if proposal.get('repeatAdjustments') else '')
        + ((f'{review} timing(s) to review. Missing word times have been left blank.' if using_english() else f"{review} calage(s) à vérifier ; aucun horaire de mot inventé.") if review
           else ui_text('Mots recalés sur la piste chant.', 'Words aligned to the vocal track.')))
    if timing:
        reference['message']+=(f" Line starts match {timing['publisher']} · {timing['consistent']} of {timing['compared']} compared." if using_english() else f" Débuts de ligne concordants avec {timing['publisher']} · {timing['consistent']} sur {timing['compared']} comparés.")
    return result
