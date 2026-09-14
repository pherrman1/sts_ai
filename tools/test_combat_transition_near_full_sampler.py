import copy
import unittest
import numpy as np
import torch
from tools import combat_transition_near_full_sampler as s,combat_transition_potion_trajectory as t


class SamplerTest(unittest.TestCase):
    def pre(self):
        return dict(curHp=50,maxHp=80,gold=100,potionCount=1,potionCapacity=3,potions=[t.BREW,1,1,1,1],smokeBombUsed=True,stolenGold=13,relics=[],relicBits=[0,0,0],deck=[dict(id=s.c.base._CARD_IDS['RITUAL_DAGGER'],misc=10,upgraded=False)],cardTypeCounts=[1,0,0,0],bottleIdxs=[-1,-1,-1],upgradeableCount=1,transformableCount=1,combatRng=[dict(counter=10+i,seed0=11+i,seed1=12+i) for i in range(6)])

    def test_batched_native_trajectory_matches_scalar_one_row(self):
        class AlwaysBrew(torch.nn.Module):
            def __init__(self):super().__init__();self.anchor=torch.nn.Parameter(torch.tensor(0.))
            def output_logits(self,z,inventory,delta,hp):
                logits=torch.full((len(inventory),64),-torch.inf)
                for i,slots in enumerate(inventory):
                    found=torch.nonzero(slots==t.BREW)
                    logits[i,32+(1<<int(found[0])) if len(found) else 0]=0
                return logits
        pre=self.pre();net=AlwaysBrew();a=t.sample(net,np.zeros(64,np.float32),pre,0,.5,np.random.default_rng(8))
        b=s.sample_potions_batch(net,np.zeros((1,64),np.float32),[pre],np.asarray([0]),np.asarray([.5]),np.random.default_rng(8),np.asarray([False]))[0]
        self.assertEqual(a,b)

    def test_raw_assembly_keeps_advanced_hypothetical_rng_and_native_deck(self):
        pre=self.pre();before=copy.deepcopy(pre);origin=t.brew.native_origin(77);body,state=t.brew.generate(origin,3)
        trace=dict(outcome='VICTORY',potions=list(body)+[1,1],potionCount=3,potionRng=state)
        pi=dict(globals=dict(encounter=s.c.base.WRITHING_MASS_ID))
        post=s.assemble(pre,pi,50,86,trace,dict(turns=1,attacks=0,cards=0,shuffles=0),1,(3,),(100,0))
        self.assertEqual(pre,before);self.assertEqual(post['combatRng'][4],state);self.assertNotEqual(post['combatRng'][4],pre['combatRng'][4])
        for i in (0,1,3,5):self.assertEqual(post['combatRng'][i],pre['combatRng'][i])
        self.assertEqual(post['deck'][0]['misc'],13);self.assertEqual(post['deck'][-1]['id'],s.c.base._CARD_IDS['PARASITE'])
        self.assertEqual(post['cardTypeCounts'],[1,0,0,1]);self.assertEqual(post['transformableCount'],2);self.assertEqual(post['bottleIdxs'],pre['bottleIdxs'])
        self.assertFalse(post['smokeBombUsed']);self.assertEqual(post['stolenGold'],0)


if __name__=='__main__':unittest.main()
