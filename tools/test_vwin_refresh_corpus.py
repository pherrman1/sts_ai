"""Synthetic corpus tests reuse the strict bundle and combat-teacher fixtures."""
from __future__ import annotations

import copy
import csv
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import test_vwin_refresh_contract as fixtures
from tools.test_combat_transition_contract import teacher as make_teacher
from tools.vwin_refresh_contract import ContractError, OUTPUTS, _sha256, validate_bundle
from tools.vwin_refresh_corpus import IDENTITY_FIELDS, SCHEMA, main, validate_corpus


class CorpusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.paths = [self.make_bundle("old", fixtures.SEED, "a"),
                      self.make_bundle("fixed", fixtures.SEED + 1, "b")]
        self.index_path = self.root / "corpus.json"
        self.index = {"schemaVersion": SCHEMA, "sourceSeeds": [fixtures.SEED, fixtures.SEED + 1],
                      "allowedProducers": [], "components": []}
        for path in self.paths:
            manifest = json.loads(path.read_text())
            self.index["allowedProducers"].append({
                **{k: manifest[k] for k in IDENTITY_FIELDS},
                "teacherManifest": str((path.parent / 'teacher.json').relative_to(self.root))})
            self.index["components"].append({"manifest": str(path.relative_to(self.root)),
                                              "sha256": _sha256(path)})
        self.save_index()

    def make_bundle(self, name, seed, identity):
        directory = self.root / name
        directory.mkdir()
        with patch.object(fixtures, "SEED", seed):
            path = fixtures._make_bundle(directory)
            fixtures._add_decision_sink(path)
        manifest = json.loads(path.read_text())
        teacher = make_teacher()
        teacher.update(git_sha=identity * 40, executable_sha256=identity * 64,
                       teacher_id=f"teacher-{name}")
        teacher["environment"]["STS_EXECUTABLE_GIT_SHA"] = teacher["git_sha"]
        teacher["ooc_policy"] = {
            "schema_version": "runFullRunOOC_policy_v1", "policy_chain": "runFullRunOOC",
            "native_ooc": True, "flags": {"collect_keys": False}, "parameters": {"strategic_margin": 1.0},
            "model_artifacts": [{"path": "v_win.txt", "role": "win", "sha256": "c" * 64}]}
        teacher_path = directory / "teacher.json"
        teacher_path.write_text(json.dumps(teacher))
        manifest.update(producerGitSha=teacher["git_sha"],
                        producerExecutableSha256=teacher["executable_sha256"],
                        teacherId=teacher["teacher_id"], teacherManifestSha256=_sha256(teacher_path),
                        teacherPath=str(teacher_path), combatTeacher=teacher,
                        policy=copy.deepcopy(teacher["ooc_policy"]),
                        sampling={"schema": "outcome_blind_reservoir_per_type_v1", "samplesPerType": 1,
                                  "optionCap": 6, "capRule": "chosen_plus_five_sha256_ranked",
                                  "capDomain": "vwin-option-cap-334-v1:{seed}:{decisionIdx}:{optionKey}"})
        manifest["decisionSink"].update(label="trajectory_finalWon",
            screenContentsEncoding="canonical_json_public_state_v1",
            candidatesEncoding="canonical_semantic_keys_with_chosen_v1",
            decisionIdxJoin="legacy_decisions_csv_or_minus_one_for_capture_only")
        for table in manifest["outputs"]:
            p = Path(str(path).replace(".manifest.json", OUTPUTS[table]))
            with p.open(newline="") as f:
                reader = csv.DictReader(f)
                header, rows = reader.fieldnames, list(reader)
            for row in rows:
                if "teacherId" in row:
                    row["teacherId"] = teacher["teacher_id"]
            fixtures._write_csv(p, header, rows)
            manifest["outputs"][table] = _sha256(p)
        sink = manifest["decisionSink"]
        size = Path(str(path).replace(".manifest.json", ".decision.csv")).stat().st_size
        sink.update(bytes=size, bytesPerRow=size / sink["rows"], projectedA2Bytes=size * 4096)
        path.write_text(json.dumps(manifest))
        validate_bundle(path)
        return path

    def save_index(self):
        self.index_path.write_text(json.dumps(self.index))

    def mutate(self, change, number=1):
        path = self.paths[number]
        manifest = json.loads(path.read_text())
        change(manifest)
        path.write_text(json.dumps(manifest))
        self.index["components"][number]["sha256"] = _sha256(path)
        self.save_index()

    def mutate_teacher(self, change):
        path = self.paths[1].parent / "teacher.json"
        teacher = json.loads(path.read_text())
        change(teacher)
        path.write_text(json.dumps(teacher))
        digest = _sha256(path)
        self.index["allowedProducers"][1]["teacherManifestSha256"] = digest
        self.mutate(lambda m: m.update(combatTeacher=teacher, policy=teacher["ooc_policy"],
                                      teacherManifestSha256=digest))

    def test_mixed_provenance_and_table_paths(self):
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        corpus = validate_corpus(self.index_path)
        self.assertEqual(corpus.manifests(), tuple(self.paths))
        tables = list(corpus.tables("map.csv"))
        self.assertEqual(len(tables), 2)
        self.assertEqual(len({t.component.producer.identity for t in tables}), 2)
        for table, manifest in zip(tables, self.paths):
            self.assertEqual(table.component.manifest_path, manifest)
            self.assertEqual(table.path, manifest.with_name("pilot.map.csv"))
            self.assertEqual(table.sha256, _sha256(table.path))
        self.assertEqual(before, {p: p.read_bytes() for p in before})
        self.assertEqual(main([str(self.index_path)]), 0)
        with self.assertRaisesRegex(ContractError, "unknown table"):
            list(corpus.tables("bogus.csv"))

    def test_relative_index_can_move_with_evidence(self):
        destination = self.root / "moved"
        destination.mkdir()
        for name in ("old", "fixed"):
            shutil.copytree(self.root / name, destination / name)
        shutil.copy(self.index_path, destination / "corpus.json")
        # Historical teacherPath strings stay untouched, and are not used to locate teachers.
        shutil.rmtree(self.root / "old")
        shutil.rmtree(self.root / "fixed")
        corpus = validate_corpus(destination / "corpus.json")
        self.assertTrue(all(destination in t.path.parents for t in corpus.tables("decision.csv")))

    def test_duplicate_source_seed(self):
        self.index["components"].append(self.index["components"][0])
        self.save_index()
        with self.assertRaisesRegex(ContractError, "duplicate source seed"):
            validate_corpus(self.index_path)

    def test_missing_extra_and_substituted_seeds(self):
        for seeds in ([fixtures.SEED, fixtures.SEED + 1, fixtures.SEED + 2],
                      [fixtures.SEED], [fixtures.SEED, fixtures.SEED + 2]):
            with self.subTest(seeds=seeds):
                self.index["sourceSeeds"] = seeds
                self.save_index()
                with self.assertRaisesRegex(ContractError, "source cohort mismatch"):
                    validate_corpus(self.index_path)

    def test_unlisted_identity(self):
        for field in IDENTITY_FIELDS:
            with self.subTest(field=field):
                original = self.paths[1].read_text()
                self.mutate(lambda m: m.update({field: "d" * (40 if field == "producerGitSha" else 64)}))
                with self.assertRaisesRegex(ContractError, "unlisted producer identity|teacherId"):
                    validate_corpus(self.index_path)
                self.paths[1].write_text(original)

    def test_invalid_component_uses_existing_validator(self):
        self.mutate(lambda m: m["outputs"].update({"map.csv": "0" * 64}))
        with patch("tools.vwin_refresh_corpus.validate_bundle", wraps=validate_bundle) as validator:
            with self.assertRaisesRegex(ContractError, "map.csv: SHA-256 mismatch"):
                validate_corpus(self.index_path)
            self.assertEqual(validator.call_count, 2)

    def test_manifest_and_teacher_hashes(self):
        for key, container in (("sha256", self.index["components"][0]),
                               ("teacherManifestSha256", self.index["allowedProducers"][0])):
            with self.subTest(key=key):
                original = container[key]
                container[key] = "0" * 64
                self.save_index()
                with self.assertRaisesRegex(ContractError, "SHA-256 mismatch"):
                    validate_corpus(self.index_path)
                container[key] = original

    def test_scientific_mismatches_in_individually_valid_bundles(self):
        changes = [
            lambda m: m["stateFeatures"].update(schema="different"),
            lambda m: m["split"].update(additionalRule="different"),
            lambda m: m["sampling"].update(samplesPerType=2),
            lambda m: m["sampling"].update(optionCap=5),
            lambda m: m["branchParity"].update(percent=99),
            lambda m: m["seedSpec"].update(ascension=1),
            lambda m: m["decisionSink"].update(label="different"),
            lambda m: m["decisionSink"].update(candidatesEncoding="different"),
            lambda m: m.update(targetSemantics="different"),
        ]
        original = self.paths[1].read_text()
        for change in changes:
            with self.subTest(change=changes.index(change)):
                self.paths[1].write_text(original)
                self.mutate(change)
                validate_bundle(self.paths[1])
                with self.assertRaisesRegex(ContractError, "scientific semantics mismatch"):
                    validate_corpus(self.index_path)

    def test_feature_header_mismatch(self):
        original = fixtures.FEATURES
        renamed = ["different_feature", *original[1:]]
        with patch.object(fixtures, "FEATURES", renamed), patch.object(fixtures, "FEATURE_HEADER", ",".join(renamed)):
            path = self.make_bundle("renamed", fixtures.SEED + 2, "a")
        self.index["allowedProducers"].append({
            **{k: json.loads(path.read_text())[k] for k in IDENTITY_FIELDS},
            "teacherManifest": "renamed/teacher.json"})
        self.index["components"].append({"manifest": "renamed/pilot.manifest.json", "sha256": _sha256(path)})
        self.index["sourceSeeds"].append(fixtures.SEED + 2)
        self.save_index()
        with self.assertRaisesRegex(ContractError, "scientific semantics mismatch"):
            validate_corpus(self.index_path)

    def test_teacher_policy_model_and_environment_semantics(self):
        changes = [lambda t: t["ooc_policy"]["flags"].update(collect_keys=True),
                   lambda t: t["ooc_policy"]["model_artifacts"][0].update(sha256="d" * 64),
                   lambda t: t["model_artifacts"][0].update(sha256="d" * 64),
                   lambda t: t["environment"].update(UNRELATED="changed"),
                   lambda t: t.update(additionalTeacherRule="changed")]
        teacher_path = self.paths[1].parent / "teacher.json"
        original = teacher_path.read_text()
        for change in changes:
            with self.subTest(change=changes.index(change)):
                teacher_path.write_text(original)
                self.mutate_teacher(change)
                validate_bundle(self.paths[1])
                with self.assertRaisesRegex(ContractError, "teacher scientific semantics mismatch"):
                    validate_corpus(self.index_path)

    def test_exact10k_and_project_fair_required(self):
        teacher_path = self.paths[1].parent / "teacher.json"
        original = teacher_path.read_text()
        for change, error in (
                (lambda t: t["search_configuration"].update(simulation_budgets=[9999]), "simulation_budgets"),
                (lambda t: t.update(rng_regime="known_rng"), "project_fair"),
                (lambda t: t.update(combat_backend="other"), "native_silver")):
            with self.subTest(error=error):
                teacher_path.write_text(original)
                self.mutate_teacher(change)
                with self.assertRaisesRegex(ContractError, error):
                    validate_corpus(self.index_path)

    def test_combat_target_header_mismatch(self):
        path = self.paths[1].with_name("pilot.combat.csv")
        with path.open(newline="") as stream:
            reader = csv.DictReader(stream)
            header, rows = reader.fieldnames, list(reader)
        for row in rows:
            row["newTarget"] = "0"
        fixtures._write_csv(path, header + ["newTarget"], rows)
        self.mutate(lambda m: m["outputs"].update({"combat.csv": _sha256(path)}))
        validate_bundle(self.paths[1])
        with self.assertRaisesRegex(ContractError, "scientific semantics mismatch"):
            validate_corpus(self.index_path)

    def test_sink_presence_must_agree(self):
        self.mutate(lambda m: (m.pop("decisionSink"), m["outputs"].pop("decision.csv")))
        validate_bundle(self.paths[1])
        with self.assertRaisesRegex(ContractError, "scientific semantics mismatch"):
            validate_corpus(self.index_path)

    def test_only_documented_teacher_binding_difference_passes(self):
        a, b = [json.loads((p.parent / "teacher.json").read_text()) for p in self.paths]
        for teacher in (a, b):
            for key in ("teacher_id", "git_sha", "executable_sha256"):
                teacher.pop(key)
            teacher["environment"].pop("STS_EXECUTABLE_GIT_SHA")
        self.assertEqual(a, b)
        validate_corpus(self.index_path)

    def test_wrong_executable_binding_rejected(self):
        self.mutate_teacher(lambda t: t["environment"].update(STS_EXECUTABLE_GIT_SHA="a" * 40))
        with self.assertRaisesRegex(ContractError, "teacher executable binding"):
            validate_corpus(self.index_path)

    def test_effective_policy_and_embedded_teacher_must_match(self):
        original = self.paths[1].read_text()
        for field in ("policy", "combatTeacher"):
            with self.subTest(field=field):
                self.paths[1].write_text(original)
                self.mutate(lambda m: m[field].update(unrecorded=True))
                with self.assertRaisesRegex(ContractError, "differs from"):
                    validate_corpus(self.index_path)

    def test_under_specified_semantics_rejected(self):
        for field in ("sampling", "combatTeacher", "policy"):
            original = self.paths[1].read_text()
            self.mutate(lambda m: m.pop(field))
            with self.assertRaises(ContractError):
                validate_corpus(self.index_path)
            self.paths[1].write_text(original)

    def test_partial_source_not_admitted(self):
        path = self.paths[1]
        def table(name, change):
            p = Path(str(path).replace(".manifest.json", OUTPUTS[name]))
            with p.open(newline="") as stream:
                reader = csv.DictReader(stream)
                header, rows = reader.fieldnames, list(reader)
            change(rows)
            fixtures._write_csv(p, header, rows)
            self.mutate(lambda m: m["outputs"].update({name: _sha256(p)}))
        self.mutate(lambda m: (m.pop("decisionSink"), m["outputs"].pop("decision.csv")))
        def runouts(rows):
            rows[0].update(finalOutcome="UNDECIDED", finalWon="-1", trajectoryComplete="0", trajectoryValid="0")
            rows[1]["branchParity"] = "NA"
        table("runout.csv", runouts)
        table("branches.csv", lambda rows: rows[0].update(valid="0"))
        def change(m):
            m["branchParity"]["checks"] = 0
            m["integrity"].update(chosenReplayChecks=0, validSources=0, completedSources=0)
            m["branchRows"][0]["chosenReplayParity"] = None
        self.mutate(change)
        validate_bundle(path)
        with self.assertRaisesRegex(ContractError, "partial or invalid source cohort"):
            validate_corpus(self.index_path)

    def test_bad_index_schema(self):
        for field, value in (("sourceSeeds", [True]), ("sourceSeeds", [1, 1]),
                             ("components", []), ("allowedProducers", []),
                             ("schemaVersion", "wrong")):
            original = copy.deepcopy(self.index)
            self.index[field] = value
            self.save_index()
            with self.assertRaises(ContractError):
                validate_corpus(self.index_path)
            self.index = original


if __name__ == "__main__":
    unittest.main()
