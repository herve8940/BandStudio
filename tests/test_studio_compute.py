"""Compute selection and recovery without claiming a physical GPU in CI."""
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'desktop/studio'))
import compute


def torch_device(*,available=True,broken=False):
    calls=[]
    def ones(count,device):
        calls.append(('probe',device))
        if broken:raise RuntimeError('CUDA driver initialization failed')
        return 1
    cuda=SimpleNamespace(is_available=lambda:available,synchronize=lambda:calls.append('sync'),
        get_device_properties=lambda n:SimpleNamespace(name='NVIDIA GeForce GTX 1650',total_memory=4096*1024**2),
        empty_cache=lambda:calls.append('empty'))
    return SimpleNamespace(cuda=cuda,ones=ones,version=SimpleNamespace(cuda='12.4')),calls


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.delenv('REACUE_DEVICE',raising=False)
    monkeypatch.setattr(compute.diagnostics,'event',lambda *args,**kwargs:None)


def test_gtx1650_uses_cuda_after_real_operation_and_short_segments():
    torch,calls=torch_device()
    info=compute.select_device(torch)
    assert info['device']=='cuda' and info['vram_mb']==4096
    assert compute.demucs_segment(info)==4
    assert calls==[('probe','cuda'),'sync']


def test_cpu_override_and_unavailable_gpu_do_not_allocate_cuda(monkeypatch):
    torch,calls=torch_device(available=False)
    assert compute.select_device(torch)['device']=='cpu' and calls==[]
    torch,calls=torch_device()
    monkeypatch.setenv('REACUE_DEVICE','cpu')
    assert compute.select_device(torch)['device']=='cpu' and calls==[]


def test_broken_driver_falls_back_to_cpu():
    torch,calls=torch_device(broken=True)
    info=compute.select_device(torch)
    assert info['device']=='cpu' and 'driver' in info['fallback']


def test_cuda_oom_releases_model_and_retries_once_on_cpu():
    torch,calls=torch_device();attempts=[];notices=[]
    def run(info):
        attempts.append(info['device'])
        if info['device']=='cuda':raise RuntimeError('CUDA out of memory')
        return 'audio result'
    result,info=compute.run(torch,'separate',run,cleanup=lambda:calls.append('model.cpu'),notify=notices.append)
    assert result=='audio result' and attempts==['cuda','cpu']
    assert calls[-2:]==['model.cpu','empty']
    assert [i['device'] for i in notices]==['cuda','cpu'] and info['fallback']=='CUDA out of memory'


def test_invalid_model_is_not_disguised_as_gpu_failure():
    torch,calls=torch_device()
    def invalid(info):raise RuntimeError('invalid tensor shape')
    with pytest.raises(RuntimeError,match='invalid tensor'):compute.run(torch,'separate',invalid)
    assert 'empty' not in calls


def test_cpu_retry_failure_is_reported():
    torch,calls=torch_device()
    def fail(info):raise RuntimeError('CUDA out of memory' if info['device']=='cuda' else 'invalid CPU input')
    with pytest.raises(RuntimeError,match='invalid CPU'):compute.run(torch,'smartgrid',fail)
