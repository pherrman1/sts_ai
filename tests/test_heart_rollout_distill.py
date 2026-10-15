import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import heart_rollout_distill as h
from heart_record_encoder import encode_record,pack_tokens
import torch


def record():
    return {'obs.fixed_observation':[70,80,100,12,3,1,20,0,0,1],
            'obs.deck.cards':[1,2],'obs.deck.upgrades':[0,1],
            'obs.relics.relics':[1],'obs.relics.relic_counters':[3],
            'obs.potions':[2],'obs.map.xs':[0,0],'obs.map.ys':[0,1],
            'obs.map.roomTypes':[4,3],'obs.map.pathXs':[[0,-1,-1],[-1,-1,-1]],
            'obs.map.burningEliteX':0,'obs.map.burningEliteY':1,'obs.mapX':0,'obs.mapY':0,
            'cards_offered.cards':[3],'cards_offered.upgrades':[0],
            'relics_offered':[],'potions_offered':[], 'fixed_actions':[],
            'paths_offered':[0],'screen_state':5,'select_screen_type':0}


class DistillTest(unittest.TestCase):
    def test_public_record_ignores_metadata_and_keeps_keys_and_edges(self):
        r=record(); baseline=encode_record(r)
        r.update(seed=123,rng=[99],target=.99,endpoint={'hp':1},action=42)
        self.assertEqual(baseline,encode_record(r))
        r['obs.fixed_observation'][8]=1
        self.assertNotEqual(baseline[0],encode_record(r)[0])
        r=record();r['obs.map.pathXs'][0][0]=1
        self.assertNotEqual(baseline[1],encode_record(r)[1])
    def test_public_battle_and_memory_game_extensions(self):
        r=record();r['screen_state']=9;r['leaf.publicBattleEncounter']=4
        a=encode_record(r);r['leaf.publicBattleEncounter']=5
        self.assertNotEqual(a,encode_record(r))
        r['leaf.publicBattleEncounter']=64
        with self.assertRaises(ValueError):encode_record(r)
        del r['leaf.publicBattleEncounter']
        with self.assertRaises(KeyError):encode_record(r)
        r=record();r['screen_state']=1;r['leaf.matchAttempts']=5
        r['leaf.matchSlots']=[{'position':0,'state':-1,'card':-1,'upgrades':0},
                              {'position':1,'state':1,'card':2,'upgrades':0}]
        a=encode_record(r);r['leaf.matchSlots'][1]['card']=3
        self.assertNotEqual(a,encode_record(r))
        r['leaf.matchSlots'][0]['card']=1
        with self.assertRaises(ValueError):encode_record(r)
    def test_native_screen_enum_contract(self):
        import re
        header=(Path(__file__).resolve().parents[1]/'include/game/GameContext.h').read_text()
        body=re.search(r'enum class ScreenState\s*\{([^}]+)',header).group(1)
        values=[v.strip().split('=')[0] for v in body.split(',') if v.strip()]
        self.assertEqual((values.index('EVENT_SCREEN'),values.index('BATTLE')),(1,9))
    def test_bad_record_fails_closed(self):
        r=record();r['obs.deck.upgrades'].pop()
        with self.assertRaises(ValueError):encode_record(r)
        r=record();r['obs.deck.cards'][0]=999
        with self.assertRaises(ValueError):encode_record(r)
        r=record();r['obs.fixed_observation'][0]=float('nan')
        # Dense values are checked separately below.
        with self.assertRaises(ValueError):encode_record(r)
    def test_action_metric_aggregates_chance_outcomes(self):
        rows=[{'seed':1,'target':.9,'action':0},{'seed':1,'target':.1,'action':0},
              {'seed':1,'target':.6,'action':1}]
        m=h.metrics(rows,[[0,1,2]],[1.,1.,.7])['aggregate']
        self.assertAlmostEqual(m['regret'],.1)
        self.assertEqual(m['concordance'],0.)
    def test_token_models_are_padding_and_permutation_invariant(self):
        torch.set_num_threads(1);torch.manual_seed(0)
        f,t=encode_record(record()); rows=[{'tokens':t},{'tokens':list(reversed(t))}]
        k,e,a=[torch.from_numpy(v) for v in pack_tokens(rows)]
        x=torch.ones(2,5);b=torch.ones(2)*.5
        for variant in ('counts','pool','attention'):
            net=h.Net(5,variant).eval()
            with torch.no_grad():y=net(x,b,k,e,a)
            self.assertTrue(torch.allclose(y[0],y[1],atol=1e-6),variant)
            kp=torch.nn.functional.pad(k,(0,3));ep=torch.nn.functional.pad(e,(0,3));ap=torch.nn.functional.pad(a,(0,0,0,3))
            with torch.no_grad():z=net(x,b,kp,ep,ap)
            self.assertTrue(torch.allclose(y,z,atol=1e-6),variant)
    def test_fit_never_opens_test(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'freeze.json').write_text(json.dumps({'toolHashes':{}}))
            def split(root,freeze,name):
                self.assertIn(name,('train','validation'))
                return [],[],{'raw':1,'accepted':0,'groups':0,'sources':1}
            with patch.object(h,'load_split',side_effect=split) as call, patch.object(h,'verify_tools'),patch.object(h,'verify_bundle'),patch.object(h,'verify_corpus',return_value='sha'):
                h.fit(root,root/'out')
            self.assertEqual(call.call_count,2)
            self.assertFalse((root/'out/test-opened.json').exists())
    def test_incomplete_groups_and_bad_cost_are_rejected(self):
        def raw(ordinal,action,parent=0):
            return {'seed':1,'decision':0,'ordinal':ordinal,'parent':parent,'action':action,
                'parentScreen':5,'act':1,'floor':12,'value':.5,'extra':{'record':record(),'x2b':.5,
                'rolloutCpuSeconds':.064,'anchorCpuSeconds':.001,
                'recordSchema':'heart1-public-record-v2','recordPublicParityQualified':False,'repeats':[{'value':.6}]*64}}
        rows=[raw(0,0),raw(1,1),raw(2,0,1),raw(3,1,1)]
        rows[1]['extra']['repeats'].pop()
        accepted,groups,cov=h.validate_rows(rows,1)
        self.assertEqual((len(accepted),len(groups),cov['rejected']),(2,1,2))
        for value in (0.,-1.,float('nan')):
            r=raw(0,0);r['extra']['rolloutCpuSeconds']=value
            self.assertIsNone(h.validate_row(r,1))
        with self.assertRaises(ValueError):h.validate_row(raw(0,0),2)
        with self.assertRaises(ValueError):h.validate_rows([raw(0,0),raw(0,1)],1)
    def test_joint_capture_and_receipt_drift_is_detected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);capture=root/'seed-1.sib.jsonl';receipt=root/'seed-1.receipt.json'
            capture.write_text('original\n')
            receipt.write_text(json.dumps({'seed':1,'returncode':0,'captureSha256':h.sha(capture)}))
            manifest={'sources':{'1':{'receiptSha256':h.sha(receipt),'captureSha256':h.sha(capture)}}}
            (root/'corpus-manifest.json').write_text(json.dumps(manifest))
            freeze={'splits':{'test':[1]}}
            h.verify_corpus(root,freeze,'test')
            capture.write_text('changed\n')
            receipt.write_text(json.dumps({'seed':1,'returncode':0,'captureSha256':h.sha(capture)}))
            with self.assertRaises(ValueError):h.verify_corpus(root,freeze,'test')
    def test_candidate_gate_requires_complete_cost_and_quality_evidence(self):
        student={'concordance':.75,'regret':.8};baseline={'concordance':.7,'regret':1.}
        self.assertTrue(h.candidate_passes(student,baseline,[.01,.3],4.))
        for speed in (0.,3.99,float('nan')):
            self.assertFalse(h.candidate_passes(student,baseline,[.01,.3],speed))
        self.assertFalse(h.candidate_passes(student,baseline,[-.01,.3],4.))
        self.assertFalse(h.candidate_passes({'concordance':.71,'regret':.8},baseline,[.01,.3],4.))
    def test_models_support_training_gradients(self):
        torch.set_num_threads(1);f,t=encode_record(record())
        k,e,a=[torch.from_numpy(v) for v in pack_tokens([{'tokens':t},{'tokens':t}])]
        for variant in ('counts','pool','attention'):
            net=h.Net(5,variant)
            p=net(torch.tensor([[1.]*5,[2.]*5]),torch.tensor([.4,.6]),k,e,a)
            ((p-torch.tensor([.2,.8]))**2).mean().backward()
            self.assertTrue(torch.isfinite(net.layers[0].weight.grad).all())
    def test_opus_reference_transforms_match_frozen_trainer(self):
        import ast, math
        from heart1_leaf_reference import old_features,predict_reference
        repo=Path(__file__).resolve().parents[1]
        source=repo/'docs/experiments/evidence/ooc_sibling_leaf_capture_20261015/train_value.py'
        node=next(n for n in ast.parse(source.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='feats')
        ns={};exec(compile(ast.Module(body=[node],type_ignores=[]),str(source),'exec'),ns)
        r={'record':record(),'act':1,'floor':12,'x2b':.6}
        expected=ns['feats'](r['record'],r)
        dense,bags=old_features(r['record'],r)
        self.assertEqual(dense,expected[0]+[math.log(.6/.4)])
        self.assertEqual(bags,list(expected[1:]))
        checkpoint=repo/'docs/experiments/evidence/ooc_sibling_leaf_capture64_20261015/tv_within_x2b.json.pt'
        p=predict_reference(checkpoint,[r]);self.assertTrue(0<=p[0]<=1)
    def test_test_custody_preflight_precedes_latch(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);out=root/'out';out.mkdir()
            (root/'freeze.json').write_text(json.dumps({'splits':{'test':[1]}}))
            (root/'corpus-manifest.json').write_text(json.dumps({'sources':{'1':{'receiptSha256':'missing','captureSha256':'missing'}}}))
            (out/'selected.pt').write_bytes(b'x');(out/'vocabulary.json').write_text('[]')
            selection={'checkpointSha256':h.sha(out/'selected.pt'),'vocabularySha256':h.sha(out/'vocabulary.json'),
                'freezeSha256':h.sha(root/'freeze.json'),'toolSha256':h.sha(h.__file__),
                'corpusManifestSha256':h.sha(root/'corpus-manifest.json')}
            (out/'selection.json').write_text(json.dumps(selection))
            with patch.object(h,'verify_tools'),patch.object(h,'verify_bundle'):
                with self.assertRaises(FileNotFoundError):h.test(root,out)
            self.assertFalse((out/'test-opened.json').exists())
    def test_tensor_bound_applies_before_allocation(self):
        rows=[{"tokens":[1]*384}]
        self.assertGreater(h.check_tensor_bound((rows,),100),0)
        with self.assertRaises(RuntimeError):h.check_tensor_bound((rows,),300_000_000)
    def test_runtime_identity_roundtrip(self):
        freeze={'toolHashes':{},'runtime':h.runtime_identity()}
        json.dumps(freeze,allow_nan=False)
        h.verify_tools(freeze)
        freeze['runtime']['torch']='changed'
        with self.assertRaises(ValueError):h.verify_tools(freeze)
    def test_bad_identity_precedes_test_latch(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);out=root/'out';out.mkdir();(root/'freeze.json').write_text('{}')
            (out/'selected.pt').write_bytes(b'x');(out/'selection.json').write_text(json.dumps({'checkpointSha256':'wrong'}))
            with self.assertRaises(ValueError):h.test(root,out)
            self.assertFalse((out/'test-opened.json').exists())


if __name__=='__main__':unittest.main()
