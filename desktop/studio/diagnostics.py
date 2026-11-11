"""Bounded local diagnostics. No audio, project contents or credentials are collected."""
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import platform
import re
import sys
import threading
from urllib.parse import urlencode
import zipfile

REPOSITORY = 'herve8940/BandStudio'
VERSION = '1.1.0'

def directory():
    if sys.platform == 'darwin': return Path.home()/'Library/Logs/BandStudio'
    return Path(os.environ.get('LOCALAPPDATA', Path.home()/'.local/state'))/'BandStudio/Logs'

def redact(value):
    text = str(value).replace(str(Path.home()), '<home>')
    text = re.sub(r'https?://[^\s<>"\']+', '<url>', text)
    text = re.sub(r'(?i)(token|password|secret|authorization|api[_-]?key)\s*[:=]\s*\S+', r'\1=<redacted>', text)
    text = re.sub(r'(?i)[a-z]:[\\/][^\r\n"<>]+', '<path>', text)
    return text[:3000]

def logger():
    log = logging.getLogger('bandstudio')
    if not log.handlers:
        folder = directory(); folder.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(folder/'application.log', maxBytes=1_000_000, backupCount=3, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        log.addHandler(handler); log.setLevel(logging.INFO); log.propagate = False
    return log

def event(name, **fields):
    # Call sites supply metadata, never command arguments or song contents.
    try:logger().info('%s %s', name, json.dumps({k:redact(v) for k,v in fields.items()}, ensure_ascii=False))
    except OSError:pass  # A read-only log folder must never stop playback or analysis.

def install_hooks():
    original = sys.excepthook
    def crash(kind, value, tb):
        event('unhandled', kind=kind.__name__, error=value); original(kind, value, tb)
    sys.excepthook = crash
    old_thread = threading.excepthook
    def thread_crash(args):
        event('thread.unhandled', kind=args.exc_type.__name__, error=args.exc_value); old_thread(args)
    threading.excepthook = thread_crash

def summary():
    info={'application':'BandStudio', 'version':VERSION, 'os':platform.system(),
          'os_version':platform.release(), 'architecture':platform.machine(), 'python':platform.python_version()}
    try:
        build=json.loads(Path(__file__).with_name('build.json').read_text(encoding='utf-8'))
        commit=build.get('commit','')
        if re.fullmatch('[0-9a-f]{40}',commit):info['commit']=commit
    except (OSError,ValueError,TypeError):pass
    return info

def export_report(destination):
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('system.json', json.dumps(summary(), indent=2))
        for file in sorted(directory().glob('application.log*')):
            archive.writestr(file.name, '\n'.join(redact(line) for line in file.read_text(errors='replace').splitlines()))
    return str(destination)

def issue_url():
    info=summary()
    body=('## Problème\nDécris le problème ici.\n\n## Pour reproduire\n1. \n\n'
          '## Résultat attendu\n\n## Environnement\n'+json.dumps(info,ensure_ascii=False,indent=2)+
          '\n\n## Diagnostic\nTu peux joindre le ZIP depuis Réglages → Exporter le diagnostic après l’avoir vérifié.\n')
    return 'https://github.com/'+REPOSITORY+'/issues/new?'+urlencode({'title':'[Bug] ', 'labels':'bug', 'body':body})
