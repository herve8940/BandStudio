"""Reference-first lyrics: lexical anchors locate audio, never generate new text.

Estimated positions select acoustic windows only. A failed acoustic alignment
keeps the reference text with no word timings, explicitly requiring review.
"""
from collections import Counter
from difflib import SequenceMatcher
import copy
import math
import re


def lexical(text):
    from lyrics_reference import tokens, key
    return [key(w) for w in tokens(text)]


def artifact(text):
    value = ' '.join(lexical(text))
    return bool(re.search(r'amara|sous titres realises|subtitles by|thanks for watching|merci d avoir regarde', value))


def observed_words(segments):
    """Rejoin Whisper's split apostrophes without inventing word timestamps."""
    from lyrics_reference import tokens, key
    result = []
    for row_index,row in enumerate(segments):
        if artifact(row.get('text', '')):
            continue
        words = tokens(row.get('text', ''))
        raw = row.get('words', [])
        chars, owners = '', []
        for w in raw:
            value = key(w.get('w', w.get('text', '')))
            chars += value
            owners.extend([w] * len(value))
        text = ''.join(map(key, words))
        mapping = {}
        for block in SequenceMatcher(None, text, chars, autojunk=False).get_matching_blocks():
            for k in range(block.size):
                mapping[block.a+k] = owners[block.b+k]
        cursor = 0
        for word in words:
            size = len(key(word))
            matched = [mapping.get(i) for i in range(cursor, cursor+size)]
            cursor += size
            timed = bool(matched) and all(w is not None for w in matched)
            start = matched[0].get('t', matched[0].get('start')) if timed else row.get('t', row.get('start', 0))
            end = matched[-1]['end'] if timed else row['end']
            result.append(dict(text=word, t=start, end=end, timed=timed, segment=row_index,manual=bool(row.get('manual'))))
    return result


def plan(segments, text):
    from lyrics_reference import tokens, key, match_words
    texts = [line.strip() for line in text.splitlines() if tokens(line)]
    rows = [tokens(line) for line in texts]
    words = [word for row in rows for word in row]
    observed = observed_words(segments)
    pairs, agreement = match_words([w['text'] for w in observed], words)
    a, b = [key(w['text']) for w in observed], list(map(key, words))
    counts_a, counts_b = Counter(a), Counter(b)
    exact = {(i, j) for i, j in pairs if i is not None and j is not None and a[i] == b[j]}
    stop = {'le','la','les','des','du','de','un','une','a','et','en','au','aux','que','qui','dans',
            'the','a','an','and','to','of','in','on','is','it','i','you','we','my','your','el','y','los'}
    anchors = []
    for i, j in sorted(exact):
        word = observed[i]
        context = ((i-1,j-1) in exact or (i+1,j+1) in exact)
        distinctive = len(b[j]) >= 6 and counts_a[b[j]] == counts_b[b[j]] == 1
        if b[j] in stop or not (context or distinctive) or not word['timed']:
            continue
        if not (math.isfinite(word['t']) and math.isfinite(word['end']) and 0 <= word['t'] < word['end']):
            continue
        if anchors and word['t'] < anchors[-1]['end']:
            continue
        anchors.append(dict(index=j, t=word['t'], end=word['end']))
    # Several distinctive matches spread through the song identify a heavily
    # damaged transcript. Common isolated words alone cannot confirm a song.
    supported = sum(a[i] not in stop and len(a[i]) >= 4 for i,j in exact)
    spread = (anchors[-1]['index']-anchors[0]['index'])/max(1,len(words)-1) if anchors else 0
    confirmed = bool(words) and (agreement >= .45 or
        (agreement >= .2 and supported >= 8 and len(anchors) >= 6 and spread >= .55))
    # Even a misspelt ASR phrase may retain its correct utterance boundaries.
    # Keep these as search hints only, never as final word timestamps.
    owners=[n for n,row in enumerate(rows) for _ in row];votes=[Counter() for _ in rows]
    for i,j in pairs:
        if i is not None and j is not None:votes[owners[j]][observed[i]['segment']]+=1
    hints=[]
    for n,vote in enumerate(votes):
        row=segments[vote.most_common(1)[0][0]] if vote else {}
        similarity=SequenceMatcher(None,key(texts[n]),key(row.get('text','')),autojunk=False).ratio()
        start=row.get('t',row.get('start',0));end=row.get('end',start)
        hints.append(dict(t=start,end=end) if similarity>=.55 and .3<end-start<8 else None)
    return dict(rows=rows, texts=texts, words=words, anchors=anchors, hints=hints,agreement=agreement,
                confirmed=confirmed, supported=supported)


