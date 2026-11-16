#!/usr/bin/env python3
"""Pack D2 / D2b G16 + mb4 roots (Gumbel distillation corpus, ledger §787) for the policy-MLP trainer.

Issue #1053 (Gumbel AZ loop for the rollout prior). The output keeps `tools/silver_az_mlp.py`'s pack layout
(st_idx, st_val, st_ptr, r_*, e_act, e_tgt, e_vis, tags), so `silver_az_mlp.Data` and the gen-6/7 trainer load it,
and adds the search's per-edge values and auxiliary targets:

  e_q, e_qb, e_prior      mean Q, max-backed Q (NaN for an unvisited edge) and the recorded root prior (g7f_E)
  r_gpick                 index of the played Gumbel pick in the root's edges (-1 if none)
  r_room, r_act, r_enc    room (0 MONSTER, 1 ELITE, 2 BOSS, 3 EVENT), act, encounter (index into `encounters`)
  r_turn, r_hp, r_maxhp   root turn and player HP
  r_won, r_endhp          fight outcome (NaN when the fight has no fight row, e.g. an aborted run)
  r_turns_left            fight turns minus the root's turn
  r_hp_next               player HP at the fight's first later root with a larger turn; endHp (won) / 0 (lost)
                          when no such root exists; NaN without a fight row
  r_pot_used              potions held at the root minus potions held at the fight's last root (lower bound on
                          potions used in the rest of the fight: the last root's own potion use is not seen)
  r_val                   won * (53 + endHp) / 100, as silver_az_mlp.py (the trainer's value head target)

Each unit tar is checked against the freeze list's sha256, featurized with `one_combat silversynthfeatures` in a
temporary directory (deleted afterwards), and joined with its own jsonl rows by (seed, fight, decision).

usage:
  pack_d2.py units ONE_COMBAT FREEZE_LIST SHARE_ROOT OUT_DIR [--jobs 4]   # one .npz per unit tar
  pack_d2.py merge OUT_DIR PACK.npz                                       # concatenate the unit files
"""
import argparse
import concurrent.futures
import gzip
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import time

import numpy as np

S, A = 1766, 22
ROOMS = {"MONSTER": 0, "ELITE": 1, "BOSS": 2, "EVENT": 3}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_freeze(path):
    out = []
    for line in open(path):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        digest, rel = line.split()
        out.append((digest, rel))
    return out


def corpus_rows(jsonl_gz):
    roots, fights = {}, {}
    with gzip.open(jsonl_gz, "rt") as f:
        for line in f:
            r = json.loads(line)
            if r["kind"] == "fight":
                fights[(r["variant"], r["seed"], r["fight"])] = r
            elif r["kind"] == "root":
                roots[(r["variant"], r["seed"], r["fight"], r["decision"])] = r
    return roots, fights


def fight_context(roots, fights):
    """Per root key: (hp_next, pot_used, turns_left, won, endHp) from the fight's other roots and its fight row."""
    by_fight = {}
    for k, r in roots.items():
        by_fight.setdefault(k[:3], []).append(r)
    ctx = {}
    for fk, rs in by_fight.items():
        rs.sort(key=lambda r: r["decision"])
        fr = fights.get(fk)
        last_pot = (rs[-1]["wire"] or {}).get("potionCount")
        for i, r in enumerate(rs):
            if fr is None:
                ctx[(*fk, r["decision"])] = (np.nan, np.nan, np.nan, np.nan, np.nan)
                continue
            nxt = next((q for q in rs[i + 1:] if q["turn"] > r["turn"]), None)
            hp_next = nxt["hp"] if nxt is not None else (fr["endHp"] if fr["won"] else 0)
            pot = (r["wire"] or {}).get("potionCount")
            pot_used = pot - last_pot if pot is not None and last_pot is not None else np.nan
            ctx[(*fk, r["decision"])] = (hp_next, pot_used, fr["turns"] - r["turn"], float(fr["won"]), fr["endHp"])
    return ctx


