#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import copy
import unittest
from tools import combat_transition_sparse_events as n
from tools.combat_transition_sparse_events import b

class SparseEvents(unittest.TestCase):
    def pre(self):
        return dict(deck=[dict(id=b._CARD_IDS['RITUAL_DAGGER'],misc=15,upgraded=False)],
                    relics=[],cardTypeCounts=[1,0,0,0],transformableCount=1,upgradeableCount=1,bottleIdxs=[-1,-1,-1])
    def test_parasite_exact_structure(self):
        pre=self.pre();saved=copy.deepcopy(pre); posts=n.writhing_posts(pre)
        self.assertEqual(pre,saved);self.assertEqual(len(posts),2)
        self.assertEqual(posts[1]['deck'][-1],dict(id=b._CARD_IDS['PARASITE'],misc=0,upgraded=False))
        self.assertEqual(posts[1]['cardTypeCounts'],[1,0,0,1]);self.assertEqual(posts[1]['transformableCount'],2)
        self.assertEqual(n.writhing_target(pre,posts[1]),1)
    def test_omamori_active_flag_from_charges(self):
        for count in range(3):
            pre=self.pre();pre['relics']=[dict(id=b._RELIC_IDS['OMAMORI'],data=count)]
            posts=n.writhing_posts(pre);self.assertEqual(len(posts),2)
            self.assertEqual(posts[-1]['relics'][0]['data'],max(0,count-1));self.assertEqual(len(posts[-1]['deck']),len(pre['deck'])+int(count==0))
    def test_duplicate_identity_and_composition(self):
        pre=self.pre();pre['deck'].append(copy.deepcopy(pre['deck'][0]))
        post=copy.deepcopy(pre);post['deck'][1]['misc']+=3
        changes=n.ritual_changes(pre,post);self.assertEqual([(c['index'],c['delta']) for c in changes],[(0,0),(1,3)])
        implant=n.writhing_posts(pre)[1];implant['deck'][1]['misc']+=3
        self.assertEqual(n.writhing_target(pre,implant),1)
    def test_reject_unrelated_mutation(self):
        pre=self.pre();pre['deck'].append(dict(id=b._CARD_IDS['BASH'],misc=0,upgraded=False))
        post=copy.deepcopy(pre);post['deck'][1]['misc']=3
        with self.assertRaises(ValueError):n.ritual_changes(pre,post)

    def test_native_dagger_amounts_and_common_budget(self):
        pre=self.pre();pre.update(potions=[1]*5,gold=0)
        pi=dict(cards=[],globals=dict(encounter=b._ENCOUNTER_IDS['CULTIST'],ascension=0))
        self.assertEqual(n.ritual_posts(pre,pi),((0,),(3,)))
        pre['deck'].append(copy.deepcopy(pre['deck'][0]))
        self.assertNotIn((3,3),n.ritual_posts(pre,pi))
        pre['deck'][1]['upgraded']=True
        self.assertIn((0,5),n.ritual_posts(pre,pi))
        pi['cards']=[dict(cardId=b._CARD_IDS['ARMAMENTS'],upgraded=False)]
        self.assertIn((5,0),n.ritual_posts(pre,pi))

    def test_shared_kill_budget_and_thief_escape(self):
        from tools import combat_transition_gold_proc_budget as budget
        pre=self.pre();pre.update(potions=[1]*5,gold=100)
        pi=dict(cards=[dict(cardId=b._CARD_IDS['HAND_OF_GREED'],upgraded=False)],globals=dict(encounter=b._ENCOUNTER_IDS['CULTIST'],ascension=0))
        self.assertEqual(budget.joint_gold_posts(pre,pi,0,(3,)),((100,0),))
        pi['globals']['encounter']=b._ENCOUNTER_IDS['TWO_THIEVES']
        possible=budget.joint_gold_posts(pre,pi,0,(3,))
        self.assertNotIn((10,0),possible)
        self.assertIn((100,0),possible)

    def test_smoke_escape_budget_and_raw_stolen_intent_rule(self):
        from tools import combat_transition_gold_proc_budget as budget
        pre=self.pre();pre.update(potions=[1]*5,gold=100)
        pi=dict(cards=[dict(cardId=b._CARD_IDS['HAND_OF_GREED'],upgraded=False)],globals=dict(encounter=b._ENCOUNTER_IDS['LOOTER'],ascension=17))
        posts=budget.joint_gold_posts(pre,pi,0,(0,),escaped=True)
        self.assertIn((80,20),posts) # Alive thief, next mug: RAW includes theft.
        self.assertIn((60,0),posts) # Alive thief, next escape: RAW omits theft.
        self.assertFalse(any(gold>100 for gold,_ in posts))
        with self.assertRaises(ValueError):budget.joint_gold_posts(pre,pi,0,(3,),escaped=True)
        pi['globals']['encounter']=b._ENCOUNTER_IDS['TWO_THIEVES']
        posts=budget.joint_gold_posts(pre,pi,0,(0,),escaped=True)
        self.assertIn((60,40),posts);self.assertNotIn((140,0),posts)

    def test_generated_forge_controls_native_dagger_amounts(self):
        pre=self.pre();pre.update(potions=[1]*5,gold=0)
        pi=dict(cards=[],globals=dict(encounter=b._ENCOUNTER_IDS['TWO_LOUSE'],ascension=0))
        self.assertNotIn((5,),n.ritual_posts(pre,pi))
        self.assertIn((5,),n.ritual_posts(pre,pi,consumed_potions=[b._POTION_IDS['BLESSING_OF_THE_FORGE']]))

if __name__=='__main__':unittest.main()
