"""Structured, monotonic worker progress. Percentages count work, never elapsed time."""
from ui_language import ui_text, using_english
from contextlib import contextmanager
import json
import math
import os
from pathlib import Path
import time
from types import SimpleNamespace

WINDOWS = os.name == 'nt'


class Reporter:
    def __init__(self, output, task):
        self.path = Path(output).resolve().parent / 'progress.json'
        self.state = dict(task=task, stage=task, progress=0., indeterminate=True,
                          progressLabel=ui_text('Préparation…', 'Preparing…'))
        self.update()

    def update(self, *, completed=None, total=None, progress=None, **values):
        if completed is not None and total is not None and total > 0:
            progress = 100 * completed / total
            values.update(completed=completed, total=total, indeterminate=False)
        if progress is not None and math.isfinite(progress):
            # Only finish() may publish 100: audio and result files must exist first.
            self.state['progress'] = max(self.state['progress'], min(99., max(0., progress)))
        self.state.update(values)
        self._write()

    def finish(self):
        self.state.update(progress=100., indeterminate=False, progressLabel=ui_text('Terminé', 'Completed'), finished=True)
        self._write()

    def fail(self):
        self.state.update(indeterminate=False, failed=True, progressLabel=ui_text('Traitement interrompu', 'Processing interrupted'))
        self._write()

    def _write(self):
        write_status(self.path, json.dumps(self.state, ensure_ascii=False, allow_nan=False))


def replace_file(source, target, attempts=40, delay=.025):
    """os.replace, tolerant of Windows readers.

    On Windows, replacing a file fails with PermissionError (WinError 5) while
    another process holds it open — the studio host polls progress.json several
    times per second, and antivirus or sync tools briefly open new files too.
    Those locks last milliseconds, so retry instead of failing the whole job.
    """
    for attempt in range(attempts):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if not WINDOWS or attempt == attempts - 1:
                raise
            time.sleep(delay)


def write_status(path, text):
    """Publish a UI status file. A busy status file must never abort an analysis."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(text, encoding='utf-8')
    try:
        replace_file(tmp, path)
    except PermissionError:
        # Readers open with shared write access on Windows: an in-place write still
        # succeeds. A reader catching a half-written file already treats it as empty.
        try:
            path.write_text(text, encoding='utf-8')
        except OSError:
            pass
        try:
            tmp.unlink()
        except OSError:
            pass


_active = None


@contextmanager
def reporting(output, task):
    global _active
    previous, _active = _active, Reporter(output, task)
    try:
        yield _active
        if not Path(output).is_file():
            raise RuntimeError(ui_text('Le traitement n’a pas créé son résultat.', 'Processing did not produce a result.'))
        _active.finish()
    except BaseException:
        _active.fail()
        raise
    finally:
        _active = previous


def emit(info=None, **values):
    if _active is not None:
        _active.update(**{**(info or {}), **values})


def phase_items(items, phase, phases, label):
    """Count actual work within explicit, equally weighted phases (not a duration ETA)."""
    items = list(items)
    for index, item in enumerate(items):
        emit(progress=100*(phase+index/len(items))/phases, progressBasis='steps',
             progressLabel=f'{label} · {index+1}/{len(items)}', indeterminate=False)
        yield item
        emit(progress=100*(phase+(index+1)/len(items))/phases)
    if not items:
        emit(progress=100*(phase+1)/phases, progressBasis='steps')


class PassProgress:
    """Wrap Demucs' chunk iterator; count every model and every shift exactly once."""
    def __init__(self, passes, notify=emit):
        self.passes, self.notify, self.index = max(1, passes), notify, 0

    def wrap(self, iterable, **kwargs):
        self.index += 1
        index, count = self.index, len(iterable)
        def report(done):
            fraction = done / count if count else 1
            self.notify(dict(completed=index - 1 + fraction, total=self.passes,
                             passIndex=index, passCount=self.passes, passProgress=100 * fraction,
                             progressLabel=(f'Passage {index} of {self.passes}' if using_english() else f'Passage {index} sur {self.passes}')))
        report(0)
        for done, item in enumerate(iterable, 1):
            yield item
            # The caller has now computed and accumulated this chunk successfully.
            report(done)

    @contextmanager
    def track(self, module):
        original = module.tqdm
        module.tqdm = SimpleNamespace(tqdm=self.wrap)
        try:
            yield
        finally:
            module.tqdm = original


