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

if __name__=='__main__':unittest.main()
