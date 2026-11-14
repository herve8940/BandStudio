#!/usr/bin/env python3
"""Keep the native Discord destinations in sync with config/community.json."""
import argparse
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]

def main(check=False):
    config=json.loads((ROOT/'config/community.json').read_text())
    if not re.fullmatch(r'https://discord\.gg/[A-Za-z0-9]+',config['inviteUrl']):
        raise ValueError('Une invitation Discord vérifiée est requise.')
    assert re.fullmatch(r'\d{17,20}',config['serverId'])
    assert all(re.fullmatch(r'\d{17,20}',v) for v in config['channels'].values())
    links={'invite':config['inviteUrl'],**{k:f"https://discord.com/channels/{config['serverId']}/{v}" for k,v in config['channels'].items()}}
    blocks=[('desktop/studio/diagnostics.py','#','COMMUNITY = '+json.dumps(links,indent=4)),
            ('desktop/studio/StudioDiagnostics.swift','//','let studioCommunity: [String:String] = [\n'+',\n'.join('    '+json.dumps(k)+': '+json.dumps(v) for k,v in links.items())+'\n]')]
    for filename,prefix,body in blocks:
        path=ROOT/filename;text=path.read_text()
        start=prefix+' BEGIN GENERATED COMMUNITY';end=prefix+' END GENERATED COMMUNITY'
        updated=re.sub(re.escape(start)+r'.*?'+re.escape(end),lambda _:start+'\n'+body+'\n'+end,text,flags=re.S)
        if check:
            if updated!=text:raise SystemExit(filename+' : lancer python3 tools/sync_community.py')
        else:path.write_text(updated)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true')
    main(parser.parse_args().check)
