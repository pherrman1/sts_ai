from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'tools'/'heart1'))
from capture_provenance import row_wing_boots_counter, single_wing_boots_counter


class WingBootsCounterProvenance(unittest.TestCase):
    def test_rows_without_field_are_frozen_encoding(self):
        self.assertEqual(row_wing_boots_counter({'record': {}}), 0)
        self.assertEqual(row_wing_boots_counter({'wing_boots_counter': 1}), 1)
        with self.assertRaises(ValueError):
            row_wing_boots_counter({'wing_boots_counter': 2})

    def test_training_set_uses_one_value(self):
        self.assertEqual(single_wing_boots_counter([]), 0)
        self.assertEqual(single_wing_boots_counter([1, 1]), 1)
        self.assertEqual(single_wing_boots_counter([0, 0]), 0)
        with self.assertRaises(ValueError):
            single_wing_boots_counter([0, 1])


if __name__ == '__main__':
    unittest.main()
