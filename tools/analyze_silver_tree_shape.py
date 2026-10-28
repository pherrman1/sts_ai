#!/usr/bin/env python3
"""Per-encounter search shape of native Silver from STS_SILVER_TREE_PROFILE rows (#888).

Reads rows that carry the "search" block (searched real decisions; singleton skips and
error rows are left out) and reports, per encounter:

- depth per simulation, pooled over the encounter's decisions: tree actions, tree rounds,
  rollout actions, rollout rounds, total actions, total rounds (median / p90 / max);
- endpoint classes and stop reasons;
- the most-visited line's depth where its edges keep >= 10 visits and >= 10% of the root's visits;
- the first End Turn transition on the most-visited line: visits, distinct outcome nodes,
  distinct public projections, RNG draws, largest-child share and effective children;
  plus how many first End Turn transitions the search reached;
- node growth per simulation and tree size at the end of the search.

Cross-encounter rows weight encounters equally (median of encounter medians).
Rounds are BattleContext::turn deltas: one round = a player turn plus the enemy turn.
"""
import argparse
import collections
import gzip
import json
import statistics
import sys


def opener(path):
    return gzip.open(path, "rt") if path.endswith(".gz") else open(path)


def hist_add(target, hist):
    for k, v in hist.items():
        target[int(k)] += v


def hist_quantile(hist, q):
    total = sum(hist.values())
    if total == 0:
        return None
    need = q * total
    run = 0
    for k in sorted(hist):
        run += hist[k]
        if run >= need:
            return k
    return max(hist)


def hist_stats(hist):
    if not hist or sum(hist.values()) == 0:
        return {"n": 0, "median": None, "p90": None, "max": None, "mean": None}
    total = sum(hist.values())
    return {"n": total, "median": hist_quantile(hist, 0.5), "p90": hist_quantile(hist, 0.9), "max": max(hist),
            "mean": round(sum(k * v for k, v in hist.items()) / total, 2)}


def q(values, p):
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    idx = min(len(values) - 1, max(0, int(round(p * (len(values) - 1)))))
    return values[idx]


def dist(values):
    values = [v for v in values if v is not None]
    if not values:
        return {"n": 0, "median": None, "p90": None, "max": None, "mean": None}
    return {"n": len(values), "median": round(statistics.median(values), 3), "p90": round(q(values, 0.9), 3),
            "max": round(max(values), 3), "mean": round(statistics.fmean(values), 3)}


