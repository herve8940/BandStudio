"""Optional, reference-assisted review of the existing arrangement.

Reference times are approximate. Only interpolate between several matching
local landmarks, snap to the saved measures, and preserve protected boundaries.
An accepted export is a batch decision, never beat/section training truth.
"""
from __future__ import annotations

import copy
import hashlib
from html.parser import HTMLParser
import json
import math
from pathlib import Path
import re
import shutil
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener
import uuid

from chord_sources import identity, normalized, matches_heading
from preparation import fingerprint as preparation_fingerprint
from services import atomic

SCHEMA = 1
MAX_BYTES = 800_000


def fingerprint(project):
    # Identity metadata and the selected chart can change without moving notes.
    value = dict(preparation=preparation_fingerprint(project), identity=identity(project),
                 reference=project.get('chordReference'))
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def validate_document(project):
    from windows.project import validate
    # Capture settings are unchanged; the native hosts validate them. The Mac
    # worker intentionally ships the shared document module without Windows I/O.
    validate({k:v for k,v in project.items() if k != 'capture'}, project['_root'])


def record_decision(root, proposal, action, after_fingerprint=None):
    uuid.UUID(proposal['id'])
    event = dict(schema=1, id=str(uuid.uuid4()), proposalID=proposal['id'], action=action,
                 beforeFingerprint=proposal['fingerprint'], afterFingerprint=after_fingerprint,
                 changes=proposal['changes'], sources=proposal['sources'], createdAt=time.time(),
                 labelPolicy='Batch decision only; no marker, beat or chord ground truth.')
    atomic(Path(root)/'Learning/structure-reviews'/(event['id']+'.json'), event)


def address(url):
    try:
        p = urlsplit(url)
        return (p.scheme == 'https' and p.hostname == 'drumy.app' and
                not p.username and not p.password and p.port in (None, 443) and
                re.fullmatch(r'/drums/[a-z0-9-]+/?', p.path) is not None and not p.query)
    except ValueError:
        return False


class Redirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not address(newurl):
            raise ValueError('Adresse de référence refusée.')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url):
    if not address(url):
        raise ValueError('Adresse de référence refusée.')
    request = Request(url, headers={'User-Agent': 'BandStudio/1.1 (structure reference reader)', 'Accept': 'text/html'})
    with build_opener(Redirects()).open(request, timeout=6) as response:
        if response.status != 200 or not address(response.url):
            raise ValueError('Référence indisponible.')
        data = response.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError('Référence trop volumineuse.')
        return data.decode('utf-8', errors='replace'), response.url


class SongMap(HTMLParser):
    """Read only the named song-map list, not fills, navigation or scripts."""
    def __init__(self):
        super().__init__()
        self.heading = ''; self.duration = None; self.entries = []
        self.in_heading = False; self.label = ''; self.fact = None
        self.waiting = False; self.in_map = False; self.row = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'h1': self.in_heading = True
        if tag == 'dt': self.label = ''; self.fact = 'label'
        if tag == 'dd': self.fact = 'value'; self.value = ''
        if attrs.get('id') == 'song-map': self.waiting = True
        if tag == 'ol' and self.waiting:
            self.in_map = True; self.waiting = False
        if tag == 'li' and self.in_map: self.row = ''

    def handle_data(self, text):
        if self.in_heading: self.heading += text
        if self.fact == 'label': self.label += text
        if self.fact == 'value': self.value += text
        if self.row is not None: self.row += text + ' '

    def handle_endtag(self, tag):
        if tag == 'h1': self.in_heading = False
        if tag == 'dt': self.fact = None
        if tag == 'dd':
            if self.label.strip() == 'Length': self.duration = seconds(self.value.strip())
            self.fact = None
        if tag == 'li' and self.row is not None:
            match = re.fullmatch(r'\s*(\d{1,3}:\d{2})\s+(.{1,80}?)\s*', self.row)
            if match:
                self.entries.append({'time': seconds(match[1]), 'name': match[2].strip()})
            self.row = None
        if tag == 'ol': self.in_map = False


def seconds(value):
    match = re.fullmatch(r'(\d{1,3}):([0-5]\d)', value)
    return int(match[1]) * 60 + int(match[2]) if match else None


def parse(page, title, artist, url):
    chart = SongMap(); chart.feed(page)
    entries = chart.entries
    if not address(url) or not matches_heading(chart.heading, title, artist):
        raise ValueError('La référence ne correspond pas au titre et à l’artiste.')
    if (not chart.duration or not 3 <= len(entries) <= 150 or
            any(e['time'] is None or e['time'] >= chart.duration for e in entries) or
            any(b['time'] <= a['time'] for a, b in zip(entries, entries[1:]))):
        raise ValueError('La référence ne contient pas de structure exploitable.')
    return dict(schema=SCHEMA, title=title, artist=artist, publisher='DRUMY', url=url,
                duration=chart.duration, entries=entries, retrievedAt=time.time())


