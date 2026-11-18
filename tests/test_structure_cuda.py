"""SongFormer CUDA recovery, including OOM during partial model loading."""
import sys
from types import SimpleNamespace
import weakref

import pytest
import reacue_structure as structure


class Model:
    def __init__(self,device='cpu'):self.device=device
    def to(self,device):self.device=device;return self


@pytest.fixture
def cuda(monkeypatch):
    calls=[]
    gpu=SimpleNamespace(is_available=lambda:True,empty_cache=lambda:calls.append('empty'),
                        get_device_properties=lambda _:SimpleNamespace(total_memory=6*2**30),
                        mem_get_info=lambda:(5*2**30,6*2**30))
    torch=SimpleNamespace(cuda=gpu)
    monkeypatch.setitem(sys.modules,'torch',torch)
    monkeypatch.delenv('REACUE_DEVICE',raising=False)
    monkeypatch.setattr(structure.reacue_metal,'device',lambda _: 'cpu')
    monkeypatch.setattr(structure.reacue_performance,'profile',lambda:'balanced')
    return torch,calls


def app():
    return SimpleNamespace(device='cuda:0',muq_model=Model('cuda'),musicfm_model=Model('cuda'),
        msa_model=Model('cuda'),rule_post_processing=lambda x:x,format_as_segments=lambda x:x)


def test_oom_drops_traceback_moves_models_and_retries_once(cuda):
    target=app();attempts=[];notices=[];references=[]
    def process(audio,**kw):
        attempts.append((target.device,kw))
        if target.device.startswith('cuda'):
            tensor=Model('cuda');references.append(weakref.ref(tensor))
            raise RuntimeError('CUDA out of memory. Tried to allocate 4.52 GiB')
        assert references[0]() is None  # No failed inference tensor retained by traceback.
        assert all(getattr(target,n).device=='cpu' for n in ('muq_model','musicfm_model','msa_model'))
        return None,[dict(start=0,end=120,label='verse')]
    target.process_audio=process
    result=structure.segments_from_app(target,'song.wav',120,notify=notices.append)
    assert result[0]['label']=='verse'
    assert [x[0] for x in attempts]==['cuda:0','cpu']
    assert attempts[0][1]==dict(win_size=120,hop_size=120)
    assert attempts[1][1]==dict(win_size=60,hop_size=60)
    assert cuda[1]==['empty'] and notices[0]['device']=='cpu'
    structure.segments_from_app(target,'next.wav',120)
    assert attempts[-1][0]=='cpu' and cuda[1]==['empty']


@pytest.mark.parametrize('failure',['CUDA invalid tensor shape','CPU out of memory'])
def test_non_gpu_memory_errors_are_reported_without_retry(cuda,failure):
    target=app();attempts=[]
    if failure.startswith('CPU'):target.device='cpu'
    def process(*a,**kw):attempts.append(1);raise RuntimeError(failure)
    target.process_audio=process
    with pytest.raises(RuntimeError,match=failure):structure.segments_from_app(target,'song.wav',120)
    assert attempts==[1] and cuda[1]==[]


def test_cpu_retry_failure_is_not_retried_again(cuda):
    target=app();attempts=[]
    def process(*a,**kw):
        attempts.append(target.device)
        raise RuntimeError('CUDA out of memory' if len(attempts)==1 else 'CPU failure')
    target.process_audio=process
    with pytest.raises(RuntimeError,match='CPU failure'):structure.segments_from_app(target,'song.wav',120)
    assert attempts==['cuda:0','cpu']


@pytest.mark.parametrize('force_cpu',[False,True])
def test_partial_cuda_initialization_can_restart_cleanly_on_cpu(cuda,monkeypatch,force_cpu):
    torch,cleared=cuda;target=app();attempts=[]
    target.download_all=lambda **kw:None
    if force_cpu:monkeypatch.setenv('REACUE_DEVICE','cpu')
    def initialize(**kw):
        target.device='cuda' if torch.cuda.is_available() else 'cpu'
        attempts.append(target.device)
        target.muq_model=Model(target.device)
        if target.device=='cuda':raise RuntimeError('CUDA out of memory')
        if not force_cpu:assert target.musicfm_model is None and target.msa_model is None
        target.musicfm_model=Model();target.msa_model=Model()
    target.initialize_models=initialize
    structure.init_models(target)
    assert attempts==(['cpu'] if force_cpu else ['cuda','cpu'])
    assert target.device=='cpu' and torch.cuda.is_available()  # Override was scoped to initialization.
    assert cleared==([] if force_cpu else ['empty'])


def test_small_or_busy_gpu_uses_short_windows_without_confusing_host_ram(cuda,monkeypatch):
    torch,_=cuda;monkeypatch.setattr(structure,'ram_gb',lambda:64)
    assert structure.choose_window()==120
    torch.cuda.get_device_properties=lambda _:SimpleNamespace(total_memory=24*2**30)
    assert structure.choose_window()==120  # Only 5 GiB free.
    torch.cuda.mem_get_info=lambda:(20*2**30,24*2**30)
    assert structure.choose_window()==420
    monkeypatch.setenv('REACUE_DEVICE','cpu')
    assert structure.choose_window()==60
    assert structure.choose_window(ram=8)==30


def test_cpu_and_shared_memory_devices_never_default_to_whole_song(cuda,monkeypatch):
    torch,_=cuda
    torch.cuda.is_available=lambda:False
    monkeypatch.setattr(structure,'ram_gb',lambda:16)
    assert structure.choose_window()==60
    monkeypatch.setattr(structure.reacue_metal,'device',lambda _:'mps')
    assert structure.choose_window()==60
    monkeypatch.setattr(structure,'ram_gb',lambda:32)
    assert structure.choose_window()==120
    monkeypatch.setattr(structure.reacue_performance,'profile',lambda:'fast')
    assert structure.choose_window()==30
    assert structure.choose_window(300)==300  # Deliberate CLI override remains available.


@pytest.mark.parametrize('tail',[0,1,1024,1025])
def test_tiny_audio_tail_cannot_spin_forever_and_loader_is_restored(tail):
    samples=list(range(30*24000+tail))
    original=lambda *a,**k:(samples,24000)
    target=SimpleNamespace(librosa=SimpleNamespace(load=original))
    target.process_audio=lambda audio,**kw:target.librosa.load(audio)
    result,rate=structure._process_audio(target,'audio.wav',30)
    assert len(result)==(30*24000 if tail<=1024 else len(samples))
    assert len(samples)==30*24000+tail  # Never modify source data.
    assert target.librosa.load is original and rate==24000


def test_empty_audio_fails_without_entering_upstream_loop():
    original=lambda *a,**k:([],24000)
    target=SimpleNamespace(librosa=SimpleNamespace(load=original))
    target.process_audio=lambda audio,**kw:target.librosa.load(audio)
    with pytest.raises(ValueError,match='trop court'):
        structure._process_audio(target,'empty.wav',60)
    assert target.librosa.load is original
