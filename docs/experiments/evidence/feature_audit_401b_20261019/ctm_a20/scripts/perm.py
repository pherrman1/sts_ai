#!/usr/bin/env python3
"""#401b ctm_a20 Steps 2-3: grouped permutation importance of the fast DeepSets CTM (ae785ec2) on
main-corpus VALIDATION rows served directly by the fast child (no Entropic Brew, no active Lizard).
Per-row losses per head; a group's columns/token block are permuted jointly across rows (one row
permutation shared by every column of the group, so within-group correlation is kept); model-side
structural arguments (HP legality, potion inventory for the potion label, escape eligibility) keep
the true values. Survival uses the deployed §470 boss death-logit shift."""
import json, sys, time, zlib
import numpy as np, torch
sys.path.insert(0, sys.path[0]); import ctmlib as L
src, out = sys.argv[1], sys.argv[2]
REPEATS = int(sys.argv[3]) if len(sys.argv) > 3 else 5
d = dict(np.load(src, allow_pickle=False))
keep = ~(d["m_brew"].astype(bool) | d["m_lizard"].astype(bool))
A = {k: d[k][keep] for k in L.KEYS}; M = {k[2:]: d[k][keep] for k in d if k.startswith("m_")}
n = int(keep.sum()); model = L.load("fast"); meta = model.metadata
CLS = np.asarray(meta["hpClasses"]); DV = np.asarray(meta["maxHpClasses"]); C0 = int(CLS[0])
T = model.escape.t
win = M["outcome"] == 1
y_death = (~win).astype(float)
boss = M["boss"].astype(bool)
# labels
dlt = M["post_max"] - M["pre_max"]
didx = np.array([np.searchsorted(DV, v) if v in set(DV.tolist()) else -1 for v in dlt])
hcls = (M["post_hp"] - M["pre_hp"]) - C0
hp_ok = win & (didx >= 0) & (M["post_hp"] >= 1) & (M["post_hp"] <= M["post_max"]) & (hcls >= 0) & (hcls < len(CLS))
pre_pot = M["pre_pot"].astype(np.int64); post_pot = M["post_pot"].astype(np.int64)
SMOKE, BREW = 37, 17
cap = M["capacity"].astype(int)
elig = np.array([(not b) and any(p == SMOKE for p in pp[:c]) for pp, c, b in zip(pre_pot, cap, boss)])
used = (pre_pot > 1) & (post_pot == 1)
pmask = (used * (1 << np.arange(5))).sum(1)
trig = ((pre_pot == SMOKE) | (pre_pot == BREW)).any(1)
pot_ok = hp_ok & ~trig & (np.where(used, 1, pre_pot) == post_pot).all(1)
def legal_actions():
    L64 = np.zeros((n, 64), bool)
    for a in range(32):
        bits = np.array([(a >> s) & 1 for s in range(5)], bool)
        ok = ~((bits[None] & ~((pre_pot > 1) & (np.arange(5)[None] < cap[:, None]))).any(1))
        L64[:, a] = ok
    return L64   # no trigger potions on pot_ok rows: use actions (>=32) are illegal
LEG = legal_actions()
escaped = M["smoke_used"].astype(float)

@torch.inference_mode()
def hp_logits(z, delta_idx, esc):
    x = torch.cat((z, T["hp.delta_embedding.weight"][delta_idx], esc[:, None]), -1)
    h = torch.relu(x @ T["hp.hp.0.weight"].T + T["hp.hp.0.bias"])
    return h @ T["hp.hp.2.weight"].T + T["hp.hp.2.bias"]