def windows(segments, proposal, duration):
    """Partition at known word onsets, including omitted passages between them."""
    words, anchors = proposal['words'], proposal['anchors']
    useful = [s for s in segments if not artifact(s.get('text', ''))]
    start = max(0., min((s.get('t',s.get('start',0)) for s in useful),default=0)-1.)
    end = min(duration, max((s['end'] for s in useful),default=duration)+1.)
    if not anchors:
        # The fallback only supplies line windows, never word timings.
        points = [(0,start),(len(words),end)]
    else:
        start = min(start, max(0., anchors[0]['t']-anchors[0]['index']*1.5-1))
        points = [(0,start)] + [(x['index'],x['t']) for x in anchors if x['index'] > 0] + [(len(words),end)]
    def position(index):
        for (i,a),(j,b) in zip(points,points[1:]):
            if i <= index <= j:
                return a+(b-a)*(index-i)/max(1,j-i)
        return end
    cuts = [(0,start)]
    # Cut text only at known word onsets. Inference is chunked separately,
    # allowing long unrecognized passages without cutting a sung phrase.
    while end-cuts[-1][1] > 27:
        i,t = cuts[-1]
        candidates = [x for x in anchors if x['index']>i and 10 <= x['t']-t <= 24]
        if candidates:
            chosen = candidates[-1]; cuts.append((chosen['index'],chosen['t']))
        else:
            chosen=next((x for x in anchors if x['index']>i and x['t']>t+24),None)
            if chosen is None:break
            cuts.append((chosen['index'],chosen['t']))
    cuts.append((len(words),end))
    jobs=[]
    for n,((i,a),(j,b)) in enumerate(zip(cuts,cuts[1:])):
        if j<=i:continue
        jobs.append(dict(id=str(n),text=' '.join(words[i:j]),t0=max(0,a),t1=min(duration,b),
                         first=i,last=j,coreStart=a,coreEnd=b))
    return jobs,position


def language_for(text, default):
    # Code switching matters for singing. Whisper's multilingual aligner can
    # follow Spanish text even when the initial transcription chose French.
    values=set(lexical(text))
    spanish={'para','queja','mexica','sueno','celebremos','siempre','ahorita','aqui','nosotros',
             'corazon','pero','porque','cuando','quiero','estoy','contigo','tengo'}
    if values & spanish:return 'es'
    return default if default not in ('auto',None,'') else 'fr'


def acoustic_align(audio,jobs,language,folder):
    """Align without cutting unknown phrases, then refine each sung line."""
    try:
        return ctc_align(audio,jobs,language if language in ('fr','en','es') else 'fr',folder)
    except (OSError,ValueError,RuntimeError,ImportError):
        return whisper_align(audio,jobs,language)


def ctc_frames(audio,language,folder):
    # Chunk only inference, never the reference text. Reuse frame probabilities
    # for arbitrary anchor-to-anchor windows, including omitted 40 s passages.
    import hashlib
    import json
    from pathlib import Path
    import torch
    import reacue_words
    import reacue_performance
    reacue_performance.configure_torch(torch)
    files=reacue_words.model_files(language,download=False)
    path=Path(audio);stat=path.stat()
    signature=hashlib.sha256(json.dumps([str(path.resolve()),stat.st_size,stat.st_mtime_ns,
                                       language,files['weights'],1]).encode()).hexdigest()
    cache=Path(folder)/('ctc-'+signature+'.pt')
    model=None
    if cache.exists():
        saved=torch.load(cache,map_location='cpu',weights_only=True)
        em,step,vocab,blank=saved['em'],saved['step'],saved['vocab'],saved['blank']
    else:
        model,vocab,blank,normalize=reacue_words.load_model(language,files)
        wav=reacue_words._load_audio(str(audio));parts=[]
        # XLSR emits a frame every 20 ms. Include context at chunk boundaries
        # and discard its frames; no duplicated or missing sung words.
        frame=320;chunk=20*16000;context=16000
        with torch.inference_mode():
            for start in range(0,len(wav),chunk):
                print(f'Recalage vocal {language} : {start//chunk+1}/{math.ceil(len(wav)/chunk)}',flush=True)
                end=min(len(wav),start+chunk)
                a=max(0,start-context);b=min(len(wav),end+context)
                logits,_=reacue_words.emissions(model,wav[a:b],normalize)
                left=round((start-a)/frame);right=min(logits.shape[1],round((end-a)/frame))
                parts.append(logits[:,left:right])
        em=torch.cat(parts,dim=1);step=len(wav)/16000/em.shape[1]
        temporary=cache.with_suffix('.tmp')
        torch.save(dict(em=em,step=step,vocab=vocab,blank=blank),temporary)
        temporary.replace(cache)
    return em,step,vocab,blank


