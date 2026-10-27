"""Offline gates for an expert-anchored candidate vs student_sel.

usage: gates.py DATA_DIR BASE_EXP.jsonl CAND_EXP.jsonl BOT_RECORDS BASE_BOT.jsonl CAND_BOT.jsonl OUT.json
DATA_DIR: make_dataset output (expert rows of held-out files exp-*.capture with seed % 8 == 7).
*_EXP.jsonl: heart1score of those held-out expert records in file order (see gates.sh); *_BOT.jsonl: heart1score
of all bot records. Gate 1: expert top-1 on card rewards and rest sites up >= 8 pp. Gate 2: argmax change share on
bot states per screen (> 40% on any screen -> prefer the lower alpha). Also writes changed bot decisions for the
hand spot check.
"""
import collections, glob, gzip, json, os, sys

data, be, ce, brec, bb, cb, outp = sys.argv[1:8]
SCREENS = {1: "event", 2: "rewards", 3: "boss_relic", 4: "card_select", 5: "map", 6: "treasure", 7: "rest", 8: "shop"}
rows = []
for f in sorted(glob.glob(os.path.join(data, "exp-*.capture.jsonl.gz"))):
    if int(f.split("exp-")[1].split(".")[0]) % 8 != 7: continue
    rows += [json.loads(l) for l in gzip.open(f, "rt")]
base = [json.loads(l) for l in open(be)]; cand = [json.loads(l) for l in open(ce)]
assert len(rows) == len(base) == len(cand), (len(rows), len(base), len(cand))
res = {"expert_heldout": {}, "bot_drift": {}}
agg = collections.defaultdict(lambda: [0, 0, 0])
for r, b, c in zip(rows, base, cand):
    t = r["expert_type"]; t = "card_reward" if t.startswith("card_reward") else t
    exp = max(range(len(r["logits"])), key=r["logits"].__getitem__) if False else None
    # expert token = the target's argmax at alpha >= 0.5; in general the token(s) carrying the alpha mass:
    # recover it as the token whose target exceeds the base probability mass the most.
    import math
    lg = b["logits"]; m = max(lg); e = [math.exp(x - m) for x in lg]; z = sum(e)
    gain = [math.exp(t_) - e_ / z for t_, e_ in zip(r["logits"], e)]
    exp = {i for i, g in enumerate(gain) if g > 1e-9}
    a = agg[t]; a[0] += 1; a[1] += b["argmax"] in exp; a[2] += c["argmax"] in exp
for t, (n, sb, sc) in sorted(agg.items()):
    res["expert_heldout"][t] = {"n": n, "student_sel": round(sb / n, 3), "candidate": round(sc / n, 3),
                                "gain_pp": round(100 * (sc - sb) / n, 1)}
recs = [json.loads(l) for l in open(brec)]
B = [json.loads(l) for l in open(bb)]; C = [json.loads(l) for l in open(cb)]
drift = collections.defaultdict(lambda: [0, 0]); changed = collections.defaultdict(list)
for rec, b, c in zip(recs, B, C):
    r = rec["record"]; s = SCREENS.get(r["screen_state"], "?")
    if s == "card_select": s += ":%d" % r["select_screen_type"]
    d = drift[s]; d[0] += 1
    if b["argmax"] != c["argmax"]:
        d[1] += 1
        if len(changed[s]) < 40: changed[s].append({"seed": rec["seed"], "act": rec["act"], "base": b["argmax"], "cand": c["argmax"],
                                                    "offered_cards": r["cards_offered.cards"], "relics": r["relics_offered"],
                                                    "fixed": [f["action"] for f in r["fixed_actions"]], "paths": r["paths_offered"],
                                                    "hp": r["obs.fixed_observation"][:2], "floor": r["obs.fixed_observation"][3]})
res["bot_drift"] = {s: {"n": n, "changed": round(k / n, 3)} for s, (n, k) in sorted(drift.items())}
res["changed_examples"] = changed
json.dump(res, open(outp, "w"), indent=1)
print(json.dumps({k: res[k] for k in ("expert_heldout", "bot_drift")}, indent=1))
