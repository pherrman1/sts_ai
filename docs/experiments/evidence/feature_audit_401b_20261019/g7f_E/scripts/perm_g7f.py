"""Grouped permutation importance (#401 Stage 1) for g7f_E on its validation fold (r_seed % 5 == 3).
State groups: one random permutation of all validation roots per repeat; root r receives the group's raw
columns of root pi[r]; derived inputs (encounter embedding, monster id/intent embeddings, target-slot
features) are recomputed from the permuted raw state. Candidate (action) groups: roots are permuted within
strata of equal candidate count; edge j of root r receives the group's columns (and, for the targeting
group, the target slot) of edge j of root sigma[r]. Metric: per-root CE vs search-visit shares, top-1,
value-head squared error. CI: 1,000 cluster-bootstrap resamples over (source, r_seed) clusters of the
per-root delta averaged over repeats.
usage: perm_g7f.py ARTIFACT.txt MODEL.pt VAL.npz PHASE OUT.json [REPEATS]
PHASE: groups | sub | single"""
import sys, json, time, numpy as np, torch
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import g7f_model as G
torch.set_num_threads(1)
art, ckpt, valp, phase, out = sys.argv[1:6]
REP = int(sys.argv[6]) if len(sys.argv) > 6 else 5
NBOOT = 1000
t0 = time.time()
z = np.load(valp)
model = G.Model(art, ckpt)
names = model.names
st_idx = z["st_idx"].astype(np.int64); st_val = z["st_val"]; st_ptr = z["st_ptr"]
nedge = z["r_nedge"]; e_act = z["e_act"]; e_tgt = z["e_tgt"]
n = len(nedge); e_ptr = np.concatenate([[0], np.cumsum(nedge, dtype=np.int64)])
eroot = np.repeat(np.arange(n), nedge)
st_root = np.repeat(np.arange(n), np.diff(st_ptr))
vsum = np.add.reduceat(z["e_vis"], e_ptr[:-1])
share = (z["e_vis"] / np.maximum(vsum[eroot], 1)).astype(np.float32).astype(np.float64)
rv = z["r_val"]; hv = ~np.isnan(rv); rv0 = np.nan_to_num(rv)
src = z["r_src"]; tags = [str(t) for t in z["tags"]]
A4 = tags.index("g7a4")
key = src.astype(np.int64) * (1 << 40) + z["r_seed"]
_, clus = np.unique(key, return_inverse=True); ncl = clus.max() + 1
cl_src = np.zeros(ncl, np.int64); cl_src[clus] = src
boot_rng = np.random.default_rng(401)
BW = boot_rng.multinomial(ncl, np.full(ncl, 1.0 / ncl), size=NBOOT).astype(np.float64)   # NBOOT x ncl
# within-source bootstrap weights for the window/g7a4 breakdown use the same draws restricted by mask
def boot(delta, mask=None):
    m = np.ones(n, bool) if mask is None else mask
    cs = np.bincount(clus[m], weights=delta[m], minlength=ncl); cc = np.bincount(clus[m], minlength=ncl).astype(float)
    b = (BW @ cs) / np.maximum(BW @ cc, 1)
    return [float(delta[m].mean()), float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))]

def score(lg, val):
    ce, top = G.root_stats(lg, share, nedge)
    se = np.where(hv, (val - rv0) ** 2, 0.0)
    return ce, top, se

lg0, v0 = model.forward(st_idx, st_val, st_ptr, nedge, e_act, e_tgt)
ce0, top0, se0 = score(lg0, v0)
print(f"baseline ce {ce0.mean():.6f} top1 {top0.mean():.6f} value_mse {se0[hv].mean():.6f} ({time.time()-t0:.0f}s)", flush=True)

def perm_state(cols, rng):
    inG = np.zeros(G.S, bool); inG[cols] = True
    m = inG[st_idx]
    pi = rng.permutation(n); pinv = np.empty(n, np.int64); pinv[pi] = np.arange(n)
    nr = np.concatenate([st_root[~m], pinv[st_root[m]]])
    ni = np.concatenate([st_idx[~m], st_idx[m]]); nv = np.concatenate([st_val[~m], st_val[m]])
    o = np.argsort(nr, kind="stable")
    ptr = np.concatenate([[0], np.cumsum(np.bincount(nr, minlength=n))])
    return model.forward(ni[o], nv[o], ptr, nedge, e_act, e_tgt)

