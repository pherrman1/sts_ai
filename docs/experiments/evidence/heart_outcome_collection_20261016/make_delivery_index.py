#!/usr/bin/env python3
"""Build the immutable §497 cloud delivery index from the share (hashes and source accounting only).

Reads receipts and hashes archive bytes; never opens or unpacks any archive.
Usage: python3 -I make_delivery_index.py SHARE_ROOT OUT_JSON
"""
import hashlib
import json
import pathlib
import sys

PLAN = "4b49a40427dde2470044847e8e843cc349a460e183d6fa2ddbdda4c0494d14a3"
ACT = "9f66ee277e52874b8c74dcd11561027f827029b336da28f81c534e3c5a041b22"
BUNDLE = "836a34129c99bfd68e691ed802f0a403cd75e37db7effd0e1b01f51b4697f6d5"
V1, V2, V3 = ("3c033a2009dd6cfa920905c4a137450a853266b5", "98cc07bbdf5e0fefad655ae044237426cd13054a",
              "33c3c1107a9419a9ebc1a783411b166fde5340aa")
RERUN = "35d0b6a565582ee67018e28409290b0e0fcf3f75"
LOST = (7, 8, 27, 34)
ARCH = ("train.tar.gz", "validation.tar.gz", "SEALED-test.tar.gz")


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def run_commit(w):
    return V1 if w == 1 else V2 if w in (0, 3, 9, 14, 15, 17) else V3


def main(root, out):
    root = pathlib.Path(root)
    camp = root / "campaign"
    assert sha(camp / "plan.json") == PLAN and sha(camp / "activation.json") == ACT
    assert sha(camp / "bundle-manifest" / "bundle.json") == BUNDLE
    plan = json.loads((camp / "plan.json").read_text())
    split = {s["seed"]: s["split"] for s in plan["sources"]}
    owner = {}
    for s in plan["sources"]:
        owner.setdefault(s["worker"], []).append(s["seed"])
    covered, rows, problems = {}, [], []

    def take(folder, w, h, commit):
        d = root / "deliveries" / folder
        rec = json.loads((d / "worker-receipt.json").read_text())
        exp = owner[w] if h is None else owner[w][h::2]
        ok = (rec["worker"] == w and rec["planSha256"] == PLAN and rec["activationSha256"] == ACT
              and rec["sources"] == exp and len(rec["returncodes"]) == len(exp))
        archives = {}
        for a in ARCH:
            got = sha(d / a)
            ok &= got == rec["archives"][a]
            archives[a] = {"sha256": got, "bytes": (d / a).stat().st_size}
        if not ok:
            problems.append(folder)
        for s in exp:
            assert s not in covered, s
            covered[s] = folder
        n = {k: sum(split[s] == k for s in exp) for k in ("train", "validation", "test")}
        rows.append({"folder": folder, "worker": w, "half": h, "runCommit": commit,
                     "receiptSha256": sha(d / "worker-receipt.json"),
                     "workerStartedSha256": sha(d / "worker-started.json"),
                     "complete": rec["complete"], "sources": len(exp), "splitCounts": n,
                     "nonzeroReturncodes": sum(r != 0 for r in rec["returncodes"]),
                     "archives": archives, "verified": ok})

    for w in range(45):
        if w in LOST:
            for h in (0, 1):
                take(f"r{w:02d}-{h}", w, h, RERUN)
        else:
            take(f"w{w:02d}", w, None, run_commit(w))
    superseded = []
    for w in LOST:
        d = root / "deliveries" / f"w{w:02d}"
        assert not (d / "worker-receipt.json").exists()
        p = d / "SEALED-partial-out.tar.gz"
        cause = ("died during the account usage-limit interruption 18:44-19:13Z (last progress 18:49:33Z)" if w == 27
                 else "died in the container-restart wave 19:24-19:27Z")
        superseded.append({"folder": f"w{w:02d}", "runCommit": run_commit(w), "status": cause + ", censored",
                           "partialArchive": {"sha256": sha(p), "bytes": p.stat().st_size},
                           "use": "superseded raw evidence; never unpacked; all 40 sources taken from reruns"})
    assert len(covered) == 1800 and set(covered) == set(split), "source accounting"
    idx = {"schema": "heart-outcome-cloud-delivery-index-v1", "ledger": "§497", "pr": 572,
           "planSha256": PLAN, "activationSha256": ACT, "bundleSha256": BUNDLE,
           "cohortStartedSha256": sha(camp / "COHORT-STARTED.json"),
           "environmentSha256": sha(camp / "bundle-manifest" / "environment.json"),
           "frozenTxtSha256": sha(root / "FROZEN.txt"),
           "sourceAccounting": {"sources": 1800, "originalWorkers": 41, "rerunHalves": 8,
                                "byFolder": len(rows), "allVerified": not problems, "problems": problems},
                           "deliveries": rows, "superseded": superseded,
           "deviations": [
               "Export check was one-way (reviewer read of a 288 MiB share blob), chosen by Philipp 2026-10-16 17:42Z.",
               "Three RUN_COMMITs of the cloud wrapper (v1 W=1, v2 W=0,3,9,14,15,17, v3 others); same producer, plan, bundle.",
               "W=27 died during the account usage-limit interruption (18:44-19:13Z); W=7,8,34 died in the "
               "container-restart wave (19:24-19:27Z).",
               "Philipp chose card option 'Redistribute all' (20:18Z: stop running workers, redistribute over 45 new "
               "workers), not the recommended 'Rerun lost 160'. Only the lost 160 sources were rerun, as 8 half-workers "
               "at RUN_COMMIT 35d0b6a5 with unchanged worker code restricted to own[h::2]; stopping the running "
               "workers got no answer from Philipp and, on the lead's judgment, was not carried out.",
               "W=11 ran on a 2.80GHz Xeon, others 2.10GHz; decisions use fixed simulation counts on the same binary.",
           ],
           "testCustody": "No SEALED-test or partial archive was opened, unpacked or summarized by the lead."}
    pathlib.Path(out).write_text(json.dumps(idx, indent=1, sort_keys=True) + "\n")
    print("index", sha(out), "problems", problems)


if __name__ == "__main__":
    main(*sys.argv[1:3])