def pv_depth(pv, root_visits, share):
    """Deepest step of the most-visited line whose edge keeps >= max(10, share * root visits) visits."""
    need = max(10, share * root_visits)
    actions = rounds = 0
    for a, r, visits, _end in pv:
        if visits < need:
            break
        actions, rounds = a, r
    return actions, rounds


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("profiles", nargs="+")
    ap.add_argument("--output", required=True, help="summary JSON")
    ap.add_argument("--markdown", help="per-encounter tables")
    args = ap.parse_args()

    rows = []
    for path in args.profiles:
        with opener(path) as f:
            for line in f:
                row = json.loads(line)
                row["_file"] = path
                rows.append(row)
    searched = [r for r in rows if r.get("search") and not r.get("singleton_skip") and not r.get("error")]
    skipped = sum(1 for r in rows if r.get("singleton_skip"))
    errors = sum(1 for r in rows if r.get("error"))

    by_enc = collections.defaultdict(list)
    for r in searched:
        by_enc[r["encounter"]].append(r)

    hist_keys = {"tree_actions": None, "tree_rounds": "tree_rounds", "rollout_actions": "rollout_actions",
                 "rollout_rounds": "rollout_rounds", "total_actions": None, "total_rounds": "total_rounds"}
    encounters = {}
    for enc, rs in sorted(by_enc.items()):
        h = {k: collections.Counter() for k in hist_keys}
        endpoints = collections.Counter()
        stops = collections.Counter()
        growth = collections.Counter()
        dec = collections.defaultdict(list)
        for r in rs:
            s = r["search"]
            for name, e in r["endpoints"].items():
                endpoints[name] += e["count"]
                hist_add(h["tree_actions"], e["tree_depth"])
                hist_add(h["total_actions"], e["total_depth"])
            for k, src in hist_keys.items():
                if src:
                    hist_add(h[k], s[src])
            stops.update(s["stops"])
            hist_add(growth, s["new_nodes_per_simulation"])
            sims = r["completed_simulations"]
            dec["simulations"].append(sims)
            dec["cpu_seconds"].append(s["cpu_seconds"])
            dec["cpu_ms_per_1k_sims"].append(1e6 * s["cpu_seconds"] / sims if sims else None)
            # per-decision medians so the encounter summary is not dominated by big searches
            dec["tree_actions_median"].append(hist_quantile(
                {int(k): v for e in r["endpoints"].values() for k, v in e["tree_depth"].items()}, 0.5))
            dec["tree_rounds_median"].append(hist_quantile({int(k): v for k, v in s["tree_rounds"].items()}, 0.5))
            a10, r10 = pv_depth(s["pv"], s["root_visits"], 0.0)
            a_share, r_share = pv_depth(s["pv"], s["root_visits"], 0.10)
            dec["pv_actions_v10"].append(a10)
            dec["pv_rounds_v10"].append(r10)
            dec["pv_actions_10pct"].append(a_share)
            dec["pv_rounds_10pct"].append(r_share)
            ets = s["first_end_turns"]
            dec["first_end_turn_nodes"].append(len(ets))
            total_edge = sum(t["edge_visits"] for t in ets)
            dec["top_end_turn_share"].append(ets[0]["edge_visits"] / total_edge if total_edge else None)
            pvt = next((t for t in ets if t["on_pv"]), None)
            if pvt and pvt["stochastic"]:
                child_visits = pvt["visits"]
                dec["pv_et_visits"].append(pvt["visits"])
                dec["pv_et_children"].append(pvt["children"])
                dec["pv_et_observable"].append(pvt["observable"])
                dec["pv_et_draws"].append(pvt["draws"])
                dec["pv_et_cap"].append(pvt["cap"])
                dec["pv_et_max_child_share"].append(pvt["max_child_visits"] / child_visits if child_visits else None)
                dec["pv_et_effective"].append(pvt["effective_children"])
                dec["pv_et_terminal_children"].append(pvt["terminal_children"])
            elif pvt:
                dec["pv_et_deterministic"].append(1)
            else:
                dec["pv_et_missing"].append(1)
            created = s["allocated_nodes"] - s["allocated_nodes_before"]
            dec["nodes_end"].append(s["allocated_nodes"])
            dec["nodes_before"].append(s["allocated_nodes_before"])
            dec["nodes_created"].append(created)
            dec["nodes_per_sim"].append(created / sims if sims else None)
            dec["reachable_decision"].append(s["reachable_decision_nodes"])
            dec["reachable_chance"].append(s["reachable_chance_nodes"])
            dec["reachable_outcome_edges"].append(s["reachable_outcome_edges"])
            dec["inherited_visits"].append(r["inherited_visits"])
        sims_total = sum(growth.values())
        fights = {(r["_file"], r["seed"], r["combat_id"]) for r in rs}
        encounters[enc] = {
            "rooms": sorted({r["room"] for r in rs}), "acts": sorted({r["act"] for r in rs}),
            "fights": len(fights), "decisions": len(rs), "simulations": sims_total,
            "depth_per_simulation": {k: hist_stats(v) for k, v in h.items()},
            "endpoint_share": {k: round(v / sims_total, 4) for k, v in endpoints.items()} if sims_total else {},
            "stop_share": {k: round(v / sims_total, 4) for k, v in stops.items()} if sims_total else {},
            "growth_share": {"zero": round(growth.get(0, 0) / sims_total, 4),
                             "one": round(growth.get(1, 0) / sims_total, 4),
                             "multiple": round(sum(v for k, v in growth.items() if k >= 2) / sims_total, 4)}
            if sims_total else {},
            "per_decision": {k: dist(v) for k, v in dec.items()},
        }

    def cross(path):
        vals = []
        for e in encounters.values():
            cur = e
            for p in path:
                cur = cur.get(p) if isinstance(cur, dict) else None
            vals.append(cur)
        return dist(vals)

    summary = {
        "rows": len(rows), "searched_decisions": len(searched), "singleton_skips": skipped, "error_rows": errors,
        "encounters": encounters,
        "cross_encounter_equal_weight": {
            "tree_actions_median": cross(["depth_per_simulation", "tree_actions", "median"]),
            "tree_rounds_median": cross(["depth_per_simulation", "tree_rounds", "median"]),
            "rollout_rounds_median": cross(["depth_per_simulation", "rollout_rounds", "median"]),
            "total_rounds_median": cross(["depth_per_simulation", "total_rounds", "median"]),
            "pv_rounds_10pct_median": cross(["per_decision", "pv_rounds_10pct", "median"]),
            "pv_et_children_median": cross(["per_decision", "pv_et_children", "median"]),
            "pv_et_observable_median": cross(["per_decision", "pv_et_observable", "median"]),
            "nodes_end_median": cross(["per_decision", "nodes_end", "median"]),
            "nodes_per_sim_median": cross(["per_decision", "nodes_per_sim", "median"]),
        },
    }
    with open(args.output, "w") as f:
        json.dump(summary, f, indent=1, sort_keys=True)

    if args.markdown:
        out = []
        def g(e, *p):
            for k in p:
                e = e.get(k) if isinstance(e, dict) else None
            return e
        def fmt(x):
            return "-" if x is None else (f"{x:.2f}" if isinstance(x, float) and not float(x).is_integer() else f"{x:g}" if isinstance(x, float) else str(x))
        def mpm(d):
            return f"{fmt(d['median'])} / {fmt(d['p90'])} / {fmt(d['max'])}"
        out.append("### Depth per simulation (median / p90 / max, pooled over the encounter's simulations)\n")
        out.append("| encounter | room | fights | decisions | sims/decision (median) | CPU s/decision (median) | tree actions | tree rounds | rollout actions | rollout rounds | total actions | total rounds |")
        out.append("|---|---|---:|---:|---:|---:|---|---|---|---|---|---|")
        for enc, e in encounters.items():
            d = e["depth_per_simulation"]
            out.append(f"| {enc} | {','.join(e['rooms'])} | {e['fights']} | {e['decisions']} | "
                       f"{fmt(g(e,'per_decision','simulations','median'))} | {fmt(g(e,'per_decision','cpu_seconds','median'))} | "
                       + " | ".join(mpm(d[k]) for k in ["tree_actions", "tree_rounds", "rollout_actions",
                                                        "rollout_rounds", "total_actions", "total_rounds"]) + " |")
        out.append("\n### Endpoints, stop reasons and most-visited line\n")
        out.append("| encounter | victory | death | nonterminal | turn limit+engine stop | new leaf | terminal revisit | cycle | PV rounds (>=10 visits) median/max | PV rounds (>=10% root) median/max | PV actions (>=10% root) median |")
        out.append("|---|---:|---:|---:|---:|---:|---:|---:|---|---|---:|")
        for enc, e in encounters.items():
            es, ss, pd = e["endpoint_share"], e["stop_share"], e["per_decision"]
            out.append(f"| {enc} | {fmt(es.get('victory'))} | {fmt(es.get('death'))} | {fmt(es.get('nonterminal'))} | "
                       f"{fmt(round(es.get('turn_limit',0)+es.get('engine_stop',0),4))} | {fmt(ss.get('new_leaf'))} | "
                       f"{fmt(ss.get('terminal_revisit'))} | {fmt(ss.get('cycle'))} | "
                       f"{fmt(pd['pv_rounds_v10']['median'])}/{fmt(pd['pv_rounds_v10']['max'])} | "
                       f"{fmt(pd['pv_rounds_10pct']['median'])}/{fmt(pd['pv_rounds_10pct']['max'])} | "
                       f"{fmt(pd['pv_actions_10pct']['median'])} |")
        out.append("\n### First End Turn on the most-visited line (per-decision median / p90 / max)\n")
        out.append("| encounter | stochastic decisions | visits | distinct outcome nodes | distinct public states | RNG draws | widening cap | largest-child share | effective children | first End Turn nodes reached | top node's share of End Turn visits |")
        out.append("|---|---:|---|---|---|---|---|---|---|---|---|")
        for enc, e in encounters.items():
            pd = e["per_decision"]
            out.append(f"| {enc} | {pd['pv_et_visits']['n']} | {mpm(pd['pv_et_visits'])} | {mpm(pd['pv_et_children'])} | "
                       f"{mpm(pd['pv_et_observable'])} | {mpm(pd['pv_et_draws'])} | {mpm(pd['pv_et_cap'])} | "
                       f"{mpm(pd['pv_et_max_child_share'])} | {mpm(pd['pv_et_effective'])} | "
                       f"{mpm(pd['first_end_turn_nodes'])} | {mpm(pd['top_end_turn_share'])} |")
        out.append("\n### Node growth and tree size (per-decision median / p90 / max)\n")
        out.append("| encounter | sims with 0 / 1 / 2+ new nodes | nodes at end | nodes before (reused) | created | created per sim | reachable decision | reachable chance | reachable outcome edges |")
        out.append("|---|---|---|---|---|---|---|---|---|")
        for enc, e in encounters.items():
            pd, gs = e["per_decision"], e["growth_share"]
            out.append(f"| {enc} | {fmt(gs.get('zero'))} / {fmt(gs.get('one'))} / {fmt(gs.get('multiple'))} | "
                       f"{mpm(pd['nodes_end'])} | {mpm(pd['nodes_before'])} | {mpm(pd['nodes_created'])} | "
                       f"{mpm(pd['nodes_per_sim'])} | {mpm(pd['reachable_decision'])} | {mpm(pd['reachable_chance'])} | "
                       f"{mpm(pd['reachable_outcome_edges'])} |")
        with open(args.markdown, "w") as f:
            f.write("\n".join(out) + "\n")
    print(json.dumps({k: summary[k] for k in ["rows", "searched_decisions", "singleton_skips", "error_rows"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
