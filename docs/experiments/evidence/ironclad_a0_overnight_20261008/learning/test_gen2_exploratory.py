#!/usr/bin/env python3
"""Synthetic weighting/uncertainty checks; no game or research rows opened."""
import unittest
import analyze_gen2_exploratory as a


class ExploratoryWeightingTest(unittest.TestCase):
    def test_no_state_zero_only_for_effects(self):
        values={a.SEEDS[0]:.5}
        self.assertEqual(a.source_summary(values)['estimate'],.5)
        self.assertEqual(a.source_summary(values,True)['estimate'],.5/32)
        self.assertEqual(a.source_summary(values)['exposed_source_count'],1)

    def test_all_undefined_draws_retained(self):
        r=a.source_summary({})
        self.assertIsNone(r['estimate'])
        self.assertIsNone(r['ci95_pointwise_unadjusted'])
        self.assertEqual(r['bootstrap_undefined_draws'],10000)

    def test_family_additivity_unequal_state_counts(self):
        s0,s1=a.SEEDS[:2]
        card=(s0,1,'CARD_REWARD');boss=(s0,2,'BOSS_RELIC');other=(s1,3,'CARD_REWARD')
        states=[card,boss,other]
        x=a.state_summary({card:.5,other:1},states,True)['estimate']
        y=a.state_summary({boss:-.5},states,True)['estimate']
        total=a.state_summary({card:.5,boss:-.5,other:1},states,True)['estimate']
        self.assertEqual(x+y,total)
        self.assertEqual(total,1/32)
        self.assertEqual(a.state_summary({card:.5,other:1},states)['estimate'],.75)

    def test_calibration_balances_sources_states_options(self):
        s0,s1=a.SEEDS[:2];x=(s0,1,'CARD_REWARD');y=(s0,2,'BOSS_RELIC');z=(s1,3,'CARD_REWARD')
        opts={x:['a'],y:['a','b','c'],z:['a']};labels={};pred={}
        for state,options in opts.items():
            for option in options:
                for k in range(4,8):
                    labels[(state,option,k)]={'finalWon':'0'}
                    pred[(state,option,k)]={x:.1,y:.9,z:.4}[state]
        r=a.calibration([x,y,z],opts,labels,pred)
        self.assertAlmostEqual(r['bias']['estimate'],.45)
        self.assertAlmostEqual(r['brier']['estimate'],((.01+.81)/2+.16)/2)
        self.assertEqual(r['source_count'],2)
        self.assertEqual(r['rows'],20)
        masses=[b['weighted_mass'] for b in r['reliability']]
        self.assertAlmostEqual(sum(masses),1)
        self.assertAlmostEqual(masses[0],.25)
        self.assertAlmostEqual(masses[4],.25)
        self.assertAlmostEqual(masses[2],.5)
        self.assertEqual(r['reliability'][1]['mean_prediction']['bootstrap_undefined_draws'],10000)

    def test_paired_variance_preserves_coupling(self):
        left=[0,1,0,1];right=[0,1,0,1]
        self.assertGreater(a.stats(left)['sample_variance'],0)
        self.assertEqual(a.stats([x-y for x,y in zip(left,right)])['sample_variance'],0)


if __name__=='__main__':unittest.main(verbosity=2)