@torch.inference_mode()
def losses(arrs):
    z = L.encode(model, arrs)
    sl = L.survival_logit(model, z["survival"]) - np.where(boss, L.BOSS_SHIFT, 0.0)
    p = np.clip(1 / (1 + np.exp(sl)), 1e-7, 1 - 1e-7)       # death probability
    surv = -(y_death * np.log(p) + (1 - y_death) * np.log(1 - p))
    brier = (p - y_death) ** 2
    lp_delta = torch.log_softmax(model.max_hp_head(z["max_hp"]), -1).double().numpy()
    maxhp = np.full(n, np.nan); maxhp[hp_ok] = -lp_delta[hp_ok, didx[hp_ok]]
    hp = np.full(n, np.nan); mae = np.full(n, np.nan)
    zh = z["hp"]; pre = torch.from_numpy(M["pre_hp"].astype(np.float64)); post_hp = M["post_hp"]
    ep = torch.sigmoid(zh @ T["escape.escape.weight"][0] + T["escape.escape.bias"][0]).double()
    ep = torch.where(torch.from_numpy(elig), ep, torch.zeros_like(ep))
    pdelta = torch.from_numpy(np.exp(lp_delta))
    cls = torch.from_numpy(CLS.astype(np.float64))
    for i in range(0, n, 4096):
        sl_ = slice(i, min(n, i + 4096)); m = len(range(*sl_.indices(n)))
        zz = zh[sl_]; pr = pre[sl_]; post_final = pr[:, None] + cls[None]
        exp_hp = torch.zeros(m, dtype=torch.float64)
        for k, dv in enumerate(DV):
            mx = torch.from_numpy((M["pre_max"][sl_] + dv).astype(np.float64))
            legal = (post_final >= 1) & (post_final <= mx[:, None])
            di = torch.full((m,), k, dtype=torch.long)
            pr0 = torch.softmax(hp_logits(zz, di, torch.zeros(m)).double().masked_fill(~legal, -torch.inf), -1)
            pr1 = torch.softmax(hp_logits(zz, di, torch.ones(m)).double().masked_fill(~legal, -torch.inf), -1)
            e = ep[sl_][:, None]; mix = (1 - e) * pr0 + e * torch.nan_to_num(pr1)
            exp_hp += pdelta[sl_, k] * (mix * post_final).sum(-1)
        mae[sl_] = np.abs(exp_hp.numpy() - post_hp[sl_])
        okr = np.flatnonzero(hp_ok[sl_])
        if len(okr):
            g = okr + i
            mx = torch.from_numpy((M["post_max"][g]).astype(np.float64))
            legal = (pre[g][:, None] + cls[None] >= 1) & (pre[g][:, None] + cls[None] <= mx[:, None])
            lg = hp_logits(zz[okr], torch.from_numpy(didx[g]), torch.from_numpy(escaped[g]).float()).double()
            lsm = torch.log_softmax(lg.masked_fill(~legal, -torch.inf), -1)
            hp[g] = -lsm[torch.arange(len(g)), torch.from_numpy(hcls[g])].numpy()
    mae[~win] = np.nan
    pot = np.full(n, np.nan); g = np.flatnonzero(pot_ok)
    frac = torch.from_numpy((M["post_hp"][g] / M["post_max"][g]).astype(np.float32))
    lg = model.potion_net.output_logits(z["potion_encoder"][g], torch.from_numpy(pre_pot[g]), torch.from_numpy(didx[g]), frac).double()
    lsm = torch.log_softmax(lg.masked_fill(~torch.from_numpy(LEG[g]), -torch.inf), -1)
    pot[g] = -lsm[torch.arange(len(g)), torch.from_numpy(pmask[g])].numpy()
    return {"surv": surv, "brier": brier, "maxhp": maxhp, "hp": hp, "hp_mae": mae, "potion": pot, "p_death": p}

# ---- groups (model's own field names; see metadata continuousFields / predictorFieldSchema)
CF = list(meta["continuousFields"]); CAT = ["characterClass", "encounter", "roomClass", "lastRoom"]
def gcol(*names): return [("globals_continuous", CF.index(x)) for x in names if x in CF] + [("global_categories", CAT.index(x)) for x in names if x in CAT]
GROUPS = {
 "hp (curHp, maxHp)": gcol("curHp", "maxHp"),
 "progress (act, floor)": gcol("act", "floor"),
 "encounter (monster group id)": gcol("encounter"),
 "room type (roomClass, isBurningElite)": gcol("roomClass", "isBurningElite"),
 "path (lastRoom)": gcol("lastRoom"),
 "gold": gcol("gold"),
 "potion scalars (potionCount, potionCapacity)": gcol("potionCount", "potionCapacity"),
 "potionKeepValue (other model's output)": gcol("potionKeepValue"),
 "potion tokens (5 slots)": [("potions", None)],
 "deck (card token set)": [("cards", None), ("card_mask", None)],
 "relics (relic token set)": [("relics", None), ("relic_mask", None)],
 "constants (ascension, characterClass)": gcol("ascension", "characterClass"),
}
GROUPS["potions all (tokens + scalars + keepValue)"] = GROUPS["potion tokens (5 slots)"] + GROUPS["potion scalars (potionCount, potionCapacity)"] + GROUPS["potionKeepValue (other model's output)"]
SINGLES = {f: gcol(f) for f in ("curHp", "maxHp", "act", "floor", "roomClass", "isBurningElite", "potionCount", "potionCapacity")}
# token-field shuffles: pool the field over all valid tokens of the held-out rows and permute it
TOKEN_FIELDS = {"card id": ("cards", "card_mask", 0), "card upgraded": ("cards", "card_mask", 1),
                "card misc": ("cards", "card_mask", 2), "card bottleBinding": ("cards", "card_mask", 3),
                "relic id": ("relics", "relic_mask", 0), "relic data (counter)": ("relics", "relic_mask", 1),
                "relic orderIndex": ("relics", "relic_mask", 2)}
