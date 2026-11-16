"""Who decides in heart1 PPO games: decision sources, fallbacks and rule-shadow counts from trajectory parts (#1055).

Read-only and offline. Input: heart1-ppo-traj-v1 JSONL parts as `ppoStep`/`ppoEndGame` write them
(apps/one_combat/heart1_policy.cpp), plain or gzipped (a `ppo_cloud.py` store keeps them gzipped in its
traj-NNNN-pK refs). No net is evaluated and no game is played.

    python3 tools/heart1/ppo_decision_sources.py PART_OR_DIR [...] [--out report.json]

Counts (all per decision line unless stated; a "decision" is one net call, so a reward screen where the net first
takes a potion and then leaves is two decisions):
  games, sources       decision lines by source (heart1_ppo = more than one choice, heart1_ppo_single = one),
                       fallback lines by reason (the old chain decided), auto_gold (gold rewards taken before the
                       net sees the screen), each also per game.
  screens              decisions per ScreenState, split multi/single choice.
  discarded_potions    the potion each chosen discard token threw away (Blood Potion, Fruit Juice and Entropic Brew
                       could be drunk out of combat instead; drink tokens exist since #1055).
  tokens               PPO-only fixed tokens: decisions that offer the token and decisions that choose it
                       (discard_potion, drink_potion = an out-of-combat drink, match_and_keep, event_generic = an
                       event option without a silverbot mapping, take_key, recall, open_chest).
  relics_left          rewards decisions where the net chose leave (FA_SKIP) while a relic was still offered,
                       one row per relic left: `reviewed_exception` (apps/one_combat/ooc_tree_rules.cpp
                       reviewedRewardRelic, which the old relic rule also leaves to the policy), `key_on_screen`
                       (a key token on the same screen), else `rule_would_take` (rewardRelicRuleAction would have
                       taken it), with act and relic name for the last class.
  treasure             chest decisions: opened / skipped, with and without Cursed Key (the old chest rule opens
                       every chest without Cursed Key).
  boss_relic           boss-relic decisions: relic taken / skipped.
  sapphire             rewards decisions offering a key token next to a relic (Sapphire), by act: taken or not.
  ruby                 per game, the first rest-site decision in act >= 3 that offers Recall: recalled or not
                       (ADR-0041's Ruby rule recalls there).
"""
import argparse
import collections
import gzip
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RELICS_H = os.path.join(HERE, "..", "..", "include", "constants", "Relics.h")
POTIONS_H = os.path.join(HERE, "..", "..", "include", "constants", "Potions.h")

SCREENS = {0: "invalid", 1: "event", 2: "rewards", 3: "boss_relic", 4: "card_select", 5: "map", 6: "treasure",
           7: "rest", 8: "shop", 9: "battle"}
# apps/one_combat/heart1_policy.{h,cpp}: fixed-action ids.
FA_SKIP, FA_RECALL, FA_TAKE_KEY, FA_OPEN_CHEST = 1, 6, 164, 165
FA_DISCARD, FA_MATCH_FIRST, FA_MATCH_LAST, FA_EVENT_FIRST, FA_DRINK = 166, 167, 169, 170, 178
# apps/one_combat/ooc_tree_rules.cpp reviewedRewardRelic (Philipp's list, 2026-10-07).
REVIEWED_RELICS = ("BOTTLED_FLAME", "BOTTLED_LIGHTNING", "BOTTLED_TORNADO", "DEAD_BRANCH", "TUNGSTEN_ROD",
                   "UNCEASING_TOP", "JUZU_BRACELET")


def enum_names(path, array):
    text = open(path, encoding="utf-8").read()
    body = re.search(array + r"\[\]\s*=?\s*\{(.*?)\};", text, re.S)
    if not body:
        raise SystemExit(f"cannot find {array} in {path}")
    return [x.strip().strip('"') for x in body.group(1).split(",") if x.strip()]


def relic_names(path=RELICS_H):
    return enum_names(path, "relicEnumNames")


def potion_names(path=POTIONS_H):
    return enum_names(path, "potionEnumNames")


def token_class(action):
    if action == FA_DISCARD:
        return "discard_potion"
    if FA_MATCH_FIRST <= action <= FA_MATCH_LAST:
        return "match_and_keep"
    if FA_EVENT_FIRST <= action < FA_DRINK:
        return "event_generic"
    if action == FA_DRINK:
        return "drink_potion"
    return {FA_TAKE_KEY: "take_key", FA_RECALL: "recall", FA_OPEN_CHEST: "open_chest"}.get(action)


def chosen_fixed(d):
    """The chosen fixed action id, or None when the net chose a card, relic, potion or path token.
    Token order is buildChoice's: cards, relics, potions, fixed actions, paths."""
    r = d["record"]
    i = d["chosen"] - len(r["cards_offered.cards"]) - len(r["relics_offered"]) - len(r["potions_offered"])
    fixed = r["fixed_actions"]
    return fixed[i]["action"] if 0 <= i < len(fixed) else None


def part_files(paths):
    out = []
    for p in paths:
        if os.path.isdir(p):
            out += sorted(os.path.join(p, f) for f in os.listdir(p) if f.endswith((".jsonl", ".jsonl.gz")))
        else:
            out.append(p)
    if not out:
        raise SystemExit("no trajectory parts given")
    return out