def ctc_align(audio,jobs,language,folder):
    import reacue_words
    em,step,vocab,blank=ctc_frames(audio,language,folder)
    result=[]
    for job in jobs:
        try:
            a=max(0,math.ceil(job['t0']/step));b=min(em.shape[1],math.floor(job['t1']/step))
            words,score=reacue_words.align_words(em[:,a:b],step,reacue_words.tokenize(job['text'],vocab),
                                                blank,vocab.get('|'),offset=a*step)
            result.append(dict(id=job['id'],words=words,score=score))
        except (ValueError,RuntimeError) as error:
            result.append(dict(id=job['id'],error=str(error)))
    return result


def comparison_words(proposal):
    from lyrics_reference import tokens
    # Parenthesised backing responses are often simultaneous or inaudible to
    # a speech model. Their presence must not make a complete source lose to
    # one omitting them. Exclude only explicit, standalone backing lines from
    # source scoring; retain every line for the eventual reference import.
    rows=proposal.get('texts',[])
    main=[word for row in rows if not re.fullmatch(r'\s*\([^()]+\)\s*',row)
          for word in tokens(row)]
    return main if len(main)>=len(proposal['words'])*.6 else proposal['words']


def align_reference(audio,segments,proposal,duration,language,folder):
    """Locate main phrases first so uncertain backing words cannot steal notes."""
    backing=[bool(re.fullmatch(r'\s*\([^()]+\)\s*',row)) for row in proposal['texts']]
    separate=any(backing) and not all(backing)
    primary=plan(segments,'\n'.join(row for row,is_backing in zip(proposal['texts'],backing) if not is_backing)) if separate else proposal
    jobs,position=windows(segments,primary,duration)
    aligned=acoustic_align(audio,jobs,language,folder)
    if not separate:
        adapted=adapt_repetitions(audio,segments,primary,jobs,aligned,language,folder)
        if adapted is not primary:
            primary=adapted;jobs,position=windows(segments,primary,duration)
            aligned=acoustic_align(audio,jobs,language,folder)
    jobs,aligned=refine(audio,primary,jobs,aligned,language,folder)
    if not separate:return primary,jobs,aligned,position
    by_id={str(item['id']):item for item in aligned};located={};quality={}
    for job in jobs:
        item=by_id.get(str(job['id']),{});words=item.get('words',[])
        if lexical(' '.join(w.get('w','') for w in words))!=lexical(' '.join(primary['words'][job['first']:job['last']])):continue
        located.update(enumerate(words,job['first']))
        quality.update((n,item.get('score',0)) for n in range(job['first'],job['last']))
    output_jobs=[];output_aligned=[];primary_cursor=0;cursor=0;bounds=[]
    for i,(row,is_backing) in enumerate(zip(proposal['rows'],backing)):
        job=dict(id=str(i),text=' '.join(row),first=cursor,last=cursor+len(row));cursor+=len(row)
        bounds.append(None)
        if is_backing:
            output_jobs.append(job);continue
        indexes=list(range(primary_cursor,primary_cursor+len(row)));primary_cursor+=len(row)
        words=[located.get(n) for n in indexes]
        if words and all(words):
            job.update(t0=words[0]['t'],t1=words[-1]['end']);bounds[-1]=(job['t0'],job['t1'])
            output_aligned.append(dict(id=job['id'],words=words,score=min(quality[n] for n in indexes)))
        else:job.update(t0=position(indexes[0]),t1=position(indexes[-1]+1))
        output_jobs.append(job)
    backing_jobs=[];by_line=list(output_jobs)
    for i,is_backing in enumerate(backing):
        if not is_backing:continue
        left=next((v[1] for v in reversed(bounds[:i]) if v),0.)
        right=next((v[0] for v in bounds[i+1:] if v),duration)
        # A short response belongs next to its main phrase, not to an arbitrary
        # vowel in a long instrumental break. Low scores remain reviewable.
        right=min(right,left+12.)
        job=by_line[i];job.update(t0=left,t1=right)
        if right-left>=.2:
            if backing_jobs and backing_jobs[-1]['last']==job['first']:
                previous=backing_jobs[-1]
                previous.update(text=previous['text']+' '+job['text'],last=job['last'])
                output_jobs.remove(job)
            else:backing_jobs.append(job)
    if backing_jobs:
        try:output_aligned.extend(acoustic_align(audio,backing_jobs,language,folder))
        except (OSError,ValueError,RuntimeError,ImportError):pass
    _,position=windows(segments,proposal,duration)
    return proposal,output_jobs,output_aligned,position


