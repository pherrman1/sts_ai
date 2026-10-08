import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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
        derived = [k for keys in staged.DERIVED.values() for k in keys] + list(staged.DEEPSETS)
        self.assertEqual(len(derived), len(set(derived)))
        self.assertLessEqual(set(derived), declared)
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
                write(artifact.parent / "fit.json", dict(artifactSha256=staged.sha256(artifact)))
            staged.near_full(d / "pins-3.json", parent, d / "pins-4.json")

            hpo = d / "hpo"
            write(hpo / "attention_tuned.pt", b"t")
            write(hpo / "attention_hpo_evidence.json", dict(winner=dict(candidate=dict(name="hp_weight_2"), selectedEpochs=11)))
            last = staged.hpo(d / "pins-4.json", hpo, d / "pins-5.json")
            self.assertEqual(sorted(last["pending"]), sorted(staged.DEEPSETS))
            self.assertEqual(last["pins"]["combat_transition_composed_evaluate.SPLIT"], str(split.resolve()))
            self.assertEqual(last["pins"]["export_combat_transition_deepset_stack.SCALAR_FIT_ROWS"], 18)
            self.assertEqual(last["pins"]["combat_transition_attention_hpo_promote.WINNER_EPOCHS"], 11)
            self.assertEqual(staged.check(d / "pins-5.json", d / "pins-3.json")["stages"], list(staged.STAGES))

            # The final file is a valid STS_CTM_PINS file for every declared key.
            os.environ[ctm_pins.ENV] = str(d / "pins-5.json")
            self.assertEqual(ctm_pins.value("combat_transition_rng_audit.FROZEN_SHA", None), staged.sha256(data))

            # verify_data keys may not change after phase2.
            changed = json.loads((d / "pins-5.json").read_text())
            changed["pins"]["combat_transition_composed_evaluate.PREPARED"] = "/elsewhere"
            write(d / "pins-6.json", changed)
            with self.assertRaisesRegex(ValueError, "verify_data"):
                staged.check(d / "pins-6.json", d / "pins-3.json")


if __name__ == "__main__":
    unittest.main()
