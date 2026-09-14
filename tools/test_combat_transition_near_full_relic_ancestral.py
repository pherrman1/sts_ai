import unittest
import numpy as np
import torch
from tools import combat_transition_near_full_relic_ancestral as r
from tools import combat_transition_composed as c

class PosteriorLikelihood(unittest.TestCase):
    def test_compatible_residue_and_ambiguous_mask_are_marginalized_before_log(self):
        class Net(torch.nn.Module):
            def __init__(self):
                super().__init__();self.turns=torch.nn.Parameter(torch.tensor([[1.,0.,-1.,2.,-2.,.5],[-1.,2.,0.,.5,1.,-2.]]))
            def forward(self,z,signed,fraction,mask,escaped):
                return dict(turns=self.turns[mask],attacks=self.turns.new_zeros((len(mask),10)),cards=self.turns.new_zeros((len(mask),10)),shuffles=self.turns.new_zeros((len(mask),3)))
        net=Net();cache=dict(z=np.zeros((1,64),np.float32),trueHp=np.array([20]),preHp=np.array([20]),trueMax=np.array([40]),traces=np.array([0]),escaped=np.array([False]),observed=np.array([[True,False,False,False]]))
        for name,size in [('turns',6),('attacks',10),('cards',10),('shuffles',3)]:cache['compatible_'+name]=np.ones((1,size),bool)
        cache['compatible_turns'][:]=False;cache['compatible_turns'][0,[0,3]]=True
        posterior=np.zeros(256);posterior[0]=.3;posterior[1]=.7
        result=r.teacher(net,cache,{0:posterior},np.array([0]))
        probabilities=net.turns.softmax(-1);expected=-torch.log(.3*probabilities[0,[0,3]].sum()+.7*probabilities[1,[0,3]].sum())
        self.assertAlmostEqual(float(result.detach()[0]),float(expected.detach()),places=6)
        result.sum().backward();self.assertTrue(torch.isfinite(net.turns.grad).all());self.assertGreater(float(net.turns.grad.abs().sum()),0)
        self.assertFalse(torch.allclose(result[0],.3*(-probabilities[0,[0,3]].sum().log())+.7*(-probabilities[1,[0,3]].sum().log())))

if __name__=='__main__':unittest.main()