def reference_scores(audio, proposals, segments, language, folder):
    """Compare reference versions on exactly the same acoustic frames.

    A word-only mean rewards omitted lyrics. Whole CTC paths also score the
    frames left unexplained by a shortened reference. ASR locates the common
    search interval; it never supplies replacement words.
    """
    import torch
    import torchaudio.functional as AF
    import reacue_words
    em,step,vocab,blank=ctc_frames(audio,language if language in ('fr','en','es') else 'fr',folder)
    useful=[s for s in segments if not artifact(s.get('text',''))]
    start=max(0,min((s.get('t',s.get('start',0)) for s in useful),default=0)-2)
    end=min(em.shape[1]*step,max((s['end'] for s in useful),default=em.shape[1]*step)+2)
    a=math.ceil(start/step);b=math.floor(end/step)
    window=em[:,a:b];result=[]
    for proposal in proposals:
        try:
            words=reacue_words.tokenize(' '.join(comparison_words(proposal)),vocab);targets=[]
            for i,word in enumerate(words):
                if i and '|' in vocab:targets.append(vocab['|'])
                targets.extend(word['ids'])
            if not targets:raise ValueError('Référence vide.')
            _,scores=AF.forced_align(window,torch.tensor([targets],dtype=torch.int32),blank=blank)
            score=float(scores.mean())
            result.append(score if math.isfinite(score) else None)
        except (ValueError,RuntimeError):result.append(None)
    return result


