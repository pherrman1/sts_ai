#!/usr/bin/env python3
"""Pack the silver-leaf-a20 rows for the leaf value head (README analysis step 2).

For every unit (DEST/out/units/<id>/<variant>-<first>.jsonl.gz whose .done says rc=0) the prior's extractor
`one_combat silversynthfeatures` (the campaign binary, run from the repo root) rebuilds each searched root from its
wire; this keeps the root's 1,766-wide state block and labels it z = score / 100, the fight's `score` (Silver's own
end evaluation, referenced to the fight's first searched root). Per root it also stores won, end HP and turns of the
fight, act, floor, room, encounter, turn, the turn-start flag (the first root of its turn in its fight), decision
index, edge count, the most visited edge's Q, the visit-weighted mean Q, HP, variant and seed (fold = seed % 5), and
refchg: the root's gold or max HP differs from the fight's first searched root (Looter/Mugger steal, Feed), where
the label's gold and max-HP terms no longer match the tree's own reference at that root; and winnow, the root's
win-now value (SilverSearcher::winNowValue, extractors from 2026-10-23 on; NaN from older ones).
Roots whose fight has no fight row or a null score are dropped and counted. Extractor files are deleted per unit.

usage: pack_a20.py ONE_COMBAT REPO DEST OUT.npz [WORK_DIR] [JOBS]
"""
import concurrent.futures
import glob
import gzip
import json
import os
import re
import shutil
import subprocess
import sys
import time

import numpy as np

BIN, REPO, DEST, OUT = sys.argv[1:5]
WORK = sys.argv[5] if len(sys.argv) > 5 else OUT + ".work"
JOBS = int(sys.argv[6]) if len(sys.argv) > 6 else 4
S = 1766
ROOMS = ["MONSTER", "ELITE", "BOSS", "EVENT"]
t0 = time.time()


def units():
    out, bad = [], []
    for gz in sorted(glob.glob(os.path.join(DEST, "out", "units", "*", "*.jsonl.gz"))):
        done = gz[: -len(".jsonl.gz")] + ".done"
        txt = open(done).read() if os.path.exists(done) else ""
        (out if re.search(r"\brc=0\b", txt) else bad).append(gz)
    return out, bad