def lookup(project):
    title, artist = identity(project)
    if not title or not artist:
        return None, 'Titre et artiste incomplets : structure Internet non comparée.'
    key = hashlib.sha256((title + '\n' + artist).encode()).hexdigest()
    cache = Path(project['_root']) / 'References' / ('structure-' + key + '.json')
    slug = lambda text: normalized(re.sub(r"['’`′]", '', text)).replace(' ', '-')
    url = 'https://drumy.app/drums/' + slug(title) + '-' + slug(artist)
    try:
        page, url = fetch(url)
        reference = parse(page, title, artist, url)
        atomic(cache, reference)
        return reference, ''
    except (OSError, ValueError, HTTPError):
        try:
            saved = json.loads(cache.read_text())
            # Reparse the small cached factual map; never trust arbitrary paths
            # or a stale identity from a different recording.
            if (saved['schema'] == SCHEMA and saved['title'] == title and saved['artist'] == artist
                    and address(saved['url']) and 3 <= len(saved['entries']) <= 150
                    and 0 < saved['duration'] <= 43200 and saved['publisher'] == 'DRUMY'
                    and all(math.isfinite(x['time']) and 0 <= x['time'] < saved['duration']
                            and isinstance(x['name'],str) and 0 < len(x['name']) <= 80 for x in saved['entries'])
                    and all(b['time'] > a['time'] for a, b in zip(saved['entries'], saved['entries'][1:]))):
                return saved, 'Référence de structure enregistrée utilisée ; Internet non actualisé.'
        except (OSError, ValueError, KeyError, TypeError):
            pass
        return None, 'Repères minutés non récupérés auprès de DRUMY.'


def kind(name):
    value = normalized(name)
    if value in ('prechorus','pre chorus','pre refrain'):return 'prechorus'
    if value in ('postchorus','post chorus','post refrain'):return 'postchorus'
    if any(x in value for x in ('post chorus','post refrain')):return 'postchorus'
    if value in ('break','breakdown','arret'):return 'break'
    if value in ('ending','end'):return 'outro'
    if value in ('re intro','reintro'):return 'instrumental'
    if 'pre' in value.split() and ('verse' in value or 'couplet' in value): return 'preverse'
    if 'pre' in value.split() and ('solo' in value): return 'presolo'
    if 'riff avant couplet' in value: return 'preverse'
    if 'riff avant solo' in value: return 'presolo'
    if any(x in value for x in ('pre chorus', 'pre refrain')): return 'prechorus'
    if any(x in value for x in ('chorus', 'refrain')): return 'chorus'
    if any(x in value for x in ('verse', 'couplet')): return 'verse'
    if 'solo' in value: return 'solo'
    if value.startswith('intro'): return 'intro'
    if any(x in value for x in ('outro', 'coda', 'final')): return 'outro'
    if any(x in value for x in ('bridge', 'pont')): return 'bridge'
    if value in ('instrumental', 'interlude', 'riff'): return 'instrumental'
    from chord_sources import section_kind
    translated=section_kind(value)
    if translated:return translated
    return value


def label(name):
    names = dict(intro='Intro', preverse='Riff avant couplet', presolo='Riff avant solo',
                 verse='Couplet', chorus='Refrain', solo='Solo', outro='Outro',
                 bridge='Pont', prechorus='Pré-refrain', postchorus='Post-refrain', break_='Break', instrumental='Instrumental')
    names['break']=names.pop('break_')
    return names.get(kind(name), name)


def protected(section):
    return section.get('locked') or section.get('reviewed') or section.get('origin') == 'manual'


def confirmed(section):
    # Accepting a previous batch proposal is not an individual marker review.
    return section.get('reviewed') or section.get('origin') == 'manual'


