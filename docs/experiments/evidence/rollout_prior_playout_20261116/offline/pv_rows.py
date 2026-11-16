#!/usr/bin/env python3
"""Rows for one_combat playoutvaluebench from prior-factory unit tars (validation split only).

usage: python3 -I pv_rows.py OUT.jsonl TAR [TAR ...]
Keeps root rows (kind root) of validation-split seeds (train.py::split_of == 1) in prior-playout rooms (boss rooms and
act-4 elites; train.py's Pack.playout) with >= 2 edges, and adds the fight's recorded outcome (fight row: score, won,
endHp) as `ref`. Also writes extra rows (tree / playout states) of the same rooms with `ref` = null (no outcome).
"""
import json, lzma, sys, tarfile


def split_of(seed):
    return (seed * 2654435761) % 2 ** 32 % 10


def playout_room(r):
    return r.get("room") == "BOSS" or (int(r.get("act", 0)) == 4 and r.get("room") == "ELITE")


def main(out, *tars):
    n = {"root": 0, "extra": 0}
    with open(out, "w") as f:
        for t in tars:
            with tarfile.open(t) as tf:
                m = [x for x in tf.getmembers() if x.name.endswith(".jsonl.xz")]
                rows = [json.loads(l) for l in lzma.decompress(tf.extractfile(m[0]).read()).splitlines() if l.strip()]
            fights = {(r["seed"], r["fight"]): r for r in rows if r.get("kind") == "fight"}
            for r in rows:
                k = r.get("kind")
                if k not in ("root", "extra") or split_of(int(r["seed"])) != 1 or not playout_room(r):
                    continue
                if len(r.get("edges") or []) < 2 or not r.get("wire"):
                    continue
                fr = fights.get((r["seed"], r["fight"]))
                o = {"seed": r["seed"], "fight": r["fight"], "decision": r["decision"] if k == "root" else
                     1_000_000 + int(r["decision"]) * 8 + n["extra"] % 8, "wire": r["wire"],
                     "k": {"kind": k if k == "root" else r.get("source"), "enc": r.get("encounter"), "act": r.get("act"),
                           "turn": r.get("turn"), "hp": r.get("hp"), "qb": r.get("rootQBacked"),
                           "ref": None if k != "root" or fr is None else
                           {"score": fr.get("score"), "won": fr.get("won"), "endHp": fr.get("endHp")}}}
                f.write(json.dumps(o) + "\n")
                n[k] += 1
    print(json.dumps(n))


if __name__ == "__main__":
    main(*sys.argv[1:])
