import importlib.util
from pathlib import Path
import unittest
spec = importlib.util.spec_from_file_location('profile', Path(__file__).parents[1] / 'analyze_run_profile.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)

class RunProfileTest(unittest.TestCase):
    def row(self):
        def actions(n, flip=False):
            return [dict(id=0, visits=n//2 + (-1 if flip else 1), q=.5, prior=.5),
                    dict(id=1, visits=n//2 + (1 if flip else -1), q=.5, prior=.5)]
        return dict(expanded_action_histogram={'2':1}, expanded_nodes=1,
            completed_simulations=512, configured_simulations=512, singleton_bypass=0,
            selection_rule='visits_q_id', selected_action=0, aborted=False, executed=True,
            actions=actions(512), checkpoints=[dict(simulations=n, actions=actions(n,n==128)) for n in (128,256,512)])
    def test_stability(self):
        row=p.decision(self.row())
        self.assertEqual(row['b_stable_full_budget'],256)
        self.assertEqual(row['leader_changes'],1)
    def test_early_stop_not_full_budget(self):
        row=self.row(); row['configured_simulations']=2048
        self.assertIsNone(p.decision(row)['b_stable_full_budget'])
    def test_missing_checkpoint_and_histogram_rejected(self):
        row=self.row(); row['checkpoints'].pop(0)
        with self.assertRaises(ValueError): p.decision(row)
        row=self.row(); row['expanded_nodes']=2
        with self.assertRaises(ValueError): p.decision(row)
    def test_floor_reconciliation(self):
        row = self.row()
        row.update(schema=1, kind='ooc_decision', seed='0', act=1, floor=1, decision=0,
                   screen=1, room='EVENT', wall_seconds=1, thread_cpu_seconds=1,
                   leaf_evaluations=512, transition_samples=512, outcome_particles=512, ctm_samples=0)
        floor = dict(schema=1, kind='floor', seed='0', act=1, floor=1, room='EVENT', status='advanced',
                     wall_seconds=2, thread_cpu_seconds=2, real_combat_wall_seconds=0,
                     real_combat_cpu_seconds=0, ooc_wall_seconds=1, ooc_cpu_seconds=1,
                     combat_decisions=0, ooc_decisions=1, ooc_owned=1, fallbacks=0, support_aborts=0,
                     ooc_simulations=512, leaf_evaluations=512,
                     transition_samples=512, outcome_particles=512, ctm_samples=0)
        self.assertEqual(p.analyze([row, floor])['expanded_nodes'], 1)
        floor['ctm_samples'] = 1
        with self.assertRaises(ValueError): p.analyze([row, floor])

    def zero_work(self, executed=True, aborted=False):
        row = self.row()
        row.update(schema=1, kind='ooc_decision', seed='0', act=1, floor=1, decision=0,
                   screen=1, room='EVENT', wall_seconds=0, thread_cpu_seconds=0,
                   expanded_action_histogram={}, expanded_nodes=0, completed_simulations=0,
                   actions=[], checkpoints=[], singleton_bypass=int(executed),
                   executed=executed, aborted=aborted, leaf_evaluations=0,
                   transition_samples=0, outcome_particles=0, ctm_samples=0)
        floor = dict(schema=1, kind='floor', seed='0', act=1, floor=1, room='EVENT',
                     status='advanced', wall_seconds=1, thread_cpu_seconds=1,
                     real_combat_wall_seconds=0, real_combat_cpu_seconds=0,
                     ooc_wall_seconds=0, ooc_cpu_seconds=0, combat_decisions=0,
                     ooc_decisions=1, ooc_owned=int(executed), fallbacks=int(not executed),
                     support_aborts=int(aborted), ooc_simulations=0, leaf_evaluations=0,
                     transition_samples=0, outcome_particles=0, ctm_samples=0)
        return row, floor

    def test_missing_zero_work_rows(self):
        for executed, aborted in ((True, False), (False, False), (False, True)):
            row, floor = self.zero_work(executed, aborted)
            self.assertEqual(p.analyze([row, floor])['decisions'], 1)
            with self.assertRaisesRegex(ValueError, 'ooc_decisions'):
                p.analyze([floor])

    def test_status_counters(self):
        for field in ('ooc_owned', 'fallbacks', 'support_aborts'):
            row, floor = self.zero_work()
            floor[field] += 1
            with self.assertRaisesRegex(ValueError, field): p.analyze([row, floor])
        for field in ('executed', 'aborted'):
            row, floor = self.zero_work(); row[field] = 1
            with self.assertRaises(ValueError): p.analyze([row, floor])

    def test_explicit_unprofiled_paths(self):
        for disabled, observer in ((1, 0), (0, 1), (2, 3)):
            row, floor = self.zero_work()
            floor.update(unprofiled_disabled=disabled, unprofiled_observer=observer,
                         ooc_decisions=1 + disabled + observer, fallbacks=observer)
            self.assertEqual(p.analyze([row, floor])['decisions'], 1)
            with self.assertRaises(ValueError): p.analyze([floor])
            for field in ('unprofiled_disabled', 'unprofiled_observer'):
                bad = dict(floor); bad[field] = -1
                with self.assertRaises(ValueError): p.analyze([row, bad])
            del floor['unprofiled_disabled']; del floor['unprofiled_observer']
            with self.assertRaises(ValueError): p.analyze([row, floor])
        row, floor = self.zero_work()
        floor.update(unprofiled_disabled=1, ooc_owned=0)
        self.assertEqual(p.analyze([floor])['decisions'], 0)
        floor.update(unprofiled_disabled=0, unprofiled_observer=1, fallbacks=1)
        self.assertEqual(p.analyze([floor])['decisions'], 0)

    def test_partial_abort_floor_not_qualified(self):
        row, floor = self.zero_work()
        floor['status'] = 'abort'
        self.assertEqual(p.analyze([floor])['decisions'], 0)

    def test_strict_lock_and_tie(self):
        actions=[dict(id=0,visits=7,q=.2,prior=.5),dict(id=1,visits=3,q=.9,prior=.5)]
        self.assertTrue(p.action_stats(actions,10,13,'visits_q_id')['strict_visit_lock'])
        self.assertFalse(p.action_stats(actions,10,14,'visits_q_id')['strict_visit_lock'])
        self.assertEqual(p.action_stats(actions,10,14,'q_visits_id')['winner'],1)
if __name__ == '__main__': unittest.main()
