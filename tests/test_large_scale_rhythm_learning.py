"""Run with the installed rhythm Python (torch), no pytest dependency required."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
try:
    import torch
    from beat_this.model.beat_tracker import SumHead
except ImportError:
    torch = None
    SumHead = None

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import large_scale_rhythm_learning as learning


@unittest.skipIf(torch is None, 'Run with BandStudio’s rhythm Python for the training checks')
class LargeScaleLearningTests(unittest.TestCase):
    def setUp(self):torch.set_num_threads(2)

    def test_packaged_decoder_measures_cues_without_source_tree_imports(self):
        repo=Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for name in learning.DECODER_FILES:
                shutil.copy2(repo/'desktop/studio'/name,root/name)
            shutil.copy2(repo/'tools/large_scale_rhythm_learning.py',root/'learning.py')
            code='''
import sys
sys.path.insert(0,sys.argv[1])
import numpy as np
from learning import measure
times=np.arange(.5,20,.5)
reference=np.column_stack((times,np.arange(len(times))%4+1))
beat=np.full(1000,-8.); down=beat.copy()
beat[np.rint(times*50).astype(int)]=8.
down[np.rint(times[::4]*50).astype(int)]=8.
result=measure(dict(duration=20.,hasDownbeats=True),reference,beat,down)
assert all(value==1. for value in result.values()),result
'''
            completed=subprocess.run([sys.executable,'-I','-c',code,str(root)],cwd=root,
                                     capture_output=True,text=True,timeout=60)
            self.assertEqual(completed.returncode,0,completed.stdout+completed.stderr)

    def test_frame_stitching_preserves_first_last_and_overlap(self):
        class Model(torch.nn.Module):
            def __init__(self):
                super().__init__();self.task_heads=SumHead(512)
            def forward(self,x):return self.task_heads(torch.cat([x]*4,dim=-1))
        model=Model().eval();spect=torch.randn(1501,128)
        x,b,d,error=learning.extract_features(model,spect)
        np.testing.assert_allclose(x,np.tile(spect.numpy(),(1,4)),atol=1e-6)
        self.assertEqual(len(b),1501);self.assertEqual(len(d),1501);self.assertLess(error,.0001)

    def test_matching_is_one_to_one(self):
        self.assertAlmostEqual(learning.f1([5,5.04],[5.02]),2/3)
        self.assertEqual(learning.f1([0,6,7],[0,6,7]),1)

    def test_gate_rejects_a_broken_previously_correct_track(self):
        rows=[dict(id=str(i),style='rock',before={k:.6 for k in learning.METRICS},after={k:.8 for k in learning.METRICS}) for i in range(100)]
        rows.append(dict(id='regression',style='rock',before={k:1. for k in learning.METRICS},after={k:.8 for k in learning.METRICS}))
        protocol={'gate':dict(minMeanGain=.01,minCueGain=.005,maxMetricDrop=.002,maxStyleMeanDrop=.01,maxHarmfulFraction=.02)}
        result=learning.gate(rows,protocol)
        self.assertFalse(result['passed']);self.assertFalse(result['checks']['correctTracks'])

    def test_artist_and_work_groups_do_not_leak_in_prepared_manifest(self):
        path=Path(__file__).resolve().parents[1]/'tmp/learning-scale-preflight/manifest.json'
        if not path.exists():self.skipTest('Prepare the preflight corpus first')
        manifest=json.loads(path.read_text());sets={s:{r['group'] for r in manifest['excerpts'] if r['split']==s} for s in ('train','validation','test')}
        self.assertFalse(sets['train']&sets['validation']);self.assertFalse(sets['train']&sets['test']);self.assertFalse(sets['validation']&sets['test'])
        test=[r for r in manifest['excerpts'] if r['split']=='test']
        self.assertGreaterEqual(len(test),80)
        self.assertFalse(any(r['previouslyEvaluated'] for r in test))
        self.assertEqual(len({r['inputSHA256'] for r in manifest['excerpts']}),len(manifest['excerpts']))

    def test_missing_downbeat_annotation_is_not_a_negative_label(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'x.beats';np.savetxt(path,[.2,.6,1.])
            row=dict(id='x',frames=100,hasDownbeats=False,annotationSHA256=learning.digest(path))
            y,reference=learning.labels_for(row,dict(annotationRoot=folder))
            self.assertEqual(y[0].sum(),3);self.assertEqual(reference.shape[1],1)
            self.assertFalse(row['hasDownbeats']) # training masks this channel entirely

    def test_actual_gradient_update_and_validation_only_model_selection(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);features=root/'features';features.mkdir();annotations=root/'annotations';annotations.mkdir()
            rows=[];rng=np.random.default_rng(3)
            for name,split in [('train_a','train'),('train_b','train'),('val','validation'),('hidden','test')]:
                path=annotations/(name+'.beats');np.savetxt(path,[[.3,1],[.7,2],[1.1,3],[1.5,4],[1.9,1],[2.3,2]])
                rows.append(dict(id=name,frames=150,duration=3.,hasDownbeats=True,split=split,style='rock',genre='rock',annotationSHA256=learning.digest(path)))
                if split!='test':np.save(features/(name+'.npy'),rng.normal(size=(150,512)).astype('float32'))
            manifest=dict(excerpts=rows,features=str(features),annotationRoot=str(annotations))
            protocol=dict(seed=7,epochs=1,evaluateEpochs=[1],learningRate=.0003,batchSize=2,targetStyleWeight=3,
                positiveWeights={'beat':19,'downbeat':86},shiftToleranceFrames=3,distillationWeight=.02,blendCandidates=[1.],
                gate=dict(minMeanGain=.01,minCueGain=.005,maxMetricDrop=.002,maxStyleMeanDrop=.01,maxHarmfulFraction=.02))
            learning.atomic(root/'manifest.json',manifest);learning.atomic(root/'protocol.json',protocol)
            learning.save_npz(root/'initial-head.npz',weight=np.zeros((2,512),dtype='float32'),bias=np.zeros(2,dtype='float32'))
            def evaluate(selected,*args):
                self.assertEqual([r['id'] for r in selected],['val'])
                return [dict(id='val',style='rock',before={k:.5 for k in learning.METRICS},after={k:.6 for k in learning.METRICS})]
            with patch.object(learning,'evaluate',side_effect=evaluate):
                learning.train(manifest,protocol,root,learning.Progress(root))
            final=np.load(root/'frozen-head.npz',allow_pickle=False)
            self.assertGreater(float(abs(final['weight']).sum()),0)
            self.assertTrue((root/'training.pt').exists());self.assertTrue((root/'frozen.json').exists())


if __name__=='__main__':unittest.main()
