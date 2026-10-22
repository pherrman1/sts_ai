#!/usr/bin/env python3
"""AZ-loop training rows from `heartoutcomegen ... policy` captures (torch-free).

Turns a generation's worker tars (or unpacked on-SEED.jsonl[.gz] files) into distill.py rows:
- policy rows: searched, non-singleton, full-budget real roots. The target is the Gumbel improved policy
  (ADR-0043) pi' = softmax(log prior + sigma(completedQ)), q min-max normalised per root, completedQ = the
  action's Q where visited, else the root mean Q. sigma(q) = beta * q by default; --visit-scaled uses the
  paper's (c_visit + max visits) * beta * q. On gen 0 the visit-scaled fit fell about as 1/visits from the
  128- to the 2048-sim checkpoint while the constant beta stayed near 2.5-3, so the constant form is the default.
  pi' goes onto the record's choice tokens; a candidate behind several tokens splits its mass evenly.
  Tokens no candidate maps to get no target ("logits" entry null), so distill.py masks them out;
  candidates without a token (potion discard, gold) drop out and pi' is renormalised over the rest.
- value rows: every supported state of the run, "z" = 1 when the run killed the Heart, else 0.
  A policy row carries z too; its state gets no separate value row.
Rows record "wing_boots_counter" from the capture header (capture_provenance.py).

  convert --beta B OUT SRC...      one OUT/az-SEED.capture.jsonl.gz per run (distill.py reads the seed from it)
  fit-sigma SRC... [--fold 6] [--sims 2048]
                                   beta grid on full-budget roots of seeds with seed % 8 == fold: pi' from the
                                   --sims checkpoint scored on the action the 4096-sim search selected
SRC: worker tars (out/units/SEED/on-SEED.jsonl.gz inside) or on-SEED.jsonl[.gz] files."""
import argparse, gzip, io, json, math, os, re, sys, tarfile

C_VISIT = 50.0
GRID = [0.0] + [10 ** (e / 8) for e in range(-16, 17)]  # 0.01 .. 100
VISIT_GRID = [0.0] + [10 ** (e / 8) for e in range(-48, 1)]  # 1e-6 .. 1
TOKEN_KINDS = ("token", "skip_card", "bowl")


def runs(paths):
    """Yields (seed, rows) per on-arm run file."""
    pat = re.compile(r"(?:^|/)on-(\d+)\.jsonl(?:\.gz)?$")
    for p in paths:
        if p.endswith(".tar"):
            with tarfile.open(p) as t:
                for m in t:
                    hit = pat.search(m.name)
                    if not hit or not m.isfile(): continue
                    raw = t.extractfile(m).read()
                    if m.name.endswith(".gz"): raw = gzip.decompress(raw)
                    yield int(hit.group(1)), [json.loads(l) for l in io.StringIO(raw.decode())]
        else:
            hit = pat.search(p)
            if not hit: sys.exit(f"not an on-SEED.jsonl[.gz] file: {p}")
            with (gzip.open if p.endswith(".gz") else open)(p, "rt") as f:
                yield int(hit.group(1)), [json.loads(l) for l in f]


def improved_policy(priors, qs, visits, root_q, beta, visit_scaled=False, c_visit=C_VISIT):
    """pi' over candidates. priors need not be normalised; qs/visits per candidate (q ignored when unvisited)."""
    cq = [q if n > 0 else root_q for q, n in zip(qs, visits)]
    lo, hi = min(cq), max(cq)
    qn = [(q - lo) / (hi - lo) if hi > lo else 0.0 for q in cq]
    scale = (c_visit + max(visits)) * beta if visit_scaled else beta
    z = sum(priors)
    logits = [math.log(max(p / z, 1e-30)) + scale * q for p, q in zip(priors, qn)]
    m = max(logits)
    e = [math.exp(l - m) for l in logits]
    s = sum(e)
    return [x / s for x in e]


def policy_root(d):
    """The decision's root when it is a policy-target root: searched, non-singleton, full budget, not aborted."""
    root = d.get("root") or {}
    if d.get("type") != "decision" or not d.get("searched") or not root: return None
    if root.get("singleton") or root.get("aborted") or not root.get("fullBudget"): return None
    return root


def token_targets(root, pi, n_tokens):
    """pi' on choice tokens: (list with None for unmapped tokens, dropped mass) or (None, dropped) if < 2 tokens."""
    mass = [0.0] * n_tokens
    covered = [False] * n_tokens
    dropped = 0.0
    for c, p in zip(root["candidates"], pi):
        toks = c.get("heart1Tokens") or []
        if c.get("heart1Map") not in TOKEN_KINDS or not toks:
            dropped += p
            continue
        for t in toks:
            if not 0 <= t < n_tokens: raise ValueError(f"token {t} outside {n_tokens} choice tokens")
            mass[t] += p / len(toks); covered[t] = True
    kept = 1.0 - dropped
    if sum(covered) < 2 or kept <= 0: return None, dropped
    return [math.log(max(m / kept, 1e-30)) if c else None for m, c in zip(mass, covered)], dropped


