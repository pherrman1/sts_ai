# split the X4 snapshot dump into the arm inputs (stratum fixed: copy-0 entry HP / max HP < 0.5)
import json, os, struct, sys
X = sys.argv[1]
dump = f"{X}/dump"
strat = set()
for l in open(f"{dump}/index.jsonl"):
    r = json.loads(l)
    if r["copy"] == 0 and r["entry_hp"] / r["max_hp"] < 0.5:
        strat.add((r["seed"], r["floor"]))
os.makedirs(f"{X}/in128", exist_ok=True); os.makedirs(f"{X}/in1024", exist_ok=True)
f128, f1024, n128, n1024, nall = [], [], 0, 0, 0
for fn in sorted(os.listdir(dump)):
    if not fn.endswith(".states"):
        continue
    seed = int(fn[2:-7]); b = open(f"{dump}/{fn}", "rb").read(); at = 0
    k128, k1024 = bytearray(), bytearray()
    while at < len(b):
        fl, c, ln = struct.unpack_from("<III", b, at); rec = b[at:at + 12 + ln]; at += 12 + ln
        s = (seed, fl) in strat
        if c == 0: nall += 1
        if c <= 1 or s: k128 += rec; n128 += 1
        if s: k1024 += rec; n1024 += 1
    if k128: open(f"{X}/in128/{fn}", "wb").write(k128); f128.append(f"{X}/in128/{fn}")
    if k1024: open(f"{X}/in1024/{fn}", "wb").write(k1024); f1024.append(f"{X}/in1024/{fn}")
open(f"{X}/files128.txt", "w").write(",".join(f128)); open(f"{X}/files1024.txt", "w").write(",".join(f1024))
json.dump(dict(starts=nall, stratum_starts=len(strat), copies128=n128, copies1024=n1024), open(f"{X}/split.json", "w"))
print(nall, len(strat), n128, n1024)
