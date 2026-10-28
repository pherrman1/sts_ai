"""sr_heads.py ONE_COMBAT WORKDIR OUT.json NAME=weights.bin ... -- secondary #886 check: score the same paired
variants with heart1-format value heads (student_sel and the SR learning-curve heads), none of which the A20 search
reads.

The variants' public records are rebuilt from each captured leaf's record (extra.record): HP is
obs.fixed_observation[0] (min(curHp, 200)), an upgrade adds 1 to obs.deck.upgrades[deckIndex] (the record lists the
deck in game order, heart1_policy.cpp::encodeObservation). The rebuild is validated against the capture: scoring
the rebuilt records with the loaded student_sel must reproduce the heart1 value the capture computed on the edited
game state for every variant. Run with STS_REPO set (one_combat reads its models from the repo); SIB files are read
from WORKDIR/*.sib.jsonl[.gz]."""
import copy, glob, gzip, json, os, subprocess, sys
from collections import defaultdict
from pathlib import Path

EPS = 1e-9

def rows(paths):
    for p in paths:
        with (gzip.open(p, "rt") if p.endswith(".gz") else open(p)) as f:
            for line in f:
                try: yield json.loads(line)
                except json.JSONDecodeError: pass

def variant_record(base, v):
    rec = copy.deepcopy(base)   # flat keys, e.g. "obs.fixed_observation"
    if v["kind"] == "hp":
        rec["obs.fixed_observation"][0] = min(rec["obs.fixed_observation"][0] + v["delta"], 200)
    elif v["kind"] == "upgrade":
        rec["obs.deck.upgrades"][v["deckIndex"]] += 1
    return rec

def main(binary, work, out, nets):
    work = Path(work)
    meta, recs = [], []
    for r in rows(sorted(glob.glob(str(work / "*.sib.jsonl*")))):
        e = r.get("extra", {})
        if "mono" not in e or "record" not in e: continue
        for j, v in enumerate(e["mono"]["variants"]):
            recs.append(variant_record(e["record"], v))
            meta.append({"seed": r["seed"], "decision": r["decision"], "leaf": r["leaf"], "j": j, "kind": v["kind"],
                         "label": v.get("delta", v.get("card")), "captured": v.get("heart1"),
                         "sign": (1 if v.get("delta", 1) > 0 else -1)})
    with open(work / "mono_records.jsonl", "w") as f:
        for rec in recs: f.write(json.dumps(rec) + "\n")
    values = {}
    for spec in nets:
        name, weights = spec.split("=", 1)
        score = work / f"mono_records.{name}.score"
        subprocess.run([binary, "heart1score", weights, str(work / "mono_records.jsonl"), str(score)], check=True,
                       cwd=os.environ["STS_REPO"], stdout=subprocess.DEVNULL)
        values[name] = [float(json.loads(line)["value"]) for line in open(score)]
        assert len(values[name]) == len(recs)
    res = {"records": len(recs), "nets": {}}
    for name, vals in values.items():
        s = defaultdict(lambda: defaultdict(float))
        base = None
        maxdev = 0.0
        for m, x in zip(meta, vals):
            if m["captured"] is not None: maxdev = max(maxdev, abs(m["captured"] - x))
            if m["kind"] == "base": base = x; continue
            d = (x - base) * m["sign"]
            g = s[m["kind"]]
            g["n"] += 1
            if abs(d) <= EPS: g["tie"] += 1
            elif d < 0: g["wrong"] += 1; g["wrong_mag_sum"] += -d
            else: g["right"] += 1
        res["nets"][name] = {"maxAbsDeviationFromCapturedHeart1": maxdev, **{k: dict(v) for k, v in s.items()}}
    Path(out).write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")
    print(json.dumps(res, indent=1, sort_keys=True))

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:])
