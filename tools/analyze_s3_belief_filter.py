#!/usr/bin/env python3
"""Summarize Searcher3 posterior-collapse diagnostics and paired arms."""
import argparse, csv, statistics, collections

def rows(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))

def val(r, k): return float(r[k])
def avg(rs, k): return statistics.mean(val(r,k) for r in rs) if rs else float("nan")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--diag", required=True)
    ap.add_argument("--control")
    ap.add_argument("--filter")
    ap.add_argument("--fresh")
    args=ap.parse_args()
    ds=rows(args.diag)
    print(f"rows={len(ds)} seeds={len({r['seed'] for r in ds})}")
    for k in ("filter_compatible_fraction", "posterior_collapse",
              "propagation_failures", "filter_fallback_shuffles",
              "distinct_surviving_draw_orders",
              "distinct_surviving_rng_signatures", "filter_cpu_ms"):
        print(f"{k},mean={avg(ds,k):.6f},median={statistics.median(val(r,k) for r in ds):.6f}")
    collapses=[r for r in ds if int(r["posterior_collapse"])]
    print("collapse_categories", collections.Counter(r["collapse_category"] for r in collapses))
    print("collapse_action_types", collections.Counter(r["action_type"] for r in collapses))
    print("collapse_reshuffle_rows", sum(int(r["reshuffle_observed"]) for r in collapses))
    if collapses:
        print(f"collapse_predicted_distinct_mean={avg(collapses, 'distinct_predicted_observations'):.3f}")
        print(f"collapse_predicted_entropy_mean={avg(collapses, 'predicted_observation_entropy'):.3f}")
    probes=[r for r in collapses if int(r["sensitivity_probed"])]
    for k in ("sensitivity_64", "sensitivity_128", "sensitivity_256", "sensitivity_512"):
        xs=[int(r[k]) for r in probes if int(r[k]) >= 0]
        if xs: print(f"{k},mean={statistics.mean(xs):.3f},positive={sum(x>0 for x in xs)}/{len(xs)}")
    if args.control and args.filter:
        arms={"A":{r["seed"]:r for r in rows(args.control)},
              "B":{r["seed"]:r for r in rows(args.filter)}}
        if args.fresh: arms["C"]={r["seed"]:r for r in rows(args.fresh)}
        seeds=sorted(set.intersection(*(set(x) for x in arms.values())))
        print("metric,"+",".join(arms))
        for k in ("won", "floor", "hpEnd", "sec"):
            print(k+","+",".join(f"{statistics.mean(val(arms[a][s],k) for s in seeds):.6f}" for a in arms))
        for a in list(arms)[1:]:
            print(f"paired_win_flips_A_{a}={sum(arms['A'][s]['won'] != arms[a][s]['won'] for s in seeds)}/{len(seeds)}")
        if "C" in arms:
            print(f"paired_win_flips_B_C={sum(arms['B'][s]['won'] != arms['C'][s]['won'] for s in seeds)}/{len(seeds)}")

if __name__ == "__main__": main()