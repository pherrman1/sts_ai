"""W5 stage 2: aggregates persample_<slice>.npz (w5_eval.py) into results.csv / results.md / verdict.json with
run-level bootstrap CIs (B = 1000 multinomial resamples of runs, the same resample for every ckpt -> paired diffs).
usage: python3 w5_summ.py OUT_DIR"""
import json
import os
import sys

import numpy as np

od = sys.argv[1]
B = 1000
STEPS = [1594969, 1635474, 1678542, 1679639, 1717027, 1755240, 1782264, 1803647, 1805354, 1816571, 1828683]
TEACHER = 1828683
# last ckpt whose training cannot have seen the slice's runs (plan W5). testB was cut as 'unseen' relative to ckpt
# 1679639 (info_unseen.json w2_extra.step), so 1679639 is clean there too; heads_unseen was cut at step 1808284, so
# 1816571 counts as seen_runs.
CLEAN_MAX = {"heads_unseen": 1805354, "testB_unseen": 1679639}
METRICS = ["kl", "top1", "ce_out", "auc", "hpf_mse", "ce_hp"]
LOWER_BETTER = {"kl": True, "top1": False, "ce_out": True, "auc": False, "hpf_mse": True, "ce_hp": True}


def wauc(u, win, ws):
    pos = np.bincount(u, ws * win)
    neg = np.bincount(u, ws * (1 - win))
    below = np.cumsum(neg) - neg
    return float((pos * (below + 0.5 * neg)).sum() / max(1e-12, pos.sum() * neg.sum()))


rows, verdict = [], {}
for sname in ("heads_unseen", "testB_unseen"):
    fn = os.path.join(od, f"persample_{sname}.npz")
    if not os.path.exists(fn):
        continue
    z = dict(np.load(fn))
    run = z["run"].astype(np.int64); R = run.max() + 1
    rng = np.random.default_rng(20261127)
    W = rng.multinomial(R, np.full(R, 1.0 / R), size=B).astype(np.float64)   # [B, R]
    win = z["win"].astype(np.float64)
    for split in ("all", "combat", "ooc"):
        sel = np.ones(len(run), bool) if split == "all" else (z["combat"] if split == "combat" else ~z["combat"])
        polsel = sel & z["has_policy"]
        est = {}   # metric -> step -> (point, boot[B])
        for m in METRICS:
            est[m] = {}
            for s in STEPS:
                if m == "auc":
                    idx = np.flatnonzero(sel)
                    _, u = np.unique(z[f"{s}.pwin"][idx], return_inverse=True)
                    pt = wauc(u, win[idx], np.ones(len(idx)))
                    bt = np.array([wauc(u, win[idx], W[b, run[idx]]) for b in range(B)])
                else:
                    mk = polsel if m in ("kl", "top1") else sel
                    if m == "hpf_mse":
                        num, den = z[f"{s}.hpf_se"].astype(np.float64), z[f"{s}.hpf_n"].astype(np.float64)
                    else:
                        num = z[f"{s}.{m}"].astype(np.float64) * (100.0 if m == "top1" else 1.0)
                        den = np.ones(len(run))
                    rn = np.bincount(run[mk], num[mk], minlength=R)
                    rd = np.bincount(run[mk], den[mk], minlength=R)
                    pt = rn.sum() / rd.sum()
                    bt = (W @ rn) / (W @ rd)
                est[m][s] = (pt, bt)
        clean = [s for s in STEPS if s <= CLEAN_MAX[sname]]
        first, last = clean[0], clean[-1]
        for m in METRICS:
            p0, b0 = est[m][first]
            for s in STEPS:
                p, bt = est[m][s]
                d = p - p0; db = bt - b0
                rows.append(dict(slice=sname, split=split, metric=m, ckpt=s,
                                 clean=("teacher_partly_trained_on_slice" if s == TEACHER and sname == "heads_unseen"
                                        else "clean" if s <= CLEAN_MAX[sname] else "seen_runs"),
                                 value=p, ci_lo=np.quantile(bt, .025), ci_hi=np.quantile(bt, .975),
                                 d_vs_first=d, d_ci_lo=np.quantile(db, .025), d_ci_hi=np.quantile(db, .975)))

        def span(m):
            p0, b0 = est[m][first]; p1, b1 = est[m][last]
            sign = -1 if LOWER_BETTER[m] else 1   # improvement > 0
            g = sign * (p1 - p0); gb = sign * (b1 - b0)
            return {"improvement": g, "ci": [float(np.quantile(gb, .025)), float(np.quantile(gb, .975))],
                    "rel_improvement": g / abs(p0), "first": p0, "last": p1}
        sp = {m: span(m) for m in METRICS}
        dkl, dtop1 = sp["kl"]["improvement"], sp["top1"]["improvement"]
        sig = lambda m: sp[m]["ci"][0] > 0
        if dkl < 0.01 and dtop1 < 0.3:
            pol = "stalled"
        elif dkl >= 0.03 or dtop1 >= 1.0:
            pol = "policy_moves"
        else:
            pol = "between_thresholds"
        starv = sp["hpf_mse"]["rel_improvement"] < 0.01 and sp["ce_hp"]["rel_improvement"] >= 0.03
        verdict[f"{sname}/{split}"] = dict(span=[first, last], policy_rule=pol,
                                           outcome_ce_improves=sig("ce_out"), auc_improves=sig("auc"),
                                           hpf_starvation_flag=bool(starv), **{m: sp[m] for m in METRICS})
