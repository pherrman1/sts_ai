import csv, glob, gzip, json, sys
from analyze_por import rows_of, summarize
for mode in ("flat", "adaptive"):
    for arm in ("control", "shared"):
        res = [r for f in sorted(glob.glob(f"{mode}_{arm}_[04].csv")) for r in csv.DictReader(open(f))]
        prof = [r for r in rows_of(sorted(glob.glob(f"{mode}_{arm}_[04].jsonl*"))) if not r["error"]]
        searched = [r for r in prof if not r["singleton_skip"]]
        first = {}
        for r in sorted(searched, key=lambda r: (r["seed"], r["combat_id"], r["decision"])):
            first.setdefault((r["seed"], r["combat_id"], r["turn"]), r)
        s = summarize(list(first.values()), "root_turn")
        sec = sum(float(r["sec"]) for r in res); sims = sum(r["completed_simulations"] for r in prof)
        print(f"{mode:8s} {arm:7s} won {sum(int(r['won']) for r in res)}/8 floor {sum(int(r['floor']) for r in res)/8:.1f} hpEnd {[int(r['hpEnd']) for r in res]}"
              f" | dec {len(prof)} sims {sims} ms/dec {1000*sec/len(prof):.2f} us/sim {1e6*sec/sims:.2f}"
              f" | conf {s['pooled_confirmed_visit_share']:.3f} cand {s['pooled_candidate_visit_share']:.3f} med {s['median_confirmed_share']:.3f}")