def reference_anchors(musical,entries,bars,length):
    nearest=lambda t:min(bars,key=lambda b:abs(b-t))
    compatible=lambda a,b:a==b or (a=='instrumental' and b in ('solo','presolo','preverse')) or (a=='intro' and b=='preverse')
    initial=musical[0]['start']-entries[0]['time']
    def pairs(offset,explicit=False):
        result=[]
        for entry in entries:
            candidates=[s for s in musical if (kind(s['name'])==kind(entry['name']) or
                        (not confirmed(s) and compatible(kind(s['name']),kind(entry['name']))))
                        and abs(s['start']-entry['time']-offset)<=(1.8 if explicit else 1.3)
                        and (explicit and confirmed(s) or abs(s['start']-nearest(s['start']))<=.18)]
            candidates.sort(key=lambda s:(not confirmed(s) if explicit else False,abs(s['start']-entry['time']-offset)))
            if not candidates:continue
            if len(candidates)>1:
                a,b=candidates[:2]
                if not explicit or (bool(confirmed(a))==bool(confirmed(b)) and
                    abs(abs(a['start']-entry['time']-offset)-abs(b['start']-entry['time']-offset))<.35):continue
            result.append((entry['time'],candidates[0]['start'],bool(confirmed(candidates[0]))))
        if any(b[1]<=a[1] for a,b in zip(result,result[1:])):return []
        return result
    ordinary=pairs(initial)
    if not any(confirmed(s) for s in musical):
        if len(ordinary)>=3 and ordinary[-1][0]-ordinary[0][0]>=length*.5:return ordinary
        # Rounded website times and vocal pickups need not be exact downbeats.
        # Infer offset from several interior named sections, never the first label.
        stable=[(e['time'],s['start'],False) for e in entries[1:-1] for s in musical
                if kind(s['name'])==kind(e['name']) and kind(e['name']) not in ('intro','instrumental','outro')
                and abs(s['start']-e['time']-initial)<=4]
        options=[]
        for a,b,_ in stable:
            offset=b-a;rows=[x for x in stable if abs((x[1]-x[0])-offset)<=1.0]
            rows=sorted(rows)
            if len(rows)<4 or len({x[0] for x in rows})!=len(rows) or any(y[1]<=x[1] for x,y in zip(rows,rows[1:])):continue
            if rows[-1][0]-rows[0][0]<length*.55:continue
            if any(not .94<=(y[1]-x[1])/(y[0]-x[0])<=1.06 for x,y in zip(rows,rows[1:])):continue
            error=sum(abs((x[1]-x[0])-offset) for x in rows)
            options.append((len(rows),rows[-1][0]-rows[0][0],-error,rows))
        if options:return max(options,key=lambda x:x[:3])[3]
        return ordinary
    offsets={round(s['start']-e['time'],4) for s in musical if confirmed(s) for e in entries
             if kind(s['name'])==kind(e['name']) and abs(s['start']-e['time']-initial)<=max(8,length*.03)}
    candidates={tuple(pairs(offset,True)) for offset in offsets}
    candidates.discard(())
    if not candidates:return ordinary
    score=lambda rows:(sum(x[2] for x in rows),len(rows),rows[-1][0]-rows[0][0])
    ranked=sorted(candidates,key=score,reverse=True)
    if len(ranked)>1 and score(ranked[0])==score(ranked[1]):return []
    best=list(ranked[0]);trusted=[p for p in best if p[2]]
    # Two individually confirmed landmarks establish only their own interval.
    return trusted if len(trusted)>=2 else best


def measures(project):
    from services import beat_grid
    grid, length = beat_grid(project)
    saved = project.get('downbeats', [])
    if project.get('settings', {}).get('gridMode') == 'fixed':
        saved = grid[::int(project['settings']['beatsPerBar'])]
    # A beat list alone does not establish the phase of the measures.
    if len(saved) < 3 or any(not math.isfinite(t) for t in saved): return [], length
    if any(b <= a for a, b in zip(saved, saved[1:])): return [], length
    return [t for t in saved if 0 <= t < length], length


