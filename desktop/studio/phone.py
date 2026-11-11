"""Opt-in, read-only LAN prompter. No audio, filesystem browsing or remote control."""
from __future__ import annotations
import argparse
import base64
import bisect
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import math
from pathlib import Path
import secrets
import socket
import time
from services import atomic


def transpose(text, steps):
    import re
    names=['C','C#','D','Eb','E','F','F#','G','Ab','A','Bb','B'];notes=dict(C=0,D=2,E=4,F=5,G=7,A=9,B=11)
    return re.sub(r'(^|/)([A-G])([#b]?)',lambda m:m[1]+names[(notes[m[2]]+{'':0,'#':1,'b':-1}[m[3]]+round(steps))%12],text)


def public_state(p, t):
    at=t.get('position',0);s=p.get('settings',{});beats=p.get('beats',[]);meter=s.get('beatsPerBar',4)
    first=s.get('firstBeat',0);bpm=s.get('manualBPM',120) if s.get('gridMode')=='fixed' else p.get('bpm',0) or s.get('manualBPM',120)
    period=60/max(20,bpm);anchor=0
    if s.get('gridMode')=='detected' and len(beats)>1:
        index=max(0,bisect.bisect_right(beats,at)-1);anchor=min(range(len(beats)),key=lambda i:abs(beats[i]-first))%meter
        if index+1<len(beats):period=beats[index+1]-beats[index]
    else:index=max(0,math.floor((at-first)/period))
    current=lambda kind:next((x for x in p.get(kind,[]) if x['start']<=at<x['end']),None)
    section=current('sections');lyric=current('lyrics');chord=current('chords')
    next_section=next((x for x in p.get('sections',[]) if x['start']>at),None)
    shift=t.get('pitch',0);capo=p.get('capo',0)
    return dict(name=p.get('name','BandStudio'),position=at,playing=t.get('playing',False),
                beat=(index-anchor)%meter+1,meter=meter,bar=math.floor((index-anchor)/meter)+1,
                bpm=round(60/max(.01,period)*t.get('rate',1),1),section=section['name'] if section else '',
                next=next_section['name'] if next_section else '',lyric=lyric['text'] if lyric else '',
                words=[dict(text=w['text'],active=w['start']<=at<w['end']) for w in (lyric or {}).get('words') or []],
                chord=transpose(chord['text'],shift-capo) if chord else '',capo=capo,
                key=transpose(p.get('key',''),shift),count=t.get('countRemaining',0))


HTML='''<!doctype html><html lang="fr"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BandStudio · Prompteur</title><link rel="stylesheet" href="screen.css"><script src="screen.js" defer></script><body><header><span>BANDSTUDIO · PROMPTEUR LOCAL</span><button id="fullscreen">Plein écran</button></header><p id="status">Connexion…</p><h1 id="name"></h1><div class="metrics"><span id="beat"></span><span id="bpm"></span><span id="key"></span></div><h2 id="section"></h2><strong id="count"></strong><div id="chord"></div><p id="lyric"></p><p id="next"></p><footer>Lecture seule · garde cette page ouverte pendant la répétition</footer></body></html>'''
CSS='''body{background:#10151e;color:#e5ebf4;font-family:system-ui;margin:0;padding:5vw;max-width:1200px}header,.metrics{display:flex;gap:22px;align-items:center;justify-content:space-between;flex-wrap:wrap}header,footer,#status{color:#a6b5cd;font-size:14px}button{background:#26344b;border:1px solid #60708e;color:white;padding:10px;border-radius:12px}h1{font-size:24px}h2{font-size:clamp(32px,8vw,80px);margin-bottom:16px}#chord,#count{color:#6ee7b7;font-size:clamp(32px,8vw,84px)}#lyric{font-size:clamp(26px,5vw,56px);line-height:1.5;white-space:pre-line}#next{color:#d1b6ff;font-size:24px}.active{color:#6ee7b7;text-decoration:underline}footer{margin-top:50px}'''
JS='''const $=id=>document.getElementById(id);let wake;async function keepAwake(){try{wake=await navigator.wakeLock?.request('screen');}catch{}}$('fullscreen').onclick=async()=>{try{await document.documentElement.requestFullscreen();}catch{}keepAwake();};document.addEventListener('visibilitychange',()=>{if(!document.hidden)keepAwake();});async function refresh(){try{const response=await fetch('state',{cache:'no-store'});if(!response.ok)throw Error();const s=await response.json();$('status').textContent=s.playing?'Lecture':'En pause';$('name').textContent=s.name;$('section').textContent=s.section||'Prêt à jouer';$('beat').textContent=(s.bar>0?'Mesure '+s.bar:'Levée')+' · '+s.beat+' / '+s.meter;$('bpm').textContent=s.bpm+' BPM';$('key').textContent=s.key?'Tonalité '+s.key:'';$('chord').textContent=s.chord+(s.capo?' · capo '+s.capo:'');$('count').textContent=s.count?'DÉPART DANS '+s.count:'';$('next').textContent=s.next?'ENSUITE · '+s.next:'';if(s.words.length){$('lyric').replaceChildren(...s.words.map(w=>{const e=document.createElement('span');e.textContent=w.text+' ';e.className=w.active?'active':'';return e;}));}else $('lyric').textContent=s.lyric;}catch{$('status').textContent='Connexion interrompue — vérifie le Wi-Fi et BandStudio.';}setTimeout(refresh,250);}refresh();'''


def server(folder, token, host='127.0.0.1', port=0):
    folder=Path(folder)
    if len(token)<32:raise ValueError('Clé de session trop courte.')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            path=self.path.split('?',1)[0];prefix='/'+token+'/'
            if not path.startswith(prefix):self.send_error(404);return
            resource=path[len(prefix):]
            content={'':(HTML,'text/html'),'screen.js':(JS,'application/javascript'),'screen.css':(CSS,'text/css')}.get(resource)
            if resource=='state':
                try:
                    if time.time()-(folder/'transport.json').stat().st_mtime>5:raise ValueError('Stale')
                    p=json.loads((folder/'project.json').read_text());t=json.loads((folder/'transport.json').read_text())
                    content=(json.dumps(public_state(p,t),ensure_ascii=False),'application/json')
                except (OSError,ValueError,KeyError):self.send_error(503);return
            if content is None:self.send_error(404);return
            data=content[0].encode('utf-8');self.send_response(200)
            self.send_header('Content-Type',content[1]+'; charset=utf-8');self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers();self.wfile.write(data)
    return ThreadingHTTPServer((host,port),Handler)


def local_address():
    try:
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:
            s.connect(('192.0.2.1',9))  # Route lookup only: no UDP payload is sent.
            return s.getsockname()[0]
    except OSError:return '127.0.0.1'


def main(folder, host):
    import qrcode
    folder=Path(folder);token=secrets.token_urlsafe(32);http=server(folder,token,host);http.timeout=1
    address=local_address() if host=='0.0.0.0' else host
    url=f'http://{address}:{http.server_port}/{token}/'
    image=io.BytesIO();qrcode.make(url).save(image,format='PNG')
    atomic(folder/'info.json',dict(url=url,qr='data:image/png;base64,'+base64.b64encode(image.getvalue()).decode()))
    started=time.time()
    try:
        while True:
            http.handle_request()
            heartbeat=folder/'transport.json'
            if time.time()-(heartbeat.stat().st_mtime if heartbeat.exists() else started)>15:break
    finally:http.server_close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--folder',required=True);p.add_argument('--host',choices=['127.0.0.1','0.0.0.0'],default='0.0.0.0');args=p.parse_args();main(args.folder,args.host)
