#!/usr/bin/env python3
"""Where would the mirror-trained prior F change map decisions in real A20 play, and what did the search say there?

usage: roots.py build OUT ROWDIR      -> OUT/{records,meta}.jsonl: map-screen policy rows (>= 2 paths) of runs searched
                                         with student_sel (az-<seed> files; az-b- = gen-1b B arm skipped)
       roots.py report OUT            -> reads OUT/{sel,f}.scores.jsonl (one_combat heart1score), writes OUT/report.json
       roots.py margins OUT RAW_TAR...-> at departures: both moves' root q (completed: unvisited -> rootMeanQ), visits and
                                         the move the search played (root selectedId), from the raw captures
                                         (gen 0 on-SEED, gen-1b A-SEED); writes OUT/margins.json

Rows are AZ-loop policy rows (data branch claude/az-gen2-data gen2/rows: gen 0 and gen-1b arm A, A20, production
OOC MCTS with student_sel as prior). "logits" = the search's improved policy pi' (Gumbel completed-Q target) over the
row's tokens; null = token without a target. pi' is built from the guiding prior (student_sel), so it is biased
toward student_sel's choice: agreement with it is the search's verdict, not ground truth.
"""
import glob, gzip, json, math, os, sys

def build(out, rowdir):
    os.makedirs(out, exist_ok=True); n = 0
    with open(os.path.join(out, "records.jsonl"), "w") as R, open(os.path.join(out, "meta.jsonl"), "w") as M:
        for f in sorted(glob.glob(os.path.join(rowdir, "az-*.gz"))):
            b = os.path.basename(f)
            if b.startswith("az-b-"): continue
            for line in gzip.open(f, "rt"):
                r = json.loads(line)
                rec = r["record"]
                if rec["screen_state"] != 5 or len(rec["paths_offered"]) < 2 or not r.get("logits"): continue
                if sum(x is not None for x in r["logits"]) < 2: continue
                R.write(json.dumps(rec) + "\n")
                M.write(json.dumps({"seed": r["seed"], "decision": r["decision"], "act": r.get("act"),
                                    "start": rec["obs.mapY"] < 0, "pi": r["logits"], "z": r.get("z")}) + "\n")
                n += 1
    print("map rows", n)

def am(v): return max(range(len(v)), key=lambda i: -1e18 if v[i] is None else v[i])

def softmax(v):
    m = max(v); e = [math.exp(x - m) for x in v]; s = sum(e); return [x / s for x in e]

def report(out):
    meta = [json.loads(l) for l in open(os.path.join(out, "meta.jsonl"))]
    sel = [json.loads(l)["logits"] for l in open(os.path.join(out, "sel.scores.jsonl"))]
    f = [json.loads(l)["logits"] for l in open(os.path.join(out, "f.scores.jsonl"))]
    assert len(meta) == len(sel) == len(f)
    g = {}
    def add(k, key, v): g.setdefault(k, {}).setdefault(key, 0); g[k][key] += v
    for m, a, b in zip(meta, sel, f):
        ts, tf, tp = am(a), am(b), am(m["pi"])
        groups = ["all", f"act{m['act']}", "start-of-act" if m["start"] else "mid-act"]
        for k in groups:
            add(k, "n", 1); add(k, "sel_eq_pi", ts == tp); add(k, "f_eq_pi", tf == tp)
            if ts != tf:
                add(k, "depart", 1); add(k, "depart_pi_sel", tp == ts); add(k, "depart_pi_f", tp == tf)
                add(k, "depart_pi_other", tp not in (ts, tf))
                ps, pf = softmax(a), softmax(b)
                add(k, "depart_sel_p_of_f_move", ps[tf]); add(k, "depart_f_p_of_sel_move", pf[ts])
    res = {}
    for k, d in g.items():
        n, dp = d["n"], d.get("depart", 0)
        res[k] = {"n": n, "sel_agrees_pi": d["sel_eq_pi"] / n, "f_agrees_pi": d["f_eq_pi"] / n, "departures": dp,
                  "departure_rate": dp / n}
        if dp:
            res[k].update({"at_departures_pi_picks_sel": d["depart_pi_sel"] / dp, "at_departures_pi_picks_f": d["depart_pi_f"] / dp,
                           "at_departures_pi_picks_other": d["depart_pi_other"] / dp,
                           "mean_sel_prob_of_f_move": d["depart_sel_p_of_f_move"] / dp,
                           "mean_f_prob_of_sel_move": d["depart_f_p_of_sel_move"] / dp})
    json.dump(res, open(os.path.join(out, "report.json"), "w"), indent=1)
    for k in sorted(res): print(k, json.dumps({x: round(y, 4) if isinstance(y, float) else y for x, y in res[k].items()}))

