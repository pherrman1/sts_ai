"""Validation-fold (seed % 8 == 7) policy rows for the flip check: writes records.jsonl (the net inputs) and
meta.jsonl (source, seed, decision index, screen, act, pi' logits).
usage: build.py OUT student_sel|gen2 ROWDIR...
  student_sel: runs searched with student_sel (gen 0, gen-1b A, gen-2 A, gen-3 exploration; no az-b- files)
  gen2:        runs searched with the gen-2 prior (gen-2 A/B arm B: az-b- files with seed >= 111142888)"""
import glob, gzip, json, os, sys
out, which, srcs = sys.argv[1], sys.argv[2], sys.argv[3:]
assert which in ("student_sel", "gen2")
n = 0
with open(os.path.join(out, "records.jsonl"), "w") as R, open(os.path.join(out, "meta.jsonl"), "w") as M:
    for d in srcs:
        for f in sorted(glob.glob(d + "/az-*.gz")):
            b = os.path.basename(f); seed = int(b.split("-")[-1].split(".")[0])
            if seed % 8 != 7: continue
            if which == "student_sel":
                if b.startswith("az-b-"): continue
                src = "explore" if b.startswith("az-e-") else ("gen0" if seed < 111142376 else ("gen1b_A" if seed < 111142888 else "gen2_A"))
            else:
                if not (b.startswith("az-b-") and seed >= 111142888): continue
                src = "gen2_B"
            for l in gzip.open(f, "rt"):
                r = json.loads(l)
                if not r.get("logits"): continue
                R.write(json.dumps(r["record"]) + "\n")
                M.write(json.dumps({"src": src, "seed": seed, "decision": r["decision"], "screen": r.get("screen"),
                                    "act": r.get("act"), "logits": r["logits"]}) + "\n")
                n += 1
print("rows", n)