def complete_sections(project, reference):
    sections = copy.deepcopy(project.get('sections', []))
    protected_ids = {s['id'] for s in sections if protected(s)}
    bars, length = measures(project)
    warnings = []; changes = []
    if not reference: return sections, changes, warnings, 0
    if not bars:
        return sections, changes, ['Débuts de mesure insuffisants pour caler la référence.'], 0
    musical = [s for s in sections if normalized(s['name']) not in ('silence', 'silence initial','avant depart')]
    if not musical:
        return sections, changes, ['Repères locaux insuffisants pour comparer la structure.'], 0
    entries = reference['entries']; start = musical[0]['start']
    if abs((length - start) - reference['duration']) > max(4, reference['duration'] * .025):
        return sections, changes, ['Durées incompatibles : la référence peut décrire une autre version.'], 0
    anchors=reference_anchors(musical,entries,bars,length)
    trusted=sum(a[2] for a in anchors)>=2
    if ((not trusted and (len(anchors)<3 or anchors[-1][0]-anchors[0][0]<reference['duration']*.55))
            or (trusted and anchors[-1][0]-anchors[0][0]<8)):
        return sections, changes, ['Pas assez de repères concordants répartis dans le morceau.'], len(anchors)
    if any(b[1]<=a[1] or (abs((b[1]-a[1])-(b[0]-a[0]))>max(2.5,.06*(b[0]-a[0])) if trusted
                          else not .94<=(b[1]-a[1])/(b[0]-a[0])<=1.06) for a,b in zip(anchors,anchors[1:])):
        return sections, changes, ['La référence dérive par rapport au morceau : recalage automatique suspendu.'], len(anchors)

    def mapped(t):
        for a,b in zip(anchors, anchors[1:]):
            if a[0] <= t <= b[0]: return a[1]+(t-a[0])*(b[1]-a[1])/(b[0]-a[0])
        return None

    for entry in entries:
        estimate = mapped(entry['time'])
        if estimate is None: continue  # Never extrapolate beyond established anchors.
        if any(confirmed(s) and abs(s['start']-estimate)<.01 for s in sections):continue
        ranked = sorted(bars, key=lambda b: abs(b-estimate))[:2]
        at = ranked[0]
        if abs(at-estimate) > 1.05 or (len(ranked)>1 and abs(ranked[1]-estimate)-abs(at-estimate) < .25):
            warnings.append('Placement ambigu pour « '+label(entry['name'])+' » : conservé en l’état.'); continue
        current = min(sections, key=lambda s: abs(s['start']-at))
        target_kind = kind(entry['name'])
        if abs(current['start']-at) <= .2:
            # Existing boundaries are never moved. Only clarify a generic label.
            if (not protected(current) and kind(current['name']) != target_kind
                    and (kind(current['name']) in ('intro','instrumental') or target_kind in ('preverse','presolo'))):
                before = current['name']; current['name'] = label(entry['name'])
                current.update(origin='reference', locked=True, reviewed=False)
                changes.append(dict(id=str(uuid.uuid4()), kind='rename', time=current['start'],
                                    before=before, after=current['name'], reason='Repère existant concordant avec la référence.'))
            elif kind(current['name']) != target_kind and protected(current):
                warnings.append('Section protégée conservée : '+current['name']+'.')
            continue
        covering = next((s for s in sections if s['start'] < at < s['end']), None)
        if not covering: continue
        if kind(covering['name']) == target_kind:
            if min(abs(s['start']-at) for s in sections) > .2:
                warnings.append('Départ de « '+label(entry['name'])+' » différent de la référence : anticipation possible, conservée.')
            continue
        if covering['id'] in protected_ids:
            warnings.append('Section protégée conservée : '+covering['name']+'.'); continue
        if min(at-covering['start'], covering['end']-at) < .75:
            warnings.append('Transition trop proche d’un repère existant : conservée.'); continue
        # Do not split a different named passage merely because a website says so.
        if kind(covering['name']) not in ('instrumental','intro','preverse','presolo') and not trusted:
            from section_evidence import supports_change
            if not supports_change(project,at):
                warnings.append('Structure différente pour « '+label(entry['name'])+' » : à vérifier.'); continue
        end = covering['end']; covering['end'] = at
        covering.update(origin='reference', locked=True, reviewed=False)
        new = dict(id=str(uuid.uuid4()), start=at, end=end, name=label(entry['name']),
                   origin='reference', locked=True, reviewed=False)
        sections.append(new); sections.sort(key=lambda s:s['start'])
        changes.append(dict(id=str(uuid.uuid4()), kind='insert', time=at, before=covering['name'],
                            after=new['name'], reason='Passage de la référence retrouvé sur une mesure locale.'))
    # A final heading can clarify the existing ending without extrapolating a
    # new boundary beyond the anchors. Require a whole-song consensus and an
    # already nearby local transition; a live/extended ending therefore abstains.
    if len(anchors)>=4 and kind(entries[-1]['name'])=='outro':
        import statistics
        offset=statistics.median(b-a for a,b,_ in anchors)
        ending=sections[-1]
        if (not protected(ending) and kind(ending['name'])!='outro' and ending['end']>=length-.1
                and abs(ending['start']-(entries[-1]['time']+offset))<=1.6):
            before=ending['name'];ending.update(name='Outro',origin='reference',locked=True,reviewed=False)
            changes.append(dict(id=str(uuid.uuid4()),kind='rename',time=ending['start'],before=before,after='Outro',
                                reason='Fin publiée concordante avec le dernier départ local et les repères répartis dans le morceau.'))
    # A local analysis can split a long solo into two stable passages. Preserve
    # that boundary and clarify its generic continuation instead of losing it.
    for entry,next_entry in zip(entries,entries[1:]):
        start,end=mapped(entry['time']),mapped(next_entry['time'])
        if start is None or end is None or kind(entry['name']) not in ('solo','bridge','preverse','presolo'):continue
        for section in sections:
            if (not protected(section) and kind(section['name'])=='instrumental'
                    and start+.2<section['start']<end-.75 and section['end']<=end+1.3
                    and min(abs(b-section['start']) for b in bars)<=.18):
                before=section['name'];section.update(name=label(entry['name']),origin='reference',locked=True,reviewed=False)
                changes.append(dict(id=str(uuid.uuid4()),kind='rename',time=section['start'],before=before,
                                    after=section['name'],reason='Suite du même passage minuté ; limite locale conservée.'))
    changes.sort(key=lambda c:c['time'])
    return sections, changes, list(dict.fromkeys(warnings)), len(anchors)


