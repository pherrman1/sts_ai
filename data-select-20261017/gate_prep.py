# held-out rows (seed % 8 == 7): records.jsonl for heart1score + labels.jsonl (set, kind, act, select_type, teacher argmax)
import gzip, json, sys, glob, re
old, new, out = sys.argv[1], sys.argv[2], sys.argv[3]
files = [("old", f) for f in sorted(glob.glob(old + "/cap-*.capture.jsonl.gz"))] + \
        [("new", f) for f in sorted(glob.glob(new + "/w0*/x/out/cap-a20-*.capture.jsonl.gz"))]
n = 0
with open(out + "/records.jsonl", "w") as R, open(out + "/labels.jsonl", "w") as L:
    for tag, f in files:
        if int(re.search(r"-(\d+)\.capture", f).group(1)) % 8 != 7: continue
        for line in gzip.open(f, "rt"):
            r = json.loads(line); t = r["logits"]
            if len(t) < 2: continue
            rec = r["record"]
            R.write(json.dumps(rec) + "\n")
            L.write(json.dumps({"set": tag, "kind": r.get("kind", "node"), "act": r.get("act", rec.get("obs.act", 0)),
                                "screen": r.get("screen", rec["screen_state"]), "sel": rec.get("select_screen_type", 0),
                                "t": max(range(len(t)), key=t.__getitem__), "n": len(t)}) + "\n"); n += 1
print(n)
