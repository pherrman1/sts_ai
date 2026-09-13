import unittest
import numpy as np
from tools import combat_transition_hp_targets as hp


class HpTargetsTest(unittest.TestCase):
    def test_signed_healing_and_reconstruction(self):
        pre=np.array([40,40,40])
        post=np.array([20,40,50])
        maximum=np.array([80,80,90])
        values=hp.targets(pre,post,maximum)
        np.testing.assert_array_equal(values['delta'],[-20,0,10])
        for arm,value in values.items():
            np.testing.assert_allclose(hp.reconstruct(arm,value,0,1,pre,maximum),post)

    def test_normalization_train_only(self):
        value=np.array([1.,3.,10000.])
        self.assertEqual(hp.normalization(value,np.array([0,1])),dict(mean=2.,std=1.))

    def test_illegal_raw_clamp_round(self):
        metrics=hp.metrics(np.array([0.,12.,4.5]),np.array([1.,10.,5.]),np.array([10.,10.,10.]))
        self.assertAlmostEqual(metrics['mae'],3.5/3)
        self.assertAlmostEqual(metrics['clampedMae'],.5/3)
        self.assertEqual(metrics['roundedClampedMae'],0)
        self.assertAlmostEqual(metrics['belowOnePercent'],100/3)
        self.assertAlmostEqual(metrics['aboveMaxPercent'],100/3)

    def test_source_bootstrap_row_weighting(self):
        result=hp.bootstrap(np.array([1,1,2]),np.array([-1.,-1.,-4.]),1000,7)
        self.assertEqual(result['estimate'],-2)
        self.assertEqual(result['sources'],2)
        np.testing.assert_allclose(result['ci95'],[-4,-1])
        self.assertEqual(hp.classify(result['ci95'],[-1,-2,-3]),'ABSOLUTE_HP_DELTA_WINS')
        self.assertEqual(hp.classify([1,2],[1,2,3]),'HP_FRACTION_WINS')
        self.assertEqual(hp.classify([-1,1],[-1,-2,-3]),'HP_TARGET_INCONCLUSIVE')
        self.assertEqual(hp.classify([-2,-1],[-1,1,-1]),'HP_TARGET_INCONCLUSIVE')

    def test_paired_initialization_and_batch_order(self):
        import torch
        from tools import combat_transition_surrogate as base
        mean=np.zeros(len(base.CONTINUOUS_GLOBAL_FIELDS),np.float32)
        std=np.ones_like(mean)
        a=hp.new_model(torch,mean,std,3,20260912)
        b=hp.new_model(torch,mean,std,3,20260912)
        self.assertEqual(hp.state_hash(a),hp.state_hash(b))
        self.assertFalse(any('survival' in name or 'max_hp_delta' in name for name,_ in a.named_parameters()))
        orders=[list(base._batches(np.arange(17),4,np.random.default_rng(20260912))) for _ in range(2)]
        for left,right in zip(*orders):
            np.testing.assert_array_equal(left,right)
        a.train(); b.train()
        inputs=[torch.zeros((2,len(mean))),torch.zeros((2,4),dtype=torch.long),
                torch.zeros((2,1,4)),torch.zeros((2,1,3)),torch.zeros((2,5,2)),
                torch.ones((2,1),dtype=torch.bool),torch.ones((2,1),dtype=torch.bool)]
        torch.manual_seed(1); first=a(inputs,torch.tensor([0,2]))
        torch.manual_seed(1); second=b(inputs,torch.tensor([0,2]))
        torch.testing.assert_close(first,second,rtol=0,atol=0)


if __name__ == '__main__':
    unittest.main()
