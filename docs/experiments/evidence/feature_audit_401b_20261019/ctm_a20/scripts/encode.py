#!/usr/bin/env python3
"""#401b ctm_a20: encode VALIDATION rows (main corpus) into the CTM model inputs + labels.
Uses the repo's own encoder (combat_transition_model_experiment._encode_row). Also builds the
Lizard-stripped ordinary / reserve inputs for active-Lizard rows (runtime withoutLizard, reserve curHp)."""
import copy, json, sys
import numpy as np
sys.path.insert(0, "/home/user/sts_ai")
from tools import combat_transition_surrogate as s
from tools import combat_transition_model_experiment as mx
src, out = sys.argv[1], sys.argv[2]
E, R, P = s._ENCOUNTER_IDS, s._RELIC_IDS, s._POTION_IDS
BOSS = {E[n] for n in ("SLIME_BOSS","HEXAGHOST","THE_GUARDIAN","CHAMP","COLLECTOR","AUTOMATON","DONU_AND_DECA","TIME_EATER","AWAKENED_ONE","THE_HEART")}
LIZ, BLOOM = R["LIZARD_TAIL"], R["MARK_OF_THE_BLOOM"]
keys = ("globals_continuous","global_categories","cards","relics","potions","card_mask","relic_mask")
def enc(pi):
    row = dict(predictorInput=pi, sourceSeed=0, fightIdx=0, transition=dict(combatOutcome=2, post={}))
    return mx._encode_row(row)[:7]
cols = {k: [] for k in keys}; meta = {k: [] for k in ("seed","fight","act","floor","room","encounter","outcome","pre_hp","pre_max","post_hp","post_max","smoke_used","capacity","boss","brew","smoke","fairy","lizard","bloom","pre_pot","post_pot")}
liz = {"idx": [], "ord": {k: [] for k in keys}, "res": {k: [] for k in keys}}
n = 0
for line in open(src):
    row = __import__("json").loads(line)
    t = row["transition"]
    if t is None or not row["runValid"]: continue
    pi = row["predictorInput"]; g = pi["globals"]
    for k, v in zip(keys, enc(pi)): cols[k].append(v)
    pots = [p["potionId"] for p in pi["potions"]]
    rel = [(r["relicId"], r["data"]) for r in pi["relics"]]
    m = meta
    m["seed"].append(row["sourceSeed"]); m["fight"].append(row["fightIdx"]); m["act"].append(g["act"]); m["floor"].append(g["floor"])
    m["room"].append(row["roomClass"]); m["encounter"].append(g["encounter"]); m["outcome"].append(t["combatOutcome"])
    m["pre_hp"].append(t["pre"]["curHp"]); m["pre_max"].append(t["pre"]["maxHp"])
    m["post_hp"].append(t["post"].get("curHp", 0)); m["post_max"].append(t["post"].get("maxHp", 0))
    m["smoke_used"].append(bool(t["post"].get("smokeBombUsed", False))); m["capacity"].append(g["potionCapacity"])
    m["boss"].append(g["encounter"] in BOSS); m["brew"].append(P["ENTROPIC_BREW"] in pots); m["smoke"].append(P["SMOKE_BOMB"] in pots)
    m["fairy"].append(P["FAIRY_POTION"] in pots or P["FAIRY_POTION"] in t["pre"]["potions"])
    active = any(r == LIZ and d == 1 for r, d in rel); m["lizard"].append(active); m["bloom"].append(any(r == BLOOM for r, _ in rel))
    m["pre_pot"].append(t["pre"]["potions"]); m["post_pot"].append(t["post"].get("potions", [0]*5))
    if active:
        o = copy.deepcopy(pi); o["relics"] = [r for r in o["relics"] if r["relicId"] != LIZ]
        for i, r in enumerate(o["relics"]): r["orderIndex"] = i
        rs = copy.deepcopy(o); rs["globals"]["curHp"] = min(g["maxHp"], g["curHp"] + g["maxHp"] // 2)
        liz["idx"].append(n)
        for k, v in zip(keys, enc(o)): liz["ord"][k].append(v)
        for k, v in zip(keys, enc(rs)): liz["res"][k].append(v)
    n += 1
arr = {k: np.stack(v) for k, v in cols.items()}
arr.update({"m_" + k: np.asarray(v) for k, v in meta.items()})
arr["liz_idx"] = np.asarray(liz["idx"], np.int64)
for b in ("ord", "res"):
    for k in keys: arr[f"liz_{b}_{k}"] = np.stack(liz[b][k]) if liz["idx"] else np.zeros((0,))
np.savez(out, **arr)
print(json.dumps({"rows": n, "lizard": len(liz["idx"]), "brew": int(arr["m_brew"].sum()), "smoke": int(arr["m_smoke"].sum()),
                  "acts": {int(a): int((arr["m_act"] == a).sum()) for a in np.unique(arr["m_act"])},
                  "rooms": {r: int((arr["m_room"] == r).sum()) for r in np.unique(arr["m_room"])}}))
