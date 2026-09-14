import unittest
from tools import combat_transition_brew as b


class BrewNativeTest(unittest.TestCase):
    def test_recursive_native_corpus_rng_fixture(self):
        # Frozen RAW row 662: two Brew uses, including a generated Brew.
        origin=dict(counter=30,seed0=14696873073139249100,seed1=10634194548135322916)
        first,state=b.generate(origin,3)
        second,state=b.generate(state,3)
        self.assertEqual(first+second,(17,9,22,23,39,22))
        self.assertEqual(state,dict(counter=53,seed0=12108256917720706954,seed1=4584229403586905532))
        self.assertEqual(origin['counter'],30)

    def test_native_rarity_law_and_recursive_support(self):
        self.assertEqual(len(b.PROBABILITY),32)
        self.assertNotIn(b.FRUIT,b.PROBABILITY)
        for rarity,mass in b.RARITY_MASS.items():
            self.assertAlmostEqual(sum(p for potion,p in b.PROBABILITY.items() if b.RARITY[potion]==rarity),mass)
        self.assertGreater(b.PROBABILITY[b.base._POTION_IDS['ENTROPIC_BREW']],0)
        self.assertGreater(b.PROBABILITY[b.base._POTION_IDS['SMOKE_BOMB']],0)

    def test_obtain_first_empty_full_inventory_and_sozu(self):
        empty=b.base._POTION_IDS['EMPTY_POTION_SLOT']
        self.assertEqual(b.obtain([20,empty,empty],[17,9,22]),[20,17,9])
        self.assertEqual(b.obtain([20,17,9],[22,23,39]),[20,17,9])
        self.assertEqual(b.obtain([20,empty,empty],[17,9,22],sozu=True),[20,empty,empty])
        self.assertEqual(b.obtain([20,empty,empty,empty,empty],[17,9,22],capacity=3),[20,17,9,empty,empty])


if __name__=='__main__':unittest.main()