def ordered_completion(project,source):
    """Align explicit headings to existing boundaries, never invent durations.

    Forward/backward alignment identifies all optimal matches. A generic passage
    is renamed only when its match and the two surrounding confirmed anchors are
    unambiguous. Repeated or incomplete charts therefore abstain safely.
    """
    local=[s for s in project.get('sections',[]) if kind(s['name']) not in ('silence','silence initial','avant depart')]
    names=source.get('entries',[]);remote=[kind(s) for s in names]
    n,m=len(local),len(remote)
    if not n or not m or n>150 or m>128:return [],[],0
    generic={'instrumental','intro'}
    def score(i,j):
        a,b=kind(local[i]['name']),remote[j]
        if a==b:return 9 if confirmed(local[i]) else 3
        if a in generic and not protected(local[i]):return 0
        return -1000
    forward=[[-10000]*(m+1) for _ in range(n+1)];forward[0][0]=0
    for i in range(n+1):
        for j in range(m+1):
            if i:forward[i][j]=max(forward[i][j],forward[i-1][j]-2)
            if j:forward[i][j]=max(forward[i][j],forward[i][j-1]-2)
            if i and j:forward[i][j]=max(forward[i][j],forward[i-1][j-1]+score(i-1,j-1))
    backward=[[-10000]*(m+1) for _ in range(n+1)];backward[n][m]=0
    for i in range(n,-1,-1):
        for j in range(m,-1,-1):
            if i<n:backward[i][j]=max(backward[i][j],backward[i+1][j]-2)
            if j<m:backward[i][j]=max(backward[i][j],backward[i][j+1]-2)
            if i<n and j<m:backward[i][j]=max(backward[i][j],backward[i+1][j+1]+score(i,j))
    optimum=forward[n][m];matches={}
    for i in range(n):
        choices=[j for j in range(m) if forward[i][j]+score(i,j)+backward[i+1][j+1]==optimum]
        skipped=any(forward[i][j]-2+backward[i+1][j]==optimum for j in range(m+1))
        if len(choices)==1 and not skipped:matches[i]=choices[0]
    anchors={i:j for i,j in matches.items() if confirmed(local[i]) and kind(local[i]['name'])==remote[j]}
    if len(anchors)<2:
        return [],['Ordre trouvé chez '+source['publisher']+' ; deux repères confirmés non ambigus sont nécessaires pour l’adapter.'],len(anchors)
    changes=[];warnings=[]
    for a,b in zip(sorted(anchors),sorted(anchors)[1:]):
        left,right=anchors[a],anchors[b]
        for i in range(a+1,b):
            j=matches.get(i);section=local[i]
            if j is None or not left<j<right or protected(section) or kind(section['name']) not in generic:continue
            if kind(section['name'])==remote[j]:continue
            changes.append(dict(id=str(uuid.uuid4()),kind='rename',time=section['start'],before=section['name'],
                                after=label(names[j]),reason='Ordre publié par '+source['publisher']+' entre deux repères confirmés ; limite locale conservée.'))
        matched={matches[i] for i in range(a,b+1) if i in matches}
        missing=[label(names[j]) for j in range(left+1,right) if j not in matched]
        if missing:warnings.append('Passage signalé par '+source['publisher']+' entre tes repères : '+', '.join(missing)+'. Position non établie, aucun découpage inventé.')
    return changes,warnings,len(anchors)


def combine_references(project,timed,sources):
    sections,changes,warnings,anchors=complete_sections(project,timed)
    candidates={}
    for change in changes:candidates.setdefault(round(change['time'],6),[]).append(change)
    for source in sources:
        if source.get('format')!='order':continue
        extra,notes,count=ordered_completion(project,source)
        anchors=max(anchors,count);warnings.extend(notes)
        for change in extra:candidates.setdefault(round(change['time'],6),[]).append(change)
    conflicts={at for at,items in candidates.items() if len({kind(c['after']) for c in items})>1}
    # Conservatively cancel the timed batch if another usable chart contradicts
    # one of its placements; protected source sections still remain untouched.
    if conflicts:
        sections=copy.deepcopy(project['sections']);changes=[]
        warnings.append('Sources en désaccord sur un passage : changements de structure suspendus, repères actuels conservés.')
        return sections,changes,list(dict.fromkeys(warnings)),anchors
    changed={round(c['time'],6) for c in changes}
    for at,items in candidates.items():
        if at in changed:continue
        change=items[0];section=next((s for s in sections if abs(s['start']-change['time'])<1e-6),None)
        if section is None or protected(section):continue
        section.update(name=change['after'],origin='reference',locked=True,reviewed=False);changes.append(change)
    return sections,sorted(changes,key=lambda c:c['time']),list(dict.fromkeys(warnings)),anchors


