#!/usr/bin/env python3
"""Retrain the frozen 3,200-parameter OOC contextual deck representation block.

This research runner recreates the Tier-B raw-to-grouped-v2 state mapping,
distills only the contextual deck block against the deployed42 teacher's deck
representation, and writes a flat 121-tensor checkpoint (115 frozen teacher
tensors plus six contextual tensors). It does not train policy/Q heads, export
native code, or collect game seeds.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time

import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.nn import functional as F

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategic_tok_contract import build_globals, make_layout  # noqa: E402
from strategic_tok_net import MAXD, MAXP, MAXR, NGLOB, NCARD, NREL, NPOT, Net  # noqa: E402
from strategic_tok_state_cache import (  # noqa: E402
    STATE_CACHE_LAYOUT_VERSION,
    build_raw_to_grouped,
    write_raw_state_chunk,
)


CORPUS_SHA256 = "c428f229bdf7cfe070ff06fd1664978e6e49bbde872d5929ef4fa50f56ba008b"
SPLIT_SHA256 = "0efe5b56e1f87c0642827c14e55790db517b55820d54620edd32420012e8b67b"
NATIVE_SHA256 = "e62abd833fc8cb9081a1cec4a1a012832ac3b0e3166da3892841911664f1184c"
TEACHER_SHA256 = "5bc14fb437131d4bdc531ea775e22eca1f6834976d4670ec0aabb2fb14b735b8"
TRACE_GZIP_SHA256 = "192b623ca28887e7da646aca16efaecd041583261265e1af23b83a1eab958370"
NROWS = 3_057_708
NFILE = NGLOB + MAXD * 3 + MAXR * 2 + MAXP * 2
BATCH_GROUPS = 4096
EPOCHS = 30


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def atomic_json(path: Path, value: dict) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temp.replace(path)


def verify_python_native_parity(teacher_path: Path, native_path: Path,
                                trace_path: Path, out: Path):
    """Verify exporter parity and actual deployed-native trace logits before training."""
    exported = out / "teacher_python_native_parity.native"
    receipt_path = out / "teacher_python_native_parity.json"
    trace_receipt = out / "teacher_trace_parity.json"
    trace_stdout = out / "teacher_trace_parity.stdout.txt"
    if exported.exists() or receipt_path.exists() or trace_receipt.exists() or trace_stdout.exists():
        raise FileExistsError("teacher parity output already exists; refusing to replace it")
    command = [sys.executable, str(ROOT / "export_strategic_tok.py"),
               str(teacher_path), str(exported)]
    completed = subprocess.run(command, cwd=ROOT, text=True, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, check=False)
    (out / "teacher_python_native_parity.stdout.txt").write_text(completed.stdout)
    if completed.returncode != 0 or "32 parity checks passed" not in completed.stdout:
        raise RuntimeError("Python/native parity exporter failed:\n" + completed.stdout)
    exported_sha = sha256(exported)
    if exported_sha != NATIVE_SHA256 or exported_sha != sha256(native_path):
        raise RuntimeError(f"Python teacher export SHA {exported_sha} differs from tracked native")
    numeric = re.search(r"max err logit ([0-9.eE+-]+), value ([0-9.eE+-]+), Q ([0-9.eE+-]+)",
                        completed.stdout)
    if numeric is None:
        raise RuntimeError("could not parse numerical parity maxima from exporter output")
    errors = {"max_logit_error": float(numeric.group(1)),
              "max_value_error": float(numeric.group(2)),
              "max_q_error": float(numeric.group(3))}
    if errors["max_logit_error"] >= 1e-4 or errors["max_value_error"] >= 2e-4 or errors["max_q_error"] >= 2e-4:
        raise RuntimeError(f"Python/native parity error exceeds exporter tolerances: {errors}")
    receipt = {"command": command, "returncode": completed.returncode,
               "check": "32 repository Numpy/native-mirror versus PyTorch cases",
               "teacher_sha256": sha256(teacher_path),
               "tracked_native_sha256": sha256(native_path),
               "reexported_native_sha256": exported_sha,
               "reexport_byte_identical_to_tracked_native": True,
               "numeric_errors": errors,
               "stdout_sha256": sha256(out / "teacher_python_native_parity.stdout.txt")}
    if sha256(trace_path) != TRACE_GZIP_SHA256:
        raise ValueError("pretraining authoritative semantic trace SHA differs")
    trace_command = [sys.executable, str(Path(__file__).resolve().parent
                                        / "evaluate_ooc_contextual_semantic_trace.py"),
                     "--teacher-only", "--trace", str(trace_path),
                     "--teacher", str(teacher_path), "--out", str(trace_receipt)]
    trace_completed = subprocess.run(trace_command, cwd=ROOT, text=True,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     check=False)
    trace_stdout.write_text(trace_completed.stdout)
    if trace_completed.returncode != 0 or not trace_receipt.is_file():
        raise RuntimeError("Python teacher versus captured native trace preflight failed:\n"
                           + trace_completed.stdout)
    trace_result = json.loads(trace_receipt.read_text())
    if (trace_result.get("result") != "PASS"
            or trace_result.get("python_native_teacher_preflight", {}).get(
                "max_abs_python_vs_captured_native_source_logit", 1.0) >= 1e-4
            or trace_result.get("python_native_teacher_preflight", {}).get(
                "source_argmax_parity", 0.0) != 1.0):
        raise RuntimeError(f"captured native trace preflight failed: {trace_result}")
    receipt["authoritative_captured_native_trace_preflight"] = trace_result
    receipt["trace_preflight_command"] = trace_command
    receipt["trace_preflight_stdout_sha256"] = sha256(trace_stdout)
    atomic_json(receipt_path, receipt)
    return receipt


def deck_tokens(d: np.ndarray, u: np.ndarray):
    n = d.shape[0]
    ids = np.full((n, MAXD), -1, np.float32)
    ups = np.zeros((n, MAXD), np.float32)
    cfs = np.zeros((n, MAXD), np.float32)
    width = np.zeros(n, np.int32)
    for card in range(NCARD):
        upgraded = u[:, card]
        m = upgraded > 0
        if m.any():
            j = width[m]
            ids[m, j] = card
            ups[m, j] = 1.0
            cfs[m, j] = np.minimum(upgraded[m], 9) / 9.0
            width[m] += 1
        base = d[:, card] - upgraded
        m = base > 0
        if m.any():
            j = width[m]
            ids[m, j] = card
            cfs[m, j] = np.minimum(base[m], 9) / 9.0
            width[m] += 1
    return ids, ups, cfs


def relic_tokens(r: np.ndarray):
    n = r.shape[0]
    ids = np.full((n, MAXR), -1, np.float32)
    data = np.zeros((n, MAXR), np.float32)
    width = np.zeros(n, np.int32)
    for relic in range(NREL):
        value = r[:, relic]
        m = value > 0
        if m.any():
            j = width[m]
            ids[m, j] = relic
            data[m, j] = np.minimum(value[m] - 1.0, 9) / 9.0
            width[m] += 1
    return ids, data


def potion_tokens(p: np.ndarray):
    n = p.shape[0]
    ids = np.full((n, MAXP), -1, np.float32)
    counts = np.zeros((n, MAXP), np.float32)
    width = np.zeros(n, np.int32)
    for potion in range(NPOT):
        value = p[:, potion]
        m = value > 0
        if m.any():
            j = width[m]
            ids[m, j] = potion
            counts[m, j] = np.minimum(value[m], 9) / 9.0
            width[m] += 1
    return ids, counts


def token_batch(states, rows, device):
    a = np.asarray(states[rows])
    ids = torch.as_tensor(a[:, NGLOB:NGLOB + MAXD * 3:3].astype(np.int64), device=device)
    ups = torch.as_tensor(a[:, NGLOB + 1:NGLOB + MAXD * 3:3].astype(np.int64), device=device)
    cfs = torch.as_tensor(a[:, NGLOB + 2:NGLOB + MAXD * 3:3].astype(np.float32), device=device)
    return ids, ups, cfs


def group_layout(csv: Path):
    keys = pd.read_csv(csv, usecols=["seed", "decIdx"], dtype=np.int64)
    keys["_raw_row"] = np.arange(len(keys), dtype=np.int64)
    keys.sort_values(["seed", "decIdx"], kind="stable", inplace=True, ignore_index=True)
    if len(keys) != NROWS:
        raise ValueError(f"Tier-B row count {len(keys)} != {NROWS}")
    seed = keys.seed.to_numpy(np.int32, copy=True)
    dec = keys.decIdx.to_numpy(np.int32, copy=True)
    sorted_raw_rows = keys.pop("_raw_row").to_numpy(np.int64, copy=True)
    if np.any(dec < 0) or np.any(dec >= 1_000_000):
        raise ValueError("decision indices violate the composite group-key contract")
    composite = seed.astype(np.int64) * 1_000_000 + dec
    _, sorted_group_ids = np.unique(composite, return_inverse=True)
    grouped_order = np.argsort(sorted_group_ids, kind="stable")
    raw_to_grouped = build_raw_to_grouped(sorted_raw_rows, grouped_order)
    group_seed = seed[grouped_order]
    group_dec = dec[grouped_order]
    change = np.empty(NROWS, dtype=bool)
    change[0] = True
    change[1:] = ((group_seed[1:] != group_seed[:-1]) | (group_dec[1:] != group_dec[:-1]))
    starts = np.flatnonzero(change).astype(np.int64)
    sizes = np.diff(np.append(starts, NROWS)).astype(np.int32)
    if int(sizes.sum()) != NROWS or np.any(sizes <= 0):
        raise ValueError("group sizes do not partition the Tier-B source rows")
    return raw_to_grouped, group_seed[starts], group_dec[starts], starts, sizes


def create_state_cache(csv: Path, out: Path, raw_to_grouped: np.ndarray,
                       starts: np.ndarray, sizes: np.ndarray):
    state_path = out / "tierb_state_raw-to-grouped-v2.f16"
    manifest_path = out / "tierb_state_raw-to-grouped-v2.manifest.json"
    mapping_sha = hashlib.sha256(raw_to_grouped.tobytes()).hexdigest()
    binding = {"layout_version": STATE_CACHE_LAYOUT_VERSION,
               "corpus_sha256": CORPUS_SHA256,
               "rows": NROWS, "columns": NFILE, "dtype": "float16",
               "raw_to_grouped_mapping_sha256": mapping_sha,
               "group_count": int(len(starts)),
               "group_starts_sha256": hashlib.sha256(starts.tobytes()).hexdigest(),
               "group_sizes_sha256": hashlib.sha256(sizes.tobytes()).hexdigest(),
               "builder_sha256": sha256(Path(__file__))}
    if state_path.exists() or manifest_path.exists():
        if not state_path.is_file() or not manifest_path.is_file():
            raise FileExistsError("partial v2 state cache exists; refusing to overwrite")
        manifest = json.loads(manifest_path.read_text())
        if any(manifest.get(k) != v for k, v in binding.items()):
            raise ValueError("existing raw-to-grouped-v2 cache binding differs")
        if state_path.stat().st_size != NROWS * NFILE * 2:
            raise ValueError("existing v2 state cache size differs")
        if manifest.get("state_cache_sha256") != sha256(state_path):
            raise ValueError("existing v2 state cache SHA differs from its manifest")
        return state_path, manifest

    header = pd.read_csv(csv, nrows=0).columns
    ci, wi = list(header).index("chosen"), list(header).index("won")
    state_cols = list(header[ci + 1:wi])
    layout = make_layout(state_cols)
    if len(state_cols) != 1017:
        raise ValueError(f"rich state block width {len(state_cols)} != 1017")
    checks = [(23, "pvShop"), (31, "bottledPowId"), (1005, "fmDElite"),
              (1015, "curMapX"), (1016, "curMapY")]
    for index, name in checks:
        if state_cols[index] != name:
            raise ValueError(f"state column {index} is {state_cols[index]!r}, expected {name!r}")
    re_d, re_u = re.compile(r"^d(\d+)$"), re.compile(r"^u(\d+)$")
    re_r, re_p = re.compile(r"^r(\d+)$"), re.compile(r"^pot(\d+)$")
    d_idx, u_idx, r_idx, p_idx = [], [], [], []
    for i, name in enumerate(state_cols):
        if re_d.match(name): d_idx.append(i)
        elif re_u.match(name): u_idx.append(i)
        elif re_r.match(name): r_idx.append(i)
        elif re_p.match(name): p_idx.append(i)
    if (len(d_idx), len(u_idx), len(r_idx), len(p_idx)) != (NCARD, NCARD, NREL, NPOT):
        raise ValueError("rich-state token column counts differ from the V4 contract")

    tmp_path = out / "tierb_state_raw-to-grouped-v2.f16.partial"
    if tmp_path.exists():
        raise FileExistsError(f"partial state cache exists; inspect before removing: {tmp_path}")
    state_mem = np.memmap(tmp_path, dtype=np.float16, mode="w+", shape=(NROWS, NFILE))
    lo = 0
    for chunk in pd.read_csv(csv, usecols=state_cols, chunksize=25_000, dtype=np.float32):
        hi = lo + len(chunk)
        c = chunk.to_numpy(np.float64, copy=False)
        out_rows = np.zeros((len(chunk), NFILE), dtype=np.float32)
        out_rows[:, :NGLOB] = build_globals(c, layout).astype(np.float32)
        d, u, r, p = c[:, d_idx], c[:, u_idx], c[:, r_idx], c[:, p_idx]
        ids, ups, counts = deck_tokens(d, u)
        out_rows[:, NGLOB:NGLOB + MAXD * 3:3] = ids
        out_rows[:, NGLOB + 1:NGLOB + MAXD * 3:3] = ups
        out_rows[:, NGLOB + 2:NGLOB + MAXD * 3:3] = counts
        ids, data = relic_tokens(r)
        out_rows[:, NGLOB + MAXD * 3:NGLOB + MAXD * 3 + MAXR * 2:2] = ids
        out_rows[:, NGLOB + MAXD * 3 + 1:NGLOB + MAXD * 3 + MAXR * 2:2] = data
        ids, counts = potion_tokens(p)
        out_rows[:, NGLOB + MAXD * 3 + MAXR * 2:NFILE:2] = ids
        out_rows[:, NGLOB + MAXD * 3 + MAXR * 2 + 1:NFILE:2] = counts
        write_raw_state_chunk(state_mem, raw_to_grouped, lo, out_rows)
        lo = hi
        if lo % 500_000 < len(chunk):
            print(f"state-cache source rows={lo:,}/{NROWS:,}", flush=True)
    if lo != NROWS:
        raise ValueError(f"state-cache rows written {lo} != {NROWS}")
    state_mem.flush()
    del state_mem
    tmp_path.replace(state_path)
    manifest = {**binding, "state_cache_sha256": sha256(state_path)}
    atomic_json(manifest_path, manifest)

    states = np.memmap(state_path, dtype=np.float16, mode="r", shape=(NROWS, NFILE))
    group_for_row = np.repeat(np.arange(len(starts), dtype=np.int32), sizes)
    for lo in range(0, NROWS, 16_384):
        hi = min(lo + 16_384, NROWS)
        row_group = group_for_row[lo:hi]
        a = np.asarray(states[lo:hi])
        b = np.asarray(states[starts[row_group]])
        same = (a == b) | (np.isnan(a) & np.isnan(b))
        if not np.all(same):
            bad = int(np.flatnonzero(~same.all(axis=1))[0] + lo)
            raise ValueError(f"candidate state rows differ inside decision group at grouped row {bad}")
    return state_path, manifest


class ContextualDeck(nn.Module):
    def __init__(self):
        super().__init__()
        self.fc1 = nn.Linear(64, 32)
        self.fc2 = nn.Linear(32, 32)
        self.norm = nn.LayerNorm(32, eps=1e-5)
        nn.init.zeros_(self.fc2.weight)
        nn.init.zeros_(self.fc2.bias)

    def forward(self, tokens: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
        counts = mask.sum(1, keepdim=True)
        mean = (tokens * mask.unsqueeze(-1)).sum(1) / counts.clamp_min(1)
        pair = torch.cat((tokens, mean[:, None, :].expand_as(tokens)), -1)
        h = self.norm(tokens + self.fc2(F.gelu(self.fc1(pair))))
        return (h * mask.unsqueeze(-1)).sum(1) / counts.clamp_min(1)


def representation_metrics(pred, target):
    p = np.asarray(pred, dtype=np.float32)
    t = np.asarray(target, dtype=np.float32)
    diff = p - t
    pn, tn = np.linalg.norm(p, axis=1), np.linalg.norm(t, axis=1)
    cosine = np.sum(p * t, axis=1) / np.maximum(pn * tn, 1e-12)
    return {"mse": float(np.mean(diff * diff)),
            "mae": float(np.mean(np.abs(diff))),
            "cosine_mean": float(np.mean(cosine)),
            "cosine_median": float(np.median(cosine)),
            "cosine_p10": float(np.quantile(cosine, 0.1)),
            "student_teacher_norm_ratio_mean": float(np.mean(pn / np.maximum(tn, 1e-12)))}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--split", type=Path, required=True)
    parser.add_argument("--native", type=Path, required=True)
    parser.add_argument("--teacher", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    resolved_out = args.out.resolve()
    if any(resolved_out.parts[i] == ".codex"
           and resolved_out.parts[i + 1] == "worktrees"
           for i in range(len(resolved_out.parts) - 1)):
        raise ValueError("training artifacts must be written outside disposable .codex/worktrees")
    args.out.mkdir(parents=True, exist_ok=True)
    for path in (args.csv, args.split, args.native, args.teacher, args.trace):
        if not path.is_file():
            raise FileNotFoundError(path)
    actual = {"corpus_sha256": sha256(args.csv), "split_sha256": sha256(args.split),
              "native_sha256": sha256(args.native), "teacher_sha256": sha256(args.teacher)}
    actual["trace_gzip_sha256"] = sha256(args.trace)
    expected = {"corpus_sha256": CORPUS_SHA256, "split_sha256": SPLIT_SHA256,
                "native_sha256": NATIVE_SHA256, "teacher_sha256": TEACHER_SHA256,
                "trace_gzip_sha256": TRACE_GZIP_SHA256}
    if actual != expected:
        raise ValueError(f"input hashes differ: {actual}")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for the approved full-corpus run")
    device = "cuda"
    torch.set_num_threads(4)
    print(f"device={device} corpus_bytes={args.csv.stat().st_size:,}", flush=True)

    checkpoint = torch.load(args.teacher, map_location="cpu", weights_only=False)
    if checkpoint.get("native_sha256") != NATIVE_SHA256:
        raise ValueError("reconstructed teacher checkpoint is not bound to the tracked native")
    if len(checkpoint.get("state_dict", {})) != 115:
        raise ValueError("teacher state_dict must contain exactly 115 tensors")
    parity = verify_python_native_parity(args.teacher, args.native, args.trace, args.out)
    print(f"python_native_parity={json.dumps(parity, sort_keys=True)}", flush=True)
    teacher = Net(rung=4, nprobes=0, transformer=False, nquants=0, ncross=0).to(device)
    teacher.load_state_dict(checkpoint["state_dict"], strict=True)
    if len(teacher.state_dict()) != 115:
        raise ValueError("current Python teacher tensor inventory differs from 115")
    teacher.eval()
    for parameter in teacher.parameters():
        parameter.requires_grad_(False)

    split = json.loads(args.split.read_text())
    train_seeds = np.asarray(split["train_seeds"], dtype=np.int32)
    val_seeds = np.asarray(split["val_seeds"], dtype=np.int32)
    if len(train_seeds) != 3720 or len(val_seeds) != 930 or np.intersect1d(train_seeds, val_seeds).size:
        raise ValueError("Tier-B split seed membership differs from the frozen 3720/930 split")
    raw_to_grouped, group_seed, group_dec, starts, sizes = group_layout(args.csv)
    all_seeds = np.unique(group_seed)
    if not np.array_equal(np.sort(np.concatenate((train_seeds, val_seeds))), all_seeds):
        raise ValueError("split seed sets do not exactly cover the source corpus")
    train_mask = np.isin(group_seed, train_seeds)
    val_mask = np.isin(group_seed, val_seeds)
    if not np.all(train_mask | val_mask) or np.any(train_mask & val_mask):
        raise ValueError("source decision groups do not exactly map to frozen split")
    print(f"group_count={len(starts)} train_groups={int(train_mask.sum())} "
          f"validation_groups={int(val_mask.sum())}", flush=True)
    state_path, state_manifest = create_state_cache(args.csv, args.out, raw_to_grouped, starts, sizes)
    states = np.memmap(state_path, dtype=np.float16, mode="r", shape=(NROWS, NFILE))

    target_path = args.out / "teacher_deck_z.npy"
    plain_path = args.out / "teacher_token_mean.npy"
    target_manifest_path = args.out / "teacher_targets.manifest.json"
    group_binding = {"version": "deployed42-attention-deck-target-v1",
                     "teacher_sha256": TEACHER_SHA256, "native_sha256": NATIVE_SHA256,
                     "corpus_sha256": CORPUS_SHA256, "split_sha256": SPLIT_SHA256,
                     "state_cache_sha256": state_manifest["state_cache_sha256"],
                     "group_count": int(len(starts)), "token_cache_layout": STATE_CACHE_LAYOUT_VERSION}
    if target_path.exists() or plain_path.exists() or target_manifest_path.exists():
        if not (target_path.is_file() and plain_path.is_file() and target_manifest_path.is_file()):
            raise FileExistsError("partial teacher target cache exists; refusing to overwrite")
        target_manifest = json.loads(target_manifest_path.read_text())
        if any(target_manifest.get(k) != v for k, v in group_binding.items()):
            raise ValueError("existing teacher target cache has different provenance")
        if target_manifest.get("teacher_z_sha256") != sha256(target_path) or target_manifest.get("plain_mean_sha256") != sha256(plain_path):
            raise ValueError("existing teacher target cache content hash differs")
        teacher_z = np.load(target_path, mmap_mode="r")
        plain_z = np.load(plain_path, mmap_mode="r")
    else:
        target_tmp = target_path.with_suffix(".npy.partial")
        plain_tmp = plain_path.with_suffix(".npy.partial")
        z = np.lib.format.open_memmap(target_tmp, mode="w+", dtype=np.float32, shape=(len(starts), 32))
        plain = np.lib.format.open_memmap(plain_tmp, mode="w+", dtype=np.float32, shape=(len(starts), 32))
        with torch.no_grad():
            for lo in range(0, len(starts), 2048):
                hi = min(lo + 2048, len(starts))
                ids, ups, cfs = token_batch(states, starts[lo:hi], device)
                tokens = teacher.deck_tokens(ids, ups, cfs)
                mask = ids >= 0
                z[lo:hi] = teacher.deck_encode(ids, ups, cfs).float().cpu().numpy()
                count = mask.sum(1, keepdim=True).clamp_min(1)
                plain[lo:hi] = ((tokens * mask.unsqueeze(-1)).sum(1) / count).float().cpu().numpy()
                if hi % 100_000 < 2048:
                    print(f"teacher-target groups={hi:,}/{len(starts):,}", flush=True)
        z.flush(); plain.flush()
        del z, plain
        target_tmp.replace(target_path)
        plain_tmp.replace(plain_path)
        target_manifest = {**group_binding, "teacher_z_sha256": sha256(target_path),
                           "plain_mean_sha256": sha256(plain_path)}
        atomic_json(target_manifest_path, target_manifest)
        teacher_z = np.load(target_path, mmap_mode="r")
        plain_z = np.load(plain_path, mmap_mode="r")

    train_ids = np.flatnonzero(train_mask)
    val_ids = np.flatnonzero(val_mask)
    plain_metrics = representation_metrics(plain_z[val_ids], teacher_z[val_ids])
    torch.manual_seed(0)
    torch.cuda.manual_seed_all(0)
    student = ContextualDeck().to(device)
    params = sum(parameter.numel() for parameter in student.parameters() if parameter.requires_grad)
    if params != 3200 or len(student.state_dict()) != 6:
        raise ValueError(f"contextual block inventory differs: params={params}, tensors={len(student.state_dict())}")
    optimizer = torch.optim.AdamW(student.parameters(), lr=1e-3, weight_decay=1e-4)
    rng = np.random.default_rng(0)
    history = []
    start = time.perf_counter()
    for epoch in range(1, EPOCHS + 1):
        student.train()
        permutation = rng.permutation(train_ids)
        total_loss = 0.0
        seen = 0
        for lo in range(0, len(permutation), BATCH_GROUPS):
            group_ids = permutation[lo:lo + BATCH_GROUPS]
            ids, ups, cfs = token_batch(states, starts[group_ids], device)
            with torch.no_grad():
                tokens = teacher.deck_tokens(ids, ups, cfs)
            mask = ids >= 0
            target = torch.as_tensor(np.asarray(teacher_z[group_ids]), device=device, dtype=torch.float32)
            pred = student(tokens, mask)
            loss = F.mse_loss(pred, target)
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            total_loss += float(loss.detach()) * len(group_ids)
            seen += len(group_ids)
        record = {"epoch": epoch, "train_representation_mse": total_loss / max(seen, 1)}
        if epoch in (1, 5, 10, 15, 20, 25, 30):
            student.eval()
            predicted = np.empty((len(val_ids), 32), dtype=np.float32)
            with torch.no_grad():
                for lo in range(0, len(val_ids), 4096):
                    ids0 = val_ids[lo:lo + 4096]
                    ids, ups, cfs = token_batch(states, starts[ids0], device)
                    tokens = teacher.deck_tokens(ids, ups, cfs)
                    predicted[lo:lo + len(ids0)] = student(tokens, ids >= 0).float().cpu().numpy()
            record["validation"] = representation_metrics(predicted, teacher_z[val_ids])
        history.append(record)
        print(json.dumps({"epoch": epoch, "train_mse": record["train_representation_mse"],
                          "validation": record.get("validation")}, sort_keys=True), flush=True)

    student.eval()
    teacher_state = {k: v.detach().cpu().clone() for k, v in checkpoint["state_dict"].items()}
    combined = dict(teacher_state)
    contextual_state = {f"contextDeck.{k}": v.detach().cpu().clone()
                        for k, v in student.state_dict().items()}
    combined.update(contextual_state)
    if len(combined) != 121 or len(contextual_state) != 6:
        raise ValueError("assembled student must contain exactly 115+6 tensors")
    if any(not torch.equal(teacher_state[k], combined[k]) for k in teacher_state):
        raise ValueError("assembled student modified a frozen teacher tensor")
    student_path = args.out / "contextual_student_frozen.pt"
    if student_path.exists():
        raise FileExistsError(f"refusing to overwrite frozen checkpoint: {student_path}")
    checkpoint_out = {"state_dict": combined,
                      "teacher_state_dict": teacher_state,
                      "contextual_deck_state_dict": {k.removeprefix("contextDeck."): v
                                                       for k, v in contextual_state.items()},
                      "teacher_sha256": TEACHER_SHA256,
                      "native_sha256": NATIVE_SHA256,
                      "corpus_sha256": CORPUS_SHA256,
                      "split_sha256": SPLIT_SHA256,
                      "trace_gzip_sha256": TRACE_GZIP_SHA256,
                      "state_cache_layout": STATE_CACHE_LAYOUT_VERSION,
                      "state_cache_sha256": state_manifest["state_cache_sha256"],
                      "state_cache_layout": STATE_CACHE_LAYOUT_VERSION,
                      "teacher_targets_sha256": target_manifest["teacher_z_sha256"],
                      "python_native_parity": parity,
                      "model_seed": 0, "epoch": EPOCHS,
                      "optimizer": {"name": "AdamW", "lr": 1e-3, "weight_decay": 1e-4},
                      "batch_groups": BATCH_GROUPS, "representation_loss_only": True,
                      "policy_or_q_loss": False, "end_to_end_finetuning": False,
                      "trainable_parameter_count": params,
                      "architecture": "mean token context -> Linear(64,32) -> GELU -> Linear(32,32); LayerNorm(t_i + delta_i); valid-token mean",
                      "history": history}
    tmp_checkpoint = student_path.with_suffix(".pt.partial")
    torch.save(checkpoint_out, tmp_checkpoint)
    tmp_checkpoint.replace(student_path)
    elapsed = time.perf_counter() - start
    final_metrics = history[-1]["validation"]
    run = {"version": "contextual-deck-repr-deployed42-retrained-v1",
           "input_hashes": actual,
           "python_native_parity": parity,
           "artifacts": {"state_cache": str(state_path),
                         "state_cache_sha256": state_manifest["state_cache_sha256"],
                         "state_cache_layout": STATE_CACHE_LAYOUT_VERSION,
                         "teacher_targets_sha256": target_manifest["teacher_z_sha256"],
                         "plain_mean_targets_sha256": target_manifest["plain_mean_sha256"],
                         "frozen_student_checkpoint": str(student_path),
                         "frozen_student_checkpoint_sha256": sha256(student_path),
                         "training_script_sha256": sha256(Path(__file__))},
           "split": {"train_seeds": len(train_seeds), "validation_seeds": len(val_seeds),
                     "groups_total": len(starts), "groups_train": len(train_ids),
                     "groups_validation": len(val_ids)},
           "recipe": {"seed": 0, "optimizer": "AdamW", "lr": 1e-3,
                      "weight_decay": 1e-4, "batch_groups": BATCH_GROUPS,
                      "max_epochs": EPOCHS, "representation_mse_only": True,
                      "policy_or_q_loss": False, "end_to_end_finetuning": False},
           "architecture": {"trainable_parameters": params,
                            "trainable_tensors": sorted(contextual_state),
                            "teacher_tensors": 115, "teacher_tensor_equality": "all exact",
                            "fc1": "64->32", "activation": "GELU", "fc2": "32->32",
                            "residual": "LayerNorm(t_i + delta_i), eps=1e-5",
                            "pool": "valid-token mean; zero for empty deck"},
           "plain_mean_validation": plain_metrics,
           "training_history": history,
           "final_validation_representation": final_metrics,
           "training_wall_seconds": elapsed,
           "capture_or_gameplay_seeds_collected": 0}
    atomic_json(args.out / "retraining_result.json", run)
    print(json.dumps(run, indent=2, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
