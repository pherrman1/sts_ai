import unittest
import numpy as np
import importlib.util
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools import combat_transition_stochastic_hp as hp


class StochasticHpTests(unittest.TestCase):
    def test_domain_uses_predictors_and_upstream_classes(self):
        classes, provenance=hp.freeze_domain(np.array([60,1,999]),np.array([80,100,999]),[-2,0,8],np.array([True,True,False]))
        self.assertEqual((classes[0],classes[-1]),(-59,107))
        self.assertEqual(provenance['classes'],167)
        self.assertEqual(provenance,hp.freeze_domain(np.array([60,1]),np.array([80,100]),[-2,0,8],np.array([True,True]))[1])

    def test_structural_check_fails_without_expanding(self):
        c=np.arange(-2,3)
        np.testing.assert_array_equal(hp.check_targets(c,np.array([3,3,3]),np.array([5,5,5]),np.array([1,3,5])),[0,2,4])
        for post in (np.array([6]),np.array([0]),np.array([3.5])):
            with self.assertRaises(ValueError):
                hp.check_targets(c,np.array([3]),np.array([5]),post)
        np.testing.assert_array_equal(c,np.arange(-2,3))

    @unittest.skipUnless(importlib.util.find_spec("torch"), "optional torch dependency")
    def test_row_support_and_mask_before_softmax(self):
        import torch
        # Test the actual head with a small stub encoder to avoid unrelated token plumbing.
        c=np.arange(-4,5)
        model=hp.new_model(torch,np.zeros(16),np.ones(16),2,c,20260912)
        class Encoder(torch.nn.Module):
            def forward(self,*inputs):
                return torch.zeros(2,64)
        model.encoder=Encoder()
        logits=model((),torch.tensor([0,1]),torch.tensor([1,5]),torch.tensor([3,5]))
        legal=torch.tensor(hp.legal_support(c,np.array([1,5]),np.array([3,5])))
        self.assertTrue(torch.isneginf(logits[~legal]).all())
        probability=logits.softmax(-1)
        self.assertTrue((probability[~legal]==0).all())
        self.assertTrue(torch.isfinite(logits[legal]).all())
        with self.assertRaises(ValueError):
            model((),torch.tensor([0,1]),torch.tensor([1,5]),torch.tensor([0,0]))

    def test_crps_degenerate_equals_integer_absolute_error(self):
        c=np.arange(-2,3)
        prob=np.eye(5)[[0,2,4]]
        rows=hp.row_scores(prob,c,np.array([3,3,3]),np.array([5,5,5]),np.array([2,5,1]),np.zeros(3))
        np.testing.assert_allclose(rows['crps'],[1,2,4])
        np.testing.assert_allclose(rows['expectedMae'],[1,2,4])

    def test_crps_and_intervals_known_distribution(self):
        rows=hp.row_scores(np.array([[.25,.5,.25]]),np.array([-1,0,1]),np.array([2]),np.array([3]),np.array([2]),np.array([-np.log(.5)]))
        self.assertAlmostEqual(rows['crps'][0],.125)
        self.assertEqual(rows['width50'][0],1)
        self.assertEqual(rows['width80'][0],2)
        self.assertEqual(rows['coverage95'][0],1)

    def test_sampling_boundaries_healing_and_fraction(self):
        c=np.arange(-4,5)
        pre=np.array([1,5,3]); maximum=np.array([3,5,7])
        probability=hp.legal_support(c,pre,maximum).astype(float)
        probability/=probability.sum(1,keepdims=True)
        sampled,fraction=hp.sample_hp(probability,c,pre,maximum,np.random.default_rng(7),1000)
        self.assertTrue(np.all(sampled>=1)); self.assertTrue(np.all(sampled<=maximum[:,None]))
        self.assertTrue(np.any(sampled[2]>pre[2]))
        np.testing.assert_array_equal(fraction,sampled/maximum[:,None])
        probability[0,0]=.1
        with self.assertRaises(ValueError):
            hp.sample_hp(probability,c,pre,maximum,np.random.default_rng(7))

    def test_decision_boundaries(self):
        cases=[([-2,-1],[-1,1],'QUALIFIED'),([-2,-1],[0,1],'QUALIFIED'),
               ([-2,-1],[.1,1],'REJECTED'),([.1,1],[-2,-1],'REJECTED'),
               ([-1,1],[-1,1],'INCONCLUSIVE'),([-1,0],[-1,0],'INCONCLUSIVE')]
        for crps,mae,label in cases:
            self.assertEqual(hp.classify(crps,mae),'STOCHASTIC_DELTA_HP_'+label)


if __name__=='__main__':
    unittest.main()
