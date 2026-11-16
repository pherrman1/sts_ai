#!/usr/bin/env python3
"""Pack prior-factory units (issue #1053 next prior; docs/experiments/evidence/prior_factory_20261116) for the
policy-MLP trainer.

Same layout as pack_d2.py (one .npz per unit tar, then `merge`), for rows of kind root and of kind extra
(STS_AZGEN_EXTRA_LABELS). Every state, wherever it comes from, has the same kind of target: the edges' visits of a
Gumbel root search, its Q / max-backed Q and its Gumbel pick. Extra columns:

  r_kind      0 = root (the played 16k search), 1 = tree node, 2 = playout state (both labelled by a fresh short search)
  r_lsims     simulations of the labelling search (the played root's budget for roots: 16000)
  r_depth     extras: decision-node depth below the root (tree) or tree depth where the playout started (playout)
  r_pstep     playout states: playout step (0 for roots and tree nodes)
  r_nvis      tree nodes: the played tree's visits at that node (0 otherwise)
  e_tvis      tree nodes: the played tree's visits of each edge at that node (NaN for other rows)

Value-side columns (r_val, r_won, r_endhp, r_turns_left, r_hp_next, r_pot_used) are the parent root's for extras:
they describe the played fight, not the extra state. Extras get r_decision = 1,000,000 + root decision * 8 + k.

usage:
  pack_factory.py units ONE_COMBAT UNITS_DIR OUT_DIR [--jobs 4]   # one .npz per unit tar in UNITS_DIR
  pack_factory.py merge OUT_DIR PACK.npz [--more DIR ...] [--splits 1] [--rooms playout] [--compress]
"""
import argparse
import concurrent.futures
import hashlib
import io
import json
import lzma
import os
import subprocess
import sys
import tarfile
import tempfile
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pack_d2 import ROOMS, S, A, fight_context, sha256  # noqa: E402

KIND = {"root": 0, "tree": 1, "playout": 2}


def read_unit(tar_path, tmp):
    with tarfile.open(tar_path) as t:
        members = [m for m in t.getmembers() if m.name.endswith(".jsonl.xz")]
        if len(members) != 1:
            raise RuntimeError(f"{tar_path}: want one .jsonl.xz, got {len(members)}")
        t.extract(members[0], tmp, filter="data")
    return os.path.join(tmp, members[0].name)


def corpus(jl):
    """(rows fed to silversynthfeatures, records by key, fights). Extras become root-shaped rows."""
    roots, fights, recs, feed = {}, {}, {}, []
    k_extra = {}
    with lzma.open(jl, "rt") as f:
        for line in f:
            r = json.loads(line)
            kind = r["kind"]
            if kind == "fight":
                fights[(r["variant"], r["seed"], r["fight"])] = r
                continue
            if kind == "root":
                key = (r["variant"], r["seed"], r["fight"], r["decision"])
                roots[key] = r
                recs[key] = (r, 0, r["decision"])
                feed.append(line)
            elif kind == "extra":
                pk = (r["variant"], r["seed"], r["fight"], r["decision"])
                k = k_extra.get(pk, 0)
                k_extra[pk] = k + 1
                dec = 1_000_000 + r["decision"] * 8 + k
                row = dict(r)
                row["kind"] = "root"
                row["decision"] = dec
                row.setdefault("inheritedVisits", 0)
                recs[(r["variant"], r["seed"], r["fight"], dec)] = (r, KIND[r["source"]], r["decision"])
                feed.append(json.dumps(row) + "\n")
    return feed, recs, roots, fights


