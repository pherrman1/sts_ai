import copy
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import importlib.util
import contextlib
torch = __import__("torch") if importlib.util.find_spec("torch") else None
from tools import combat_transition_composed as c



class FakeModels:
    ready=True
    classes=c.CLASSES
    delta_values=np.asarray([0,3])
    domain=dict(preCurHpRange=[1,161],preMaxHpRange=[24,172],maxHpDeltaValues=[0,3])
    trained_groups=c.TRAINED_GROUPS
    encounter_names=c.native_rng.encounter_names()
    torch=torch or SimpleNamespace(inference_mode=contextlib.nullcontext)
    def __init__(self,pwin=1): self.calls=[]; self.pwin=pwin; self.z=object()
    def encode_visible(self,pi): self.calls.append('visible'); return pi
    def survival(self,inputs): self.calls.append('survival'); return self.pwin
    def max_hp(self,inputs): self.calls.append('max'); return np.asarray([0,1.])
    def hp_encoding(self,inputs): self.calls.append('hp_encoder'); return self.z
    def hp_distribution(self,z,delta,pre,maximum):
        self.calls.append(('hp',delta,maximum)); assert z is self.z
        p=np.zeros(304); p[2-c.CLASSES[0]]=1; return p
    def potion_distribution(self,inputs,pre,delta,fraction):
        self.calls.append(('potion',delta,fraction)); p=np.zeros(32); p[1]=1; return p
    def relic_distribution(self,z,signed_class,fraction,mask):
        assert z is self.z
        self.calls.append(('relic',signed_class,fraction,mask))
        return {g:np.eye(k)[0] for g,k in c.relic.HEAD_CLASSES.items() if g in self.trained_groups}


class ComposedTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Fixture is stored in existing tests; no external dataset dependency.
        from tools.test_combat_transition_surrogate import predictor
        cls.pi=predictor(card_id=c.base._CARD_IDS["BASH"])

    def state(self):
        pi=copy.deepcopy(self.pi)
        pi['globals'].update(curHp=40,maxHp=80,potionCount=1,potionCapacity=3)
        pi['potions'][0]['potionId']=c.base._POTION_IDS['FIRE_POTION']
        for p in pi['potions'][1:]: p['potionId']=1
        pi['relics']=[]
        pre={k:0 for k in c.base.PERSISTENT_KEYS}
        pre.update(curHp=40,maxHp=80,potionCount=1,potionCapacity=3,potions=[p['potionId'] for p in pi['potions']],
                   smokeBombUsed=False,stolenGold=0,relics=[],relicBits=[0]*3,deck=[],cardTypeCounts=[0]*4,bottleIdxs=[-1]*3,
                   combatRng=[dict(seed0=2,seed1=3,counter=0) for _ in range(6)])
        return pre,pi

    def test_death_no_downstream(self):
        pre,pi=self.state(); m=FakeModels(0)
        result=c.ComposedSampler(m).sample_transition(pre,pi,np.random.default_rng(1))
        self.assertEqual(result.outcome,'DEATH'); self.assertEqual(m.calls,['visible','survival'])

    def test_ancestral_conditioning_encoder_reuse_copythrough(self):
        pre,pi=self.state(); original=copy.deepcopy(pre); m=FakeModels()
        result=c.ComposedSampler(m).sample_transition(pre,pi,np.random.default_rng(1))
        post=result.post_state
        self.assertEqual(result.outcome,'VICTORY'); self.assertEqual((post['curHp'],post['maxHp']),(42,83))
        self.assertIn(('hp',1,83),m.calls)
        self.assertIn(('potion',1,42/83),m.calls)
        self.assertIn(('relic',162,42/83,1),m.calls)
        self.assertEqual(m.calls.count('hp_encoder'),1)
        self.assertEqual(post['potions'],[1]*5); self.assertEqual(post['potionCount'],0)
        self.assertEqual(pre,original)
        for k in (*c.base.COPY_THROUGH_KEYS,'smokeBombUsed'): self.assertEqual(post[k],pre[k])

    def test_gate_before_outcome_and_unloaded(self):
        pre,pi=self.state()
        for pwin in (0,1):
            m=FakeModels(pwin); m.ready=False
            result=c.ComposedSampler(m).sample_transition(pre,pi,np.random.default_rng(1))
            self.assertEqual(result.outcome,'FULL_SURROGATE_FALLBACK'); self.assertEqual(m.calls,[])

    def test_active_lizard_fail_closed_bloom_native(self):
        pre,pi=self.state(); rid=c.base._RELIC_IDS['LIZARD_TAIL']
        pre['relics']=[dict(id=rid,data=1)]; pi['relics']=[dict(relicId=rid,data=1,orderIndex=0)]
        m=FakeModels(); self.assertIn('active_unqualified_lizard',c.full_support_reasons(pre,pi,m))
        bloom=c.base._RELIC_IDS['MARK_OF_THE_BLOOM']
        pre['relics'].append(dict(id=bloom,data=0)); pi['relics'].append(dict(relicId=bloom,data=0,orderIndex=1))
        self.assertEqual(c.full_support_reasons(pre,pi,m),[])

    def test_invalid_hp_fails_without_clipping(self):
        pre,pi=self.state(); m=FakeModels()
        m.classes=c.CLASSES.copy(); m.classes[162]=1000
        self.assertEqual(c.ComposedSampler(m).sample_transition(pre,pi,np.random.default_rng(1)).outcome,'FULL_SURROGATE_FALLBACK')
        m.classes=c.CLASSES
        def illegal(*args):
            p=np.zeros(304); p[0]=1; return p
        m.hp_distribution=illegal
        with self.assertRaisesRegex(ValueError,'invalid sampled HP'):
            c.ComposedSampler(m).sample_transition(pre,pi,np.random.default_rng(1))

    def test_rng_exact_and_no_raw_six_stream_claim(self):
        pre,pi=self.state(); pi['globals']['encounter']=c.base._ENCOUNTER_IDS['GREMLIN_GANG']
        post=c.ComposedSampler(FakeModels()).sample_transition(pre,pi,np.random.default_rng(1)).post_state
        self.assertNotIn('combatRng',post)
        self.assertEqual(post['oocContinuationRng']['potionRng'],pre['combatRng'][4])
        self.assertEqual(post['oocContinuationRng']['miscRng'],c.native_rng.replay_misc(pre['combatRng'][2],'GREMLIN_GANG'))

    def test_hashes_all_enforced_before_load(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x'; p.write_bytes(b'frozen')
            good=c.base.sha256(p)
            for name in c.ARTIFACTS:
                with self.assertRaisesRegex(ValueError,name): c.verify_hashes({name:(p,'0'*64)})
            self.assertEqual(c.verify_hashes({'x':(p,good)}),{'x':good})
        if torch is None:
            return
        with patch.object(c,'verify_hashes',side_effect=ValueError('hash')),patch.object(torch,'load') as load:
            with self.assertRaises(ValueError): c.FrozenModels()
            load.assert_not_called()

    def test_mixture_probability_before_log(self):
        result=c.trajectory.mixture_nll(np.log(np.asarray([[.1],[.9]])))
        self.assertAlmostEqual(float(result[0]),-np.log(.5))

    def test_consumption_and_shared_residues(self):
        pre,pi=self.state()
        for name,data in [('HAPPY_FLOWER',2),('INCENSE_BURNER',4),('NUNCHAKU',9),('PEN_NIB',3)]:
            rid=c.base._RELIC_IDS[name]; pre['relics'].append(dict(id=rid,data=data)); pi['relics'].append(dict(relicId=rid,data=data,orderIndex=len(pi['relics'])))
        residues=dict(turns=5,attacks=7,cards=0,shuffles=0)
        post=c.assemble_victory(pre,pi,83,42,1,residues,c.native_rng.encounter_names())
        self.assertEqual([r['data'] for r in post['relics']],[1,3,6,0])
        post['potions'][0]=c.base._POTION_IDS['BLOCK_POTION']
        with self.assertRaises(ValueError): c.validate_victory(pre,pi,post,residues,c.native_rng.encounter_names())

    def test_actual_mixture_and_individual_gate(self):
        value=c.mixture_nll_from_probabilities([[.1],[.9]])
        self.assertAlmostEqual(value[0],-np.log(.5))
        loss=c.mixture_nll_from_probabilities([[0.],[0.]])
        self.assertTrue(np.isposinf(loss[0]))
        for bad in ('hp','potion','relic'):
            gaps=dict(hp=-1,potion=-1,relic=-1); gaps[bad]=.10001
            self.assertEqual(c.classify(gaps,{}),'COMPOSED_TRANSITION_REJECTED')
        self.assertEqual(c.classify(dict(hp=float('inf')),{}),'COMPOSED_TRANSITION_REJECTED')
        self.assertEqual(c.classify(dict(hp=.1,potion=.1,relic=.1),{}),'COMPOSED_TRANSITION_QUALIFIED')
        self.assertEqual(c.classify({},dict(invalid=1)),'COMPOSED_TRANSITION_REJECTED')
        self.assertEqual(c.classify({}, {}, provenance=False),'COMPOSED_TRANSITION_REJECTED')

    def test_exact_hp_marginal_keeps_rare_supported_class(self):
        weights=np.zeros((1,11)); weights[0,0]=.99; weights[0,2]=.01
        conditional=np.zeros((1,11)); conditional[0,2]=.2
        marginal=c.exact_hp_marginal(weights,conditional)
        self.assertAlmostEqual(marginal[0],.002)
        self.assertTrue(np.isfinite(-np.log(marginal[0])))
        self.assertTrue(np.isposinf(c.mixture_nll_from_probabilities(np.zeros((32,1)))[0]))
        # Unequal weights distinguish an exact marginal from a class mean.
        self.assertNotAlmostEqual(marginal[0],conditional.mean())

    def test_exact_hp_marginal_rejects_invalid_inputs(self):
        for weights,conditional in [([[1,0]],[[.2]]), ([[.5,.4]],[[.2,0]]),
                                     ([[-.1,1.1]],[[.2,0]]), ([[1,0]],[[float('nan'),0]]),
                                     ([[1,0]],[[1.2,0]])]:
            with self.assertRaises(ValueError): c.exact_hp_marginal(weights,conditional)

    @unittest.skipUnless(torch, 'optional torch dependency')
    def test_exact_hp_evaluates_all_classes_and_native_zeros_using_cached_z(self):
        from tools import combat_transition_composed_evaluate as e
        values=np.asarray([0,3,4,5,6,7,8,9,10,11,12])
        m=SimpleNamespace(delta_values=values,classes=c.CLASSES)
        z=np.ones((2,64),np.float32); weights=np.zeros((2,11)); weights[:,0]=.99; weights[:,2]=.01
        pre=np.asarray([80,40]); maximum=np.asarray([80,80]); target=np.asarray([164,162])
        calls=[]
        def hp_head(models,cached,delta,cur,maxhp):
            self.assertIs(models,m); np.testing.assert_array_equal(cached,z)
            calls.append(delta.copy())
            legal=c.hp.legal_support(c.CLASSES,cur,maxhp).astype(float)
            return legal/legal.sum(-1,keepdims=True)
        with patch.object(e,'hp_prob',side_effect=hp_head),patch.object(e,'draw_categories',side_effect=AssertionError('sampling forbidden')):
            marginal,conditional=e.exact_hp_target_probabilities(m,z,weights,pre,maximum,target)
        self.assertEqual(len(calls),11)
        np.testing.assert_array_equal(np.asarray(calls)[:,0],np.arange(11))
        self.assertEqual(conditional[0,0],0); self.assertEqual(conditional[0,1],0)
        self.assertGreater(conditional[0,2],0)
        self.assertAlmostEqual(marginal[0],.01*conditional[0,2])
        self.assertGreater(marginal[1],0)

    @unittest.skipUnless(torch, 'optional torch dependency')
    def test_batch_matches_direct_sampler_and_counts_death_calls(self):
        from tools import combat_transition_composed_evaluate as e
        pre,pi=self.state()
        class Encoder(torch.nn.Module):
            def __init__(self): super().__init__(); self.rows=0
            def forward(self,*inputs):
                self.rows+=len(inputs[0]); return torch.zeros((len(inputs[0]),64))
        def head(inputs,outputs,index):
            layer=torch.nn.Linear(inputs,outputs)
            with torch.no_grad():
                layer.weight.zero_(); layer.bias.fill_(-torch.inf); layer.bias[index]=0
            return layer
        class Potion(torch.nn.Module):
            def forward(self,z,*args):
                logits=torch.full((len(z),32),-torch.inf); logits[:,1]=0; return logits
        class Relic(torch.nn.Module):
            def forward(self,z,*args):
                result={}
                for g,k in c.relic.HEAD_CLASSES.items():
                    result[g]=torch.full((len(z),k),-torch.inf); result[g][:,0]=0
                return result
        def model(pwin):
            m=c.FrozenModels.__new__(c.FrozenModels); m.__dict__.update(vars(FakeModels()))
            m.ready=True; m.classes=c.CLASSES; m.domain=FakeModels.domain; m.delta_values=FakeModels.delta_values
            m.device='cpu'; m.torch=torch; m.trained_groups=c.TRAINED_GROUPS; m.encounter_names=c.native_rng.encounter_names()
            m.survival_net=SimpleNamespace(encoder=Encoder(),survival=torch.nn.Linear(64,1))
            with torch.no_grad(): m.survival_net.survival.weight.zero_(); m.survival_net.survival.bias.fill_(1000 if pwin else -1000)
            m.max_net=SimpleNamespace(encoder=Encoder(),max_hp_delta=head(64,2,1))
            m.hp_net=SimpleNamespace(encoder=Encoder(),delta_embedding=torch.nn.Embedding(2,8),hp=head(72,304,162))
            m.potion_encoder=SimpleNamespace(encoder=Encoder()); m.potion_net=Potion(); m.relic_net=Relic()
            return m
        for pwin in (0,1):
            direct=model(pwin); batch=model(pwin); arrays=c.visible_arrays(pi)
            reference=c.ComposedSampler(direct).sample_transition(pre,pi,np.random.default_rng(1))
            with torch.inference_mode():
                sample=e.complete_batch(batch,arrays,np.asarray([0]),np.asarray([40]),np.asarray([80]),np.asarray([pre['potions']]),np.asarray([3]),np.random.default_rng(1))
            if not pwin:
                self.assertEqual(reference.outcome,'DEATH'); self.assertFalse(sample['alive'][0])
                self.assertTrue(all(v==0 for k,v in sample['counts'].items() if k!='survivalRows'))
            else:
                self.assertTrue(sample['alive'][0])
                result=c.assemble_victory(pre,pi,int(sample['maximum'][0]),int(sample['ending'][0]),int(sample['mask'][0]),{g:int(v[0]) for g,v in sample['residues'].items()},batch.encounter_names)
                self.assertEqual(reference.post_state,result)
                self.assertEqual(batch.hp_net.encoder.rows,1)
            for m in (direct,batch):
                self.assertEqual(m.max_net.encoder.rows,pwin)
                self.assertEqual(m.hp_net.encoder.rows,pwin)
                self.assertEqual(m.potion_encoder.encoder.rows,pwin)

    @unittest.skipUnless(torch, 'optional torch dependency')
    def test_contract_failure_persists_rejection(self):
        from tools import combat_transition_composed_evaluate as e
        with tempfile.TemporaryDirectory() as d:
            with patch.object(e,'evaluate',side_effect=ValueError('invalid sampled maxHP state')):
                with self.assertRaises(ValueError): e.run_evaluation(Path(d),'reviewed')
            result=json.loads((Path(d)/'results.json').read_text())
            self.assertEqual(result['classification'],'COMPOSED_TRANSITION_REJECTED')
            self.assertEqual(result['hardValidity']['invalidMaxHpClassOrState'],1)

    @unittest.skipUnless(torch, 'optional torch dependency')
    def test_repeated_evaluation_preserves_prior_evidence(self):
        from tools import combat_transition_composed_evaluate as e
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'results.json'; original='{"preserved": true}\n'; path.write_text(original)
            with patch.object(e,'evaluate') as evaluate:
                with self.assertRaisesRegex(ValueError,'prior evidence preserved'): e.run_evaluation(Path(d),'reviewed')
                evaluate.assert_not_called()
            self.assertEqual(path.read_text(),original)

    @unittest.skipUnless(torch, 'optional torch dependency')
    def test_component_backend_restores_global_state(self):
        previous=torch.backends.mha.get_fastpath_enabled()
        for enabled in (False,True):
            with c.attention_backend(torch,enabled):
                self.assertEqual(torch.backends.mha.get_fastpath_enabled(),enabled)
            self.assertEqual(torch.backends.mha.get_fastpath_enabled(),previous)
        with self.assertRaises(ValueError):
            with c.attention_backend(torch,not previous): raise ValueError('failed forward')
        self.assertEqual(torch.backends.mha.get_fastpath_enabled(),previous)

    def test_bounded_rng_rejection_continuation(self):
        from tools.test_combat_transition_rng_audit import rejection_state
        pre,pi=self.state(); pre['combatRng'][2]=rejection_state()
        pi['globals']['encounter']=c.base._ENCOUNTER_IDS['GREMLIN_GANG']
        result=c.ComposedSampler(FakeModels()).sample_transition(pre,pi,np.random.default_rng(1)).post_state
        self.assertEqual(result['oocContinuationRng']['miscRng'],c.native_rng.replay_misc(pre['combatRng'][2],'GREMLIN_GANG'))
        self.assertEqual(result['oocContinuationRng']['miscRng']['counter'],4)


if __name__=='__main__': unittest.main()