def memory_proposal(project):
    """Fast path used before running missing analyses on a renamed re-import."""
    from song_memory import remember,recall,grid,discover
    validate_document(project)
    try:
        remember(project)
        found,status=recall(project)
        if status=='not_found':
            discover(project);found,status=recall(project)
    except (OSError,ValueError):return None
    if not found:return None
    restored=found['project']
    try:validate_document(restored)
    except (OSError,ValueError,KeyError,TypeError):return None
    musical=lambda rows,key:[(s['start'],s['end'],s[key]) for s in rows]
    if (musical(restored['sections'],'name')==musical(project['sections'],'name') and
            musical(restored.get('chords',[]),'text')==musical(project.get('chords',[]),'text') and grid(restored)==grid(project)):
        return None
    return dict(schema=SCHEMA,id=str(uuid.uuid4()),fingerprint=fingerprint(project),createdAt=time.time(),status='proposed',
                message='Préparation du même enregistrement retrouvée : '+found['name']+'.',sources=[],sourceChecks=[],
                confirmedSections=sum(bool(confirmed(s)) for s in project['sections']),anchors=0,changes=[],warnings=[],
                sections=restored['sections'],chords=restored.get('chords',[]),chordReference=restored.get('chordReference'),
                chordUpdate=musical(restored.get('chords',[]),'text')!=musical(project.get('chords',[]),'text'),
                restoredGrid=grid(restored),memory=dict(name=found['name'],scope=found['scope'],sections=found['sections'],chords=found['chords']),
                reviewPassages=[],repeatedGroups=0,transferredPhrases=0)


def propose(project, reference=None):
    validate_document(project)
    remembered=memory_proposal(project)
    if remembered:return remembered
    signature = fingerprint(project)
    from structure_sources import collect,chart_references
    proposed=copy.deepcopy(project)
    if reference is None:
        found=collect(project,lookup);reference=found['timed'];source_note=found['note']
        sources=found['sources'];checks=found['checks'];proposed['chordReference']=found['chart']
    else:
        sources,checks=chart_references(project.get('chordReference'))
        sources.insert(0,{**reference,'format':'timed'});source_note=''
    from section_evidence import refine
    from musical_patterns import describe,used_roles,ROLE_LABELS
    features=None
    try:
        features=describe(proposed)
        proposed['sections'],adjustments=refine(proposed,features)
    except (OSError,ValueError):adjustments=[]
    sections,changes,warnings,anchors=combine_references(proposed,reference,sources)
    from section_functions import analyse as functions
    functional=functions(proposed,features,reference,sections)
    sections=functional['sections']
    if functional['evidence']['timedAnchors']>=3:
        # The offset/interior fit resolves these initial whole-file failures.
        # Keep other source conflicts and protected-region notices visible.
        obsolete=('Durées incompatibles :','Pas assez de repères concordants','La référence dérive par rapport au morceau :')
        warnings=[w for w in warnings if not w.startswith(obsolete)]
    changes=sorted(adjustments+functional['changes']+changes,key=lambda c:c['time'])
    warnings=functional['warnings']+warnings
    anchors=max(anchors,functional['evidence']['timedAnchors'])
    if source_note:
        warnings.insert(0,source_note)
    proposed['sections']=sections
    from musical_patterns import analyse as patterns,transfer_chords,listening_plan
    try:
        pattern=patterns(proposed,features)
        sections=pattern['sections'];changes.extend(pattern['changes']);proposed['sections']=sections
    except (OSError,ValueError):
        pattern=dict(groups=[],pairs=[])
        warnings.append('Comparaison audio des répétitions indisponible : aucune répétition supposée.')
    from musical_timing import align_section_grid
    sections,alignment=align_section_grid(proposed,force=True,
        protected_ids=[s['id'] for s in project['sections'] if protected(s)])
    proposed['sections']=sections
    for change in alignment:
        section=next(s for s in sections if s['id']==change['id'])
        changes.append(dict(id=str(uuid.uuid4()),kind='adjust',time=change['after'],
            before=section['name'],after=section['name'],
            reason=f"Début calé sur une mesure entière : {change['before']:.3f} s → {change['after']:.3f} s."))
    chord_update = False
    # Reuse a successful chart; retry old failures without doing the same failed
    # request twice immediately after the existing "prepare all" pipeline.
    from chord_sources import analyze, apply, lookup as lookup_chords
    saved_chart = proposed.get('chordReference') or {}
    if not saved_chart.get('sources') and time.time()-saved_chart.get('checkedAt', 0) > 60:
        found = lookup_chords(project)
        proposed['chordReference'] = found['reference']
    charts = (proposed.get('chordReference') or {}).get('sources', [])
    if charts:
        source = next((s for s in charts if s['url'] == proposed['chordReference'].get('selectedURL')), charts[0])
        from advanced import media_path
        track = next((t for t in project['tracks'] if t['role']=='source'), None)
        if track:
            try:
                result = analyze(proposed, media_path(project['_root'], track['file']), ordered=True,phrase_groups=pattern['groups'])
                if result.get('segments'):
                    apply(proposed, result)
                    musical=lambda rows:[(round(c['start'],6),round(c['end'],6),c['text']) for c in rows]
                    chord_update=musical(proposed['chords'])!=musical(project.get('chords',[]))
                    alignment = result['reference'].get('alignment', {})
                    if alignment.get('uncertainCells'):
                        warnings.append('Certains accords restent incertains : leurs positions sont proposées, pas confirmées.')
                    if not (alignment.get('orderedSections') or alignment.get('orderedChart')):
                        warnings.append('Ordre des accords par section non confirmé par la source et l’audio.')
                else: warnings.append('Calage des accords non obtenu : accords actuels conservés.')
            except (OSError, ValueError):
                warnings.append('Calage des accords indisponible : accords actuels conservés.')
    else:
        warnings.append('Aucune grille d’accords Internet disponible : accords actuels conservés.')
    proposed['chords'],transfers=transfer_chords(proposed,pattern,features)
    musical=lambda rows:[(round(c['start'],6),round(c['end'],6),c['text']) for c in rows]
    chord_update=musical(proposed.get('chords',[]))!=musical(project.get('chords',[]))
    passages=listening_plan(proposed,changes,pattern)
    if fingerprint(project) != signature:
        raise ValueError('Un média a changé pendant la comparaison. Relance la vérification.')
    return dict(schema=SCHEMA, id=str(uuid.uuid4()), fingerprint=signature, createdAt=time.time(),
                status='proposed', message='Proposition prête à valider.' if changes or chord_update else 'Préparation actuelle conservée.',
                sources=[dict(title=(s['title']+' — '+s['artist']) if s.get('artist') else s['title'],publisher=s['publisher'],
                              url=s['url'],format=s['format'],sectionNames=[e['name'] for e in s['entries']] if s['format']=='timed' else s['entries']) for s in sources],
                sourceChecks=checks,confirmedSections=sum(confirmed(s) for s in project['sections']),
                audioEvidence=[ROLE_LABELS[r] for r in used_roles(features or {})],
                reviewPassages=passages,repeatedGroups=len(pattern['groups']),transferredPhrases=len(transfers),
                anchors=anchors, changes=sorted(changes,key=lambda c:c['time']), warnings=list(dict.fromkeys(warnings)),
                sections=sections, chords=proposed.get('chords', []), chordReference=proposed.get('chordReference'), chordUpdate=chord_update)


