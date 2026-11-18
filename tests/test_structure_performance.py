"""Numerical equivalence and cleanup for the bounded SongFormer inference path."""
from types import SimpleNamespace
import pytest
import reacue_structure as structure

torch=pytest.importorskip('torch')
nn=torch.nn


def test_feature_only_encoder_matches_layer_ten_without_running_unused_tail():
    class Conformer(nn.Module):
        def __init__(self):
            super().__init__()
            self.layers=nn.ModuleList([nn.Linear(8,8) for _ in range(12)])
            self.final=nn.LayerNorm(8)
            self.seen=[]
        def forward(self,x,output_hidden_states=False):
            states=[]
            for i,layer in enumerate(self.layers):
                states.append(x)
                x=layer(x)
                self.seen.append(i)
            return dict(hidden_states=states+[self.final(x)])
    class Encoder(nn.Module):
        def __init__(self):
            super().__init__();self.conv=nn.Identity();self.conformer=Conformer()
    model=Encoder().eval();values=torch.randn(1,17,8)
    expected=model.conformer(values)['hidden_states'][10]
    model.conformer.seen.clear()
    original=lambda *a,**k:'fallback'
    encode=structure._feature_encoder(model,original,True)
    actual=encode(values)[1][10]
    torch.testing.assert_close(expected,actual,rtol=0,atol=0)
    assert model.conformer.seen==list(range(10))
    assert not model.conformer.layers[10]._forward_pre_hooks
    assert encode(values,attention_mask=torch.ones(1,17))=='fallback'
    model.train()
    assert encode(values)=='fallback'


def test_feature_hook_removed_after_inference_error():
    class Failure(nn.Module):
        def forward(self,x,**kwargs):raise RuntimeError('inference failed')
    conformer=Failure();conformer.layers=nn.ModuleList([nn.Identity() for _ in range(12)])
    model=SimpleNamespace(training=False,conv=nn.Identity(),conformer=conformer)
    with pytest.raises(RuntimeError,match='inference failed'):
        structure._feature_encoder(model,None,False)(torch.zeros(1,4,8))
    assert not conformer.layers[10]._forward_pre_hooks


@pytest.mark.parametrize('masked',[False,True])
def test_sdpa_matches_dense_rotary_attention(masked):
    class Attention(nn.Module):
        def __init__(self):
            super().__init__();self.num_heads=2;self.head_size=4;self.position_embeddings_type='rotary'
            self.linear_q=nn.Linear(8,8);self.linear_k=nn.Linear(8,8)
            self.linear_v=nn.Linear(8,8);self.linear_out=nn.Linear(8,8)
        def _apply_rotary_embedding(self,x,positions):return x*positions
    torch.manual_seed(5)
    attention=Attention().eval();x=torch.randn(2,19,8);position=torch.randn(1,19,8)
    mask=torch.zeros(2,1,19,19) if masked else None
    if mask is not None:mask[:,:,:,-3:]=-10000
    def heads(projection,values):return projection(values).view(2,19,2,4).transpose(1,2)
    q=heads(attention.linear_q,x*position);k=heads(attention.linear_k,x*position);v=heads(attention.linear_v,x)
    scores=q@k.transpose(-2,-1)/2
    if mask is not None:scores=scores+mask
    expected=attention.linear_out((scores.softmax(-1)@v).transpose(1,2).reshape(2,19,8))
    fallback=lambda *a:'fallback'
    actual,_=structure._sdpa_forward(attention,fallback)(x,mask,position)
    torch.testing.assert_close(expected,actual,rtol=1e-5,atol=1e-6)
    assert structure._sdpa_forward(attention,fallback)(x,output_attentions=True)=='fallback'
    attention.train()
    assert structure._sdpa_forward(attention,fallback)(x,mask,position)=='fallback'


class SmallSubsampler(nn.Module):
    """Same temporal receptive field, tiny channel count for numerical regressions."""
    def __init__(self):
        super().__init__()
        self.blocks=nn.ModuleList([
            nn.ModuleList([nn.Conv2d(channels,2,3,stride=2,padding=1),nn.Conv2d(2,2,3,padding=1),nn.Conv2d(channels,2,3,stride=2,padding=1)])
            for channels in (1,2)])
        self.calls=[]
    def forward(self,values):
        self.calls.append(values.shape[-1])
        x=values.unsqueeze(1)
        for a,b,c in self.blocks:x=(b(a(x).relu())+c(x)).relu()
        return x.permute(0,3,1,2).flatten(2)


@pytest.mark.parametrize('frames',[512,513,1024,1051])
def test_tiled_convolution_preserves_seams_and_odd_final_padding(frames):
    model=SmallSubsampler().eval();values=torch.randn(1,8,frames)
    expected=model(values);model.calls.clear()
    actual=structure._tiled_convolution(model,values)
    torch.testing.assert_close(expected,actual,rtol=1e-5,atol=1e-6)
    assert max(model.calls)<=536


@pytest.mark.parametrize('offset,frames',[(0,500),(500,500),(1000,501)])
def test_local_convolution_reuses_only_matching_interior_and_recomputes_edges(offset,frames):
    model=SmallSubsampler().eval()
    cache=structure._ConvolutionReuse(model)
    audio=torch.zeros(1,1501*240);mel=torch.randn(1,8,1501)
    cache.wave=audio;cache(mel)
    local=mel[...,offset:offset+frames].clone()
    local[...,:5]+=2;local[...,-5:]-=3  # Local STFT boundary differs from whole-context STFT.
    cache.wave=audio[:,offset*240:(offset+frames)*240]
    expected=model(local);model.calls.clear()
    actual=cache(local)
    torch.testing.assert_close(expected,actual,rtol=1e-5,atol=1e-6)
    assert max(model.calls)<=80 and sum(model.calls)<160
    local[...,100]+=1  # Changed normalization/content must disable reuse.
    expected=model(local);model.calls.clear()
    torch.testing.assert_close(cache(local),expected,rtol=1e-5,atol=1e-6)
    assert max(model.calls)>=frames
