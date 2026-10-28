#!/usr/bin/env python3
"""Phase-2 gate, root selection and fork units (PREREG.md, frozen rules).

Input: phase-1 probe rows (probe-SEED-INDEX.probe.jsonl.gz, found recursively under the given dirs, tars allowed).
Gate: x_i = mean over grid seeds of Q(i) - Q(a_ref) for leaf sr, h = 3, at the final budget; projected
SE(beta_SR) = 0.45 * sqrt(DEFF / (M * sum over selected (root, i != ref) of (x_i - mean x)^2)), DEFF = 3, M = 4.
Selection: the 64 roots with the largest max_i |x_i|, plus 32 of the rest by splitmix64(seed ^ index ^ 0x504832) order.
Units: one per (root, salt 1..4, distinct candidate effect), key = the first candidate key with that effect.
Usage: python3 -I make_fork_units.py OUT_PREFIX DIR_OR_TAR...   -> OUT_PREFIX.units.txt, OUT_PREFIX.selection.json
"""
import gzip, io, json, math, sys, tarfile
from pathlib import Path

MASK = (1 << 64) - 1
SD, DEFF, M, TOP, RANDOM, GATE = 0.45, 3.0, 4, 64, 32, 0.35


def splitmix64(x):
    x = (x + 0x9E3779B97F4A7C15) & MASK
    z = ((x ^ (x >> 30)) * 0xBF58476D1CE4E5B9) & MASK
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK
    return z ^ (z >> 31)


def probe_rows(paths):
    for p in map(Path, paths):
        files = [p] if p.is_file() else sorted(p.rglob("*"))
        for f in files:
            if f.name.endswith(".probe.jsonl.gz"):
                yield from (json.loads(l) for l in gzip.open(f, "rt") if l.strip())
            elif f.suffix == ".tar":
                with tarfile.open(f) as t:
                    for m in t.getmembers():
                        if m.name.endswith(".probe.jsonl.gz"):
                            data = gzip.decompress(t.extractfile(m).read()).decode()
                            yield from (json.loads(l) for l in data.splitlines() if l.strip())


def root_summary(row):
    cands = row["candidates"]
    ref_keys = row["production"].get("keys") or []
    if not ref_keys:
        raise SystemExit(f"{row['seed']}/{row['decisionIndex']}: production choice matches no candidate")
    key_of = {c["id"]: c["key"] for c in cands}
    ref = ref_keys[0]
    runs = [g for g in row["grid"] if g.get("leaf") == "sr" and g.get("horizon") == 3 and "error" not in g]
    if not runs:
        raise SystemExit(f"{row['seed']}/{row['decisionIndex']}: no sr:3 grid run")
    q = {}
    for g in runs:
        for a in g["actions"]:
            if a["visits"] and not a["pruned"]:
                q.setdefault(key_of[a["id"]], []).append(a["q"])
    mean = {k: sum(v) / len(v) for k, v in q.items()}
    x = {k: mean[k] - mean[ref] for k in mean if k != ref}
    effects, keys = set(), []
    for c in cands:
        e = c.get("effect", c["key"])
        if e not in effects:
            effects.add(e)
            keys.append(c["key"])
    return {"seed": row["seed"], "index": row["decisionIndex"], "ref": ref, "x": x, "keys": keys}


def main():
    prefix, paths = sys.argv[1], sys.argv[2:]
    roots = sorted((root_summary(r) for r in probe_rows(paths)), key=lambda r: (r["seed"], r["index"]))
    if len({(r["seed"], r["index"]) for r in roots}) != len(roots):
        raise SystemExit("duplicate probe rows")
    spread = lambda r: max((abs(v) for v in r["x"].values()), default=0.0)
    by_spread = sorted(roots, key=lambda r: (-spread(r), r["seed"]))
    top = by_spread[:TOP]
    rest = sorted(by_spread[TOP:], key=lambda r: splitmix64(r["seed"] ^ r["index"] ^ 0x504832))
    chosen = top + rest[:RANDOM]
    xs = [v for r in chosen for v in r["x"].values()]
    mx = sum(xs) / len(xs)
    sxx = sum((v - mx) ** 2 for v in xs)
    se = SD * math.sqrt(DEFF / (M * sxx)) if sxx > 0 else math.inf
    n_pool = len(roots)
    for r in chosen:
        r["stratum"] = "top" if r in top else "random"
        r["inclusion"] = 1.0 if r in top else RANDOM / max(1, n_pool - TOP)
    out = {"roots_in_pool": n_pool, "selected": len(chosen), "projected_se_beta_sr": se, "gate": GATE,
           "gate_pass": se <= GATE, "roots": chosen}
    Path(prefix + ".selection.json").write_text(json.dumps(out, indent=1))
    if se <= GATE:
        with open(prefix + ".units.txt", "w") as f:
            for r in chosen:
                for salt in range(1, M + 1):
                    for k in r["keys"]:
                        f.write(f"fork {r['seed']} {r['index']} {salt} {k}\n")
    print(json.dumps({k: out[k] for k in ("roots_in_pool", "selected", "projected_se_beta_sr", "gate_pass")}))


if __name__ == "__main__":
    main()
