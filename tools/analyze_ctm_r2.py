#!/usr/bin/env python3
"""Score the Run 2 (Path B) CTM candidate on the §408 states (ledger §409).

usage: python3 tools/analyze_ctm_r2.py OUT.json --v2 PREFIX... --r2 PREFIX...
--v2 names the 16 §408 v2 shards (truth, Silver arms); --r2 names the
CTM-only rerun shards (``ctmsilvergen ... 0``) on the same seeds, which carry
the production CTM again plus the candidate (forecaster ``ctm_r2``).

Validity: every v2 state must reappear with identical source fields and an
identical production CTM forecast (support, P(death), HP expectation; CPU
columns excepted) and identical production CTM samples. Any difference makes
the run INVALID.

Scored states: §408-valid states that both CTMs support. Losses as in §408
with the post-combat HP deviation (truth = control RAW post-combat HP):
death Brier, HP MSE (h = (1 - P(death)) E[HP | win] for a CTM, mean of the
replicates for Silver) and the per-field sample Brier (all-but-HP joint is
the field co-primary). Paired seed-bootstrap CIs (10,000 resamples, seed 0)
for ctm_r2 - ctm and ctm_r2 - prior256 (x4).
"""
import argparse, csv, json, os, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze_ctm_vs_silver as base  # noqa: E402

CPU_COLS = {"ctmForecastCpuUs", "ctmSampleCpuUs"}
FIELDS = base.FIELDS


def read(prefixes, suffix):
    out = []
    for p in prefixes:
        with open(p + suffix) as f:
            out.extend(csv.DictReader(f))
    return out


def brier(samples, truth, fld):
    vals = [x[fld] for x in samples]; k = len(vals)
    p_t = sum(v == truth[fld] for v in vals) / k
    counts = {}
    for v in vals:
        counts[v] = counts.get(v, 0) + 1
    return 1 - 2 * p_t + sum(c * (c - 1) for c in counts.values()) / (k * (k - 1))


