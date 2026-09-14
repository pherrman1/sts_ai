import copy
import unittest
import numpy as np
import torch
from tools import combat_transition_potion_trajectory as t


class TrajectoryTest(unittest.TestCase):
    def fixture(self,potions,post,escape=False):
        pre=dict(potions=potions,potionCapacity=3,relics=[],combatRng=[{}, {}, {}, {}, dict(seed0=11,seed1=12,counter=99),{}])
        return pre,dict(potions=post,smokeBombUsed=escape)

    def test_ordinary_target_is_original_joint_mask_probability(self):
        pre,post=self.fixture([23,16,1,1,1],[1,16,1,1,1])
        graph=t.target_graph(pre,post,[])
        lp=torch.full((1,32),-torch.inf);lp[0,[0,1,2,3]]=torch.tensor([.1,.2,.3,.4]).log()
        self.assertAlmostEqual(float(t.target_log_probability(lp,graph).exp()),.2,places=6)

    def test_all_native_consumption_orders_are_marginalized(self):
        pre,post=self.fixture([t.BREW,16,1,1,1],[23,16,23,1,1])
        graph=t.target_graph(pre,post,[23,16,23])
        logits=torch.zeros((len(graph.inventories),64),requires_grad=True)
        legal=torch.as_tensor(np.stack([t.legal_actions(i,3) for i in graph.inventories]))
        lp=torch.log_softmax(logits.masked_fill(~legal,-torch.inf),-1)
        loss=-t.target_log_probability(lp,graph,False);loss.backward()
        self.assertTrue(torch.isfinite(loss));self.assertTrue(torch.isfinite(logits.grad).all())
        terminal_owner=graph.target_edges[0][0]
        self.assertGreater(sum(child==terminal_owner for _,_,child in graph.edges),1)

    def test_recursive_body_and_escape(self):
        pre,post=self.fixture([t.BREW,1,1,1,1],[1,23,1,1,1],True)
        graph=t.target_graph(pre,post,[t.BREW,23,t.SMOKE,23,t.SMOKE,23])
        self.assertEqual(graph.rounds,2)
        self.assertTrue(all(b>a for a,_,b in graph.edges))
        with self.assertRaises(ValueError):t.target_graph(pre,post,[t.BREW,23,t.SMOKE,23,t.SMOKE,23],True)

    def test_effect_posterior_preserves_compatible_paths_and_native_mass(self):
        forge=t.EFFECT_IDS[2]
        pre,post=self.fixture([t.BREW,forge,1,1,1],[forge,forge,forge,1,1])
        graph=t.target_graph(pre,post,[forge,forge,forge])
        legal=torch.as_tensor(np.stack([t.legal_actions(i,3) for i in graph.inventories]))
        lp=torch.log_softmax(torch.zeros((len(graph.inventories),64)).masked_fill(~legal,-torch.inf),-1)
        posterior,total=t.trace_posterior(lp,graph)
        self.assertAlmostEqual(total,float(t.target_log_probability(lp,graph,False).exp()),places=7)
        self.assertAlmostEqual(posterior.sum(),1.,places=12)
        # The original Brew is always cleared; compatible paths differ on
        # whether the original Forge was used before generated Forge refilled it.
        active=np.flatnonzero(posterior)
        self.assertTrue(np.all((active&1)==1))
        self.assertTrue(np.any(((active>>5)&4)==4))
        self.assertTrue(np.any(((active>>5)&4)==0))
        self.assertGreater(len(active),1)

    def test_native_boss_smoke_discard_is_not_escape(self):
        # Frozen RAW row64773, Slime Boss: Smoke removed, no escape/RNG draw.
        pre,post=self.fixture([t.SMOKE,1,1,1,1],[1]*5)
        graph=t.target_graph(pre,post,[],True)
        self.assertIn((0,1,1),graph.edges)
        self.assertTrue(t.legal_actions(pre['potions'],3,True)[1])
        self.assertFalse(t.legal_actions(pre['potions'],3,True)[33])
        self.assertEqual(graph.generation_log_prior,0.)

    def test_batched_exact_marginal_matches_independent_scalar_dag(self):
        first,last=self.fixture([t.BREW,16,1,1,1],[23,16,23,1,1])
        second,end=self.fixture([23,t.SMOKE,1,1,1],[1,1,1,1,1],True)
        graphs=[t.target_graph(first,last,[23,16,23]),t.target_graph(second,end,[])]
        net=t.new_decoder(11);z=np.zeros((2,64),np.float32)
        batch=t.batch_target_log_probabilities(net,graphs,z,np.asarray([3,3]),np.asarray([0,0]),np.asarray([.5,.5]),np.asarray([False,False]),False)
        scalar=[]
        for graph in graphs:
            n=len(graph.inventories)
            lp=t.log_probabilities(net,np.zeros((n,64),np.float32),graph.inventories,np.full(n,3),np.zeros(n,np.int64),np.full(n,.5),np.zeros(n,bool))
            scalar.append(t.target_log_probability(lp,graph,False))
        torch.testing.assert_close(batch,torch.stack(scalar),rtol=1e-6,atol=1e-6)
        (-batch.mean()).backward()
        self.assertTrue(all(torch.isfinite(p.grad).all() for p in net.parameters()))

    def test_hypothetical_origin_ignores_hidden_rng_and_survives_generation(self):
        class AlwaysBrew(torch.nn.Module):
            def __init__(self):super().__init__();self.anchor=torch.nn.Parameter(torch.tensor(0.))
            def output_logits(self,z,inventory,delta,hp):
                logits=torch.full((len(inventory),64),-torch.inf)
                for i,slots in enumerate(inventory):
                    brew_slots=torch.nonzero(slots==t.BREW)
                    logits[i,32+(1<<int(brew_slots[0])) if len(brew_slots) else 0]=0
                return logits
        pre,_=self.fixture([t.BREW,1,1,1,1],[1]*5);other=copy.deepcopy(pre);other['combatRng'][4]=dict(seed0=222,seed1=333,counter=17)
        first=t.sample(AlwaysBrew(),np.zeros(64,np.float32),pre,0,.5,np.random.default_rng(8))
        second=t.sample(AlwaysBrew(),np.zeros(64,np.float32),other,0,.5,np.random.default_rng(8))
        self.assertEqual(first,second)
        state=dict(first['hypotheticalOrigin']);body=[]
        for _ in range(first['brewUses']):
            generated,state=t.brew.generate(state,3);body.extend(generated)
        self.assertEqual(first['generated'],body);self.assertEqual(first['potionRng'],state)
        self.assertNotEqual(first['potionRng'],pre['combatRng'][4])


if __name__=='__main__':unittest.main()
