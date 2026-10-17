#!/usr/bin/env python3
"""One-use controlled Ritual coverage pilot; no fitting or model inference.

`plan` prepares reviewable templates. Freeze/run additionally require an exact
independent packet review and recorded human resource approval. Analysis is
serial; the single-threaded scheduler owns at most BUDGET["workers"] native process groups.
"""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import struct
import subprocess
import sys
import time
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[1]
# Analysis imports `tools.*`; script execution only puts tools/ on sys.path.
sys.path.insert(0, str(REPO))
PROTOCOL = REPO / "docs/experiments/evidence/ritual_coverage_pilot_20261017/PROTOCOL.md"
LIVE_SHA = "8879b5314136c8f9acfe999e40c202e33fde0571"
SPLIT = Path("/home/philippherrmann/Documents/sts/wt-ctm-retrain/build/ctm-retrain-a69f8862/p1/split_manifest.json")
SPLIT_SHA = "a32ff220b0a6e4b8fa7350ed0f29cba267ea46cef1b140c60f0cdbb181ba8e85"
TEMPLATE = REPO / "build/ritual-corrected-canary-plan/teacher-template.json"
TEMPLATE_SHA = "7d3312c2afe1e14185c00e55679f41f1193ce577b4311a9cdb9b280917c6490d"
TRAIN = (52000001, 52000002, 52000003, 52000004, 52000005, 52000006, 52000008, 52000009)
VALIDATION = (52000007, 52000011, 52000015, 52000019)
CELLS = tuple("ritual_writhing_v2_" + "_".join((upgrade, copies, potion))
              for upgrade in ("base", "upgraded") for copies in ("single", "double")
              for potion in ("natural", "brew", "smoke"))
BUDGET = dict(workers=8, threadsPerWorker=1, unitSeconds=60, cleanupSeconds=5,
              packetSeconds=5400, addressSpaceBytesPerWorker=8_000_000_000, gpu=False,
              simulations=10000, ascension=0, units=144)
