#!/usr/bin/env python3
"""Freeze the #347 default-stack boss deaths from the stage-1 rows (PLAN.md).

Reads only the stage-1 bestbench rows (default[0-3].csv) for seeds
66000000..66000255. Every run that died to an act boss is selected, up to
MAX_ENTRIES by ascending SHA-256 rank; nothing is replaced afterwards.
Usage: select.py SOURCE_DIR OUT.json
"""
import csv, glob, hashlib, importlib.util, json, os, sys

# Boss enum values parsed from the C++ header by the #425 selector.
_spec = importlib.util.spec_from_file_location("rescue_select", os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "../boss_budget_rescue_347_pilot_20261007/select.py"))
_rescue = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_rescue)
BOSSES, BOSS_FLOOR = _rescue.BOSSES, _rescue.BOSS_FLOOR

SEEDS = list(range(66000000, 66000256))
DOMAIN = "boss-deaths-347-v1"
MAX_ENTRIES = 48
PLANNER_REPS = 8


def load(source_dir):
    rows = {}
    for path in sorted(glob.glob(os.path.join(source_dir, "default[0-3].csv"))):
        with open(path, newline="") as f:
            for r in csv.DictReader(f):
                seed = int(r["seed"])
                if seed in rows:
                    sys.exit(f"duplicate seed {seed}")
                rows[seed] = {k: (float(v) if k == "sec" else int(v)) for k, v in r.items()}
    if sorted(rows) != SEEDS:
        sys.exit("stage-1 rows do not cover exactly seeds 66000000..66000255")
    return rows


def main():
    source_dir, out = sys.argv[1], sys.argv[2]
    rows = load(source_dir)
    losses = [s for s in SEEDS if rows[s]["won"] == 0]
    deaths = []
    for s in losses:
        if rows[s]["deathEncounter"] not in BOSSES:
            continue
        act, boss = BOSSES[rows[s]["deathEncounter"]]
        deaths.append({"stratum": "D", "sourceArm": "default", "seed": s, "act": act, "boss": boss,
                       "floorMatchesBossFloor": rows[s]["floor"] == BOSS_FLOOR[act],
                       "historicalRow": {k: v for k, v in rows[s].items() if k != "sec"},
                       "rankKey": hashlib.sha256(f"{DOMAIN}:{s}:{act}".encode()).hexdigest()})
    selected = sorted(deaths, key=lambda c: c["rankKey"])[:MAX_ENTRIES]
    selected.sort(key=lambda c: c["seed"])
    for c in selected:
        c["stateId"] = f"D-{c['seed']}-a{c['act']}"
    census = {"runs": len(SEEDS), "wins": sum(rows[s]["won"] for s in SEEDS), "losses": len(losses),
              "bossDeaths": len(deaths),
              "bossDeathsByAct": {a: sum(d["act"] == a for d in deaths) for a in (1, 2, 3)},
              "cpuSeconds": sum(rows[s]["sec"] for s in SEEDS)}
    manifest = {
        "schema": "boss_deaths_default_347_selection_v1",
        "plannerReps": PLANNER_REPS,
        "source": {"seeds": "66000000..66000255", "runFilesSha256": {
            os.path.basename(p): hashlib.sha256(open(p, "rb").read()).hexdigest()
            for p in sorted(glob.glob(os.path.join(source_dir, "default[0-3].csv")))}},
        "rule": {"eligible": "won == 0 and deathEncounter is an act boss",
                 "order": f"ascending sha256('{DOMAIN}:{{seed}}:{{act}}'), first {MAX_ENTRIES}",
                 "plannerSeedDomain": "boss-deaths-347-planner-v1:{runSeed}:{act}:{rep}"},
        "census": census, "eligibleCount": len(deaths),
        "selected": selected, "dropped": len(deaths) - len(selected),
    }
    with open(out, "w") as f:
        json.dump(manifest, f, indent=1)
        f.write("\n")
    print(json.dumps(census))
    for c in selected:
        print(c["stateId"], c["boss"], "floor", c["historicalRow"]["floor"],
              "" if c["floorMatchesBossFloor"] else "FLOOR_MISMATCH")
    print("selected", len(selected), "of", len(deaths))


if __name__ == "__main__":
    main()
