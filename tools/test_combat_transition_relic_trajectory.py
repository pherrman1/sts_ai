import unittest
import numpy as np
import importlib.util
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
if importlib.util.find_spec("torch"):
    import torch
from tools import combat_transition_relic_legality as r
from tools import combat_transition_relic_trajectory as t

class RelicTrajectoryTest(unittest.TestCase):
    def entry(self,name,data): return dict(id=r.base._RELIC_IDS[name],data=data)
    def test_partial_turn_intersection_and_reconstruction(self):
        pre=[self.entry('HAPPY_FLOWER',2),self.entry('INCENSE_BURNER',4),self.entry('INSERTER',1)]
        post=r.reconstruct(pre,dict(turns=5),0)
        self.assertEqual([x['data'] for x in post],[1,3,0])
        self.assertEqual(r.trajectory_constraints(pre[:1],post[:1],0)['turns'],{2,5})
        self.assertEqual(r.trajectory_constraints(pre,post,0)['turns'],{5})
    def test_attack_coherence_all_residues(self):
        for a in range(10):
            for p in range(10):
                for c in range(10):
                    pre=[self.entry('NUNCHAKU',a),self.entry('PEN_NIB',p)]
                    post=r.reconstruct(pre,dict(attacks=c),0)
                    self.assertEqual(r.trajectory_constraints(pre,post,0)['attacks'],{c})
    def test_contradiction_rejected(self):
        pre=[self.entry('NUNCHAKU',0),self.entry('PEN_NIB',0)]
        with self.assertRaisesRegex(ValueError,'contradictory'):
            r.trajectory_constraints(pre,[self.entry('NUNCHAKU',1),self.entry('PEN_NIB',2)],0)
    def test_native_deterministic_and_lizard(self):
        pre=[self.entry('NEOWS_LAMENT',2),self.entry('OMAMORI',2),self.entry('BURNING_BLOOD',17),self.entry('LIZARD_TAIL',1)]
        post=r.reconstruct(pre,dict(lizard=1),0)
        self.assertEqual([x['data'] for x in post],[1,2,17,0])
        self.assertEqual(r.trajectory_constraints(pre,post,0),dict(lizard={1}))
        self.assertEqual(r.reconstruct(pre,dict(lizard=1),0,True)[-1]['data'],1)
    def test_unknown_mutation_rejected(self):
        with self.assertRaisesRegex(ValueError,'unsupported mutable'):
            r.trajectory_constraints([self.entry('VAJRA',0)],[self.entry('VAJRA',1)],0)
    @unittest.skipUnless(importlib.util.find_spec("torch"), "optional torch")
    def test_stable_partial_likelihood(self):
        x=torch.tensor([[1000.,1001.,-1000.]],requires_grad=True)
        c=torch.tensor([[True,True,False]])
        loss=t.constraint_nll(torch,x,c)
        self.assertAlmostEqual(loss.item(),0.,places=5)
        loss.sum().backward(); self.assertTrue(torch.isfinite(x.grad).all())
        uniform=t.constraint_nll(torch,torch.zeros((1,6)),torch.tensor([[False,True,False,False,True,False]]))
        self.assertAlmostEqual(uniform.item(),np.log(3),places=6)
    @unittest.skipUnless(importlib.util.find_spec("torch"), "optional torch")
    def test_row_weighting_and_encoder_detach(self):
        logits={g:torch.zeros((2,k),requires_grad=True) for g,k in r.HEAD_CLASSES.items()}
        c={g:torch.zeros((2,k),dtype=torch.bool) for g,k in r.HEAD_CLASSES.items()}
        for v in c.values(): v[:,0]=True
        obs=torch.tensor([[1,0,0,0,0],[1,1,0,0,0]],dtype=torch.bool)
        loss=t.partial_loss(torch,logits,c,obs)
        self.assertAlmostEqual(loss.item(),(np.log(6)+(np.log(6)+np.log(10))/2)/2,places=6)
        model=t.new_decoder(torch,304,7); z=torch.randn(2,64,requires_grad=True)
        sum(v.sum() for v in model(z,torch.zeros(2,dtype=torch.long),torch.ones(2),torch.zeros(2,dtype=torch.long)).values()).backward()
        self.assertIsNone(z.grad)
    def test_mixture_before_log(self):
        actual=t.mixture_nll(np.log(np.array([[.1],[.9]])))
        self.assertAlmostEqual(actual[0],-np.log(.5))
    def test_death_and_unsupported_hp_never_call_decoder(self):
        args=(None,None,{}, {},None,0,1,1,0,np.arange(3),set())
        self.assertIsNone(t.sample_supported_relics(*args,False,True,None))
        self.assertIsNone(t.sample_supported_relics(*args,True,False,None))
    def test_classification_fixed_boundaries(self):
        self.assertEqual(t.classify([-.2,-.1],.1,{'invalid':0}),'RELIC_TRAJECTORY_QUALIFIED')
        self.assertEqual(t.classify([-.2,-.1],.10001,{'invalid':0}),'RELIC_TRAJECTORY_INCONCLUSIVE')
        self.assertEqual(t.classify([-.2,-.1],0,{'invalid':1}),'RELIC_TRAJECTORY_REJECTED')
        self.assertEqual(t.classify([.1,.2],0,{}),'RELIC_TRAJECTORY_REJECTED')
    def test_per_relic_carrier_and_change_denominators(self):
        flower=r.base._RELIC_IDS['HAPPY_FLOWER']; vajra=r.base._RELIC_IDS['VAJRA']
        cache=dict(relicPre=np.array([[0],[7]]),relicPost=np.array([[1],[7]]),
                   relicIds=np.array([[flower],[vajra]]),relicMask=np.ones((2,1),bool),
                   encounter=np.zeros(2,int),bloom=np.zeros(2,bool))
        metrics,_,_=t.reconstruction_metrics(cache,np.arange(2),{g:np.zeros(2,int) for g in t.HEADS})
        result=metrics['byRelic']['HAPPY_FLOWER']['decoder']
        self.assertEqual(result['rows'],1); self.assertEqual(result['fullVectorExact'],0.)
        self.assertEqual(result['changedVectorRows'],1)
        absent=metrics['byRelic']['SUNDIAL']['decoder']
        self.assertEqual(absent['rows'],0); self.assertIsNone(absent['fullVectorExact'])
        self.assertEqual(absent['changedVectorRows'],0)
    def test_sampled_slice_uses_each_draw_conditional_score(self):
        cache=dict(observed=np.ones((1,5),bool),preHp=np.array([20]),deltaClass=np.array([0]),
                   classes=np.array([0]),potionMask=np.array([0]),act=np.array([1]),room=np.array([4]))
        result=t.slices(cache,np.array([0]),np.array([1.]),np.array([2.]),np.array([[20],[5]]),np.zeros((2,1),int),np.array([[3.],[9.]]))
        self.assertEqual(result['sampledHpLoss']['[0,1)']['drawConditionalNll'],3.)
        self.assertEqual(result['sampledHpLoss']['[10,30)']['drawConditionalNll'],9.)

if __name__=='__main__': unittest.main()
