"""Persistent, explicitly started preparation queue. JSON-line IPC, no network listener."""
import argparse
import json
import os
from pathlib import Path
import queue
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid

from platform_tools import creation_flags, python_for
from services import atomic, safe_name


def options(value):
    result = dict(model='htdemucs', quality='standard', language='auto')
    result.update({k: value[k] for k in result if k in value})
    for key, allowed in [('model', ('htdemucs', 'htdemucs_ft', 'htdemucs_6s')),
                         ('quality', ('fast', 'standard', 'careful')),
                         ('language', ('auto', 'fr', 'en'))]:
        if result[key] not in allowed:
            raise ValueError('Réglage de préparation invalide : ' + key)
    return result


def terminate(proc):
    if proc is None or proc.poll() is not None:
        return
    if os.name == 'nt':
        subprocess.run(['taskkill.exe', '/PID', str(proc.pid), '/T', '/F'],
                       capture_output=True, creationflags=creation_flags(), timeout=15)
    else:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name == 'nt':
            proc.kill()
        else:
            os.killpg(proc.pid, signal.SIGKILL)
        proc.wait(timeout=5)


class PreparationQueue:
    def __init__(self, engine, library):
        self.engine, self.library = Path(engine).resolve(), Path(library).resolve()
        self.directory = self.library / '.PreparationQueue'
        if self.directory.is_symlink():
            raise ValueError('Dossier de file d’attente invalide.')
        self.directory.mkdir(parents=True, exist_ok=True)
        self.file = self.directory / 'queue.json'
        self.items = json.loads(self.file.read_text(encoding='utf-8'))['items'] if self.file.exists() else []
        if not isinstance(self.items, list) or any(
                not isinstance(e, dict) or len(e.get('id', '')) != 32 or
                any(c not in '0123456789abcdef' for c in e['id']) for e in self.items):
            raise ValueError('File enregistrée illisible. Le fichier a été conservé.')
        self.enabled = False  # A restart always waits for the musician's button.
        self.ready = False
        self.heartbeat = 0.0
        self.proc = self.log = self.current = None
        self.stage = ''
        self.message = ''
        self.ack = None
        self.library_changed = False
        for item in self.items:
            if item['status'] == 'running':
                item['status'] = 'pending'
            self.recover(item)
        self.save()

    def root(self, item):
        return self.directory / item['id'] / 'project.bandstudio'

    def recover(self, item):
        root = self.root(item)
        if (root / 'project.json').is_file():
            p = json.loads((root / 'project.json').read_text(encoding='utf-8'))
            item['completed'] = p.get('_queueCompleted', [])
            item['title'] = p['name']
        # Recover a crash between publishing the project and saving the queue.
        if item.get('destination') and item['status'] != 'done':
            target = self.library / item['destination']
            if target.parent != self.library or target.is_symlink():
                raise ValueError('Destination de file invalide.')
            if (target / 'project.json').is_file():
                p = json.loads((target / 'project.json').read_text(encoding='utf-8'))
                if p.get('_queueID') == item['id']:
                    item.update(status='done', project=str(target), completed=p.get('_queueCompleted', []))

    def save(self):
        atomic(self.file, dict(version=1, items=self.items))

    def state(self):
        from batch_project import LABELS
        running = self.current is not None
        status = 'Traitement en cours' if running else (
            'En attente : lecture ou traitement dans BandStudio' if self.enabled and not self.available()
            else 'File démarrée' if self.enabled else 'En pause · démarrage manuel')
        return dict(type='batchQueue', enabled=self.enabled, running=running, status=status,
                    message=self.message, ack=self.ack, libraryChanged=self.library_changed,
                    items=[{**{k: e.get(k) for k in ('id', 'title', 'kind', 'source', 'status', 'error', 'project')},
                            'completed': len(e.get('completed', [])), 'total': len(e.get('plan', [])),
                            'stage': LABELS.get(e.get('stage'), e.get('stage', ''))} for e in self.items])

    def available(self):
        return self.ready and time.monotonic() - self.heartbeat < 4

    def command(self, value):
        action = value.get('action')
        if action == 'heartbeat':
            self.ready = value.get('ready') is True
            self.heartbeat = time.monotonic()
            return
        self.message = ''
        if action == 'add':
            sources = value.get('sources', [])
            kind = value.get('kind')
            if kind != 'file' or not isinstance(sources, list) or not 1 <= len(sources) <= 100:
                raise ValueError('Ajoute de 1 à 100 fichiers à la fois.')
            if len(self.items) + len(sources) > 500:
                raise ValueError('Vide les tâches terminées avant d’ajouter d’autres morceaux (500 maximum).')
            settings = options(value.get('options') or {})
            added = []
            keys = {(e['kind'], e['source']) for e in self.items}
            for source in sources:
                if not isinstance(source, str) or not source.strip():
                    raise ValueError('Source vide ou invalide.')
                source = str(Path(source).expanduser().resolve())
                if not Path(source).is_file():
                    raise ValueError('Fichier source introuvable : ' + Path(source).name)
                key = (kind, source)
                if key in keys:
                    continue
                keys.add(key)
                added.append(dict(id=uuid.uuid4().hex, kind=kind, source=source,
                                  title=Path(source).stem,
                                  options=settings.copy(), status='pending', completed=[], error=''))
            self.items.extend(added)
            self.message = f'{len(added)} morceau(x) ajouté(s).'
            if not self.enabled:
                self.message += ' Clique sur Démarrer la file quand ta liste est prête.'
            self.ack = dict(id=value.get('requestID'), ok=True)
        elif action in ('start', 'pause'):
            self.enabled = action == 'start'
            if not self.enabled:
                self.interrupt()
        elif action == 'clearDone':
            self.items = [e for e in self.items if e['status'] != 'done']
        elif action in ('retry', 'remove', 'up'):
            item = next((e for e in self.items if e['id'] == value.get('id')), None)
            if item is None:
                raise ValueError('Cette tâche n’existe plus.')
            if item is self.current:
                self.interrupt()
            if action == 'retry':
                if item['status'] != 'error':
                    raise ValueError('Seules les tâches en erreur peuvent être réessayées.')
                item.update(status='pending', error='')
            elif action == 'remove':
                self.items.remove(item)
                shutil.rmtree(self.directory / item['id'], ignore_errors=True)
            else:
                index = self.items.index(item)
                if index:
                    self.items[index - 1], self.items[index] = item, self.items[index - 1]
        else:
            raise ValueError('Commande de file inconnue.')
        self.save()

    def interrupt(self):
        if self.proc:
            terminate(self.proc)
            self.log.close()
            self.current['status'] = 'pending'
            self.proc = self.log = self.current = None
            self.save()

    def fail(self, item, error):
        item.update(status='error', error=str(error)[-1400:])
        self.save()

    def publish(self, item):
        root = self.root(item)
        if not item.get('destination'):
            item['destination'] = safe_name(item['title']) + ' ' + item['id'][:8] + '.bandstudio'
            self.save()
        target = self.library / item['destination']
        if target.exists():
            raise ValueError('La destination existe déjà. Aucun projet n’a été remplacé.')
        root.rename(target)
        item.update(status='done', project=str(target), stage='', error='')
        self.library_changed = True
        self.save()
        shutil.rmtree(self.directory / item['id'], ignore_errors=True)

    def tick(self):
        from batch_project import apply, plan, request
        if self.proc and self.proc.poll() is not None:
            item, stage, code = self.current, self.stage, self.proc.returncode
            self.log.close()
            self.proc = self.log = self.current = None
            folder = self.directory / item['id'] / 'work'
            try:
                if code:
                    with (folder / 'traitement.log').open('rb') as f:
                        f.seek(0, 2); f.seek(max(0, f.tell() - 4000))
                        lines = f.read().decode(errors='replace').strip().splitlines()
                    raise RuntimeError(lines[-1] if lines else 'Traitement interrompu. Réessaie cette tâche.')
                p = apply(item, stage, self.root(item), folder, self.library)
                item.update(completed=p['_queueCompleted'], title=p['name'], status='pending', error='')
                self.save()
                shutil.rmtree(folder, ignore_errors=True)
            except Exception as error:
                self.fail(item, error)
        if self.proc and (not self.enabled or not self.available()):
            self.interrupt()
        if self.proc or not self.enabled or not self.available():
            return
        item = next((e for e in self.items if e['status'] == 'pending'), None)
        if item is None:
            self.enabled = False
            return
        try:
            self.recover(item)
            if item['status'] == 'done':
                self.library_changed = True
                self.save()
                return
            if not item.get('plan'):
                try:
                    item['plan'] = plan(self.engine)
                except ValueError as error:
                    # A missing common engine is a setup issue, not hundreds of failed songs.
                    self.enabled = False
                    self.message = str(error)
                    return
            pending = [s for s in item['plan'] if s not in item['completed']]
            if not pending:
                self.publish(item)
                return
            stage = pending[0]
            folder = self.directory / item['id'] / 'work'
            shutil.rmtree(folder, ignore_errors=True)
            folder.mkdir(parents=True)
            args = request(item, stage, self.root(item), folder, self.engine, self.library)
            env = {**os.environ, 'PYTHONUTF8': '1', 'PYTHONIOENCODING': 'utf-8',
                   'PYTHONUNBUFFERED': '1', 'PYTHONDONTWRITEBYTECODE': '1', 'HF_HUB_OFFLINE': '1'}
            env['PATH'] = str(self.engine / 'import-tools') + os.pathsep + env.get('PATH', '')
            self.log = (folder / 'traitement.log').open('wb')
            try:
                self.proc = subprocess.Popen(args, stdout=self.log, stderr=self.log, stdin=subprocess.DEVNULL,
                                             cwd=folder, env=env, start_new_session=os.name != 'nt',
                                             creationflags=creation_flags())
            except Exception:
                self.log.close(); self.log = None
                raise
            self.current, self.stage = item, stage
            item.update(status='running', stage=stage)
            self.save()
        except Exception as error:
            self.fail(item, error)


