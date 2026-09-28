import csv, gzip, json, glob, statistics
from collections import Counter
for arm in ("control", "topup"):
    rows = []
    for f in sorted(glob.glob(f"{arm}_[04].csv")): rows += list(csv.DictReader(open(f)))
    prof = [json.loads(l) for f in sorted(glob.glob(f"{arm}_prof_*.jsonl*")) for l in (gzip.open(f, "rt") if f.endswith(".gz") else open(f))]
    sec = sum(float(r["sec"]) for r in rows)
    dec = len(prof); sims = sum(p["completed_simulations"] for p in prof)
    searched = [p for p in prof if not p["singleton_skip"]]
    ret = [p for p in searched if p["inherited_visits"] > 0]
    fresh = [p for p in searched if p["inherited_visits"] == 0]
    zero = sum(p["completed_simulations"] == 0 for p in searched)
    one = sum(p["completed_simulations"] == 1 for p in searched)
    print(f"== {arm}: won {sum(int(r['won']) for r in rows)}/8  floors {[int(r['floor']) for r in rows]}  hpEnd {[int(r['hpEnd']) for r in rows]}")
    print(f"  total sec {sec:.1f}  decisions {dec}  sims {sims}  sec/decision {1000*sec/dec:.2f} ms  sims/decision {sims/dec:.0f}  us/sim {1e6*sec/sims:.2f}")
    print(f"  combats {len(set((p['seed'],p['combat_id']) for p in prof))}  searched {len(searched)} (retained {len(ret)}, fresh {len(fresh)})  zero-sim retained {zero}  one-sim {one}")
    if ret: print(f"  retained: mean inherited {statistics.mean(p['inherited_visits'] for p in ret):.0f}  mean new sims {statistics.mean(p['completed_simulations'] for p in ret):.0f}  median {statistics.median(p['completed_simulations'] for p in ret)}")
    per_seed = {r["seed"]: float(r["sec"]) for r in rows}
    print("  per-seed sec", {k: round(v, 2) for k, v in per_seed.items()})
