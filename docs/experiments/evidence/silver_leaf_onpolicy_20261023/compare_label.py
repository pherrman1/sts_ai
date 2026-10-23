#!/usr/bin/env python3
"""The README's generator checks (check_label.sh writes DIR): A = production, B = the q_e2e head, C = head + label
search; X_base = a binary without the change, X_new = with it. Checks that A and B rows are byte-identical between the
binaries, that C plays exactly as B (only the label fields and the teacher id differ), and that wherever C's state is
still production's own (A's, same fight and decision), C's label rows equal A's rows. Also prints how often the
head's action is the label search's choice. usage: compare_label.py DIR"""
import hashlib
import json
import os
import sys

D = sys.argv[1]


def rows(tag):
    return [json.loads(line) for line in open(os.path.join(D, tag + ".jsonl"), "rb")]


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def best(edges):
    return max(range(len(edges)), key=lambda j: edges[j]["visits"])


ok = True
for mode in ("A", "B"):
    a, b = (os.path.join(D, f"{mode}_{x}.jsonl") for x in ("base", "new"))
    if not (os.path.exists(a) and os.path.exists(b)):
        print(mode, "missing"); ok = False; continue
    same = sha(a) == sha(b)
    ma, mb = (json.load(open(os.path.join(D, f"{mode}_{x}.manifest.json"))) for x in ("base", "new"))
    for m in (ma, mb):
        m.pop("producerExecutableSha256"); m["rows"].pop("path")
    print(f"{mode}: rows {'byte-identical' if same else 'DIFFER'} ({sha(a)[:12]}, {sum(1 for _ in open(a))} rows); "
          f"manifests {'identical' if ma == mb else 'DIFFER'} apart from the binary sha and the rows path")
    ok &= same and ma == mb

B, C = rows("B_new"), rows("C_new")
roots = 0
if len(B) != len(C):
    print("B and C row counts differ", len(B), len(C)); ok = False
for rb, rc in zip(B, C):
    kb, kc = set(rb), set(rc)
    extra = {"playEdges", "playInheritedVisits"} if rb.get("kind") == "root" else set()
    if kc != kb | extra:
        print("keys differ", kb ^ kc); ok = False; break
    if extra:
        roots += 1
        if rc["playEdges"] != rb["edges"] or rc["playInheritedVisits"] != rb["inheritedVisits"]:
            print("played edges differ", rb["seed"], rb["fight"], rb["decision"]); ok = False; break
    bad = [k for k in kb - {"edges", "inheritedVisits", "teacherId"} if rc[k] != rb[k]]
    if bad:
        print("row differs in", bad, rb.get("kind"), rb.get("seed"), rb.get("fight"), rb.get("decision")); ok = False
        break
mc = json.load(open(os.path.join(D, "C_new.manifest.json")))
print(f"C vs B: {len(C)} rows, {roots} roots; play identical apart from edges/inheritedVisits/teacherId: "
      f"{'yes' if ok else 'NO'}; C manifest labelSearch {mc.get('labelSearch')}; teacher {mc['teacherId']}")

# While a fight's states coincide with production's (A), the label search must equal production's search.
A = rows("A_new")
fa, fc = {}, {}
for R, F in ((A, fa), (C, fc)):
    for r in R:
        if r.get("kind") == "root":
            F.setdefault((r["seed"], r["fight"]), []).append(r)
same = diff = 0
for key in sorted(fc):
    for x, y in zip(fa.get(key, []), fc[key]):
        if x["wire"] != y["wire"]:
            break
        if x["edges"] == y["edges"] and x["inheritedVisits"] == y["inheritedVisits"]:
            same += 1
        else:
            diff += 1
            print("label differs from production at a shared state", key, x["decision"])
print(f"C label vs A at shared states: {same} equal, {diff} different")
ok &= diff == 0 and same > 0

# Descriptive: how often the head's played action differs from the label search's choice, and the Q gap.
n = agree = 0
gap = []
for r in C:
    if r.get("kind") != "root":
        continue
    lb, pb = best(r["edges"]), best(r["playEdges"])
    n += 1
    agree += r["edges"][lb]["bits"] == r["playEdges"][pb]["bits"]
    gap.append(r["playEdges"][pb]["q"] - r["edges"][lb]["q"])
if n:
    gap.sort()
    print(f"C: {n} roots; head's most visited edge = label's in {agree} ({100 * agree / n:.1f}%); "
          f"played Q - label Q: mean {sum(gap) / n:+.2f}, median {gap[n // 2]:+.2f}")
print("ALL OK" if ok else "FAILED")
