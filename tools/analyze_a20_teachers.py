#!/usr/bin/env python3
"""Strict descriptive analysis of the fixed A20 teacher pilot; never runs games.

Usage: analyze_a20_teachers.py OUT.json FREEZE.json PREFIX... [--canary]
See evidence/a20_teacher_comparison_20261014/ANALYSIS-CONTRACT.md.
"""
import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import sys


CANARY = 97150801
COHORT = [97150810, 97150811, 97150812, 97150813]
ARM_CONFIG = {"plain2k": (2000, False), "prior2k": (2000, True),
              "plain10k": (10000, False), "prior10k": (10000, True)}
FORECASTERS = ("ctm", *ARM_CONFIG)
CONTRASTS = {"prior2k_minus_plain2k": ("prior2k", "plain2k"),
             "prior10k_minus_plain10k": ("prior10k", "plain10k"),
             "plain10k_minus_plain2k": ("plain10k", "plain2k"),
             "prior10k_minus_prior2k": ("prior10k", "prior2k")}
SLOTS = ((1, "NORMAL"), (1, "ELITE"), (1, "BOSS"),
         (2, "ELITE"), (2, "BOSS"), (3, "BOSS"))
CTM_HASHES = {
    "fast.native": "ae785ec2e28ceb3755fb63a71534f873ed61a069a6c2e107ef4131a788af7b6b",
    "standard.native": "e338506ddf14177bec27cfe174670bd9dcac333c26b30416b9f0c76717392b0d",
    "manifest.json": "704f2a58c70d731c10ea8f4b00dc977f6d57ee0872480bf53e461e88583404d0"}
STATE_COLUMNS = ("stateId,sourceSeed,fightIdx,act,floor,roomClass,encounter,preHp,preMaxHp,"
                 "prePotions,sourceWon,sourceTerminalHp,sourceValid,ctmSupported,ctmReason,"
                 "ctmPDeath,ctmMeanHpWin,ctmExpectedHp,ctmForecastCpuUs,ctmSampleCpuUs,"
                 "sourcePostHp,sourceRawHp,sourceRawMaxHp,sourceRawOutcome,sourceRawCaptureCount").split(",")
ARM_COLUMNS = ("stateId,sourceSeed,fightIdx,arm,k,budget,prior,redraw,redrawSeed,won,terminalHp,"
               "cpuSeconds,simulations,decisions,valid,controlReplayMatch,quarantineReason,"
               "treeMinVisits,plannerSeed,rawHp,rawMaxHp,rawOutcome,rawCaptureCount,battleSeed").split(",")
SAMPLE_COLUMNS = ("stateId,forecaster,k,outcome,curHp,maxHp,gold,potionCount,potions,relics,"
                  "deckHash,smokeBombUsed,stolenGold").split(",")
OUTCOMES = {"DEATH", "VICTORY", "ESCAPE"}
SELECTION = {
    "rule": "first_captured_entry_per_fixed_slot_before_outcome_or_support_filtering",
    "slots": [{"act": act, "roomClass": room} for act, room in SLOTS],
    "maxPerSource": 6, "absentSlotPolicy": "skip_no_substitution",
    "unsupportedPolicy": "retain_state_and_source_raw_exclude_all_forecasts_no_substitution"}
REDRAW = ("A20 battle seed plus six GC streams redrawn; ordinary init derives four correlated streams "
          "from battleSeed+floor, misc/potion retain redrawn GC streams; Colosseum continuation retains six redrawn GC streams")
REDRAW_KERNEL = {
    "id": "teacher_a20_native_init_v1", "engine": "std::mt19937_64",
    "drawOrder": ["gc.seed", "gc.aiRng", "gc.cardRandomRng", "gc.miscRng", "gc.monsterHpRng", "gc.potionRng", "gc.shuffleRng"],
    "gcCountersPreservedBeforeInit": True, "ordinaryInitFourCountersReset": True,
    "redrawSeedSalt": 0xC0FFEE07, "plannerSeedSalt": 0x91A77E2, "ctmSeedSalt": 0x5A3B1E,
    "sharedSilverReplicates": True, "sourceControlOriginalFuture": True}
SOURCE_CONTROL = {
    "budget": 10000, "rootPrior": False, "treeMinVisits": 0, "budgetPolicy": "flat", "skipSingletonRoots": False,
    "controlEquality": "source terminal labels, first action, post-callback HP, and exact RAW CombatTransitionPersistentState JSON including combat RNG"}


class Invalid(ValueError):
    """A contract violation; never an instruction to exclude just one row."""


def require(ok, reason):
    if not ok:
        raise Invalid(reason)


def keys(value, expected, where):
    require(isinstance(value, dict), f"{where}: expected object")
    require(set(value) == set(expected),
            f"{where}: missing {sorted(set(expected)-set(value))}; unknown {sorted(set(value)-set(expected))}")


def json_object(pairs):
    obj = {}
    for key, value in pairs:
        require(key not in obj, f"duplicate JSON key: {key}")
        obj[key] = value
    return obj


def decode_json(text):
    def bad_constant(value):
        raise Invalid(f"nonfinite JSON constant: {value}")
    return json.loads(text, object_pairs_hook=json_object, parse_constant=bad_constant,
                      parse_float=lambda value: number(value, "JSON float"))


