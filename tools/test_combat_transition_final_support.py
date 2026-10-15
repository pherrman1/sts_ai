import unittest
from tools import combat_transition_near_full_support as s
class FinalSupport(unittest.TestCase):
    def row(self):return {'pi':{'globals':{'encounter':1}},'pre':{'potions':[1]*5,'smokeBombUsed':False,'deck':[]}}
    def test_smoke_and_prior_flag_fail_closed(self):
        row=self.row();row['pre']['potions'][0]=s.c.base._POTION_IDS['SMOKE_BOMB'];self.assertEqual(s.final_exclusions(row['pi'],row['pre']),['smoke_bomb'])
        row['pre']['potions'][0]=1;row['pre']['smokeBombUsed']=True;self.assertEqual(s.final_exclusions(row['pi'],row['pre']),['pre_smoke_bomb_used'])
    def test_intersection_keeps_individual_mechanisms(self):
        row=self.row();row['pi']['globals']['encounter']=s.c.base.WRITHING_MASS_ID;self.assertFalse(s.final_exclusions(row['pi'],row['pre']))
        row['pre']['deck']=[{'id':s.c.base._CARD_IDS['RITUAL_DAGGER']}];self.assertEqual(s.final_exclusions(row['pi'],row['pre']),['writhing_ritual_intersection'])
        row['pi']['globals']['encounter']=1;self.assertFalse(s.final_exclusions(row['pi'],row['pre']))
    def test_capabilities_lift_only_their_exclusion(self):
        row=self.row();row['pi']['globals']['encounter']=s.c.base.WRITHING_MASS_ID;row['pre']['deck']=[{'id':s.c.base._CARD_IDS['RITUAL_DAGGER']}]
        row['pre']['potions'][0]=s.c.base._POTION_IDS['SMOKE_BOMB']
        self.assertEqual(s.final_exclusions(row['pi'],row['pre'],writhing_ritual=True),['smoke_bomb'])
        self.assertEqual(s.final_exclusions(row['pi'],row['pre'],escape=True),['writhing_ritual_intersection'])
        self.assertFalse(s.final_exclusions(row['pi'],row['pre'],escape=True,writhing_ritual=True))
        row['pre']['smokeBombUsed']=True;self.assertEqual(s.final_exclusions(row['pi'],row['pre'],escape=True,writhing_ritual=True),['pre_smoke_bomb_used'])
    def test_brew_generation_output_cannot_decide_prestate_support(self):
        row=self.row();row['pre']['potions'][0]=s.c.base._POTION_IDS['ENTROPIC_BREW'];row['post']={'smokeBombUsed':True};self.assertTrue(s.final_mask([row])[0])
if __name__=='__main__':unittest.main()
