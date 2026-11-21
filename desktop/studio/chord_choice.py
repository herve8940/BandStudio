"""Choose a published chart for this recording, without inventing popularity.

Public ratings are only a small tie-breaker. Harmonic agreement with the actual
recording comes first; a source explicitly chosen by the musician always wins.
"""
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


def choose(project,sources,features=None):
    if not sources:raise ValueError('Aucune grille à comparer.')
    reference=project.get('chordReference') or {}
    selected=next((s for s in sources if s['url']==reference.get('selectedURL')),None)
    if selected and reference.get('selectionMode','manual')=='manual':
        return selected,'Ta grille choisie est conservée.'
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
    for index,source in enumerate(sources):
        templates=[]
        for chord in source['chords']:
            notes=tones(chord)
            if not notes:continue
            vector=np.zeros(12);vector[notes[0]]=1;vector/=max(np.linalg.norm(vector),1e-9);templates.append(vector)
        acoustic=float(np.mean(np.max(cells@np.array(templates).T,axis=1))) if cells is not None and templates else None
        rating=source.get('rating',3.5);count=source.get('ratingCount',0)
        if not isinstance(rating,(int,float)) or not math.isfinite(rating) or not 0<=rating<=5:rating=3.5
        if not isinstance(count,int) or not 0<=count<10**9:count=0
        # Ten neutral prior votes limit the effect of a single public review.
        public=(35+rating*count)/(10+count)/5
        score=(acoustic if acoustic is not None else 0)+.025*public-.001*max(0,len(templates)-18)
        ranked.append((score,-index,source,acoustic))
    _,_,chosen,acoustic=max(ranked,key=lambda row:row[:2])
    if acoustic is None:
        reason='Source publiée retenue parmi '+str(len(sources))+' grilles disponibles ; concordance audio non mesurable.'
    else:
        reason='Grille retenue parmi '+str(len(sources))+' sources pour sa concordance harmonique avec ton enregistrement.'
        if acoustic<.65:reason+=' Concordance limitée : accords à écouter.'
    return chosen,reason
