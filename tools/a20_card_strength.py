"""A20 combat-strength card probe: offline scoring.

Plan: docs/experiments/evidence/a20_card_floor_20261009/PLAN-STRENGTH.md.
Joins `one_combat cardstrengthprobe` outputs (PROBE root, part*.{states,options,
strength}.csv) with the §402 counterfactual corpus (CORPUS root), checks that
each replayed decision matches the corpus, scores every card-reward option by
its weighted CTM utility against the act's remaining enemies and reports the
floor-reached selection gain over the teacher's pick. Nothing is fitted, so
TRAIN and VALIDATION are both scored; TEST sources are never read.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from tools.vwin_e3_cf import HIDDEN_FUTURE, SKIP_EFFECTS, apply_rules, cluster_mean, load, source_split

STATE = ["sourceSeed", "decisionIdx"]
MISMATCH_LIMIT = 0.05
POOLS = ("weak", "strong", "elite", "boss", "next_weak", "next_strong", "next_elite", "next_boss")
# Fixed next-act fight counts (PLAN-SILVER-NEXT-ACT.md), used only when the probe ran with NEXT_ACT=1.
NEXT_COUNTS = dict(next_weak=2, next_strong=3, next_elite=2, next_boss=1)


def load_probe(root):
    import pandas as pd
    parts = {"states": [], "options": [], "strength": []}
    manifests = []
    for man in sorted(Path(root).glob("**/part*.manifest.json")):
        prefix = str(man)[:-len(".manifest.json")]
        doc = json.loads(man.read_text())
        if doc["schemaVersion"] != "card_strength_probe_v1":
            raise ValueError(f"{man}: not a strength probe")
        for kind, digest in doc["outputs"].items():
            if hashlib.sha256(Path(prefix + "." + kind).read_bytes()).hexdigest() != digest:
                raise ValueError(f"{prefix}.{kind}: SHA-256 mismatch")
        manifests.append(dict(part=prefix, git=doc["producerGitSha"], exe=doc["producerExecutableSha256"],
                              seeds=doc["seedSpec"], integrity=doc["integrity"]))
        for kind in parts:
            parts[kind].append(pd.read_csv(f"{prefix}.{kind}.csv", dtype={"optionKey": str, "chosenKey": str,
                                                                          "error": str}))
    if not manifests:
        raise ValueError("no finished probe parts")
    return {k: pd.concat(v, ignore_index=True) for k, v in parts.items()}, manifests


def corpus_after_rows(root):
    import pandas as pd
    rows = [pd.read_csv(p, dtype={"optionKey": str}) for p in sorted(Path(root).glob("**/part*.options.csv"))
            if Path(str(p)[:-len(".options.csv")] + ".manifest.json").exists()]
    return pd.concat(rows, ignore_index=True)


def eligible_states(corpus_root):
    """Corpus card states as §413 (prepare) uses them, TEST excluded, with per-option mean floor."""
    lab, mp, _ = load(corpus_root)
    df, _ = apply_rules(lab, mp)
    df = df[(df["type"] == "CARD_REWARD") & (df["split"] != "TEST")].copy()
    leak = df["mapAct"].astype(int) != df["lab_act"].astype(int)
    leaky = set(map(tuple, df.loc[leak, STATE].drop_duplicates().to_numpy()))
    per = df.groupby(STATE + ["optionIdx"]).agg(floor=("horizonFloor", "mean"), chosen=("chosen", "max"),
                                                key=("optionKey", "first"), act=("lab_act", "first"),
                                                split=("split", "first")).reset_index()
    out = {}
    for state, g in per.groupby(STATE):
        if state in leaky or len(g) < 2 or g["chosen"].sum() != 1 or not 1 <= int(g["act"].iloc[0]) <= 3:
            continue
        out[tuple(int(v) for v in state)] = g.set_index("optionIdx")
    return out, len(leaky)


def match_state(state, opts, probe_opts, corpus_rows, columns):
    """True when the replayed decision is the corpus decision: same option keys, chosen flag and rich rows."""
    p = probe_opts.get(state)
    if p is None or not p["ok"].astype(bool).all():
        return False
    p = p.set_index("optionIdx")
    if set(p.index) != set(opts.index):
        return False
    for idx, row in opts.iterrows():
        if p.loc[idx, "optionKey"] != row["key"] or int(p.loc[idx, "chosen"]) != int(row["chosen"]):
            return False
        c = corpus_rows.get(state + (idx,))
        if c is None or any(not np.isclose(float(p.loc[idx, col]), float(c[col]), rtol=0, atol=1e-9)
                            for col in columns):
            return False
    return True


def strength(enc, state_row, current_only=False):
    """Weighted strength utility per option; encounters unsupported for any option are dropped for all."""
    if current_only:
        enc = enc[~enc["pool"].str.startswith("next_")]
    ok = enc.groupby(["pool", "encounter"])["supported"].transform("min").astype(bool)
    enc = enc[ok]
    act, offset = int(state_row["act"]), int(state_row["monOffset"])
    n_monster, n_elite = int(state_row["cMonster"]), int(state_row["cElite"])
    n_weak = min(max(0, (3 if act == 1 else 2) - offset), n_monster)
    counts = dict(weak=n_weak, strong=n_monster - n_weak, elite=n_elite, boss=1)
    if enc["pool"].str.startswith("next_").any():
        counts.update(NEXT_COUNTS if act < 3 else dict(next_boss=1))
    scores, missing = {}, []
    for idx, g in enc.groupby("optionIdx"):
        total = weight = 0.0
        for pool in POOLS:
            q = g[g["pool"] == pool]
            n = counts.get(pool, 0)
            if q.empty:
                if n:
                    missing.append(pool)
                continue
            if not n:
                continue
            u = float(np.average(q["utility"], weights=q["poolWeight"]))
            total += n * u
            weight += n
        scores[int(idx)] = total / weight if weight else np.nan
    return scores, sorted(set(missing)), counts


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("probe")
    ap.add_argument("corpus")
    ap.add_argument("--output", required=True)
    ap.add_argument("--reps", type=int, default=2000)
    ap.add_argument("--only-seeds", help="score only these source seeds (one per line)")
    ap.add_argument("--current-act-only", action="store_true", help="ignore next-act pools (diagnostic)")
    args = ap.parse_args()
    probe, manifests = load_probe(args.probe)
    states, leaky = eligible_states(args.corpus)
    rich = [c for c in probe["options"].columns[7:] if c not in HIDDEN_FUTURE]
    corpus_opts = corpus_after_rows(args.corpus)
    corpus_rows = {(int(r.sourceSeed), int(r.decisionIdx), int(r.optionIdx)): r
                   for r in corpus_opts[corpus_opts["type"] == "CARD_REWARD"].itertuples(index=False)}
    corpus_rows = {k: v._asdict() for k, v in corpus_rows.items()}
    probe_opts = {tuple(int(v) for v in s): g for s, g in probe["options"].groupby(STATE)}
    probe_states = {tuple(int(v) for v in s): g.iloc[0] for s, g in probe["states"].groupby(STATE)}
    probe_enc = {tuple(int(v) for v in s): g for s, g in probe["strength"].groupby(STATE)}
    probed_seeds = set(int(s) for s in probe["states"]["sourceSeed"])
    if args.only_seeds:
        probed_seeds &= {int(line) for line in Path(args.only_seeds).read_text().split()}
    rows, mismatched, unscored = [], [], []
    for state, opts in sorted(states.items()):
        if state[0] not in probed_seeds:
            continue
        if not match_state(state, opts, probe_opts, corpus_rows, rich) or state not in probe_states:
            mismatched.append(list(state))
            continue
        scores, missing, counts = strength(probe_enc.get(state, probe["strength"].iloc[:0]),
                                           probe_states[state], args.current_act_only)
        if missing or len(scores) != len(opts) or any(np.isnan(v) for v in scores.values()):
            unscored.append(dict(state=list(state), missing=missing))
            continue
        score = np.array([scores[i] for i in opts.index])
        top = np.isclose(score, score.max(), rtol=0, atol=1e-12)
        chosen = opts["chosen"].to_numpy() == 1
        pick = np.flatnonzero(chosen & top)
        pick = pick[0] if len(pick) else np.flatnonzero(top)[0]
        floors = opts["floor"].to_numpy(float)
        base = floors[chosen][0]
        skip = opts["key"].str.contains("|".join(SKIP_EFFECTS)).to_numpy()
        rows.append(dict(seed=state[0], decision=state[1], split=opts["split"].iloc[0],
                         act=int(opts["act"].iloc[0]), gain=floors[pick] - base,
                         oracle=floors.max() - base, uniform=floors.mean() - base,
                         agrees=bool(chosen[pick]), picks_skip=bool(skip[pick]),
                         teacher_skip=bool(skip[chosen][0]), spread=float(score.max() - score.min()),
                         n_weak=counts["weak"], n_strong=counts["strong"], n_elite=counts["elite"]))
    eligible = sum(1 for s in states if s[0] in probed_seeds)
    rate = len(mismatched) / eligible if eligible else 1.0

    def block(part):
        seeds = [r["seed"] for r in part]
        if not part:
            return dict(states=0)
        return dict(states=len(part), gain=cluster_mean([r["gain"] for r in part], seeds, args.reps),
                    oracle=cluster_mean([r["oracle"] for r in part], seeds, args.reps),
                    uniform=cluster_mean([r["uniform"] for r in part], seeds, args.reps),
                    agreement=float(np.mean([r["agrees"] for r in part])),
                    skip_rate=float(np.mean([r["picks_skip"] for r in part])),
                    teacher_skip_rate=float(np.mean([r["teacher_skip"] for r in part])),
                    median_score_spread=float(np.median([r["spread"] for r in part])))

    results = {"PRIMARY": block(rows)}
    for split in ("TRAIN", "VALIDATION"):
        results[split] = block([r for r in rows if r["split"] == split])
    for act in (1, 2, 3):
        results[f"act{act}"] = block([r for r in rows if r["act"] == act])
    if rate > MISMATCH_LIMIT:
        verdict = "INVALID"
    else:
        lo = results["PRIMARY"]["gain"]["ci95"][0]
        verdict = "PASS" if lo > 0 else "NOT_SHOWN"
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False)
    report = dict(schema="a20_card_strength_v1", probe=str(Path(args.probe).resolve()),
                  corpus=str(Path(args.corpus).resolve()),
                  producer_git=sorted({m["git"] for m in manifests}),
                  producer_exe=sorted({m["exe"] for m in manifests}), parts=len(manifests),
                  integrity=[m["integrity"] for m in manifests], leaky_states_excluded=leaky,
                  eligible_states=eligible, mismatched=len(mismatched), mismatch_rate=rate,
                  unscored=unscored, mismatched_states=mismatched, results=results, verdict=verdict)
    (out / "report.json").write_text(json.dumps(report, indent=1, default=float) + "\n")
    import pandas as pd
    pd.DataFrame(rows).to_csv(out / "states.csv", index=False)
    assert all(source_split(r["seed"]) != "TEST" for r in rows)
    print("VERDICT", verdict, json.dumps(results["PRIMARY"]))


if __name__ == "__main__":
    main()
