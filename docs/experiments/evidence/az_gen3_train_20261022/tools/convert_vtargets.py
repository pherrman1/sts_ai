#!/usr/bin/env python3
"""AZ gen 2 value targets from the search: az_targets.convert_run rows plus
  "root_v": the decision's root value (rootMeanQ, the visit-weighted mean candidate q) on policy rows;
  "nstep_v": the root value of the run's 5th later searched decision (by stateIndex), else z — on every row.
usage: convert_vtargets.py AZ_TARGETS_DIR OUT --beta B SRC.tar ...   (writes OUT/az-SEED.capture.jsonl.gz)
Checks that the rows without the new fields equal az_targets.convert_run's (same order and content)."""
import argparse, gzip, json, os, sys
ap = argparse.ArgumentParser(); ap.add_argument("tools"); ap.add_argument("out"); ap.add_argument("--beta", type=float, required=True)
ap.add_argument("--n", type=int, default=5); ap.add_argument("src", nargs="+"); a = ap.parse_args()
sys.path.insert(0, a.tools); import az_targets as T
os.makedirs(a.out, exist_ok=True); stats = {"runs": 0, "policy_root_v": 0, "nstep_from_root": 0, "nstep_z": 0}
import io, re, tarfile
def arm_runs(paths):
    """(output name, seed, rows) for gen-0 on-SEED files and gen-1b/gen-2 A-SEED / B-SEED files (B -> az-b-SEED), gen-3 exploration E-SEED (-> az-e-SEED)."""
    pat = re.compile(r"(?:^|/)(on|A|B|E)-(\d+)\.jsonl(?:\.gz)?$")
    for p in paths:
        with tarfile.open(p) as t:
            for m in t:
                hit = pat.search(m.name)
                if not hit or not m.isfile(): continue
                raw = t.extractfile(m).read()
                if m.name.endswith(".gz"): raw = gzip.decompress(raw)
                arm, seed = hit.group(1), int(hit.group(2))
                yield ({"B": f"az-b-{seed}", "E": f"az-e-{seed}"}.get(arm, f"az-{seed}")), seed, [json.loads(l) for l in io.StringIO(raw.decode())]
for name, seed, rows in arm_runs(a.src):
    base, st = T.convert_run(seed, rows, a.beta)
    if not base: continue
    outcome = next(r for r in rows if r.get("type") == "outcome"); z = 1 if outcome.get("heartKilled") else 0
    dec = sorted([(d["stateIndex"], d["root"]["rootMeanQ"]) for d in rows if d.get("type") == "decision" and d.get("searched")
                  and d.get("root") and not d["root"].get("aborted") and d["root"].get("rootMeanQ") is not None], key=lambda x: x[0])
    by_state = {d["stateIndex"]: d for d in rows if d.get("type") == "decision"}
    def nstep(si):
        later = [v for s, v in dec if s > si]
        return later[a.n - 1] if len(later) >= a.n else float(z)
    # recover each base row's state index: policy rows carry "decision", value rows follow the state order
    pol_states = {d["decisionIndex"]: d["stateIndex"] for d in rows if d.get("type") == "decision"}
    with_policy = {pol_states[r["decision"]] for r in base if "logits" in r}
    states = [s["index"] for s in rows if s.get("type") == "state" and s.get("supported") and s["index"] not in with_policy]
    vi = iter(states); out = []
    for r in base:
        si = pol_states[r["decision"]] if "logits" in r else next(vi)
        r = dict(r)
        if "logits" in r:
            r["root_v"] = by_state[si]["root"]["rootMeanQ"]; stats["policy_root_v"] += r["root_v"] is not None
        r["nstep_v"] = nstep(si); stats["nstep_from_root" if any(s > si for s, _ in dec[a.n - 1:]) else "nstep_z"] += 1
        out.append(r)
    assert next(vi, None) is None
    with gzip.open(os.path.join(a.out, f"{name}.capture.jsonl.gz"), "wt") as f:
        for r in out: f.write(json.dumps(r) + "\n")
    stats["runs"] += 1
print(json.dumps(stats))