def lines(path):
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if line.strip():
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as e:
                    raise SystemExit(f"{path}:{n}: {e}")


def tally(paths, names, potions=None):
    potions = potions if potions is not None else potion_names()
    C = collections.Counter
    reviewed = {names.index(n) for n in REVIEWED_RELICS}
    cursed_key = names.index("CURSED_KEY")
    games = 0
    sources, fallbacks, fallback_where = C(), C(), C()
    auto_gold = 0
    screens = collections.defaultdict(C)
    offered, chosen = C(), C()
    relics_left, relics_left_names, relics_left_acts = C(), C(), C()
    treasure, boss_relic, sapphire = C(), C(), C()
    ruby, discarded = C(), C()
    for path in part_files(paths):
        ruby_seen = set()
        for d in lines(path):
            kind = d.get("type")
            if kind == "game":
                games += 1
                auto_gold += int(d.get("auto_gold", 0))
                continue
            if kind == "fallback":
                fallbacks[d["reason"]] += 1
                fallback_where[f'{d["reason"]}:{SCREENS.get(d["screen"], d["screen"])}:event{d.get("event")}'] += 1
                continue
            if kind != "decision":
                continue
            sources[d["source"]] += 1
            screen = SCREENS.get(d["screen"], str(d["screen"]))
            screens[screen]["multi" if d["n"] > 1 else "single"] += 1
            r = d["record"]
            fixed = [x["action"] for x in r["fixed_actions"]]
            for cls in {token_class(a) for a in fixed} - {None}:
                offered[cls] += 1
            pick = chosen_fixed(d)
            if pick is not None and token_class(pick):
                chosen[token_class(pick)] += 1
            if pick == FA_DISCARD:
                p = r["fixed_actions"][d["chosen"] - len(r["cards_offered.cards"]) - len(r["relics_offered"])
                                       - len(r["potions_offered"])].get("potion", -1)
                discarded[potions[p] if 0 <= p < len(potions) else str(p)] += 1
            if screen == "rewards" and pick == FA_SKIP:
                key = FA_TAKE_KEY in fixed
                for rel in r["relics_offered"]:
                    cls = "reviewed_exception" if rel in reviewed else "key_on_screen" if key else "rule_would_take"
                    relics_left[cls] += 1
                    if cls == "rule_would_take":
                        relics_left_names[names[rel] if 0 <= rel < len(names) else str(rel)] += 1
                        relics_left_acts[f'act{d["act"]}'] += 1
            if screen == "rewards" and FA_TAKE_KEY in fixed and r["relics_offered"]:
                sapphire[f'act{d["act"]}:{"taken" if pick == FA_TAKE_KEY else "not_taken"}'] += 1
            if screen == "treasure" and d["n"] > 1:
                ck = "cursed_key" if cursed_key in r["obs.relics.relics"] else "no_cursed_key"
                treasure[f'{ck}:{"open" if pick == FA_OPEN_CHEST else "skip"}'] += 1
            if screen == "boss_relic":
                boss_relic["skip" if pick == FA_SKIP else "relic"] += 1
            if screen == "rest" and d["act"] >= 3 and FA_RECALL in fixed and d["seed"] not in ruby_seen:
                ruby_seen.add(d["seed"])
                ruby["recall" if pick == FA_RECALL else "other"] += 1
    per_game = lambda c: {k: round(v / games, 3) for k, v in sorted(c.items())} if games else {}
    return {
        "games": games,
        "sources": dict(sources), "sources_per_game": per_game(sources),
        "fallbacks": dict(fallbacks), "fallbacks_per_game": per_game(fallbacks),
        "fallback_where": dict(fallback_where.most_common()),
        "auto_gold": auto_gold, "auto_gold_per_game": round(auto_gold / games, 3) if games else None,
        "screens": {k: dict(v) for k, v in sorted(screens.items())},
        "tokens": {k: {"offered": offered[k], "chosen": chosen[k]} for k in
                   ("discard_potion", "drink_potion", "match_and_keep", "event_generic", "take_key", "recall",
                    "open_chest")},
        "discarded_potions": dict(discarded.most_common()),
        "relics_left": dict(relics_left), "relics_left_rule_would_take_by_act": dict(sorted(relics_left_acts.items())),
        "relics_left_rule_would_take_by_relic": dict(relics_left_names.most_common()),
        "treasure": dict(sorted(treasure.items())), "boss_relic": dict(boss_relic),
        "sapphire": dict(sorted(sapphire.items())), "ruby_first_act3_rest": dict(ruby),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("parts", nargs="+", help="trajectory part files (.jsonl / .jsonl.gz) or directories of them")
    ap.add_argument("--out", help="write the JSON report here (default: stdout)")
    ap.add_argument("--relics-h", default=RELICS_H, help="include/constants/Relics.h (relic names)")
    ap.add_argument("--potions-h", default=POTIONS_H, help="include/constants/Potions.h (potion names)")
    args = ap.parse_args(argv)
    report = tally(args.parts, relic_names(args.relics_h), potion_names(args.potions_h))
    text = json.dumps(report, indent=1, sort_keys=False)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    else:
        sys.stdout.write(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
