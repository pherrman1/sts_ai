"""§501 arm isolation, §500 reproduction, public block and verdict checks."""
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import torch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import heart_outcome_dev_compare as dev
import heart_outcome_weighting as weighting


def record(hp=40,max_hp=80,boss=3,screen=2,potions=(1,5,1)):
    return {'obs.fixed_observation':[hp,max_hp,99,8,boss,0,20,1,0,0],'screen_state':screen,
            'obs.potions':list(potions),'obs.deck.cards':[1,2,3],'obs.deck.upgrades':[0,1,0],'obs.relics.relics':[7]}


def meta():
    return [{'seed':s,'index':i,'label':s%2,'act':a,'floor':f} for s in range(4) for i,(a,f) in enumerate(((1,0),(1,8),(2,20)))]


class DevCompareTest(unittest.TestCase):
    def test_public_block_values_and_vocabulary(self):
        row=dev.public_block(record(),2)
        self.assertEqual(len(row),len(dev.PUBLIC_NAMES))
        named=dict(zip(dev.PUBLIC_NAMES,row))
        self.assertAlmostEqual(named['hpFraction'],.5);self.assertEqual(named['boss3'],1.);self.assertEqual(named['act2'],1.)
        self.assertEqual(named['screen2'],1.);self.assertAlmostEqual(named['potionsHeld/3'],1/3)
        self.assertAlmostEqual(named['upgraded/10'],.1);self.assertEqual(named['keyRuby'],1.)
        for bad in ((record(),5),(record(boss=10),1),(record(screen=10),1)):
            with self.assertRaises(ValueError): dev.public_block(*bad)

    def test_weights_change_only_the_intended_mass(self):
        rows=meta()
        np.testing.assert_allclose(dev.train_weights(rows,'equal'),np.full(12,1/12))
        early=dev.train_weights(rows,'early')
        self.assertAlmostEqual(early.sum(),1.);self.assertAlmostEqual(early[0]/early[2],2.)
        sub=dev.train_weights(rows,'equal',{1,2})
        self.assertTrue(np.all(sub[[r['seed'] not in (1,2) for r in rows]]==0));self.assertAlmostEqual(sub.sum(),1.)
        with self.assertRaises(ValueError): dev.train_weights(rows,'source')
        with self.assertRaises(ValueError): dev.train_weights(rows,'equal',{99})

    def test_learning_curve_subsets_are_nested_and_fixed(self):
        seeds=list(range(110180000,110181080))
        for draw in dev.CURVE_DRAWS:
            a,b,c=(dev.curve_subset(seeds,n,draw) for n in dev.CURVE_SOURCES)
            self.assertTrue(a<b<c);self.assertEqual([len(a),len(b),len(c)],[135,270,540])
            self.assertEqual(c,dev.curve_subset(seeds,540,draw))
        self.assertNotEqual(dev.curve_subset(seeds,135,0),dev.curve_subset(seeds,135,1))

    def test_equal_arm_reproduces_section_500_head_and_fit(self):
        torch.set_num_threads(1);torch.use_deterministic_algorithms(True)
        norm={'mean':torch.arange(64,dtype=torch.float32)/100,'scale':torch.full((64,),2.)}
        for init in (0,1):
            self.assertEqual(weighting.tensor_sha(dev.make_head(norm['mean'],norm['scale'],init,'cpu').state_dict()),
                             weighting.tensor_sha(weighting.make_head(norm,init,'cpu').state_dict()))
        x=torch.arange(12*64,dtype=torch.float32).reshape(12,64)/1000
        y=torch.tensor([r['label'] for r in meta()],dtype=torch.float32)
        w=dev.train_weights(meta(),'equal')
        np.testing.assert_array_equal(w,weighting.sampling_weights(meta(),'visitation'))
        ours,_,_=dev.fit(x,y,x,y,norm['mean'],norm['scale'],w,1,time.monotonic()+30,steps=10,every=5)
        theirs,_,_=weighting.fit(x,y,x,y,norm,w,1,time.monotonic()+30,steps=10,every=5)
        self.assertEqual(ours['step'],theirs['step'])
        self.assertEqual(weighting.tensor_sha(ours['state']),weighting.tensor_sha(theirs['state']))

    def test_variable_width_fit_is_deterministic(self):
        torch.set_num_threads(1);torch.use_deterministic_algorithms(True)
        x=torch.randn(12,101,generator=torch.Generator().manual_seed(3))
        y=torch.tensor([r['label'] for r in meta()],dtype=torch.float32)
        w=dev.train_weights(meta(),'early')
        runs=[dev.fit(x,y,x,y,x.mean(0),x.std(0),w,0,time.monotonic()+30,steps=10,every=5) for _ in range(2)]
        self.assertEqual(weighting.tensor_sha(runs[0][0]['state']),weighting.tensor_sha(runs[1][0]['state']))
        self.assertEqual(runs[0][2],runs[1][2])
        with self.assertRaises(ValueError): dev.fit(x,y,x,y,x.mean(0),x.std(0),w*2,0,time.monotonic()+30,steps=1)

    def test_public_rows_must_match_cache_order(self):
        cache={s:{'meta':[{'seed':1,'index':0,'label':0,'act':1},{'seed':1,'index':1,'label':0,'act':1}]} for s in ('train','validation')}
        rows=[{'record':record(),'seed':1,'index':i,'label':0,'act':1} for i in (0,1)]
        with patch.object(dev.value,'read_sources',side_effect=lambda a,m,s:iter(rows)):
            out=dev.public_features(SimpleNamespace(),[],cache)
        self.assertEqual(tuple(out['train'].shape),(2,len(dev.PUBLIC_NAMES)))
        with patch.object(dev.value,'read_sources',side_effect=lambda a,m,s:iter(rows[::-1])):
            with self.assertRaises(ValueError): dev.public_features(SimpleNamespace(),[],cache)
        with patch.object(dev.value,'read_sources',side_effect=lambda a,m,s:iter(rows[:1])):
            with self.assertRaises(ValueError): dev.public_features(SimpleNamespace(),[],cache)

    def test_verdict_rules(self):
        c={'treatmentMinusControl':[-.004,0.],'sourceClusterDescriptive95':[[-.008,-.001],[-.001,0.]]}
        self.assertEqual(dev.representation_verdict(c),'REPRESENTATION_LOSS_SIGNAL')
        c['sourceClusterDescriptive95'][1][0]=.0001
        self.assertEqual(dev.representation_verdict(c),'REPRESENTATION_LOSS_NOT_SHOWN')
        c={'treatmentMinusControl':[-.002,0.],'sourceClusterDescriptive95':[[-.008,-.001],[-.001,0.]]}
        self.assertEqual(dev.representation_verdict(c),'REPRESENTATION_LOSS_NOT_SHOWN')
        def arm(bce,bias): return {'visitation':{'bce':bce},'landmarks':{k:{'bias':{'mean':bias}} for k in weighting.LANDMARKS}}
        self.assertEqual(dev.early_verdict(arm(.45,-.04),arm(.4515,-.01)),'EARLY_WEIGHTING_SIGNAL')
        self.assertEqual(dev.early_verdict(arm(.45,-.04),arm(.4525,-.01)),'EARLY_WEIGHTING_NOT_SHOWN')
        self.assertEqual(dev.early_verdict(arm(.45,-.04),arm(.44,-.04)),'EARLY_WEIGHTING_NOT_SHOWN')
        curve=[{'sources':540,'validationVisitationBce':v} for v in (.456,.457)]
        self.assertEqual(dev.curve_verdict(curve,.454),'MORE_SOURCES_SIGNAL')
        self.assertEqual(dev.curve_verdict(curve,.455),'MORE_SOURCES_NOT_SHOWN')


if __name__=='__main__': unittest.main()