def one(gz):
    """Featurize one unit and return its root arrays (state rows only)."""
    tag = os.path.basename(os.path.dirname(gz)) + "-" + os.path.basename(gz)[: -len(".jsonl.gz")]
    prefix = os.path.join(WORK, tag)
    fights, ref = {}, {}
    with gzip.open(gz, "rb") as f:
        raw = f.read()
    for line in raw.splitlines():
        if b'"kind":"fight"' in line:
            r = json.loads(line)
            fights[(r["variant"], r["seed"], r["fight"])] = r
        elif b'"kind":"root"' in line:
            # Top-level keys are sorted and the wire comes last; the wire's only "gold" is the player's.
            g = {k: ROOT_KEYS[k].search(line).group(1) for k in ROOT_KEYS}
            rk = (g["variant"].decode(), int(g["seed"]), int(g["fight"]), int(g["decision"]))
            ref[rk] = (int(g["gold"]), int(g["maxHp"]))
    first = {}
    for (v, sd, fi, de), gm in sorted(ref.items()):
        first.setdefault((v, sd, fi), gm)
    for suf in (".nnz", ".idx", ".val", ".meta.jsonl", ".summary.json"):
        if os.path.exists(prefix + suf):
            os.remove(prefix + suf)
    p = subprocess.run([BIN, "silversynthfeatures", prefix], input=raw, cwd=REPO,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode != 0:
        raise RuntimeError(f"{gz}: rc {p.returncode}: {p.stderr.decode()[-400:]}")
    del raw
    summary = json.load(open(prefix + ".summary.json"))
    nnz = np.fromfile(prefix + ".nnz", dtype=np.uint32)
    ptr = np.concatenate([[0], np.cumsum(nnz, dtype=np.int64)])
    idx = np.fromfile(prefix + ".idx", dtype=np.uint16)
    val = np.fromfile(prefix + ".val", dtype=np.float32)
    meta = [json.loads(line) for line in open(prefix + ".meta.jsonl")]
    for suf in (".nnz", ".idx", ".val", ".meta.jsonl", ".summary.json"):
        os.remove(prefix + suf)

    st_idx, st_val, cols = [], [], {k: [] for k in COLS}
    dropped = 0
    i, n = 0, len(meta)
    last_turn = {}
    while i < n:
        m = meta[i]
        if m.get("k") != "state":
            i += 1
            continue
        row = i
        q, v = [], []
        i += 1
        while i < n and meta[i].get("k") in ("act", "after"):
            if meta[i]["k"] == "act":
                q.append(meta[i]["q"]); v.append(meta[i]["visits"])
            i += 1
        key = (m["variant"], m["seed"], m["fight"])
        fr = fights.get(key)
        if fr is None or fr.get("score") is None:
            dropped += 1
            continue
        gm = ref.get((m["variant"], m["seed"], m["fight"], m["decision"]))
        refchg = int(gm is None or gm != first.get(key))
        start = last_turn.get(key) != m["turn"]
        last_turn[key] = m["turn"]
        sl = slice(ptr[row], ptr[row + 1])
        st_idx.append(idx[sl]); st_val.append(val[sl])
        vs = float(sum(v))
        best = max(range(len(v)), key=lambda j: v[j])
        for k, x in (("seed", m["seed"]), ("fight", m["fight"]), ("var", 0 if m["variant"] == "natural" else 1),
                     ("z", fr["score"] / 100.0), ("won", int(bool(fr["won"]))), ("endhp", fr["endHp"]),
                     ("fturns", fr["turns"]), ("act", m["act"]), ("floor", m["floor"]),
                     ("room", ROOMS.index(m["room"]) if m["room"] in ROOMS else len(ROOMS)),
                     ("turn", m["turn"]), ("tstart", int(start)), ("decision", m["decision"]),
                     ("nedge", len(v)), ("qchosen", q[best]),
                     ("qmean", sum(a * b for a, b in zip(q, v)) / vs if vs else np.nan),
                     ("hp", m["hp"]), ("refchg", refchg), ("enc", m["encounter"]),
                     ("winnow", m.get("winNow", float("nan")))):
            cols[k].append(x)
    nn = np.array([len(a) for a in st_idx], np.int64)
    return (tag, summary, dropped, np.concatenate(st_idx) if st_idx else np.zeros(0, np.uint16),
            np.concatenate(st_val) if st_val else np.zeros(0, np.float32), nn, cols)


COLS = ["seed", "fight", "var", "z", "won", "endhp", "fturns", "act", "floor", "room", "turn", "tstart", "decision",
        "nedge", "qchosen", "qmean", "hp", "refchg", "enc", "winnow"]
ROOT_KEYS = {k: re.compile(rb'"%s":"?(\w+)' % k.encode()) for k in ("variant", "seed", "fight", "decision", "maxHp", "gold")}

if __name__ == "__main__":
    os.makedirs(WORK, exist_ok=True)
    good, bad = units()
    print(f"{len(good)} units with rc=0, {len(bad)} without: {bad[:5]}", flush=True)
    all_idx, all_val, all_nn, all_cols = [], [], [], {k: [] for k in COLS}
    counts, dropped_total = {}, 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=JOBS) as ex:
        for j, (tag, summary, dropped, si, sv, nn, cols) in enumerate(ex.map(one, good)):
            all_idx.append(si); all_val.append(sv); all_nn.append(nn)
            for k in COLS:
                all_cols[k].extend(cols[k])
            for k, v in summary.get("counts", {}).items():
                counts[k] = counts.get(k, 0) + v
            dropped_total += dropped
            if j % 10 == 0 or j == len(good) - 1:
                print(f"{j + 1}/{len(good)} {tag} roots so far {len(all_cols['seed'])} {time.time() - t0:.0f}s", flush=True)
    encs = sorted(set(all_cols["enc"]))
    nn = np.concatenate(all_nn)
    out = {"st_idx": np.concatenate(all_idx), "st_val": np.concatenate(all_val),
           "st_ptr": np.concatenate([[0], np.cumsum(nn)]).astype(np.int64),
           "encs": np.array(encs), "rooms": np.array(ROOMS)}
    for k in COLS:
        if k == "enc":
            out["r_enc"] = np.array([encs.index(e) for e in all_cols[k]], np.int16)
        elif k in ("z", "qchosen", "qmean", "winnow"):
            out["r_" + k] = np.array(all_cols[k], np.float32)
        else:
            out["r_" + k] = np.array(all_cols[k], np.int64)
    np.savez(OUT, **out)
    shutil.rmtree(WORK, ignore_errors=True)
    print(json.dumps({"units": len(good), "unitsNotRc0": len(bad), "roots": int(len(nn)), "droppedNoScore": dropped_total,
                      "extractorCounts": counts, "nnzMean": float(nn.mean()) if len(nn) else 0,
                      "seconds": round(time.time() - t0)}))
