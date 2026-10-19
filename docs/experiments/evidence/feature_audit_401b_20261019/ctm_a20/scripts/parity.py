#!/usr/bin/env python3
"""#401b ctm_a20 Step 1 parity: reproduce the composed stack's VALIDATION scores recorded in
§470 fit-validation.json (one_combat ctmscorerows, uncalibrated manifest 704f2a58, LIZARD=1) and
fit-validation-recheck.json (calibrated, boss shift) from the deployed artifacts in Torch.
Composition mirrors EntropicBrewFallbackCombatTransitionSampler: Brew -> standard child; active
Lizard Tail (data 1, no Mark of the Bloom) -> death = q (1 - r), q = 1 - s(ordinary), r from s(reserve)."""
import json, sys, time
import numpy as np
sys.path.insert(0, sys.path[0]); import ctmlib as L
d = dict(np.load(sys.argv[1], allow_pickle=False)); out = sys.argv[2]
t0 = time.time()
fast, std = L.load("fast"), L.load("standard")
n = len(d["m_seed"])
def surv(model, arrs):
    z = L.encode(model, arrs, names=("survival",))["survival"]
    return L.survival_logit(model, z)
sl_fast = surv(fast, d)
brew = d["m_brew"].astype(bool)
sub = {k: d[k][brew] for k in L.KEYS}
sl_std = np.full(n, np.nan); sl_std[brew] = surv(std, sub)
boss = d["m_boss"].astype(bool)
def rprob(model_json, p):
    b = model_json["standardizedCoefficients"]; m, s = model_json["featureMean"][0], model_json["featureScale"][0]
    return 1 / (1 + np.exp(-np.clip(b[0] + b[1] * ((p - m) / s), -40, 40)))
meta = fast.metadata
r_fast = meta["activeLizardCorrection"]["rModel"]; r_brew = meta["capabilities"]["lizardBrew"]["rModel"]
li = d["liz_idx"]
lo = {k: d["liz_ord_" + k] for k in L.KEYS}; lr = {k: d["liz_res_" + k] for k in L.KEYS}
def composed_death(shift):
    def sig(x): return 1 / (1 + np.exp(-x))
    logit = np.where(brew, sl_std, sl_fast) + np.where(boss, -shift, 0.0)
    pd = 1 - sig(logit)
    # Lizard rows
    bl = brew[li]; bloom = d["m_bloom"][li].astype(bool)
    so = np.where(bl, 0, 0).astype(float)
    sof = L.survival_logit(fast, L.encode(fast, lo, ("survival",))["survival"])
    srf = L.survival_logit(fast, L.encode(fast, lr, ("survival",))["survival"])
    if bl.any():
        sos = L.survival_logit(std, L.encode(std, {k: v[bl] for k, v in lo.items()}, ("survival",))["survival"])
        srs = L.survival_logit(std, L.encode(std, {k: v[bl] for k, v in lr.items()}, ("survival",))["survival"])
        sof[bl] = sos; srf[bl] = srs
    bshift = np.where(boss[li], -shift, 0.0)
    po, pr = sig(sof + bshift), sig(srf + bshift)
    r = np.where(bl, rprob(r_brew, pr), rprob(r_fast, pr))
    dl = (1 - po) * (1 - r)
    pd = pd.copy(); keep = ~bloom; pd[li[keep]] = dl[keep]
    return pd
y = (d["m_outcome"] != 1).astype(float); room = d["m_room"]
res = {}
for name, shift in (("uncalibrated", 0.0), ("calibrated", L.BOSS_SHIFT)):
    p = np.clip(composed_death(shift), 1e-7, 1 - 1e-7); b = room == "BOSS"
    nll = lambda q, yy: float(-(yy * np.log(q) + (1 - yy) * np.log(1 - q)).mean())
    res[name] = {"rows": int(n), "boss_rows": int(b.sum()), "boss_deaths": int(y[b].sum()),
                 "boss_nll": nll(p[b], y[b]), "all_nll": nll(p, y),
                 "bias_by_class": {c: float((p[room == c] - y[room == c]).mean()) for c in ("NORMAL", "ELITE", "BOSS")}}
ref = {"uncalibrated": {"boss_nll": 0.3046647928469686, "bias_by_class": {"NORMAL": -0.0011018584553933238, "ELITE": 0.004174692458777337, "BOSS": 0.01930594849092657}},
       "calibrated": {"boss_nll": 0.3028973816988733, "bias_by_class": {"NORMAL": -0.0011018584553933238, "ELITE": 0.004174692458777337, "BOSS": -1.9485963997730017e-05}}}
res["reference_470"] = ref
res["counts"] = {"brew_rows": int(brew.sum()), "active_lizard_rows": int(len(li)), "bloom_boundary": int(d["m_bloom"][li].sum())}
res["seconds"] = time.time() - t0
json.dump(res, open(out, "w"), indent=1); print(json.dumps(res, indent=1))
