#!/usr/bin/env python3
"""Replay the historical Tier-B source-policy screen for a frozen student."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from strategic_tok_net import MAXD, MAXP, MAXR, NGLOB, Net  # noqa: E402
from retrain_ooc_contextual_student import (  # noqa: E402
    CORPUS_SHA256, NATIVE_SHA256, NFILE, NROWS, SPLIT_SHA256, TRACE_GZIP_SHA256,
    ContextualDeck, group_layout, sha256, token_batch,
)


SCREEN_NAMES = {1: "event", 2: "card_reward", 3: "boss_relic",
                4: "selector_upgrade", 5: "map", 6: "treasure",
                7: "rest", 8: "shop"}


class HybridTeacher(Net):
    """Frozen V4 policy head with an explicit deck-encoding override."""
    def __init__(self):
        super().__init__(rung=4, nprobes=0, transformer=False, nquants=0, ncross=0)
        self._z_override = None

    def deck_encode(self, ids, ups, cfs):
        if self._z_override is None:
            return super().deck_encode(ids, ups, cfs)
        return self._z_override


def parse_bits(value) -> int:
    text = str(value)
    return int(text[5:]) if text.startswith("bits=") else int(text)


def make_heldout(csv, raw_to_grouped, group_seed, group_dec, starts, sizes,
                 val_seeds, chunksize=200_000):
    n_groups = len(starts)
    group_for_row = np.repeat(np.arange(n_groups, dtype=np.int32), sizes)
    val_mask = np.isin(group_seed, val_seeds)
    eligible_candidate = val_mask & (sizes >= 2)
    label_count = np.zeros(n_groups, dtype=np.int32)
    keep_cols = ["seed", "decIdx", "screen", "action", "actionType", "c1", "c2", "c3",
                 "cand1", "cand2", "cand3", "labelWon", "labelHp"]
    selected = []
    raw_lo = 0
    for chunk in pd.read_csv(csv, usecols=keep_cols, dtype={"action": str}, chunksize=chunksize):
        raw_hi = raw_lo + len(chunk)
        grouped_rows = raw_to_grouped[raw_lo:raw_hi]
        gids = group_for_row[grouped_rows]
        keep = eligible_candidate[gids]
        if np.any(keep):
            q = (10.0 * chunk.labelWon.to_numpy(np.float32)
                 + chunk.labelHp.to_numpy(np.float32))
            valid = keep & np.isfinite(q)
            if valid.any():
                label_count += np.bincount(gids[valid], minlength=n_groups).astype(np.int32)
            part = chunk.loc[keep].copy()
            part["_group_id"] = gids[keep]
            part["_grouped_row"] = grouped_rows[keep]
            selected.append(part)
        raw_lo = raw_hi
        if raw_hi % 500_000 < len(chunk):
            print(f"source-policy input rows={raw_hi:,}/{NROWS:,}", flush=True)
    if raw_lo != NROWS:
        raise ValueError(f"source-policy CSV rows {raw_lo} != {NROWS}")
    group_ids = np.flatnonzero(eligible_candidate & (label_count >= 2)).astype(np.int64)
    if len(group_ids) != 100_314:
        raise ValueError(f"historical held-out eligible group count {len(group_ids)} != 100314")
    raw = pd.concat(selected, ignore_index=True)
    eligible_set = np.zeros(n_groups, dtype=bool)
    eligible_set[group_ids] = True
    raw = raw.loc[eligible_set[raw["_group_id"].to_numpy(np.int32)]].copy()
    raw.sort_values("_grouped_row", kind="stable", inplace=True, ignore_index=True)
    if len(raw) != 567_642:
        raise ValueError(f"historical source candidate row count {len(raw)} != 567642")
    if not np.array_equal(raw.seed.to_numpy(np.int32), group_seed[raw["_group_id"].to_numpy(np.int32)]):
        raise ValueError("raw candidate seeds do not match their grouped source states")
    if not np.array_equal(raw.decIdx.to_numpy(np.int32), group_dec[raw["_group_id"].to_numpy(np.int32)]):
        raise ValueError("raw candidate decision indices do not match grouped source states")

    # Tier-B candidate rows retain stable raw-row order within the canonical
    # (seed, decIdx) group. Reconstruct the same 8-field identity used by the
    # historical sealed source-policy evaluator.
    raw["_bits"] = [parse_bits(v) for v in raw.action]
    raw["_atype"] = np.clip(raw.actionType.to_numpy(np.int64) + 1, 0, 15)
    sig_cols = []
    raw["_sig0"] = raw["_bits"].astype(str)
    raw["_sig1"] = raw["_atype"].astype(str)
    sig_cols.extend(["_sig0", "_sig1"])
    for i, col in enumerate(("c1", "c2", "c3", "cand1", "cand2", "cand3"), start=2):
        name = f"_sig{i}"
        raw[name] = np.clip(raw[col].to_numpy(np.int64) + 1, 0, 511).astype(str)
        sig_cols.append(name)
    raw["_signature"] = raw[sig_cols].astype(str).agg(":".join, axis=1)
    grouped = raw.groupby("_group_id", sort=True)
    signature = grouped["_signature"].agg("|".join)
    screen = grouped["screen"].first()
    seed = pd.Series(group_seed, index=np.arange(n_groups, dtype=np.int64)).loc[group_ids]
    dec = pd.Series(group_dec, index=np.arange(n_groups, dtype=np.int64)).loc[group_ids]
    held = pd.DataFrame({"group_id": group_ids,
                         "seed": seed.to_numpy(np.int32),
                         "decIdx": dec.to_numpy(np.int32),
                         "screen": screen.reindex(group_ids).to_numpy(np.int16),
                         "nCand": sizes[group_ids].astype(np.int32),
                         "candidateIds": signature.reindex(group_ids).to_numpy(str)})
    if np.any(grouped["screen"].nunique().to_numpy() != 1):
        raise ValueError("source screen differs within a decision group")
    if not np.array_equal(held.nCand.to_numpy(np.int32),
                          raw.groupby("_group_id", sort=True).size().reindex(group_ids).to_numpy(np.int32)):
        raise ValueError("candidate identity width differs from grouped source row counts")
    return held, group_ids


def predict_heldout(model, states, starts, held, group_ids, z_all=None):
    device = next(model.parameters()).device
    z_group = z_all[group_ids] if z_all is not None else None
    widths = held.nCand.to_numpy(np.int32)
    offsets = np.concatenate(([0], np.cumsum(widths, dtype=np.int64)))
    nrows = int(offsets[-1])
    row_gids = np.repeat(np.arange(len(held), dtype=np.int32), widths)
    bits = np.empty(nrows, np.int64)
    atype = np.empty(nrows, np.int64)
    cats = np.empty((nrows, 6), np.int64)
    for gi, text in enumerate(held.candidateIds):
        lo, hi = int(offsets[gi]), int(offsets[gi + 1])
        sigs = [[int(v) for v in sig.split(":")] for sig in text.split("|")]
        if len(sigs) != hi - lo or any(len(sig) != 8 for sig in sigs):
            raise ValueError(f"malformed Tier-B candidate signature at held-out group {gi}")
        array = np.asarray(sigs, dtype=np.int64)
        bits[lo:hi], atype[lo:hi], cats[lo:hi] = array[:, 0], array[:, 1], array[:, 2:]
    screen = np.repeat(held.screen.to_numpy(np.int64), widths)
    reps = starts[group_ids]
    gold = np.asarray(states[reps, 5], dtype=np.float32)
    gold_rows = np.repeat(gold, widths)
    raw_type = atype - 1
    candidate1, candidate2 = cats[:, 3] - 1, cats[:, 4] - 1
    ent_type = np.zeros(nrows, np.int64)
    ent_id = np.full(nrows, -1, np.int64)
    gold_ge = np.zeros(nrows, np.float32)
    m = np.isin(screen, (2, 8)) & (raw_type == 0)
    ent_type[m] = 1; ent_id[m] = candidate1[m]
    m = np.isin(screen, (2, 8)) & (raw_type == 4)
    ent_type[m] = 2; ent_id[m] = candidate1[m]
    m = np.isin(screen, (2, 8)) & (raw_type == 3)
    ent_type[m] = 3; ent_id[m] = candidate1[m]
    m = screen == 4
    ent_type[m] = 1; ent_id[m] = candidate1[m]
    m = (screen == 2) & (raw_type == 1) & (candidate1 >= 0)
    gold_ge[m] = (gold_rows[m] >= candidate1[m]).astype(np.float32)
    m = (screen == 8) & (candidate2 >= 0)
    gold_ge[m] = (gold_rows[m] >= candidate2[m]).astype(np.float32)
    mean = torch.as_tensor(model._experiment_mean, device=device)
    inv = torch.as_tensor(model._experiment_inv, device=device)
    policy = np.empty(nrows, np.float32)
    model.eval()
    with torch.no_grad():
        for lo in range(0, nrows, 4096):
            hi = min(lo + 4096, nrows)
            local_group = row_gids[lo:hi]
            state_rows = starts[group_ids[local_group]]
            x = torch.as_tensor(np.asarray(states[state_rows]), device=device, dtype=torch.float32)
            g = torch.clamp((x[:, :NGLOB] - mean) * inv, -8, 8)
            dk_id = x[:, NGLOB:NGLOB + MAXD * 3:3].long()
            dk_up = x[:, NGLOB + 1:NGLOB + MAXD * 3:3].long()
            dk_cf = x[:, NGLOB + 2:NGLOB + MAXD * 3:3]
            rel_start = NGLOB + MAXD * 3
            rl_id = x[:, rel_start:rel_start + MAXR * 2:2].long()
            rl_df = x[:, rel_start + 1:rel_start + MAXR * 2:2]
            pot_start = rel_start + MAXR * 2
            pt_id = x[:, pot_start:NFILE:2].long()
            pt_cf = x[:, pot_start + 1:NFILE:2]
            bit_tensor = torch.as_tensor(bits[lo:hi], device=device, dtype=torch.int64)
            bit_index = torch.arange(32, device=device, dtype=torch.int64)
            bit_features = ((bit_tensor[:, None] >> bit_index) & 1).float()
            cat_tensor = torch.as_tensor(cats[lo:hi], device=device, dtype=torch.long)
            atype_tensor = torch.as_tensor(atype[lo:hi], device=device, dtype=torch.long)
            screen_tensor = torch.as_tensor(screen[lo:hi], device=device, dtype=torch.long)
            entity_type_tensor = torch.as_tensor(ent_type[lo:hi], device=device, dtype=torch.long)
            entity_id_tensor = torch.as_tensor(ent_id[lo:hi], device=device, dtype=torch.long)
            gold_ge_tensor = torch.as_tensor(gold_ge[lo:hi], device=device)
            if z_group is None:
                model._z_override = None
            else:
                model._z_override = torch.as_tensor(z_group[local_group], device=device)
            logits, _, _, _ = model(g, dk_id, dk_up, dk_cf, rl_id, rl_df, pt_id, pt_cf,
                                    bit_features, cat_tensor, atype_tensor, screen_tensor,
                                    entity_type_tensor, entity_id_tensor, gold_ge_tensor)
            policy[lo:hi] = logits.float().cpu().numpy()
    model._z_override = None
    return [policy[int(offsets[i]):int(offsets[i + 1])] for i in range(len(held))]


def softmax(logits):
    x = np.asarray(logits, dtype=np.float64)
    x = x - np.max(x)
    p = np.exp(x)
    return p / p.sum()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--split", type=Path, required=True)
    parser.add_argument("--teacher", type=Path, required=True)
    parser.add_argument("--student", type=Path, required=True)
    parser.add_argument("--state-cache", type=Path, required=True)
    parser.add_argument("--state-manifest", type=Path, required=True)
    parser.add_argument("--target-cache", type=Path, required=True)
    parser.add_argument("--target-manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    for p in (args.csv, args.split, args.teacher, args.student, args.state_cache,
              args.state_manifest, args.target_cache, args.target_manifest):
        if not p.is_file():
            raise FileNotFoundError(p)
    input_hashes = {"corpus_sha256": sha256(args.csv), "split_sha256": sha256(args.split),
                    "teacher_sha256": sha256(args.teacher), "student_sha256": sha256(args.student),
                    "state_cache_sha256": sha256(args.state_cache),
                    "target_cache_sha256": sha256(args.target_cache)}
    if input_hashes["corpus_sha256"] != CORPUS_SHA256 or input_hashes["split_sha256"] != SPLIT_SHA256:
        raise ValueError("source policy corpus/split hash changed")
    if input_hashes["teacher_sha256"] != "5bc14fb437131d4bdc531ea775e22eca1f6834976d4670ec0aabb2fb14b735b8":
        raise ValueError("source policy teacher checkpoint hash changed")
    manifest = json.loads(args.state_manifest.read_text())
    if (manifest.get("layout_version") != "raw-to-grouped-v2"
            or manifest.get("corpus_sha256") != CORPUS_SHA256
            or manifest.get("state_cache_sha256") != input_hashes["state_cache_sha256"]):
        raise ValueError("source policy state-cache manifest mismatch")
    if args.state_cache.stat().st_size != NROWS * NFILE * 2:
        raise ValueError("source policy state-cache size mismatch")
    target_manifest = json.loads(args.target_manifest.read_text())
    if (target_manifest.get("teacher_z_sha256") != input_hashes["target_cache_sha256"]
            or target_manifest.get("teacher_sha256") != input_hashes["teacher_sha256"]
            or target_manifest.get("native_sha256") != NATIVE_SHA256
            or target_manifest.get("corpus_sha256") != CORPUS_SHA256
            or target_manifest.get("split_sha256") != SPLIT_SHA256
            or target_manifest.get("state_cache_sha256") != input_hashes["state_cache_sha256"]
            or target_manifest.get("token_cache_layout") != "raw-to-grouped-v2"):
        raise ValueError("source-policy attention target cache binding differs")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for full held-out source-policy replay")
    device = "cuda"
    torch.set_num_threads(4)

    checkpoint = torch.load(args.teacher, map_location="cpu", weights_only=False)
    if checkpoint.get("native_sha256") != NATIVE_SHA256:
        raise ValueError("source-policy teacher checkpoint is not bound to the tracked native artifact")
    student_ckpt = torch.load(args.student, map_location="cpu", weights_only=False)
    teacher_sd = checkpoint["state_dict"]
    student_sd = student_ckpt["state_dict"]
    shared = set(teacher_sd) & set(student_sd)
    extra = sorted(set(student_sd) - set(teacher_sd))
    teacher_trace_preflight = (student_ckpt.get("python_native_parity", {})
                               .get("authoritative_captured_native_trace_preflight", {}))
    trace_parity = teacher_trace_preflight.get("python_native_teacher_preflight", {})
    if (len(teacher_sd) != 115 or len(shared) != 115 or len(extra) != 6
            or student_ckpt.get("trainable_parameter_count") != 3200
            or student_ckpt.get("epoch") != 30
            or student_ckpt.get("model_seed") != 0
            or student_ckpt.get("representation_loss_only") is not True
            or student_ckpt.get("policy_or_q_loss") is not False
            or student_ckpt.get("end_to_end_finetuning") is not False
            or student_ckpt.get("optimizer") != {"name": "AdamW", "lr": 1e-3, "weight_decay": 1e-4}
            or student_ckpt.get("batch_groups") != 4096
            or student_ckpt.get("teacher_sha256") != input_hashes["teacher_sha256"]
            or student_ckpt.get("native_sha256") != NATIVE_SHA256
            or student_ckpt.get("corpus_sha256") != CORPUS_SHA256
            or student_ckpt.get("split_sha256") != SPLIT_SHA256
            or student_ckpt.get("trace_gzip_sha256") != TRACE_GZIP_SHA256
            or student_ckpt.get("state_cache_layout") != "raw-to-grouped-v2"
            or student_ckpt.get("state_cache_sha256") != input_hashes["state_cache_sha256"]
            or student_ckpt.get("teacher_targets_sha256") != input_hashes["target_cache_sha256"]
            or teacher_trace_preflight.get("result") != "PASS"
            or trace_parity.get("max_abs_python_vs_captured_native_source_logit", 1.0) >= 1e-4
            or trace_parity.get("source_argmax_parity", 0.0) != 1.0
            or trace_parity.get("max_abs_python_vs_captured_candidate_logit", 1.0) >= 1e-4
            or trace_parity.get("max_abs_rebuilt_teacher_final_prior", 1.0) >= 1e-4):
        raise ValueError("frozen student tensor/parameter inventory differs from 115+6/3200")
    if any(not torch.equal(teacher_sd[k], student_sd[k]) for k in teacher_sd):
        raise ValueError("frozen student teacher tensors differ")
    if not all(k.startswith("contextDeck.") for k in extra):
        raise ValueError(f"unexpected additional tensor keys: {extra}")
    context = ContextualDeck().to(device)
    context_state = {k.removeprefix("contextDeck."): student_sd[k] for k in extra}
    context.load_state_dict(context_state, strict=True)
    context.eval()
    teacher = HybridTeacher().to(device)
    teacher.load_state_dict(teacher_sd, strict=True)
    teacher.eval()
    for parameter in teacher.parameters():
        parameter.requires_grad_(False)
    teacher._experiment_mean = checkpoint["mean"]
    teacher._experiment_inv = checkpoint["inv"]

    split = json.loads(args.split.read_text())
    val_seeds = np.asarray(split["val_seeds"], dtype=np.int32)
    raw_to_grouped, group_seed, group_dec, starts, sizes = group_layout(args.csv)
    held, group_ids = make_heldout(args.csv, raw_to_grouped, group_seed, group_dec,
                                   starts, sizes, val_seeds)
    states = np.memmap(args.state_cache, dtype=np.float16, mode="r", shape=(NROWS, NFILE))
    teacher_z = np.load(args.target_cache, mmap_mode="r")
    if teacher_z.shape != (len(starts), 32):
        raise ValueError("teacher target cache shape differs from grouped source states")

    # Verify the cached attention targets against direct attention on the first
    # 128 historical held-out groups before using them for either policy.
    bounded = min(128, len(held))
    direct = predict_heldout(teacher, states, starts, held.iloc[:bounded].reset_index(drop=True),
                             group_ids[:bounded], None)
    cached = predict_heldout(teacher, states, starts, held.iloc[:bounded].reset_index(drop=True),
                             group_ids[:bounded], teacher_z)
    max_cached_error = max(float(np.max(np.abs(a - b)))
                           for rows_a, rows_b in zip(direct, cached, strict=True)
                           for a, b in zip(rows_a, rows_b, strict=True))
    if max_cached_error > 1e-5:
        raise ValueError(f"cached teacher target replay differs on bounded subset: {max_cached_error}")

    unique_groups = np.unique(group_ids)
    student_z = np.zeros((len(starts), 32), dtype=np.float32)
    with torch.no_grad():
        for lo in range(0, len(unique_groups), 4096):
            gids = unique_groups[lo:lo + 4096]
            ids, ups, cfs = token_batch(states, starts[gids], device)
            token = teacher.deck_tokens(ids, ups, cfs)
            student_z[gids] = context(token, ids >= 0).float().cpu().numpy()
            if lo % 20_000 == 0:
                print(f"student deck encodings={min(lo + len(gids), len(unique_groups)):,}/{len(unique_groups):,}", flush=True)

    teacher_rows = predict_heldout(teacher, states, starts, held, group_ids, teacher_z)
    student_rows = predict_heldout(teacher, states, starts, held, group_ids, student_z)
    widths = held.nCand.to_numpy(np.int32)
    expected_source_rows = int(widths.sum())
    agree = np.empty(len(held), dtype=bool)
    tv = np.empty(len(held), dtype=np.float64)
    for i, (tlog, slog) in enumerate(zip(teacher_rows, student_rows, strict=True)):
        if len(tlog) != widths[i] or len(slog) != widths[i]:
            raise ValueError(f"source-policy candidate width differs at group {i}")
        agree[i] = int(np.argmax(tlog)) == int(np.argmax(slog))
        tp = np.exp(tlog.astype(np.float64) - np.max(tlog))
        tp /= tp.sum()
        sp = np.exp(slog.astype(np.float64) - np.max(slog))
        sp /= sp.sum()
        tv[i] = 0.5 * np.abs(tp - sp).sum()

    def metrics(indexes):
        ix = np.asarray(indexes, dtype=np.int64)
        if ix.size == 0:
            return {"groups": 0, "source_rows": 0}
        return {"groups": int(ix.size),
                "source_rows": int(widths[ix].sum()),
                "argmax_agreement": float(agree[ix].mean()),
                "tv_median": float(np.median(tv[ix])),
                "tv_p90": float(np.quantile(tv[ix], 0.9)),
                "tv_mean": float(tv[ix].mean()),
                "tv_max": float(tv[ix].max())}

    all_ix = np.arange(len(held), dtype=np.int64)
    screen_codes = held.screen.to_numpy(np.int16)
    by_screen = {name: metrics(np.flatnonzero(screen_codes == code))
                 for code, name in SCREEN_NAMES.items() if np.any(screen_codes == code)}
    overall = metrics(all_ix)
    critical_pass = all(by_screen.get(name, {}).get("argmax_agreement", 0.0) >= 0.90
                        and by_screen[name]["tv_median"] <= 0.05
                        and by_screen[name]["tv_p90"] <= 0.15
                        for name in ("card_reward", "shop"))
    gate = {"overall_argmax_ge_0_95": overall["argmax_agreement"] >= 0.95,
            "overall_median_tv_le_0_03": overall["tv_median"] <= 0.03,
            "overall_p90_tv_le_0_10": overall["tv_p90"] <= 0.10,
            "card_reward_and_shop_no_major_collapse": critical_pass}
    gate["pass"] = all(gate.values())
    result = {"version": "contextual-deployed42-source-policy-v1",
              "artifacts": {**input_hashes,
                            "native_teacher_sha256": NATIVE_SHA256,
                            "state_cache_layout": manifest["layout_version"],
                            "state_cache_manifest_sha256": sha256(args.state_manifest),
                            "target_cache_manifest_sha256": sha256(args.target_manifest),
                            "source_evaluator_sha256": sha256(Path(__file__))},
              "population": {"heldout_groups": int(len(held)),
                             "source_candidate_rows": expected_source_rows,
                             "bounded_teacher_target_replay_groups": bounded,
                             "bounded_teacher_target_replay_max_logit_error": max_cached_error},
              "overall": overall,
              "by_screen": by_screen,
              "gate": gate,
              "gate_policy": {"overall": "argmax >= 0.95; median TV <= 0.03; p90 TV <= 0.10",
                              "card_reward_and_shop_review_guard": "each argmax >= 0.90; median TV <= 0.05; p90 TV <= 0.15"},
              "historical_old_checkpoint_reference": {"argmax_agreement": 0.9795,
                                                       "tv_median": 0.00313,
                                                       "tv_p90": 0.03480,
                                                       "shop_argmax_agreement": 0.9386,
                                                       "card_reward_argmax_agreement": 0.9919},
              "interpretation": "source-action softmax at T=1 over Tier-B candidate rows; no semantic aggregation/multiplicity correction and no Q/policy training"}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