def read_json(path):
    return decode_json(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def integer(value, where, minimum=None, maximum=None):
    if isinstance(value, str):
        require(re.fullmatch(r"-?(0|[1-9][0-9]*)", value) is not None, f"{where}: invalid integer")
        value = int(value)
    require(type(value) is int, f"{where}: expected integer")
    require(minimum is None or value >= minimum, f"{where}: below minimum")
    require(maximum is None or value <= maximum, f"{where}: above maximum")
    return value


def number(value, where, minimum=None, maximum=None):
    require(not isinstance(value, bool), f"{where}: boolean is not a number")
    try:
        result = float(value)
    except (ValueError, TypeError) as exc:
        raise Invalid(f"{where}: invalid number") from exc
    require(math.isfinite(result), f"{where}: nonfinite number")
    require(minimum is None or result >= minimum, f"{where}: below minimum")
    require(maximum is None or result <= maximum, f"{where}: above maximum")
    return result


def read_csv(path, columns):
    with Path(path).open(newline="") as stream:
        reader = csv.DictReader(stream, strict=True)
        require(reader.fieldnames == columns, f"{path}: missing/unknown/reordered/duplicate CSV columns")
        rows = list(reader)
    for row in rows:
        require(None not in row and all(v is not None for v in row.values()), f"{path}: malformed CSV row")
    return rows


def unique_rows(rows, fields, where):
    result = {}
    for row in rows:
        key = tuple(row[f] for f in fields)
        require(key not in result, f"{where}: duplicate row {key}")
        result[key] = row
    return result


def splitmix64(value):
    mask = (1 << 64) - 1
    value = (value + 0x9e3779b97f4a7c15) & mask
    value = ((value ^ (value >> 30)) * 0xbf58476d1ce4e5b9) & mask
    value = ((value ^ (value >> 27)) * 0x94d049bb133111eb) & mask
    return value ^ (value >> 31)


def replicate_seed(seed, fight, k, salt):
    return splitmix64(splitmix64(seed ^ salt) ^ (fight << 16) ^ k)


def mt19937_64_first(seed):
    """First draw of the standard C++ engine; seeds are independently derived."""
    mask = (1 << 64) - 1
    state = [seed]
    for i in range(1, 312):
        previous = state[-1]
        state.append((6364136223846793005 * (previous ^ (previous >> 62)) + i) & mask)
    combined = (state[0] & (mask ^ ((1 << 31) - 1))) | (state[1] & ((1 << 31) - 1))
    value = state[156] ^ (combined >> 1) ^ (0xb5026f5aa96619e9 if combined & 1 else 0)
    value ^= (value >> 29) & 0x5555555555555555
    value ^= (value << 17) & 0x71d67fffeda60000
    value ^= (value << 37) & 0xfff7eee000000000
    return (value ^ (value >> 43)) & mask


def validate_freeze(freeze):
    keys(freeze, ("schemaVersion", "producerGitSha", "repository", "binary", "binarySha256", "teacher",
                  "environment", "canarySeed", "cohortSeeds", "outputs", "resourceLimits", "priorIdentity",
                  "ctmIdentity", "arms", "buildCommands", "artifactFiles"), "freeze")
    require(freeze["schemaVersion"] == "a20_teacher_comparison_freeze_v2", "unknown freeze schema")
    require(freeze["canarySeed"] == CANARY and freeze["cohortSeeds"] == COHORT, "wrong frozen seed panel")
    require(re.fullmatch(r"[0-9a-f]{40}", freeze["producerGitSha"]) is not None, "invalid source revision")
    require(freeze["resourceLimits"] == {"cpuSecondsPerSource": 600, "wallSecondsPerSource": 900,
                                        "maxConcurrentSources": 2, "maxAttemptedSources": 5}, "wrong resource caps")
    require(freeze["ctmIdentity"] == CTM_HASHES, "wrong PR524 CTM identity")
    keys(freeze["priorIdentity"], ("sha256", "generation", "source", "treeMinVisits", "weight", "rootBonus"), "prior identity")
    prior_hash = freeze["priorIdentity"]["sha256"]
    require(re.fullmatch(r"[0-9a-f]{64}", prior_hash) is not None, "invalid prior digest")
    generation = integer(freeze["priorIdentity"]["generation"], "prior generation", 5, 6)
    origin = freeze["priorIdentity"]["source"]
    require(isinstance(origin, str) and bool(origin.strip()), "missing prior source")
    require(freeze["priorIdentity"] == {"sha256": prior_hash, "generation": generation, "source": origin,
                                        "treeMinVisits": 8, "weight": 400,
                                        "rootBonus": True}, "wrong prior settings")
    expected_arms = [{"name": name, "budget": budget, "prior": prior, "replicates": 4}
                     for name, (budget, prior) in ARM_CONFIG.items()]
    require(freeze["arms"] == expected_arms, "wrong frozen arm panel")
    require(isinstance(freeze["environment"], dict)
            and all(isinstance(k, str) and isinstance(v, str) for k, v in freeze["environment"].items()),
            "invalid frozen environment")
    require(isinstance(freeze["artifactFiles"], dict) and freeze["artifactFiles"], "missing frozen artifacts")
    for path, digest in freeze["artifactFiles"].items():
        require(Path(path).is_absolute() and re.fullmatch(r"[0-9a-f]{64}", digest) is not None,
                f"invalid artifact path/hash: {path}")
        require(sha(path) == digest, f"frozen artifact changed: {path}")
    repo = Path(freeze["repository"])
    packet = repo / "docs/experiments/evidence/a20_teacher_comparison_20261014"
    for path in (freeze["binary"], freeze["teacher"], str(Path(__file__).resolve()),
                 str(repo / "tools/seed_guard.sh"), str(packet / "run_pilot.py"),
                 str(packet / "PROTOCOL-V2.md"), str(packet / "PROTOCOL.md"), str(packet / "ANALYSIS-CONTRACT.md")):
        require(path in freeze["artifactFiles"], f"required file absent from freeze: {path}")
    require(freeze["artifactFiles"][freeze["binary"]] == freeze["binarySha256"], "binary hash mismatch")
    keys(freeze["outputs"], map(str, (CANARY, *COHORT)), "frozen output prefixes")
    prefixes = list(freeze["outputs"].values())
    require(len(set(prefixes)) == 5 and all(isinstance(p, str) and Path(p).is_absolute() for p in prefixes),
            "invalid frozen output prefixes")
    teacher = read_json(freeze["teacher"])
    require(teacher["git_sha"] == freeze["producerGitSha"]
            and teacher["executable_sha256"] == freeze["binarySha256"]
            and teacher["environment"] == freeze["environment"], "teacher/freeze identity mismatch")
    require(teacher["search_configuration"]["simulation_budgets"] == [10000]
            and teacher["combat_backend"] == "native_silver" and teacher["rng_regime"] == "project_fair",
            "wrong source teacher configuration")
    for artifact in teacher["model_artifacts"] + teacher["ooc_policy"]["model_artifacts"]:
        path = str((repo / artifact["path"]).resolve())
        require(freeze["artifactFiles"].get(path) == artifact["sha256"], f"unfrozen teacher model: {path}")
    env = freeze["environment"]
    fixed_env = {"OMP_NUM_THREADS": "1", "OMP_DYNAMIC": "FALSE", "STS_FAIR": "1", "STS_SEARCHER3": "0",
                 "STS_SILVER_SEARCH": "1", "STS_SILVER_EXACT_ROOT_BUDGETS": "1",
                 "STS_SILVER_ADAPTIVE": "0", "STS_SILVER_LEARNED_STOP": "0", "STS_SILVER_LOOP_GUARD": "0",
                 "STS_SILVER_ROOT_PRIOR_WEIGHT": "400", "STS_CTMSILVER_ARMSET": "teacher_a20",
                 "STS_OOC_MCTS": "0", "STS_COLLECT_KEYS": "0", "STS_STOP_AFTER_ACT": "3",
                 "STS_EXECUTABLE_GIT_SHA": freeze["producerGitSha"]}
    require(all(env.get(key) == value for key, value in fixed_env.items()), "incorrect frozen study environment")
    for key, name in (("STS_CTMSILVER_CANDIDATE_FAST", "fast.native"),
                      ("STS_CTMSILVER_CANDIDATE_STANDARD", "standard.native"),
                      ("STS_CTM_RESEARCH_CANDIDATE_MANIFEST", "manifest.json")):
        require(freeze["artifactFiles"].get(env.get(key)) == CTM_HASHES[name], f"CTM artifact not frozen: {key}")
    require(env.get("STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256") == CTM_HASHES["manifest.json"],
            "candidate manifest environment mismatch")
    require(env.get("STS_SILVER_ROOT_PRIOR") == env.get("STS_CTMSILVER_MLP_PRIOR")
            and freeze["artifactFiles"].get(env.get("STS_SILVER_ROOT_PRIOR")) == prior_hash, "unfrozen prior")
    return teacher


def validate_sample(row):
    require(row["outcome"] in OUTCOMES, "unsupported/unknown RAW outcome")
    for key in ("curHp", "maxHp", "gold", "stolenGold"):
        integer(row[key], f"sample {key}")
    integer(row["potionCount"], "sample potion count", 0, 5)
    integer(row["smokeBombUsed"], "sample smoke flag", 0, 1)
    require(re.fullmatch(r"[0-9a-f]{1,16}", row["deckHash"]) is not None, "malformed deck hash")
    potions = row["potions"].split(";")
    require(len(potions) == 5, "expected five potion slots")
    for potion in potions:
        integer(potion, "potion id", -1)
    if row["relics"]:
        for relic in row["relics"].split(";"):
            parts = relic.split(":")
            require(len(parts) == 2, "malformed relic")
            integer(parts[0], "relic id", 0)
            integer(parts[1], "relic data")
    if row["outcome"] != "DEATH":
        require(0 < int(row["curHp"]) <= int(row["maxHp"]), "invalid surviving RAW HP")
        require((row["outcome"] == "ESCAPE") == (row["smokeBombUsed"] == "1"), "escape/smoke mismatch")


def validate_rows(states, arms, samples, seed):
    smap = unique_rows(states, ("stateId",), "states")
    amap = unique_rows(arms, ("stateId", "arm", "k"), "arms")
    pmap = unique_rows(samples, ("stateId", "forecaster", "k"), "samples")
    expected_arms, expected_samples = set(), set()
    supported = []
    for row in samples:
        validate_sample(row)
    for state in states:
        sid = state["stateId"]
        require(integer(state["sourceSeed"], "state source seed") == seed, "state from different source")
        fight = integer(state["fightIdx"], "fight index", 0)
        require(sid == f"s{seed}-f{fight}", "state id mismatch")
        require((integer(state["act"], "act", 1, 3), state["roomClass"]) in SLOTS, "invalid selected slot")
        integer(state["floor"], "floor", 1, 60)
        for key in ("preHp", "preMaxHp", "sourceTerminalHp", "sourcePostHp", "sourceRawHp", "sourceRawMaxHp"):
            integer(state[key], f"state {key}")
        require(0 < int(state["preHp"]) <= int(state["preMaxHp"]), "invalid precombat HP")
        integer(state["prePotions"], "pre potion count", 0, 5)
        integer(state["sourceWon"], "source won", 0, 1)
        require(state["sourceValid"] == "1" and state["sourceRawCaptureCount"] == "1", "invalid source RAW capture")
        require(state["ctmSupported"] in {"0", "1"}, "invalid support flag")
        source_key = (sid, "source", "0")
        expected_samples.add(source_key)
        require(source_key in pmap, "missing original source RAW sample")
        source = pmap[source_key]
        require((state["sourceRawHp"], state["sourceRawMaxHp"], state["sourceRawOutcome"])
                == (source["curHp"], source["maxHp"], source["outcome"]), "source RAW fields/sample mismatch")
        require((state["sourceWon"] == "0") == (source["outcome"] == "DEATH"), "source won/outcome mismatch")
        if state["ctmSupported"] == "0":
            require(bool(state["ctmReason"]) and state["ctmReason"] != "supported", "missing unsupported reason")
            require(all(number(state[key], key) == -1 for key in
                        ("ctmPDeath", "ctmMeanHpWin", "ctmExpectedHp", "ctmForecastCpuUs", "ctmSampleCpuUs")),
                    "unsupported state contains forecasts")
            continue
        require(state["ctmReason"] == "supported", "supported reason mismatch")
        p = number(state["ctmPDeath"], "CTM death probability", 0, 1)
        mean_hp = number(state["ctmMeanHpWin"], "CTM conditional HP", 0)
        expected_hp = number(state["ctmExpectedHp"], "CTM expected HP", 0)
        require(math.isclose(expected_hp, (1 - p) * mean_hp, abs_tol=2e-6, rel_tol=2e-8), "CTM expectation identity mismatch")
        number(state["ctmForecastCpuUs"], "CTM expectation cost", 0)
        number(state["ctmSampleCpuUs"], "CTM sample cost", 0)
        supported.append(state)
        expected_samples.update((sid, "ctm", str(k)) for k in range(32))
        for name, (budget, prior) in {"control": (10000, False), **ARM_CONFIG}.items():
            for k in range(1 if name == "control" else 4):
                key = (sid, name, str(k))
                expected_arms.add(key)
                expected_samples.add(key)
                require(key in amap and key in pmap, f"missing arm/sample: {key}")
                arm, sample = amap[key], pmap[key]
                require(arm["sourceSeed"] == state["sourceSeed"] and arm["fightIdx"] == state["fightIdx"], "arm state identity mismatch")
                require(arm["valid"] == "1" and arm["quarantineReason"] == "" and arm["rawCaptureCount"] == "1", "invalid arm RAW capture")
                require(arm["controlReplayMatch"] == ("1" if name == "control" else "-1"), "control replay mismatch")
                require((arm["budget"], arm["prior"], arm["redraw"], arm["treeMinVisits"])
                        == (str(budget), str(int(prior)), str(int(name != "control")), "8" if prior else "0"), "arm configuration mismatch")
                redraw = replicate_seed(seed, fight, k, 0xC0FFEE07) if name != "control" else 0
                planner = replicate_seed(seed, fight, k, 0x91A77E2) if name != "control" else 0
                battle = mt19937_64_first(redraw) if name != "control" else seed
                for field, expected in (("redrawSeed", redraw), ("plannerSeed", planner), ("battleSeed", battle)):
                    require(integer(arm[field], field, 0, (1 << 64) - 1) == expected, f"wrong {field}")
                number(arm["cpuSeconds"], "arm CPU", 0)
                integer(arm["simulations"], "simulations", 0)
                integer(arm["decisions"], "decisions", 0)
                integer(arm["terminalHp"], "terminal HP")
                integer(arm["won"], "arm won", 0, 1)
                require((arm["rawHp"], arm["rawMaxHp"], arm["rawOutcome"])
                        == (sample["curHp"], sample["maxHp"], sample["outcome"]), "arm RAW sample mismatch")
                require((arm["won"] == "0") == (sample["outcome"] == "DEATH"), "arm won/outcome mismatch")
                if name == "control":
                    require(all(source[field] == sample[field] for field in SAMPLE_COLUMNS[3:]), "source/control RAW sample mismatch")
                    require(arm["terminalHp"] == state["sourceTerminalHp"], "source/control terminal HP mismatch")
    require(set(amap) == expected_arms, "extra or unknown arm rows")
    require(set(pmap) == expected_samples, "missing/extra/unknown sample rows")
    require(len(smap) <= 6, "more than six selected states")
    return supported, amap, pmap


def sample_values(row):
    dead = row["outcome"] == "DEATH"
    return {"death": float(dead), "rawHp": 0.0 if dead else float(row["curHp"]),
            "potions": 0.0 if dead else float(row["potionCount"]),
            "escape": float(row["outcome"] == "ESCAPE")}


def categorical_values(row):
    fields = ("maxHp", "gold", "potions", "relics", "deckHash", "smokeBombUsed", "stolenGold")
    if row["outcome"] == "DEATH":
        # Structural marker cannot collide with any valid string or tuple value.
        result = {field: ("DEATH",) for field in fields}
    else:
        result = {field: ("VALUE", row[field]) for field in fields}
        result["potions"] = ("VALUE", row["potionCount"], row["potions"])
    return {"outcome": row["outcome"], **result,
            "nonHpJoint": tuple(result[field] for field in fields)}


def categorical_score(values, reference):
    counts = Counter(values)
    size = len(values)
    match = counts[reference] / size
    return {"brier": 1 - 2 * match + sum((count / size) ** 2 for count in counts.values()),
            "referenceMatchProbability": match}


def dispersion(values):
    variance = statistics.variance(values) if len(values) > 1 else None
    return {"n": len(values), "mean": statistics.mean(values), "sampleVariance": variance,
            "sd": math.sqrt(variance) if variance is not None else None,
            "min": min(values), "max": max(values), "range": max(values) - min(values)}


def mean_objects(objects):
    """Mean identically shaped numeric summaries, retaining undefined ratios."""
    require(bool(objects), "cannot aggregate no observations")
    if isinstance(objects[0], dict):
        require(all(set(x) == set(objects[0]) for x in objects), "inconsistent metric shapes")
        return {key: mean_objects([x[key] for x in objects]) for key in objects[0]}
    return statistics.mean(objects) if all(x is not None for x in objects) else None


def state_metrics(state, arm_rows, samples):
    def draws(name):
        return [samples[(state["stateId"], name, str(k))]
                for k in range(32 if name == "ctm" else 1 if name == "control" else 4)]
    reference = draws("control")[0]
    target = sample_values(reference)
    target_fields = categorical_values(reference)
    forecasts, repeat, costs = {}, {}, {}
    for name in FORECASTERS:
        ds = draws(name)
        values = [sample_values(row) for row in ds]
        p = float(state["ctmPDeath"]) if name == "ctm" else statistics.mean(v["death"] for v in values)
        h = float(state["ctmExpectedHp"]) if name == "ctm" else statistics.mean(v["rawHp"] for v in values)
        forecasts[name] = {
            "deathBrier": (p - target["death"]) ** 2,
            "deathBias": p - target["death"], "hpSquaredError": (h - target["rawHp"]) ** 2,
            "hpBias": h - target["rawHp"], "hpAbsoluteError": abs(h - target["rawHp"]),
            "predictedDeath": p, "predictedRawHp": h,
            "categorical": {field: categorical_score([categorical_values(row)[field] for row in ds], value)
                            for field, value in target_fields.items()}}
        repeat[name] = {metric: dispersion([v[metric] for v in values]) for metric in target}
        if name == "ctm":
            costs[name] = {"expectationCpuSeconds": float(state["ctmForecastCpuUs"]) / 1e6,
                           "prepareAndSampleCpuSeconds": float(state["ctmSampleCpuUs"]) / 1e6}
        else:
            rows = [arm_rows[(state["stateId"], name, str(k))] for k in range(4)]
            cpu = sum(float(row["cpuSeconds"]) for row in rows)
            decisions = sum(int(row["decisions"]) for row in rows)
            costs[name] = {"forecastCpuSeconds": cpu, "fightCpuSeconds": cpu / 4,
                           "decisions": decisions, "simulations": sum(int(row["simulations"]) for row in rows),
                           "cpuSecondsPerDecision": cpu / decisions if decisions else None}
    paired = {}
    for contrast, (left, right) in CONTRASTS.items():
        deltas = []
        for k, (a, b) in enumerate(zip(draws(left), draws(right))):
            va, vb = sample_values(a), sample_values(b)
            delta = {metric: va[metric] - vb[metric] for metric in va}
            delta["cpuSeconds"] = (float(arm_rows[(state["stateId"], left, str(k))]["cpuSeconds"])
                                   - float(arm_rows[(state["stateId"], right, str(k))]["cpuSeconds"]))
            deltas.append(delta)
        paired[contrast] = {metric: dispersion([d[metric] for d in deltas]) for metric in deltas[0]}
    control = arm_rows[(state["stateId"], "control", "0")]
    return {"stateId": state["stateId"], "sourceSeed": int(state["sourceSeed"]),
            "act": int(state["act"]), "floor": int(state["floor"]), "roomClass": state["roomClass"],
            "reference": target, "forecast": forecasts, "repeat": repeat, "cost": costs,
            "controllerContrasts": paired, "controlCpuSeconds": float(control["cpuSeconds"])}


def summarize_states(rows):
    result = {"matchedStates": len(rows),
              "forecast": mean_objects([r["forecast"] for r in rows]),
              "cost": mean_objects([r["cost"] for r in rows]),
              "controllerContrasts": {
                  contrast: {metric: statistics.mean(r["controllerContrasts"][contrast][metric]["mean"] for r in rows)
                             for metric in rows[0]["controllerContrasts"][contrast]}
                  for contrast in CONTRASTS}}
    for name in FORECASTERS:
        result["forecast"][name]["hpRmse"] = math.sqrt(result["forecast"][name]["hpSquaredError"])
        if name != "ctm":
            cpu = sum(r["cost"][name]["forecastCpuSeconds"] for r in rows)
            decisions = sum(r["cost"][name]["decisions"] for r in rows)
            result["cost"][name]["cpuSecondsPerDecision"] = cpu / decisions if decisions else None
    return result


def equal_source_summary(summaries):
    result = {field: mean_objects([summary[field] for summary in summaries])
              for field in ("forecast", "cost", "controllerContrasts")}
    for name in FORECASTERS:
        result["forecast"][name]["hpRmse"] = math.sqrt(result["forecast"][name]["hpSquaredError"])
    return result


def expected_runtime_arms(freeze):
    result = []
    for name, (budget, prior) in {"control": (10000, False), **ARM_CONFIG}.items():
        result.append({"name": name, "budget": budget, "rootPrior": prior,
                       "redrawCombatFuture": name != "control", "replicates": 1 if name == "control" else 4,
                       "treeMinVisits": 8 if prior else 0,
                       "priorModel": freeze["environment"]["STS_SILVER_ROOT_PRIOR"] if prior else None,
                       "priorModelSha256": freeze["priorIdentity"]["sha256"] if prior else None})
    return result


def validate_progress(path, seed, source, states, arm_rows, cpu_seconds):
    text = Path(path).read_text()
    require(text.endswith("\n"), "truncated progress record")
    records = [decode_json(line) for line in text.splitlines()]
    expected = [("source_start", {}, ())]
    expected.append(("trajectory_complete", {"capturedFights": source["capturedCount"],
                     "finalFloor": source["finalFloor"], "valid": True}, ()))
    for state in states:
        sid = state["stateId"]
        expected.append(("state_start", {"stateId": sid, "fightIdx": int(state["fightIdx"]),
                         "act": int(state["act"]), "floor": int(state["floor"]),
                         "roomClass": state["roomClass"], "encounter": state["encounter"]}, ()))
        expected.append(("ctm_complete", {"stateId": sid, "supported": state["ctmSupported"] == "1"},
                         ("phaseCpuSeconds",)))
        if state["ctmSupported"] == "1":
            for name, (budget, _) in {"control": (10000, False), **ARM_CONFIG}.items():
                for k in range(1 if name == "control" else 4):
                    row = arm_rows[(sid, name, str(k))]
                    identity = {"stateId": sid, "arm": name, "k": k, "budget": budget}
                    expected.append(("arm_start", identity, ()))
                    expected.append(("arm_complete", identity | {"decisions": int(row["decisions"]),
                                     "simulations": int(row["simulations"]), "valid": True},
                                     ("phaseCpuSeconds", "combatCpuSeconds")))
        expected.append(("state_complete", {"stateId": sid}, ()))
    expected.append(("source_complete", {"selectedStates": len(states)}, ()))
    require(len(records) == len(expected), "missing or extra progress records")
    previous, arm_start, state_start = -1., None, None
    for record, (event, identity, timed_fields) in zip(records, expected):
        keys(record, ("event", "sourceSeed", "elapsedCpuSeconds", *identity, *timed_fields), "progress record")
        require(record["event"] == event and record["sourceSeed"] == seed
                and all(type(record[key]) is type(value) and record[key] == value for key, value in identity.items()),
                "progress order/identity mismatch")
        elapsed = number(record["elapsedCpuSeconds"], "progress CPU", 0, cpu_seconds + .02)
        require(elapsed >= previous, "nonmonotone progress CPU")
        previous = elapsed
        for field in timed_fields:
            number(record[field], "progress " + field, 0)
        if event == "state_start":
            state_start = elapsed
        if event == "ctm_complete":
            require(record["phaseCpuSeconds"] <= elapsed - state_start + .02,
                    "progress CTM phase CPU mismatch")
        if event == "arm_start":
            arm_start = elapsed
        if event == "arm_complete":
            row = arm_rows[(record["stateId"], record["arm"], str(record["k"]))]
            combat = record["combatCpuSeconds"]
            require(math.isclose(combat, float(row["cpuSeconds"]), rel_tol=1e-7, abs_tol=1e-8),
                    "progress/CSV combat CPU mismatch")
            require(combat <= record["phaseCpuSeconds"] + .000001
                    and record["phaseCpuSeconds"] <= elapsed - arm_start + .02,
                    "progress phase CPU mismatch")


def validate_job(prefix, seed, freeze, freeze_hash, teacher):
    prefix = str(Path(prefix).resolve())
    require(prefix == freeze["outputs"][str(seed)], "prefix differs from frozen output")
    receipt = read_json(prefix + ".receipt.json")
    keys(receipt, ("returncode", "cpuSeconds", "wallSeconds", "timedOut", "argv", "seed",
                   "binarySha256", "freezeSha256"), "runner receipt")
    argv = ["bash", str(Path(freeze["repository"]) / "tools/seed_guard.sh"), freeze["binary"],
            "ctmsilvergen", "1", "20", prefix, str(seed), freeze["teacher"], "4"]
    require(receipt["argv"] == argv and receipt["seed"] == seed, "runner command/seed mismatch")
    require(integer(receipt["returncode"], "process return code") == 0 and receipt["timedOut"] is False,
            "source process failed or timed out")
    require(receipt["binarySha256"] == freeze["binarySha256"] and receipt["freezeSha256"] == freeze_hash,
            "runner custody mismatch")
    number(receipt["cpuSeconds"], "job CPU", 0, 600)
    number(receipt["wallSeconds"], "job wall time", 0, 900)
    started = read_json(prefix + ".started.json")
    require(started == {"argv": argv, "freezeSha256": freeze_hash}, "job launch latch mismatch")
    require(Path(prefix + ".log").is_file(), "missing source log")
    manifest = read_json(prefix + ".manifest.json")
    keys(manifest, ("schemaVersion", "producerGitSha", "producerExecutableSha256", "teacherId", "teacherManifestSha256",
                    "combatTeacher", "policy", "seedSpec", "rootPrior", "ctm", "redraw", "ctmOnly", "candidate",
                    "arms", "armSet", "sources", "integrity", "outputs", "producerExecutablePath", "teacherPath",
                    "selection", "redrawKernel", "sourceControl", "environment"), "runtime manifest")
    require(manifest["schemaVersion"] == "ctm_vs_silver_teacher_a20_v2" and manifest["armSet"] == "teacher_a20"
            and manifest["ctmOnly"] is False and manifest["candidate"] is None, "wrong runtime mode")
    require(manifest["producerGitSha"] == freeze["producerGitSha"]
            and manifest["producerExecutableSha256"] == freeze["binarySha256"]
            and manifest["producerExecutablePath"] == freeze["binary"], "runtime producer mismatch")
    require(manifest["teacherPath"] == freeze["teacher"]
            and manifest["teacherManifestSha256"] == sha(freeze["teacher"])
            and manifest["teacherId"] == teacher["teacher_id"]
            and manifest["combatTeacher"] == teacher and manifest["policy"] == teacher["ooc_policy"],
            "runtime teacher/policy mismatch")
    require(manifest["seedSpec"] == {"start": seed, "count": 1, "ascension": 20}, "runtime seed specification mismatch")
    env = freeze["environment"]
    require(manifest["environment"] == env, "runtime environment mismatch")
    require(manifest["rootPrior"] == {"path": env["STS_SILVER_ROOT_PRIOR"],
                                      "sha256": freeze["priorIdentity"]["sha256"], "weight": 400}, "runtime prior mismatch")
    require(manifest["arms"] == expected_runtime_arms(freeze), "runtime arm panel mismatch")
    ctm = manifest["ctm"]
    expected_ctm = {"fast": env["STS_CTMSILVER_CANDIDATE_FAST"], "fastSha256": CTM_HASHES["fast.native"],
                    "standard": env["STS_CTMSILVER_CANDIDATE_STANDARD"], "standardSha256": CTM_HASHES["standard.native"],
                    "activeLizard": True, "timingReps": 20, "forecastSamples": 32, "candidateId": "pathb-a20",
                    "manifestPath": env["STS_CTM_RESEARCH_CANDIDATE_MANIFEST"],
                    "manifestSha256": CTM_HASHES["manifest.json"],
                    "loadedIdentity": read_json(env["STS_CTM_RESEARCH_CANDIDATE_MANIFEST"])}
    require(ctm == expected_ctm, "runtime loaded CTM identity mismatch")
    require(manifest["selection"] == SELECTION and manifest["redrawKernel"] == REDRAW_KERNEL
            and manifest["redraw"] == REDRAW and manifest["sourceControl"] == SOURCE_CONTROL,
            "runtime selection/redraw/source protocol mismatch")
    keys(manifest["outputs"], ("statesSha256", "armsSha256", "samplesSha256", "statesPath", "armsPath", "samplesPath", "progressPath", "progressSha256"),
         "runtime outputs")
    for name in ("states", "arms", "samples", "progress"):
        path = prefix + (".progress.jsonl" if name == "progress" else f".{name}.csv")
        require(manifest["outputs"][name + "Path"] == path
                and manifest["outputs"][name + "Sha256"] == sha(path), f"runtime output custody mismatch: {name}")
    states = read_csv(prefix + ".states.csv", STATE_COLUMNS)
    arms = read_csv(prefix + ".arms.csv", ARM_COLUMNS)
    samples = read_csv(prefix + ".samples.csv", SAMPLE_COLUMNS)
    supported, amap, pmap = validate_rows(states, arms, samples, seed)
    require(len(manifest["sources"]) == 1, "expected one source per job")
    source = manifest["sources"][0]
    keys(source, ("seed", "complete", "valid", "fights", "finalFloor", "won", "captured", "capturedCount",
                  "selectedStateIds", "selectedCount", "finalHp", "finalOutcome", "fatalFailure",
                  "simulatorHealthFailures", "invalidCombatRows"), "source summary")
    for field in ("seed", "fights", "capturedCount", "selectedCount", "simulatorHealthFailures", "invalidCombatRows"):
        integer(source[field], f"source {field}", 0)
    require(source["seed"] == seed and source["complete"] is True and source["valid"] is True
            and source["fatalFailure"] is False and source["simulatorHealthFailures"] == 0
            and source["invalidCombatRows"] == 0, "invalid/incomplete source trajectory")
    require(source["finalOutcome"] in {"VICTORY", "DEATH"} and type(source["won"]) is bool
            and source["won"] == (source["finalOutcome"] == "VICTORY"), "source final outcome mismatch")
    integer(source["finalHp"], "final HP")
    integer(source["finalFloor"], "final floor", 1, 60)
    captured = source["captured"]
    require(isinstance(captured, list) and len(captured) == source["capturedCount"] == source["fights"], "capture count mismatch")
    selected, seen, previous = [], set(), -1
    for entry in captured:
        keys(entry, ("stateId", "fightIdx", "act", "roomClass", "floor"), "captured entry")
        fight = integer(entry["fightIdx"], "captured fight index", 0)
        require(fight > previous and entry["stateId"] == f"s{seed}-f{fight}", "unordered/duplicate captured entry")
        previous = fight
        integer(entry["act"], "captured act", 1, 3)
        integer(entry["floor"], "captured floor", 1, 60)
        slot = (entry["act"], entry["roomClass"])
        if slot in SLOTS and slot not in seen:
            selected.append(entry["stateId"])
            seen.add(slot)
    require(selected == source["selectedStateIds"] == [r["stateId"] for r in states]
            and len(selected) == source["selectedCount"] <= 6, "first-slot selection mismatch")
    captured_map = {entry["stateId"]: entry for entry in captured}
    for state in states:
        entry = captured_map[state["stateId"]]
        require(all(str(entry[field]) == state[field] for field in ("fightIdx", "act", "roomClass", "floor")),
                "selected state/capture metadata mismatch")
    reasons = dict(Counter(s["ctmReason"] for s in states if s["ctmSupported"] == "0"))
    for field, value in manifest["integrity"].items():
        if field != "unsupportedReasons":
            integer(value, f"integrity {field}", 0)
    require(manifest["integrity"] == {
        "completeSources": 1, "validSources": 1, "states": len(states), "ctmSupported": len(supported),
        "controlReplayMatches": len(supported), "controlReplayMismatches": 0, "invalidArmRows": 0,
        "capturedStates": len(captured), "selectedStates": len(states), "ctmUnsupported": len(states) - len(supported),
        "unsupportedReasons": reasons}, "integrity counts mismatch")
    require(bool(supported), f"source {seed} has no supported matched state")
    validate_progress(prefix + ".progress.jsonl", seed, source, states, amap, receipt["cpuSeconds"])
    # Arm timers are contained in the process timer. GNU time rounds to .01s.
    require(sum(float(r["cpuSeconds"]) for r in arms) <= receipt["cpuSeconds"] + .02,
            "sum of arm CPU exceeds process CPU")
    return {"seed": seed, "prefix": prefix, "receipt": receipt,
            "coverage": {"captured": len(captured), "selected": len(states), "matched": len(supported),
                         "unsupported": len(states) - len(supported), "unsupportedReasons": reasons,
                         "selectedStateIds": selected, "absentSlots": [dict(act=a, roomClass=r) for a, r in SLOTS if (a, r) not in seen],
                         "finalFloor": source["finalFloor"], "finalOutcome": source["finalOutcome"]},
            "metrics": [state_metrics(state, amap, pmap) for state in supported]}


def analyze(freeze_path, prefixes, canary=False):
    freeze_hash = sha(freeze_path)
    freeze = read_json(freeze_path)
    teacher = validate_freeze(freeze)
    seeds = [CANARY] if canary else COHORT
    require(len(prefixes) == len(seeds) and len(set(prefixes)) == len(seeds), "wrong or duplicate source panel")
    expected = {freeze["outputs"][str(seed)]: seed for seed in seeds}
    normalized = [str(Path(prefix).resolve()) for prefix in prefixes]
    require(set(normalized) == set(expected), "unexpected or missing source prefix")
    phase = "canary" if canary else "cohort"
    phase_latch = Path(freeze_path).parent / ("phase-" + phase + ".started.json")
    require(read_json(phase_latch) == {"freezeSha256": freeze_hash}, "phase latch mismatch")
    jobs = [validate_job(freeze["outputs"][str(seed)], seed, freeze, freeze_hash, teacher) for seed in seeds]
    all_jobs = list(jobs)
    if not canary:
        canary_report = read_json(Path(freeze_path).parent / "canary-report.json")
        require(canary_report["verdict"] == "CANARY_VALID" and canary_report["freezeSha256"] == freeze_hash
                and canary_report["sourceSeeds"] == [CANARY], "excluded canary did not pass this freeze")
        all_jobs.append(validate_job(freeze["outputs"][str(CANARY)], CANARY, freeze, freeze_hash, teacher))
    cpu = sum(job["receipt"]["cpuSeconds"] for job in all_jobs)
    require(cpu <= 3000, "aggregate CPU cap exceeded")
    rows = [row for job in jobs for row in job["metrics"]]
    per_source = {str(job["seed"]): {"coverage": job["coverage"], "summary": summarize_states(job["metrics"])} for job in jobs}
    equal = equal_source_summary([source["summary"] for source in per_source.values()])
    custody = {str(Path(freeze_path).resolve()): freeze_hash}
    for job in all_jobs:
        for extension in ("states.csv", "arms.csv", "samples.csv", "progress.jsonl", "manifest.json", "receipt.json", "started.json", "log"):
            path = job["prefix"] + "." + extension
            custody[path] = sha(path)
    return {"schemaVersion": "a20_teacher_comparison_analysis_v1",
            "verdict": "CANARY_VALID" if canary else "DESCRIPTIVE_COMPARISON_MEASURED", "reasons": [],
            "freezeSha256": freeze_hash, "sourceSeeds": seeds, "canaryExcluded": not canary,
            "inputHashes": custody, "sources": len(jobs), "matchedStates": len(rows),
            "coverage": {"captured": sum(j["coverage"]["captured"] for j in jobs),
                         "selected": sum(j["coverage"]["selected"] for j in jobs),
                         "unsupported": sum(j["coverage"]["unsupported"] for j in jobs),
                         "unsupportedReasons": dict(sum((Counter(j["coverage"]["unsupportedReasons"]) for j in jobs), Counter()))},
            "perState": rows, "perSource": per_source, "equalSourceMeans": equal, "pooledStateMeans": summarize_states(rows),
            "execution": {"totalCpuSecondsIncludingExcludedCanary": cpu,
                          "jobs": [{"seed": j["seed"], "cpuSeconds": j["receipt"]["cpuSeconds"],
                                    "wallSeconds": j["receipt"]["wallSeconds"]} for j in all_jobs]},
            "costScopes": {
                "silver": "cpuSeconds and all derived fight/forecast/decision CPU values time playoutBattle only; exclude exitBattle, RAW copy and post-callback work.",
                "ctmExpectation": "Repeated captureCombatPredictorInput plus expectation, averaged over timing repetitions.",
                "ctmSample": "Repeated input capture, prepare and one sample, averaged over timing repetitions; distinct from the 32 forecast draws.",
                "process": "Runner receipt covers whole source process and all overhead. No exact end-to-end CTM/Silver CPU ratio is claimed."},
            "limitations": ["Descriptive selected trajectories, at most four source clusters; no confidence intervals or winner.",
                            "Plain10k is an independent behavioral reference, not optimal play; CTM controller mismatch remains.",
                            "CTM32 and Silver4 categorical scores evaluate different finite-sample forecast sizes.",
                            "No training, OOC decision quality, public-input sufficiency, or promotion conclusion."]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out", type=Path)
    parser.add_argument("freeze", type=Path)
    parser.add_argument("prefixes", nargs="+")
    parser.add_argument("--canary", action="store_true")
    args = parser.parse_args(argv)
    # Reserve output before reading. Invalid and partial inputs get a durable
    # failure report; an existing report always remains byte-identical.
    with args.out.open("x") as output:
        try:
            result = analyze(args.freeze, args.prefixes, args.canary)
        except (OSError, ValueError, TypeError, KeyError, IndexError, OverflowError, csv.Error) as exc:
            result = {"schemaVersion": "a20_teacher_comparison_analysis_v1", "verdict": "INVALID_OR_INSUFFICIENT",
                      "reasons": [f"{type(exc).__name__}: {exc}"], "sourcePrefixes": args.prefixes,
                      "freezeSha256": sha(args.freeze) if args.freeze.is_file() else None}
        json.dump(result, output, indent=2, allow_nan=False)
        output.write("\n")
    print(json.dumps({"verdict": result["verdict"], "reasons": result["reasons"]}))
    return 0 if result["verdict"] != "INVALID_OR_INSUFFICIENT" else 1


if __name__ == "__main__":
    sys.exit(main())
