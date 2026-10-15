#!/usr/bin/env python3
"""Summarize STS_OOC_MCTS_REUSE_TRACE rows (issue #339 reroot opportunity).

Each row is one real OOC decision. A decision is a reroot opportunity when its
public fingerprint equals a stored decision node of the previous completed
non-singleton search under that search's selected root action. Retained work is
the matching node's visit count (simulations that passed through it). Merged
work sums the visits of every publicly identical particle on that branch, an
upper bound that direct single-node rerooting cannot reach.
"""
import argparse
import collections
import json


def depth_bucket(depth):
    return "1" if depth == 1 else "2" if depth == 2 else "3+"


def summarize(rows, identity):
    searched = [r for r in rows if r["searched"] and not r["aborted"]]
    out = {"identity": identity, "decisions": len(rows),
           "searchedDecisions": len(searched),
           "singletonDecisions": sum(r["singleton"] for r in rows)}
    for label, subset in (("all", rows), ("searched", searched)):
        with_prev = [r for r in subset if r["previousSearch"]]
        hits = [r for r in with_prev if r[identity]["selectedBranchMatches"]]
        any_hits = [r for r in with_prev if r[identity]["matches"]]
        depths = collections.Counter(depth_bucket(r[identity]["best"]["depth"]) for r in hits)
        retained = [r[identity]["best"]["visits"] for r in hits]
        merged = [r[identity]["selectedBranchVisitsSum"] for r in hits]
        out[label] = {
            "decisions": len(subset), "withPreviousSearch": len(with_prev),
            "selectedBranchHits": len(hits), "anyBranchHits": len(any_hits),
            "hitRate": len(hits) / len(subset) if subset else 0.0,
            "depth": dict(sorted(depths.items())),
            "combatOnPath": sum(r[identity]["best"]["combatOnPath"] for r in hits),
            "publicStochasticOnPath": sum(r[identity]["best"]["publicStochasticOnPath"] for r in hits),
            "retainedVisits": sum(retained),
            "retainedVisitsMedian": sorted(retained)[len(retained) // 2] if retained else 0,
            "retainedVisitsMax": max(retained, default=0),
            "mergedVisits": sum(merged),
            "mergedVisitsMedian": sorted(merged)[len(merged) // 2] if merged else 0,
        }
    total_sims = sum(r["simulations"] for r in searched)
    hits = [r for r in searched if r["previousSearch"] and r[identity]["selectedBranchMatches"]]
    retained = sum(r[identity]["best"]["visits"] for r in hits)
    merged = sum(r[identity]["selectedBranchVisitsSum"] for r in hits)
    out["searchedSimulations"] = total_sims
    out["retainedFractionOfSearchedSimulations"] = retained / total_sims if total_sims else 0.0
    out["mergedFractionOfSearchedSimulations"] = merged / total_sims if total_sims else 0.0
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("traces", nargs="+")
    args = parser.parse_args()
    rows = []
    for path in args.traces:
        with open(path) as handle:
            rows.extend(json.loads(line) for line in handle if line.strip())
    for identity in ("rng", "public"):
        print(json.dumps(summarize(rows, identity), indent=1))
    misses = collections.Counter(
        (r["previous"]["screen"], r["screen"], r["floor"] != r["previous"]["floor"])
        for r in rows if r["searched"] and r["previousSearch"] and not r["public"]["selectedBranchMatches"])
    print("public-identity searched misses by (previous screen, screen, floor changed):")
    for key, count in misses.most_common():
        print(" ", key, count)


if __name__ == "__main__":
    main()
