"""Conservative audio checks for proposed structure, never manual boundaries."""
from ui_language import ui_text, using_english
import copy
import math
import uuid
from pathlib import Path
import numpy as np


def boundary(features,time,window=2.):
    middle=features['middle'];left=(middle>=time-window)&(middle<time);right=(middle>=time)&(middle<time+window)
    if left.sum()<2 or right.sum()<2:return None
    evidence={}
    def covered(key):
        coverage=features.get(key+'Coverage')
        return coverage is None or min(coverage[left].mean(),coverage[right].mean())>=.9
    for key in ('harmony','bass','texture'):
        x=features[key][left].mean(axis=0);y=features[key][right].mean(axis=0)
        usable=covered('harmony' if key=='texture' else key) and min(np.linalg.norm(x),np.linalg.norm(y))>=.05
        evidence[key]=float(1-x@y/max(np.linalg.norm(x)*np.linalg.norm(y),1e-9)) if usable else 0.
    for key in ('voice','drums'):
        evidence[key]=abs(float(features[key+'Energy'][left].mean()-features[key+'Energy'][right].mean())) if covered(key) else 0.
    from musical_patterns import used_roles,HARMONIC_ROLES,VOICE_ROLES,DRUM_ROLES
    roles=used_roles(features)
    harmonic=[r for r in roles if r in HARMONIC_ROLES]
    level=max((float(features[r+'_level']) for r in harmonic),default=0)
    for role in roles:
        energy=features[role+'_energy'];coverage=features[role+'_coverage']
        if min(coverage[left].mean(),coverage[right].mean())<.9:continue
        if role in harmonic and float(features[role+'_level'])>=max(1e-5,.12*level):
            x=features[role+'_chroma'][left].mean(axis=0);y=features[role+'_chroma'][right].mean(axis=0)
            if min(energy[left].mean(),energy[right].mean())>.08 and min(np.linalg.norm(x),np.linalg.norm(y))>=.05:
                novelty=float(1-x@y/(np.linalg.norm(x)*np.linalg.norm(y)))
                evidence['harmony']=max(evidence['harmony'],novelty)
        family='voice' if role in VOICE_ROLES else 'drums' if role in DRUM_ROLES else None
        if family:evidence[family]=max(evidence[family],abs(float(energy[left].mean()-energy[right].mean())))
    return evidence


def supports_change(project,time,features=None):
    from musical_patterns import describe
    if features is None:
        try:features=describe(project)
        except (OSError,ValueError):return False
    if features is None:return False
    e=boundary(features,time)
    if not e:return False
    # Harmony and its timbre are one family; four drum stems are also one.
    return sum((e['harmony']>.12 or e['texture']>.08,e['bass']>.30,e['voice']>.30,e['drums']>.30))>=2


def _line_entries(project):
    return [line['words'][0] for line in project.get('lyrics', []) if line.get('words')]


def _attack(stream, time):
    """Local rise in channel power around a timestamp, independent of track gain."""
    hop = max(1, round(stream.samplerate * .01))
    start = round(time * stream.samplerate) - 10 * hop
    if start < 0 or start + 18 * hop > stream.frames:
        return 0.
    stream.seek(start)
    audio = stream.read(18 * hop, dtype='float32', always_2d=True)
    energy = np.sqrt(np.mean(audio.reshape(18, hop, -1) ** 2, axis=(1, 2)))
    peak = float(max(energy[8:16]))
    return max(0., peak - float(np.median(energy[:7]))) / max(peak, .003)


def _arrival_in_audio(project, downbeat, marker, pulse):
    import soundfile as sf
    from preparation import media_file
    if not project.get('_root'):
        return None
    labels = {'drums':'la batterie', 'drum_kick':'la grosse caisse', 'bass':'la basse', 'source':'le mix'}
    for role, label in labels.items():
        for track in project.get('tracks', []):
            if track['role'] != role or not track.get('file'):
                continue
            offset = track.get('offset', 0)
            try:
                with sf.SoundFile(media_file(Path(project['_root']), track['file'])) as stream:
                    on_bar = _attack(stream, downbeat - offset)
                    on_marker = _attack(stream, marker - offset)
            except (OSError, RuntimeError, ValueError):
                continue
            # Two windows separated by just a few tens of ms can contain the same attack.
            same_attack = marker - downbeat <= .1 * pulse and on_bar >= on_marker - .05
            if on_bar >= .40 and (same_attack or on_bar >= on_marker + .15):
                return label
    return None