def apply_proposal(project):
    proposal = project.get('structureProposal') or {}
    if proposal.get('status')=='prepared':
        raise ValueError('Cette préparation a déjà été appliquée au morceau.')
    if proposal.get('schema') != SCHEMA or proposal.get('fingerprint') != fingerprint(project):
        raise ValueError('Le morceau a changé depuis la proposition. Relance Vérifier et compléter.')
    uuid.UUID(proposal['id'])
    result = copy.deepcopy(project)
    result['sections'] = copy.deepcopy(proposal['sections'])
    result['chords'] = copy.deepcopy(proposal['chords'])
    result['chordReference'] = copy.deepcopy(proposal.get('chordReference'))
    restored=proposal.get('restoredGrid')
    if restored:
        from song_memory import GRID_KEYS,grid
        if (project.get('gridLocked') or project['settings'].get('gridMode')=='fixed') and restored!=grid(project):
            raise ValueError('La grille protégée ne peut pas être remplacée par une préparation mémorisée.')
        for key in ('bpm','beats','downbeats','gridLocked'):result[key]=copy.deepcopy(restored[key])
        result['settings'].update({k:restored[k] for k in GRID_KEYS if restored.get(k) is not None})
    result.pop('structureProposal', None)
    validate_document(result)
    # Defence in depth: saved proposals cannot bypass protected musical edits.
    for section in project['sections']:
        if protected(section) and section not in result['sections']:
            raise ValueError('Une section protégée a changé dans la proposition.')
    for chord in project.get('chords', []):
        if chord.get('manual') and chord not in result['chords']:
            raise ValueError('Un accord manuel a changé dans la proposition.')
    return result


def save_proposal(snapshot,output):
    """Return a validated document for the host's normal save/undo transaction."""
    original=json.loads(Path(snapshot).read_text())
    project=apply_proposal(original)
    project['guideKey']=''  # Rebuild announcements for the new sections on playback.
    if project.get('preparation'):
        project['preparation'].pop('fingerprint',None)
        project['preparation'].pop('validatedAt',None)
    if fingerprint(original)!=original['structureProposal']['fingerprint']:
        raise ValueError('Un média a changé pendant la validation. Relance la vérification.')
    atomic(output,dict(project=project))
    record_decision(project['_root'],original['structureProposal'],'accepted_in_project',fingerprint(project))


