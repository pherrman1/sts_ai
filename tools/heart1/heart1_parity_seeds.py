#!/usr/bin/env python3
"""heart1 parity on gameplay seeds (run through tools/seed_guard.sh).

  early <nSeeds> <seedStart> <asc> <silverbot_repo> <heart1.pt> <one_combat> <heart1.bin> <outdir>
      Cross-engine check on matched early-game states. For each seed and each
      Neow option, silverbot's engine and code play from Neow to the first
      combat (greedy heart1 after the forced Neow pick). Our engine replays the
      same out-of-combat actions (one_combat heart1replay). Every decision's
      record must be identical and the native logits must match silverbot's.

  trace <nSeeds> <seedStart> <asc> <silverbot_repo> <heart1.pt> <sims> <out.jsonl>
      silverbot's engine and greedy heart1 play whole games with their own
      combat agent at <sims> simulations, writing every policy decision's
      record and silverbot logits (input for one_combat heart1score).
"""
import json
import os
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import heart1_reference as ref  # noqa: E402


def their_decision(sts, network, net, playouts, gc, forced=None):
    """One silverbot run_episode step. Returns (taken actions, decision or None, done)."""
    taken = [(int(a.bits), False) for a in playouts.take_free_rewards(gc)]
    if gc.screen_state == sts.ScreenState.BATTLE or gc.outcome != sts.GameOutcome.UNDECIDED:
        return taken, None
    obs = sts.getNNRepresentation(gc)
    actions = sts.GameAction.getAllActionsInState(gc)
    choice = playouts.construct_choice(gc, obs, actions)
    if choice is None:
        return taken, {"unsupported": True}
    rec = ref.normalize_record(sts, choice)
    flat_actions = (choice.card_actions + choice.relic_actions + choice.potion_actions
                    + choice.fixed_actions_list + choice.path_actions)
    decision = {"record": rec, "screen": int(gc.screen_state), "n": len(flat_actions)}
    # A reward screen with only "proceed" left (after a Neow card or potion pick)
    # has no counterpart in our engine, which leaves the screen at once.
    decision["proceed_only"] = (len(flat_actions) == 1 and gc.screen_state == sts.ScreenState.REWARDS
                                and not rec["cards_offered.cards"] and not rec["potions_offered"]
                                and not rec["relics_offered"])
    if len(flat_actions) > 1:
        logits, value = ref.silverbot_score(network, net, [rec])[0]
        chosen = int(np.argmax(logits)) if forced is None else forced
        decision.update(logits=logits, value=value, chosen=chosen)
    else:
        chosen = 0
    action = flat_actions[chosen]
    decision["action_bits"] = int(action.bits)
    decision["idx1"] = int(action.idx1)
    action.execute(gc)
    return taken, decision


def our_bits(screen, sts, bits, idx1):
    # Boss relic screen: silverbot uses RELIC i / SKIP; ours uses plain i / 3.
    if screen == int(sts.ScreenState.BOSS_RELIC_REWARDS):
        a = sts.GameAction(bits)
        return 3 if a.rewards_action_type == sts.RewardsActionType.SKIP else idx1
    return bits


KNOWN_CAUSES = ("neow_transform_curse", "potion_slot_full")


def divergence_cause(keys, theirs, mine):
    """Name the known engine difference behind a first record mismatch."""
    t, o = theirs["record"], mine.get("record", {})
    if keys == ["obs.deck.cards", "obs.deck.upgrades"] and len(o["obs.deck.cards"]) == len(t["obs.deck.cards"]) + 1:
        return "neow_transform_curse"  # ours adds a curse on Neow "transform two cards"
    if keys == ["potions_offered"] and len(o["potions_offered"]) < len(t["potions_offered"]):
        return "potion_slot_full"  # ours offers reward potions only with a free slot
    return "other"