strata = [np.flatnonzero(nedge == k) for k in np.unique(nedge)]
def perm_action(cols, with_tgt, rng):
    sig = np.arange(n)
    for s in strata:
        sig[s] = s[rng.permutation(len(s))]
    srce = e_ptr[sig][eroot] + (np.arange(len(eroot)) - e_ptr[eroot])
    a = e_act.copy()
    if len(cols):
        a[:, cols] = e_act[srce][:, cols]
    t = e_tgt[srce] if with_tgt else e_tgt
    return model.forward(st_idx, st_val, st_ptr, nedge, a, t)

nm = {x: i for i, x in enumerate(names)}
R = lambda a, b: list(range(a, b + 1))
def cols_of(prefixes):  # names starting with any prefix followed by digits/slot pattern handled by caller
    return [i for i, x in enumerate(names[:G.S]) if any(x.startswith(p) for p in prefixes)]
STATE = {
    "ascension": [0],
    "encounter_id (+enc embedding)": [1],
    "turn/progress (turn, cards/attacks/skills played)": [2] + R(1755, 1757),
    "player HP/block (curHp, maxHp, block)": [3, 4, 5],
    "energy": [6],
    "player powers/statuses (str/dex/focus/artifact, p*, panacheCtr)": R(7, 10) + R(26, 49) + [1765],
    "monster aggregates (monAlive..monSumArt, incomingDmg, nAttacking)": R(11, 16) + [1662, 1663],
    "monster slots m0-m4 (+id/intent embeddings, target features)": R(1664, 1708),
    "hand (count, nAvail by type, hd* composition)": [17] + R(21, 24) + R(178, 548),
    "draw pile (count, dr*)": [18] + R(549, 919),
    "discard pile (count, ds*)": [19] + R(920, 1290),
    "exhaust pile (count, ex*)": [20] + R(1291, 1661),
    "relics (r*, relic counters)": R(50, 177) + R(1758, 1764),
    "potions (count, pot*, potionCap)": [25] + R(1709, 1752) + [1754],
    "gold": [1753],
}
ACTION = {  # action column indices (0..21) and whether the target slot moves with them
    "cand: action type (aIsCard/Potion/EndTurn/Select)": (R(0, 3), False),
    "cand: card id (aCardId -> card embedding)": ([4], False),
    "cand: card attributes (cost, upg, atk/skl/pow)": (R(5, 9), False),
    "cand: targeting (aTargetsEnemy, aTargetHp, target slot -> slot features)": ([10, 11], True),
    "cand: play order / obtain weight": ([12, 13], False),
    "cand: select-screen features (aSel*)": (R(14, 21), False),
}
REF = {"REF all state": ("state", list(range(G.S))), "REF all candidate (22 cols + target)": ("action", (list(range(22)), True)),
       "REF monsters all (aggregates + slots)": ("state", R(11, 16) + R(1662, 1708))}
slot = lambda ch: [1664 + 9 * k + ch for k in range(5)]
SUB = {
    "mon slot Id (+id embedding)": slot(0), "mon slot Hp": slot(1), "mon slot Block": slot(2),
    "mon slot Str": slot(3), "mon slot Intent (+intent embedding)": slot(4), "mon slot Atk": slot(5),
    "mon slot Vuln/Weak/Poison": slot(6) + slot(7) + slot(8),
    "hand counts (hand, nAtk/Skl/Pow/OtherAvail)": [17] + R(21, 24), "hand composition hd*": R(178, 548),
    "draw count": [18], "draw composition dr*": R(549, 919),
    "discard count": [19], "discard composition ds*": R(920, 1290),
    "exhaust count": [20], "exhaust composition ex*": R(1291, 1661),
    "player p* powers only": R(26, 49), "player str/dex/focus/artifact": R(7, 10),
    "relic counters only": R(1758, 1764), "relics r* only": R(50, 177),
    "potion slots pot* only": R(1709, 1752),
}

