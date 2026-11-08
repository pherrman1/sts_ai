"""pack_states.py (combat plan stage 2): the played card may be another copy of the edge's card."""

import importlib.util
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("pack_states", os.path.join(ROOT, "tools", "combat_net", "pack_states.py"))
ps = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ps)


class NoUid(unittest.TestCase):
    def test_unique_id_is_zeroed(self):
        a = "sa/t=1/s=1/c=179_16_0_1_1_0_0_0/o=0/p=0_-1/x=0/d=0/k=0/task=0/sel="
        b = "sa/t=1/s=1/c=179_13_0_1_1_0_0_0/o=0/p=0_-1/x=0/d=0/k=0/task=0/sel="
        self.assertEqual(ps.no_uid(a), ps.no_uid(b))
        self.assertEqual(ps.no_uid(a), "sa/t=1/s=1/c=179_0_0_1_1_0_0_0/o=0/p=0_-1/x=0/d=0/k=0/task=0/sel=")

    def test_other_fields_still_differ(self):
        a = "sa/t=1/s=1/c=179_16_0_1_1_0_0_0/o=0/p=0_-1/x=0/d=0/k=0/task=0/sel="
        self.assertNotEqual(ps.no_uid(a), ps.no_uid(a.replace("x=0", "x=1")))
        self.assertNotEqual(ps.no_uid(a), ps.no_uid(a.replace("c=179_16_0", "c=179_16_1")))


if __name__ == "__main__":
    unittest.main()
