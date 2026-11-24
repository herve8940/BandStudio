"""Bounded local diagnostics. No audio, project contents or credentials are collected."""
from ui_language import ui_text
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

# BEGIN GENERATED COMMUNITY
COMMUNITY = {
    "invite": "https://discord.gg/5UnQPdMUpR",
    "welcome": "https://discord.com/channels/1571210838315106304/1571211032007806986",
    "news": "https://discord.com/channels/1571210838315106304/1571211189483213044",
    "guide": "https://discord.com/channels/1571210838315106304/1571211224513781801",
    "help": "https://discord.com/channels/1571210838315106304/1571211286144884899",
    "bugs": "https://discord.com/channels/1571210838315106304/1571211312518668308",
    "ideas": "https://discord.com/channels/1571210838315106304/1571211338053718186",
    "rules": "https://discord.com/channels/1571210838315106304/1571211472200007680"
}
# END GENERATED COMMUNITY

def community_url(destination='invite'):
    if destination not in COMMUNITY:raise ValueError(ui_text('Destination Discord inconnue.', 'Unknown Discord destination.'))
    return COMMUNITY[destination]

def compact_debug():
    """Metadata only: never include free-form error messages, paths or project data."""
    file=directory()/'application.log'
    if file.is_symlink():return ui_text('Journal indisponible.', 'Log unavailable.')
    try:
        with file.open('rb') as source:
            source.seek(0,2);size=source.tell();source.seek(max(0,size-32_000))
            lines=source.read(32_000).decode('utf-8',errors='replace').splitlines()
    except OSError:return ui_text('Aucun événement récent.', 'No recent events.')
    result=[]
    for line in lines:
        match=re.search(r'\b(?:INFO|ERROR|WARNING) ([a-z][a-zA-Z0-9_.-]{0,50}) (\{.*\})$',line)
        if not match:continue
        try:fields=json.loads(match[2])
        except ValueError:continue
        if not isinstance(fields,dict):continue
        event=match[1]
        if event=='command' and fields.get('command') in ('supportInfo','copyDiscordReport','openCommunity'):continue
        parts=[event]
        for key in ('command','task','component','kind','exit','elapsed','line','busy','playing'):
            value=str(fields.get(key,''))
            if re.fullmatch(r'[a-zA-Z0-9_.-]{1,50}',value):parts.append(key+'='+value)
        result.append(' '.join(parts))
    return '\n'.join(result[-6:])[-650:] or ui_text('Aucun événement récent.', 'No recent events.')

def support_info():
    info=summary()
    environment=f"BandStudio {info['version']} · {info['os']} {info['os_version']} · {info['architecture']}"
    if info.get('commit'):environment+=' · '+info['commit'][:12]
    return {'type':'supportInfo','environment':environment,'debug':compact_debug()}

def validate_discord_report(text):
    if not isinstance(text,str) or not text.strip() or len(text.encode('utf-16-le'))//2>2000:
        raise ValueError(ui_text('Le rapport doit contenir entre 1 et 2 000 caractères.', 'The report must be between 1 and 2,000 characters.'))
    return text

def copy_report_windows(text):
    # clip.exe reads UTF-16; stdin avoids command interpolation and preserves Unicode.
    import subprocess
    text=validate_discord_report(text)
    subprocess.run(['clip.exe'],input=text.encode('utf-16le'),check=True,timeout=5,
                   creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))

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
    body=(ui_text('## Problème\nDécris le problème ici.\n\n## Pour reproduire\n1. \n\n'
          '## Résultat attendu\n\n## Environnement\n', '## Issue\nDescribe the issue here.\n\n## Steps to reproduce\n1. \n\n## Expected result\n\n## Environment\n')+json.dumps(info,ensure_ascii=False,indent=2)+
          ui_text('\n\n## Diagnostic\nTu peux joindre le ZIP depuis Réglages → Exporter le diagnostic après l’avoir vérifié.\n', '\n\n## Diagnostics\nAfter reviewing the ZIP, attach it from Settings → Export diagnostics.\n'))
    return 'https://github.com/'+REPOSITORY+'/issues/new?'+urlencode({'title':'[Bug] ', 'labels':'bug', 'body':body})
