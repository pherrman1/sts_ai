"""usage: cmp_modes.py TAG DIR... -- exact first fights: per config and encounter, every mode's paired regret change
against none, and the pairwise contrasts of the shortfall head (hblend:a20sf:0.5/1) with the capped and uncapped
plain head; the played outcome (end HP - 0.4 x turns) next to it. mean +- SE over fights."""
import glob, json, math, sys, collections
tag, dirs = sys.argv[1], sys.argv[2:]
rows = {}
for d in dirs:
    for f in glob.glob(f"{d}/{tag}_*.jsonl"):
        for l in open(f):
            r = json.loads(l)
            if r.get("summary") and "failure" not in r:
                rows[(r["config"], r.get("leafOracle", "none"), r["encounter"], r["seed"])] = r
def ms(v):
    if len(v) < 2: return "   n/a      "
    m = sum(v) / len(v); se = math.sqrt(sum((x - m) ** 2 for x in v) / (len(v) - 1) / len(v))
    return f"{m:+7.3f} ±{se:5.3f}"
SF, CAP, RAW = "hblend:a20sf:0.5/1", "hblend:a20:0.5/1+cap", "hblend:a20:0.5/1"
out = lambda r: r["endHp"] - 0.4 * r["turns"] if r["outcome"] == "win" else 0.0
for cfg in ("prod", "prod@mb=4"):
    print(f"\n{cfg}")
    for enc in ("CULTIST", "JAW_WORM", "TWO_LOUSE", "all"):
        f = collections.defaultdict(dict)
        for (c, m, e, s), r in rows.items():
            if c == cfg and (enc == "all" or e == enc):
                f[(e, s)][m] = r
        full = [v for v in f.values() if all(k in v for k in ("none", RAW, CAP, SF))]
        if not full: continue
        line = f"  {enc:9} n={len(full):3} none {sum(v['none']['regretSum'] for v in full)/len(full):6.3f} |"
        for m, lab in ((RAW, "/1"), (CAP, "cap"), (SF, "sf")):
            line += f" {lab} {ms([v[m]['regretSum'] - v['none']['regretSum'] for v in full])}"
        line += f" | sf-cap {ms([v[SF]['regretSum'] - v[CAP]['regretSum'] for v in full])}"
        line += f" sf-/1 {ms([v[SF]['regretSum'] - v[RAW]['regretSum'] for v in full])}"
        line += f" | outcome sf-none {ms([out(v[SF]) - out(v['none']) for v in full])}"
        line += f" lost {sum(1 for v in full for m in ('none', RAW, CAP, SF) if v[m]['outcome'] != 'win')}"
        print(line)
