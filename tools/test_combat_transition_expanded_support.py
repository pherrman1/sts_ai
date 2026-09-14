import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import importlib.util
import unittest
from unittest.mock import patch
import numpy as np
x=None
if importlib.util.find_spec('torch'):
    from tools import combat_transition_expanded_support as x


@unittest.skipUnless(x, 'optional torch dependency, matching composed evaluator tests')
class ExpandedSupportTest(unittest.TestCase):
    def test_disjoint_union_and_counts_fail_closed(self):
        masks={'OLD':np.array([1,0,0],bool),'RECOVERED':np.array([0,1,0],bool),'EXPANDED':np.array([1,1,0],bool)}
        expected={'OLD':1,'RECOVERED':1,'EXPANDED':2}
        x.prove_partitions(masks,expected)
        with self.assertRaises(ValueError): x.prove_partitions(masks,dict(expected,RECOVERED=2))
        with self.assertRaises(ValueError): x.prove_partitions(dict(masks,RECOVERED=np.array([1,0,0],bool)),expected)
        with self.assertRaises(ValueError): x.prove_partitions(dict(masks,EXPANDED=np.ones(3,bool)),expected)

    def test_historical_certification_retains_color_and_brew_exclusions(self):
        c=x.c; audited=x.old_card_ids()
        pi=dict(globals=dict(characterClass=c.base.IRONCLAD_ID),cards=[dict(cardId=c.base._CARD_IDS['BASH'])],potions=[])
        self.assertTrue(x.old_certified(pi,audited))
        self.assertFalse(x.old_certified(dict(pi,cards=[dict(cardId=c.base._CARD_IDS['ACROBATICS'])]),audited))
        self.assertFalse(x.old_certified(dict(pi,potions=[dict(potionId=c.base.ENTROPIC_BREW_ID)]),audited))
        self.assertFalse(x.old_certified(dict(pi,globals=dict(characterClass=-1)),audited))

    def test_gate_is_independent_and_inclusive_with_rejection_precedence(self):
        scores={k:{h:dict(mean=.1) for h in ('hp','potion','relic')} for k in ('RECOVERED','EXPANDED')}
        validity={k:dict.fromkeys(x.e.VALIDITY_KEYS,0) for k in ('RECOVERED','EXPANDED')}
        self.assertEqual(x.classify(scores,validity,True),'EXPANDED_COMPOSED_TRANSITION_QUALIFIED')
        for cohort in scores:
            for component in scores[cohort]:
                scores[cohort][component]['mean']=.10001
                self.assertEqual(x.classify(scores,validity,True),'EXPANDED_COMPOSED_TRANSITION_REJECTED')
                scores[cohort][component]['mean']=.1
        for cohort in scores:
            for component in scores[cohort]:
                incomplete={k:dict(v) for k,v in scores.items()}; del incomplete[cohort][component]
                self.assertEqual(x.classify(incomplete,validity,True),'EXPANDED_COMPOSED_TRANSITION_INCONCLUSIVE')
        for cohort in validity:
            for key in validity[cohort]:
                incomplete={k:dict(v) for k,v in validity.items()}; del incomplete[cohort][key]
                self.assertEqual(x.classify(scores,incomplete,True),'EXPANDED_COMPOSED_TRANSITION_INCONCLUSIVE')
        self.assertEqual(x.classify({},validity,True),'EXPANDED_COMPOSED_TRANSITION_INCONCLUSIVE')
        validity['RECOVERED']['hpBelow1']=-1
        self.assertEqual(x.classify(scores,validity,True),'EXPANDED_COMPOSED_TRANSITION_REJECTED')
        validity['RECOVERED']['hpBelow1']=0
        scores['RECOVERED']['relic']['mean']=None
        self.assertEqual(x.classify(scores,validity,True),'EXPANDED_COMPOSED_TRANSITION_INCONCLUSIVE')
        scores['EXPANDED']['hp']['mean']=float('inf')
        self.assertEqual(x.classify(scores,validity,True),'EXPANDED_COMPOSED_TRANSITION_REJECTED')
        scores['EXPANDED']['hp']['mean']=.1;validity['RECOVERED']['hpBelow1']=1
        self.assertEqual(x.classify(scores,validity,True),'EXPANDED_COMPOSED_TRANSITION_REJECTED')
        self.assertEqual(x.classify(scores,{'EXPANDED':dict(hpBelow1=0)},False),'EXPANDED_COMPOSED_TRANSITION_REJECTED')

    def test_exposure_uses_probability_mixture_then_informative_group_normalization(self):
        metrics=dict(rows=np.array([10,20,30]),source=np.array([1,2,2]),observedGroups=np.array([2,0,1]))
        raw=dict(rows=np.array([10,20,30]),hpExactNll=np.array([.4,.5,.6]))
        for key in ('hp','potion','relic'):
            raw[key+'-teacherNll']=np.array([.2,.3,.4])
            raw[key+'-drawMass']=np.array([[.1,.3,.5],[.9,.5,.3]])
        selected=np.array([1,1,0],bool)
        with patch.object(x.e,'source_gap_bootstrap',side_effect=lambda sources,diff:dict(mean=float(diff.mean()),sourceBootstrap95=[0,1],rows=len(diff))):
            score=x.exposure_metrics(raw,metrics,selected)
        self.assertAlmostEqual(score['hp']['mean'],.2)
        self.assertAlmostEqual(score['potion']['mean'],((-np.log(.5)-.2)+(-np.log(.4)-.3))/2)
        self.assertAlmostEqual(score['relic']['mean'],(-np.log(.5)-.2)/2)
        self.assertEqual(score['relic']['rows'],1)
        with patch.object(x.e,'source_gap_bootstrap',side_effect=lambda sources,diff:dict(mean=float(diff.mean()))):
            empty=x.exposure_metrics(raw,metrics,np.array([0,1,0],bool))
        self.assertIsNone(empty['relic']['mean'])
        self.assertEqual(empty['relic']['decision'],'NO_INFORMATIVE_ROWS')


if __name__=='__main__': unittest.main()