MODEL_PINS = {
    "models/v_rich_trees.txt": "3a3420469b1d648e0e306d6cb6a7e85f3d3499105e3ff3a56eee6c579194ffe3",
    "models/v_win_trees.txt": "fc52c14cb7239a33b3c1f9d0477ccb6c895fd51a07240fe804744e605067ad70",
    "selfplay/models/combat_transition_deepsets_pathb_r2_lizard.native": "c6d56bbc959f4d5de8fe1dd57f58a922112cd8323bcbac9711e0aecda93f5a3c",
    "selfplay/models/combat_transition_near_full_escape_pathb_r2.native": "b9188de03ed6cc0611094c108f607a8770a5d5c5f367c157851bc6af91f8d9cf",
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def units():
    return [dict(index=i, partition=partition, sourceSeed=seed, setup=cell,
                 id=f"{i:03d}-{seed}-{cell}")
            for i, (partition, seed, cell) in enumerate(
                (partition, seed, cell) for partition, seeds in (("TRAIN", TRAIN), ("VALIDATION", VALIDATION))
                for seed in seeds for cell in CELLS)]


def recipe():
    return dict(schema="ritual_coverage_pilot_v1", budget=BUDGET, units=units(),
                sourceGroups=12, splitManifest=str(SPLIT), splitManifestSha256=SPLIT_SHA,
                liveAncestor=LIVE_SHA, teacherTemplateSha256=TEMPLATE_SHA,
                modelPins=MODEL_PINS, initialMechanicsCheckpointUnits=12,
                coverage=dict(cellTargets={"TRAIN": 4, "VALIDATION": 2},
                              cellPositive={"TRAIN": 3, "VALIDATION": 2},
                              actualRoutePositive={"TRAIN": 3, "VALIDATION": 2},
                              doubleOrdinalPositive={"TRAIN": 2, "VALIDATION": 1},
                              identifiableNamedPotionUse={"TRAIN": 2, "VALIDATION": 1}),
                retry=False, resume=False, replacements=False, extension=False,
                fitting=False, modelInference=False, testAccess=False, promotion=False,
                noTargetOrGrowth="retain_and_continue", ordinaryChildExclusions=[
                    "active_tail_without_bloom", "pre_smoke_used", "act4", "other_public_support"],
                deduplication="exact_source_fight_predictor_transition_including_outcome; retain_raw_and_memberships")


def teacher_template():
    require(sha(TEMPLATE) == TEMPLATE_SHA, "reviewed canary teacher template differs")
    teacher = read(TEMPLATE)
    teacher["environment"].update(STS_COLLECT_KEYS="1", STS_STOP_AFTER_ACT="0", STS_CTM_GEN_DEPLOYED_OOC="0")
    return teacher


def plan(out):
    out.mkdir(parents=True, exist_ok=False)
    write(out / "recipe.json", recipe())
    write(out / "teacher-template.json", teacher_template())
    write(out / "resource-approval-template.json", dict(schema="ritual_coverage_resource_approval_v1",
          approved=False, recipeSha256=digest(recipe()), budget=BUDGET, humanAuthorization="PENDING"))
    write(out / "status.json", dict(status="PENDING_INDEPENDENT_REVIEW_AND_USER_RESOURCE_APPROVAL",
          frozen=False, executed=False, recipeSha256=digest(recipe())))


def selection_check():
    require(sha(SPLIT) == SPLIT_SHA, "original split custody differs")
    members = read(SPLIT)["members"]
    for name, expected in (("train", TRAIN), ("validation", VALIDATION)):
        selected = tuple(seed for seed in range(52000000, 52000400) if seed in set(members[name]))[:len(expected)]
        require(selected == expected, "frozen original source membership differs: " + name)
    require(not set(TRAIN) & set(VALIDATION), "source partitions overlap")


def git(*args):
    return subprocess.check_output(["git", "-C", str(REPO), *args], text=True).strip()


def packet_identity():
    paths = [Path(__file__), REPO / "tests/test_ctm_ritual_coverage_pilot.py", PROTOCOL]
    return {str(path.relative_to(REPO)): sha(path) for path in paths}


def source_identity(executable, source_sha):
    require(len(source_sha) == 40 and git("rev-parse", "HEAD") == source_sha, "source SHA differs")
    require(not git("status", "--porcelain", "--untracked-files=all"), "clean committed source required")
    subprocess.run(["git", "-C", str(REPO), "merge-base", "--is-ancestor", LIVE_SHA, source_sha], check=True)
    executable = Path(executable).resolve()
    require(executable.name == "one_combat" and executable.is_file() and os.access(executable, os.X_OK),
            "one_combat executable required")
    for relative, expected in MODEL_PINS.items():
        require(sha(REPO / relative) == expected, "model custody differs: " + relative)
    return dict(sourceSha=source_sha, reviewedLivePrSha=LIVE_SHA, executable=str(executable),
                executableSha256=sha(executable), indexBlobListSha256=hashlib.sha256(
                    git("ls-files", "--stage").encode()).hexdigest(), modelPins=MODEL_PINS)


def build_binding(path, identity):
    value = read(path)
    require(value.get("schema") == "reviewed_source_build_v1"
            and all(value.get(key) == identity[key] for key in (
                "sourceSha", "reviewedLivePrSha", "executableSha256", "executable"))
            and value.get("sourceCleanBeforeBuild") is True and value.get("sourceCleanAfterBuild") is True
            and value.get("returnCode") == 0 and Path(value.get("workingDirectory", "")).resolve() == REPO,
            "build receipt does not bind clean source/executable")
    command = value.get("command", [])
    require(command[:2] == ["cmake", "--build"] and "--target" in command
            and command.index("--target") + 1 < len(command)
            and command[command.index("--target") + 1] == "one_combat", "wrong build command")
    require(sha(value["logPath"]) == value["logSha256"], "build log custody differs")
    return dict(path=str(Path(path).resolve()), sha256=sha(path), receipt=value)


def approval_check(review, approval, identity):
    require(review.get("verdict") == "PASS" and review.get("independent") is True
            and review.get("sourceSha") == identity["sourceSha"]
            and review.get("packetIdentity") == packet_identity()
            and review.get("recipeSha256") == digest(recipe()), "independent exact-packet review differs")
    require(approval.get("schema") == "ritual_coverage_resource_approval_v1"
            and approval.get("approved") is True and approval.get("budget") == BUDGET
            and approval.get("recipeSha256") == digest(recipe())
            and isinstance(approval.get("humanAuthorization"), str)
            and approval["humanAuthorization"].strip() not in ("", "PENDING"), "human resource approval required")


def child_environment(teacher):
    return {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": os.environ["HOME"],
            "LANG": "C.UTF-8", "OMP_NUM_THREADS": "1", "OMP_THREAD_LIMIT": "1",
            "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "CUDA_VISIBLE_DEVICES": "",
            **teacher["environment"]}


def command_for(out, frozen, unit):
    return ["bash", str(REPO / "tools/seed_guard.sh"), frozen["identity"]["executable"],
            "combattransitionforcedgen", "1", "10000", "0", str((out / unit["id"] / "rows.jsonl").resolve()),
            str(unit["sourceSeed"]), str((out / "teacher.json").resolve()), unit["setup"]]


def freeze(args):
    identity = source_identity(args.exe, args.source_sha)
    selection_check()
    build = build_binding(args.build_receipt, identity)
    review, approval = read(args.review), read(args.approval)
    approval_check(review, approval, identity)
    teacher = teacher_template()
    teacher.update(git_sha=identity["sourceSha"], executable_sha256=identity["executableSha256"],
                   teacher_id="silver-ordinary-fair-learnedstop-ritual-coverage-" + identity["sourceSha"][:12])
    teacher["environment"]["STS_EXECUTABLE_GIT_SHA"] = identity["sourceSha"]
    cpus = sorted(os.sched_getaffinity(0))[:BUDGET["workers"]]
    require(bool(cpus), "no available CPU affinity")
    args.out.mkdir(parents=True, exist_ok=False)
    for name, value in (("teacher.json", teacher), ("review.json", review),
                        ("resource-approval.json", approval), ("build-receipt.json", build["receipt"])):
        write(args.out / name, value)
    frozen = dict(identity=identity, recipe=recipe(), packetIdentity=packet_identity(), buildReceipt=build,
                  teacher=teacher, environment=child_environment(teacher), affinityCpus=cpus,
                  reviewSha256=sha(args.review), approvalSha256=sha(args.approval),
                  reviewPath=str(args.review.resolve()), approvalPath=str(args.approval.resolve()))
    frozen["copiedReceipts"] = {name: sha(args.out / name) for name in (
        "teacher.json", "review.json", "resource-approval.json", "build-receipt.json")}
    frozen["commands"] = [command_for(args.out, frozen, unit) for unit in units()]
    write(args.out / "freeze.json", frozen)


ANALYSIS_MODULES = ("combat_transition_surrogate", "combat_transition_contract", "combat_predictor_input_contract",
                    "combat_transition_sparse_events", "combat_transition_potion_trajectory",
                    "combat_transition_composed", "combat_transition_near_full_support")


def analysis_imports_check():
    import importlib
    for name in ANALYSIS_MODULES:
        importlib.import_module("tools." + name)


def verify_freeze(out):
    analysis_imports_check()
    frozen = read(out / "freeze.json")
    require(frozen["recipe"] == recipe() and frozen["packetIdentity"] == packet_identity(), "recipe/packet changed")
    require(source_identity(frozen["identity"]["executable"], frozen["identity"]["sourceSha"]) == frozen["identity"],
            "source/model/executable identity changed")
    selection_check()
    require(build_binding(frozen["buildReceipt"]["path"], frozen["identity"]) == frozen["buildReceipt"],
            "build receipt changed")
    for name, expected in frozen["copiedReceipts"].items():
        require(sha(out / name) == expected, "frozen receipt changed: " + name)
    require(sha(frozen["reviewPath"]) == frozen["reviewSha256"]
            and sha(frozen["approvalPath"]) == frozen["approvalSha256"], "review/approval changed")
    approval_check(read(out / "review.json"), read(out / "resource-approval.json"), frozen["identity"])
    expected_teacher = teacher_template()
    expected_teacher.update(git_sha=frozen["identity"]["sourceSha"],
        executable_sha256=frozen["identity"]["executableSha256"],
        teacher_id="silver-ordinary-fair-learnedstop-ritual-coverage-" + frozen["identity"]["sourceSha"][:12])
    expected_teacher["environment"]["STS_EXECUTABLE_GIT_SHA"] = frozen["identity"]["sourceSha"]
    require(frozen["teacher"] == expected_teacher == read(out / "teacher.json"), "teacher changed")
    expected_env = child_environment(expected_teacher)
    require(frozen["environment"] == expected_env, "effective child environment changed")
    require(frozen["commands"] == [command_for(out, frozen, unit) for unit in units()], "launch commands changed")
    require(0 < len(frozen["affinityCpus"]) <= BUDGET["workers"]
            and len(set(frozen["affinityCpus"])) == len(frozen["affinityCpus"])
            and set(frozen["affinityCpus"]) <= os.sched_getaffinity(0), "CPU affinity changed")
    return frozen


def descriptor(cell, ids):
    upgrade, copies, potion = cell.removeprefix("ritual_writhing_v2_").split("_")
    return dict(schema="ritual_writhing_public_intervention_v1", researchOnly=True, setup=cell,
        upgraded=upgrade == "upgraded", copies=1 if copies == "single" else 2,
        damageByOrdinal=[15] if copies == "single" else [15, 30],
        forcedPotion=ids["EMPTY_POTION_SLOT"] if potion == "natural" else ids["ENTROPIC_BREW" if potion == "brew" else "SMOKE_BOMB"],
        timing="each_act3_hallway_before_predictor_and_raw_pre_capture",
        daggerPolicy="retain_first_remove_surplus_append_missing_reset_damage_and_upgrade",
        potionPolicy="held_then_lowest_free_else_last_active_overwrite_direct_even_sozu",
        physicalIdentity="current_master_deck_index_per_fight", sourceGrouping="sourceSeed_across_all_variants_and_fights",
        changesSelectedActions=False, consumesRng=False)


def predictor_matches(pre, predictor):
    from tools.combat_predictor_input_contract import validate_predictor_input
    validate_predictor_input(predictor)
    g = predictor["globals"]
    require(all(g[key] == pre[key] for key in ("curHp", "maxHp", "gold", "potionCount", "potionCapacity")),
            "predictor/ROOT globals differ")
    cards = [dict(cardId=card["id"], upgraded=card["upgraded"], misc=card["misc"],
                  bottleBinding=next((binding for binding, idx in enumerate(pre["bottleIdxs"]) if idx == index), -1))
             for index, card in enumerate(pre["deck"])]
    cards.sort(key=lambda c: (c["cardId"], c["upgraded"], c["misc"], c["bottleBinding"]))
    require(predictor["cards"] == cards, "predictor/ROOT physical cards differ")
    require(predictor["relics"] == [dict(relicId=r["id"], data=r["data"], orderIndex=i)
            for i, r in enumerate(pre["relics"])], "predictor/ROOT relics differ")
    require(predictor["potions"] == [dict(slot=i, potionId=p) for i, p in enumerate(pre["potions"])],
            "predictor/ROOT potion slots differ")


def check_target(row, receipt, requested):
    from tools import combat_transition_surrogate as b
    from tools.combat_transition_contract import validate_state
    before, after = receipt["before"], receipt["after"]
    validate_state(before, "before"); validate_state(after, "after")
    require(receipt["sourceSeed"] == row["sourceSeed"] and receipt["fightIdx"] == row["fightIdx"], "target identity differs")
    require(receipt.get("assertionsPassed") is True and receipt.get("rawPreMatchesNormalizedRoot") is True,
            "native target assertions failed")
    require(after == row["transition"]["pre"] and receipt["predictorInput"] == row["predictorInput"],
            "normalized ROOT/predictor/RAW pre differ")
    predictor_matches(after, row["predictorInput"])
    predictor_matches(before, receipt["originalPredictorInput"])
    original = receipt["originalPredictorInput"]["globals"]
    require(original["encounter"] == receipt["originalEncounter"], "original encounter differs")
    require(row["act"] == 3 and row["roomClass"] == "NORMAL"
            and row["encounter"] == b.WRITHING_MASS_ID, "target is not actual Act-3 hallway Writhing")
    for key, value in row["predictorInput"]["globals"].items():
        if key not in ("encounter", "potionCount"):
            require(value == original[key], "unrelated predictor global changed: " + key)
    rng = receipt["rngBefore"]
    require(rng == receipt["rngAfter"] and isinstance(rng, list) and len(rng) == 14
            and all(isinstance(stream, list) and len(stream) == 3
                    and all(type(x) is int for x in stream) for stream in rng), "setup consumed or omitted RNG")
    allowed = {"deck", "cardTypeCounts", "bottleIdxs", "upgradeableCount", "transformableCount", "potions", "potionCount"}
    require(all(after[key] == value for key, value in before.items() if key not in allowed), "unrelated ROOT fields changed")
    dagger = b._CARD_IDS["RITUAL_DAGGER"]
    retained = [i for i, card in enumerate(before["deck"]) if card["id"] == dagger][:requested["copies"]]
    expected_deck = [copy.deepcopy(card) for i, card in enumerate(before["deck"])
                     if card["id"] != dagger or i in retained]
    while sum(card["id"] == dagger for card in expected_deck) < requested["copies"]:
        expected_deck.append(dict(id=dagger, misc=15, upgraded=requested["upgraded"]))
    actual_daggers = []
    for index, card in enumerate(expected_deck):
        if card["id"] == dagger:
            ordinal = len(actual_daggers); card.update(misc=requested["damageByOrdinal"][ordinal], upgraded=requested["upgraded"])
            actual_daggers.append(dict(ordinal=ordinal, deckIndex=index, misc=card["misc"], upgraded=card["upgraded"]))
    require(expected_deck == after["deck"] and receipt["daggers"] == actual_daggers, "actual physical Dagger setup differs")
    belt = list(before["potions"]); named = requested["forcedPotion"]; slot = -1; action = "natural_unchanged"
    if named != b._POTION_IDS["EMPTY_POTION_SLOT"]:
        active = belt[:before["potionCapacity"]]
        if named in active:
            slot, action = active.index(named), "already_held"
        elif b._POTION_IDS["EMPTY_POTION_SLOT"] in active:
            slot, action = active.index(b._POTION_IDS["EMPTY_POTION_SLOT"]), "fill_lowest_free"
        else:
            slot, action = before["potionCapacity"] - 1, "overwrite_last_active"
        belt[slot] = named
    expected_override = dict(action=action, slot=slot,
        sozu=any(r["id"] == b._RELIC_IDS["SOZU"] for r in before["relics"]), directPublicStatePlacement=True)
    require(receipt["potionOverride"] == expected_override and after["potions"] == belt
            and after["potionCount"] == sum(p != b._POTION_IDS["EMPTY_POTION_SLOT"] for p in belt), "potion intervention differs")
    return actual_daggers


def structural_traces(pre, post):
    """Boolean reachability, never posterior probabilities or model calls."""
    from tools import combat_transition_potion_trajectory as t
    state, target = dict(pre["combatRng"][4]), post["combatRng"][4]
    require(0 <= target["counter"] - state["counter"] <= 4096, "unbounded generation body")
    generated = []
    while state["counter"] < target["counter"]:
        generated.append(t.brew.draw_native(state))
    require(state == target, "native generation body RNG differs")
    graph = t.target_graph(pre, post, generated, False)
    require(len(graph.inventories) <= 4096, "structural potion graph exceeds analysis bound")
    initial_bits = sum(1 << i for i, p in enumerate(graph.inventories[0]) if p > 1)
    reachable = [set() for _ in graph.inventories]; reachable[0].add((0, False, False))
    edges, endings = {}, {}
    for owner, action, child in graph.edges:
        edges.setdefault(owner, []).append((action, child))
    for owner, action in graph.target_edges:
        endings.setdefault(owner, []).append(action)
    results = set()
    for owner in range(len(reachable)):
        for action, child in edges.get(owner, []) + [(action, None) for action in endings.get(owner, [])]:
            _, used = t.consume(graph.inventories[owner], action & 31)
            effects = sum(1 << bit for bit, potion in enumerate(t.EFFECT_IDS) if potion in used)
            for code, brew, smoke in reachable[owner]:
                result = ((code & 31) | ((action & 31) & initial_bits) | (32 * ((code >> 5) | effects)),
                          brew or (action >= 32 and t.BREW in used), smoke or (action >= 32 and t.SMOKE in used))
                (results if child is None else reachable[child]).add(result)
    require(bool(results), "no structurally compatible potion trace")
    return [dict(initialMask=code & 31, consumed=[p for bit, p in enumerate(t.EFFECT_IDS) if (code >> 5) & (1 << bit)],
                 brewUsed=brew, smokeUsed=smoke) for code, brew, smoke in sorted(results)], len(generated) // pre["potionCapacity"]


def legal_growth(row):
    from tools import combat_transition_sparse_events as events
    pre, post = row["transition"]["pre"], row["transition"]["post"]
    adjusted = events.writhing_posts(pre)[events.writhing_target(pre, post)]
    changes = events.ritual_changes(adjusted, post)
    traces, rounds = structural_traces(pre, post)
    target = tuple(change["delta"] for change in changes)
    require(any(target in events.ritual_posts(pre, row["predictorInput"], trace["initialMask"], trace["consumed"],
                bool(post["smokeBombUsed"])) for trace in traces), "Ritual target outside compatible native closure")
    require(all(change["delta"] >= 0 for change in changes), "negative Ritual growth")
    return changes, traces, rounds


def support_headers():
    result = {}
    for route, name in (("FAST", "combat_transition_deepsets_pathb_r2_lizard.native"),
                         ("STANDARD", "combat_transition_near_full_escape_pathb_r2.native")):
        path = REPO / "selfplay/models" / name
        require(sha(path) == MODEL_PINS[str(path.relative_to(REPO))], "support artifact custody differs")
        with path.open("rb") as stream:
            require(stream.read(29) == b"COMBAT_TRANSITION_RUNTIME_V2\0", "support artifact magic differs")
            version, length = struct.unpack("<II", stream.read(8))
            require(version == 2 and 0 < length <= 1024 * 1024, "invalid support artifact header")
            result[route] = json.loads(stream.read(length))
    return result


def public_support(row, headers):
    import numpy as np
    from tools import combat_transition_composed as c, combat_transition_near_full_support as support
    pre, pi = row["transition"]["pre"], row["predictorInput"]
    b = c.base
    route = "STANDARD" if b._POTION_IDS["ENTROPIC_BREW"] in pre["potions"] else "FAST"
    relics = {r["id"]: r["data"] for r in pre["relics"]}
    reasons = []
    if relics.get(b._RELIC_IDS["LIZARD_TAIL"]) == 1 and b._RELIC_IDS["MARK_OF_THE_BLOOM"] not in relics:
        reasons.append("active_tail_without_bloom")
    if pre["smokeBombUsed"]:
        reasons.append("pre_smoke_used")
    if pi["globals"]["act"] == 4:
        reasons.append("act4")
    if not reasons:
        header = headers[route]
        proxy = SimpleNamespace(ready=True, classes=np.asarray(header["hpClasses"]),
            delta_values=np.asarray(header["maxHpClasses"]), domain=header["domain"],
            trained_groups=c.TRAINED_GROUPS, encounter_names=c.native_rng.encounter_names())
        previous = c.CLASSES
        try:
            # Analysis is serial in the scheduler parent; restore even on refusal.
            c.CLASSES = proxy.classes
            reasons.extend(support.final_reasons(pi, pre, proxy, escape=True, writhing_ritual=True))
        finally:
            c.CLASSES = previous
    return route, sorted(set(reasons))


def analyze_unit(directory, unit, frozen, execution, headers):
    """Preserve invalid/partial outcomes as receipts; never reinterpret as no fights."""
    result = dict(unit=unit, execution=execution, captureValid=False, targets=[], observations=[])
    path = directory / "rows.jsonl"
    if path.exists():
        result["rawSha256"] = sha(path)
    try:
        from tools import combat_transition_surrogate as b
        from tools.combat_transition_contract import validate_corpus
        require(execution["returnCode"] == 0 and not execution["timedOut"], "incomplete/resource-failed native unit")
        manifest_path = directory / "rows.jsonl.manifest.json"
        manifest = read(manifest_path)
        require(manifest["producerGitSha"] == frozen["identity"]["sourceSha"]
                and manifest["producerExecutableSha256"] == frozen["identity"]["executableSha256"]
                and manifest["combatTeacher"] == frozen["teacher"]
                and manifest["seedSpec"] == dict(start=unit["sourceSeed"], count=1)
                and manifest["forcedSetup"] == unit["setup"] and manifest["oocPolicy"] == "pathb_chain"
                and Path(manifest["csv"]["path"]).resolve() == path.resolve(), "producer identity/request differs")
        contract = validate_corpus(manifest)
        require(contract["rows"] > 0 and contract["sourceSeeds"] == contract["requestedSeeds"] == contract["completedSeeds"] == 1
                and contract["quarantinedSeeds"] == contract["quarantinedRows"] == 0
                and not contract["outcomes"].get(0, 0), "capture/source contract failed")
        requested = descriptor(unit["setup"], b._POTION_IDS)
        intervention = manifest["ritualWrithingIntervention"]
        require(all(intervention.get(key) == value for key, value in requested.items()), "setup descriptor differs")
        receipts = {}
        for receipt in intervention["targets"]:
            key = (receipt["sourceSeed"], receipt["fightIdx"])
            require(key not in receipts, "duplicate target receipt")
            receipts[key] = receipt
        matched = set(); target_seen = False
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        for line_number, row in enumerate(rows, 1):
            require(row["sourceSeed"] == unit["sourceSeed"] and row["captureCount"] == 1
                    and row["runValid"] and not row["quarantineReason"], "row capture/identity invalid")
            key = (row["sourceSeed"], row["fightIdx"])
            actual_target = row["act"] == 3 and row["roomClass"] == "NORMAL"
            require((key in receipts) == actual_target, "requested targets and actual hallway rows differ")
            observation = dict(sourceSeed=row["sourceSeed"], fightIdx=row["fightIdx"],
                canonicalPayload=canonical([row["sourceSeed"], row["fightIdx"], row["predictorInput"], row["transition"]]),
                rawLine=line_number, target=actual_target, commonPrefix=not target_seen and not actual_target)
            result["observations"].append(observation)
            if not actual_target:
                continue
            target_seen = True; matched.add(key)
            daggers = check_target(row, receipts[key], requested)
            route, reasons = public_support(row, headers)
            changes, traces, rounds = legal_growth(row)
            post = row["transition"]["post"]
            potion = unit["setup"].rsplit("_", 1)[-1]
            named_key = "brewUsed" if potion == "brew" else "smokeUsed" if potion == "smoke" else None
            uses = [trace[named_key] for trace in traces] if named_key else []
            result["targets"].append(dict(fightIdx=row["fightIdx"], route=route, excludedReasons=reasons,
                ordinaryChild=not reasons, combatOutcome=row["transition"]["combatOutcome"],
                escaped=post["smokeBombUsed"], changes=changes, daggers=daggers,
                positiveOrdinals=[i for i, change in enumerate(changes) if change["delta"] > 0],
                namedPotionUse="ALL_COMPATIBLE" if uses and all(uses) else "SOME_COMPATIBLE" if any(uses) else "NONE",
                potionTracePossibilities=traces, brewRounds=rounds,
                actualInitialBrew=route == "STANDARD"))
        require(matched == set(receipts), "orphaned target receipt")
        result.update(captureValid=True, rows=len(rows), contract=contract, manifestSha256=sha(manifest_path))
    except Exception as error:
        result["analysisError"] = dict(type=type(error).__name__, message=str(error))
    return result


def aggregate(results):
    expected = units()
    require(len(results) == len(expected) and all(r["unit"] == u for r, u in zip(results, expected)), "unit ledger/order differs")
    tables = {"cellTargets": {}, "cellPositive": {}, "actualRoutePositive": {},
              "doubleOrdinalPositive": {}, "identifiableNamedPotionUse": {}}
    route_counts, exclusions, outcomes = Counter(), Counter(), Counter()
    dedup = {}; duplicates = 0
    for result in results:
        unit = result["unit"]; partition = unit["partition"]; seed = unit["sourceSeed"]
        cell = unit["setup"]; upgrade, copies, potion = cell.removeprefix("ritual_writhing_v2_").split("_")
        for observation in result.get("observations", []):
            payload = observation["canonicalPayload"]; key = hashlib.sha256(payload.encode()).hexdigest()
            member = dict(unitId=unit["id"], rawLine=observation["rawLine"], target=observation["target"], commonPrefix=observation["commonPrefix"])
            if key in dedup:
                require(dedup[key]["canonicalPayload"] == payload, "observation SHA collision")
                duplicates += 1
                dedup[key]["memberships"].append(member)
            else:
                dedup[key] = dict(canonicalPayload=payload, sourceSeed=seed,
                                 fightIdx=observation["fightIdx"], memberships=[member])
        for target in result.get("targets", []):
            route_counts[target["route"]] += 1
            outcomes[str(target["combatOutcome"])] += 1
            exclusions.update(target["excludedReasons"])
            if not result.get("captureValid") or not target["ordinaryChild"]:
                continue
            def add(table, key):
                tables[table].setdefault(key, {}).setdefault(partition, set()).add(seed)
            add("cellTargets", cell)
            positive = target["positiveOrdinals"]
            if positive:
                add("cellPositive", cell)
                add("actualRoutePositive", "_".join((upgrade, copies, target["route"])))
            if copies == "double":
                for ordinal in positive:
                    add("doubleOrdinalPositive", "_".join((upgrade, target["route"], str(ordinal))))
            if potion != "natural" and target["namedPotionUse"] == "ALL_COMPATIBLE":
                add("identifiableNamedPotionUse", "_".join((upgrade, copies, potion)))
    keys = dict(cellTargets=CELLS, cellPositive=CELLS,
        actualRoutePositive=["_".join((up, copies, route)) for up in ("base", "upgraded") for copies in ("single", "double") for route in ("FAST", "STANDARD")],
        doubleOrdinalPositive=["_".join((up, route, str(ordinal))) for up in ("base", "upgraded") for route in ("FAST", "STANDARD") for ordinal in (0, 1)],
        identifiableNamedPotionUse=["_".join((up, copies, potion)) for up in ("base", "upgraded") for copies in ("single", "double") for potion in ("brew", "smoke")])
    missing = []
    for table, required_keys in keys.items():
        for key in required_keys:
            for partition, minimum in recipe()["coverage"][table].items():
                sources = tables[table].setdefault(key, {}).setdefault(partition, set())
                if len(sources) < minimum:
                    missing.append(dict(table=table, path=key, partition=partition, observed=len(sources), required=minimum))
    valid = all(result.get("captureValid") is True for result in results)
    serial = {table: {key: {partition: sorted(values) for partition, values in parts.items()}
                      for key, parts in cells.items()} for table, cells in tables.items()}
    return dict(classification="PILOT_INCOMPLETE_OR_INVALID" if not valid else
                "PILOT_COVERAGE_INCONCLUSIVE" if missing else "PILOT_COVERAGE_ADEQUATE_FOR_REVIEW_ONLY",
        sourceGroups=12, plannedUnits=144, attemptedUnits=sum(r.get("attempted", False) for r in results),
        validUnits=sum(r.get("captureValid", False) for r in results), coverageSourceGroups=serial,
        missingCoverage=missing, targetRoutes=dict(route_counts), targetOutcomes=dict(outcomes), exclusions=dict(exclusions),
        distinctObservations=len(dedup), duplicateObservations=duplicates, duplicateMap=dedup,
        training=False, modelInference=False, testAccess=False, qualification=False, promotion=False,
        retry=False, extension=False)


def stop_process(proc):
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        return proc.wait(timeout=BUDGET["cleanupSeconds"])
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        return proc.wait()


def run(out):
    frozen = verify_freeze(out)
    write(out / "run-started.json", dict(unixTime=time.time(), freezeSha256=sha(out / "freeze.json")))
    results = [dict(unit=unit, attempted=False, captureValid=False, status="UNATTEMPTED") for unit in units()]
    active = {}; next_index = 0; started = time.monotonic(); stop_reason = None
    headers = support_headers()
    try:
        while next_index < len(results) or active:
            now = time.monotonic()
            if now - started >= BUDGET["packetSeconds"] - BUDGET["cleanupSeconds"]:
                stop_reason = "packet_wall_limit"
            # Do not launch source two until the first source's twelve cells
            # passed integrity. Valid no-target/no-growth cells continue.
            checkpoint_wait = next_index >= 12 and any(not result.get("finished") for result in results[:12])
            while not stop_reason and not checkpoint_wait and len(active) < len(frozen["affinityCpus"]) and next_index < len(results):
                index = next_index; unit = results[index]["unit"]; directory = out / unit["id"]
                directory.mkdir(); results[index].update(attempted=True, status="ATTEMPTED")
                stdout = (directory / "stdout.log").open("x"); stderr = (directory / "stderr.log").open("x")
                cpu = next(cpu for cpu in frozen["affinityCpus"] if cpu not in [entry["cpu"] for entry in active.values()])
                def limits(cpu=cpu):
                    os.sched_setaffinity(0, {cpu})
                    resource.setrlimit(resource.RLIMIT_AS, (BUDGET["addressSpaceBytesPerWorker"],) * 2)
                launch = time.monotonic()
                proc = subprocess.Popen(command_for(out, frozen, unit), cwd=REPO, env=frozen["environment"],
                    stdout=stdout, stderr=stderr, preexec_fn=limits, start_new_session=True)
                stdout.close(); stderr.close()
                active[index] = dict(proc=proc, start=launch, cpu=cpu)
                next_index += 1
                checkpoint_wait = next_index >= 12 and any(not result.get("finished") for result in results[:12])
            for index, entry in list(active.items()):
                elapsed = time.monotonic() - entry["start"]; proc = entry["proc"]
                # A unit that already exited is never relabelled as timed out.
                rc = proc.poll(); timed_out = False
                if rc is None and (elapsed >= BUDGET["unitSeconds"] or stop_reason):
                    rc = stop_process(proc); timed_out = True
                if rc is None:
                    continue
                execution = dict(returnCode=rc, timedOut=timed_out, wallSeconds=time.monotonic() - entry["start"], affinityCpu=entry["cpu"])
                unit = results[index]["unit"]; directory = out / unit["id"]
                write(directory / "exit.json", execution)
                result = analyze_unit(directory, unit, frozen, execution, headers)
                result.update(attempted=True, finished=True, status="FINISHED")
                results[index] = result; write(directory / "result.json", result); del active[index]
                if not result["captureValid"]:
                    stop_reason = "unit_integrity_or_resource_failure"
            if next_index == 12 and not active and not (out / "mechanics-checkpoint.json").exists():
                write(out / "mechanics-checkpoint.json", dict(valid=all(r["captureValid"] for r in results[:12]),
                    unexercisedCells=[r["unit"]["setup"] for r in results[:12] if not r.get("targets")],
                    validNoTargetOrGrowth="retained_continue", units=[r["unit"]["id"] for r in results[:12]]))
            if stop_reason and not active:
                break
            time.sleep(.05)
    except BaseException as error:
        stop_reason = type(error).__name__ + ": " + str(error)
    finally:
        for index, entry in active.items():
            rc = stop_process(entry["proc"])
            execution = dict(returnCode=rc, timedOut=True, wallSeconds=time.monotonic() - entry["start"], affinityCpu=entry["cpu"])
            directory = out / results[index]["unit"]["id"]
            write(directory / "exit.json", execution)
            result = analyze_unit(directory, results[index]["unit"], frozen, execution, headers)
            result.update(attempted=True, finished=True, status="FINISHED")
            results[index] = result; write(directory / "result.json", result)
        write(out / "unit-ledger.json", results)
        summary = aggregate(results); summary.update(stopReason=stop_reason, wallSeconds=time.monotonic() - started)
        write(out / "result.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "identity", "freeze", "run"))
    parser.add_argument("--out", type=Path)
    parser.add_argument("--exe", type=Path); parser.add_argument("--source-sha")
    parser.add_argument("--build-receipt", type=Path); parser.add_argument("--review", type=Path)
    parser.add_argument("--approval", type=Path)
    args = parser.parse_args()
    if args.command == "identity":
        print(json.dumps(dict(packetIdentity=packet_identity(), recipeSha256=digest(recipe())), indent=2)); return
    require(args.out is not None, "--out required")
    if args.command == "plan":
        plan(args.out)
    elif args.command == "freeze":
        require(all((args.exe, args.source_sha, args.build_receipt, args.review, args.approval)),
                "explicit source/executable/build/review/resource approval required")
        freeze(args)
    else:
        print(json.dumps(run(args.out), indent=2))


if __name__ == "__main__":
    main()