def permuted(spec, rng):
    B = dict(A); perm = rng.permutation(n)
    for key, col in spec:
        x = B[key].copy() if B[key] is A[key] else B[key]
        if col is None: x = A[key][perm]
        else: x[:, col] = A[key][perm, col]
        B[key] = x
    return B
def token_shuffled(spec, rng):
    key, mkey, f = spec; B = dict(A); x = A[key].copy(); m = A[mkey]
    vals = x[..., f][m]; x[..., f][m] = vals[rng.permutation(len(vals))]
    B[key] = x; return B

HEADS = ("surv", "brier", "maxhp", "hp", "hp_mae", "potion")
seeds = M["seed"]; useeds, sidx = np.unique(seeds, return_inverse=True); S = len(useeds); acts = M["act"]
def boot(delta, mask, rng, reps=1000):
    ok = mask & ~np.isnan(delta); dd = np.where(ok, delta, 0.0)
    s = np.bincount(sidx, dd, S); c = np.bincount(sidx, ok.astype(float), S)
    w = rng.multinomial(S, np.full(S, 1 / S), size=reps).astype(float)
    est = (w @ s) / np.maximum(w @ c, 1)
    return float(dd[ok].mean()) if ok.any() else float("nan"), [float(np.percentile(est, 2.5)), float(np.percentile(est, 97.5))]
t0 = time.time(); base = losses(A); tb = time.time() - t0
print(f"baseline {tb:.1f}s", {h: float(np.nanmean(base[h])) for h in HEADS}, flush=True)
def auc(p, y):
    o = np.argsort(p); r = np.empty(len(p)); r[o] = np.arange(1, len(p) + 1); pos = y == 1
    return float((r[pos].sum() - pos.sum() * (pos.sum() + 1) / 2) / (pos.sum() * (~pos).sum()))
baseline = {"rows": n, "seeds": S, "wins": int(win.sum()), "hp_rows": int(hp_ok.sum()), "potion_rows": int(pot_ok.sum()),
            "survival_auc": auc(base["p_death"], y_death), "death_rate": float(y_death.mean()), "mean_p_death": float(base["p_death"].mean()),
            **{h: float(np.nanmean(base[h])) for h in HEADS},
            "by_act": {int(a): {"rows": int((acts == a).sum()), **{h: float(np.nanmean(base[h][acts == a])) for h in HEADS}} for a in np.unique(acts)}}
rng_b = np.random.default_rng(401)
def run(name, maker, spec, reps):
    deltas = {h: [] for h in HEADS}
    for r in range(reps):
        rng = np.random.default_rng([zlib.crc32(name.encode()), r, 401])
        ls = losses(maker(spec, rng))
        for h in HEADS: deltas[h].append(ls[h] - base[h])
    res = {}
    for h in HEADS:
        D = np.stack(deltas[h]); mean_row = D.mean(0)
        est, ci = boot(mean_row, np.ones(n, bool), rng_b)
        res[h] = {"delta": est, "ci95": ci, "repeat_means": [float(np.nanmean(x)) for x in D],
                  "by_act": {str(int(a)): dict(zip(("delta", "ci95"), boot(mean_row, acts == a, rng_b))) for a in np.unique(acts)}}
    print(f"{name}: surv {res['surv']['delta']:+.5f} {res['surv']['ci95']} hp {res['hp']['delta']:+.4f} mae {res['hp_mae']['delta']:+.3f} ({time.time()-t0:.0f}s)", flush=True)
    return res
import os
PART = out + ".partial.json"   # checkpoint after every item; a restart resumes from it
results = json.load(open(PART)) if os.path.exists(PART) else {"groups": {}, "singles": {}, "token_fields": {}}
def ck(sec, g, maker, spec, reps):
    if g in results[sec]: return
    results[sec][g] = run(g, maker, spec, reps)
    json.dump(results, open(PART + ".tmp", "w")); os.replace(PART + ".tmp", PART)
for g, spec in GROUPS.items(): ck("groups", g, permuted, spec, REPEATS)
for g, spec in SINGLES.items(): ck("singles", g, permuted, spec, 3)
for g, spec in TOKEN_FIELDS.items(): ck("token_fields", g, token_shuffled, spec, 3)
json.dump({"baseline": baseline, "results": results, "groups_mapping": {g: [f"{k}[{CF[c] if k=='globals_continuous' else CAT[c] if k=='global_categories' else 'all'}]" if c is not None else k for k, c in s] for g, s in GROUPS.items()},
           "excluded_rows": {"entropic_brew_routed_to_standard": int(d["m_brew"].sum()), "active_lizard_composed": int(d["m_lizard"].sum()), "kept": n},
           "seconds": time.time() - t0}, open(out, "w"), indent=1)
