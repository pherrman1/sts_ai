#!/usr/bin/env python3
"""Pack `one_combat rolloutpolicybench` prior-call captures into silver_az_mlp.py's npz layout.

usage: pack_capture.py OUT.npz PREFIX [PREFIX ...]

Each capture is a state row followed by one act row per edge; `visits` = round(1e6 * g7f_E prior), so
silver_az_mlp.py's `share` is the teacher's distribution. r_val is NaN (no value head target); folds are
silver_az_mlp's seed % 5 (train 0-2, val 3, test 4). Also writes OUT.meta.json (encounter, turn, root id per row).
"""
import json
import sys

import numpy as np

S, A = 1766, 22


def main():
    out, prefixes = sys.argv[1], sys.argv[2:]
    st_idx, st_val, st_ptr = [], [], [0]
    r_seed, r_fight, r_nedge, e_act, e_tgt, e_vis, meta = [], [], [], [], [], [], []
    for prefix in prefixes:
        nnz = np.fromfile(prefix + ".nnz", dtype=np.uint32)
        ptr = np.concatenate([[0], np.cumsum(nnz, dtype=np.int64)])
        idx = np.fromfile(prefix + ".idx", dtype=np.uint16)
        val = np.fromfile(prefix + ".val", dtype=np.float32)
        rows = [json.loads(l) for l in open(prefix + ".meta.jsonl")]
        i = 0
        while i < len(rows):
            m = rows[i]
            assert m["k"] == "state", (prefix, i)
            j = i + 1
            while j < len(rows) and rows[j]["k"] == "act":
                j += 1
            n = j - i - 1
            if n >= 2 and len(rows) >= j:
                sl = slice(ptr[i], ptr[i + 1])
                st_idx.append(idx[sl].astype(np.int16)); st_val.append(val[sl])
                st_ptr.append(st_ptr[-1] + int(nnz[i]))
                r_seed.append(m["seed"]); r_fight.append(m["fight"]); r_nedge.append(n)
                blk = np.zeros((n, A), np.float32)
                for k in range(n):
                    s2 = slice(ptr[i + 1 + k], ptr[i + 2 + k])
                    blk[k, idx[s2].astype(np.int64) - S] = val[s2]
                    e_tgt.append(rows[i + 1 + k]["tgt"]); e_vis.append(rows[i + 1 + k]["visits"])
                e_act.append(blk)
                meta.append([m["enc"], m["turn"], m["seed"], m["fight"], m["decision"]])
            i = j
    n = len(r_seed)
    np.savez(out, st_idx=np.concatenate(st_idx), st_val=np.concatenate(st_val), st_ptr=np.array(st_ptr, np.int64),
             r_src=np.zeros(n, np.int8), r_seed=np.array(r_seed, np.int64), r_fight=np.array(r_fight, np.int32),
             r_var=np.zeros(n, np.int8), r_val=np.full(n, np.nan, np.float32), r_nedge=np.array(r_nedge, np.int32),
             e_act=np.concatenate(e_act), e_tgt=np.array(e_tgt, np.int8), e_vis=np.array(e_vis, np.float32),
             tags=np.array(["capture"]))
    json.dump(meta, open(out + ".meta.json", "w"))
    print(json.dumps({"rows": n, "edges": len(e_tgt)}))


if __name__ == "__main__":
    main()