def boot(rows, key_a, key_b, rng, n=10000):
    seeds = sorted({r["seed"] for r in rows})
    ix = {s: i for i, s in enumerate(seeds)}
    per = np.zeros((len(seeds), 2))
    for r in rows:
        per[ix[r["seed"]]] += (r[key_a] - r[key_b], 1)
    draws = rng.integers(0, len(seeds), size=(n, len(seeds)))
    stats = per[draws, 0].sum(1) / per[draws, 1].sum(1)
    d = float(per[:, 0].sum() / per[:, 1].sum())
    ci = [float(np.quantile(stats, .025)), float(np.quantile(stats, .975))]
    return {"diff": d, "ci95": ci, "label": "A_LOWER" if ci[1] < 0 else "A_HIGHER" if ci[0] > 0 else "NO_DIFFERENCE_DETECTED"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out"); ap.add_argument("--v2", nargs="+", required=True); ap.add_argument("--r2", nargs="+", required=True)
    a = ap.parse_args()
    v2_states, v2_arms = base.load(a.v2)
    r2_states = {r["stateId"]: r for r in read(a.r2, ".states.csv")}
    # Validity: identical source fields and production CTM forecast.
    mism = {}
    for sid, s in v2_states.items():
        r = r2_states.get(sid)
        if r is None:
            mism["missing_state"] = mism.get("missing_state", 0) + 1
            continue
        for k, v in s.items():
            if k not in CPU_COLS and r.get(k) != v:
                mism[k] = mism.get(k, 0) + 1
    extra = len(set(r2_states) - set(v2_states))
    v2_samples, r2_samples = {}, {}
    for r in read(a.v2, ".samples.csv"):
        v2_samples.setdefault((r["stateId"], r["forecaster"]), []).append(r)
    for r in read(a.r2, ".samples.csv"):
        r2_samples.setdefault((r["stateId"], r["forecaster"]), []).append(r)
    sample_mism = sum(1 for (sid, f), xs in v2_samples.items() if f == "ctm" and r2_samples.get((sid, f)) != xs)
    valid = not mism and not extra and not sample_mism
    rows = base.forecasts(v2_states, v2_arms)
    post = {r["sid"]: r for r in base.hp_post_rows([r for r in rows if r["ctm"]], a.v2)}
    scored = []
    for sid, r in post.items():
        c = r2_states[sid]
        if c["candSupported"] != "1":
            continue
        truth = base.sample_fields(v2_samples[(sid, "control")][0])
        q = {"sid": sid, "seed": r["seed"], "act": r["act"], "d": r["d"], "y": r["y"]}
        for name, p, h, samples in (
                ("ctm", r["ctm_p"], r["ctm_h"], v2_samples[(sid, "ctm")]),
                ("ctm_r2", float(c["candPDeath"]), float(c["candExpectedHp"]), r2_samples[(sid, "ctm_r2")]),
                ("prior256", r["prior256_p"], r["prior256_h"], v2_samples[(sid, "prior256")])):
            q[name + ":brier"] = (p - r["d"]) ** 2
            q[name + ":hp_mse"] = (h - r["y"]) ** 2
            q[name + ":hp_bias"] = h - r["y"]
            fs = [base.sample_fields(x) for x in samples]
            for fld in FIELDS:
                q[f"{name}:{fld}"] = brier(fs, truth, fld)
        q["ctm_r2:us"] = float(c["candForecastCpuUs"]); q["ctm_r2:sample_us"] = float(c["candSampleCpuUs"])
        q["ctm:us"] = float(v2_states[sid]["ctmForecastCpuUs"])
        scored.append(q)
    metrics = ["brier", "hp_mse"] + list(FIELDS)
    res = {"valid": valid, "validity": {"field_mismatches": mism, "extra_states": extra, "ctm_sample_mismatches": sample_mism},
           "states_v2_valid_ctm_supported": len(post), "states_scored": len(scored),
           "candidate_unsupported_on_scored_set": sum(1 for sid in post if r2_states[sid]["candSupported"] != "1"),
           "candidate_reasons_all_states": {}, "means": {}, "paired": {}}
    for s in r2_states.values():
        if s["candSupported"] != "1":
            res["candidate_reasons_all_states"][s["candReason"]] = res["candidate_reasons_all_states"].get(s["candReason"], 0) + 1
    res["candidate_supported_where_production_not"] = sum(
        1 for s in r2_states.values() if s["candSupported"] == "1" and s["ctmSupported"] != "1")
    for name in ("ctm", "ctm_r2", "prior256"):
        m = {k: float(np.mean([q[f"{name}:{k}"] for q in scored])) for k in metrics + ["hp_bias"]}
        m["hp_rmse"] = float(np.sqrt(m["hp_mse"]))
        res["means"][name] = m
    res["cpu_ms"] = {"ctm_forecast": float(np.mean([q["ctm:us"] for q in scored]) / 1e3),
                     "ctm_r2_forecast": float(np.mean([q["ctm_r2:us"] for q in scored]) / 1e3),
                     "ctm_r2_sample": float(np.mean([q["ctm_r2:sample_us"] for q in scored]) / 1e3)}
    rng = np.random.default_rng(0)
    for a_name, b_name in (("ctm_r2", "ctm"), ("ctm_r2", "prior256")):
        res["paired"][f"{a_name}-{b_name}"] = {m: boot(scored, f"{a_name}:{m}", f"{b_name}:{m}", rng) for m in metrics}
    res["by_act"] = {}
    for act in sorted({q["act"] for q in scored}):
        sub = [q for q in scored if q["act"] == act]
        res["by_act"][act] = {name: {"n": len(sub), "hp_rmse": float(np.sqrt(np.mean([q[f"{name}:hp_mse"] for q in sub]))),
                                     "hp_bias": float(np.mean([q[f"{name}:hp_bias"] for q in sub])),
                                     "brier": float(np.mean([q[f"{name}:brier"] for q in sub]))}
                              for name in ("ctm", "ctm_r2", "prior256")}
    json.dump(res, open(a.out, "w"), indent=2)
    print(json.dumps({"valid": valid, "validity": res["validity"], "scored": len(scored),
                      "means": {n: {k: round(v, 4) for k, v in m.items() if k in ("brier", "hp_rmse", "hp_bias", "nonhp_joint", "joint")}
                                for n, m in res["means"].items()},
                      "labels": {c: {m: v["label"] for m, v in d.items() if m in ("brier", "hp_mse", "nonhp_joint")}
                                 for c, d in res["paired"].items()},
                      "cpu_ms": res["cpu_ms"]}, indent=1))


if __name__ == "__main__":
    main()