# learning confirmation: policy moves AND (same-slice outcome CE and AUC improve OR early ckpts improve on Test B)
tb = {k.split("/")[1]: v for k, v in verdict.items() if k.startswith("testB_unseen/")}
for k, v in verdict.items():
    if v["policy_rule"] == "policy_moves":
        early = tb.get(k.split("/")[1], {})
        conf = (v["outcome_ce_improves"] and v["auc_improves"]) or (
            bool(early) and early["outcome_ce_improves"] and early["auc_improves"])
        v["final"] = "learning" if conf else "policy_moves_unconfirmed"
    else:
        v["final"] = v["policy_rule"]

import csv  # noqa: E402
with open(os.path.join(od, "results.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    for r in rows:
        w.writerow({k: (f"{v:.6g}" if isinstance(v, float) else v) for k, v in r.items()})
json.dump(verdict, open(os.path.join(od, "verdict.json"), "w"), indent=1, default=float)

FMT = {"kl": "{:.4f}", "top1": "{:.2f}", "ce_out": "{:.4f}", "auc": "{:.4f}", "hpf_mse": "{:.5f}", "ce_hp": "{:.4f}"}
L = ["# W5 held-out learning check (1.2M, 11-25 .. 11-27)", "",
     "Values with 95 % run-bootstrap CI half-width; Δ = vs the first ckpt (paired bootstrap). top1 in %. "
     "kl = KL(search target ‖ prior) [nats]; ce_out = final-outcome CE; auc = AUC of P(win); hpf_mse = per-floor HP "
     "MSE (HP/255, masked); ce_hp = HP-class head CE vs real end HP. Marks: * = runs seen in training "
     "(not held out), T = teacher (trained on part of the slice's runs).", ""]
for key, v in verdict.items():
    sname, split = key.split("/")
    L += [f"## {sname} / {split}", "", "| ckpt | " + " | ".join(METRICS) + " |", "|---" * (len(METRICS) + 1) + "|"]
    for s in STEPS:
        rr = {r["metric"]: r for r in rows if r["slice"] == sname and r["split"] == split and r["ckpt"] == s}
        mark = "T" if rr["kl"]["clean"].startswith("teacher") else ("*" if rr["kl"]["clean"] == "seen_runs" else "")
        L.append(f"| {s}{mark} | " + " | ".join(
            FMT[m].format(rr[m]["value"]) + " ± " + FMT[m].format((rr[m]["ci_hi"] - rr[m]["ci_lo"]) / 2)
            for m in METRICS) + " |")
    L.append("")
    L.append(f"Span {v['span'][0]} → {v['span'][1]} (improvement, 95 % CI): " + "; ".join(
        f"{m} {v[m]['improvement']:+.4g} [{v[m]['ci'][0]:+.3g}, {v[m]['ci'][1]:+.3g}]" for m in METRICS))
    L.append(f"Verdict: **{v['final']}** (policy rule: {v['policy_rule']}; outcome CE improves: "
             f"{v['outcome_ce_improves']}; AUC improves: {v['auc_improves']}; per-floor HP starvation flag: "
             f"{v['hpf_starvation_flag']})")
    L.append("")
open(os.path.join(od, "results.md"), "w").write("\n".join(L))
print("\n".join(L))