def cmd_early(n_seeds, seed_start, asc, repo, ckpt, one_combat, weights, outdir):
    sts, network = ref.load_silverbot(repo)
    from silverbot import playouts
    net = ref.load_net(network, ckpt)
    os.makedirs(outdir, exist_ok=True)
    totals = {"seeds": 0, "branches": 0, "decisions": 0, "identical_records": 0, "scored": 0,
              "argmax_disagree": 0, "unsupported": 0, "proceed_absent": 0, "max_abs_logit_diff": 0.0,
              "max_abs_value_diff": 0.0, "diverged_branches": {}}
    mismatches = []
    for seed in range(seed_start, seed_start + n_seeds):
        totals["seeds"] += 1
        probe = sts.GameContext(sts.CharacterClass.IRONCLAD, seed, asc)
        n_neow = len([a for a in sts.GameAction.getAllActionsInState(probe)])
        for neow in range(n_neow):
            gc = sts.GameContext(sts.CharacterClass.IRONCLAD, seed, asc)
            plan, decisions = [], []
            forced = neow
            while gc.screen_state != sts.ScreenState.BATTLE and gc.outcome == sts.GameOutcome.UNDECIDED and len(plan) < 40:
                taken, decision = their_decision(sts, network, net, playouts, gc, forced)
                forced = None
                plan += [{"bits": b, "record": False} for b, _ in taken]
                if decision is None:
                    break
                if decision.get("unsupported"):
                    totals["unsupported"] += 1
                    break
                plan.append({"bits": our_bits(decision["screen"], sts, decision["action_bits"], decision["idx1"]),
                             "record": True, "proceed_only": decision["proceed_only"]})
                decisions.append(decision)
            totals["branches"] += 1
            tag = f"{seed}-neow{neow}"
            plan_path = os.path.join(outdir, f"plan-{tag}.json")
            ours_path = os.path.join(outdir, f"ours-{tag}.jsonl")
            json.dump(plan, open(plan_path, "w"))
            # one_combat loads its default models relative to the repository root.
            subprocess.run([os.path.abspath(one_combat), "heart1replay", os.path.abspath(weights), str(asc), str(seed),
                            os.path.abspath(plan_path), os.path.abspath(ours_path)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           cwd=os.path.dirname(os.path.dirname(os.path.abspath(one_combat))))
            ours = [json.loads(line) for line in open(ours_path)]
            invalid = next((row for row in ours if "invalid_action" in row), None)
            ours = [row for row in ours if "invalid_action" not in row]
            # Compare up to the first divergence: after it the states differ by construction.
            divergence = None
            for theirs, mine in zip(decisions, ours):
                if mine.get("skipped") == "proceed_absent":
                    totals["proceed_absent"] += 1
                    continue
                totals["decisions"] += 1
                if mine.get("record") != theirs["record"]:
                    keys = sorted(k for k in theirs["record"] if mine.get("record", {}).get(k) != theirs["record"][k])
                    divergence = {"branch": tag, "step": mine["step"], "cause": divergence_cause(keys, theirs, mine),
                                  "keys": keys, "theirs": {k: theirs["record"][k] for k in keys},
                                  "ours": {k: mine.get("record", {}).get(k) for k in keys}}
                    break
                totals["identical_records"] += 1
                if "logits" in theirs and "logits" in mine:
                    totals["scored"] += 1
                    diff, same = ref.compare(mine["logits"], theirs["logits"])
                    totals["max_abs_logit_diff"] = max(totals["max_abs_logit_diff"], diff)
                    totals["max_abs_value_diff"] = max(totals["max_abs_value_diff"], abs(mine["value"] - theirs["value"]))
                    totals["argmax_disagree"] += 0 if same else 1
            if divergence is None and invalid is not None:
                # One of silverbot's actions is illegal in our engine.
                divergence = {"branch": tag, "step": invalid["step"], "cause": "invalid_action",
                              "action_bits": invalid["invalid_action"]}
            if divergence is not None:
                mismatches.append(divergence)
                totals["diverged_branches"][divergence["cause"]] = totals["diverged_branches"].get(divergence["cause"], 0) + 1
    json.dump({"summary": totals, "mismatches": mismatches}, open(os.path.join(outdir, "early-summary.json"), "w"), indent=1)
    print(json.dumps(totals))
    # Known engine differences are reported, not failures; anything else fails.
    unexplained = sum(n for cause, n in totals["diverged_branches"].items() if cause not in KNOWN_CAUSES)
    return 0 if totals["argmax_disagree"] == 0 and unexplained == 0 else 1


def cmd_trace(n_seeds, seed_start, asc, repo, ckpt, sims, out_path):
    sts, network = ref.load_silverbot(repo)
    from silverbot import playouts
    net = ref.load_net(network, ckpt)
    with open(out_path, "w") as out:
        for seed in range(seed_start, seed_start + n_seeds):
            gc = sts.GameContext(sts.CharacterClass.IRONCLAD, seed, asc)
            agent = sts.Agent()
            agent.simulation_count_base = sims
            agent.verbosity_level = 0
            while gc.outcome == sts.GameOutcome.UNDECIDED:
                if gc.screen_state == sts.ScreenState.BATTLE:
                    agent.playout_battle(gc)
                    continue
                _, decision = their_decision(sts, network, net, playouts, gc)
                if decision is None:
                    continue
                if decision.get("unsupported"):
                    agent.pick_gameaction(gc).execute(gc)
                    continue
                if "logits" in decision:
                    out.write(json.dumps({"seed": seed, "floor": int(gc.floor_num), "record": decision["record"],
                                          "silverbot_logits": decision["logits"],
                                          "silverbot_value": decision["value"]}) + "\n")
            print(f"seed {seed}: floor {gc.floor_num} outcome {gc.outcome}", flush=True)
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in ("early", "trace"):
        sys.exit(__doc__)
    args = sys.argv[2:]
    if sys.argv[1] == "early" and len(args) == 8:
        sys.exit(cmd_early(int(args[0]), int(args[1]), int(args[2]), *args[3:]))
    if sys.argv[1] == "trace" and len(args) == 7:
        sys.exit(cmd_trace(int(args[0]), int(args[1]), int(args[2]), args[3], args[4], int(args[5]), args[6]))
    sys.exit(__doc__)
