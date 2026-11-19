"""Temporary diagnostic: real chord-site lookups, per provider, with exact errors."""
import sys,ssl,time,json,platform,traceback
sys.path.insert(0,'desktop/studio')
import chord_sources as cs
from urllib.error import HTTPError
print('python',sys.version,'|',platform.platform(),'|',ssl.OPENSSL_VERSION)
print('verify paths',ssl.get_default_verify_paths())
songs=[('Wonderwall','Oasis'),('Let It Be','The Beatles'),('Hotel California','Eagles'),("Knockin' On Heaven's Door",'Bob Dylan'),('Zombie','The Cranberries')]
summary={}
for title,artist in songs:
    print(f'\n=== {artist} - {title}')
    for p in [p for p in cs.PROVIDERS if p.get('template')]:
        url=cs.provider_url(p,title,artist);t=time.monotonic()
        try:
            page,final=cs.fetch(url);chart=cs.Chart(p['id']);chart.feed(page)
            ok=cs.matches_heading(chart.title,title,artist)
            res=f"200 title={chart.title.strip()[:70]!r} match={ok} chords={len(chart.chords)}"
            st='found' if ok and chart.chords else 'parsed-nothing'
        except HTTPError as e:res=f'HTTP {e.code}';st=f'http{e.code}'
        except Exception as e:res='EXC '+repr(e)[:220];st=type(e).__name__
        print(f'  {p["id"]:12} {time.monotonic()-t:5.2f}s {res}  <- {url}')
        summary.setdefault(p['id'],[]).append(st)
    import analysis_progress
    r=cs._search(title,artist)
    print('  _search (8s budget):',{k:v[0] for k,v in r.items()})
print('\nSUMMARY',json.dumps(summary))
