import importlib.util
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location('census',Path(__file__).parents[1]/'analyze_silver_useless.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
class CensusTest(unittest.TestCase):
    def example(self):
        return dict(schema=1,seed='0',provably_useless=True,
            proof_scope='frozen_concrete_state_forced_end_turn',snapshot=[1],reason='fixture',
            chosen_action=10,comparator_action=20,classification='lower_q_but_selected',q_difference=-1,
            root_actions=[dict(action=10,edge_visits=10,q=1),dict(action=20,edge_visits=5,q=2)])
    def test_visit_selection_diagnosis(self):
        self.assertEqual(c.analyze([self.example()])['classification'],{'lower_q_but_selected':1})
    def test_tie_order_and_wrong_classification(self):
        row=self.example();row['root_actions'][1]['edge_visits']=10
        self.assertEqual(c.analyze([row])['verified_selected'],1)
        row['root_actions'].reverse()
        with self.assertRaises(ValueError):c.analyze([row])
        row=self.example();row['classification']='higher_q_for_useless_action'
        with self.assertRaises(ValueError):c.analyze([row])
    def test_zero_census(self):
        row=dict(schema=1,seed='0',provably_useless=False,reason='outside_class')
        self.assertEqual(c.analyze([row])['verified_selected'],0)
if __name__=='__main__':unittest.main()