def header_wing_boots(rows):
    h = next((r for r in rows if r.get("type") == "header"), None)
    if h is None: raise ValueError("capture has no header row")
    v = (h.get("provenance") or {}).get("heart1WingBootsCounter")
    if v not in (0, 1): raise ValueError(f"header heart1WingBootsCounter must be 0 or 1, got {v!r}")
    return v


def convert_run(seed, rows, beta, visit_scaled=False):
    """distill.py rows for one run, plus counters."""
    out, stats = [], {"policy": 0, "value": 0, "dropped_mass": 0.0, "short": 0}
    outcome = next((r for r in rows if r.get("type") == "outcome"), None)
    if outcome is None or not outcome.get("complete") or not outcome.get("integrityPassed"):
        stats["skipped_run"] = 1
        return out, stats
    z = 1 if outcome.get("heartKilled") else 0
    wb = header_wing_boots(rows)
    with_policy = set()
    for d in rows:
        root = policy_root(d)
        if root is None: continue
        c = root["candidates"]
        pi = improved_policy([x["prior"] for x in c], [x["q"] for x in c], [x["visits"] for x in c],
                             root["rootMeanQ"], beta, visit_scaled)
        logits, dropped = token_targets(root, pi, d["heart1Tokens"])
        stats["dropped_mass"] += dropped
        if logits is None:
            stats["short"] += 1
            continue
        rec = d["heart1Record"]
        out.append({"record": rec, "logits": logits, "z": z, "act": d.get("act", 0), "screen": rec["screen_state"],
                    "wing_boots_counter": wb, "seed": seed, "decision": d["decisionIndex"]})
        with_policy.add(d["stateIndex"])
        stats["policy"] += 1
    for s in rows:
        if s.get("type") != "state" or not s.get("supported") or s["index"] in with_policy: continue
        out.append({"record": s["record"], "z": z, "act": s.get("act", 0), "screen": s.get("screen"),
                    "wing_boots_counter": wb, "seed": seed})
        stats["value"] += 1
    return out, stats


def checkpoint_policy(root, sims, beta, visit_scaled=False):
    """pi' from the root's `sims` checkpoint (priors from the candidates); None when the root has no such checkpoint."""
    cp = next((c for c in root.get("checkpoints", []) if c["simulations"] == sims), None)
    if cp is None: return None
    by = {a["id"]: a for a in cp["actions"]}
    c = root["candidates"]
    qs = [by.get(x["id"], {}).get("q", 0.0) for x in c]
    ns = [by.get(x["id"], {}).get("visits", 0) for x in c]
    tot = sum(ns)
    root_q = sum(q * n for q, n in zip(qs, ns)) / tot if tot else 0.0
    return improved_policy([x["prior"] for x in c], qs, ns, root_q, beta, visit_scaled)


def fit_sigma(paths, fold, sims=2048, visit_scaled=False):
    roots = []
    for seed, rows in runs(paths):
        if seed % 8 != fold: continue
        for d in rows:
            root = policy_root(d)
            if root is not None: roots.append(root)
    res = []
    for cs in (VISIT_GRID if visit_scaled else GRID):
        nll = top = n = 0
        for root in roots:
            pi = checkpoint_policy(root, sims, cs, visit_scaled)
            if pi is None: continue
            ids = [x["id"] for x in root["candidates"]]
            k = ids.index(root.get("searchSelectedId", root["selectedId"]))   # the search's pick, not a sampled play
            nll -= math.log(max(pi[k], 1e-30)); top += max(range(len(pi)), key=pi.__getitem__) == k; n += 1
        res.append({"beta": cs, "roots": n, "nll": nll / n if n else None, "top1": top / n if n else None})
    best = min((r for r in res if r["nll"] is not None), key=lambda r: r["nll"])
    return {"fold": fold, "checkpoint_sims": sims, "visit_scaled": visit_scaled, "c_visit": C_VISIT,
            "best": best, "grid": res}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("convert"); c.add_argument("--beta", type=float, required=True)
    c.add_argument("out"); c.add_argument("src", nargs="+")
    f = sub.add_parser("fit-sigma"); f.add_argument("src", nargs="+"); f.add_argument("--fold", type=int, default=6)
    f.add_argument("--sims", type=int, default=2048)
    for q in (c, f): q.add_argument("--visit-scaled", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "fit-sigma":
        print(json.dumps(fit_sigma(a.src, a.fold, a.sims, a.visit_scaled), indent=1))
        return
    os.makedirs(a.out, exist_ok=True)
    tot = {}
    for seed, rows in runs(a.src):
        out, stats = convert_run(seed, rows, a.beta, a.visit_scaled)
        for k, v in stats.items(): tot[k] = tot.get(k, 0) + v
        tot["runs"] = tot.get("runs", 0) + 1
        if not out: continue
        # mtime 0 and no file name in the gzip header: the same inputs give byte-identical files
        with open(os.path.join(a.out, f"az-{seed}.capture.jsonl.gz"), "wb") as raw, \
                gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as g:
            for r in out: g.write((json.dumps(r, separators=(",", ":")) + "\n").encode())
    tot["beta"] = a.beta; tot["visit_scaled"] = a.visit_scaled; tot["c_visit"] = C_VISIT
    json.dump(tot, open(os.path.join(a.out, "convert.json"), "w"), indent=1)
    print(json.dumps(tot))


if __name__ == "__main__":
    main()
