"""student_sel vs expert picks. usage: analyze.py decisions.jsonl scores.jsonl meta.jsonl OUT_PREFIX"""
import collections, json, math, sys, random

dec_path, score_path, meta_path, outp = sys.argv[1:5]
meta = {json.loads(l)["run"]: json.loads(l) for l in open(meta_path)}

# Merge boss-marginal rows: average probabilities over the candidate bosses.
groups = collections.OrderedDict()
for dl, sl in zip(open(dec_path), open(score_path)):
    d = json.loads(dl); s = json.loads(sl)
    lg = s["logits"]; m = max(lg); e = [math.exp(x - m) for x in lg]; z = sum(e); p = [x / z for x in e]
    key = (d["run"], d["floor"], d["type"], json.dumps(d["labels"]), d["expert"])
    g = groups.get(key)
    if g is None:
        groups[key] = g = {"d": d, "p": [0.0] * len(p), "n": 0}
    g["p"] = [a + b for a, b in zip(g["p"], p)]; g["n"] += 1

rows = []
for g in groups.values():
    d = g["d"]; p = [x / g["n"] for x in g["p"]]
    if len(p) != len(d["labels"]): continue
    # Collapse identical labels (copies of one card in smith/remove lists).
    labs = []; pp = []
    for l, x in zip(d["labels"], p):
        if l in labs: pp[labs.index(l)] += x
        else: labs.append(l); pp.append(x)
    exp_l = d["labels"][d["expert"]]
    if len(labs) < 2: continue
    d = dict(d); d["labels"] = labs; d["expert"] = labs.index(exp_l); p = pp
    m = meta.get(d["run"], {})
    rows.append({"run": d["run"], "floor": d["floor"], "type": d["type"], "labels": d["labels"], "expert": d["expert"],
                 "p": p, "argmax": max(range(len(p)), key=p.__getitem__), "victory": d["victory"],
                 "deck_ok": m.get("deck_diff", 99) <= 2, "flags": d["flags"], "hp": d["record"]["obs.fixed_observation"][0],
                 "mhp": d["record"]["obs.fixed_observation"][1], "act": d["record"]["obs.act"],
                 "deck": len(d["record"]["obs.deck.cards"]), "rec": d["record"]})


def summarize(rs):
    n = len(rs)
    if not n: return None
    agree = sum(r["argmax"] == r["expert"] for r in rs) / n
    pexp = sum(r["p"][r["expert"]] for r in rs) / n
    nll = -sum(math.log(max(r["p"][r["expert"]], 1e-9)) for r in rs) / n
    rnd = sum(1 / len(r["p"]) for r in rs) / n
    conf = sum(max(r["p"]) for r in rs) / n
    # confident disagreements: student >= 0.9 on a non-expert action
    cd = sum(r["argmax"] != r["expert"] and max(r["p"]) >= 0.9 for r in rs) / n
    # bootstrap CI on agreement by run
    byrun = collections.defaultdict(list)
    for r in rs: byrun[r["run"]].append(r["argmax"] == r["expert"])
    keys = list(byrun); random.seed(1); bs = []
    for _ in range(300):
        smp = [k for k in (random.choice(keys) for _ in keys)]
        tot = sum(len(byrun[k]) for k in smp); bs.append(sum(sum(byrun[k]) for k in smp) / tot)
    bs.sort()
    return {"n": n, "runs": len(keys), "top1_agree": round(agree, 3), "ci90": [round(bs[15], 3), round(bs[284], 3)],
            "p_expert": round(pexp, 3), "nll": round(nll, 3), "random_top1": round(rnd, 3),
            "student_conf": round(conf, 3), "confident_disagree": round(cd, 3)}


out = {}
types = sorted({r["type"] for r in rows})
base = [r for r in rows if r["deck_ok"]]
out["by_type"] = {t: summarize([r for r in base if r["type"] == t]) for t in types}
out["by_type_all_runs"] = {t: summarize([r for r in rows if r["type"] == t]) for t in types}
out["by_type_act"] = {f"{t}|act{a}": summarize([r for r in base if r["type"] == t and r["act"] == a])
                      for t in types for a in (1, 2, 3, 4) if any(r["type"] == t and r["act"] == a for r in base)}
out["by_type_victory"] = {f"{t}|win={v}": summarize([r for r in base if r["type"] == t and r["victory"] == v])
                          for t in types for v in (True, False)}