def align_bar_arrivals(project):
    """Correct late automatic boundaries only when the local musical attack agrees."""
    from musical_timing import BeatClock
    from structure_review import protected
    rows = copy.deepcopy(project.get('sections', []))
    changes = []
    if not rows:
        return rows, changes
    clock = BeatClock(project)
    fixed = project.get('settings', {}).get('gridMode') == 'fixed'
    if not fixed and (not clock.detected or (not project.get('gridLocked') and clock.confidence < .85)):
        return rows, changes
    entries = _line_entries(project)
    for previous, current in zip(rows, rows[1:]):
        old = current['start']
        if (protected(previous) or protected(current) or abs(previous['end'] - old) > 1e-7
                or previous.get('announce') is False or current.get('announce') is False):
            continue
        index = math.floor(clock.coordinate(old) / clock.meter) * clock.meter
        bar = clock.at(index)
        pulse = clock.at(index + 1) - bar
        if not (1e-6 < old - bar <= pulse / 2):
            continue
        # The attack must be inside two substantial sections, never a short break or pickup.
        if previous['start'] > clock.at(index - clock.meter) + 1e-7 or current['end'] < clock.at(index + clock.meter) - 1e-7:
            continue
        if clock.detected and not fixed:
            observed = project.get('beats', [])
            if not observed or not observed[0] <= bar <= observed[-1]:
                continue
        nearby = [w for w in entries if bar - .15 * pulse <= w['start'] <= old + .15 * pulse]
        if any(not w.get('timingReview') and abs(w['start'] - old) < abs(w['start'] - bar)
               and w['start'] - bar > .15 * pulse for w in nearby):
            continue
        vocal = any(not w.get('timingReview') and abs(w['start'] - bar) <= .15 * pulse
                    and abs(w['start'] - bar) < abs(w['start'] - old) for w in nearby)
        source = 'le chant' if vocal else _arrival_in_audio(project, bar, old, pulse)
        if source:
            previous['end'] = current['start'] = bar
            changes.append(dict(id=str(uuid.uuid4()), kind='adjust', time=bar, before=current['name'], after=current['name'],
                                reason=(f'Start moved from {old:.3f} s to {bar:.3f} s, on the downbeat heard in {source}.' if using_english() else f'Début ramené de {old:.3f} s à {bar:.3f} s sur le premier temps entendu dans {source}.')))
    # The structure model reports its last analysis frame; keep the final audio samples in the section.
    tail = rows[-1]
    duration = clock.basis['duration']
    if (tail.get('origin') in ('analysis', 'automatic-review', 'intro-calibration') and not protected(tail)
            and 0 < duration - tail['end'] <= .05):
        tail['end'] = duration
    return rows, changes


def refine(project,features=None):
    from musical_patterns import describe
    from structure_review import protected,measures
    rows=copy.deepcopy(project.get('sections',[]));changes=[]
    from musical_timing import BeatClock
    bars,_=measures(project);beats=np.asarray(BeatClock(project).beats)
    if not bars or len(beats)<4:return rows,changes
    if features is None:features=describe(project)
    if features is None:return rows,changes
    entries=_line_entries(project)
    for i in range(1,len(rows)):
        previous,current=rows[i-1:i+1];old=current['start']
        if protected(previous) or protected(current) or abs(previous['end']-old)>.001:continue
        if old-previous['start']<4 or current['end']-old<4:continue
        near=beats[np.abs(beats-old)<3]
        if len(near)<3:continue
        pulse=float(np.median(np.diff(near)));radius=min(1.3,1.35*pulse)
        # A cue already on a pulse may deliberately anticipate a chord. Only
        # off-pulse model estimates can move backwards to a stronger arrival.
        off_pulse=min(abs(near-old))>.18*pulse
        candidates=[b for b in bars if .35*pulse<abs(b-old)<=radius and (b>old or off_pulse)
                    and previous['start']+2<b<current['end']-2]
        before=boundary(features,old)
        if not candidates or not before:continue
        ranked=[]
        for at in candidates:
            if 0 < at-old <= .5*pulse and any(old-.1*pulse <= w['start'] < at for w in entries):
                continue  # A sung pickup belongs to the incoming section.
            e=boundary(features,at)
            # Joint harmonic/bass novelty, not a loud fill or a vocal pickup.
            if not e or e['harmony']<.17 or e['bass']<.30:continue
            score=e['harmony']+e['bass']
            if score<(before['harmony']+before['bass'])*1.28+.025:continue
            # Require the same arrival on a short window. A loud fill/change
            # elsewhere in the surrounding two seconds cannot move the cue.
            short=boundary(features,at,max(.6,1.5*pulse))
            if not short or short['harmony']<.17 or short['bass']<.30:continue
            ranked.append((score,at))
        ranked.sort(reverse=True)
        if not ranked or (len(ranked)>1 and ranked[0][0]-ranked[1][0]<.10):continue
        _,at=ranked[0];previous['end']=at;current['start']=at
        changes.append(dict(id=str(uuid.uuid4()),kind='adjust',time=at,before=current['name'],after=current['name'],
                            reason=(f'Suggested start at {at:.2f} s instead of {old:.2f} s: harmony and bass agree over a local bar at two listening scales.' if using_english() else f'Début proposé à {at:.2f} s au lieu de {old:.2f} s : harmonie et basse concordantes sur une mesure locale, à deux échelles d’écoute.')))
    return rows,changes
