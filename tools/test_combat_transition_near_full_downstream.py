import math
import unittest
import numpy as np
import torch
from tools import combat_transition_near_full_downstream as d
from tools import combat_transition_sparse_evaluate as sparse,combat_transition_relic_trajectory as relic
from tools import combat_transition_gold as g,combat_transition_potion_trajectory as t


class DownstreamTest(unittest.TestCase):
    def test_sparse_warm_start_and_new_condition_gradients(self):
        old=sparse.net().eval();new=d.event_net(old.state_dict()).eval()
        z=torch.randn(3,64);hp=torch.randn(3,3);bits=torch.zeros(3,5);features=torch.randn(3,5);candidate=torch.randn(3,4,1,3);legal=torch.ones(3,4,dtype=torch.bool)
        a=old(z,hp,bits,features,candidate,legal);b=new(z,hp,bits,torch.cat((features,torch.zeros(3,3)),-1),candidate,legal)
        torch.testing.assert_close(a,b,rtol=1e-6,atol=1e-7)
        (-b[:,0].mean()).backward();self.assertTrue(all(torch.isfinite(p.grad).all() for p in new.parameters()))

    def test_relic_escape_warm_start(self):
        old=relic.new_decoder(torch,304,20260912).eval();new=d.relic_net(old).eval()
        z=torch.randn(3,64);delta=torch.tensor([0,160,303]);fraction=torch.tensor([.1,.5,1.]);mask=torch.tensor([0,1,31])
        a=old(z,delta,fraction,mask);b=new(z,delta,fraction,mask,torch.zeros(3))
        for name in a:torch.testing.assert_close(a[name],b[name],atol=1e-7,rtol=1e-6)
        (-torch.log_softmax(b['turns'],-1)[:,0].mean()).backward();self.assertTrue(torch.isfinite(new.shared[0].weight.grad).all())

    def test_native_incompatible_path_keeps_its_zero_mass(self):
        # Given the retained potion target, only 30% of compatible paths have
        # consumed generated Forge. A +5 unupgraded Dagger target cannot use
        # the other 70%; conditioning must not renormalize that mass away.
        nets=torch.nn.ModuleDict(dict(relic=d.relic_net(relic.new_decoder(torch,304,20260912)),gold=g.new_decoder(torch),writhing=d.event_net(sparse.net().state_dict()),ritual=d.event_net(sparse.net().state_dict())))
        card=dict(id=g.b._CARD_IDS['RITUAL_DAGGER'],upgraded=False,misc=10)
        pre=dict(gold=100,deck=[card],potions=[t.BREW,1,1,1,1],relics=[])
        pi=dict(cards=[dict(cardId=card['id'],upgraded=False,misc=10)],globals=dict(encounter=g.b._ENCOUNTER_IDS['REPTOMANCER'],ascension=0))
        mechanical=g.mechanics(pi,pre,1,(t.EFFECT_IDS[2],))[1].tolist();features=[0,0,1,0,0,0,1,0]
        option=dict(trace=129,weight=.3,mechanical=mechanical,features=features,posts=[(100,0)],goldTarget=0,daggerPosts=[(0,),(3,),(5,)],daggerTarget=2,daggerCandidates=[[[.1,0,0]],[[.1,0,.15]],[[.1,0,.25]]])
        record=dict(pre=pre,traces=[option],writhingTarget=0)
        cache=dict(z=np.zeros((1,64),np.float32),preHp=np.asarray([50]),preMax=np.asarray([80]),trueHp=np.asarray([50]),trueMax=np.asarray([80]),escaped=np.asarray([False]),writhing=np.asarray([False]),dagger=np.asarray([True]),observed=np.zeros((1,4),bool))
        for name,k in [('turns',6),('attacks',10),('cards',10),('shuffles',3)]:cache['compatible_'+name]=np.ones((1,k),bool)
        value=d.losses(nets,cache,{}, {0:record},np.asarray([0]))[0]
        lp=nets['ritual'](torch.zeros(1,64),torch.tensor([[0.,.625,0.]]),torch.tensor([[1.,0.,0.,0.,0.]]),torch.tensor([features],dtype=torch.float32),torch.tensor([option['daggerCandidates']]),torch.ones(1,3,dtype=torch.bool))[0,2]
        torch.testing.assert_close(value,(-lp-math.log(.3))/2,atol=1e-6,rtol=1e-6)
        value.backward();self.assertTrue(torch.isfinite(nets['ritual'].context[0].weight.grad).all())


if __name__=='__main__':unittest.main()
