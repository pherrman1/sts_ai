"""Controlled Ritual coverage pilot launcher boundaries; no native run."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import ctm_ritual_coverage_pilot as pilot
from tools import combat_transition_surrogate as b


class RitualCoveragePilotTest(unittest.TestCase):
    def test_unit_ledger_is_fixed_source_major_cell_order(self):
        units = pilot.units()
        self.assertEqual(len(units), pilot.BUDGET["units"])
        self.assertEqual([u["index"] for u in units], list(range(144)))
        self.assertEqual([u["setup"] for u in units[:12]], list(pilot.CELLS))
        self.assertEqual(pilot.CELLS[0], "ritual_writhing_v2_base_single_natural")
        self.assertEqual(pilot.CELLS[-1], "ritual_writhing_v2_upgraded_double_smoke")
        self.assertEqual({u["sourceSeed"] for u in units if u["partition"] == "TRAIN"}, set(pilot.TRAIN))
        self.assertEqual({u["sourceSeed"] for u in units if u["partition"] == "VALIDATION"}, set(pilot.VALIDATION))
        self.assertFalse(set(pilot.TRAIN) & set(pilot.VALIDATION))
        self.assertEqual(len({u["id"] for u in units}), 144)

    def test_descriptor_matches_native_cell_semantics(self):
        d = pilot.descriptor("ritual_writhing_v2_upgraded_double_brew", b._POTION_IDS)
        self.assertTrue(d["upgraded"]); self.assertEqual(d["copies"], 2)
        self.assertEqual(d["damageByOrdinal"], [15, 30])
        self.assertEqual(d["forcedPotion"], b._POTION_IDS["ENTROPIC_BREW"])
        d = pilot.descriptor("ritual_writhing_v2_base_single_natural", b._POTION_IDS)
        self.assertFalse(d["upgraded"]); self.assertEqual(d["damageByOrdinal"], [15])
        self.assertEqual(d["forcedPotion"], b._POTION_IDS["EMPTY_POTION_SLOT"])
        self.assertFalse(d["consumesRng"]); self.assertFalse(d["changesSelectedActions"])

    def test_recipe_forbids_fitting_retry_and_test_access(self):
        r = pilot.recipe()
        for key in ("retry", "resume", "replacements", "extension", "fitting",
                    "modelInference", "testAccess", "promotion"):
            self.assertIs(r[key], False, key)
        self.assertEqual(r["budget"]["workers"], 8)
        self.assertEqual(r["budget"]["threadsPerWorker"], 1)
        self.assertFalse(r["budget"]["gpu"])

    def test_approval_requires_exact_review_and_named_human_authorization(self):
        identity = dict(sourceSha="a" * 40)
        review = dict(verdict="PASS", independent=True, sourceSha=identity["sourceSha"],
                      packetIdentity=pilot.packet_identity(), recipeSha256=pilot.digest(pilot.recipe()))
        approval = dict(schema="ritual_coverage_resource_approval_v1", approved=True, budget=pilot.BUDGET,
                        recipeSha256=pilot.digest(pilot.recipe()), humanAuthorization="Philipp: yes")
        pilot.approval_check(review, approval, identity)
        for bad in (dict(approval, humanAuthorization="PENDING"), dict(approval, approved=False),
                    dict(approval, budget=dict(pilot.BUDGET, workers=12))):
            with self.assertRaises(ValueError):
                pilot.approval_check(review, bad, identity)
        for bad in (dict(review, independent=False), dict(review, sourceSha="b" * 40),
                    dict(review, recipeSha256="0" * 64)):
            with self.assertRaises(ValueError):
                pilot.approval_check(bad, approval, identity)


if __name__ == "__main__":
    unittest.main()
