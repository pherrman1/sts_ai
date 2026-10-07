#!/usr/bin/env python3
"""Freeze the eight #347 boss-entry sources from the #417 pilot rows (PLAN.md).

Reads only historical bestbench rows (flat10k*.csv, mcts*.csv) of the #417
pilot. Writes the complete eligibility list and the selected manifest.
Usage: select.py RUN_DIR OUT.json
"""
import csv, glob, hashlib, json, os, sys

BOSS_NAMES = {1: ("SLIME_BOSS", "THE_GUARDIAN", "HEXAGHOST"),
              2: ("AUTOMATON", "COLLECTOR", "CHAMP"),
              3: ("AWAKENED_ONE", "TIME_EATER", "DONU_AND_DECA")}


def encounter_values(header):
    """Enum values of MonsterEncounter, parsed from the C++ header."""
    body = open(header).read().split("enum class MonsterEncounter", 1)[1].split("};", 1)[0]
    values, nxt = {}, 0
    for line in body.split("{", 1)[1].splitlines():
        name = line.split("//")[0].strip().rstrip(",")
        if not name:
            continue
        if "=" in name:
            name, nxt = name.split("=")[0].strip(), int(name.split("=")[1])
        values[name] = nxt
        nxt += 1
    return values


ENUM = encounter_values(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     "../../../../include/constants/MonsterEncounters.h"))
BOSSES = {ENUM[name]: (act, name) for act, names in BOSS_NAMES.items() for name in names}
BOSS_FLOOR = {1: 16, 2: 33, 3: 50}
DOMAIN = "boss-loss-347-pilot-v1"
PER_STRATUM = 4


def load(run_dir, arm):
    rows = {}
    for path in sorted(glob.glob(os.path.join(run_dir, f"{arm}[0-9].csv"))):
        with open(path, newline="") as f:
            for r in csv.DictReader(f):
                seed = int(r["seed"])
                if seed in rows:
                    sys.exit(f"duplicate seed {seed} in arm {arm}")
                rows[seed] = {k: (float(v) if k == "sec" else int(v)) for k, v in r.items()}
                rows[seed]["file"] = os.path.basename(path)
    return rows


def boss_loss(row):
    """Boss identity comes from the recorded death encounter, not the floor."""
    if row["won"] != 0 or row["deathEncounter"] not in BOSSES:
        return None
    act, boss = BOSSES[row["deathEncounter"]]
    return {"act": act, "boss": boss, "floorMatchesBossFloor": row["floor"] == BOSS_FLOOR[act]}


def rank_key(stratum, seed, act):
    return hashlib.sha256(f"{DOMAIN}:{stratum}:{seed}:{act}".encode()).hexdigest()


def select(cands, stratum):
    buckets = {a: sorted((c for c in cands if c["act"] == a), key=lambda c: c["rankKey"])
               for a in (1, 2, 3)}
    chosen = []
    while len(chosen) < PER_STRATUM and any(buckets.values()):
        for act in (1, 2, 3):
            if buckets[act] and len(chosen) < PER_STRATUM:
                chosen.append(buckets[act].pop(0))
    return chosen


def main():
    run_dir, out = sys.argv[1], sys.argv[2]
    flat, mcts = load(run_dir, "flat10k"), load(run_dir, "mcts")
    seeds = list(range(48000000, 48000128))
    for arm, rows in (("flat10k", flat), ("mcts", mcts)):
        if sorted(rows) != seeds:
            sys.exit(f"arm {arm} does not cover exactly the 128 pilot seeds")
    census = {}
    for arm, rows in (("flat10k", flat), ("mcts", mcts)):
        losses = [s for s in seeds if rows[s]["won"] == 0]
        boss = [s for s in losses if boss_loss(rows[s])]
        census[arm] = {"wins": sum(rows[s]["won"] for s in seeds), "losses": len(losses),
                       "bossLosses": len(boss),
                       "bossLossesByAct": {a: sum(boss_loss(rows[s])["act"] == a for s in boss)
                                           for a in (1, 2, 3)}}

    def cand(stratum, arm, rows, seed):
        info = boss_loss(rows[seed])
        return {"stratum": stratum, "sourceArm": arm, "seed": seed, **info,
                "historicalRow": rows[seed], "pairedArmRow": (flat if arm == "mcts" else mcts)[seed],
                "rankKey": rank_key(stratum, seed, info["act"])}

    eligible_r = [cand("R", "mcts", mcts, s) for s in seeds
                  if boss_loss(mcts[s]) and flat[s]["won"] == 1]
    chosen_r = select(eligible_r, "R")
    r_seeds = {c["seed"] for c in chosen_r}
    eligible_c = [cand("C", "flat10k", flat, s) for s in seeds
                  if boss_loss(flat[s]) and s not in r_seeds]
    chosen_c = select(eligible_c, "C")
    selected = chosen_r + chosen_c
    if len({c["seed"] for c in selected}) != len(selected):
        sys.exit("selected seeds are not distinct")
    for i, c in enumerate(selected):
        c["stateId"] = f"{c['stratum']}{i % PER_STRATUM + 1}-{c['seed']}-a{c['act']}"
    shortfall = 2 * PER_STRATUM - len(selected)
    manifest = {
        "schema": "boss_budget_rescue_347_pilot_selection_v1",
        "source": {"pr": 417, "ledger": "§384",
                   "evidenceRef": "10e56bd813202db969ddb176aad8ed33173179f7",
                   "historicalGameplayBaseline": "5e9583cc4c871b887ab0eccc5e290c7c0f990117",
                   "historicalProducerBuild": "aa000e8a0f4a1b839555e78ec1b874e1f77aa722",
                   "runFilesSha256": {os.path.basename(p): hashlib.sha256(open(p, "rb").read()).hexdigest()
                                      for p in sorted(glob.glob(os.path.join(run_dir, "*.csv")))
                                      if os.path.basename(p).startswith(("flat10k", "mcts"))}},
        "rule": {"domain": f"{DOMAIN}:{{stratum}}:{{seed}}:{{act}}", "perStratum": PER_STRATUM,
                 "R": "mcts boss loss and flat10k won the same seed",
                 "C": "flat10k boss loss, seed not selected into R",
                 "order": "round-robin acts 1,2,3 skipping empty buckets; ascending SHA-256 within bucket",
                 "bossIdentity": "historical deathEncounter; confirmed again at reconstruction"},
        "census": census,
        "eligible": {"R": sorted(eligible_r, key=lambda c: (c["act"], c["rankKey"])),
                     "C": sorted(eligible_c, key=lambda c: (c["act"], c["rankKey"]))},
        "selected": selected, "shortfall": shortfall,
    }
    with open(out, "w") as f:
        json.dump(manifest, f, indent=1, sort_keys=False)
        f.write("\n")
    print(json.dumps(census))
    for c in selected:
        print(c["stateId"], c["sourceArm"], c["boss"], "floor", c["historicalRow"]["floor"],
              "floorOK" if c["floorMatchesBossFloor"] else "FLOOR_MISMATCH")
    print("eligible R", len(eligible_r), "C", len(eligible_c), "shortfall", shortfall)


if __name__ == "__main__":
    main()
