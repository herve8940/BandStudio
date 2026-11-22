"""Account-free lyric references, checked against local vocals before correction.

Remote timestamps are never copied: different releases can have different edits.
Only title/artist leave the machine. Confirmed reference text replaces ASR guesses;
manual edits survive, while text confidence and timing confidence stay separate.
"""
import copy
from difflib import SequenceMatcher
import hashlib
import json
import math
from pathlib import Path
import re
import time
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener

from chord_sources import identity, normalized

HOSTS = {'lrclib.net', 'api.lyrics.ovh'}
MAX_BYTES = 1_000_000
MAX_WORDS = 1800


def tokens(text):
    return re.findall(r"[^\W_]+(?:['’−-][^\W_]+)*", text, re.UNICODE)


def key(word):
    return normalized(word).replace(' ', '')


def safe_url(url):
    try:
        p = urlsplit(url)
        return p.scheme == 'https' and p.hostname in HOSTS and not p.username and not p.password and p.port in (None, 443)
    except ValueError:
        return False


class Redirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not safe_url(newurl) or urlsplit(req.full_url).hostname != urlsplit(newurl).hostname:
            raise ValueError('Redirection de paroles refusée.')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url):
    if not safe_url(url):
        raise ValueError('Source de paroles invalide.')
    request = Request(url, headers={'User-Agent': 'BandStudio/1.1 (https://github.com/herve8940/BandStudio)', 'Accept': 'application/json'})
    with build_opener(Redirects()).open(request, timeout=6) as response:
        if response.status != 200 or not safe_url(response.url):
            raise ValueError('Source de paroles indisponible.')
        data = response.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError('Réponse de paroles trop volumineuse.')
        return json.loads(data)


def clean_text(value):
    if not isinstance(value, str) or len(value) > 50_000:
        return ''
    rows = []
    for row in value.splitlines():
        row = re.sub(r'\[[^\]\n]*\]', '', row).strip()
        if not row or re.match(r'^(Paroles de la chanson|Lyrics of|Lyrics for)\b', row, re.I):
            continue
        rows.append(row)
    return '\n'.join(rows)