def finish_preparation(snapshot,output,engine):
    """Finish one-click preparation, retaining a visual before/after receipt.

    This is an automatic analysis, not a human approval or a training label.
    Manually protected regions/chords pass the same defence as explicit apply.
    """
    original=json.loads(Path(snapshot).read_text())
    signature=fingerprint(original)
    proposal=propose(original)
    result=apply_proposal({**original,'structureProposal':proposal})
    fixed={s['id'] for s in original['sections'] if protected(s)}
    # Automatic refinements must remain refinable on a later preparation.
    for section in result['sections']:
        if section['id'] not in fixed and section.get('origin')=='reference':
            section.update(locked=False,reviewed=False,origin='automatic-review')
    proposal.update(status='prepared',beforeSections=copy.deepcopy(original['sections']),sections=copy.deepcopy(result['sections']),
                    message='Préparation terminée. Les améliorations sont appliquées ; les passages signalés restent à écouter.')
    roles={t['role'] for t in result['tracks']}
    for names,label in (({'drum_kick','drum_snare','drum_toms','drum_cymbals'},'Éléments de batterie'),({'vocal_lead','vocal_backing'},'Chant principal et chœurs')):
        if not names<=roles:proposal['warnings'].append(label+' : séparation complète indisponible ; les pistes existantes sont conservées.')
    result['guideKey']=''
    if result.get('preparation'):
        result['preparation'].pop('fingerprint',None);result['preparation'].pop('validatedAt',None)
    proposal['fingerprint']=fingerprint(result)
    result['structureProposal']=proposal
    validate_document(result)
    if fingerprint(original)!=signature:
        raise ValueError('Un média a changé pendant la préparation.')
    atomic(output,dict(project=result))
    record_decision(result['_root'],{**proposal,'fingerprint':signature},'prepared_automatically',proposal['fingerprint'])


def export_proposal(snapshot, output, engine):
    """Prepare a new portable export, committing the document only on success.

    Hosts receive the finished document and use their existing undo/save paths.
    A failed worker never replaces project.json or an existing REAPER session.
    """
    from services import guides
    from preparation import validate_project, export_validated
    from windows.project import guide_track, guide_key
    original = json.loads(Path(snapshot).read_text())
    project = apply_proposal(original)
    work = Path(output).parent; root = Path(project['_root'])
    prepared = work / 'reviewed-project.json'
    atomic(prepared, project)
    guide_folder = root / 'Guides' / ('review-' + str(uuid.uuid4()))
    try:
        if project['settings'].get('exportGuides'):
            guide_result = work / 'review-guides.json'
            guides(prepared, guide_result)
            result = json.loads(guide_result.read_text())
            guide_folder.mkdir(parents=True)
            mapping = {}
            for i,(key,value) in enumerate(result['files'].items()):
                source = Path(value).resolve()
                if not source.is_relative_to(work.resolve()) or not source.is_file():
                    raise ValueError('Guide hors du dossier de préparation.')
                target = guide_folder / (str(i)+'.wav'); shutil.copy2(source, target)
                mapping[key] = target.relative_to(root).as_posix()
            project['guideFiles'] = mapping
            previous_guides = project['tracks']
            project['tracks'] = [t for t in previous_guides if not t['role'].startswith('guide_')]
            for key,name,role in [('click','Métronome','guide_click'),('calls','Appels de régions','guide_voice'),
                                  ('cues','Cues','guide_cue'),('counts','Décomptes','guide_count')]:
                project['tracks'].append(guide_track(root/mapping[key], root, name, role, previous_guides))
            project['guideKey'] = guide_key(project)
        else:
            project['guideKey'] = ''  # Old guides must not be reused after section edits.
        atomic(prepared, project)
        validate_project(prepared, work/'review-validation.json')
        project['preparation'] = json.loads((work/'review-validation.json').read_text())['preparation']
        atomic(prepared, {**project, '_exportChordTrack': True})
        # Bind export to the media version that the user approved in the preview.
        if fingerprint(original) != original['structureProposal']['fingerprint']:
            raise ValueError('Un média a changé pendant la préparation de l’export.')
        export_validated(prepared, work/'review-export.json', engine)
        exported = json.loads((work/'review-export.json').read_text())
        record_decision(root, original['structureProposal'], 'accepted_for_export', fingerprint(project))
        atomic(output, dict(project=project, **exported))
        # The successful user-approved preparation may be recalled on exactly
        # the same audio. It is not added to general model training labels.
        from song_memory import remember
        try:remember(project,accepted=True)
        except (OSError,ValueError):pass
    except Exception:
        shutil.rmtree(guide_folder, ignore_errors=True)
        raise
