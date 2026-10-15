#!/usr/bin/env python3
"""Freeze the #347 boss-preparation R-match sources (PLAN.md).

The four run seeds are the frozen #425 R entries (mcts boss loss, flat10k won
the same seed). Each seed gets two sources from its historical #417 rows:
M (mcts arm, expected target-boss loss) and F (flat10k arm, expected target-
boss win). The smoke manifest uses the #425 smoke R seed with 2 planner reps.
Usage: select.py RUN417_DIR RESCUE425_SELECTION RESCUE425_SMOKE OUT_DIR
"""
import csv, glob, hashlib, json, os, sys

EVIDENCE_REF = "10e56bd813202db969ddb176aad8ed33173179f7"
FROZEN_R = [48000024, 48000014, 48000116, 48000095]   # handout order
SMOKE_R = [48000117]
PLANNER_DOMAIN = "boss-prep-347-planner-v1:{runSeed}:{act}:{rep}"
ARMS = (("M", "mcts", 0), ("F", "flat10k", 1))


def load(run_dir, arm):
    rows = {}
    for path in sorted(glob.glob(os.path.join(run_dir, f"{arm}[0-9].csv"))):
        with open(path, newline="") as f:
            for r in csv.DictReader(f):
                seed = int(r["seed"])
                if seed in rows:
                    sys.exit(f"duplicate seed {seed} in arm {arm}")
                rows[seed] = {k: (float(v) if k == "sec" else int(v)) for k, v in r.items()}
                rows[seed]["file"] = os.path.basename(path)
    return rows


def sources(seeds, rescue, rows, smoke):
    by_seed = {e["seed"]: e for e in rescue["selected"] if e["stratum"] == "R"}
    out = []
    for seed in seeds:
        r = by_seed.get(seed)
        if r is None:
            sys.exit(f"seed {seed} is not an R entry of the #425 manifest")
        # The #425 manifest and the #417 rows must agree before anything is frozen.
        if r["historicalRow"] != rows["mcts"][seed] or r["pairedArmRow"] != rows["flat10k"][seed]:
            sys.exit(f"#425 manifest rows differ from #417 rows for seed {seed}")
        if rows["mcts"][seed]["won"] != 0 or rows["flat10k"][seed]["won"] != 1:
            sys.exit(f"seed {seed} is not an mcts loss / flat10k win")
        for label, arm, expected in ARMS:
            out.append({"stateId": f"{'smoke' if smoke else ''}{label}-{seed}-a{r['act']}",
                        "stratum": label, "prepArm": label, "sourceArm": arm, "seed": seed,
                        "act": r["act"], "boss": r["boss"], "expectedSourceWon": expected,
                        "historicalRow": rows[arm][seed], "rescue425StateId": r["stateId"]})
    return out


def main():
    run_dir, sel425, smoke425, out_dir = sys.argv[1:5]
    rows = {arm: load(run_dir, arm) for arm in ("mcts", "flat10k")}
    rescue, rescue_smoke = json.load(open(sel425)), json.load(open(smoke425))
    common = {
        "schema": "boss_preparation_rmatch_347_selection_v1",
        "source": {"pr": 417, "ledger": "§384", "evidenceRef": EVIDENCE_REF,
                   "historicalGameplayBaseline": "5e9583cc4c871b887ab0eccc5e290c7c0f990117",
                   "rescue425Selection": {"path": os.path.basename(sel425),
                                          "sha256": hashlib.sha256(open(sel425, "rb").read()).hexdigest()},
                   "runFilesSha256": {os.path.basename(p): hashlib.sha256(open(p, "rb").read()).hexdigest()
                                      for p in sorted(glob.glob(os.path.join(run_dir, "*.csv")))
                                      if os.path.basename(p).startswith(("flat10k", "mcts"))}},
        "rule": {"seeds": "frozen #425 R entries: mcts boss loss where flat10k won the same seed",
                 "arms": {"M": "mcts-produced boss entry + fixed flat10k combat",
                          "F": "flat10k-produced boss entry + fixed flat10k combat"},
                 "plannerSeedDomain": PLANNER_DOMAIN,
                 "pairing": "M/F rows pair by runSeed + rep; planner seed excludes arm and stateId"},
    }
    main_sel = dict(common, plannerReps=8, smoke=False, selected=sources(FROZEN_R, rescue, rows, False))
    smoke_sel = dict(common, plannerReps=2, smoke=True, selected=sources(SMOKE_R, rescue_smoke, rows, True))
    for name, sel in (("selection.json", main_sel), ("smoke.json", smoke_sel)):
        with open(os.path.join(out_dir, name), "w") as f:
            json.dump(sel, f, indent=1)
            f.write("\n")
        for s in sel["selected"]:
            print(name, s["stateId"], s["sourceArm"], s["boss"], "expectedSourceWon", s["expectedSourceWon"])


if __name__ == "__main__":
    main()
