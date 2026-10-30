#!/usr/bin/env python3
"""Act-4 entry forks for one heartoutcomegen game (value_clean_labels_run1 campaign).

  a4_fork.py entry BASE.jsonl            first decision index in act 4 ('none' if the game never got there)
  a4_fork.py prefix BASE.jsonl FORK.jsonl INDEX   exit 0 iff every state/decision before INDEX is identical
  a4_fork.py summary OUT.json SEED INDEX BASE.jsonl [FORK.jsonl ...]   entry record + outcome per game (fork i = salt i)
"""
import gzip, json, sys


def rows(path):
    with (gzip.open if path.endswith(".gz") else open)(path, "rt") as f:
        return [json.loads(line) for line in f if line.strip()]


def outcome(rs):
    out = [r for r in rs if r.get("type") == "outcome"]
    if len(out) != 1 or not out[0].get("complete") or not out[0].get("integrityPassed"):
        raise SystemExit("incomplete or failed game")
    return out[0]


def entry(rs):
    # A decision row names its state; only searched decisions carry the act themselves.
    acts = {r["index"]: r["act"] for r in rs if r.get("type") == "state"}
    for r in rs:
        if r.get("type") == "decision" and acts[r["stateIndex"]] == 4:
            return r
    return None


def prefix(rs, index):
    out = []
    for r in rs:
        if r.get("type") == "decision":
            if r["decisionIndex"] >= index:
                break
            out.append(r)
        elif r.get("type") == "state":
            out.append(r)
    return out


def main(argv):
    if argv[1] == "entry":
        rs = rows(argv[2]); outcome(rs)
        e = entry(rs)
        print("none" if e is None else e["decisionIndex"])
    elif argv[1] == "prefix":
        index = int(argv[4])
        a, b = prefix(rows(argv[2]), index), prefix(rows(argv[3]), index)
        if not a or a != b:
            raise SystemExit("fork prefix differs from the base game")
    elif argv[1] == "summary":
        path, seed, index, games = argv[2], int(argv[3]), int(argv[4]), argv[5:]
        result = {"schema": "a4-entry-forks-v1", "seed": seed, "entryDecisionIndex": index, "games": []}
        for i, g in enumerate(games):
            rs = rows(g); o = outcome(rs); e = entry(rs)
            if e is None or e["decisionIndex"] != index:
                raise SystemExit(f"{g}: act-4 entry is not decision {index}")
            states = {r["index"]: r for r in rs if r.get("type") == "state"}
            if i == 0:
                result["entryRecord"] = states[e["stateIndex"]]["record"]
            result["games"].append({"salt": i, "file": g.rsplit("/", 1)[-1],
                                    "heartKilled": bool(o["heartKilled"]), "finalAct": o["finalAct"],
                                    "finalFloor": o["finalFloor"], "finalHp": o["finalHp"]})
        with open(path, "w") as f:
            json.dump(result, f)
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
