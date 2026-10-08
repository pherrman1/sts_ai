import argparse
import json
import tempfile
import unittest
from pathlib import Path

try:
    from tools import combat_transition_model_experiment as experiment
    from tools.combat_transition_contract import ROW_SCHEMA_VERSION, SCHEMA_VERSION, sha256
    from tools.ctm_corpus_adapter import assemble, union
    from tools.combat_transition_contract import validate_corpus
    from tools.test_combat_transition_contract import predictor_input, state, teacher
except ModuleNotFoundError:  # direct invocation from the tools directory
    import combat_transition_model_experiment as experiment
    from combat_transition_contract import ROW_SCHEMA_VERSION, SCHEMA_VERSION, sha256
    from ctm_corpus_adapter import assemble, union
    from combat_transition_contract import validate_corpus
    from test_combat_transition_contract import predictor_input, state, teacher

try:
    from tools.combat_predictor_input_contract import FIELD_SCHEMA_HASH, SCHEMA_VERSION as PREDICTOR_SCHEMA_VERSION
except ModuleNotFoundError:
    from combat_predictor_input_contract import FIELD_SCHEMA_HASH, SCHEMA_VERSION as PREDICTOR_SCHEMA_VERSION


def learned_teacher():
    t = teacher()
    t["teacher_id"] = "learned"
    t["search_configuration"].update({"budget_policy": "learned_stop",
                                      "learned_stop_model": "gbt-770201c31f7b",
                                      "learned_stop_threshold": 0.0323})
    t["environment"].update({"STS_SILVER_EXACT_ROOT_BUDGETS": "0", "STS_SILVER_LEARNED_STOP": "1"})
    return t


def write_unit(path: Path, start: int, count: int, setup: str, skip=()):
    rows = []
    for seed in range(start, start + count):
        if seed in skip:
            continue
        for fight, outcome in ((0, 1), (1, seed % 2 + 1)):
            rows.append({
                "schemaVersion": SCHEMA_VERSION, "rowSchemaVersion": ROW_SCHEMA_VERSION,
                "sourceSeed": seed, "fightIdx": fight, "act": 1, "floor": fight + 1,
                "roomClass": "NORMAL", "encounter": 1, "teacherId": "learned",
                "runValid": True, "quarantineReason": "", "captureCount": 1,
                "captureStatus": "exactly_one", "predictorInput": predictor_input(fight + 1),
                "transition": {"schemaVersion": SCHEMA_VERSION, "combatOutcome": outcome,
                               "rawGameOutcome": 1, "pre": state(), "post": state()},
            })
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    manifest = {
        "schemaVersion": SCHEMA_VERSION, "rowSchemaVersion": ROW_SCHEMA_VERSION,
        "predictorInputSchemaVersion": PREDICTOR_SCHEMA_VERSION,
        "predictorInputFieldSchemaHash": FIELD_SCHEMA_HASH, "format": "jsonl",
        "producerGitSha": "a" * 40, "producerExecutableSha256": "b" * 64,
        "combatTeacher": learned_teacher(), "seedSpec": {"start": start, "count": count},
        "csv": {"path": f"/elsewhere/{path.name}", "sha256": sha256(path)},
        "integrity": {"requestedSeeds": count, "completedSeeds": count, "quarantinedSeeds": 0,
                      "rows": len(rows)},
        "forcedSetup": setup,
    }
    Path(str(path) + ".manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return {"path": f"part-a/{path.name}", "sha256": sha256(path), "rows": len(rows),
            "seeds": manifest["seedSpec"]}