class Client:
    """Windows host client; the native Mac host uses the same pipe protocol."""
    def __init__(self, engine, library, receive):
        self.receive, self.lock = receive, threading.Lock()
        self.proc = subprocess.Popen([str(python_for(engine)), str(Path(engine) / 'batch_queue.py'),
                                      '--engine', str(engine), '--library', str(library)],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     text=True, encoding='utf-8', creationflags=creation_flags())
        threading.Thread(target=self.read, daemon=True).start()

    def read(self):
        for line in self.proc.stdout:
            try:
                self.receive(json.loads(line))
            except (ValueError, OSError):
                pass

    def send(self, message):
        with self.lock:
            if self.proc.poll() is not None:
                raise ValueError('La file s’est arrêtée. Ferme puis rouvre BandStudio pour la reprendre.')
            self.proc.stdin.write(json.dumps(message, ensure_ascii=True) + '\n')
            self.proc.stdin.flush()

    def close(self):
        with self.lock:
            self.proc.stdin.close()  # EOF stops the current worker and leaves checkpoints intact.
        try:
            self.proc.wait(timeout=12)
        except subprocess.TimeoutExpired:
            self.proc.terminate()


def main():
    # Load NumPy's native libraries before a thread blocks on piped stdin.
    # On Windows the reverse order can deadlock the DLL loader (numpy#24290).
    import batch_project
    parser = argparse.ArgumentParser()
    parser.add_argument('--engine', required=True)
    parser.add_argument('--library', required=True)
    args = parser.parse_args()
    directory = Path(args.library) / '.PreparationQueue'
    directory.mkdir(parents=True, exist_ok=True)
    # Hold an OS lock for the whole service lifetime; two app windows cannot run the same file.
    with (directory / 'service.lock').open('a+b') as lock:
        if os.name == 'nt':
            import msvcrt
            lock.write(b'0'); lock.flush(); lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        work = PreparationQueue(args.engine, args.library)
        def stop(signum, frame):
            raise KeyboardInterrupt()
        signal.signal(signal.SIGTERM, stop)
        incoming = queue.Queue()
        def read():
            for line in sys.stdin:
                incoming.put(line)
            incoming.put(None)
        threading.Thread(target=read, daemon=True).start()
        previous = None
        try:
            while True:
                try:
                    line = incoming.get(timeout=.2)
                except queue.Empty:
                    line = ''
                if line is None:
                    break
                value = {}
                try:
                    if line:
                        if len(line) > 1_000_000:
                            raise ValueError('Liste trop longue.')
                        value = json.loads(line)
                        work.command(value)
                    work.tick()
                except Exception as error:
                    work.message = str(error)
                    if isinstance(value, dict) and value.get('requestID'):
                        work.ack = dict(id=value['requestID'], ok=False)
                state = work.state()
                encoded = json.dumps(state, ensure_ascii=True)
                if encoded != previous:
                    print(encoded, flush=True)
                    previous = encoded
                    work.library_changed = False
        except KeyboardInterrupt:
            pass
        finally:
            work.interrupt()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps(dict(type='batchQueue', enabled=False, running=False, items=[],
                              status='File indisponible', message=str(error))), flush=True)
        sys.exit(1)
