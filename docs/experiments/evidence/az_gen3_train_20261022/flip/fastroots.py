#!/usr/bin/env python3
"""Decision flips at searched roots without a policy row (fast roots: learned stop / 1024 cap; review of #814).
build: fastroots.py build OUT RAW_TAR...   -> OUT/records.jsonl (heart1Record) + OUT/meta.jsonl (root summary) for
       validation-fold (seed % 8 == 7) runs, every searched, non-singleton, non-aborted root that is not full-budget.
report: fastroots.py report OUT            -> after `one_combat heart1score BIN OUT/records.jsonl OUT/out_{sel,g2,g3}.jsonl`
dp uses the gen-3 root_v calibration (as margins.py)."""
import gzip, io, json, math, os, re, sys, tarfile, statistics as st
A, B = -1.6115816831588745, 0.5970583558082581
KINDS = ("token", "skip_card", "bowl")
pat = re.compile(r"(?:^|/)(on|A|B|E)-(\d+)\.jsonl(?:\.gz)?$")
mode, out = sys.argv[1], sys.argv[2]
if mode == "build":
    n = 0
    with open(out + "/records.jsonl", "w") as R, open(out + "/meta.jsonl", "w") as M:
        for p in sys.argv[3:]:
            with tarfile.open(p) as t:
                for mem in t:
                    h = pat.search(mem.name)
                    if not h or not mem.isfile() or int(h.group(2)) % 8 != 7: continue
                    raw = t.extractfile(mem).read()
                    if mem.name.endswith(".gz"): raw = gzip.decompress(raw)
                    for d in map(json.loads, io.StringIO(raw.decode())):
                        r = d.get("root") or {}
                        if d.get("type") != "decision" or not d.get("searched") or not r or r.get("singleton") \
                           or r.get("aborted") or r.get("fullBudget") or not d.get("heart1Record"): continue
                        c = [{"q": x["q"], "n": x["visits"], "tok": x.get("heart1Tokens") or [], "map": x.get("heart1Map"),
                              "id": x["id"]} for x in r["candidates"]]
                        R.write(json.dumps(d["heart1Record"]) + "\n")
                        M.write(json.dumps({"arm": h.group(1), "seed": int(h.group(2)), "decision": d["decisionIndex"],
                                            "rootMeanQ": r["rootMeanQ"], "sims": r.get("completedSimulations"),
                                            "selectedId": r["selectedId"], "c": c}) + "\n")
                        n += 1
    print("fast roots", n)
    sys.exit(0)
cal = lambda q: 1 / (1 + math.exp(-(A + B * math.log(min(max(q, 1e-4), 1 - 1e-4) / (1 - min(max(q, 1e-4), 1 - 1e-4))))))
meta = [json.loads(l) for l in open(out + "/meta.jsonl")]
outs = {k: [json.loads(l)["logits"] for l in open(f"{out}/out_{k}.jsonl")] for k in ("sel", "g2", "g3")}
GROUPS = {"searched with student_sel (gen 0, gen-1b A, gen-2 A, exploration)": lambda m: m["arm"] in ("on", "A", "E"),
          "searched with the gen-2 prior (gen-2 B)": lambda m: m["arm"] == "B" and m["seed"] >= 111142888}
for gname, keep in GROUPS.items():
    res = {"g3": [], "g2": []}; usable = 0; sims = []
    for i, m in enumerate(meta):
        if not keep(m): continue
        tok2c = {t: ci for ci, x in enumerate(m["c"]) if x["map"] in KINDS for t in x["tok"]}
        if len(set(tok2c.values())) < 2: continue
        usable += 1; sims.append(m["sims"] or 0)
        cq = [x["q"] if x["n"] > 0 else m["rootMeanQ"] for x in m["c"]]
        played = next(ci for ci, x in enumerate(m["c"]) if x["id"] == m["selectedId"])
        ch = {k: tok2c[max(tok2c, key=lambda t: outs[k][i][t])] for k in outs}
        for net in ("g3", "g2"):
            if ch[net] == ch["sel"]: continue
            a, b = ch[net], ch["sel"]
            res[net].append({"dq": cq[a] - cq[b], "dp": cal(cq[a]) - cal(cq[b]), "n_new": m["c"][a]["n"], "n_sel": m["c"][b]["n"],
                             "played": "new" if played == a else "sel" if played == b else "other", "arm": m["arm"]})
    runs = len({(m["arm"], m["seed"]) for m in meta if keep(m)})
    print(f"{gname}: {runs} runs, fast roots with >= 2 mapped candidates {usable} ({usable/runs:.1f} per run, median completed sims {st.median(sims):.0f})")
    for net, lab in (("g3", "gen 3"), ("g2", "gen 2")):
        xs = res[net]; g = [abs(x["dq"]) for x in xs]; pl = [x["played"] for x in xs]
        chg = [x for x in xs if x["played"] == "sel"]
        print(f"  {lab} vs student_sel: {len(xs)} flips ({len(xs)/usable:.2%}) | |dq| median {st.median(g):.4f} | mean dq new-minus-sel "
              f"{st.mean(x['dq'] for x in xs):+.4f} (new higher at {sum(x['dq'] > 0 for x in xs)/len(xs):.0%}) | mean dp {st.mean(x['dp'] for x in xs):+.4f} "
              f"| search played new {pl.count('new')}, sel {pl.count('sel')}, other {pl.count('other')} | mean dp where it played sel "
              f"{st.mean(x['dp'] for x in chg):+.4f} | median visits new {st.median(x['n_new'] for x in xs):.0f}, sel {st.median(x['n_sel'] for x in xs):.0f}")
