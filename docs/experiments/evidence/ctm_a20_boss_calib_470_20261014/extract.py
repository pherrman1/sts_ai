#!/usr/bin/env python3
"""§470: Stage 1 main-corpus rows of one hash split (main-*.jsonl + rerun-*.jsonl), duplicate keys refused."""
import glob, hashlib, json, re, sys
split, out = sys.argv[1], sys.argv[2]
def split_for_seed(seed):
    b = int.from_bytes(hashlib.sha256(f"combat-transition-model-v1:{seed}".encode()).digest()[:8], "big") % 100
    return "train" if b < 80 else "validation" if b < 90 else "test"
SEED = re.compile(rb'"sourceSeed":(\d+)'); FIGHT = re.compile(rb'"fightIdx":(\d+)')
# Stalled units were rerun one seed per unit (rerun-stalled/rerun/): a rerun seed takes its rows from the rerun
# (identical to the main rows where both exist); a seed whose rerun failed (rc != 0) is dropped entirely.
R = "/root/calib470/stage1/rerun-stalled/rerun/"
done = dict(re.match(r"unit=rerun-(\d+) .*?rc=(\d+)", l).groups() for l in open(R + "DONE.txt") if l.strip())
rerun_seeds = {int(s) for s in done}
dropped = {int(s) for s, rc in done.items() if rc != "0"}
files = sorted(R + f"rerun-{s}.jsonl" for s, rc in done.items() if rc == "0") + sorted(glob.glob("/root/calib470/stage1/w*/out/main-*.jsonl"))
keys, n, seeds = set(), 0, set()
with open(out, "wb") as sink:
    for f in files:
        for line in open(f, "rb"):
            if not line.strip(): continue
            s = int(SEED.search(line).group(1))
            if split_for_seed(s) != split or s in dropped or ("/main-" in f and s in rerun_seeds): continue
            k = (s, int(FIGHT.search(line).group(1)))
            if k in keys: sys.exit(f"duplicate key {k} in {f}")
            keys.add(k); seeds.add(s); n += 1
            sink.write(line if line.endswith(b"\n") else line + b"\n")
print(json.dumps({"split": split, "files": len(files), "rows": n, "seeds": len(seeds), "dropped_seeds": sorted(dropped)}))
