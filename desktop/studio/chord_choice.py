"""Choose a published chart for this recording, without inventing popularity.

Public ratings are only a small tie-breaker. Harmonic agreement with the actual
recording comes first; a source explicitly chosen by the musician always wins.
"""
from ui_language import ui_text
from html.parser import HTMLParser
import json
import math


def reputation(page,title):
    class Ratings(HTMLParser):
        def __init__(self):super().__init__();self.active=False;self.parts=[];self.blocks=[]
        def handle_starttag(self,tag,attrs):
            if tag=='script':self.active=dict(attrs).get('type')=='application/ld+json';self.parts=[]
        def handle_data(self,text):
            if self.active:self.parts.append(text)
        def handle_endtag(self,tag):
            if tag=='script' and self.active:self.blocks.append(''.join(self.parts));self.active=False
    parser=Ratings();parser.feed(page)
    def walk(obj,depth=0):
        if depth>8:return None
        if isinstance(obj,list):
            return next((found for item in obj[:100] if (found:=walk(item,depth+1))),None)
        if not isinstance(obj,dict):return None
        rating=obj.get('aggregateRating')
        from chord_sources import normalized
        chart_name=normalized(str(obj.get('name','')))
        song_name=normalized(title)
        if isinstance(rating,dict) and song_name and (' '+song_name+' ') in (' '+chart_name+' '):
            try:
                value=float(rating['ratingValue']);count=int(rating.get('ratingCount',rating.get('reviewCount',0)));best=float(rating.get('bestRating',5))
                if math.isfinite(value+best) and best>0 and 0<=value<=best and 0<count<10**9:return dict(rating=round(value/best*5,3),ratingCount=count)
            except (ValueError,TypeError,KeyError,OverflowError):pass
        return walk(obj.get('@graph'),depth+1)
    for block in parser.blocks[:20]:
        try:found=walk(json.loads(block))
        except (ValueError,TypeError):continue
        if found:return found
    return {}


def recording_shift(features, templates, roots):
    """Change a chart's key only when independent bass and harmony agree across the song."""
    import numpy as np
    from musical_patterns import HARMONIC_ROLES,used_roles
    roles=used_roles(features)
    if 'bass' not in roles or not set(HARMONIC_ROLES).intersection(roles) or len(set(roots))<3:
        return 0
    active=(features['harmonyCoverage'] & features['bassCoverage'] &
            (features['harmonyEnergy']>.12) & (features['bassEnergy']>.12))
    cells=np.flatnonzero(active)
    if len(cells)<64:return 0
    cells=cells[::math.ceil(len(cells)/1024)]
    quarters=4*cells//len(active)
    if min(np.bincount(quarters,minlength=4))<8:return 0
    harmony=features['harmony'][cells];bass=features['bass'][cells]
    roots=np.asarray(roots);templates=np.asarray(templates)
    scores=[];harmonic_scores=[];winners=[]
    for shift in range(12):
        similarity=harmony@np.roll(templates,shift,axis=1).T
        combined=similarity+.35*bass[:,(roots+shift)%12]
        scores.append(combined.max(axis=1))
        harmonic_scores.append(similarity.max(axis=1).mean())
        winners.append(combined.argmax(axis=1))
    scores=np.asarray(scores);means=scores.mean(axis=1)
    best,runner=means.argsort()[-2:][::-1]
    if (best==0 or best!=np.argmax(harmonic_scores) or means[best]-means[0]<.12 or
            means[best]-means[runner]<.05 or
            any(scores[:,quarters==q].mean(axis=1).argmax()!=best for q in range(4))):
        return 0
    _,counts=np.unique(roots[winners[best]],return_counts=True)
    if np.count_nonzero(counts>=len(cells)*.04)<3:return 0
    return int(best if best<=6 else best-12)


def choose(project,sources,features=None):
    if not sources:raise ValueError(ui_text('Aucune grille à comparer.', 'No charts to compare.'))
    reference=project.get('chordReference') or {}
    selected=next((s for s in sources if s['url']==reference.get('selectedURL')),None)
    manual=selected is not None and reference.get('selectionMode','manual')=='manual'
    if features is None:
        from musical_patterns import describe
        try:features=describe(project)
        except (OSError,ValueError,KeyError):features=None
    import numpy as np
    from chord_alignment import tones
    cells=None
    if features is not None:
        mask=features['harmonyCoverage']&(features['harmonyEnergy']>.12)
        if mask.sum()>=32:cells=features['harmony'][mask]
    ranked=[]
    for index,source in enumerate([selected] if manual else sources):
        templates=[];roots=[]
        for chord in source['chords']:
            notes=tones(chord)
            if not notes:continue
            vector=np.zeros(12);vector[notes[0]]=1;vector/=np.linalg.norm(vector);templates.append(vector);roots.append(notes[1])
        shift=recording_shift(features,templates,roots) if cells is not None else 0
        if shift:
            from chord_sources import transposed_chart
            source={**transposed_chart(source,shift),'recordingTranspose':shift}
            templates=np.roll(templates,shift,axis=1).tolist()
        acoustic=float(np.mean(np.max(cells@np.array(templates).T,axis=1))) if cells is not None and templates else None
        rating=source.get('rating',3.5);count=source.get('ratingCount',0)
        if not isinstance(rating,(int,float)) or not math.isfinite(rating) or not 0<=rating<=5:rating=3.5
        if not isinstance(count,int) or not 0<=count<10**9:count=0
        # Ten neutral prior votes limit the effect of a single public review.
        public=(35+rating*count)/(10+count)/5
        score=(acoustic if acoustic is not None else 0)+.025*public-.001*max(0,len(templates)-18)-(.025 if shift else 0)
        ranked.append((score,-index,source,acoustic))
    _,_,chosen,acoustic=max(ranked,key=lambda row:row[:2])
    if manual:
        reason=ui_text('Ta grille choisie est conservée.', 'Your selected chart has been kept.')
    elif acoustic is None:
        reason=ui_text('Source publiée retenue parmi ', 'Published source selected from ')+str(len(sources))+ui_text(' grilles disponibles ; concordance audio non mesurable.', ' charts available. Audio agreement could not be measured.')
    else:
        reason=ui_text('Grille retenue parmi ', 'Chart selected from ')+str(len(sources))+ui_text(' sources pour sa concordance harmonique avec ton enregistrement.', ' sources for its harmonic match with your recording.')
        if acoustic<.65:reason+=ui_text(' Concordance limitée : accords à écouter.', ' Limited agreement. Check the chords by ear.')
    return chosen,reason
