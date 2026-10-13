import json
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import torch

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS.parent))
from tools import ctm_pins, ctm_retrain_pins as staged  # noqa: E402


def write(path: Path, value) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(value, bytes):
        path.write_bytes(value)
    else:
        path.write_text(json.dumps(value), encoding="utf-8")
    return path


class TestCtmRetrainPins(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {}, clear=False)
        self.env.start()
        os.environ.pop(ctm_pins.ENV, None)
        ctm_pins._cache = None

    def tearDown(self):
        self.env.stop()
        ctm_pins._cache = None

    def test_stages_partition_the_declared_keys(self):
        declared = set(ctm_pins.declared_keys())
        names = [k for keys in staged.DERIVED.values() for k in keys] + list(staged.KEPT)
        self.assertEqual(len(names), len(set(names)))
        production = staged.production_values()
        covered = set()
        for name in names:
            key, _, field = name.partition("[")
            self.assertIn(key, declared)
            if field:
                self.assertIn(field.rstrip("]"), production[key])
                covered.add(name)
            else:
                covered.add(key)
        # Every key is derived or kept whole, or every field of a dict-valued key is.
        for key in declared:
            fields = {f"{key}[{f}]" for f in production[key]} if isinstance(production[key], dict) else set()
            self.assertTrue(key in covered or (fields and fields <= covered), key)
        self.assertLessEqual(set(staged.VERIFY_DATA_KEYS), declared)

    def test_chain_derives_each_stage_and_refuses_disorder(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            dom = d / "dom"
            hp, relic = write(dom / "hp.pt", b"hp"), write(dom / "relic.pt", b"relic")
            domain = dict(min=-219, max=231, classes=451)
            write(dom / "receipt.json", dict(schema="ctm_hp_domain_expansion_v1", domain=domain,
                                             outputs=dict(hp=staged.sha256(hp), relic=staged.sha256(relic)),
                                             pins={"combat_transition_composed.HP_CLASS_RANGE": [-219, 231]}))
            first = staged.init(dom, d / "pins-0.json")
            pins = first["pins"]
            self.assertEqual(pins["combat_transition_composed.HP_CLASS_RANGE"], [-219, 231])
            self.assertEqual(pins["combat_transition_composed.ARTIFACTS"]["hp"][1], staged.sha256(hp))
            # Warm starts other than hp/relic keep production.
            production = staged.production_values()
            self.assertEqual(pins["combat_transition_composed.ARTIFACTS"]["survival"],
                             production["combat_transition_composed.ARTIFACTS"]["survival"])
            self.assertIsNone(pins["combat_transition_gold_evaluate.FROZEN_COUNTS"])
            self.assertEqual(pins["combat_transition_deepset_distill.EXPECTED_HP_CLASS_COUNT"], 451)
            # Ascension re-centring is off unless requested (§443).
            self.assertIsNone(pins["combat_transition_composed.ASCENSION_CENTER"])
            a20 = staged.init(dom, d / "pins-a20.json", ascension_center=20)
            self.assertEqual(a20["pins"]["combat_transition_composed.ASCENSION_CENTER"], 20)
            # A pins file written before the key existed (#418) still checks complete.
            legacy = dict(first, pins={k: v for k, v in pins.items() if k != "combat_transition_composed.ASCENSION_CENTER"})
            write(d / "pins-legacy.json", legacy)
            staged.check(d / "pins-legacy.json")

            union = d / "union"
            data = write(union / "corpus.jsonl", b"{}\n")
            write(union / "corpus.jsonl.manifest.json", dict(forcedSetup="union", csv=dict(sha256=staged.sha256(data))))
            with self.assertRaisesRegex(ValueError, "cannot follow"):
                staged.phase1(d / "pins-0.json", d, d / "bad.json")
            staged.corpus(d / "pins-0.json", union, d / "pins-1.json")
            with self.assertRaises(FileExistsError):
                staged.corpus(d / "pins-0.json", union, d / "pins-1.json")

            p1 = d / "p1"
            split = write(p1 / "split_manifest.json", {"members": {}})
            write(p1 / "prepared.npz", b"npz")
            write(p1 / "prepared_manifest.json", dict(corpusSha256=staged.sha256(data), rows=20, counts={"0": 15, "1": 3, "2": 2}))
            att, ds = write(p1 / "attention.pt", b"a"), write(p1 / "deepsets.pt", b"d")
            write(p1 / "model_evidence.json", dict(modelArtifacts=dict(attentionSha256=staged.sha256(att),
                                                                       deepsetsSha256=staged.sha256(ds))))
            staged.phase1(d / "pins-1.json", p1, d / "pins-2.json")

            p2 = d / "p2"
            write(p2 / "prepared.npz", b"p2"); write(p2 / "target_spec.json", {})
            write(p2 / "prepared_manifest.json", dict(corpusSha256=staged.sha256(data), counts=dict(
                supported=19, supportedTrain=14, supportedValidation=3, supportedTest=2)))
            staged.phase2(d / "pins-2.json", p2, d / "pins-3.json")

            parent = d / "parent"
            for component in staged.NEAR_FULL_COMPONENTS + ("downstream",):
                name = "downstream.pt" if component == "downstream" else "component.pt"
                artifact = write(parent / f"full-union-{component}-v1" / name, component.encode())
                write(artifact.parent / "fit.json", dict(artifactSha256=staged.sha256(artifact), sourceSha="s",
                                                        trainRows=2, validationRows=1))
            tc = parent / "potion-trajectory-v2"; tc.mkdir()
            # rows: 0,1,2 TRAIN wins (2 eligible), 3 VALIDATION win (eligible, recursive graph), 4 TEST.
            np.savez_compressed(tc / "cache.npz", ids=np.arange(5), source=np.array([7, 7, 8, 9, 10]),
                                split=np.array([0, 0, 0, 1, 2]), win=np.array([1, 1, 1, 1, 1], bool))
            write(tc / "preparation.json", dict(cacheSha256=staged.sha256(tc / "cache.npz")))
            write(tc / "graphs.json", {"3": dict(rounds=2), "0": dict(rounds=1)})
            write(parent / "full-union-downstream-labels-v1" / "preparation.json", dict(sourceSha="s"))
            down = parent / "full-union-downstream-v1"
            np.savez_compressed(down / "cache.npz", observed=np.array([[1], [0], [0], [1], [1]], bool),
                                writhing=np.zeros(5, bool), dagger=np.zeros(5, bool))
            (down / "affected_rows.jsonl").write_text(json.dumps(dict(index=2)) + "\n")
            staged.near_full(d / "pins-3.json", parent, d / "pins-4.json")

            hpo = d / "hpo"
            write(hpo / "attention_tuned.pt", b"t")
            write(hpo / "attention_hpo_evidence.json", dict(winner=dict(candidate=dict(name="hp_weight_2"), selectedEpochs=11)))
            mid = staged.hpo(d / "pins-4.json", hpo, d / "pins-5.json")
            self.assertEqual(mid["pins"]["combat_transition_composed_evaluate.SPLIT"], str(split.resolve()))
            self.assertEqual(mid["pins"]["export_combat_transition_deepset_stack.SCALAR_FIT_ROWS"], 18)
            self.assertEqual(mid["pins"]["combat_transition_attention_hpo_promote.WINNER_EPOCHS"], 11)
            self.assertEqual(mid["pins"]["combat_transition_deepset_potion_specialist.RECURSIVE_VALIDATION_ROWS"], 1)
            self.assertEqual(mid["pins"]["combat_transition_deepset_downstream.TRAIN_ROWS"], 2)
            self.assertEqual(mid["pins"]["combat_transition_deepset_potion.EXPECTED"]["cache"], staged.sha256(tc / "cache.npz"))
            # A dict-valued pin keeps the production fields its later stages derive.
            self.assertEqual(mid["pins"]["combat_transition_deepset_potion.EXPECTED"]["baseline"],
                             production["combat_transition_deepset_potion.EXPECTED"]["baseline"])

            std = write(d / "std.native", staged.MAGIC + struct.pack("<II", 2, 2) + b"{}" + b"T")
            staged.control(d / "pins-5.json", std, d / "pins-6.json")
            s17 = d / "s17"
            outputs = {n: staged.sha256(write(s17 / f"teacher-{n}.npy", n.encode())) for n in ("maxHP", "HP")}
            write(s17 / "results.json", dict(counts=mid["pins"]["combat_transition_deepset_distill.EXPECTED_COUNTS"],
                                             provenance=dict(teacherOutputs=outputs)))
            staged.teachers(d / "pins-6.json", s17, d / "pins-7.json")
            s18 = d / "s18"
            student = write(s18 / "student.pt", b"s")
            write(s18 / "results.json", dict(checkpointSha256=staged.sha256(student), decision="SHARED_TRANSITION_ENCODER_REJECTED",
                                             scalarNormalization=dict(rows=2, rowIdsSha256="r"), selectedEpoch=9, experimentSha="e"))
            with self.assertRaisesRegex(ValueError, "require GO"):
                staged.distill(d / "pins-7.json", s18, d / "pins-8.json")
            write(s18 / "results.json", dict(checkpointSha256=staged.sha256(student), decision="SHARED_TRANSITION_ENCODER_GO",
                                             scalarNormalization=dict(rows=2, rowIdsSha256="r"), selectedEpoch=9, experimentSha="e"))
            staged.distill(d / "pins-7.json", s18, d / "pins-8.json")
            s19 = d / "s19"
            z = write(s19 / "z_deepset.npy", b"z"); head = write(s19 / "downstream.pt", b"ds")
            write(s19 / "representation.json", dict(candidateZSha256=staged.sha256(z), generatedRows=5))
            write(s19 / "qualification.json", dict(decision="DEEPSET_DOWNSTREAM_REJECTED",
                                                   candidate=dict(checkpointSha256=staged.sha256(head))))
            with self.assertRaisesRegex(ValueError, "require GO"):
                staged.downstream(d / "pins-8.json", s19, d / "pins-9.json")
            failure = "cards singleton exact-label accuracy drop exceeds 0.5pp"
            rejected = write(s19 / "qualification.json", dict(decision="DEEPSET_DOWNSTREAM_REJECTED", finiteAndLegal=True,
                                                              failures=[failure], candidate=dict(checkpointSha256=staged.sha256(head))))
            override = dict(schema="ctm_gate_override_v1", stage="downstream", qualificationSha256=staged.sha256(rejected),
                            failures=[failure], approval="test", reason="noise", evidence=dict(ci95=[-0.02, 0.01]))
            for change, message in ((dict(qualificationSha256="x"), "does not bind"), (dict(failures=[]), "exactly the one"),
                                    (dict(reason=""), "approval and reason"), (dict(evidence={}), "evidence"),
                                    (dict(stage="potion"), "downstream stage")):
                with self.assertRaisesRegex(ValueError, message):
                    staged.downstream(d / "pins-8.json", s19, d / "pins-9.json", write(d / "override.json", dict(override, **change)))
            def refused(qualification, message):
                written = write(s19 / "qualification.json", dict(qualification, candidate=dict(checkpointSha256=staged.sha256(head))))
                with self.assertRaisesRegex(ValueError, message):
                    staged.downstream(d / "pins-8.json", s19, d / "pins-9.json", write(d / "override.json", dict(
                        override, qualificationSha256=staged.sha256(written), failures=qualification["failures"])))
            two = [failure, "relics singleton exact-label accuracy drop exceeds 0.5pp"]
            refused(dict(decision="DEEPSET_DOWNSTREAM_REJECTED", finiteAndLegal=True, failures=two), "exactly the one")
            refused(dict(decision="DEEPSET_DOWNSTREAM_GO", finiteAndLegal=True, failures=[failure]), "finite/legal")
            refused(dict(decision="DEEPSET_DOWNSTREAM_REJECTED", finiteAndLegal=False, failures=[failure]), "finite/legal")
            nll = write(s19 / "qualification.json", dict(decision="DEEPSET_DOWNSTREAM_REJECTED", finiteAndLegal=True,
                                                          failures=["joint NLL relative degradation exceeds 2%"],
                                                          candidate=dict(checkpointSha256=staged.sha256(head))))
            with self.assertRaisesRegex(ValueError, "only singleton"):
                staged.downstream(d / "pins-8.json", s19, d / "pins-9.json", write(d / "override.json", dict(
                    override, qualificationSha256=staged.sha256(nll), failures=["joint NLL relative degradation exceeds 2%"])))
            rejected = write(s19 / "qualification.json", dict(decision="DEEPSET_DOWNSTREAM_REJECTED", finiteAndLegal=True,
                                                              failures=[failure], candidate=dict(checkpointSha256=staged.sha256(head))))
            accepted = staged.downstream(d / "pins-8.json", s19, d / "pins-9-override.json",
                                         write(d / "override.json", override))
            self.assertEqual(accepted["stages"][-1]["inputs"]["override"], staged.sha256(d / "override.json"))
            write(s19 / "qualification.json", dict(decision="DEEPSET_DOWNSTREAM_GO", candidate=dict(checkpointSha256="other")))
            with self.assertRaisesRegex(ValueError, "qualified candidate"):
                staged.downstream(d / "pins-8.json", s19, d / "pins-9.json")
            write(s19 / "qualification.json", dict(decision="DEEPSET_DOWNSTREAM_GO",
                                                   candidate=dict(checkpointSha256=staged.sha256(head))))
            staged.downstream(d / "pins-8.json", s19, d / "pins-9.json")
            s20 = d / "s20"
            for name in ("A.pt", "B.pt"):
                write(s20 / name, name.encode())
            write(s20 / "results.json", {})
            staged.potion(d / "pins-9.json", s20, d / "pins-10.json")
            s21 = d / "s21"; s21.mkdir()
            torch.save(dict(selectedEpoch=21), s21 / "C.pt"); write(s21 / "results.json", {})
            staged.specialist(d / "pins-10.json", s21, d / "pins-11.json")
            fast = write(d / "fast.native", staged.MAGIC + struct.pack("<II", 2, 2) + b"{}" + b"PAYLOAD")
            last = staged.fast(d / "pins-11.json", fast, d / "pins-12.json")
            self.assertEqual(last["pending"], [])
            self.assertEqual(last["pins"]["package_deepsets_lizard_artifact.FAST_PAYLOAD_SHA256"],
                             staged.hashlib.sha256(b"PAYLOAD").hexdigest())
            self.assertEqual(last["pins"]["export_combat_transition_deepset_stack.POTION_SELECTED_EPOCH"], 21)
            self.assertEqual(last["pins"]["combat_transition_deepset_potion_specialist.EXPECTED"]["encoder"],
                             staged.sha256(student))
            self.assertEqual(staged.check(d / "pins-12.json", d / "pins-3.json")["stages"], list(staged.STAGES))

            # The final file is a valid STS_CTM_PINS file for every declared key.
            os.environ[ctm_pins.ENV] = str(d / "pins-5.json")
            self.assertEqual(ctm_pins.value("combat_transition_rng_audit.FROZEN_SHA", None), staged.sha256(data))

            # verify_data keys may not change after phase2.
            changed = json.loads((d / "pins-5.json").read_text())
            changed["pins"]["combat_transition_composed_evaluate.PREPARED"] = "/elsewhere"
            write(d / "pins-6.json", changed)
            with self.assertRaisesRegex(ValueError, "verify_data"):
                staged.check(d / "pins-6.json", d / "pins-3.json")


    def test_trajectory_graphs_load_past_the_pins_receipt(self):
        # json_dump stamps every dict under pins, including the row-id map graphs.json.
        from tools import combat_transition_potion_trajectory_evaluate as trajectory
        graph = dict(inventories=[[1, 0, 0, 0, 0]], edges=[[0, 0, 1]], target_edges=[[0, 1]],
                     generation_log_prior=-1.5, rounds=1)
        with tempfile.TemporaryDirectory() as d:
            path = write(Path(d) / "graphs.json", {"7": graph, "ctmPinsSha256": "0" * 64})
            graphs = trajectory.load_graphs(path)
        self.assertEqual(list(graphs), [7])
        self.assertEqual(graphs[7].rounds, 1)


if __name__ == "__main__":
    unittest.main()
