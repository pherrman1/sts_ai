"""Small native fixtures, never scientific collection or quality evidence."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import silver_prior_dataset as data
from silver_prior_projection import project, digest, canonical, permute_candidates
from ironclad_reachable_domain_census import build_census


def rejects(call):
    try:
        call()
    except (ValueError, KeyError):
        return
    raise AssertionError("expected rejection")


def main():
    bridge, labeler = map(str, map(Path, sys.argv[1:]))
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    env = {k: v for k, v in os.environ.items() if not k.startswith("STS_")}
    env.update(STS_EXECUTABLE_GIT_SHA=sha, STS_SILVER_ADAPTIVE="0")
    plan = data.read(ROOT / "docs/experiments/evidence/silver_prior_dataset_v1/plan.json")
    vocab = data.read(ROOT / "docs/experiments/evidence/silver_prior_dataset_v1/vocabulary.json")
    data.validate_plan(plan)
    assert data.vocabulary(build_census()) == vocab
    assert len(vocab["entries"]) == 158
    names = {e["name"] for e in vocab["entries"]}
    assert {"BRUTALITY", "COMBUST", "DAZED", "BURN", "ASCENDERS_BANE", "BITE", "JAX", "FLASH_OF_STEEL"} <= names
    assert Counter(e["classification"] for e in vocab["entries"]) == {"REACHABLE": 131, "UNKNOWN": 27}

    with tempfile.TemporaryDirectory() as temporary:
        tmp = Path(temporary)

        def run(*command, success=True, extra=None):
            result = subprocess.run(["bash", str(ROOT / "tools/seed_guard.sh"), *map(str, command)],
                                    cwd=ROOT, env={**env, **(extra or {})}, capture_output=True, text=True)
            assert (result.returncode == 0) == success, result.stdout + result.stderr
            return result

        run(bridge, "--root-mechanism-fixture", tmp / "root.jsonl")
        root = data.rows(tmp / "root.jsonl")[0]
        entry = {"root": root, "split": "TRAIN", "judge_selected": False}
        job = data.job_for(entry, plan, sha, fixture=True)

        def label(job, name):
            data.publish(tmp / f"{name}.job.json", job)
            run(labeler, tmp / f"{name}.job.json", tmp / f"{name}.raw.json")
            return data.read(tmp / f"{name}.raw.json")

        raw = label(job, "first")
        assert label(job, "repeat") == raw
        values = data.validate_raw(raw, job, True)
        observation = project(root, vocab, raw["reference"])
        assert observation["candidates"] and len(values) == len(root["actions"])
        permutation = list(reversed(range(len(values))))
        permuted, permuted_values = permute_candidates(observation, values, permutation)
        assert permute_candidates(permuted, permuted_values, permutation) == (observation, values)
        changed = copy.deepcopy(root)
        w = changed["state"]["state"]
        w["isolatedSearchSeed"] += 123
        w["observedGeneration"] += 234
        w["nextUniqueCardId"] += 345
        w["loopCount"] += 456
        changed.update(root_id="arbitrary", source_seed=987654321, state_hash="different")
        for zone in ("hand", "limbo", "stasisCards"):
            for c in w[zone]:
                c["uniqueId"] += 1000
        for zone in ("drawPile", "discardPile", "exhaustPile"):
            for segment in ("knownBottom", "unknown", "knownTop"):
                for c in w[zone][segment]:
                    c["uniqueId"] += 1000
                if segment == "unknown":
                    w[zone][segment].reverse()
        for action in changed["actions"]:
            action["card"]["uniqueId"] += 1000
        assert project(changed, vocab, raw["reference"]) == observation
        changed["state"]["state"]["extraRollMoveOnTurn"] = 5
        assert project(changed, vocab, raw["reference"])["extraRollMoveSlots"] == [0, 2]
        # Same ID, different occurrence state must remain distinct.
        changed = copy.deepcopy(root)
        card = copy.deepcopy(changed["state"]["state"]["hand"][0])
        card.update(uniqueId=30000, costForTurn=0, specialData=9, upgraded=True, freeToPlayOnce=True)
        changed["state"]["state"]["hand"].append(card)
        distinct = project(changed, vocab, raw["reference"])["cards"]
        assert distinct[0]["card_id"] == distinct[len(root["state"]["state"]["hand"])]["card_id"]
        assert distinct[0] != distinct[len(root["state"]["state"]["hand"])]
        # Observed order remains visible; unknown order does not.
        changed = copy.deepcopy(root)
        pile = changed["state"]["state"]["drawPile"]
        pile["knownTop"], pile["unknown"], pile["fullOrderObserved"] = pile["unknown"], [], True
        ordered = project(changed, vocab, raw["reference"])
        pile["knownTop"].reverse()
        assert project(changed, vocab, raw["reference"]) != ordered
        # Runic Dome is enforced again at the projection boundary.
        changed = copy.deepcopy(root)
        changed["state"]["state"]["intentsHidden"] = True
        hidden = project(changed, vocab, raw["reference"])
        for monster in changed["state"]["state"]["monsters"]:
            monster["moveHistory"] = [111, 222]
        assert project(changed, vocab, raw["reference"]) == hidden
        changed = copy.deepcopy(root)
        changed["state"]["state"]["hand"][0]["id"] = 1
        rejects(lambda: project(changed, vocab, raw["reference"]))
        changed = copy.deepcopy(raw)
        changed["actions"][0]["replicates"].pop()
        rejects(lambda: data.validate_raw(changed, job, True))
        changed = copy.deepcopy(raw)
        changed["actions"].pop()
        rejects(lambda: data.validate_raw(changed, job, True))
        changed = copy.deepcopy(raw)
        changed["actions"][0]["replicates"][0]["rng_identity"] += 1
        rejects(lambda: data.validate_raw(changed, job, True))
        rejects(lambda: data.validate_raw(raw, job))
        for key, value in (("executable_git_sha", "0" * 40), ("schema", "wrong")):
            bad = {**job, key: value}
            data.publish(tmp / f"bad-{key}.json", bad)
            run(labeler, tmp / f"bad-{key}.json", tmp / "bad-out.json", success=False)
            assert not (tmp / "bad-out.json").exists()
        judge_job = data.job_for({**entry, "split": "VALIDATION", "judge_selected": True},
                                plan, sha, role="J", fixture=True)
        judge = label(judge_job, "judge")
        data.validate_raw(judge, judge_job, True)
        assert {r["rng_identity"] for a in raw["actions"] for r in a["replicates"]}.isdisjoint(
            {r["rng_identity"] for a in judge["actions"] for r in a["replicates"]})
        # Force terminal wins and the zero-continuation exception.
        terminal_root = copy.deepcopy(root)
        for monster in terminal_root["state"]["state"]["monsters"]:
            if monster["curHp"] > 0:
                monster["curHp"] = 1
        terminal_root["state_hash"] = f'{data.fnv(canonical(terminal_root["state"])):016x}'
        terminal_job = {**job, "root": terminal_root}
        terminal = label(terminal_job, "terminal")
        data.validate_raw(terminal, terminal_job, True)
        assert any(r["terminal_after_action"] and r["simulations"] == 0
                   for a in terminal["actions"] for r in a["replicates"])
        # Existing fixed correction root, adapted only to current no-target semantics.
        historical = data.rows(ROOT / "docs/experiments/evidence/silver_forced_action_target_2026-09-19/roots.jsonl")
        correction = next(r for r in historical if r["root_id"] == "12006015/1/13/7/3")
        for i in (0, 1, 3, 4, 5):
            correction["actions"][i]["target"] = -1
            correction["native_order"][i] = correction["native_order"][i].replace("/x=0/", "/x=-1/")
        correction_job = {**job, "root": correction}
        corrected = label(correction_job, "correction")
        data.validate_raw(corrected, correction_job, True)
        assert any(r["victory_baseline_correction"] != 0
                   for a in corrected["actions"] for r in a["replicates"])
        potions = project(correction, vocab, corrected["reference"])
        assert all(c["potion_id"] == potions["potions"][c["potion_slot"]]["potion_id"]
                   for c in potions["candidates"] if c["type"] == 2)
        stored = data.shard(raw, job, vocab, True)
        data.publish(tmp / "shard.json.gz", stored)
        before = (tmp / "shard.json.gz").read_bytes()
        data.publish(tmp / "shard.json.gz", stored)
        assert (tmp / "shard.json.gz").read_bytes() == before
        rejects(lambda: data.publish(tmp / "shard.json.gz", {**stored, "values": []}))
        rejects(lambda: data.load_training(tmp / "shard.json.gz", vocab, job))
        # Capture neutrality covers live gameplay decisions and RNG counters.
        control = run(bridge, "--capture-neutrality-fixture")
        captured = run(bridge, "--capture-neutrality-fixture",
                       extra={"STS_SILVER_ROOT_MECHANISM_CAPTURE": str(tmp / "capture.jsonl")})
        assert (control.stdout, control.stderr) == (captured.stdout, captured.stderr)
        assert data.rows(tmp / "capture.jsonl")
        # Selection remains label-independent, capped per combat/act/source, and pilot is a subset.
        captures = []
        for act in (1, 2, 3):
            for combat in range(6):
                for turn in (1, 2, 3, 4):
                    r = copy.deepcopy(root)
                    r.update(source_seed=plan["pilot_sources"][0], act=act, combat_id=f"{act}/{combat}",
                             root_id=f"{plan['pilot_sources'][0]}/{act}/{combat}/{turn}",
                             executable_git_sha=sha, capture_config=data.CAPTURE)
                    r["state"]["state"].update(turn=turn, act=act)
                    captures.append(r)
        selected = data.select(plan, captures, sha)
        pilot = data.select(plan, captures, sha, True)
        assert len(selected["entries"]) == 24 and len(pilot["entries"]) == 6
        assert {e["root"]["root_id"] for e in pilot["entries"]} <= {e["root"]["root_id"] for e in selected["entries"]}
        assert max(Counter(e["root"]["combat_id"] for e in selected["entries"]).values()) <= 2
        print(canonical({"fixture_only": True, "deterministic": True, "capture_neutral": True,
                         "actions": len(values), "vocabulary": len(vocab["entries"]),
                         "terminal_and_correction_valid": True}))


if __name__ == "__main__":
    from collections import Counter
    main()
