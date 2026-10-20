#!/usr/bin/env python3
"""A20 winrate check (PLAN.md): usage analyze.py TAR... > report.json

Reads every worker tar's out/units/*/S-a20-SEED.{done,csv,mcts.csv}. A unit counts when its .done line has rc=0 and
its CSV holds the seed's row. Reports Heart kills (won) / counted with a Wilson 95% interval, reached Act 4 (act >= 4),
Act-1 deaths, mean floor, seconds per run and MCTS CPU per OOC decision.
"""
import csv, io, json, math, re, sys, tarfile

EXPECTED = set(range(111194580, 111195092))


def wilson(k, n, z=1.959964):
    if n == 0:
        return [None, None]
    p = k / n; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(c - h, 4), round(c + h, 4)]


units, rcs = {}, {}
for path in sys.argv[1:]:
    with tarfile.open(path) as t:
        files = {m.name: m for m in t.getmembers() if m.isfile()}
        for name, m in files.items():
            g = re.search(r"/S-a20-(\d+)\.done$", name)
            if not g:
                continue
            seed = int(g.group(1)); base = name[:-5]
            line = t.extractfile(m).read().decode().strip()
            rc = re.search(r"rc=(\d+)", line).group(1); rcs[seed] = rc
            if rc != "0" or base + ".csv" not in files:
                continue
            rows = [r for r in csv.DictReader(io.StringIO(t.extractfile(files[base + ".csv"]).read().decode()))
                    if int(r["seed"]) == seed]
            if len(rows) != 1:
                continue
            u = rows[0]
            if base + ".mcts.csv" in files:
                tr = list(csv.DictReader(io.StringIO(t.extractfile(files[base + ".mcts.csv"]).read().decode())))
                if tr:
                    u["oocDecisions"], u["mctsCpuSec"] = float(tr[-1]["oocDecisions"]), float(tr[-1]["mctsCpuSec"])
            if seed in units:
                raise SystemExit(f"duplicate seed {seed}")
            units[seed] = u

seeds = sorted(s for s in units if s in EXPECTED)
n = len(seeds)
won = sum(int(units[s]["won"]) for s in seeds)
act4 = sum(int(units[s]["act"]) >= 4 for s in seeds)
act1 = sum(int(units[s]["act"]) == 1 and int(units[s]["won"]) == 0 for s in seeds)
dec = sum(units[s].get("oocDecisions", 0) for s in seeds); cpu = sum(units[s].get("mctsCpuSec", 0) for s in seeds)
rep = {
    "counted": n, "expected": len(EXPECTED), "missing_count": len(EXPECTED - set(seeds)),
    "nonzero_rc": {str(s): rc for s, rc in sorted(rcs.items()) if rc != "0"},
    "heart_kills": won, "winrate": round(won / n, 4) if n else None, "winrate_wilson95": wilson(won, n),
    "reached_act4": act4, "act4_rate": round(act4 / n, 4) if n else None, "act4_wilson95": wilson(act4, n),
    "heart_kills_per_act4": round(won / act4, 4) if act4 else None,
    "act1_deaths": act1, "mean_floor": round(sum(int(units[s]["floor"]) for s in seeds) / n, 2) if n else None,
    "sec_per_run": round(sum(float(units[s]["sec"]) for s in seeds) / n, 1) if n else None,
    "mcts_cpu_sec_per_decision": round(cpu / dec, 3) if dec else None,
    "act_reached": {a: sum(int(units[s]["act"]) == a for s in seeds) for a in range(1, 5)},
}
json.dump(rep, sys.stdout, indent=1); print()