def run_group(name, kind, spec, reps, gseed):
    acc = {k: np.zeros(n) for k in ("ce", "top", "se")}
    per_rep = []
    for r in range(reps):
        rng = np.random.default_rng([gseed, r])
        if kind == "state":
            lg, v = perm_state(spec, rng)
        else:
            lg, v = perm_action(spec[0], spec[1], rng)
        ce, top, se = score(lg, v)
        d = {"ce": ce - ce0, "top": top - top0, "se": se - se0}
        for k in acc: acc[k] += d[k]
        per_rep.append({"d_ce": float(d["ce"].mean()), "d_top1": float(d["top"].mean()),
                        "d_value_mse": float(d["se"][hv].mean()),
                        "d_ce_window": float(d["ce"][src != A4].mean()), "d_ce_g7a4": float(d["ce"][src == A4].mean())})
    for k in acc: acc[k] /= reps
    hvm = hv
    res = {"group": name, "kind": kind, "repeats": reps,
           "d_ce": boot(acc["ce"]), "d_top1": boot(acc["top"]),
           "d_value_mse": boot(np.where(hv, acc["se"], 0.0) * (n / hv.sum())) if kind == "state" else [0.0, 0.0, 0.0],
           "d_ce_window": boot(acc["ce"], src != A4), "d_ce_g7a4": boot(acc["ce"], src == A4),
           "d_top1_window": boot(acc["top"], src != A4), "d_top1_g7a4": boot(acc["top"], src == A4),
           "d_ce_by_tag": {t: float(acc["ce"][src == i].mean()) for i, t in enumerate(tags)},
           "per_repeat": per_rep,
           "repeat_spread_d_ce": [float(min(p["d_ce"] for p in per_rep)), float(max(p["d_ce"] for p in per_rep)),
                                  float(np.std([p["d_ce"] for p in per_rep]))]}
    if kind == "state":
        res["columns"] = [names[c] for c in spec]
    else:
        res["columns"] = [names[G.S + c] for c in spec[0]] + (["e_tgt (target slot)"] if spec[1] else [])
    print(f"{name}: dCE {res['d_ce'][0]:+.5f} [{res['d_ce'][1]:+.5f},{res['d_ce'][2]:+.5f}] dTop1 {res['d_top1'][0]:+.4f} "
          f"win {res['d_ce_window'][0]:+.5f} a4 {res['d_ce_g7a4'][0]:+.5f} ({time.time()-t0:.0f}s)", flush=True)
    return res

base = {"roots": int(n), "edges": int(len(lg0)), "clusters": int(ncl), "ce": float(ce0.mean()), "top1": float(top0.mean()),
        "value_mse": float(se0[hv].mean()), "value_rows": int(hv.sum()),
        "ce_window": float(ce0[src != A4].mean()), "ce_g7a4": float(ce0[src == A4].mean()),
        "top1_window": float(top0[src != A4].mean()), "top1_g7a4": float(top0[src == A4].mean()),
        "roots_window": int((src != A4).sum()), "roots_g7a4": int((src == A4).sum()),
        "ce_by_tag": {t: float(ce0[src == i].mean()) for i, t in enumerate(tags)},
        "roots_by_tag": {t: int((src == i).sum()) for i, t in enumerate(tags)},
        "action_strata_singletons": int(sum(len(s) == 1 for s in strata)),
        "baseline_boot_ce": boot(ce0)}
results = {"phase": phase, "baseline": base, "groups": []}
if phase == "groups":
    jobs = [(k, "state", v) for k, v in STATE.items()] + [(k, "action", v) for k, v in ACTION.items()] + \
           [(k, v[0], v[1]) for k, v in REF.items()]
    results["group_columns"] = {k: [names[c] for c in v] for k, v in STATE.items()}
    results["group_columns"].update({k: [names[G.S + c] for c in v[0]] + (["e_tgt"] if v[1] else []) for k, v in ACTION.items()})
elif phase == "sub":
    jobs = [(k, "state", v) for k, v in SUB.items()]
else:  # single: individual columns named on the command line after REPEATS
    jobs = []
    for nmx in sys.argv[7].split(","):
        if nmx == "e_tgt":
            jobs.append(("e_tgt (target slot only)", "action", ([], True)))
        elif nm[nmx] >= G.S:
            jobs.append((nmx, "action", ([nm[nmx] - G.S], False)))
        else:
            jobs.append((nmx, "state", [nm[nmx]]))
import os
done = {}
if os.path.exists(out):  # resume after an interruption: keep finished groups (same per-group seeds)
    prev = json.load(open(out))
    if prev.get("phase") == phase:
        done = {g["group"]: g for g in prev["groups"]}
        print("resuming; kept", list(done), flush=True)
for gi, (k, kind, spec) in enumerate(jobs):
    if k in done:
        results["groups"].append(done[k]); continue
    results["groups"].append(run_group(k, kind, spec, REP, hash(k) % (2**31) if False else 7919 * (gi + 1) + {"groups": 0, "sub": 1, "single": 2}[phase]))
    json.dump(results, open(out, "w"), indent=1)
results["seconds"] = time.time() - t0
json.dump(results, open(out, "w"), indent=1)
print("done", time.time() - t0)
