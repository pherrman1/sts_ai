#!/usr/bin/env python3
"""Synthetic-only contract/math tests. Never invokes one_combat or a game seed."""
import copy
import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

REPO = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


a = module("a20_analysis", REPO / "tools/analyze_a20_teachers.py")
runner = module("a20_runner", REPO / "docs/experiments/evidence/a20_teacher_comparison_20261014/run_pilot.py")


def dump(path, value):
    Path(path).write_text(json.dumps(value))


def csv_write(path, columns, rows):
    with Path(path).open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


class Fixture:
    """A clearly synthetic source panel with all custody paths in a tempdir."""
    def __init__(self, root):
        self.root = root
        self.repo = root / "repo"
        packet = self.repo / "docs/experiments/evidence/a20_teacher_comparison_20261014"
        packet.mkdir(parents=True)
        (self.repo / "tools").mkdir()
        paths = [root / "one_combat", root / "prior.txt", root / "fast.native", root / "standard.native",
                 self.repo / "tools/seed_guard.sh", packet / a.RUNNER_FILE, packet / a.PROTOCOL_FILE, packet / "PROTOCOL.md", packet / "ANALYSIS-CONTRACT.md"]
        for path in paths:
            path.write_text("SYNTHETIC FIXTURE ONLY " + path.name)
        self.identity = {"candidateId": "pathb-a20", "synthetic": True}
        dump(root / "manifest.json", self.identity)
        self.ctm_hashes = {name: a.sha(root / name) for name in ("fast.native", "standard.native", "manifest.json")}
        env = {"OMP_NUM_THREADS": "1", "OMP_DYNAMIC": "FALSE", "STS_FAIR": "1", "STS_SEARCHER3": "0",
               "STS_SILVER_SEARCH": "1", "STS_SILVER_EXACT_ROOT_BUDGETS": "1", "STS_SILVER_ADAPTIVE": "0",
               "STS_SILVER_LEARNED_STOP": "0", "STS_SILVER_LOOP_GUARD": "0", "STS_SILVER_ROOT_PRIOR_WEIGHT": "400",
               "STS_CTMSILVER_ARMSET": a.ARM_SET, "STS_OOC_MCTS": "0", "STS_COLLECT_KEYS": "0",
               "STS_STOP_AFTER_ACT": "3", "STS_EXECUTABLE_GIT_SHA": "a" * 40,
               "STS_CTMSILVER_CANDIDATE_FAST": str(root / "fast.native"),
               "STS_CTMSILVER_CANDIDATE_STANDARD": str(root / "standard.native"),
               "STS_CTM_RESEARCH_CANDIDATE_MANIFEST": str(root / "manifest.json"),
               "STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256": self.ctm_hashes["manifest.json"],
               "STS_SILVER_ROOT_PRIOR": str(root / "prior.txt"), "STS_CTMSILVER_MLP_PRIOR": str(root / "prior.txt")}
        self.teacher = {"git_sha": "a" * 40, "executable_sha256": a.sha(root / "one_combat"),
                        "environment": env, "search_configuration": {"simulation_budgets": [10000]},
                        "combat_backend": "native_silver", "rng_regime": "project_fair", "model_artifacts": [],
                        "ooc_policy": {"model_artifacts": []}, "teacher_id": "synthetic-teacher"}
        dump(root / "teacher.json", self.teacher)
        self.freeze = {"schemaVersion": a.FREEZE_SCHEMA, "producerGitSha": "a" * 40,
                       "repository": str(self.repo), "binary": str(root / "one_combat"),
                       "binarySha256": a.sha(root / "one_combat"), "teacher": str(root / "teacher.json"),
                       "environment": env, "canarySeed": a.CANARY, "cohortSeeds": a.COHORT,
                       "outputs": {str(seed): str(root / ("canary" if seed == a.CANARY else f"s{seed}"))
                                   for seed in (a.CANARY, *a.COHORT)},
                       "resourceLimits": a.RESOURCE_LIMITS,
                       "priorIdentity": {"sha256": a.sha(root / "prior.txt"), "generation": 5,
                                         "source": "synthetic://completed-fixture", "treeMinVisits": 8, "weight": 400, "rootBonus": True},
                       "ctmIdentity": self.ctm_hashes,
                       "arms": [{"name": name, "budget": budget, "prior": prior, "replicates": a.REPLICATES}
                                for name, (budget, prior) in a.ARM_CONFIG.items()], "buildCommands": [],
                       "artifactFiles": {str(path): a.sha(path) for path in
                                         [*paths, root / "manifest.json", root / "teacher.json", REPO / "tools/analyze_a20_teachers.py"]}}
        dump(root / "freeze.json", self.freeze)
        self.freeze_hash = a.sha(root / "freeze.json")

    def prefix(self, seed):
        return self.freeze["outputs"][str(seed)]

    def source(self, seed):
        prefix = self.prefix(seed)
        states, arms, samples = [], [], []

        def sample(sid, name, k, hp=40, dead=False):
            return {"stateId": sid, "forecaster": name, "k": str(k), "outcome": "DEATH" if dead else "VICTORY",
                    "curHp": str(hp), "maxHp": "80", "gold": "99", "potionCount": "1", "potions": "1;0;0;0;0",
                    "relics": "1:0", "deckHash": "abcd", "smokeBombUsed": "0", "stolenGold": "0"}

        for fight, room, support in ((0, "NORMAL", True), (2, "ELITE", False)):
            sid = f"s{seed}-f{fight}"
            state = {"stateId": sid, "sourceSeed": str(seed), "fightIdx": str(fight), "act": "1", "floor": str(fight + 1),
                     "roomClass": room, "encounter": "SYNTHETIC", "preHp": "70", "preMaxHp": "80", "prePotions": "1",
                     "sourceWon": "1", "sourceTerminalHp": "34", "sourceValid": "1", "ctmSupported": str(int(support)),
                     "ctmReason": "supported" if support else "synthetic_support_miss",
                     "ctmPDeath": "0.5" if support else "-1", "ctmMeanHpWin": "80" if support else "-1",
                     "ctmExpectedHp": "40" if support else "-1", "ctmForecastCpuUs": "10" if support else "-1",
                     "ctmSampleCpuUs": "20" if support else "-1", "sourcePostHp": "80", "sourceRawHp": "40",
                     "sourceRawMaxHp": "80", "sourceRawOutcome": "VICTORY", "sourceRawCaptureCount": "1"}
            states.append(state)
            samples.append(sample(sid, "source", 0))
            if not support:
                continue
            for k in range(32):
                samples.append(sample(sid, "ctm", k, hp=80 if k % 2 else 0, dead=k % 2 == 0))
            for name, (budget, prior) in {"control": (10000, False), **a.ARM_CONFIG}.items():
                for k in range(1 if name == "control" else a.REPLICATES):
                    hp = 40 if name == "control" else 10 * (k % 4 + 1) + (5 if prior else 0)
                    samples.append(sample(sid, name, k, hp))
                    redraw = a.replicate_seed(seed, fight, k, 0xC0FFEE07) if name != "control" else 0
                    planner = a.replicate_seed(seed, fight, k, 0x91A77E2) if name != "control" else 0
                    arms.append({"stateId": sid, "sourceSeed": str(seed), "fightIdx": str(fight), "arm": name, "k": str(k),
                                 "budget": str(budget), "prior": str(int(prior)), "redraw": str(int(name != "control")),
                                 "redrawSeed": str(redraw), "won": "1", "terminalHp": "34" if name == "control" else str(hp - 6),
                                 "cpuSeconds": ".01", "simulations": str(budget * 2), "decisions": "2", "valid": "1",
                                 "controlReplayMatch": "1" if name == "control" else "-1", "quarantineReason": "",
                                 "treeMinVisits": "8" if prior else "0", "plannerSeed": str(planner), "rawHp": str(hp),
                                 "rawMaxHp": "80", "rawOutcome": "VICTORY", "rawCaptureCount": "1",
                                 "battleSeed": str(a.mt19937_64_first(redraw) if name != "control" else seed)})
        for name, cols, rows in (("states", a.STATE_COLUMNS, states), ("arms", a.ARM_COLUMNS, arms), ("samples", a.SAMPLE_COLUMNS, samples)):
            csv_write(prefix + f".{name}.csv", cols, rows)
        env = self.freeze["environment"]
        manifest = {"schemaVersion": a.RUNTIME_SCHEMA, "producerGitSha": "a" * 40,
                    "producerExecutableSha256": self.freeze["binarySha256"], "teacherId": self.teacher["teacher_id"],
                    "teacherManifestSha256": a.sha(self.freeze["teacher"]), "combatTeacher": self.teacher,
                    "policy": self.teacher["ooc_policy"], "seedSpec": {"start": seed, "count": 1, "ascension": 20},
                    "rootPrior": {"path": env["STS_SILVER_ROOT_PRIOR"], "sha256": self.freeze["priorIdentity"]["sha256"], "weight": 400},
                    "ctm": {"fast": env["STS_CTMSILVER_CANDIDATE_FAST"], "fastSha256": self.ctm_hashes["fast.native"],
                            "standard": env["STS_CTMSILVER_CANDIDATE_STANDARD"], "standardSha256": self.ctm_hashes["standard.native"],
                            "activeLizard": True, "timingReps": 20, "forecastSamples": 32, "candidateId": "pathb-a20",
                            "manifestPath": env["STS_CTM_RESEARCH_CANDIDATE_MANIFEST"], "manifestSha256": self.ctm_hashes["manifest.json"],
                            "loadedIdentity": self.identity}, "redraw": a.REDRAW, "ctmOnly": False, "candidate": None,
                    "arms": a.expected_runtime_arms(self.freeze), "armSet": a.ARM_SET,
                    "sources": [{"seed": seed, "complete": True, "valid": True, "fights": 3, "finalFloor": 4, "won": False,
                                 "captured": [{"stateId": f"s{seed}-f{i}", "fightIdx": i, "act": 1,
                                               "roomClass": "ELITE" if i == 2 else "NORMAL", "floor": i + 1} for i in range(3)],
                                 "capturedCount": 3, "selectedStateIds": [f"s{seed}-f0", f"s{seed}-f2"], "selectedCount": 2,
                                 "finalHp": 0, "finalOutcome": "DEATH", "fatalFailure": False, "simulatorHealthFailures": 0, "invalidCombatRows": 0}],
                    "integrity": {"completeSources": 1, "validSources": 1, "states": 2, "ctmSupported": 1, "controlReplayMatches": 1,
                                  "controlReplayMismatches": 0, "invalidArmRows": 0, "capturedStates": 3, "selectedStates": 2,
                                  "ctmUnsupported": 1, "unsupportedReasons": {"synthetic_support_miss": 1}},
                    "outputs": {key: value for name in ("states", "arms", "samples") for key, value in
                                ((name + "Path", prefix + f".{name}.csv"), (name + "Sha256", a.sha(prefix + f".{name}.csv")))},
                    "producerExecutablePath": self.freeze["binary"], "teacherPath": self.freeze["teacher"],
                    "selection": a.SELECTION, "redrawKernel": a.REDRAW_KERNEL, "sourceControl": a.SOURCE_CONTROL, "environment": env}
        progress, elapsed = [], 0.

        def event(name, **fields):
            nonlocal elapsed
            elapsed += .01
            progress.append({"event": name, "sourceSeed": seed, "elapsedCpuSeconds": elapsed, **fields})

        event("source_start")
        event("trajectory_complete", capturedFights=3, finalFloor=4, valid=True)
        for state in states:
            sid = state["stateId"]
            event("state_start", stateId=sid, fightIdx=int(state["fightIdx"]), act=1,
                  floor=int(state["floor"]), roomClass=state["roomClass"], encounter="SYNTHETIC")
            event("ctm_complete", stateId=sid, supported=state["ctmSupported"] == "1", phaseCpuSeconds=.001)
            for row in (r for r in arms if r["stateId"] == sid):
                identity = {"stateId": sid, "arm": row["arm"], "k": int(row["k"]), "budget": int(row["budget"])}
                event("arm_start", **identity)
                event("arm_complete", **identity, combatCpuSeconds=.01, phaseCpuSeconds=.01,
                      decisions=int(row["decisions"]), simulations=int(row["simulations"]), valid=True)
            event("state_complete", stateId=sid)
        event("source_complete", selectedStates=len(states))
        Path(prefix + ".progress.jsonl").write_text("".join(json.dumps(row) + "\n" for row in progress))
        manifest["outputs"].update(progressPath=prefix + ".progress.jsonl",
                                   progressSha256=a.sha(prefix + ".progress.jsonl"))
        dump(prefix + ".manifest.json", manifest)
        argv = ["bash", str(self.repo / "tools/seed_guard.sh"), self.freeze["binary"], "ctmsilvergen", "1", "20", prefix,
                str(seed), self.freeze["teacher"], str(a.REPLICATES)]
        dump(prefix + ".receipt.json", {"returncode": 0, "cpuSeconds": 1. if a.REPLICATES == 4 else 3., "wallSeconds": 4., "timedOut": False,
                                        "argv": argv, "seed": seed, "binarySha256": self.freeze["binarySha256"], "freezeSha256": self.freeze_hash})
        dump(prefix + ".started.json", {"argv": argv, "freezeSha256": self.freeze_hash})
        Path(prefix + ".log").write_text("SYNTHETIC ONLY\n")
        return Path(prefix)

    def phase(self, name):
        dump(self.root / ("phase-" + name + ".started.json"), {"freezeSha256": self.freeze_hash})

    def refresh_csv_hash(self, seed, name):
        path = self.prefix(seed) + ".manifest.json"
        manifest = a.read_json(path)
        manifest["outputs"][name + "Sha256"] = a.sha(self.prefix(seed) + f".{name}.csv")
        dump(path, manifest)


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="synthetic-a20-analysis-")
        self.addCleanup(self.temp.cleanup)
        self.f = Fixture(Path(self.temp.name))
        self.patch = mock.patch.object(a, "CTM_HASHES", self.f.ctm_hashes)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.f.source(a.CANARY)
        self.f.phase("canary")

    def analyze_canary(self):
        return a.analyze(self.f.root / "freeze.json", [self.f.prefix(a.CANARY)], True)

    def test_full_canary_and_metrics(self):
        report = self.analyze_canary()
        self.assertEqual(report["verdict"], "CANARY_VALID")
        self.assertEqual(report["coverage"]["unsupportedReasons"], {"synthetic_support_miss": 1})
        state = report["perState"][0]
        self.assertEqual(state["forecast"]["ctm"]["deathBrier"], .25)
        self.assertEqual(state["forecast"]["ctm"]["hpSquaredError"], 0)
        self.assertEqual(state["forecast"]["plain2k"]["hpSquaredError"], 225)
        self.assertEqual(state["forecast"]["prior2k"]["hpSquaredError"], 100)
        self.assertAlmostEqual(state["repeat"]["plain2k"]["rawHp"]["sampleVariance"], 500 / 3)
        self.assertEqual(state["controllerContrasts"]["prior2k_minus_plain2k"]["rawHp"]["mean"], 5)
        self.assertEqual(state["cost"]["plain2k"]["cpuSecondsPerDecision"], .005)

    def test_full_cohort_excludes_canary(self):
        dump(self.f.root / "canary-report.json", self.analyze_canary())
        for seed in a.COHORT:
            self.f.source(seed)
        self.f.phase("cohort")
        report = a.analyze(self.f.root / "freeze.json", [self.f.prefix(s) for s in reversed(a.COHORT)])
        self.assertEqual(report["verdict"], "DESCRIPTIVE_COMPARISON_MEASURED")
        self.assertEqual(report["sourceSeeds"], a.COHORT)
        self.assertEqual(report["matchedStates"], 4)
        self.assertEqual(report["execution"]["totalCpuSecondsIncludingExcludedCanary"], 5.)

    def test_runtime_manifest_unknown_missing_and_counts(self):
        path = self.f.prefix(a.CANARY) + ".manifest.json"
        original = a.read_json(path)
        for mutate in (lambda x: x.update(unknown=True), lambda x: x.pop("redrawKernel"),
                       lambda x: x["integrity"].update(ctmSupported=2),
                       lambda x: x["sources"][0].update(selectedStateIds=[f"s{a.CANARY}-f1", f"s{a.CANARY}-f2"]),
                       lambda x: x["ctm"]["loadedIdentity"].update(candidateId="wrong")):
            changed = copy.deepcopy(original)
            mutate(changed)
            dump(path, changed)
            with self.assertRaises(a.Invalid):
                self.analyze_canary()
        dump(path, original)

    def test_missing_extra_duplicate_and_invalid_sample(self):
        path = self.f.prefix(a.CANARY) + ".samples.csv"
        original = a.read_csv(path, a.SAMPLE_COLUMNS)
        variants = [original[:-1], original + [original[-1]],
                    original + [dict(original[-1], forecaster="unknown")]]
        for field, value in (("curHp", "nan"), ("outcome", "UNSUPPORTED"), ("curHp", "999")):
            changed = copy.deepcopy(original)
            changed[-1][field] = value
            variants.append(changed)
        for rows in variants:
            csv_write(path, a.SAMPLE_COLUMNS, rows)
            self.f.refresh_csv_hash(a.CANARY, "samples")
            with self.assertRaises(a.Invalid):
                self.analyze_canary()

    def test_wrong_control_and_pairing_seeds(self):
        path = self.f.prefix(a.CANARY) + ".arms.csv"
        original = a.read_csv(path, a.ARM_COLUMNS)
        for index, field, value in ((0, "controlReplayMatch", "0"), (1, "rawCaptureCount", "2"),
                                    (1, "redrawSeed", "5"), (1, "plannerSeed", "5"), (1, "battleSeed", "5"),
                                    (1, "budget", "999"), (1, "cpuSeconds", "NaN"), (1, "valid", "0")):
            changed = copy.deepcopy(original)
            changed[index][field] = value
            csv_write(path, a.ARM_COLUMNS, changed)
            self.f.refresh_csv_hash(a.CANARY, "arms")
            with self.assertRaises(a.Invalid):
                self.analyze_canary()

    def test_receipt_resource_failure_and_custody(self):
        path = self.f.prefix(a.CANARY) + ".receipt.json"
        original = a.read_json(path)
        for field, value in (("cpuSeconds", 601), ("wallSeconds", 901), ("cpuSeconds", .01),
                             ("returncode", 1), ("timedOut", True), ("freezeSha256", "wrong"), ("seed", 2)):
            dump(path, original | {field: value})
            with self.assertRaises(a.Invalid):
                self.analyze_canary()

    def test_progress_missing_truncated_identity_and_timing_rejected(self):
        prefix = self.f.prefix(a.CANARY)
        path = Path(prefix + ".progress.jsonl")
        original = [json.loads(line) for line in path.read_text().splitlines()]
        manifest_path = prefix + ".manifest.json"

        def write(records, final_newline=True):
            text = "\n".join(json.dumps(row) for row in records) + ("\n" if final_newline else "")
            path.write_text(text)
            manifest = a.read_json(manifest_path)
            manifest["outputs"]["progressSha256"] = a.sha(path)
            dump(manifest_path, manifest)

        for changed, newline in [(original[:-1], True), (original, False),
                                  (original + [original[-1]], True)]:
            write(changed, newline)
            with self.assertRaisesRegex(a.Invalid, "progress"):
                self.analyze_canary()
        complete = next(i for i, row in enumerate(original) if row["event"] == "arm_complete")
        for index, key, value in [(2, "stateId", "wrong"), (3, "elapsedCpuSeconds", 0.),
                                  (3, "phaseCpuSeconds", 1e9),
                                  (complete, "combatCpuSeconds", .02), (complete, "phaseCpuSeconds", .001)]:
            changed = copy.deepcopy(original)
            changed[index][key] = value
            write(changed)
            with self.assertRaisesRegex(a.Invalid, "progress"):
                self.analyze_canary()

    def test_old_attempt_seeds_or_caps_cannot_be_used_for_followup(self):
        path = self.f.root / "freeze.json"
        for changed in [self.f.freeze | {"canarySeed": 97150701},
                        self.f.freeze | {"resourceLimits": {"cpuSecondsPerSource": 180, "wallSecondsPerSource": 240,
                                                          "maxConcurrentSources": 2, "maxAttemptedSources": 5}}]:
            dump(path, changed)
            with self.assertRaises(a.Invalid):
                self.analyze_canary()

    def test_frozen_file_mutation(self):
        (self.f.root / "prior.txt").write_text("changed")
        with self.assertRaisesRegex(a.Invalid, "frozen artifact changed"):
            self.analyze_canary()

    def test_full_valid_escape_and_candidate_death(self):
        prefix = self.f.prefix(a.CANARY)
        states = a.read_csv(prefix + ".states.csv", a.STATE_COLUMNS)
        arms = a.read_csv(prefix + ".arms.csv", a.ARM_COLUMNS)
        samples = a.read_csv(prefix + ".samples.csv", a.SAMPLE_COLUMNS)
        states[0]["sourceRawOutcome"] = "ESCAPE"
        arms[0]["rawOutcome"] = "ESCAPE"
        arms[1].update(rawOutcome="DEATH", won="0", rawHp="-3", terminalHp="-3")
        for sample in samples:
            if sample["stateId"].endswith("-f0") and sample["forecaster"] in {"source", "control"}:
                sample.update(outcome="ESCAPE", smokeBombUsed="1")
            if sample["forecaster"] == "plain2k" and sample["k"] == "0":
                sample.update(outcome="DEATH", curHp="-3")
        for name, columns, rows in (("states", a.STATE_COLUMNS, states), ("arms", a.ARM_COLUMNS, arms),
                                    ("samples", a.SAMPLE_COLUMNS, samples)):
            csv_write(prefix + f".{name}.csv", columns, rows)
            self.f.refresh_csv_hash(a.CANARY, name)
        report = self.analyze_canary()
        row = report["perState"][0]
        self.assertEqual(row["reference"]["escape"], 1)
        self.assertEqual(row["reference"]["death"], 0)
        self.assertEqual(row["forecast"]["plain2k"]["predictedRawHp"], 22.5)
        self.assertEqual(row["forecast"]["plain2k"]["predictedDeath"], .25)
        self.assertEqual(row["repeat"]["plain2k"]["potions"]["mean"], .75)

    def test_zero_supported_source_is_insufficient(self):
        prefix = self.f.prefix(a.CANARY)
        states = a.read_csv(prefix + ".states.csv", a.STATE_COLUMNS)
        states[0].update(ctmSupported="0", ctmReason="synthetic_support_miss")
        for key in ("ctmPDeath", "ctmMeanHpWin", "ctmExpectedHp", "ctmForecastCpuUs", "ctmSampleCpuUs"):
            states[0][key] = "-1"
        samples = [s for s in a.read_csv(prefix + ".samples.csv", a.SAMPLE_COLUMNS) if s["forecaster"] == "source"]
        for name, columns, rows in (("states", a.STATE_COLUMNS, states), ("arms", a.ARM_COLUMNS, []),
                                    ("samples", a.SAMPLE_COLUMNS, samples)):
            csv_write(prefix + f".{name}.csv", columns, rows)
            self.f.refresh_csv_hash(a.CANARY, name)
        manifest = a.read_json(prefix + ".manifest.json")
        manifest["integrity"].update(ctmSupported=0, ctmUnsupported=2, controlReplayMatches=0,
                                     unsupportedReasons={"synthetic_support_miss": 2})
        dump(prefix + ".manifest.json", manifest)
        with self.assertRaisesRegex(a.Invalid, "no supported matched state"):
            self.analyze_canary()

    def test_source_raw_mismatch_despite_claimed_control_match(self):
        prefix = self.f.prefix(a.CANARY)
        samples = a.read_csv(prefix + ".samples.csv", a.SAMPLE_COLUMNS)
        samples[0]["gold"] = "100"
        csv_write(prefix + ".samples.csv", a.SAMPLE_COLUMNS, samples)
        self.f.refresh_csv_hash(a.CANARY, "samples")
        with self.assertRaisesRegex(a.Invalid, "source/control RAW sample mismatch"):
            self.analyze_canary()

    def test_unequal_source_weight_and_rmse(self):
        state = self.analyze_canary()["perState"][0]
        low, high = copy.deepcopy(state), copy.deepcopy(state)
        for name in a.FORECASTERS:
            low["forecast"][name]["hpSquaredError"] = 0
            high["forecast"][name]["hpSquaredError"] = 100
        summaries = [a.summarize_states([low] * 3)] + [a.summarize_states([high])] * 3
        equal = a.equal_source_summary(summaries)
        pooled = a.summarize_states([low] * 3 + [high] * 3)
        self.assertEqual(equal["forecast"]["ctm"]["hpSquaredError"], 75)
        self.assertAlmostEqual(equal["forecast"]["ctm"]["hpRmse"], 75 ** .5)
        self.assertEqual(pooled["forecast"]["ctm"]["hpSquaredError"], 50)

    def test_source_cost_ratio_uses_total_decisions(self):
        state = self.analyze_canary()["perState"][0]
        short, long = copy.deepcopy(state), copy.deepcopy(state)
        for name in a.ARM_CONFIG:
            short["cost"][name].update(forecastCpuSeconds=1., decisions=1, cpuSecondsPerDecision=1.)
            long["cost"][name].update(forecastCpuSeconds=3., decisions=9, cpuSecondsPerDecision=1 / 3)
        result = a.summarize_states([short, long])
        self.assertEqual(result["cost"]["plain2k"]["cpuSecondsPerDecision"], .4)

    def test_json_duplicate_nonfinite_and_csv_headers(self):
        for text in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":1e999}'):
            path = self.f.root / "bad.json"
            path.write_text(text)
            with self.assertRaises(a.Invalid):
                a.read_json(path)
        path = self.f.root / "bad.csv"
        path.write_text("x,x\n1,2\n")
        with self.assertRaises(a.Invalid):
            a.read_csv(path, ["x", "y"])

    def test_wrong_panel_and_missing_source(self):
        with self.assertRaises(a.Invalid):
            a.analyze(self.f.root / "freeze.json", [self.f.prefix(a.CANARY)])
        with self.assertRaises(a.Invalid):
            a.analyze(self.f.root / "freeze.json", [self.f.prefix(a.CANARY)] * 2, True)

    def test_output_exclusive_and_failure_preserved(self):
        output = self.f.root / "invalid-report.json"
        args = [str(output), str(self.f.root / "freeze.json"), self.f.prefix(a.CANARY)]
        self.assertEqual(a.main(args), 1)
        before = output.read_bytes()
        self.assertEqual(a.read_json(output)["verdict"], "INVALID_OR_INSUFFICIENT")
        self.assertNotIn("perState", a.read_json(output))
        with self.assertRaises(FileExistsError):
            a.main(args)
        self.assertEqual(output.read_bytes(), before)

    def test_actual_runner_execute_dispatch_and_phase_contract(self):
        # Use the real runner's dispatch/phase naming with fake source production
        # and in-process analyzer invocation; subprocess is never launched.
        (self.f.root / "phase-canary.started.json").unlink()
        calls = []

        def fake_source(out, seed):
            calls.append(seed)
            self.assertEqual(out, self.f.root)
            return Path(self.f.prefix(seed))

        def fake_subprocess(cmd, **kwargs):
            self.assertEqual(cmd[:2], ["python3", str(self.f.repo / "tools/analyze_a20_teachers.py")])
            self.assertEqual(a.main(cmd[2:]), 0)

        with mock.patch.object(runner, "verify", return_value=self.f.freeze), \
                mock.patch.object(runner, "REPO", self.f.repo), \
                mock.patch.object(runner, "run_source", side_effect=fake_source), \
                mock.patch.object(runner.subprocess, "run", side_effect=fake_subprocess):
            runner.execute(self.f.root, "canary")
        self.assertEqual(calls, [a.CANARY])
        self.assertEqual(a.read_json(self.f.root / "canary-report.json")["verdict"], "CANARY_VALID")


class MathTests(unittest.TestCase):
    def test_fixed_random_vectors(self):
        # Published standard MT19937-64 default vector; no gameplay involved.
        self.assertEqual(a.mt19937_64_first(5489), 14514284786278117030)
        self.assertEqual(a.mt19937_64_first(0), 2947667278772165694)
        self.assertEqual(a.splitmix64(0), 0xe220a8397b1dcdaf)

    def test_categorical_plugin_and_structural_death(self):
        self.assertEqual(a.categorical_score(["x", "x", "y", "y"], "x"),
                         {"brier": .5, "referenceMatchProbability": .5})
        self.assertEqual(a.categorical_score(["x"] * 4, "y")["brier"], 2.)
        row = {"outcome": "DEATH"}
        self.assertEqual(a.categorical_values(row)["gold"], ("DEATH",))

    def test_undefined_ratio_and_dispersion(self):
        self.assertEqual(a.dispersion([1, 2, 3, 4])["sampleVariance"], 5 / 3)
        self.assertIsNone(a.mean_objects([None, 1.]))


if __name__ == "__main__":
    unittest.main()
