#!/usr/bin/env python3
"""Extract per-fight potion/outcome rows from CTM corpus tarballs (main-* units only)."""
import io, json, sys, tarfile, gzip, csv

out_path, prefix = sys.argv[1], sys.argv[2]
tars = sys.argv[3:]
seen = set()
n_rows = n_skip = 0
with gzip.open(out_path, "wt", newline="") as fo:
    w = csv.writer(fo)
    w.writerow(["seed", "fight", "asc", "act", "floor", "room", "enc", "cap", "preHp", "preMax", "postHp", "postMax",
                "outcome", "deck", "relics", "gold", "prePot", "postPot"])
    for t in tars:
        with tarfile.open(t, "r:gz") as tf:
            for m in tf:
                name = m.name.rsplit("/", 1)[-1]
                if not (m.isfile() and name.startswith(prefix) and name.endswith(".jsonl")):
                    continue
                for line in tf.extractfile(m):
                    r = json.loads(line)
                    key = (r["sourceSeed"], r["fightIdx"])
                    if key in seen or not r.get("runValid", True) or r.get("quarantineReason"):
                        n_skip += 1
                        continue
                    seen.add(key)
                    g = r["predictorInput"]["globals"]
                    tr = r["transition"]
                    pre, post = tr["pre"], tr["post"]
                    cap = pre["potionCapacity"]
                    w.writerow([r["sourceSeed"], r["fightIdx"], g["ascension"], r["act"], r["floor"], g["roomClass"],
                                r["encounter"], cap, pre["curHp"], pre["maxHp"], post["curHp"], post["maxHp"],
                                tr["combatOutcome"], len(pre["deck"]), len(pre["relics"]), pre["gold"],
                                " ".join(map(str, pre["potions"][:cap])), " ".join(map(str, post["potions"][:cap]))])
                    n_rows += 1
print("rows", n_rows, "skipped", n_skip)