# Card rewards: skip rates and per-card take rates.
cr = [r for r in base if r["type"].startswith("card_reward")]
def is_skip(lbl): return lbl in ("SKIP", "SINGING_BOWL")
exp_skip = sum(is_skip(r["labels"][r["expert"]]) for r in cr) / len(cr)
stu_skip = sum(is_skip(r["labels"][r["argmax"]]) for r in cr) / len(cr)
out["card_reward_skip"] = {"expert": round(exp_skip, 3), "student_argmax": round(stu_skip, 3),
                           "by_act": {a: {"expert": round(sum(is_skip(r["labels"][r["expert"]]) for r in cr if r["act"] == a) / max(1, sum(r["act"] == a for r in cr)), 3),
                                          "student": round(sum(is_skip(r["labels"][r["argmax"]]) for r in cr if r["act"] == a) / max(1, sum(r["act"] == a for r in cr)), 3)}
                                      for a in (1, 2, 3, 4)}}
offered = collections.Counter(); etake = collections.Counter(); stake = collections.Counter()
for r in cr:
    for i, l in enumerate(r["labels"]):
        if is_skip(l): continue
        c = l.split("+")[0]; offered[c] += 1; etake[c] += i == r["expert"]; stake[c] += i == r["argmax"]
card_tab = sorted(((c, offered[c], etake[c] / offered[c], stake[c] / offered[c]) for c in offered if offered[c] >= 40),
                  key=lambda x: x[3] - x[2])
out["card_take_rates"] = [{"card": c, "offered": n, "expert": round(e, 3), "student": round(s, 3), "diff": round(s - e, 3)}
                          for c, n, e, s in card_tab]
# Confusion: when they disagree, what did each pick
conf_pairs = collections.Counter()
for r in cr:
    if r["argmax"] != r["expert"]:
        conf_pairs[(r["labels"][r["expert"]].split("+")[0], r["labels"][r["argmax"]].split("+")[0])] += 1
out["card_disagree_pairs_expert_vs_student"] = [[a, b, n] for (a, b), n in conf_pairs.most_common(40)]

# Rest: by HP fraction
rest = [r for r in base if r["type"] == "rest"]
bins = [(0, .4), (.4, .6), (.6, .8), (.8, 1.01)]
out["rest_by_hp"] = {}
for lo, hi in bins:
    rs = [r for r in rest if lo <= r["hp"] / max(1, r["mhp"]) < hi]
    ec = collections.Counter(r["labels"][r["expert"]] for r in rs); sc = collections.Counter(r["labels"][r["argmax"]] for r in rs)
    out["rest_by_hp"][f"{lo}-{hi}"] = {"n": len(rs), "expert": {k: round(v / len(rs), 3) for k, v in ec.items()},
                                       "student": {k: round(v / len(rs), 3) for k, v in sc.items()}} if rs else None
rc = collections.Counter((r["labels"][r["expert"]], r["labels"][r["argmax"]]) for r in rest)
out["rest_confusion_expert_student"] = [[a, b, n] for (a, b), n in rc.most_common()]

# Boss relics
br = [r for r in base if r["type"] == "boss_relic"]
off = collections.Counter(); et = collections.Counter(); st = collections.Counter()
for r in br:
    for i, l in enumerate(r["labels"]):
        off[l] += 1; et[l] += i == r["expert"]; st[l] += i == r["argmax"]
out["boss_relic_take"] = sorted([{"relic": k, "offered": off[k], "expert": round(et[k] / off[k], 3), "student": round(st[k] / off[k], 3)}
                                 for k in off if off[k] >= 15], key=lambda x: x["student"] - x["expert"])

# Map: classify by room type of chosen next node
mp = [r for r in base if r["type"] == "map"]
def room(l): return l.split(":")[1]
out["map_room_choice"] = {}
mc = collections.Counter((room(r["labels"][r["expert"]]), room(r["labels"][r["argmax"]])) for r in mp if r["argmax"] != r["expert"])
out["map_disagree_room_pairs_expert_vs_student"] = [[a, b, n] for (a, b), n in mc.most_common(20)]
for a in (1, 2, 3):
    rs = [r for r in mp if r["act"] == a]
    ee = sum(room(r["labels"][r["expert"]]) == "E" for r in rs); se = sum(room(r["labels"][r["argmax"]]) == "E" for r in rs)
    eo = sum(any(room(l) == "E" for l in r["labels"]) for r in rs)
    out["map_room_choice"][f"act{a}"] = {"n": len(rs), "elite_offered": eo, "expert_elite": ee, "student_elite": se}

# Smith / remove targets
for t in ("smith", "shop_remove"):
    rs = [r for r in base if r["type"] == t]
    ec = collections.Counter(r["labels"][r["expert"]].split("+")[0] for r in rs)
    sc = collections.Counter(r["labels"][r["argmax"]].split("+")[0] for r in rs)
    out[t + "_targets"] = {"expert": ec.most_common(15), "student": sc.most_common(15)}

json.dump(out, open(outp + "summary.json", "w"), indent=1)
with open(outp + "rows.jsonl", "w") as f:
    for r in rows:
        f.write(json.dumps({k: v for k, v in r.items() if k != "rec"}) + "\n")
for t, s in out["by_type"].items(): print(t, s)
print("skip", out["card_reward_skip"])
