#!/usr/bin/env python3
"""§443 Stage 3a offline gate: pathb-a20 (escape) vs production with ascension clamped to 0, on A20 TEST rows.

Implements PREREG-GATES.md (sha256 4134ef35..., data branch ctm-a20-stage3) and GATE3A-NOTES.md. Reads rows and
`one_combat ctmscorerows` CSVs only; runs no seeds. stdlib + numpy.
  gate3a.py clamp IN.jsonl OUT.jsonl        copy rows with predictorInput.globals.ascension = 0, all else unchanged
  gate3a.py compare --prod P.csv --cand C.csv --label L --out R.json [--role gate|secondary]

Interpretation fixed before scoring (recorded in PREREG-FROZEN.txt):
- Gate rows: scope `none` (main corpus) TEST rows (split_for_seed bucket >= 90) from the assembled scope corpus, i.e.
  including rows the union dropped (as #418). Forced scopes are reported as secondary.
- valid = run_valid and outcome in {win, loss}; metrics 1-4 on rows both stacks score ("both").
- 1: survival NLL (p_death clipped to [1e-6, 1-1e-6]) delta candidate - production, 95% CI upper < 0.
- 2: candidate death bias = mean(p_death - died); |point estimate| <= 0.01 overall and on NORMAL, ELITE, BOSS rows.
- 3: candidate win-HP bias = mean(expected_win_hp - post_hp) on wins; |point estimate| <= 3 overall and per class.
- 4: HP NLL (-max(log_p_post_hp, log 1e-6), wins) delta, 95% CI upper < 0.
- 5: candidate refusals (valid rows it does not score) <= production refusals; per-reason counts reported.
- CIs: paired source-seed bootstrap, 2000 reps, numpy default_rng(443), 95% percentile.
PASS iff 1-5 all hold, else NOT_QUALIFIED.
"""
import argparse, csv, hashlib, json, math, sys
from pathlib import Path
import numpy as np

EPS, REPS, SEED = 1e-6, 2000, 443
BIAS_DEATH, BIAS_HP = 0.01, 3.0
HEADER = ("source_seed,fight_idx,act,floor,room_class,encounter,teacher_id,run_valid,quarantine_reason,"
          "combat_outcome,pre_hp,pre_max_hp,post_hp,post_max_hp,scored,support_reason,p_death,"
          "win_hp_fraction,expected_win_hp,hist_mass,log_p_post_hp").split(",")
LABELS = HEADER[:14]
WIN, LOSS = 1, 2
CLASSES = ("NORMAL", "ELITE", "BOSS")


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()


def clamp(src, dst):
    n = 0
    with open(src, encoding="utf-8") as f, open(dst, "x", encoding="utf-8") as g:
        for line in f:
            r = json.loads(line)
            if r["predictorInput"]["globals"]["ascension"] != 20: raise SystemExit("row is not ascension 20")
            r["predictorInput"]["globals"]["ascension"] = 0
            g.write(json.dumps(r, separators=(",", ":")) + "\n"); n += 1
    print(json.dumps({"rows": n, "out": str(dst), "sha256": sha256(dst)}))


