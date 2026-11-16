#!/usr/bin/env python3
"""#1054 Stage 0: how often do same-turn infinites occur in G16 + mb4 whole runs?

usage: analyze.py OUT_DIR [REF_DIR] > analysis.json

OUT_DIR holds, per replayed seed, G16-SEED.{done,log,err} and G16-SEED.states.jsonl.gz (one_combat
STS_COMBAT_STATE_CAPTURE) plus O-SEED.jsonl (combat_infinity_oracle --snapshots, natural mode).
REF_DIR (optional) holds the §775 G16 logs (G16-SEED.log/.err anywhere below it): a game counts only
if its BEST line and its Gumbel roots/sims line equal §775's.

Descriptive only: no gate. Definitions:
- certified turn: the oracle replays a damaging same-turn card cycle on the concrete turn-start state
  to a real victory (CERTIFIED_KILL) or to the Heart's exhausted Invincible cap (CERTIFIED_TURN_CAP).
- candidate turn: a damaging repeated control state whose replay did not certify.
- missed: a certified-kill turn after which the fight did not end that turn in a win, or the player
  lost HP between that turn start and the fight's end.
"""
import collections, glob, gzip, json, os, re, sys

CERT = ("CERTIFIED_KILL", "CERTIFIED_TURN_CAP")


def room_class(act, room, encounter):
    if act == 4:
        return "heart" if room == "BOSS" else "shield_spear" if room == "ELITE" else "act4_other"
    return {"MONSTER": "hallway", "ELITE": "elite", "BOSS": "boss"}.get(room, "other")


def best_line(path):
    try:
        for line in open(path, errors="replace"):
            if line.startswith("BEST ") and "win%=" in line:
                return re.sub(r"cpu_sec/run=.*", "", line).strip()
    except FileNotFoundError:
        return None
    return None


def roots_line(path):
    try:
        for line in open(path, errors="replace"):
            if line.startswith("[silver] whole-run Gumbel roots="):
                return line.strip()
    except FileNotFoundError:
        return None
    return None


def wilson(k, n, z=1.96):
    if n == 0:
        return [None, None]
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / d
    return [round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)]


