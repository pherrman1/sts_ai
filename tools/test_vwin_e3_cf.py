import unittest

import pandas as pd

from tools.vwin_e3_cf import apply_rules, selection_rows


def _lab(rows):
    cols = ["sourceSeed", "decisionIdx", "type", "act", "optionIdx", "optionKey", "chosen", "k", "valid", "finalWon"]
    return pd.DataFrame(rows, columns=cols)


class E3Test(unittest.TestCase):
    def setUp(self):
        skip = "ooc:v1:effect=12:source=7:none"
        take = "ooc:v1:effect=5:source=7:card"
        self.lab = _lab([
            (1, 5, "CARD_REWARD", 1, 0, skip, 0, 0, 1, 0), (1, 5, "CARD_REWARD", 1, 1, take, 1, 0, 1, 1),
            (1, 5, "CARD_REWARD", 1, 0, skip, 0, 1, 1, 1), (1, 5, "CARD_REWARD", 1, 1, take, 1, 1, 0, -1),
        ])
        self.map = self.lab[["sourceSeed", "decisionIdx", "type", "optionIdx", "optionKey", "chosen", "k"]].copy()
        self.map["act"] = 2
        self.map["curHp"] = [10, 50, 11, 51]

    def test_invalid_sibling_drops_group_and_act_is_decision_act(self):
        df, dropped = apply_rules(self.lab, self.map)
        self.assertEqual(dropped, 1)
        self.assertEqual(sorted(df["k"].unique().tolist()), [0])
        self.assertEqual(df["lab_act"].tolist(), [1, 1])
        self.assertEqual(df["act"].tolist(), [2, 2])

    def test_selection_gain_skip_and_ties(self):
        df, _ = apply_rules(self.lab, self.map)
        df["score"] = [0.9, 0.1]
        row, = selection_rows(df, "score")
        self.assertEqual(row["gain"], -1.0)      # picks skip (lost) over chosen take (won)
        self.assertEqual(row["picks_skip"], 1.0)
        self.assertFalse(row["agrees"])
        df["score"] = [0.5, 0.5]
        row, = selection_rows(df, "score")
        self.assertEqual(row["gain"], -0.5)      # tie averages both options
        self.assertEqual(row["oracle"], 0.0)


if __name__ == "__main__":
    unittest.main()