def read(p):
    with open(p, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        if r.fieldnames != HEADER: raise SystemExit(f"{p}: not a ctmscorerows CSV")
        out = {}
        for x in r:
            k = (int(x["source_seed"]), int(x["fight_idx"]))
            if k in out: raise SystemExit(f"{p}: duplicate {k}")
            out[k] = x
    return out


class Boot:
    def __init__(self, seeds):
        self.uniq, self.idx = np.unique(seeds, return_inverse=True)
        rng = np.random.default_rng(SEED); S = len(self.uniq)
        self.w = np.stack([np.bincount(rng.integers(0, S, S), minlength=S) for _ in range(REPS)]).astype(float)

    def stat(self, v, m):
        m = m & np.isfinite(v)
        if not m.any(): return None
        S = len(self.uniq)
        s = np.bincount(self.idx[m], weights=v[m], minlength=S); c = np.bincount(self.idx[m], minlength=S).astype(float)
        with np.errstate(invalid="ignore", divide="ignore"): r = (self.w @ s) / (self.w @ c)
        r = r[np.isfinite(r)]; lo, hi = np.percentile(r, [2.5, 97.5])
        return {"mean": float(v[m].mean()), "ci95": [float(lo), float(hi)], "n": int(m.sum()),
                "seeds": int(len(np.unique(self.idx[m])))}


def compare(a):
    P, C = read(a.prod), read(a.cand)
    if set(P) != set(C): raise SystemExit("CSVs cover different rows")
    keys = sorted(P); p = [P[k] for k in keys]; c = [C[k] for k in keys]
    for x, y in zip(p, c):
        if any(x[f] != y[f] for f in LABELS): raise SystemExit(f"label mismatch {x['source_seed']},{x['fight_idx']}")
    seeds = np.array([k[0] for k in keys])
    out = np.array([int(x["combat_outcome"]) if x["combat_outcome"] else 0 for x in p])
    valid = np.array([x["run_valid"] == "1" for x in p]) & np.isin(out, (WIN, LOSS))
    died = (out == LOSS).astype(float); win = valid & (out == WIN)
    post = np.array([float(x["post_hp"]) if x["post_hp"] else np.nan for x in p])
    room = np.array([x["room_class"] for x in p])

    def arrays(rows):
        sc = np.array([x["scored"] == "1" for x in rows])
        pd = np.array([float(x["p_death"]) if x["scored"] == "1" else np.nan for x in rows])
        eh = np.array([float(x["expected_win_hp"]) if x["scored"] == "1" else np.nan for x in rows])
        lp = np.array([float(x["log_p_post_hp"]) if x["scored"] == "1" and x["log_p_post_hp"] != "" else np.nan for x in rows])
        q = np.clip(pd, EPS, 1 - EPS)
        return dict(scored=sc, reason=np.array([x["support_reason"] for x in rows]),
                    snll=-(died * np.log(q) + (1 - died) * np.log(1 - q)),
                    hnll=np.where(win, -np.maximum(lp, math.log(EPS)), np.nan),
                    dbias=pd - died, hbias=np.where(win, eh - post, np.nan),
                    hzero=np.where(win & np.isfinite(pd), (lp == -np.inf).astype(float), np.nan))
    sp, sc = arrays(p), arrays(c)
    both = valid & sp["scored"] & sc["scored"]
    boot = Boot(seeds)
    slices = {"all": np.ones(len(keys), bool), **{k.lower(): room == k for k in CLASSES}}

    def reasons(s, m):
        u, n = np.unique(s["reason"][m], return_counts=True); return {str(k): int(v) for k, v in zip(u, n)}
    res = {"schema": "ctm_gate3a_v1", "label": a.label, "role": a.role,
           "inputs": {"prod": str(a.prod), "prodSha256": sha256(a.prod), "cand": str(a.cand), "candSha256": sha256(a.cand),
                      "script": str(Path(__file__).resolve()), "scriptSha256": sha256(Path(__file__))},
           "numpy": np.__version__, "bootstrap": {"reps": REPS, "seed": SEED, "unit": "source_seed"},
           "census": {"rows": len(keys), "seeds": int(len(np.unique(seeds))), "valid": int(valid.sum()),
                      "wins": int(win.sum()), "losses": int((valid & (died == 1)).sum()), "both": int(both.sum()),
                      "prodRefused": int((valid & ~sp["scored"]).sum()), "candRefused": int((valid & ~sc["scored"]).sum()),
                      "prodRefusalReasons": reasons(sp, valid & ~sp["scored"]), "candRefusalReasons": reasons(sc, valid & ~sc["scored"]),
                      "prodOnly": int((valid & sp["scored"] & ~sc["scored"]).sum()), "candOnly": int((valid & ~sp["scored"] & sc["scored"]).sum()),
                      "hpZeroBoth": {"prod": int(np.nansum(sp["hzero"][both])), "cand": int(np.nansum(sc["hzero"][both]))}},
           "slices": {}}
    for name, m in slices.items():
        mm = both & m
        if not mm.any(): continue
        res["slices"][name] = {
            "n": int(mm.sum()),
            "survivalNll": {"prod": boot.stat(sp["snll"], mm), "cand": boot.stat(sc["snll"], mm), "delta": boot.stat(sc["snll"] - sp["snll"], mm)},
            "hpNll": {"prod": boot.stat(sp["hnll"], mm), "cand": boot.stat(sc["hnll"], mm), "delta": boot.stat(sc["hnll"] - sp["hnll"], mm)},
            "deathBias": {"prod": boot.stat(sp["dbias"], mm), "cand": boot.stat(sc["dbias"], mm)},
            "winHpBias": {"prod": boot.stat(sp["hbias"], mm), "cand": boot.stat(sc["hbias"], mm)}}
    if a.role == "gate":
        s = res["slices"]; ce = res["census"]
        crit = {
            "1_survival_nll_upper_ci_lt_0": s["all"]["survivalNll"]["delta"]["ci95"][1] < 0,
            "2_death_bias_abs_le_0.01": all(abs(s[k]["deathBias"]["cand"]["mean"]) <= BIAS_DEATH for k in ("all", "normal", "elite", "boss")),
            "3_win_hp_bias_abs_le_3": all(abs(s[k]["winHpBias"]["cand"]["mean"]) <= BIAS_HP for k in ("all", "normal", "elite", "boss")),
            "4_hp_nll_upper_ci_lt_0": s["all"]["hpNll"]["delta"]["ci95"][1] < 0,
            "5_refusals_le_production": ce["candRefused"] <= ce["prodRefused"]}
        res["decision"] = {"criteria": crit, "verdict": "PASS" if all(crit.values()) else "NOT_QUALIFIED"}
    Path(a.out).open("x", encoding="utf-8").write(json.dumps(res, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"label": a.label, "census": {k: res["census"][k] for k in ("rows", "seeds", "valid", "both", "prodRefused", "candRefused")},
                      "decision": res.get("decision")}, indent=1))


def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("clamp"); c.add_argument("src", type=Path); c.add_argument("dst", type=Path)
    k = sub.add_parser("compare"); k.add_argument("--prod", type=Path, required=True); k.add_argument("--cand", type=Path, required=True)
    k.add_argument("--label", required=True); k.add_argument("--out", type=Path, required=True)
    k.add_argument("--role", choices=("gate", "secondary"), default="secondary")
    a = ap.parse_args()
    clamp(a.src, a.dst) if a.cmd == "clamp" else compare(a)


if __name__ == "__main__":
    main()