A_CAL, B_CAL = -1.6115816831588745, 0.5970583558082581   # gen-3 root_v calibration, as az_gen3_train_20261022/flip

def cal(q):
    q = min(max(q, 1e-4), 1 - 1e-4); return 1 / (1 + math.exp(-(A_CAL + B_CAL * math.log(q / (1 - q)))))

def margins(out, tars):
    import io, re, statistics as st, tarfile
    meta = [json.loads(l) for l in open(os.path.join(out, "meta.jsonl"))]
    sel = [json.loads(l)["logits"] for l in open(os.path.join(out, "sel.scores.jsonl"))]
    f = [json.loads(l)["logits"] for l in open(os.path.join(out, "f.scores.jsonl"))]
    key = lambda s: ("on" if s < 111142376 else "A", s)
    need = {key(m["seed"]) for i, m in enumerate(meta) if am(sel[i]) != am(f[i])}
    pat = re.compile(r"(?:^|/)(on|A)-(\d+)\.jsonl(?:\.gz)?$"); roots = {}
    for p in tars:
        with tarfile.open(p) as t:
            for mem in t:
                h = pat.search(mem.name)
                if not h or not mem.isfile() or (h.group(1), int(h.group(2))) not in need: continue
                raw = t.extractfile(mem).read()
                if mem.name.endswith(".gz"): raw = gzip.decompress(raw)
                roots[(h.group(1), int(h.group(2)))] = {d["decisionIndex"]: d for d in map(json.loads, io.StringIO(raw.decode()))
                                                       if d.get("type") == "decision"}
    rows, miss = [], 0
    for i, m in enumerate(meta):
        ts, tf = am(sel[i]), am(f[i])
        if ts == tf: continue
        d = roots.get(key(m["seed"]), {}).get(m["decision"])
        if not d or not d.get("root"): miss += 1; continue
        root = d["root"]; c = root["candidates"]
        tok2c = {t: ci for ci, x in enumerate(c) for t in (x.get("heart1Tokens") or [])}
        if ts not in tok2c or tf not in tok2c: miss += 1; continue
        cq = [x["q"] if x["visits"] > 0 else root["rootMeanQ"] for x in c]
        played = next(ci for ci, x in enumerate(c) if x["id"] == root["selectedId"])
        a, b = tok2c[tf], tok2c[ts]
        rows.append({"dq": cq[a] - cq[b], "dp": cal(cq[a]) - cal(cq[b]), "n_f": c[a]["visits"], "n_sel": c[b]["visits"],
                     "played": "f" if played == a else "sel" if played == b else "other", "start": m["start"], "act": m["act"],
                     "full": bool(root.get("fullBudget"))})
    res = {"departures_matched": len(rows), "unmatched": miss}
    for name, ys in (("all", rows), ("start-of-act", [r for r in rows if r["start"]]), ("mid-act", [r for r in rows if not r["start"]])):
        if not ys: continue
        pl = [y["played"] for y in ys]
        res[name] = {"n": len(ys), "played_f": pl.count("f"), "played_sel": pl.count("sel"), "played_other": pl.count("other"),
                     "mean_dq_f_minus_sel": st.mean(y["dq"] for y in ys), "f_q_higher": sum(y["dq"] > 0 for y in ys) / len(ys),
                     "mean_dp_f_minus_sel": st.mean(y["dp"] for y in ys), "median_abs_dq": st.median(abs(y["dq"]) for y in ys),
                     "median_visits_f": st.median(y["n_f"] for y in ys), "median_visits_sel": st.median(y["n_sel"] for y in ys)}
    # the less F's move was explored, the noisier (and more pessimistic) its q: stratify by its visits
    for lo, hi in ((0, 100), (100, 500), (500, 1000), (1000, 10**9)):
        ys = [y for y in rows if lo <= y["n_f"] < hi]
        if ys: res[f"f_visits_{lo}_{hi if hi < 10**9 else 'up'}"] = {
            "n": len(ys), "mean_dp_f_minus_sel": st.mean(y["dp"] for y in ys), "f_q_higher": sum(y["dq"] > 0 for y in ys) / len(ys),
            "played_f": sum(y["played"] == "f" for y in ys)}
    json.dump({"summary": res, "rows": rows}, open(os.path.join(out, "margins.json"), "w"), indent=1)
    print(json.dumps(res, indent=1))

if __name__ == "__main__":
    if sys.argv[1] == "build": build(sys.argv[2], sys.argv[3])
    elif sys.argv[1] == "margins": margins(sys.argv[2], sys.argv[3:])
    else: report(sys.argv[2])
