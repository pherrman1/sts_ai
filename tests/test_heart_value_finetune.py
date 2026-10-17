"""Arm C value fine-tune: ranking loss, policy guard, memmap store and split guards."""
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import torch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import heart_value_finetune as ft


class RankLoss(unittest.TestCase):
    def test_orders_by_target_and_weights_gaps(self):
        v = torch.tensor([2.,0.,-1.])
        good = ft.rank_loss(v,[.9,.5,.1],[[0,1,2]])
        bad = ft.rank_loss(-v,[.9,.5,.1],[[0,1,2]])
        self.assertLess(float(good),float(bad))
        # Ties and pairs across groups contribute nothing.
        self.assertEqual(float(ft.rank_loss(v,[.5,.5,.5],[[0,1,2]])),0.)
        self.assertEqual(float(ft.rank_loss(v,[.9,.1,.5],[[0],[1],[2]])),0.)

    def test_gradient_reaches_values(self):
        v = torch.zeros(2,requires_grad=True)
        ft.rank_loss(v,[.2,.8],[[0,1]]).backward()
        self.assertLess(float(v.grad[1]),0.); self.assertGreater(float(v.grad[0]),0.)


class PolicyKl(unittest.TestCase):
    def test_zero_when_equal_and_ignores_forced_rows(self):
        inf = float('-inf')
        old = torch.tensor([[1.,2.,inf],[0.,inf,inf]])
        self.assertAlmostEqual(float(ft.policy_kl(old.clone(),old)),0.,places=7)
        new = torch.tensor([[2.,1.,5.],[9.,3.,3.]])
        kl, rows = ft.policy_kl(new,old,reduce=False)
        self.assertEqual(rows,1); self.assertGreater(kl,0.)
        self.assertTrue(torch.isfinite(ft.policy_kl(new,old)))

    def test_no_multi_choice_rows(self):
        old = torch.tensor([[0.,float('-inf')]])
        self.assertEqual(ft.policy_kl(torch.zeros(1,2),old,reduce=False),(0.,0))


class StoreRoundTrip(unittest.TestCase):
    def test_nested_fixed_tensors(self):
        batch = {'a':{'value':torch.arange(6,dtype=torch.int32).reshape(3,2),'mask':torch.tensor([True,False,True])},
                 'b':torch.tensor([.5,1.5,2.5])}
        with tempfile.TemporaryDirectory() as d:
            head = {'a':{k:v[:2] for k,v in batch['a'].items()},'b':batch['b'][:2]}
            s = ft.Store(Path(d)/'s',5,batch); s.put(0,batch); s.put(3,head); s.close()
            r = ft.Store(Path(d)/'s')
            got = ft.unflat(r.arrays,np.array([0,2,4]),'cpu')
            self.assertTrue(torch.equal(got['a']['value'],torch.tensor([[0,1],[4,5],[2,3]],dtype=torch.int32)))
            self.assertTrue(torch.equal(got['a']['mask'],torch.tensor([True,True,False])))
            self.assertTrue(torch.allclose(got['b'],torch.tensor([.5,2.5,1.5])))


class Splits(unittest.TestCase):
    def test_sibling_groups_split_and_need_two_actions(self):
        rows = [{'seed':110164000,'group':[110164000,0,1],'action':a,'split':'train','cohort':'494'} for a in (0,1)]
        rows += [{'seed':110164041,'group':[110164041,0,1],'action':a,'split':'validation','cohort':'494'} for a in (0,0)]
        rows += [{'seed':110164042,'group':[110164042,3,1],'action':a,'split':'validation','cohort':'494'} for a in (0,2)]
        rows += [{'seed':111101000,'group':[111101000,3,1],'action':a,'split':'validation','cohort':'r2'} for a in (0,2)]
        self.assertEqual(ft.sibling_groups(rows,True),[[0,1]])
        self.assertEqual(ft.sibling_groups(rows,False),[[4,5],[6,7]])
        self.assertEqual(ft.sibling_groups(rows,False,'r2'),[[6,7]])

    def test_no_test_reader(self):
        self.assertEqual(ft.SIBLING_VALIDATION_END,110164048)
        self.assertNotIn('test',ft.value.SPLITS)
        with self.assertRaises(ValueError):
            next(ft.round2_units('/nonexistent','confirm'))


if __name__ == '__main__':
    unittest.main()