def lookup(project, duration, fetcher=fetch, now=None):
    title, artist = identity(project)
    if not title or not artist:
        return [], 'Renseigne le titre et l’artiste pour chercher les paroles.'
    # A reference explicitly chosen for this song is durable and works offline.
    # Bind it to the musical identity, never merely the renamed folder.
    if project.get('_root'):
        try:
            selected=json.loads((Path(project['_root'])/'References/lyrics-selected.json').read_text())
            if (selected.get('confirmed') is True and key(selected.get('title',''))==key(title)
                    and key(selected.get('artist',''))==key(artist) and clean_text(selected.get('text'))):
                return [dict(publisher=selected.get('publisher','Référence choisie'),
                             url=selected.get('url',''),text=clean_text(selected['text']),confirmed=True)], ''
        except (OSError,ValueError,TypeError):pass
    now = time.time() if now is None else now
    signature = hashlib.sha256(json.dumps([title, artist, round(duration, 1), 2]).encode()).hexdigest()
    cache = Path(project['_root'])/'Cache/lyrics-reference.json' if project.get('_root') else None
    if cache:
        try:
            saved = json.loads(cache.read_text())
            if saved['key'] == signature and 0 <= now - saved['time'] < saved['ttl']:
                return saved['sources'], saved['message']
        except (OSError, ValueError, KeyError, TypeError):
            pass
    sources, errors, ttl = [], [], 86400
    requests = [('LRCLIB', 'https://lrclib.net/api/search?' + urlencode({'track_name': title, 'artist_name': artist})),
                ('lyrics.ovh', 'https://api.lyrics.ovh/v1/' + quote(artist, safe='') + '/' + quote(title, safe=''))]
    for publisher, url in requests:
        try:
            payload = fetcher(url)
            if publisher == 'LRCLIB':
                if not isinstance(payload, list):
                    raise ValueError('Réponse LRCLIB invalide.')
                for row in payload[:20]:
                    if not isinstance(row, dict) or row.get('instrumental'):
                        continue
                    if key(row.get('trackName', '')) != key(title) or key(row.get('artistName', '')) != key(artist):
                        continue
                    length = float(row.get('duration') or 0)
                    # A video may have a short pre-roll. Reject different edits.
                    if not math.isfinite(length) or abs(length-duration) > max(8., duration*.04):
                        continue
                    text = clean_text(row.get('plainLyrics') or row.get('syncedLyrics'))
                    if text and isinstance(row.get('id'), int):
                        sources.append(dict(publisher=publisher, url=f"https://lrclib.net/api/get/{row['id']}", text=text))
            elif isinstance(payload, dict):
                text = clean_text(payload.get('lyrics'))
                if text:
                    sources.append(dict(publisher=publisher, url=url, text=text))
        except HTTPError as error:
            errors.append(publisher)
            # Never retry a throttled service in this job or on immediate reruns.
            if error.code in (429, 503):
                try:ttl = max(300., min(86400., float(error.headers.get('Retry-After', 300))))
                except (ValueError, TypeError):ttl = 300.
        except (OSError, ValueError, TypeError):
            errors.append(publisher)
    message = '' if sources else ('Sources indisponibles, réessaie plus tard.' if errors else 'Aucune référence trouvée pour cette version.')
    if not sources:
        ttl = max(300., ttl if ttl != 86400 else 300.)
    if cache:
        from services import atomic
        try:atomic(cache, dict(key=signature, time=now, ttl=ttl, sources=sources, message=message))
        except OSError:pass
    return sources, message


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
                    raise ValueError('Fenêtre vocale invalide.')
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
    print(f'Comparaison de {len(candidates)} références avec la transcription et le chant…',flush=True)
    try:
        scores=(scorer or reference_scores)(audio,[item[2] for item in candidates],segments,language,folder)
    except (OSError,ValueError,RuntimeError,ImportError):scores=[]
    measured=[(float(score),item) for score,item in zip(scores,candidates)
              if isinstance(score,(int,float)) and math.isfinite(score)]
    if len(measured)==len(candidates):
        measured.sort(key=lambda value:value[0],reverse=True)
        if measured[0][0]-measured[1][0]>=.015:
            return measured[0][1],'Référence sélectionnée automatiquement avec la transcription et le chant. '
    # Even without a decisive acoustic score, matching references do not need
    # to block text import. Prefer the one explaining the most recognised
    # content; timing uncertainty is assessed independently below.
    return candidates[0],'Référence sélectionnée automatiquement d’après les mots reconnus. '


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
    from lyrics_alignment import plan, windows, reconstruct, align_reference
    result = copy.deepcopy(transcription)
    segments = result.get('segments', [])
    reference = dict(status='unavailable', message='', sources=[], corrected=0, review=0, timingReview=0, alignmentVersion=1,
                     language=result.get('language', 'auto'))
    result['lyricsReference'] = reference
    if not segments:
        reference['message'] = 'Transcris d’abord le chant pour retrouver la version et ses points d’ancrage.'
        return result
    duration = max((t.get('duration', 0) for t in project.get('tracks', []) if t.get('role') == 'source'), default=0)
    if duration <= 0:duration=max(s['end'] for s in segments)
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
        reference['message'] = (message or 'La référence ne peut pas être confirmée avec les mots reconnus.') + ' Transcription non vérifiée.'
        return result
    (_,source,proposal),selection=select_reference(ranked,audio,segments,result.get('language','auto'),folder,reference_scorer)
    reference['sources']=[source['publisher']]
    jobs,position=windows(segments,proposal,duration)
    try:
        if aligner is not None:aligned=aligner(audio,jobs,result.get('language','auto'),folder)
        else:proposal,jobs,aligned,position=align_reference(audio,segments,proposal,duration,result.get('language','auto'),folder)
    except (OSError, ValueError, RuntimeError, ImportError):
        aligned=[]
    result['segments'],review=reconstruct(segments,proposal,jobs,aligned,position,source)
    automatic=[s for s in result['segments'] if not s.get('manual')]
    reference.update(status='corrected',corrected=len(automatic),review=0,timingReview=review)
    reference['message']=(selection+f"Texte de référence appliqué : {len(automatic)} ligne(s). "
        + ('Répétitions adaptées à cette version audio. ' if proposal.get('repeatAdjustments') else '')
        + (f"{review} calage(s) à vérifier ; aucun horaire de mot inventé." if review
           else 'Mots recalés sur la piste chant.'))
    return result
