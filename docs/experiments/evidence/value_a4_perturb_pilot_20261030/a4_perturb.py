#!/usr/bin/env python3
"""Act-4 entry perturbations of one heartoutcomegen game (value_a4_perturb_pilot campaign).

  a4_perturb.py OUT.json SEED INDEX K PARENT.jsonl

Checks the parent's a4_perturb row (K children, all exit 0, fork at INDEX in act 4, SALT 0, SPECSEED = SEED) and
that every child replays the parent's states and decisions up to INDEX, then writes per child: the perturbation
(header a4Perturb), the Act-4 entry record after it (heart1-public-record-v2) and the outcome.
"""
import gzip, json, os, sys


def rows(path):
    with (gzip.open if path.endswith(".gz") else open)(path, "rt") as f:
        return [json.loads(line) for line in f if line.strip()]


def outcome(rs):
    out = [r for r in rs if r.get("type") == "outcome"]
    if len(out) != 1 or not out[0].get("complete") or not out[0].get("integrityPassed"):
        raise SystemExit("incomplete or failed game")
    return out[0]


def entry(rs):
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
    if len(argv) != 6:
        raise SystemExit(__doc__)
    path, seed, index, k, parent = argv[1], int(argv[2]), int(argv[3]), int(argv[4]), argv[5]
    prs = rows(parent)
    summ = [r for r in prs if r.get("type") == "a4_perturb"]
    if len(summ) != 1:
        raise SystemExit("parent has no single a4_perturb row")
    s = summ[0]
    if not (s.get("ok") and s["act"] == 4 and s["decisionIndex"] == index and s["children"] == k
            and s["salt"] == 0 and s["specSeed"] == seed and s["seed"] == seed and len(s["results"]) == k):
        raise SystemExit("a4_perturb row does not match the frozen unit")
    if any(c["exitStatus"] != 0 for c in s["results"]):
        raise SystemExit("a child failed")
    base = prefix(prs, index)
    result = {"schema": "a4-perturb-pilot-v1", "seed": seed, "entryDecisionIndex": index, "children": []}
    d = os.path.dirname(parent)
    for c in s["results"]:
        g = os.path.join(d, c["file"])
        rs = rows(g)
        hdr = rs[0]
        o = outcome(rs)
        e = entry(rs)
        if e is None or e["decisionIndex"] != index:
            raise SystemExit(f"{g}: act-4 entry is not decision {index}")
        if hdr.get("a4Perturb", {}).get("child") != c["child"]:
            raise SystemExit(f"{g}: header a4Perturb does not name child {c['child']}")
        if prefix(rs, index)[:len(base) - 1] != base[:-1]:
            # the parent stops at the fork and never records the entry state; its last prefix row differs from
            # the child's row at that position (#917 smoke), so compare every row before it
            raise SystemExit(f"{g}: prefix differs from the parent")
        states = {r["index"]: r for r in rs if r.get("type") == "state"}
        result["children"].append({
            "child": c["child"], "op": c["op"], "perturb": hdr["a4Perturb"], "wallSeconds": c["wallSeconds"],
            "file": c["file"], "entryRecord": states[e["stateIndex"]]["record"],
            "heartKilled": bool(o["heartKilled"]), "finalAct": o["finalAct"], "finalFloor": o["finalFloor"],
            "finalHp": o["finalHp"]})
    with open(path, "w") as f:
        json.dump(result, f)


if __name__ == "__main__":
    main(sys.argv)
