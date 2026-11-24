"""Prepare only verified bundled DLLs before loading pythonnet on Windows.

Explorer can propagate a downloaded ZIP's Zone.Identifier stream to its DLLs.
.NET Framework then refuses Python.Runtime.dll even after the user launched the
application. Never change system policy or unblock user files or optional models.
"""
from ui_language import ui_text
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

MANIFEST = 'runtime-libraries.json'
REINSTALL = (ui_text('Télécharge à nouveau BandStudio depuis ses Releases GitHub et extrais '
             'le ZIP complet dans un nouveau dossier accessible en écriture.', 'Download BandStudio again from GitHub Releases and extract the complete ZIP into a new writable folder.'))


class StartupError(RuntimeError):
    pass


def bundled_libraries(engine):
    """Read the build-time inventory, rejecting paths outside this Python runtime."""
    runtime = (Path(engine) / 'python').resolve()
    manifest = runtime / MANIFEST
    if not manifest.exists():
        # Code-only updates keep older runtimes. Already working installations
        # can continue; a blocked legacy runtime needs the complete new ZIP.
        return None
    try:
        value = json.loads(manifest.read_text(encoding='utf-8'))
        if value.get('schema') != 1 or not isinstance(value.get('libraries'), list):
            raise ValueError(ui_text('format du manifeste', 'manifest format'))
        entries, seen = [], set()
        for item in value['libraries']:
            name, digest = item['path'], item['sha256']
            path = PurePosixPath(name)
            if (path.is_absolute() or not path.parts or str(path) != name
                    or any(part in ('.', '..') or part.endswith((' ', '.')) for part in path.parts)
                    or '\\' in name or ':' in name or path.suffix.lower() not in ('.dll', '.pyd')
                    or name.lower() in seen or not re.fullmatch('[0-9a-f]{64}', digest)):
                raise ValueError(ui_text('bibliothèque non autorisée', 'library not allowed'))
            target = (runtime / name).resolve()
            if not target.is_relative_to(runtime) or not target.is_file():
                raise ValueError(ui_text('bibliothèque absente ou hors du moteur', 'library missing or outside the engine'))
            entries.append((name, target, digest))
            seen.add(name.lower())
        if 'lib/site-packages/pythonnet/runtime/python.runtime.dll' not in seen:
            raise ValueError(ui_text('Python.Runtime.dll absent du manifeste', 'Python.Runtime.dll missing from the manifest'))
        return entries
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        raise StartupError(ui_text('Le moteur Windows est incomplet ou son manifeste est invalide. ', 'The Windows engine is incomplete or its manifest is invalid. ') + REINSTALL) from error


def unblock_bundled_libraries(engine):
    """Windows only in production; tests model ADS with colon-named local files."""
    entries = bundled_libraries(engine)
    if entries is None:
        return {'manifest': 'absent', 'checked': 0, 'unblocked': 0}
    pending = []
    for name, target, expected in entries:
        stream = Path(str(target) + ':Zone.Identifier')
        try:
            # Do not log this stream: it can contain private download URLs.
            with stream.open('rb') as source:
                source.read(1)
        except FileNotFoundError:
            continue
        except OSError as error:
            raise StartupError(ui_text('Impossible de vérifier le blocage Windows des bibliothèques. ', 'Could not check the Windows block status of the libraries. ') + REINSTALL) from error
        try:
            with target.open('rb') as source:
                actual = hashlib.file_digest(source, 'sha256').hexdigest()
        except OSError as error:
            raise StartupError(ui_text('Impossible de vérifier une bibliothèque de BandStudio. ', 'Could not verify a BandStudio library. ') + REINSTALL) from error
        if actual != expected:
            raise StartupError(ui_text('Une bibliothèque de BandStudio a été modifiée : ', 'A BandStudio library was modified: ') + name + '. ' + REINSTALL)
        pending.append(stream)
    # Verify every marked file before removing any download marker.
    for stream in pending:
        try:
            stream.unlink()
        except OSError as error:
            raise StartupError(ui_text('Windows empêche la préparation des bibliothèques de BandStudio. ', 'Windows prevented BandStudio from preparing its libraries. ') + REINSTALL) from error
    return {'manifest': 'verified', 'checked': len(entries), 'unblocked': len(pending)}


def load_clr():
    try:
        import clr  # noqa: F401 -- initialize once, before pywebview's retry logic
    except Exception as error:
        raise StartupError(
            ui_text('Le composant .NET de BandStudio ne peut pas démarrer. '
            'Si cette installation vient d’un ancien ZIP, ouvre les Propriétés du ZIP, '
            'coche Débloquer, puis extrais-le dans un nouveau dossier. '
            'Vérifie aussi que .NET Framework 4.8 est disponible. ', 'BandStudio’s .NET component could not start. For an older ZIP, open its Properties, choose Unblock and extract it into a new folder. Check that .NET Framework 4.8 is available. ') + REINSTALL
        ) from error
