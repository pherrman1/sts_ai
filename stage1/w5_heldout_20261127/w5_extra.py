"""W5 supplement: paired run-bootstrap (B=1000) for extra spans on heads_unseen (clean ckpts only), to separate the
early span from the late one and the 1805354 endpoint (an outlier on every value head). Writes extra_spans.csv."""
import csv, numpy as np
z = dict(np.load("persample_heads_unseen.npz")); run = z["run"].astype(np.int64); R = run.max() + 1
W = np.random.default_rng(20261127).multinomial(R, np.full(R, 1 / R), size=1000).astype(float)
win = z["win"].astype(float)
def wauc(u, ws):
    pos = np.bincount(u, ws * win); neg = np.bincount(u, ws * (1 - win)); b = np.cumsum(neg) - neg
    return (pos * (b + .5 * neg)).sum() / (pos.sum() * neg.sum())
def boot(s, m):
    if m == "auc":
        _, u = np.unique(z[f"{s}.pwin"], return_inverse=True)
        return wauc(u, np.ones(len(run))), np.array([wauc(u, W[b, run]) for b in range(1000)])
    mk = z["has_policy"] if m in ("kl", "top1") else np.ones(len(run), bool)
    num = z[f"{s}.hpf_se"] if m == "hpf_mse" else z[f"{s}.{m}"].astype(float) * (100 if m == "top1" else 1)
    den = z[f"{s}.hpf_n"].astype(float) if m == "hpf_mse" else np.ones(len(run))
    rn = np.bincount(run[mk], num[mk], minlength=R); rd = np.bincount(run[mk], den[mk], minlength=R)
    return rn.sum() / rd.sum(), (W @ rn) / (W @ rd)
LB = {"kl": 1, "top1": -1, "ce_out": 1, "auc": -1, "hpf_mse": 1, "ce_hp": 1}
out = []
for a, b in ((1594969, 1678542), (1678542, 1803647), (1594969, 1803647), (1803647, 1805354)):
    for m in LB:
        pa, ba = boot(a, m); pb, bb = boot(b, m); g = LB[m] * (pa - pb); gb = LB[m] * (ba - bb)
        out.append(dict(slice="heads_unseen", split="all", span=f"{a}->{b}", metric=m, improvement=f"{g:.6g}",
                        ci_lo=f"{np.quantile(gb, .025):.6g}", ci_hi=f"{np.quantile(gb, .975):.6g}",
                        rel_pct=f"{100 * g / abs(pa):.3g}"))
        print(out[-1])
w = csv.DictWriter(open("extra_spans.csv", "w", newline=""), fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