def pack_unit(binary, digest, tar_path, out_path):
    if os.path.exists(out_path):
        return out_path, "kept", {}
    got = sha256(tar_path)
    if got != digest:
        raise RuntimeError(f"{tar_path}: sha256 {got} != freeze {digest}")
    with tempfile.TemporaryDirectory(prefix="rp-pack-") as tmp:
        with tarfile.open(tar_path) as t:
            members = [m for m in t.getmembers() if m.name.endswith(".jsonl.gz")]
            if len(members) != 1:
                raise RuntimeError(f"{tar_path}: want one .jsonl.gz, got {len(members)}")
            t.extract(members[0], tmp, filter="data")
        jl = os.path.join(tmp, members[0].name)
        prefix = os.path.join(tmp, "feat")
        with gzip.open(jl, "rb") as src:
            r = subprocess.run([binary, "silversynthfeatures", prefix], input=src.read(),
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if r.returncode != 0:
            raise RuntimeError(f"{tar_path}: rc {r.returncode}: {r.stderr.decode()[-500:]}")
        summary = json.load(open(prefix + ".summary.json"))
        roots, fights = corpus_rows(jl)
        ctx = fight_context(roots, fights)
        nnz = np.fromfile(prefix + ".nnz", dtype=np.uint32)
        ptr = np.concatenate([[0], np.cumsum(nnz, dtype=np.int64)])
        idx = np.fromfile(prefix + ".idx", dtype=np.uint16)
        val = np.fromfile(prefix + ".val", dtype=np.float32)
        cols = {k: [] for k in ("st_idx", "st_val", "st_nnz", "r_seed", "r_fight", "r_decision", "r_var", "r_val",
                                "r_nedge", "r_gpick", "r_room", "r_act", "r_enc", "r_turn", "r_hp", "r_maxhp",
                                "r_won", "r_endhp", "r_turns_left", "r_hp_next", "r_pot_used", "e_act", "e_tgt",
                                "e_vis", "e_q", "e_qb", "e_prior")}
        encounters = []
        counts = {"roots": 0, "single": 0, "noCorpusRow": 0, "noFight": 0}

        def flush(cur, acts):
            if cur is None:
                return
            if len(acts) < 2:
                counts["single"] += 1
                return
            m, row = cur
            key = (m["variant"], m["seed"], m["fight"], m["decision"])
            rec = roots.get(key)
            if rec is None:
                counts["noCorpusRow"] += 1
                return
            edges = rec["edges"]
            if [e["bits"] for e in edges] != [a["bits"] for _, a in acts]:
                raise RuntimeError(f"{tar_path}: edge order differs at {key}")
            sl = slice(ptr[row], ptr[row + 1])
            cols["st_idx"].append(idx[sl].astype(np.int16)); cols["st_val"].append(val[sl])
            cols["st_nnz"].append(int(nnz[row]))
            hp_next, pot_used, turns_left, won, endhp = ctx[key]
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
            blk = np.zeros((len(acts), A), np.float32)
            for j, (a_row, a_meta) in enumerate(acts):
                s2 = slice(ptr[a_row], ptr[a_row + 1])
                blk[j, idx[s2].astype(np.int64) - S] = val[s2]
                e = edges[j]
                cols["e_tgt"].append(a_meta["tgt"]); cols["e_vis"].append(e["visits"])
                cols["e_q"].append(e["q"] if e["visits"] > 0 else np.nan)
                qb = e.get("qBacked")
                cols["e_qb"].append(qb if (qb is not None and e["visits"] > 0) else np.nan)
                cols["e_prior"].append(e["prior"])
            cols["e_act"].append(blk)
            counts["roots"] += 1

        cur, acts = None, []
        with open(prefix + ".meta.jsonl") as f:
            for i, line in enumerate(f):
                if '"k":"state"' in line:
                    flush(cur, acts)
                    cur, acts = (json.loads(line), i), []
                elif '"k":"act"' in line and cur is not None:
                    acts.append((i, json.loads(line)))
        flush(cur, acts)
    if counts["roots"] == 0:
        raise RuntimeError(f"{tar_path}: no roots")
    i64 = lambda k: np.array(cols[k], np.int64)
    f32 = lambda k: np.array(cols[k], np.float32)
    np.savez(out_path + ".tmp.npz", st_idx=np.concatenate(cols["st_idx"]), st_val=np.concatenate(cols["st_val"]),
             st_nnz=i64("st_nnz"), r_seed=i64("r_seed"), r_fight=i64("r_fight"), r_decision=i64("r_decision"),
             r_var=np.array(cols["r_var"], np.int8), r_val=f32("r_val"), r_nedge=i64("r_nedge"), r_gpick=i64("r_gpick"),
             r_room=np.array(cols["r_room"], np.int8), r_act=np.array(cols["r_act"], np.int8), r_enc=i64("r_enc"),
             r_turn=i64("r_turn"), r_hp=f32("r_hp"), r_maxhp=f32("r_maxhp"), r_won=f32("r_won"), r_endhp=f32("r_endhp"),
             r_turns_left=f32("r_turns_left"), r_hp_next=f32("r_hp_next"), r_pot_used=f32("r_pot_used"),
             e_act=np.concatenate(cols["e_act"]), e_tgt=np.array(cols["e_tgt"], np.int8), e_vis=f32("e_vis"),
             e_q=f32("e_q"), e_qb=f32("e_qb"), e_prior=f32("e_prior"), encounters=np.array(encounters),
             counts=json.dumps(counts), summary=json.dumps(summary), tar=tar_path, tar_sha256=digest)
    os.replace(out_path + ".tmp.npz", out_path)
    return out_path, "ok", counts


def cmd_units(a):
    os.makedirs(a.out, exist_ok=True)
    freeze = read_freeze(a.freeze)
    jobs = [(d, os.path.join(a.share, rel), os.path.join(a.out, os.path.basename(rel) + ".npz")) for d, rel in freeze]
    prov = {"binary": os.path.abspath(a.binary), "binary_sha256": sha256(a.binary), "freeze": os.path.abspath(a.freeze),
            "freeze_sha256": sha256(a.freeze), "units": len(jobs),
            "STS_ACTIVE_POWER_FEATURES": os.environ.get("STS_ACTIVE_POWER_FEATURES", "unset (default 1)")}
    json.dump(prov, open(os.path.join(a.out, "provenance.json"), "w"), indent=1)
    t0 = time.time()
    tot = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.jobs) as ex:
        futs = [ex.submit(pack_unit, a.binary, d, p, o) for d, p, o in jobs]
        for i, fu in enumerate(concurrent.futures.as_completed(futs)):
            path, status, counts = fu.result()
            for k, v in counts.items():
                tot[k] = tot.get(k, 0) + v
            print(f"{i + 1}/{len(jobs)} {status} {os.path.basename(path)} {time.time() - t0:.0f}s {json.dumps(counts)}",
                  flush=True)
    print(json.dumps({"units": len(jobs), "seconds": round(time.time() - t0), "counts": tot}))


