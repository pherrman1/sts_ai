"""Weighting isolation, selection population, and one-use development fit checks."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import torch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import heart_outcome_weighting as weighting


def meta():
    return [{'seed':s,'index':i,'label':s%2,'act':1,'floor':f} for s in range(4) for i,f in enumerate((0,8,16))]


class WeightingTest(unittest.TestCase):
    def test_distribution_changes_future_length_weight_only(self):
        rows=[{'seed':1}]*3+[{'seed':2}]
        np.testing.assert_allclose(weighting.sampling_weights(rows,'source'),[1/6,1/6,1/6,1/2])
        np.testing.assert_allclose(weighting.sampling_weights(rows,'visitation'),[.25]*4)
        with self.assertRaises(ValueError): weighting.sampling_weights(rows,'test')
        with self.assertRaises(ValueError): weighting.sampling_weights([],'source')

    def test_landmarks_first_actual_and_no_invented_states(self):
        rows=meta();rows=[r for r in rows if not (r['seed']==1 and r['floor']>=8)]
        self.assertEqual([rows[i]['seed'] for i in weighting.landmark_indices(rows,'start')],[0,1,2,3])
        self.assertEqual([rows[i]['seed'] for i in weighting.landmark_indices(rows,'act1_floor8')],[0,2,3])
        self.assertEqual([rows[i]['floor'] for i in weighting.landmark_indices(rows,'act1_floor16')],[16]*3)
        with self.assertRaises(ValueError): weighting.landmark_indices(rows,'posthoc')

    def test_common_initialization_normalization_bias_and_architecture(self):
        norm={'mean':torch.arange(64,dtype=torch.float32),'scale':torch.full((64,),2.)}
        before=copy.deepcopy(norm)
        a=weighting.make_head(norm,0,'cpu');b=weighting.make_head(norm,0,'cpu')
        self.assertEqual(weighting.tensor_sha(a.state_dict()),weighting.tensor_sha(b.state_dict()))
        self.assertEqual(sum(p.numel() for p in a.parameters()),4225)
        self.assertAlmostEqual(torch.sigmoid(a.layers[-1].bias).item(),126/1080,places=6)
        for k,v in norm.items(): self.assertTrue(torch.equal(v,before[k]))

    def exercise_fit(self,device):
        torch.set_num_threads(1);torch.use_deterministic_algorithms(True)
        torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
        x=torch.arange(12*64,dtype=torch.float32).reshape(12,64)/1000
        y=torch.tensor([r['label'] for r in meta()],dtype=torch.float32)
        norm={'mean':x.mean(0),'scale':torch.ones(64)}
        before=x.clone();w=np.full(12,1/12)
        a,history,initial=weighting.fit(x.to(device),y.to(device),x.to(device),y.to(device),norm,w,1,time.monotonic()+30,steps=10,every=5)
        b,_,initial2=weighting.fit(x.to(device),y.to(device),x.to(device),y.to(device),norm,w,1,time.monotonic()+30,steps=10,every=5)
        self.assertEqual(len(history),2);self.assertEqual(initial,initial2)
        self.assertEqual(weighting.tensor_sha(a['state']),weighting.tensor_sha(b['state']))
        for k,v in norm.items(): self.assertTrue(torch.equal(a['state'][k],v))
        self.assertTrue(torch.equal(x,before))
        h=weighting.make_head(norm,0,device);h.load_state_dict(a['state'])
        with torch.inference_mode(): score=torch.nn.functional.binary_cross_entropy_with_logits(h(x.to(device)),y.to(device),reduction='none').double().mean().item()
        self.assertAlmostEqual(a['validationVisitationBce'],score,places=8)

    def test_cpu_determinism_and_common_validation_selection(self): self.exercise_fit('cpu')

    @unittest.skipUnless(torch.cuda.is_available() and os.environ.get('CUBLAS_WORKSPACE_CONFIG')==':4096:8','optional deterministic CUDA fixture')
    def test_cuda_sampler_and_paired_initialization(self): self.exercise_fit('cuda')

    def test_invalid_weights_fail_before_update(self):
        x=torch.zeros(12,64);y=torch.zeros(12);norm={'mean':x[0],'scale':torch.ones(64)}
        for w in (np.full(12,np.nan),np.full(12,-1.),np.ones(12),np.full(11,1/11)):
            with self.assertRaises(ValueError): weighting.fit(x,y,x,y,norm,w,0,time.monotonic()+10,steps=1)

    def test_stable_losses_and_cluster_comparison_identity(self):
        rows=meta();z=np.array([100. if r['label']==0 else -100. for r in rows])
        d=weighting.diagnostics(rows,z)
        self.assertAlmostEqual(d['visitation']['bce'],100.)
        c=weighting.compare(rows,z,z)
        np.testing.assert_array_equal(c['treatmentMinusControl'],[0.,0.])
        np.testing.assert_array_equal(c['sourceClusterDescriptive95'],[[0.,0.],[0.,0.]])
        self.assertFalse(any(v['meanBiasPass'] for v in d['landmarks'].values()))

    def test_equal_loss_selection_prefers_earlier_step_then_init(self):
        candidates=[{'validationVisitationBce':.4,'step':1000,'init':0},
            {'validationVisitationBce':.4,'step':100,'init':1},
            {'validationVisitationBce':.4,'step':100,'init':0}]
        self.assertEqual(min(candidates[:2],key=weighting.selection_key),candidates[1])
        self.assertEqual(min(candidates,key=weighting.selection_key),candidates[2])
        candidates[0]['validationVisitationBce']=.39
        self.assertEqual(min(candidates,key=weighting.selection_key),candidates[0])

    def test_verdict_requires_both_proper_scores_and_every_bias(self):
        def arm(bce,brier,bias):
            return {'visitation':{'bce':bce,'brier':brier},'landmarks':{k:{'bias':{'mean':bias}} for k in weighting.LANDMARKS}}
        control=arm(.4,.1,-.05);treatment=arm(.39,.09,-.02)
        self.assertEqual(weighting.verdict(control,treatment),'VALIDATION_WEIGHTING_SIGNAL')
        for bad in (arm(.41,.09,-.02),arm(.39,.11,-.02),arm(.39,.09,-.06),copy.deepcopy(treatment)):
            if bad==treatment: bad['landmarks']['start']['bias']['mean']=-.05
            self.assertEqual(weighting.verdict(control,bad),'VALIDATION_WEIGHTING_NOT_SHOWN')

    def test_consumed_fit_root_fails_before_second_device_or_fit(self):
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory);review=out/'review.json';review.write_text('{}')
            frozen={'identity':{},'reviewSha256':weighting.sha(review),'custody':{},'arms':list(weighting.ARMS),
                'initializations':[0,1],'steps':2000,'every':100,'batch':512,'maxSeconds':600,'testAccessAuthorized':False}
            (out/'freeze.json').write_text(json.dumps(frozen))
            cache={k:{'x':torch.zeros(1,64)} for k in ('train','validation')}
            args=SimpleNamespace(out=out,review=review)
            with patch.object(weighting,'identity',return_value={}),patch.object(weighting,'inputs',return_value=(cache,{},{})),patch.object(torch.Tensor,'cuda',side_effect=RuntimeError('device stop')) as device:
                with self.assertRaisesRegex(RuntimeError,'device stop'): weighting.run(args)
                with self.assertRaises(FileExistsError): weighting.run(args)
                self.assertEqual(device.call_count,1)

    def test_cached_input_validation_does_not_open_archives(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'audit').mkdir()
            (root/'audit/train-validation-sources.jsonl').write_text('{}\n')
            (root/'result-reviewed.json').write_text(json.dumps({'verdict':'PASS','resultSha256':weighting.PARENT['result.json']}))
            expected={**weighting.PARENT,'import-audit.json':weighting.value.AUDIT,
                'import-reviewed.json':weighting.value.REVIEW,'train-validation-sources.jsonl':weighting.value.MANIFEST}
            def checksum(path):
                self.assertNotIn('.tar',str(path))
                return expected[Path(path).name]
            cache={'train':{'policySha256':'train'},'validation':{'policySha256':'validation'}}
            head={'encoderCheckpointSha256':weighting.value.CHECKPOINT,'valueHead':{'mean':torch.zeros(64),'scale':torch.ones(64)}}
            with patch.object(weighting,'sha',side_effect=checksum),patch.object(weighting.torch,'load',side_effect=[cache,head]),patch.object(weighting.value,'validate_cache') as validate,patch.object(weighting.value.audit,'archive_units',side_effect=AssertionError('archive parser called')):
                actual,norm,custody=weighting.inputs(SimpleNamespace(parent=root,import_root=root))
            self.assertIs(actual,cache);validate.assert_called_once_with(cache,[{}])
            self.assertEqual(custody['policySha256'],{'train':'train','validation':'validation'})
            self.assertTrue(torch.equal(norm['mean'],torch.zeros(64)))


if __name__=='__main__': unittest.main()
