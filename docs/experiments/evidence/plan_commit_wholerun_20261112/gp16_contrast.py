"""Secondary (PREREG): each arm - E0's GP16 (§790), same seeds, same contrast code, not gated.
usage: python3 -I gp16_contrast.py UNITS GP16_UNITS CLAIMS OUT.json
(GP16_UNITS: greedy_playouts_g16_20261111's extracted GP16 unit dirs only)."""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyze as A
new, bad, ab, mm, pr, att = A.load(sys.argv[1], "new", sys.argv[3])
ref, bad_r, ab_r, mm_r, _, _ = A.load(sys.argv[2], "ref")
print("bad", len(bad), len(bad_r), "refgames", len(ref))
out = {}
for arm in ("PCH", "PCS"):
    r = A.contrast(new, ref, att, ("ref", "GP16"), ("new", arm), str(Path(sys.argv[4]).parent), "gp_"+arm, gated=False)
    out[arm] = r
    print(arm, "- GP16: n", r["n"], "drop", len(r["dropped"]), "heart %.2f -> %.2f d %+.2f [%+.2f, %+.2f] cpu %.2fx" % (
        100*r["heart_control"], 100*r["heart_arm"], 100*r["d"], 100*r["ci95"][0], 100*r["ci95"][1], r["cpu_ratio"]))
json.dump(out, open(sys.argv[4], "w"), indent=1)