def main():
    out = sys.argv[1]
    ref = sys.argv[2] if len(sys.argv) > 2 else None
    refs = {}
    if ref:
        for p in glob.glob(os.path.join(ref, "**", "G16-*.log"), recursive=True):
            seed = int(re.search(r"G16-(\d+)\.log$", p).group(1))
            refs[seed] = (best_line(p), roots_line(p[:-4] + ".err"))
    runs, bad = [], []
    for done in sorted(glob.glob(os.path.join(out, "G16-*.done"))):
        seed = int(re.search(r"G16-(\d+)\.done$", done).group(1))
        rc = re.search(r"rc=(\d+)", open(done).read()).group(1)
        b = done[:-5]
        opath = os.path.join(out, f"O-{seed}.jsonl")
        if rc != "0" or not os.path.exists(opath):
            bad.append({"seed": seed, "why": f"rc={rc}" if rc != "0" else "no oracle output"})
            continue
        if ref:
            mine = (best_line(b + ".log"), roots_line(b + ".err"))
            if seed not in refs or refs[seed] != mine:
                bad.append({"seed": seed, "why": "does not reproduce §775", "mine": mine, "ref": refs.get(seed)})
                continue
        fights = [json.loads(l) for l in gzip.open(b + ".states.jsonl.gz", "rt") if '"kind":"fight"' in l]
        orows = [json.loads(l) for l in open(opath)]
        summary = orows[-1]
        turns = [r for r in orows[:-1]]
        won = "win%=100.0" in (best_line(b + ".log") or "")
        runs.append({"seed": seed, "won": won, "fights": fights, "turns": turns, "summary": summary})

    by_class = collections.defaultdict(lambda: collections.Counter())
    run_flags = []
    missed, certified_rows, cpu, node_cap, depth_cap, nodes = [], [], [], 0, 0, []
    proxies = collections.Counter()
    proxy_rows = []
    unsupported = collections.Counter()
    enabler_runs = collections.Counter()
    lost_fights = collections.Counter(max_cards_turn=0)
    fights_won = {}
    for run in runs:
        fights = {f["fight"]: f for f in run["fights"]}
        flags = {"seed": run["seed"], "won": run["won"], "certified": False, "candidate": False,
                 "certified_classes": set(), "candidate_classes": set(), "heart_reached": False}
        per_fight = collections.defaultdict(list)
        for t in run["turns"]:
            per_fight[t["fight"]].append(t)
            cpu.append(t.get("cpu_ms", 0.0))
            nodes.append(t.get("nodes", 0))
            node_cap += bool(t.get("node_cap_hit"))
            depth_cap += bool(t.get("depth_cap_hit"))
            if not t.get("supported"):
                unsupported[t.get("reason")] += 1
            if t.get("fight_start_cards") is not None:
                c = t["fight_start_cards"]
                rel = set(t.get("enabler_relics", []))
                n = lambda *names: sum(v for k, v in c.items() if k.rstrip("+") in names)
                if n("DROPKICK") >= 1 and n("BASH", "UPPERCUT", "THUNDERCLAP", "SHOCKWAVE", "TRIP") >= 1:
                    enabler_runs[("dropkick+vulnerable_source", run["seed"])] = 1
                if n("CORRUPTION") and "DEAD_BRANCH" in rel:
                    enabler_runs[("corruption+dead_branch", run["seed"])] = 1
                if n("FEEL_NO_PAIN") and n("DARK_EMBRACE") and n("CORRUPTION"):
                    enabler_runs[("corruption+fnp+dark_embrace", run["seed"])] = 1
                if "UNCEASING_TOP" in rel:
                    enabler_runs[("unceasing_top", run["seed"])] = 1
        for fid, f in fights.items():
            fights_won[(run["seed"], fid)] = bool(f["won"])
            cls = room_class(f["act"], f["room"], f["encounter"])
            by_class[cls]["fights"] += 1
            if cls == "heart":
                flags["heart_reached"] = True
            if max(f.get("cards_per_turn") or [0]) >= 25:
                proxies["fights_with_turn_ge_25_cards"] += 1
                proxy_rows.append({"seed": run["seed"], "fight": fid, "encounter": f["encounter"],
                                   "max_cards_turn": max(f["cards_per_turn"])})
            if f.get("turns", 0) >= 99 or f.get("aborted"):
                proxies["fights_at_turn_or_action_cap"] += 1
            ts = per_fight.get(fid, [])
            cert = [t for t in ts if t["classification"] in CERT]
            cand = [t for t in ts if t["classification"] == "PRODUCTIVE_CYCLE_CANDIDATE"]
            if cert:
                by_class[cls]["fights_certified"] += 1
                flags["certified"] = True
                flags["certified_classes"].add(cls)
            if cand:
                by_class[cls]["fights_candidate"] += 1
                flags["candidate"] = True
                flags["candidate_classes"].add(cls)
            for t in cert:
                certified_rows.append({k: t.get(k) for k in ("seed", "fight", "turn", "act", "room", "encounter",
                                       "classification", "cycle_length", "repetitions_to_terminal",
                                       "player_hp_delta_per_cycle", "hp")})
                if t["classification"] == "CERTIFIED_KILL":
                    ended_this_turn = f["won"] and f["turns"] == t["turn"]
                    hp_lost_after = t["hp"] - f["hp_end_battle"]
                    if not ended_this_turn or hp_lost_after > 0:
                        missed.append({"seed": run["seed"], "fight": fid, "turn": t["turn"],
                                       "encounter": f["encounter"], "fight_won": f["won"],
                                       "fight_end_turn": f["turns"], "hp_lost_after": hp_lost_after,
                                       "oracle_replay_hp_lost": (t.get("replay") or {}).get("player_hp_lost"),
                                       "kind": "hp_cost_only" if ended_this_turn else "not_won_that_turn"})
            if not f["won"] and not f.get("escaped"):
                lost_fights["fights"] += 1
                lost_fights["with_non_none_verdict"] += any(t["classification"] != "NONE" for t in ts)
                lost_fights["with_node_cap_turn"] += any(t.get("node_cap_hit") for t in ts)
                lost_fights["max_cards_turn"] = max(lost_fights["max_cards_turn"],
                                                    max(f.get("cards_per_turn") or [0]))
        for cls in set(room_class(f["act"], f["room"], f["encounter"]) for f in fights.values()):
            by_class[cls]["runs_reaching"] += 1
        for cls in flags["certified_classes"]:
            by_class[cls]["runs_certified"] += 1
        for cls in flags["candidate_classes"]:
            by_class[cls]["runs_candidate"] += 1
        flags["certified_classes"] = sorted(flags["certified_classes"])
        flags["candidate_classes"] = sorted(flags["candidate_classes"])
        run_flags.append(flags)

    n = len(run_flags)
    k_cert = sum(r["certified"] for r in run_flags)
    k_any = sum(r["certified"] or r["candidate"] for r in run_flags)
    heart = [r for r in run_flags if r["heart_reached"]]
    cpu_sorted = sorted(cpu)
    q = lambda p: cpu_sorted[min(len(cpu_sorted) - 1, int(p * len(cpu_sorted)))] if cpu_sorted else None
    enablers = collections.Counter(k for k, _ in enabler_runs)
    print(json.dumps({
        "runs": n, "bad_or_dropped": bad,
        "runs_with_certified": k_cert, "share_certified": round(k_cert / n, 4) if n else None,
        "share_certified_wilson95": wilson(k_cert, n),
        "runs_with_certified_or_candidate": k_any, "share_any_wilson95": wilson(k_any, n),
        "go_threshold_share": 0.05,
        "by_room_class": {c: dict(v) for c, v in sorted(by_class.items())},
        "heart": {"runs_reaching": len(heart),
                  "kill_rate_with_certified": (sum(r["won"] for r in heart if r["certified"]),
                                               sum(1 for r in heart if r["certified"])),
                  "kill_rate_without": (sum(r["won"] for r in heart if not r["certified"]),
                                        sum(1 for r in heart if not r["certified"]))},
        "certified_turns": certified_rows, "missed_certified_kills": missed,
        "oracle": {"turn_states": len(cpu), "cpu_ms_mean": round(sum(cpu) / len(cpu), 3) if cpu else None,
                   "cpu_ms_p50": q(0.5), "cpu_ms_p99": q(0.99), "cpu_ms_max": cpu_sorted[-1] if cpu else None,
                   "cpu_s_per_run": round(sum(cpu) / 1000 / n, 2) if n else None,
                   "node_cap_hits": node_cap, "depth_cap_hits": depth_cap,
                   "nodes_mean": round(sum(nodes) / len(nodes), 1) if nodes else None,
                   "unsupported": dict(unsupported)},
        "proxies": dict(proxies), "proxy_fights": proxy_rows,
        "proxy_runs": len({p["seed"] for p in proxy_rows}),
        "proxy_fights_won": sum(fights_won[(p["seed"], p["fight"])] for p in proxy_rows),
        "lost_fights": dict(lost_fights),
        "enabler_runs": dict(enablers),
    }, indent=1, sort_keys=True))


if __name__ == "__main__":
    main()