def cmd_merge(a):
    files = sorted(f for f in os.listdir(a.out) if f.endswith(".tar.npz"))
    encounters = []
    parts = {}
    st_ptr = [np.zeros(1, np.int64)]
    off = 0
    sources = []
    for f in files:
        z = np.load(os.path.join(a.out, f))
        enc = [str(e) for e in z["encounters"]]
        for e in enc:
            if e not in encounters:
                encounters.append(e)
        remap = np.array([encounters.index(e) for e in enc], np.int64)
        for k in z.files:
            if k in ("encounters", "counts", "summary", "tar", "tar_sha256", "st_nnz"):
                continue
            v = remap[z[k]] if k == "r_enc" else z[k]
            parts.setdefault(k, []).append(v)
        st_ptr.append(off + np.cumsum(z["st_nnz"]))
        off += int(z["st_nnz"].sum())
        sources.append({"unit": f, "tar_sha256": str(z["tar_sha256"]), "counts": json.loads(str(z["counts"]))})
    out = {k: np.concatenate(v) for k, v in parts.items()}
    n = len(out["r_seed"])
    out["st_ptr"] = np.concatenate(st_ptr)
    out["r_src"] = np.zeros(n, np.int8)
    out["tags"] = np.array(["d2"])
    out["encounters"] = np.array(encounters)
    np.savez(a.pack, **out)
    info = {"pack": os.path.abspath(a.pack), "units": len(files), "roots": n, "edges": int(len(out["e_tgt"])),
            "encounters": len(encounters), "sha256": sha256(a.pack)}
    json.dump({**info, "sources": sources}, open(a.pack + ".json", "w"), indent=1)
    print(json.dumps(info))


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    u = sub.add_parser("units"); u.add_argument("binary"); u.add_argument("freeze"); u.add_argument("share")
    u.add_argument("out"); u.add_argument("--jobs", type=int, default=4)
    m = sub.add_parser("merge"); m.add_argument("out"); m.add_argument("pack")
    a = p.parse_args()
    {"units": cmd_units, "merge": cmd_merge}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