@contextmanager
def legacy_status(module, *, phases=1):
    """Bridge existing standalone engine callbacks, even without a legacy status file."""
    original = module._write_status
    def report(path, state, **values):
        original(path, state, **values)
        labels = values.get('step', '').split(' / ', 1)
        label = labels[-1] if using_english() else labels[0]
        if state == 'done':
            if phases==1:
                emit(progress=99, progressLabel=ui_text('Enregistrement du résultat…', 'Saving result…'), indeterminate=True)
            else:
                emit(progress=100/phases, progressBasis='steps', progressLabel=ui_text('Transcription terminée', 'Transcription complete'), indeterminate=False)
        elif state == 'running':
            if values.get('total', 0) > 0:
                done, total = values.get('done', 0), values['total']
                label=label if label and not label[:1].isdigit() else (f'Excerpt {min(done + 1, total)} of {total}' if using_english() else f'Extrait {min(done+1,total)} sur {total}')
                if phases==1:
                    emit(completed=done, total=total, progressLabel=label)
                else:
                    emit(progress=100*min(done,total)/(total*phases), progressBasis='steps',
                         progressLabel='Transcription · '+label, indeterminate=False)
            else:
                emit(progressLabel=label or ui_text('Calcul en cours…', 'Processing…'), indeterminate=True)
    module._write_status = report
    try:
        yield
    finally:
        module._write_status = original


@contextmanager
def track_beat_chunks(module):
    original = module.split_piece
    def split(*args, **kwargs):
        chunks, starts = original(*args, **kwargs)
        def tracked():
            for index, chunk in enumerate(chunks):
                emit(completed=index, total=len(chunks), progressLabel=(f'Excerpt {index + 1} of {len(chunks)}' if using_english() else f'Extrait {index+1} sur {len(chunks)}'))
                yield chunk
                emit(completed=index+1, total=len(chunks))
        return tracked(), starts
    module.split_piece = split
    try:
        yield
    finally:
        module.split_piece = original


@contextmanager
def track_structure(app, audio, window):
    """Observe the pinned SongFormer model calls without altering tensors or inference."""
    from contextlib import ExitStack
    from unittest.mock import patch
    methods = [('muq_model', 'forward'), ('musicfm_model', 'get_predictions'), ('msa_model', 'infer')]
    if not all(hasattr(getattr(app, name, None), method) for name, method in methods):
        yield
        return
    import soundfile as sf
    duration = sf.info(audio).duration
    # Each window: two global embeddings, two per 30-second excerpt, one classifier.
    original_process = app.process_audio
    def process(*args, **kwargs):
        current_window = kwargs.get('win_size', window)
        total = sum(3 + 2 * math.ceil(min(current_window, duration-start) / 30)
                    for start in range(0, math.ceil(duration), current_window))
        done = 0  # A GPU retry restarts the count; the reporter preserves its high-water mark.
        def observe(original, model):
            def wrapped(*args, **kwargs):
                nonlocal done
                emit(completed=done, total=total, progressBasis='steps',
                     progressLabel=(f'Music analysis · step {min(done + 1, total)} of {total}' if using_english() else f'Analyse musicale · étape {min(done+1,total)} sur {total}'))
                # Real completed encoder layers give feedback inside each long call.
                conformer = getattr(getattr(model, 'model', model), 'conformer', None)
                layers = getattr(conformer, 'layers', ())
                with ExitStack() as hooks:
                    for index, layer in enumerate(layers[:10]):
                        def completed(_module, _args, _result, index=index):
                            emit(completed=done+(index+1)/10, total=total)
                        hooks.callback(layer.register_forward_hook(completed).remove)
                    result = original(*args, **kwargs)
                done += 1
                emit(completed=done, total=total)
                return result
            return wrapped
        with ExitStack() as stack:
            for name, method in methods:
                model = getattr(app, name)
                stack.enter_context(patch.object(model, method, observe(getattr(model, method), model)))
            return original_process(*args, **kwargs)
    app.process_audio = process
    try:
        yield
    finally:
        app.process_audio = original_process
