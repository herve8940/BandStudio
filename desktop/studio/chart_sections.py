"""Section headings and word fingerprints from the already fetched chord chart.

Fingerprints locate passages in the user's own timed transcription. They contain
no remote timestamps and are not sufficient to label music without audio checks.
"""
from html.parser import HTMLParser
import hashlib
import re
import unicodedata

SCHEMA=1
MAX_WORDS=1800


def words(text):
    text=unicodedata.normalize('NFKD',text.casefold()).replace('’',"'")
    text=''.join(c for c in text if not unicodedata.combining(c))
    return re.findall(r"[^\W_]+(?:'[^\W_]+)*",text,re.UNICODE)


def word_key(word):
    return hashlib.sha256(word.replace("'",'').encode()).hexdigest()[:20]


def fingerprints(text):return [word_key(w) for w in words(text)]


def heading(text):
    text=' '.join(words(text));text=re.sub(r'\s+(?:x\s*)?\d+$','',text)
    text=re.sub(r'^(?:first|second|third|fourth|1|2|3|4)\s+','',text)
    names={'intro':'intro','introduction':'intro','verse':'verse','couplet':'verse',
           'chorus':'chorus','refrain':'chorus','refrao':'chorus','estribillo':'chorus',
           'pre chorus':'prechorus','prechorus':'prechorus','pre refrain':'prechorus','pre estribillo':'prechorus','pre refrao':'prechorus',
           'post chorus':'postchorus','postchorus':'postchorus','post refrain':'postchorus',
           'bridge':'bridge','pont':'bridge','ponte':'bridge','puente':'bridge',
           'break':'break','breakdown':'break','interlude':'instrumental','instrumental':'instrumental',
           'solo':'solo','outro':'outro','ending':'outro','final':'outro','coda':'outro'}
    if text in names:return names[text]
    if re.fullmatch(r'(?:(?:primera|primeira|segunda|tercera|terceira|cuarta|quarta|quinta|sexta)\s+parte|part|parte)',text):return 'unknown'
    return None


class Text(HTMLParser):
    def __init__(self):
        super().__init__();self.stack=[];self.parts=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag not in ('br','hr','meta','link','img','input','source','wbr'):self.stack.append((tag,attrs))
        if tag=='br' and self.in_chart():self.parts.append('\n')
    def handle_endtag(self,tag):
        if tag in ('pre','music-part') and self.in_chart():self.parts.append('\n')
        for i in range(len(self.stack)-1,-1,-1):
            if self.stack[i][0]==tag:self.stack=self.stack[:i];break
    def in_chart(self):
        return any(t=='pre' or 'chord-short-code-wrap' in a.get('class','').split() for t,a in self.stack)
    def handle_data(self,text):
        if not self.in_chart() or any(t in ('script','style') for t,_ in self.stack):return
        from chord_sources import CHORD
        tag,attrs=self.stack[-1]
        if tag in ('b','span','a','c-2') and CHORD.fullmatch(text.strip()):self.parts.append(' ')
        else:self.parts.append(text)


def extract(page):
    parser=Text();parser.feed(page)
    text=''.join(parser.parts)
    # Only recognised parenthesised headings split inline text. Ordinary lyric
    # parentheses and annotations such as "repeat chorus" are not new sections.
    text=re.sub(r'[\[(]([^\]\)\n]{1,70})[\])]',lambda m:'\n'+m[0]+'\n' if heading(m[1]) else m[0],text)
    blocks=[];current=None;total=0
    for line in text.splitlines():
        clean=line.strip();kind=heading(clean)
        if kind:
            if len(blocks)>=128:break
            current=dict(name=re.sub(r'^[^\w]+|[^\w]+$','',clean)[:70],kind=kind,words=[])
            blocks.append(current);continue
        if current is None or total>=MAX_WORDS:continue
        # Ignore notation and playing directions, not just the chord HTML tags.
        if re.search(r'(?:^|\s)[eEBGDA]\s*\|[-\d]|[-|]{3}',line):continue
        tokens=words(line)
        if not tokens or len(tokens)<2 or re.fullmatch(r'\s*(?:[A-G][#b]?(?:m|maj|sus|add|dim)?\d*\s*)+',line):continue
        if re.match(r'^\s*(?:repeat|repetir|riff|strum|x\s*\d|\d+\s*x)\b',line,re.I):continue
        hashed=[word_key(w) for w in tokens][:min(256-len(current['words']),MAX_WORDS-total)]
        current['words'].extend(hashed);total+=len(hashed)
    return [b for b in blocks if len(b['words'])>=6]
