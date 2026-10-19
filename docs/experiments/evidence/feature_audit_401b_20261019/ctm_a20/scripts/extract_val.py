#!/usr/bin/env python3
"""#401b ctm_a20: stream the Stage 1 tars and keep only VALIDATION-split rows (split_for_seed,
'combat-transition-model-v1:{seed}', 80/10/10; TEST rows are never written). Mirrors the §470
extract rule for stalled reruns: a rerun seed takes its rows from rerun/ (rc 0), a seed whose rerun
failed is dropped; forced-slice units are kept with their scope name."""
import glob, hashlib, json, re, sys, tarfile, os
SRC, OUT = sys.argv[1], sys.argv[2]
def split_for_seed(seed):
    b = int.from_bytes(hashlib.sha256(f"combat-transition-model-v1:{seed}".encode()).digest()[:8], "big") % 100
    return "train" if b < 80 else "validation" if b < 90 else "test"
SEED = re.compile(rb'"sourceSeed":(\d+)')
cache = {}
def isval(s):
    v = cache.get(s)
    if v is None: v = cache[s] = split_for_seed(s) == "validation"
    return v
# rerun bookkeeping
rt = tarfile.open(os.path.join(SRC, "rerun-stalled.tar.gz"))
done_member = [m for m in rt.getmembers() if m.name.endswith("DONE.txt")]
done = {}
for m in done_member:
    for l in rt.extractfile(m).read().decode().splitlines():
        mm = re.match(r"unit=rerun-(\d+) .*?rc=(\d+)", l)
        if mm: done[int(mm.group(1))] = mm.group(2)
rerun_seeds = set(done); dropped = {s for s, rc in done.items() if rc != "0"}
sinks, counts, seen = {}, {}, set()
def sink(scope):
    if scope not in sinks: sinks[scope] = open(os.path.join(OUT, f"val-{scope}.jsonl"), "wb"); counts[scope] = 0
    return sinks[scope]
def take(f, name, scope, is_rerun):
    for line in f:
        if not line.strip(): continue
        s = int(SEED.search(line).group(1))
        if not isval(s): continue
        if s in dropped: continue
        if scope == "none" and not is_rerun and s in rerun_seeds: continue
        k = (s, int(re.search(rb'"fightIdx":(\d+)', line).group(1)), scope)
        if k in seen: sys.exit(f"duplicate {k} in {name}")
        seen.add(k)
        sink(scope).write(line if line.endswith(b"\n") else line + b"\n"); counts[scope] += 1
for m in rt.getmembers():
    if re.search(r"rerun-(\d+)\.jsonl$", m.name):
        s = int(re.search(r"rerun-(\d+)\.jsonl$", m.name).group(1))
        if done.get(s) == "0": take(rt.extractfile(m), m.name, "none", True)
for t in sorted(glob.glob(os.path.join(SRC, "w*.tar.gz"))):
    with tarfile.open(t) as tf:
        for m in tf:
            mm = re.search(r"/(main|lizard_fairy|lizard_brew|ritual_writhing|high_maxhp)-\d+\.jsonl$", m.name)
            if not mm: continue
            take(tf.extractfile(m), m.name, "none" if mm.group(1) == "main" else mm.group(1), False)
    print(t, counts, flush=True)
for f in sinks.values(): f.close()
print(json.dumps({"counts": counts, "rerunSeeds": len(rerun_seeds), "droppedSeeds": sorted(dropped)}))
