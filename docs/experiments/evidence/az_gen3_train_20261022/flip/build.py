"""Held-out (seed % 8 == 7) policy rows from runs searched with the student_sel prior (no az-b- files):
writes records.jsonl (the net inputs) and meta.jsonl (source, seed, screen, act, pi' logits)."""
import glob, gzip, json, os, sys
out = sys.argv[1]; srcs = sys.argv[2:]
SCREENS = None
n = 0
with open(os.path.join(out, "records.jsonl"), "w") as R, open(os.path.join(out, "meta.jsonl"), "w") as M:
    for d in srcs:
        for f in sorted(glob.glob(d + "/az-*.gz")):
            b = os.path.basename(f)
            if b.startswith("az-b-"): continue
            seed = int(b.split("-")[-1].split(".")[0])
            if seed % 8 != 7: continue
            src = "explore" if b.startswith("az-e-") else ("gen0" if seed < 111142376 else ("gen1b_A" if seed < 111142888 else "gen2_A"))
            for l in gzip.open(f, "rt"):
                r = json.loads(l)
                if not r.get("logits"): continue
                R.write(json.dumps(r["record"]) + "\n")
                M.write(json.dumps({"src": src, "seed": seed, "screen": r.get("screen"), "act": r.get("act"), "logits": r["logits"]}) + "\n")
                n += 1
print("rows", n)
