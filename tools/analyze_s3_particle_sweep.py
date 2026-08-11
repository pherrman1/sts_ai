#!/usr/bin/env python3
"""Analyze paired Searcher3 particle-count gameplay and boundary diagnostics."""
import argparse
import csv
import statistics
from collections import Counter


def read(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def mean(rows, key):
    values = [float(r[key]) for r in rows]
    return statistics.mean(values) if values else 0.0


def median(rows, key):
    values = [float(r[key]) for r in rows]
    return statistics.median(values) if values else 0.0


def gameplay(path):
    rows = read(path)
    wins = sum(int(r["won"]) for r in rows)
    return rows, (wins, wins / len(rows), mean(rows, "floor"), median(rows, "floor"),
                  mean(rows, "hpEnd"), mean(rows, "sec"))


def diagnostic(path):
    rows = read(path)
    collapse = [r for r in rows if r["posterior_collapse"] == "1"]
    attempts = sum(int(r["propagated_particles_attempted"]) for r in rows)
    failures = sum(int(r["propagation_failures"]) for r in rows)
    action_types = {"0": "CARD", "1": "POTION", "2": "SINGLE_SELECT",
                    "3": "MULTI_SELECT", "4": "END_TURN"}
    by_type = Counter(action_types.get(r["action_type"], r["action_type"])
                      for r in collapse)
    by_type_all = Counter(action_types.get(r["action_type"], r["action_type"])
                          for r in rows)
    return {
        "rows": len(rows),
        "seeds": len({r["seed"] for r in rows}),
        "collapse_rate": len(collapse) / len(rows),
        "collapse_count": len(collapse),
        "prop_failure_rate": failures / attempts if attempts else 0.0,
        "compatible_mean": mean(rows, "filter_compatible_fraction"),
        "compatible_median": median(rows, "filter_compatible_fraction"),
        "distinct_draw_mean": mean(rows, "distinct_surviving_draw_orders"),
        "distinct_draw_median": median(rows, "distinct_surviving_draw_orders"),
        "distinct_rng_mean": mean(rows, "distinct_surviving_rng_signatures"),
        "distinct_rng_median": median(rows, "distinct_surviving_rng_signatures"),
        "filter_cpu_ms": mean(rows, "filter_cpu_ms"),
        "init_cpu_ms": mean(rows, "belief_initialization_cpu_ms"),
        "search_cpu_ms": mean(rows, "search_cpu_ms"),
        "sampled_mean": mean(rows, "distinct_particles_sampled"),
        "sampled_fraction": mean(rows, "sampled_particle_fraction"),
        "never_sampled_mean": mean(rows, "never_sampled_particles"),
        "usage_entropy": mean(rows, "particle_usage_entropy"),
        "collapse_by_type": by_type,
        "all_by_type": by_type_all,
        "collapse_reshuffle": sum(r["reshuffle_observed"] == "1" for r in collapse),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--arm", action="append", nargs=2, metavar=("PARTICLES", "CSV"), required=True)
    args = ap.parse_args()
    arms = {}
    for particle_count, path in args.arm:
        rows, game = gameplay(path)
        diag = diagnostic(path.replace(".csv", "_diag.csv"))
        arms[int(particle_count)] = (rows, game, diag)

    print("particles,rows,wins,win_rate,mean_floor,median_floor,mean_hp_end,mean_sec,"
          "collapse_rate,prop_failure_rate,compatible_mean,compatible_median,"
          "mean_draw_diversity,median_draw_diversity,mean_rng_diversity,median_rng_diversity,"
          "mean_filter_ms,mean_init_ms,mean_search_ms,mean_sampled,mean_sample_fraction,"
          "mean_never_sampled,usage_entropy")
    for n in sorted(arms):
        _, game, d = arms[n]
        print(n, d["rows"], game[0], f"{game[1]:.6f}", f"{game[2]:.3f}",
              f"{game[3]:.3f}", f"{game[4]:.3f}", f"{game[5]:.3f}",
              f"{d['collapse_rate']:.6f}", f"{d['prop_failure_rate']:.6f}",
              f"{d['compatible_mean']:.6f}", f"{d['compatible_median']:.6f}",
              f"{d['distinct_draw_mean']:.3f}", f"{d['distinct_draw_median']:.3f}",
              f"{d['distinct_rng_mean']:.3f}", f"{d['distinct_rng_median']:.3f}",
              f"{d['filter_cpu_ms']:.3f}", f"{d['init_cpu_ms']:.3f}",
              f"{d['search_cpu_ms']:.3f}", f"{d['sampled_mean']:.3f}",
              f"{d['sampled_fraction']:.6f}", f"{d['never_sampled_mean']:.3f}",
              f"{d['usage_entropy']:.3f}", sep=",")
        print("  collapse_by_action", dict(d["collapse_by_type"]),
              "all_actions", dict(d["all_by_type"]),
              "reshuffle", d["collapse_reshuffle"])

    base_rows = arms[64][0]
    base = {int(r["seed"]): r for r in base_rows}
    for n in sorted(arms):
        if n == 64:
            continue
        rows = {int(r["seed"]): r for r in arms[n][0]}
        flips = [(seed, base[seed]["won"], rows[seed]["won"])
                 for seed in base if base[seed]["won"] != rows[seed]["won"]]
        print(f"paired_flips_64_{n}={len(flips)}/{len(base)}", flips)


if __name__ == "__main__":
    main()