def pack_unit(binary, tar_path, out_path):
    if os.path.exists(out_path):
        return out_path, "kept", {}
    digest = sha256(tar_path)
    with tempfile.TemporaryDirectory(prefix="pf-pack-") as tmp:
        jl = read_unit(tar_path, tmp)
        feed, recs, roots, fights = corpus(jl)
        prefix = os.path.join(tmp, "feat")
        r = subprocess.run([binary, "silversynthfeatures", prefix], input="".join(feed).encode(),
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if r.returncode != 0:
            raise RuntimeError(f"{tar_path}: rc {r.returncode}: {r.stderr.decode()[-500:]}")
        summary = json.load(open(prefix + ".summary.json"))
        ctx = fight_context(roots, fights)
        nnz = np.fromfile(prefix + ".nnz", dtype=np.uint32)
        ptr = np.concatenate([[0], np.cumsum(nnz, dtype=np.int64)])
        idx = np.fromfile(prefix + ".idx", dtype=np.uint16)
        val = np.fromfile(prefix + ".val", dtype=np.float32)
        names = ("st_idx", "st_val", "st_nnz", "r_seed", "r_fight", "r_decision", "r_var", "r_val", "r_nedge",
                 "r_gpick", "r_room", "r_act", "r_enc", "r_turn", "r_hp", "r_maxhp", "r_won", "r_endhp",
                 "r_turns_left", "r_hp_next", "r_pot_used", "r_kind", "r_lsims", "r_depth", "r_pstep", "r_nvis",
                 "e_act", "e_tgt", "e_vis", "e_q", "e_qb", "e_prior", "e_tvis")
        cols = {k: [] for k in names}
        encounters = []
        counts = {"root": 0, "tree": 0, "playout": 0, "single": 0, "noCorpusRow": 0, "noFight": 0}

        def flush(cur, acts):
            if cur is None:
                return
            if len(acts) < 2:
                counts["single"] += 1
                return
            m, row = cur
            key = (m["variant"], m["seed"], m["fight"], m["decision"])
            got = recs.get(key)
            if got is None:
                counts["noCorpusRow"] += 1
                return
            rec, kind, parent = got
            edges = rec["edges"]
            if [e["bits"] for e in edges] != [a["bits"] for _, a in acts]:
                raise RuntimeError(f"{tar_path}: edge order differs at {key}")
            sl = slice(ptr[row], ptr[row + 1])
            cols["st_idx"].append(idx[sl].astype(np.int16)); cols["st_val"].append(val[sl])
            cols["st_nnz"].append(int(nnz[row]))
            hp_next, pot_used, turns_left, won, endhp = ctx.get((*key[:3], parent), (np.nan,) * 5)
            if np.isnan(won):
                counts["noFight"] += 1
            cols["r_seed"].append(m["seed"]); cols["r_fight"].append(m["fight"]); cols["r_decision"].append(m["decision"])
            cols["r_var"].append(0 if m["variant"] == "natural" else 1)
            cols["r_val"].append(np.nan if np.isnan(won) else (won * (53.0 + endhp) / 100.0))
            cols["r_nedge"].append(len(acts))
            g = rec.get("gumbelChoice")
            cols["r_gpick"].append(-1 if g is None else int(g))
            cols["r_room"].append(ROOMS.get(rec["room"], 3)); cols["r_act"].append(rec["act"])
            if rec["encounter"] not in encounters:
                encounters.append(rec["encounter"])
            cols["r_enc"].append(encounters.index(rec["encounter"]))
            cols["r_turn"].append(rec["turn"]); cols["r_hp"].append(rec["hp"]); cols["r_maxhp"].append(rec["maxHp"])
            cols["r_won"].append(won); cols["r_endhp"].append(endhp); cols["r_turns_left"].append(turns_left)
            cols["r_hp_next"].append(hp_next); cols["r_pot_used"].append(pot_used)
            cols["r_kind"].append(kind)
            cols["r_lsims"].append(rec.get("labelSims", 16000))
            cols["r_depth"].append(rec.get("depth", 0)); cols["r_pstep"].append(rec.get("playoutStep", 0))
            cols["r_nvis"].append(rec.get("nodeVisits", 0) if kind == 1 else 0)
            tv = {e["bits"]: e["visits"] for e in rec.get("treeEdges") or []} if kind == 1 else {}
            blk = np.zeros((len(acts), A), np.float32)
            for j, (a_row, a_meta) in enumerate(acts):
                s2 = slice(ptr[a_row], ptr[a_row + 1])
                blk[j, idx[s2].astype(np.int64) - S] = val[s2]
                e = edges[j]
                cols["e_tgt"].append(a_meta["tgt"]); cols["e_vis"].append(e["visits"])
                cols["e_q"].append(e["q"] if e["visits"] > 0 else np.nan)
                qb = e.get("qBacked")
                cols["e_qb"].append(qb if (qb is not None and e["visits"] > 0) else np.nan)
                cols["e_prior"].append(e.get("prior", np.nan))
                cols["e_tvis"].append(tv.get(e["bits"], np.nan) if kind == 1 else np.nan)
            cols["e_act"].append(blk)
            counts[("root", "tree", "playout")[kind]] += 1

        cur, acts = None, []
        with open(prefix + ".meta.jsonl") as f:
            for i, line in enumerate(f):
                if '"k":"state"' in line:
                    flush(cur, acts)
                    cur, acts = (json.loads(line), i), []
                elif '"k":"act"' in line and cur is not None:
                    acts.append((i, json.loads(line)))
        flush(cur, acts)
    if counts["root"] == 0:
        raise RuntimeError(f"{tar_path}: no roots")
    i64 = lambda k: np.array(cols[k], np.int64)  # noqa: E731
    f32 = lambda k: np.array(cols[k], np.float32)  # noqa: E731
    i8 = lambda k: np.array(cols[k], np.int8)  # noqa: E731
    np.savez(out_path + ".tmp.npz", st_idx=np.concatenate(cols["st_idx"]), st_val=np.concatenate(cols["st_val"]),
             st_nnz=i64("st_nnz"), r_seed=i64("r_seed"), r_fight=i64("r_fight"), r_decision=i64("r_decision"),
             r_var=i8("r_var"), r_val=f32("r_val"), r_nedge=i64("r_nedge"), r_gpick=i64("r_gpick"),
             r_room=i8("r_room"), r_act=i8("r_act"), r_enc=i64("r_enc"), r_turn=i64("r_turn"), r_hp=f32("r_hp"),
             r_maxhp=f32("r_maxhp"), r_won=f32("r_won"), r_endhp=f32("r_endhp"), r_turns_left=f32("r_turns_left"),
             r_hp_next=f32("r_hp_next"), r_pot_used=f32("r_pot_used"), r_kind=i8("r_kind"), r_lsims=i64("r_lsims"),
             r_depth=i64("r_depth"), r_pstep=i64("r_pstep"), r_nvis=i64("r_nvis"),
             e_act=np.concatenate(cols["e_act"]), e_tgt=i8("e_tgt"), e_vis=f32("e_vis"), e_q=f32("e_q"),
             e_qb=f32("e_qb"), e_prior=f32("e_prior"), e_tvis=f32("e_tvis"), encounters=np.array(encounters),
             counts=json.dumps(counts), summary=json.dumps(summary), tar=tar_path, tar_sha256=digest)
    os.replace(out_path + ".tmp.npz", out_path)
    return out_path, "ok", counts


def cmd_units(a):
    os.makedirs(a.out, exist_ok=True)
    tars = sorted(f for f in os.listdir(a.units) if f.endswith(".tar"))
    seen, jobs = set(), []
    for f in tars:  # first tar per unit id (duplicates hold the same seeds)
        uid = f.rsplit(".w", 1)[0]
        if uid in seen:
            continue
        seen.add(uid)
        jobs.append((os.path.join(a.units, f), os.path.join(a.out, f + ".npz")))
    prov = {"binary": os.path.abspath(a.binary), "binary_sha256": sha256(a.binary), "units_dir": os.path.abspath(a.units),
            "units": len(jobs), "STS_ACTIVE_POWER_FEATURES": os.environ.get("STS_ACTIVE_POWER_FEATURES", "unset (default 1)")}
    json.dump(prov, open(os.path.join(a.out, "provenance.json"), "w"), indent=1)
    t0, tot = time.time(), {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.jobs) as ex:
        futs = [ex.submit(pack_unit, a.binary, p, o) for p, o in jobs]
        for i, fu in enumerate(concurrent.futures.as_completed(futs)):
            path, status, counts = fu.result()
            for k, v in counts.items():
                tot[k] = tot.get(k, 0) + v
            print(f"{i + 1}/{len(jobs)} {status} {os.path.basename(path)} {time.time() - t0:.0f}s {json.dumps(counts)}",
                  flush=True)
    print(json.dumps({"units": len(jobs), "seconds": round(time.time() - t0), "counts": tot}))


def split_of(seeds):
    """T1's split (tools/rollout_prior/train.py::split_of): 0 = gate holdout, 1 = validation, 2..9 = training."""
    return (seeds.astype(np.uint64) * np.uint64(2654435761)) % np.uint64(2 ** 32) % np.uint64(10)


def unit_packs(dirs):
    """(name, loader) for every per-unit pack in DIRS: loose .tar.npz / .tar.npz.xz files and the members of
    bundle-*.tar files (the batch-2 packer's bundles); a unit packed twice (duplicate lanes) is read once."""
    seen = set()
    for d in dirs:
        for f in sorted(os.listdir(d)):
            path = os.path.join(d, f)
            if f.endswith((".tar.npz", ".tar.npz.xz")):
                items = [(f, lambda path=path: open(path, "rb").read())]
            elif f.startswith("bundle-") and f.endswith(".tar"):
                tf = tarfile.open(path)
                items = [(m.name, lambda m=m, tf=tf: tf.extractfile(m).read())
                         for m in tf.getmembers() if m.name.endswith(".tar.npz.xz")]
            else:
                continue
            for name, read in items:
                uid = name.split(".w")[0]
                if uid in seen:
                    continue
                seen.add(uid)
                yield name, read


def cmd_merge(a):
    encounters, parts, sources = [], {}, []
    st_ptr, off = [np.zeros(1, np.int64)], 0
    for f, read in unit_packs([a.out] + (a.more or [])):
        raw = read()
        z = np.load(io.BytesIO(lzma.decompress(raw) if f.endswith(".xz") else raw))
        z = {k: z[k] for k in z.files}
        if a.splits or a.rooms == "playout":
            keep = np.ones(len(z["r_seed"]), bool)
            if a.splits:
                # keep only rows whose run seed falls in the given T1 splits (train.py::split_of)
                keep &= np.isin(split_of(z["r_seed"]), a.splits)
            if a.rooms == "playout":
                # prior-playout rooms (train.py Pack.playout): boss rooms and Act-4 elites
                keep &= (z["r_room"] == 2) | ((z["r_act"] == 4) & (z["r_room"] == 1))
            ekeep, skeep = np.repeat(keep, z["r_nedge"]), np.repeat(keep, z["st_nnz"])
            for k in list(z):
                if k.startswith("r_") or k == "st_nnz":
                    z[k] = z[k][keep]
                elif k.startswith("e_"):
                    z[k] = z[k][ekeep]
                elif k in ("st_idx", "st_val"):
                    z[k] = z[k][skeep]
        enc = [str(e) for e in z["encounters"]]
        for e in enc:
            if e not in encounters:
                encounters.append(e)
        remap = np.array([encounters.index(e) for e in enc], np.int64)
        for k in z:
            if k in ("encounters", "counts", "summary", "tar", "tar_sha256", "st_nnz"):
                continue
            parts.setdefault(k, []).append(remap[z[k]] if k == "r_enc" else z[k])
        st_ptr.append(off + np.cumsum(z["st_nnz"]))
        off += int(z["st_nnz"].sum())
        sources.append({"unit": f, "tar_sha256": str(z["tar_sha256"]), "counts": json.loads(str(z["counts"]))})
    out = {k: np.concatenate(parts.pop(k)) for k in list(parts)}  # pop: one key's parts at a time in memory
    n = len(out["r_seed"])
    out["st_ptr"] = np.concatenate(st_ptr)
    out["r_src"] = out["r_kind"].astype(np.int8)
    out["tags"] = np.array(["factory-root", "factory-tree", "factory-playout"])
    out["encounters"] = np.array(encounters)
    (np.savez_compressed if a.compress else np.savez)(a.pack, **out)
    info = {"pack": os.path.abspath(a.pack), "units": len(sources), "rooms": a.rooms, "states": n,
            "by_kind": {k: int((out["r_kind"] == v).sum()) for k, v in KIND.items()},
            "edges": int(len(out["e_tgt"])), "encounters": len(encounters), "sha256": sha256(a.pack)}
    json.dump({**info, "sources": sources}, open(a.pack + ".json", "w"), indent=1)
    print(json.dumps(info))


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    u = sub.add_parser("units"); u.add_argument("binary"); u.add_argument("units"); u.add_argument("out")  # noqa: E702
    u.add_argument("--jobs", type=int, default=4)
    m = sub.add_parser("merge"); m.add_argument("out"); m.add_argument("pack")  # noqa: E702
    m.add_argument("--splits", type=lambda x: [int(v) for v in x.split(",")], default=None,
                   help="keep only these T1 splits, e.g. 1 (validation) or 2,3,4,5,6,7,8,9 (training)")
    m.add_argument("--more", nargs="*", help="further directories with unit packs or bundle-*.tar files")
    m.add_argument("--rooms", default="all", choices=["all", "playout"], help="playout = boss rooms + Act-4 elites only")
    m.add_argument("--compress", action="store_true", help="np.savez_compressed (train.py loads it the same way)")
    a = p.parse_args()
    {"units": cmd_units, "merge": cmd_merge}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
