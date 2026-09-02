#!/usr/bin/env python3
"""Focused contract fixtures for the V1 combat evaluator."""
import csv, json, tempfile, unittest, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from combat_evaluator_contract import validate_csv, validate_manifest, FROZEN_TEACHER
from train_combat_evaluator import stable_split, scientific_verdict

class CombatEvaluatorContractTest(unittest.TestCase):
    def make_csv(self, rows):
        f = tempfile.NamedTemporaryFile(suffix=".csv", delete=False); p = Path(f.name); f.close()
        features = [f"f{i}" for i in range(1017)]
        head = ["sourceSeed","fightIdx","act","floor","roomClass","encounter","teacherId"] + features + ["won","trueDeath","escaped","turnCapLoss","progressAmbiguous","labelValid","terminalCombatHp","terminalCombatMaxHp","terminalNonMinionCurHp","terminalNonMinionMaxHp","winHpFrac","lossRemainingFrac","signedOutcome","quarantineReason"]
        with p.open("w", newline="") as out:
            w = csv.writer(out); w.writerow(head)
            for row in rows: w.writerow(row)
        return p

    def row(self, seed, won, death, valid=1, ambiguous=0, signed=None):
        hp = 50 if won else 0; enemy = 20 if death else 0; signed = (0.5 if won else -0.2) if signed is None else signed
        return [seed,0,1,1,"NORMAL","Cultist","teacher"] + [0.0]*1017 + [won,death,0,0,ambiguous,valid,hp,100,enemy,100,0.5 if won else 0.001,0.2 if death else 0.001,signed,""]

    def test_exact_signed_formulas_and_masks(self):
        p = self.make_csv([self.row(1,1,0), self.row(2,0,1)])
        self.assertEqual(validate_csv(p)["counts"]["deaths"], 1)
        p = self.make_csv([self.row(1,1,0,signed=0.2)])
        with self.assertRaises(ValueError): validate_csv(p)

    def test_invalid_outcomes_are_counted_and_excluded(self):
        p = self.make_csv([self.row(1,1,0), self.row(2,0,0,valid=0,signed=0), self.row(3,0,1,ambiguous=1)])
        result = validate_csv(p)
        self.assertEqual(result["source_seeds"], 3)
        self.assertEqual(result["counts"]["valid"], 2)
        self.assertEqual(result["counts"]["ambiguous"], 1)

    def test_grouped_split_is_stable_and_disjoint(self):
        a, b = stable_split(range(40)), stable_split(list(reversed(range(40))))
        self.assertEqual(a, b)
        self.assertEqual(set(a), set(range(40)))
        self.assertEqual(set(a.values()), {"train", "validation", "test"})

    def test_manifest_binds_hashes_and_counts(self):
        p = self.make_csv([self.row(10, 1, 0), self.row(11, 0, 1)])
        result = validate_csv(p)
        teacher = {"teacher_id":"silver", "git_sha":"a"*40, "executable_sha256":"b"*64, **FROZEN_TEACHER}
        manifest = {"schema_version":"combat_evaluator_v1", "producer_git_sha":"a"*40, "producer_executable_sha256":"b"*64,
          "teacher":teacher, "seed_spec":{"offset":10,"count":2,"ascension":0}, "csv":{"path":str(p),"sha256":result["csv_sha256"]},
          "feature_contract":{"count":1017,"state_names":result["features"],"encounters":["Cultist"],"model_features":result["features"]+["encounter__Cultist"],"one_hot":True,
            "order_hash":__import__("hashlib").sha256("\n".join(result["features"]+["encounter__Cultist"]).encode()).hexdigest()},
          "integrity":{"rows":2,"source_seeds":2,"quarantined_source_seeds":0}}
        self.assertEqual(validate_manifest(manifest)["rows"], 2)
        manifest["csv"]["sha256"] = "0"*64
        with self.assertRaises(ValueError): validate_manifest(manifest)

    def test_low_power_verdict(self):
        metrics = {"counts":{"test":{"valid":100,"nonambiguous_deaths":29}},
                   "survival":{"model":{"logloss":0.5}}, "conditional_win_hp":{"model":{"mae":0},"train_winner_mean_baseline":{"mae":1}},
                   "conditional_loss_remaining":{"model":{"mae":0},"train_death_mean_baseline":{"mae":1}}}
        self.assertEqual(scientific_verdict(metrics), "INCONCLUSIVE_LOW_POWER")

    def test_terminal_loss_uses_non_minion_helper(self):
        source = (Path(__file__).resolve().parents[1] / "src/sim/search/BattleScumSearcher2.cpp").read_text()
        self.assertIn("!m.hasStatus<MS::MINION>()", source)
        self.assertIn("getNonMinionMonsterHpTotals(bc, enemyCurHp, enemyMaxHp)",
                      (Path(__file__).resolve().parents[1] / "apps/one_combat.cpp").read_text())

if __name__ == "__main__": unittest.main()
