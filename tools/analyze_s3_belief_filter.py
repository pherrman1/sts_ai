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
    ap.add_argument("--next-search",
                    help="sidecar from the belief audit that records the actual next-search belief source")
    args=ap.parse_args()
    ds=rows(args.diag)
    print(f"rows={len(ds)} seeds={len({r['seed'] for r in ds})}")
    for k in ("filter_compatible_fraction", "posterior_collapse",
              "propagation_failures", "filter_fallback_shuffles",
              "distinct_surviving_draw_orders",
              "distinct_surviving_rng_signatures", "filter_cpu_ms"):
        print(f"{k},mean={avg(ds,k):.6f},median={statistics.median(val(r,k) for r in ds):.6f}")
    if args.next_search:
        sources = rows(args.next_search)
        source_by_boundary = {
            (r["seed"], r["floor"], r["encounter"], r["decision_index"]): r["next_search_belief_source"]
            for r in sources
        }
        filtered = [r for r in ds if int(r["boundary_update_applied"])]
        resolved = [r for r in filtered
                    if (r["seed"], r["floor"], r["encounter"], r["decision_index"])
                    in source_by_boundary]
        print(f"filtered_boundaries={len(filtered)} resolved_next_search_sources={len(resolved)}")
        print("next_search_belief_sources", collections.Counter(
            source_by_boundary[(r["seed"], r["floor"], r["encounter"], r["decision_index"])]
            for r in resolved))
        for label, predicate in (("nontrivial_lt_1", lambda x: x < 1.0),
                                 ("strong_lt_075", lambda x: x < 0.75),
                                 ("strong_lt_05", lambda x: x < 0.5)):
            group = [r for r in resolved if predicate(val(r, "filter_compatible_fraction"))]
            consumed = sum(source_by_boundary[(r["seed"], r["floor"], r["encounter"], r["decision_index"])]
                           in ("existing_filtered_posterior", "collapse_fresh") for r in group)
            discarded = sum(source_by_boundary[(r["seed"], r["floor"], r["encounter"], r["decision_index"])]
                            == "fresh_initial" for r in group)
            print(f"{label},total={len(group)},consumed={consumed},discarded={discarded},"
                  f"discarded_fraction={discarded / len(group) if group else float('nan'):.6f}")
        for source in ("existing_filtered_posterior", "collapse_fresh", "fresh_initial"):
            group = [r for r in resolved if source_by_boundary[
                (r["seed"], r["floor"], r["encounter"], r["decision_index"])] == source]
            if group:
                print(f"source={source},collapse_rate={avg(group, 'posterior_collapse'):.6f},"
                      f"draw_diversity={avg(group, 'distinct_surviving_draw_orders'):.6f},"
                      f"rng_diversity={avg(group, 'distinct_surviving_rng_signatures'):.6f}")
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