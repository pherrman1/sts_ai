"""pack_states.py (combat plan stage 2): the played card may be another copy of the edge's card."""

import importlib.util
import os
import unittest

try:
    import numpy  # noqa: F401  (tensorize needs numpy; CI may lack it)
    HAVE_NUMPY = True
except ImportError:
    HAVE_NUMPY = False

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


@unittest.skipUnless(HAVE_NUMPY, "numpy not installed")
class ActionRows(unittest.TestCase):
    """Distinct actions (up to the played card's unique id) must give distinct tensorize action rows."""

    def setUp(self):
        spec = importlib.util.spec_from_file_location("tensorize", os.path.join(ROOT, "tools", "combat_net",
                                                                               "tensorize.py"))
        self.tz = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.tz)
        wspec = importlib.util.spec_from_file_location("wire_encoder", os.path.join(ROOT, "tools", "combat_net",
                                                                                   "wire_encoder.py"))
        self.we = importlib.util.module_from_spec(wspec)
        wspec.loader.exec_module(self.we)

    def row(self, s):
        return self.tz.action_row(self.we.parse_semantic(s))

    def test_selected_upgrade_is_kept(self):
        base = "sa/t=4/s=1/c=0_0_0_0_0_0_0_0/o=0/p=0_-1/x=-1/d=0/k=0/task=6/sel="
        self.assertNotEqual(self.row(base + "104_6_0_1_1_0_0_0"), self.row(base + "104_7_0_1_1_1_0_0"))
        self.assertNotEqual(self.row(base + "104_6_0_1_1_0_0_0"), self.row(base + "104_6_3_1_1_0_0_0"))

    def test_unique_id_is_ignored(self):
        a = "sa/t=1/s=1/c=179_16_0_1_1_0_0_0/o=0/p=0_-1/x=0/d=0/k=0/task=0/sel="
        b = "sa/t=1/s=1/c=179_13_0_1_1_0_0_0/o=0/p=0_-1/x=0/d=0/k=0/task=0/sel="
        self.assertEqual(self.row(a), self.row(b))
        self.assertEqual(len(self.row(a)), self.tz.A_LEN)


if __name__ == "__main__":
    unittest.main()