class TestCtmCorpusAdapter(unittest.TestCase):
    def build(self, root: Path):
        part = root / "part-a"; part.mkdir()
        units = [
            {"unit": "none-100-4", "setup": "none", "files": [write_unit(part / "none-100-4.jsonl", 100, 4, "none")]},
            # Unit split around stalled seed 105.
            {"unit": "none-104-4", "setup": "none", "files": [
                write_unit(part / "none-104-4.s104-1.jsonl", 104, 1, "none"),
                write_unit(part / "none-104-4.s106-2.jsonl", 106, 2, "none")]},
            {"unit": "high_maxhp-500-2", "setup": "high_maxhp",
             "files": [write_unit(part / "high_maxhp-500-2.jsonl", 500, 2, "high_maxhp")]},
        ]
        index = {"errors": [], "units": units, "stalled": {"105": ["none-104-4", "silver_stall", "part-a"]}}
        (root / "index.json").write_text(json.dumps(index), encoding="utf-8")
        return root / "index.json"

    def test_assemble_feeds_unmodified_audit_and_prepare(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); index = self.build(root)
            out = root / "scope-none"
            summary = assemble(index, root, "none", out)
            self.assertEqual(summary["seedSpec"], {"start": 100, "count": 8})
            self.assertEqual(summary["quarantined"], [105])
            self.assertEqual(summary["rows"], 14)
            block = json.loads((out / "blocks" / "none-104-4.s106-2.jsonl.manifest.json").read_text())
            self.assertEqual(block["csv"]["path"], str((root / "part-a" / "none-104-4.s106-2.jsonl").resolve()))
            self.assertEqual(block["ctmCorpusAdapter"]["originalCsvPath"], "/elsewhere/none-104-4.s106-2.jsonl")
            seeds = [json.loads(l)["sourceSeed"] for l in (out / "corpus.jsonl").read_text().splitlines()]
            self.assertEqual(seeds, sorted(seeds))
            experiment.audit(argparse.Namespace(corpus_manifest=str(out / "corpus.jsonl.manifest.json"),
                                                shard_root=str(out), output_dir=str(root / "audit")))
            audit = json.loads((root / "audit" / "corpus_audit.json").read_text())
            self.assertEqual(audit["split"]["excludedQuarantinedSeeds"], [105])
            experiment.prepare(argparse.Namespace(audit=str(root / "audit" / "corpus_audit.json"),
                                                  output_dir=str(root / "prepared")))
            self.assertEqual(json.loads((root / "prepared" / "prepared_manifest.json").read_text())["rows"], 14)

    def test_rejects_tampered_or_wrong_scope_data(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); index = self.build(root)
            with (root / "part-a" / "none-100-4.jsonl").open("a") as f:
                f.write("\n")
            with self.assertRaisesRegex(ValueError, "SHA256"):
                assemble(index, root, "none", root / "x")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); index = self.build(root)
            data = json.loads(index.read_text()); data["stalled"] = {}
            index.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "planned range"):
                assemble(index, root, "none", root / "x")
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); index = self.build(root)
            data = json.loads(index.read_text()); data["units"][2]["setup"] = "none"
            data["units"][2]["unit"] = "none-500-2"; index.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "forcedSetup"):
                assemble(index, root, "none", root / "x")

    def test_union_drops_unsupported_rows_and_records_scopes(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); index = self.build(root)
            assemble(index, root, "none", root / "none")
            assemble(index, root, "high_maxhp", root / "high")
            drop = lambda row: ["hp_envelope"] if (row["sourceSeed"], row["fightIdx"]) == (101, 1) else []
            summary = union({"high_maxhp": root / "high", "none": root / "none"}, root / "union", drop)
            self.assertEqual(summary["rows"], 17)
            self.assertEqual(summary["droppedRowReasons"], {"none": {"hp_envelope": 1}, "high_maxhp": {}})
            scopes = json.loads((root / "union" / "row_scopes.json").read_text())
            self.assertEqual({k: (v["firstRow"], v["rows"]) for k, v in scopes.items()},
                             {"none": (0, 13), "high_maxhp": (13, 4)})
            manifest = json.loads((root / "union" / "corpus.jsonl.manifest.json").read_text())
            self.assertEqual(manifest["seedSpec"], {"start": 100, "count": 402})
            self.assertEqual(validate_corpus(manifest)["rows"], 17)
            seeds = [json.loads(l)["sourceSeed"] for l in (root / "union" / "corpus.jsonl").read_text().splitlines()]
            self.assertEqual(seeds, sorted(seeds))
            with self.assertRaisesRegex(ValueError, "overwrite"):
                union({"none": root / "none"}, root / "union", drop)

    def test_audit_accepts_a_union_and_quarantines_dropped_sources(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); index = self.build(root)
            assemble(index, root, "none", root / "none")
            assemble(index, root, "high_maxhp", root / "high")
            # Every row of seed 102 is dropped; seed 101 keeps one of its two rows.
            drop = lambda row: ["x"] if row["sourceSeed"] == 102 or (row["sourceSeed"], row["fightIdx"]) == (101, 1) else []
            union({"high_maxhp": root / "high", "none": root / "none"}, root / "union", drop)
            experiment.audit(argparse.Namespace(corpus_manifest=str(root / "union" / "corpus.jsonl.manifest.json"),
                                                shard_root=str(root / "union"), output_dir=str(root / "audit")))
            audit = json.loads((root / "audit" / "corpus_audit.json").read_text())
            # Requested sources are the scope ranges (100..107, 500..501), not the gap between them.
            self.assertEqual(audit["sourcesRows"]["requestedSources"], 10)
            self.assertEqual(audit["split"]["excludedQuarantinedSeeds"], [102, 105])
            self.assertEqual(audit["sourcesRows"]["totalFights"], 15)
            self.assertEqual({e["scope"] for e in audit["shards"]["entries"]}, {"none", "high_maxhp"})
            experiment.prepare(argparse.Namespace(audit=str(root / "audit" / "corpus_audit.json"),
                                                  output_dir=str(root / "prepared")))
            self.assertEqual(json.loads((root / "prepared" / "prepared_manifest.json").read_text())["rows"], 15)
            # A scope manifest changed after the union fails closed.
            scope = root / "high" / "corpus.jsonl.manifest.json"
            scope.write_text(scope.read_text() + " ")
            with self.assertRaisesRegex(ValueError, "manifest changed"):
                experiment.audit(argparse.Namespace(corpus_manifest=str(root / "union" / "corpus.jsonl.manifest.json"),
                                                    shard_root=str(root / "union"), output_dir=str(root / "audit2")))


if __name__ == "__main__":
    unittest.main()