def whisper_align(audio,jobs,language):
    import numpy as np
    import torch
    import whisper
    from whisper.timing import find_alignment
    from whisper.tokenizer import get_tokenizer, LANGUAGES
    import reacue_transcribe
    import reacue_words
    import reacue_performance
    reacue_performance.configure_torch(torch)
    model=reacue_transcribe.load(reacue_transcribe.selected_model())
    wav=reacue_words._load_audio(str(audio)).numpy()
    tokenizer=get_tokenizer(model.is_multilingual,num_languages=model.num_languages,
                            language=language if language in LANGUAGES else 'fr',task='transcribe')
    result=[]
    for job in jobs:
        try:
            a,b=round(job['t0']*16000),min(len(wav),round(job['t1']*16000))
            if not 3200 <= b-a <= 30*16000:raise ValueError('Fenêtre vocale invalide.')
            mel=whisper.log_mel_spectrogram(whisper.pad_or_trim(wav[a:b]),model.dims.n_mels).to(model.device)
            aligned=find_alignment(model,tokenizer,tokenizer.encode(' '+job['text']),mel,(b-a)//160)
            # Match by normalized character spans to rejoin apostrophes exactly
            # as the reference spells them, retaining acoustic boundaries.
            from lyrics_reference import key, tokens
            chars='';owners=[]
            for w in aligned:
                value=key(w.word);chars+=value;owners.extend([w]*len(value))
            target=tokens(job['text'])
            if chars!=''.join(map(key,target)):raise ValueError('Mots du recalage incomplets.')
            out=[];cursor=0
            for word in target:
                span=owners[cursor:cursor+len(key(word))];cursor+=len(key(word))
                out.append(dict(w=word,t=round(a/16000+span[0].start,3),
                                end=round(a/16000+span[-1].end,3),score=round(float(np.mean([x.probability for x in span])),3)))
            result.append(dict(id=job['id'],words=out,score=float(np.mean([w['score'] for w in out]))))
        except (ValueError,RuntimeError) as error:
            result.append(dict(id=job['id'],error=str(error)))
    return result


def repeat_key(row):
    # Publishers sometimes spell an extra pickup word in one repetition.
    words=lexical(' '.join(row))
    return tuple(w for i,w in enumerate(words) if i==0 or w!=words[i-1])


def choose_repetition(variants,original_count):
    original=next((v for v in variants if v['count']==original_count),None)
    if not original:return None
    valid=[v for v in variants if math.isfinite(v['pathScore']) and v['words'] and
           all(.055 <= w['end']-w['t'] <= max(2.5,len(w['w'])*.22) for w in v['words'])]
    if not valid:return None
    winner=max(valid,key=lambda v:v['pathScore'])
    return winner if winner['count']!=original_count and winner['pathScore']>=original['pathScore']+.08 else None


def adapt_repetitions(audio,segments,proposal,jobs,aligned,language,folder):
    """Compare whole CTC paths; reject repeats squashed into vowels or silence."""
    import torch
    import torchaudio.functional as AF
    import reacue_words
    from lyrics_reference import key
    by_id={str(a['id']):a for a in aligned};located={}
    for job in jobs:
        words=by_id.get(job['id'],{}).get('words',[])
        if [key(w.get('w','')) for w in words]==list(map(key,proposal['words'][job['first']:job['last']])):
            located.update(enumerate(words,job['first']))
    offsets=[0]
    for row in proposal['rows']:offsets.append(offsets[-1]+len(row))
    rows=proposal['rows'];texts=list(proposal.get('texts',[' '.join(r) for r in rows]));changes=[]
    i=0
    while i<len(rows):
        j=i+1
        while j<len(rows) and repeat_key(rows[j])==repeat_key(rows[i]):j+=1
        count=j-i
        if count>=3 and i>0 and j+1<len(rows):
            # Include the following different line to disambiguate the end of
            # the run, with the next line's onset as the right acoustic bound.
            left=located.get(offsets[i]-1);right=located.get(offsets[j+1])
            if left and right and 1<right['t']-left['end']<60:
                lang=language_for(texts[i],language)
                try:
                    em,step,vocab,blank=ctc_frames(audio,lang,folder)
                    # A detected word onset can lag its first consonant. Keep
                    # that consonant out of the previous phrase's final token.
                    a=math.ceil(left['end']/step);b=math.floor((right['t']-.6)/step);window=em[:,a:b]
                    variants=[]
                    for n in range(1,min(16,max(count*2,count+3))+1):
                        text=' '.join([texts[i]]*n+[texts[j]])
                        words=reacue_words.tokenize(text,vocab);targets=[]
                        for k,w in enumerate(words):
                            if k and '|' in vocab:targets.append(vocab['|'])
                            targets.extend(w['ids'])
                        _,scores=AF.forced_align(window,torch.tensor([targets],dtype=torch.int32),blank=blank)
                        aligned_words,_=reacue_words.align_words(window,step,words,blank,vocab.get('|'),offset=a*step)
                        variants.append(dict(count=n,pathScore=float(scores.mean()),words=aligned_words))
                    winner=choose_repetition(variants,count)
                    if winner:changes.append((i,j,winner['count']))
                except (OSError,ValueError,RuntimeError,ImportError,KeyError):pass
        i=j
    for i,j,count in reversed(changes):texts[i:j]=[texts[i]]*count
    if changes:
        updated=plan(segments,'\n'.join(texts));updated['repeatAdjustments']=len(changes)
        return updated
    return proposal


def refine(audio,proposal,jobs,aligned,language,folder):
    """Re-align full lines in their own language using the first acoustic pass."""
    from lyrics_reference import key
    by_id={str(x.get('id')):x for x in aligned};located={}
    for job in jobs:
        values=by_id.get(job['id'],{}).get('words',[])
        expected=proposal['words'][job['first']:job['last']]
        if [key(w.get('w','')) for w in values]!=list(map(key,expected)):continue
        for i,w in enumerate(values,job['first']):
            if all(isinstance(w.get(k),(int,float)) and math.isfinite(w[k]) for k in ('t','end')) and w['t']<w['end']:
                located[i]=w
    spans=[];cursor=0
    for row in proposal['rows']:
        indexes=list(range(cursor,cursor+len(row)))
        values=[located.get(i) for i in indexes]
        reliable=[(n,w) for n,w in enumerate(values) if w and w.get('score',0)>=.12
                  and w['end']-w['t']<max(2.5,len(w.get('w',''))*.6)]
        if reliable:
            n,first=reliable[0];m,last=reliable[-1]
            a=first['t']-min(1.5,n*.45)-.3
            b=last['end']+min(1.5,(len(row)-1-m)*.45)+.4
        elif all(values):a,b=values[0]['t']-.3,values[-1]['end']+.4
        else:
            spans.append(None);cursor+=len(row);continue
        hint=(proposal.get('hints') or [None]*len(proposal['rows']))[len(spans)]
        if hint and all(values):
            quality=sum(w.get('score',0) for w in values)/len(values)
            stretched=any(w['end']-w['t']>max(2.5,len(w.get('w',''))*.6) for w in values)
            gap=any(y['t']-x['end']>1.2 for x,y in zip(values,values[1:]))
            if (quality<.3 or stretched or gap) and abs(a-hint['t'])<5:
                a,b=hint['t']-.3,hint['end']+.4
        spans.append(dict(id=str(len(spans)),text=' '.join(row),t0=max(0,a),t1=b,first=cursor,last=cursor+len(row)))
        cursor+=len(row)
    # Adjacent rows share a silence boundary rather than competing for the same
    # vowel. Every word is still positioned by acoustic forced alignment.
    for a,b in zip(spans,spans[1:]):
        if a and b and a['t1']>b['t0']:
            cut=(a['t1']+b['t0'])/2
            if a['t0']<cut<b['t1']:a['t1']=cut;b['t0']=cut
    groups={}
    for span in spans:
        if span and .2<=span['t1']-span['t0']<=30:
            groups.setdefault(language_for(span['text'],language),[]).append(span)
    refined=[];used=[]
    for lang,group in groups.items():
        if lang != language:
            merged=[]
            for span in group:
                if merged and merged[-1]['last']==span['first'] and span['t1']-merged[-1]['t0']<=28:
                    merged[-1].update(text=merged[-1]['text']+' '+span['text'],t1=span['t1'],last=span['last'])
                else:merged.append(dict(span))
            group=merged
        used.extend(group)
        try:refined.extend(ctc_align(audio,group,lang,folder))
        except (OSError,ValueError,RuntimeError,ImportError,KeyError):
            try:refined.extend(whisper_align(audio,group,lang))
            except (OSError,ValueError,RuntimeError,ImportError):pass
    # Leave unsupported lines to the explicit text-only fallback, not the old
    # ASR guess. Callers may audit each line independently.
    return used,refined


def reconstruct(segments,proposal,jobs,aligned,position,source):
    from lyrics_reference import key
    acoustic={};uncertain=set();by_id={str(x.get('id')):x for x in aligned}
    for job in jobs:
        result=by_id.get(job['id'],{});words=result.get('words',[])
        expected=proposal['words'][job['first']:job['last']]
        valid=(not result.get('error') and [key(w.get('w','')) for w in words]==list(map(key,expected))
               and all(all(isinstance(w.get(k),(int,float)) and math.isfinite(w[k]) for k in ('t','end','score'))
                       and job['t0']<=w['t']<w['end']<=job['t1']+.001 for w in words)
               and all(a['end']<=b['t'] for a,b in zip(words,words[1:])))
        if valid:
            for index,(w,text) in enumerate(zip(words,expected),job['first']):
                acoustic[index]={**w,'w':text}
                if w.get('score',0)<.08 or not math.isfinite(result.get('score',0)) or result.get('score',0)<.15:uncertain.add(index)
    result=[];cursor=0;review=0
    manual=[copy.deepcopy(s) for s in segments if s.get('manual')]
    for line_index,row in enumerate(proposal['rows']):
        indexes=range(cursor,cursor+len(row));words=[acoustic.get(i) for i in indexes]
        if all(w is not None for w in words):
            start,end=words[0]['t'],words[-1]['end']
            needs_review=any(i in uncertain for i in indexes)
        else:
            start,end=position(cursor),position(cursor+len(row));words=[];needs_review=True
        cursor+=len(row)
        if end<=start:continue
        if any(s.get('t',s.get('start',0))<end and s['end']>start for s in manual):continue
        text=proposal.get('texts',[' '.join(r) for r in proposal['rows']])[line_index]
        result.append(dict(t=start,end=end,text=text,words=words,
                           sourceURL=source['url'],confidence=min((w.get('score',0) for w in words),default=0),timingReview=needs_review))
        review+=int(needs_review)
    result=sorted(manual+result,key=lambda s:s.get('t',s.get('start',0)))
    # Overlapping estimates/context must not produce two simultaneously active
    # lines. Do not move an acoustic word to hide an uncertain boundary.
    for a,b in zip(result,result[1:]):
        if a['end']>b.get('t',b.get('start',0)) and not a.get('manual') and not b.get('manual'):
            boundary=min(b['end']-.001,max(a['t']+.001,(a['end']+b['t'])/2))
            for row in (a,b):
                if not row.get('timingReview'):review+=1
                row.update(words=[],timingReview=True,confidence=0)
            a['end']=boundary;b['t']=boundary
    return result,review
