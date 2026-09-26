#!/usr/bin/env python3
"""Evaluate the frozen contextual deck student on PR #329's captured priors."""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from strategic_tok_net import MAXD, MAXP, MAXR, NGLOB, Net  # noqa: E402
from retrain_ooc_contextual_student import (  # noqa: E402
    CORPUS_SHA256, NATIVE_SHA256, SPLIT_SHA256, TEACHER_SHA256, TRACE_GZIP_SHA256,
    ContextualDeck, sha256,
)


TRACE_GZIP_SHA256 = "192b623ca28887e7da646aca16efaecd041583261265e1af23b83a1eab958370"
TRACE_JSONL_SHA256 = "9f95592e9dfbf9b199dbdd81f1b4cae2e654e52a871c227c888ace47f7fb1cb1"
ELIGIBLE_ROWS = 11_474
UNIQUE_PRIORS = 6_317
SHOP_OCCURRENCES = 1_402
SOURCE_FIELDS = ("screen", "primitiveBits", "actionType", "cats",
                 "entityType", "entityId", "goldGePrice")
CANDIDATE_FIELDS = ("candidateId", "compoundSelector", "hasSemantic",
                    "primitiveBits", "priorSourceGroup", "semanticKey")


class HybridTeacher(Net):
    def __init__(self):
        super().__init__(rung=4, nprobes=0, transformer=False, nquants=0, ncross=0)
        self._z_override = None

    def deck_encode(self, ids, ups, cfs):
        if self._z_override is None:
            return super().deck_encode(ids, ups, cfs)
        return self._z_override


def canonical_payload(row):
    return [row["screenId"], row["priorTemperature"], row["tokenState"],
            [{k: source[k] for k in SOURCE_FIELDS} for source in row["sourcePrimitives"]],
            [{k: candidate[k] for k in CANDIDATE_FIELDS} for candidate in row["candidates"]]]


def record_key(row):
    payload = json.dumps(canonical_payload(row), sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_unique_trace(path: Path):
    digest = hashlib.sha256()
    eligible_count = 0
    shop_count = 0
    trace_record_count = 0
    singleton_count = 0
    uncovered_count = 0
    uniform_count = 0
    captured_raw_formula_error = 0.0
    captured_final_prior_formula_error = 0.0
    unique = {}
    occurrence_counts = Counter()
    with gzip.open(path, "rb") as stream:
        for line_number, line in enumerate(stream, start=1):
            digest.update(line)
            if not line.strip():
                continue
            row = json.loads(line)
            trace_record_count += 1
            if row.get("schemaVersion") != 1:
                raise ValueError(f"unsupported trace schema version at line {line_number}")
            singleton_count += int(row.get("singleton") is True)
            uncovered_count += int(row.get("sourcePriorCovered") is not True)
            uniform_count += int(row.get("uniformPrior") is True)
            if not (row.get("sourcePriorCovered") is True
                    and row.get("singleton") is False
                    and row.get("uniformPrior") is False):
                continue
            eligible_count += 1
            if float(row["priorTemperature"]) != 1.0:
                raise ValueError(f"semantic-prior trace temperature is not exactly 1.0 at line {line_number}")
            if row.get("screen") == "shop":
                shop_count += 1
            if row.get("candidateCount") != len(row.get("candidates", [])):
                raise ValueError(f"trace candidate count mismatch at line {line_number}")
            candidate_ids = [int(candidate["candidateId"]) for candidate in row["candidates"]]
            if len(set(candidate_ids)) != len(candidate_ids) or candidate_ids != sorted(candidate_ids):
                raise ValueError(f"trace candidate IDs are duplicated or out of order at line {line_number}")
            sources = row.get("sourcePrimitives", [])
            if len({int(source["primitiveBits"]) for source in sources}) != len(sources):
                raise ValueError(f"trace source primitive bits are duplicated at line {line_number}")
            if any("teacherSourceLogit" not in source for source in sources):
                raise ValueError(f"trace source primitive lacks its captured teacher logit at line {line_number}")
            if any(len(source.get("cats", [])) != 6 for source in sources):
                raise ValueError(f"trace source categorical feature width differs from six at line {line_number}")
            if any(int(source["screen"]) != int(row["screenId"]) for source in sources):
                raise ValueError(f"source feature screen differs from prior context at line {line_number}")
            n_candidates = int(row["candidateCount"])
            if any(len(row.get(field, [])) != n_candidates for field in (
                    "teacherCandidateLogits", "teacherNormalizedPrior", "teacherRawPriorWeights")):
                raise ValueError(f"captured teacher candidate-output width mismatch at line {line_number}")
            captured_probabilities = np.asarray(row["teacherNormalizedPrior"], dtype=np.float64)
            captured_logits = np.asarray(row["teacherCandidateLogits"], dtype=np.float64)
            captured_raw = np.asarray(row["teacherRawPriorWeights"], dtype=np.float64)
            source_logits = np.asarray([source["teacherSourceLogit"] for source in sources], dtype=np.float64)
            if (not np.isfinite(captured_raw).all()
                    or not np.isfinite(source_logits).all()
                    or not np.isfinite(captured_probabilities).all()
                    or not np.isfinite(captured_logits).all()
                    or abs(float(captured_probabilities.sum()) - 1.0) > 1e-10):
                raise ValueError(f"captured teacher candidate outputs are invalid at line {line_number}")
            rebuilt_raw, rebuilt_prior = semantic_prior(
                captured_logits, row["candidates"], float(row["priorTemperature"]))
            captured_raw_formula_error = max(
                captured_raw_formula_error,
                float(np.max(np.abs(rebuilt_raw - captured_raw), initial=0.0)))
            captured_final_prior_formula_error = max(
                captured_final_prior_formula_error,
                float(np.max(np.abs(rebuilt_prior - captured_probabilities), initial=0.0)))
            key = record_key(row)
            occurrence_counts[key] += 1
            existing = unique.get(key)
            if existing is None:
                unique[key] = row
            elif ([s["teacherSourceLogit"] for s in existing["sourcePrimitives"]]
                  != [s["teacherSourceLogit"] for s in row["sourcePrimitives"]]
                  or existing.get("teacherNormalizedPrior") != row.get("teacherNormalizedPrior")
                  or existing.get("teacherRawPriorWeights") != row.get("teacherRawPriorWeights")
                  or existing.get("teacherCandidateLogits") != row.get("teacherCandidateLogits")):
                raise ValueError(f"duplicate canonical prior has different captured teacher outputs: {key}")
    actual_raw_sha = digest.hexdigest()
    if actual_raw_sha != TRACE_JSONL_SHA256:
        raise ValueError(f"decompressed trace SHA mismatch: {actual_raw_sha}")
    if eligible_count != ELIGIBLE_ROWS or len(unique) != UNIQUE_PRIORS or shop_count != SHOP_OCCURRENCES:
        raise ValueError(f"trace census mismatch: eligible={eligible_count}, unique={len(unique)}, shop={shop_count}")
    if captured_raw_formula_error > 1e-10 or captured_final_prior_formula_error > 1e-10:
        raise ValueError("captured teacher candidate logits do not reproduce raw/normalized trace priors")
    return list(unique.items()), occurrence_counts, {
        "trace_records": trace_record_count,
        "singleton_trace_records": singleton_count,
        "source_prior_uncovered_records": uncovered_count,
        "uniform_prior_records": uniform_count,
        "eligible_trace_occurrences": eligible_count,
        "unique_canonical_priors": len(unique),
        "shop_trace_occurrences": shop_count,
        "unique_shop_priors": sum(row.get("screen") == "shop" for row in unique.values()),
        "max_captured_raw_weight_formula_error": captured_raw_formula_error,
        "max_captured_final_prior_formula_error": captured_final_prior_formula_error,
        "decompressed_trace_sha256": actual_raw_sha,
    }


def load_native_predictions(path: Path, expected_count: int):
    opener = gzip.open if path.suffix == ".gz" else open
    predictions = []
    with opener(path, "rt", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            prediction = json.loads(line)
            required = ("priorKey", "deckRepresentation", "sourceLogits",
                        "candidateLogits", "normalizedPrior")
            if any(name not in prediction for name in required):
                raise ValueError(f"native prediction is missing fields at line {line_number}")
            predictions.append(prediction)
    if len(predictions) != expected_count:
        raise ValueError(f"native prediction count {len(predictions)} != {expected_count}")
    return predictions


def pack_token_state(state):
    glob = np.asarray(state["glob"], dtype=np.float32)
    if glob.shape != (NGLOB,):
        raise ValueError(f"captured global input shape {glob.shape} != ({NGLOB},)")
    deck = state["deck"]["tokens"]
    relic = state["relic"]["tokens"]
    potion = state["potion"]["tokens"]
    if (len(deck) != int(state["deck"]["nDk"]) or len(deck) > MAXD
            or len(relic) != int(state["relic"]["nRl"]) or len(relic) > MAXR
            or len(potion) != int(state["potion"]["nPt"]) or len(potion) > MAXP):
        raise ValueError("captured token counts differ from token payload lengths")
    dk_id = np.full((MAXD,), -1, dtype=np.int64)
    dk_up = np.zeros((MAXD,), dtype=np.int64)
    dk_cf = np.zeros((MAXD,), dtype=np.float32)
    for i, (card_id, upgraded, count) in enumerate(deck):
        dk_id[i] = int(card_id); dk_up[i] = int(upgraded)
        dk_cf[i] = min(float(count), 9.0) / 9.0
    rl_id = np.full((MAXR,), -1, dtype=np.int64)
    rl_df = np.zeros((MAXR,), dtype=np.float32)
    for i, (relic_id, value) in enumerate(relic):
        rl_id[i] = int(relic_id); rl_df[i] = min(float(value) - 1.0, 9.0) / 9.0
    pt_id = np.full((MAXP,), -1, dtype=np.int64)
    pt_cf = np.zeros((MAXP,), dtype=np.float32)
    for i, (potion_id, value) in enumerate(potion):
        pt_id[i] = int(potion_id); pt_cf[i] = min(float(value), 9.0) / 9.0
    return glob, dk_id, dk_up, dk_cf, rl_id, rl_df, pt_id, pt_cf


def encode_teacher_trace_states(model, rows, device, batch_size=256):
    n = len(rows)
    z_teacher = np.empty((n, 32), dtype=np.float32)
    packed = [pack_token_state(row["tokenState"]) for row in rows]
    with torch.no_grad():
        for lo in range(0, n, batch_size):
            hi = min(lo + batch_size, n)
            values = packed[lo:hi]
            glob = torch.as_tensor(np.stack([x[0] for x in values]), device=device)
            dk_id = torch.as_tensor(np.stack([x[1] for x in values]), device=device)
            dk_up = torch.as_tensor(np.stack([x[2] for x in values]), device=device)
            dk_cf = torch.as_tensor(np.stack([x[3] for x in values]), device=device)
            mask = dk_id >= 0
            z_teacher[lo:hi] = model.deck_encode(dk_id, dk_up, dk_cf).float().cpu().numpy()
            if hi % 1024 < batch_size:
                print(f"trace deck encodings={hi:,}/{n:,}", flush=True)
    return packed, z_teacher


def encode_student_trace_states(model, context, packed, device, batch_size=256):
    n = len(packed)
    z_student = np.empty((n, 32), dtype=np.float32)
    with torch.no_grad():
        for lo in range(0, n, batch_size):
            hi = min(lo + batch_size, n)
            values = packed[lo:hi]
            dk_id = torch.as_tensor(np.stack([x[1] for x in values]), device=device)
            dk_up = torch.as_tensor(np.stack([x[2] for x in values]), device=device)
            dk_cf = torch.as_tensor(np.stack([x[3] for x in values]), device=device)
            tokens = model.deck_tokens(dk_id, dk_up, dk_cf)
            z_student[lo:hi] = context(tokens, dk_id >= 0).float().cpu().numpy()
            if hi % 1024 < batch_size:
                print(f"contextual student deck encodings={hi:,}/{n:,}", flush=True)
    return z_student


def forward_sources(model, packed, z_by_prior, records, device, mean, inv, batch_size=4096):
    prior_index = []
    sources = []
    for i, (_, row) in enumerate(records):
        for source in row["sourcePrimitives"]:
            prior_index.append(i)
            sources.append(source)
    n = len(sources)
    logits = np.empty(n, dtype=np.float64)
    pi = np.asarray(prior_index, dtype=np.int32)
    glob_by_prior = np.stack([x[0] for x in packed])
    dk_id_by_prior = np.stack([x[1] for x in packed])
    dk_up_by_prior = np.stack([x[2] for x in packed])
    dk_cf_by_prior = np.stack([x[3] for x in packed])
    rl_id_by_prior = np.stack([x[4] for x in packed])
    rl_df_by_prior = np.stack([x[5] for x in packed])
    pt_id_by_prior = np.stack([x[6] for x in packed])
    pt_cf_by_prior = np.stack([x[7] for x in packed])
    source_bits = np.asarray([int(s["primitiveBits"]) for s in sources], dtype=np.int64)
    bits_index = torch.arange(32, device=device, dtype=torch.int64)
    source_cats = np.asarray([s["cats"] for s in sources], dtype=np.int64)
    source_atype = np.asarray([s["actionType"] for s in sources], dtype=np.int64)
    source_screen = np.asarray([s["screen"] for s in sources], dtype=np.int64)
    source_enttype = np.asarray([s["entityType"] for s in sources], dtype=np.int64)
    source_entid = np.asarray([s["entityId"] for s in sources], dtype=np.int64)
    source_price = np.asarray([s["goldGePrice"] for s in sources], dtype=np.float32)
    norm_mean = torch.as_tensor(mean, device=device, dtype=torch.float32)
    norm_inv = torch.as_tensor(inv, device=device, dtype=torch.float32)
    model.eval()
    with torch.no_grad():
        for lo in range(0, n, batch_size):
            hi = min(lo + batch_size, n)
            indexes = pi[lo:hi]
            glob = torch.as_tensor(glob_by_prior[indexes], device=device, dtype=torch.float32)
            x = torch.clamp((glob - norm_mean) * norm_inv, -8, 8)
            dk_id = torch.as_tensor(dk_id_by_prior[indexes], device=device, dtype=torch.long)
            dk_up = torch.as_tensor(dk_up_by_prior[indexes], device=device, dtype=torch.long)
            dk_cf = torch.as_tensor(dk_cf_by_prior[indexes], device=device, dtype=torch.float32)
            rl_id = torch.as_tensor(rl_id_by_prior[indexes], device=device, dtype=torch.long)
            rl_df = torch.as_tensor(rl_df_by_prior[indexes], device=device, dtype=torch.float32)
            pt_id = torch.as_tensor(pt_id_by_prior[indexes], device=device, dtype=torch.long)
            pt_cf = torch.as_tensor(pt_cf_by_prior[indexes], device=device, dtype=torch.float32)
            bit = torch.as_tensor(source_bits[lo:hi], device=device, dtype=torch.int64)
            bit_features = ((bit[:, None] >> bits_index) & 1).float()
            cat = torch.as_tensor(np.clip(source_cats[lo:hi] + 1, 0, 511), device=device, dtype=torch.long)
            atype = torch.as_tensor(np.clip(source_atype[lo:hi] + 1, 0, 15), device=device, dtype=torch.long)
            screen = torch.as_tensor(source_screen[lo:hi], device=device, dtype=torch.long)
            enttype = torch.as_tensor(source_enttype[lo:hi], device=device, dtype=torch.long)
            entid = torch.as_tensor(source_entid[lo:hi], device=device, dtype=torch.long)
            price = torch.as_tensor(source_price[lo:hi], device=device, dtype=torch.float32)
            model._z_override = torch.as_tensor(z_by_prior[indexes], device=device, dtype=torch.float32)
            policy, _, _, _ = model(x, dk_id, dk_up, dk_cf, rl_id, rl_df,
                                    pt_id, pt_cf, bit_features, cat, atype, screen,
                                    enttype, entid, price)
            logits[lo:hi] = policy.double().cpu().numpy()
            if hi % 20_000 < batch_size:
                print(f"trace source forwards={hi:,}/{n:,}", flush=True)
    model._z_override = None
    row_values = [[] for _ in records]
    row_index = 0
    for i, (_, row) in enumerate(records):
        count = len(row["sourcePrimitives"])
        row_values[i] = logits[row_index:row_index + count]
        row_index += count
    if row_index != n:
        raise AssertionError("source-logit reconstruction indexing mismatch")
    return row_values, n


def candidate_logits(row, source_logits):
    source_index = {int(source["primitiveBits"]): i
                    for i, source in enumerate(row["sourcePrimitives"])}
    if len(source_index) != len(row["sourcePrimitives"]):
        raise ValueError("trace source primitive identities are not unique")
    values = []
    for candidate in row["candidates"]:
        group = candidate.get("priorSourceGroup", [])
        if group:
            try:
                indexes = [source_index[int(bits)] for bits in group]
            except KeyError as error:
                raise ValueError(f"candidate source group refers to missing primitive {error}") from error
            values.append(float(np.mean(source_logits[indexes], dtype=np.float64)))
        else:
            bit = int(candidate["primitiveBits"])
            if bit not in source_index:
                raise ValueError(f"direct semantic candidate refers to missing source primitive {bit}")
            values.append(float(source_logits[source_index[bit]]))
    return np.asarray(values, dtype=np.float64)


def candidate_representation(row):
    grouped = [bool(candidate.get("priorSourceGroup")) for candidate in row["candidates"]]
    if any(grouped) and not all(grouped):
        raise ValueError("one semantic prior mixes direct and grouped candidate representations")
    return "grouped" if grouped and grouped[0] else "direct"


def semantic_prior(candidate_logit, candidates, temperature):
    if not np.isfinite(temperature) or temperature <= 0:
        raise ValueError(f"invalid trace prior temperature: {temperature}")
    logits = np.asarray(candidate_logit, dtype=np.float64)
    if not np.isfinite(logits).all() or len(logits) != len(candidates) or len(logits) < 2:
        raise ValueError("semantic candidate logits are non-finite or have invalid width")
    weights = np.exp((logits - np.max(logits)) / float(temperature))
    multiplicity = Counter(int(candidate["primitiveBits"]) for candidate in candidates)
    raw = np.asarray([weights[i] / multiplicity[int(candidate["primitiveBits"])]
                      for i, candidate in enumerate(candidates)], dtype=np.float64)
    normalized = raw / raw.sum()
    return raw, normalized


def weighted_quantile(values, weights, q):
    values = np.asarray(values, dtype=np.float64)
    weights = np.asarray(weights, dtype=np.float64)
    order = np.argsort(values, kind="stable")
    cumulative = np.cumsum(weights[order])
    return float(values[order[np.searchsorted(cumulative, q * cumulative[-1], side="left")]])


def weighted_corr(x, y, weight):
    x = np.asarray(x, dtype=np.float64); y = np.asarray(y, dtype=np.float64)
    w = np.asarray(weight, dtype=np.float64)
    xm, ym = np.average(x, weights=w), np.average(y, weights=w)
    dx, dy = x - xm, y - ym
    denom = np.sqrt(np.average(dx * dx, weights=w) * np.average(dy * dy, weights=w))
    return float(np.average(dx * dy, weights=w) / denom) if denom > 0 else None


def distribution_stats(metrics, weights=None):
    """Summarize per-prior metrics; rows may have different candidate counts."""
    if not metrics:
        return {"n": 0, "weighted_n": 0}
    if weights is None:
        weights = np.ones(len(metrics), dtype=np.float64)
    else:
        weights = np.asarray(weights, dtype=np.float64)
    if len(weights) != len(metrics) or np.any(weights <= 0):
        raise ValueError("metric weights must be positive and match the prior count")

    def values(name):
        return np.asarray([row[name] for row in metrics], dtype=np.float64)

    def distribution(data):
        return {"mean": float(np.average(data, weights=weights)),
                "median": weighted_quantile(data, weights, 0.50),
                "p90": weighted_quantile(data, weights, 0.90),
                "p99": weighted_quantile(data, weights, 0.99),
                "max": float(np.max(data))}

    teacher_margin = values("teacher_top_two_candidate_logit_margin")
    student_margin = values("student_top_two_candidate_logit_margin")
    margin_abs_error = np.abs(teacher_margin - student_margin)
    return {"n_unique_priors": int(len(metrics)),
            "weighted_prior_occurrences": int(weights.sum()),
            "top_semantic_action_agreement": float(np.average(values("agree"), weights=weights)),
            "ordered_top_two_candidate_agreement": float(np.average(values("ordered_top2_agree"), weights=weights)),
            "teacher_student_top_two_candidate_logit_margin_correlation": weighted_corr(
                teacher_margin, student_margin, weights),
            "top_two_candidate_logit_margin_absolute_error": distribution(margin_abs_error),
            "teacher_top_prior_probability_absolute_error": distribution(
                values("teacher_top_prior_probability_abs_error")),
            "top_prior_probability_peak_absolute_error": distribution(
                values("prior_peak_probability_abs_error")),
            "total_variation": distribution(values("tv")),
            "jensen_shannon_nats": distribution(values("js"))}


def js_divergence(p, q):
    p = np.asarray(p, dtype=np.float64)
    q = np.asarray(q, dtype=np.float64)
    midpoint = 0.5 * (p + q)
    p_mask, q_mask = p > 0, q > 0
    left = np.sum(p[p_mask] * np.log(p[p_mask] / midpoint[p_mask]))
    right = np.sum(q[q_mask] * np.log(q[q_mask] / midpoint[q_mask]))
    return float(0.5 * (left + right))


def prior_metrics(teacher_logits, student_logits, teacher_prior, student_prior):
    teacher_logits = np.asarray(teacher_logits, dtype=np.float64)
    student_logits = np.asarray(student_logits, dtype=np.float64)
    teacher_prior = np.asarray(teacher_prior, dtype=np.float64)
    student_prior = np.asarray(student_prior, dtype=np.float64)
    if not (len(teacher_logits) == len(student_logits) == len(teacher_prior) == len(student_prior)):
        raise ValueError("teacher/student semantic vectors do not align")
    teacher_order = np.argsort(-teacher_prior, kind="stable")
    student_order = np.argsort(-student_prior, kind="stable")
    teacher_logit_order = np.argsort(-teacher_logits, kind="stable")
    student_logit_order = np.argsort(-student_logits, kind="stable")
    teacher_top = int(teacher_order[0])
    teacher_margin = float(teacher_logits[teacher_logit_order[0]] - teacher_logits[teacher_logit_order[1]])
    student_margin = float(student_logits[student_logit_order[0]] - student_logits[student_logit_order[1]])
    return {"teacher": teacher_prior, "student": student_prior,
            "teacher_candidate_logits": teacher_logits,
            "student_candidate_logits": student_logits,
            "agree": bool(teacher_order[0] == student_order[0]),
            "ordered_top2_agree": bool(np.array_equal(teacher_order[:2], student_order[:2])),
            "teacher_top_two_candidate_logit_margin": teacher_margin,
            "student_top_two_candidate_logit_margin": student_margin,
            # Compare the student's probability for the same candidate selected by the teacher.
            "teacher_top_prior_probability_abs_error": float(abs(teacher_prior[teacher_top] - student_prior[teacher_top])),
            "prior_peak_probability_abs_error": float(abs(teacher_prior[teacher_order[0]] - student_prior[student_order[0]])),
            "tv": float(0.5 * np.abs(teacher_prior - student_prior).sum()),
            "js": js_divergence(teacher_prior, student_prior)}


def examples_for_screen(records, metrics, screen=None, representation=None, limit=4):
    indexes = [i for i, (_, row) in enumerate(records)
               if (screen is None or row.get("screen") == screen)
               and (representation is None
                    or metrics[i]["candidate_representation"] == representation)]
    if not indexes:
        return []
    vals = np.asarray([metrics[i]["tv"] for i in indexes], dtype=np.float64)
    ranked = []
    labels = []
    for label, relative in (("min_tv", int(np.argmin(vals))),
                            ("median_tv", int(np.argsort(vals, kind="stable")[len(vals) // 2])),
                            ("max_tv", int(np.argmax(vals)))):
        absolute = indexes[relative]
        if absolute not in ranked:
            labels.append(label)
            ranked.append(absolute)
    disagreements = [i for i in indexes if not metrics[i]["agree"]]
    if disagreements:
        disagreement = max(disagreements, key=lambda i: metrics[i]["tv"])
        if disagreement not in ranked:
            labels.append("largest_tv_top_action_disagreement")
            ranked.append(disagreement)
    out = []
    for label, i in zip(labels[:limit], ranked[:limit], strict=True):
        key, row = records[i]
        candidate_rows = []
        for j, candidate in enumerate(row["candidates"]):
            candidate_rows.append({"candidate_id": int(candidate["candidateId"]),
                                    "compound_selector": int(candidate["compoundSelector"]),
                                    "has_semantic": bool(candidate["hasSemantic"]),
                                    "semantic_key": candidate["semanticKey"],
                                    "primitive_bits": int(candidate["primitiveBits"]),
                                    "prior_source_group_bits": [int(x) for x in candidate["priorSourceGroup"]],
                                    "primitive_multiplicity": sum(int(c["primitiveBits"]) == int(candidate["primitiveBits"])
                                                                   for c in row["candidates"]),
                                    "python_teacher_candidate_logit": float(metrics[i]["python_teacher_candidate_logits"][j]),
                                    "teacher_candidate_logit": float(metrics[i]["teacher_candidate_logits"][j]),
                                    "student_candidate_logit": float(metrics[i]["student_candidate_logits"][j]),
                                    "python_teacher_prior": float(metrics[i]["python_teacher_prior"][j]),
                                    "teacher_prior": float(metrics[i]["teacher"][j]),
                                    "student_prior": float(metrics[i]["student"][j])})
        out.append({"selection": label, "canonical_prior_sha256": key,
                    "runSeed": int(row["runSeed"]), "decisionIndex": int(row["decisionIndex"]),
                    "screen": row["screen"], "floor": int(row["floor"]), "room": row["room"],
                    "candidate_count": int(row["candidateCount"]),
                    "candidate_representation": metrics[i]["candidate_representation"],
                    "top_action_agreement": metrics[i]["agree"],
                    "ordered_top2_candidate_agreement": metrics[i]["ordered_top2_agree"],
                    "tv": metrics[i]["tv"],
                    "js_nats": metrics[i]["js"],
                    "teacher_top_two_candidate_logit_margin": metrics[i]["teacher_top_two_candidate_logit_margin"],
                    "student_top_two_candidate_logit_margin": metrics[i]["student_top_two_candidate_logit_margin"],
                    "teacher_source_logits": [
                        {"primitive_bits": int(source["primitiveBits"]),
                         "captured_native_logit": float(source["teacherSourceLogit"]),
                         "python_teacher_logit": float(metrics[i]["teacher_source_logits"][j]),
                         "student_source_logit": float(metrics[i]["student_source_logits"][j])}
                        for j, source in enumerate(row["sourcePrimitives"])],
                    "candidates": candidate_rows})
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--source-result", type=Path)
    parser.add_argument("--teacher", type=Path, required=True)
    parser.add_argument("--student", type=Path)
    parser.add_argument("--teacher-only", action="store_true",
                        help="validate Python teacher against captured native trace, without loading/evaluating a student")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--native-results", type=Path,
                        help="optional JSONL(.gz) output from the native contextual trace probe")
    parser.add_argument("--device", choices=("cuda", "cpu"), default="cuda",
                        help="inference device for the frozen Python replay (default: cuda)")
    args = parser.parse_args()
    if not args.teacher_only and (args.source_result is None or args.student is None):
        parser.error("--source-result and --student are required unless --teacher-only is set")
    required_paths = [args.trace, args.teacher]
    if not args.teacher_only:
        required_paths.extend((args.source_result, args.student))
        if args.native_results is not None:
            required_paths.append(args.native_results)
    for path in required_paths:
        if not path.is_file():
            raise FileNotFoundError(path)
    if sha256(args.trace) != TRACE_GZIP_SHA256:
        raise ValueError("PR #329 compressed trace SHA differs")
    if sha256(args.teacher) != TEACHER_SHA256:
        raise ValueError("reconstructed Python teacher checkpoint SHA differs")
    if not args.teacher_only:
        source_result = json.loads(args.source_result.read_text())
        if source_result.get("gate", {}).get("pass") is not True:
            raise ValueError("semantic trace evaluation requires a passing source-policy gate")
        if (source_result.get("artifacts", {}).get("student_sha256") != sha256(args.student)
                or source_result.get("artifacts", {}).get("teacher_sha256") != sha256(args.teacher)):
            raise ValueError("source-policy result is not bound to these exact teacher/student artifacts")
    if args.device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for the semantic trace replay")
    device = args.device
    torch.set_num_threads(4 if device == "cuda" else 1)

    teacher_ckpt = torch.load(args.teacher, map_location="cpu", weights_only=False)
    if teacher_ckpt.get("native_sha256") != NATIVE_SHA256:
        raise ValueError("teacher checkpoint is not bound to the tracked native teacher")
    teacher_sd = teacher_ckpt["state_dict"]
    if len(teacher_sd) != 115:
        raise ValueError("deployed teacher checkpoint must contain exactly 115 tensors")
    model = HybridTeacher().to(device)
    model.load_state_dict(teacher_sd, strict=True)
    model.eval()
    model._experiment_mean = teacher_ckpt["mean"]
    model._experiment_inv = teacher_ckpt["inv"]
    for parameter in model.parameters():
        parameter.requires_grad_(False)

    records, occurrences, census = load_unique_trace(args.trace)
    rows = [row for _, row in records]
    packed, z_teacher = encode_teacher_trace_states(model, rows, device)
    teacher_sources, source_count = forward_sources(model, packed, z_teacher, records,
                                                     device, teacher_ckpt["mean"],
                                                     teacher_ckpt["inv"])

    teacher_max_logit_error = 0.0
    teacher_source_rows = 0
    source_argmax_match = []
    candidate_logit_error = 0.0
    prior_error = 0.0
    raw_weight_error = 0.0
    teacher_candidate_rows = []
    teacher_prior_rows = []
    python_teacher_candidate_rows = []
    python_teacher_prior_rows = []
    for i, (key, row) in enumerate(records):
        captured_source = np.asarray([float(source["teacherSourceLogit"])
                                      for source in row["sourcePrimitives"]], dtype=np.float64)
        py_teacher = np.asarray(teacher_sources[i], dtype=np.float64)
        if len(py_teacher) != len(captured_source):
            raise ValueError(f"captured source row count differs for prior {key}")
        delta = np.abs(py_teacher - captured_source)
        teacher_max_logit_error = max(teacher_max_logit_error, float(delta.max(initial=0.0)))
        teacher_source_rows += len(captured_source)
        source_argmax_match.append(int(np.argmax(py_teacher)) == int(np.argmax(captured_source)))
        py_candidate = candidate_logits(row, py_teacher)
        stored_candidate = np.asarray(row["teacherCandidateLogits"], dtype=np.float64)
        if len(py_candidate) != len(stored_candidate):
            raise ValueError(f"captured candidate logits count differs for prior {key}")
        candidate_logit_error = max(candidate_logit_error,
                                    float(np.max(np.abs(py_candidate - stored_candidate), initial=0.0)))
        teacher_raw, py_teacher_prior = semantic_prior(py_candidate, row["candidates"],
                                                       float(row["priorTemperature"]))
        captured_prior = np.asarray(row["teacherNormalizedPrior"], dtype=np.float64)
        prior_error = max(prior_error, float(np.max(np.abs(py_teacher_prior - captured_prior), initial=0.0)))
        captured_raw = np.asarray(row["teacherRawPriorWeights"], dtype=np.float64)
        raw_weight_error = max(raw_weight_error,
                               float(np.max(np.abs(teacher_raw - captured_raw), initial=0.0)))
        teacher_candidate_rows.append(stored_candidate)
        teacher_prior_rows.append(captured_prior)
        python_teacher_candidate_rows.append(py_candidate)
        python_teacher_prior_rows.append(py_teacher_prior)

    parity = {"captured_teacher_source_rows": teacher_source_rows,
              "max_abs_python_vs_captured_native_source_logit": teacher_max_logit_error,
              "source_argmax_parity": float(np.mean(source_argmax_match)),
              "source_primitives_argmax_parity_count": int(np.sum(source_argmax_match)),
              "unique_prior_count": len(records),
              "max_abs_python_vs_captured_candidate_logit": candidate_logit_error,
              "max_abs_python_vs_captured_raw_semantic_weight": raw_weight_error,
              "max_abs_rebuilt_teacher_final_prior": prior_error}
    if (teacher_max_logit_error >= 1e-4 or parity["source_argmax_parity"] != 1.0
            or candidate_logit_error >= 1e-4):
        raise ValueError(f"native/Python teacher trace preflight failed: {parity}")
    if prior_error >= 1e-4:
        raise ValueError(f"rebuilt teacher semantic priors differ from captured output: {prior_error}")

    if args.teacher_only:
        result = {"version": "ooc-contextual-python-teacher-trace-preflight-v1",
                  "artifacts": {"trace_gzip_sha256": sha256(args.trace),
                                "trace_decompressed_sha256": census["decompressed_trace_sha256"],
                                "teacher_sha256": sha256(args.teacher),
                                "native_teacher_sha256": NATIVE_SHA256,
                                "preflight_script_sha256": sha256(Path(__file__))},
                  "population": census,
                  "python_native_teacher_preflight": parity,
                  "result": "PASS"}
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(json.dumps(result, indent=2, sort_keys=True), flush=True)
        return

    student_ckpt = torch.load(args.student, map_location="cpu", weights_only=False)
    if (student_ckpt.get("native_sha256") != NATIVE_SHA256
            or student_ckpt.get("teacher_sha256") != TEACHER_SHA256):
        raise ValueError("student checkpoint is not bound to the tracked deployed42 teacher")
    student_sd = student_ckpt["state_dict"]
    added = sorted(set(student_sd) - set(teacher_sd))
    target_sha = student_ckpt.get("teacher_targets_sha256")
    source_artifacts = source_result.get("artifacts", {})
    teacher_trace_preflight = (student_ckpt.get("python_native_parity", {})
                               .get("authoritative_captured_native_trace_preflight", {}))
    trace_parity = teacher_trace_preflight.get("python_native_teacher_preflight", {})
    if (len(teacher_sd) != 115 or len(added) != 6 or len(student_sd) != 121
            or student_ckpt.get("trainable_parameter_count") != 3200
            or student_ckpt.get("epoch") != 30
            or student_ckpt.get("model_seed") != 0
            or student_ckpt.get("representation_loss_only") is not True
            or student_ckpt.get("policy_or_q_loss") is not False
            or student_ckpt.get("end_to_end_finetuning") is not False
            or student_ckpt.get("optimizer") != {"name": "AdamW", "lr": 1e-3, "weight_decay": 1e-4}
            or student_ckpt.get("batch_groups") != 4096
            or student_ckpt.get("corpus_sha256") != CORPUS_SHA256
            or student_ckpt.get("split_sha256") != SPLIT_SHA256
            or student_ckpt.get("trace_gzip_sha256") != TRACE_GZIP_SHA256
            or student_ckpt.get("state_cache_layout") != "raw-to-grouped-v2"
            or student_ckpt.get("state_cache_sha256") != source_artifacts.get("state_cache_sha256")
            or target_sha != source_artifacts.get("target_cache_sha256")
            or teacher_trace_preflight.get("result") != "PASS"
            or trace_parity.get("max_abs_python_vs_captured_native_source_logit", 1.0) >= 1e-4
            or trace_parity.get("source_argmax_parity", 0.0) != 1.0
            or trace_parity.get("max_abs_python_vs_captured_candidate_logit", 1.0) >= 1e-4
            or trace_parity.get("max_abs_rebuilt_teacher_final_prior", 1.0) >= 1e-4
            or not isinstance(target_sha, str) or len(target_sha) != 64):
        raise ValueError("student checkpoint tensor inventory/provenance/recipe differs from the frozen Tier-B run")
    if any(not torch.equal(teacher_sd[key], student_sd[key]) for key in teacher_sd):
        raise ValueError("student checkpoint changed a frozen teacher tensor")
    if not all(key.startswith("contextDeck.") for key in added):
        raise ValueError(f"unexpected contextual checkpoint keys: {added}")

    # Do not run the contextual encoder until the Python teacher has passed
    # source-logit, source-argmax, candidate-logit, and final-prior parity.
    context = ContextualDeck().to(device)
    context.load_state_dict({key.removeprefix("contextDeck."): student_sd[key] for key in added}, strict=True)
    context.eval()
    z_student = encode_student_trace_states(model, context, packed, device)
    student_sources, student_source_count = forward_sources(model, packed, z_student, records,
                                                            device, teacher_ckpt["mean"],
                                                            teacher_ckpt["inv"])
    if source_count != student_source_count:
        raise AssertionError("teacher/student source candidate counts differ")

    metric_rows = []
    native_predictions = (load_native_predictions(args.native_results, len(records))
                          if args.native_results is not None else None)
    native_parity = None
    if native_predictions is not None:
        native_parity = {
            "unique_prior_count": len(records),
            "source_logit_count": 0,
            "max_abs_error": {"deck_representation": 0.0, "source_policy_logits": 0.0,
                              "grouped_candidate_logits": 0.0, "normalized_semantic_prior": 0.0},
            "top_semantic_action_mismatches": 0,
            "top_semantic_action_mismatch_examples": [],
        }
    for i, (key, row) in enumerate(records):
        py_student_source = np.asarray(student_sources[i], dtype=np.float64)
        py_student_candidate = candidate_logits(row, py_student_source)
        _, py_student_prior = semantic_prior(py_student_candidate, row["candidates"],
                                              float(row["priorTemperature"]))
        if native_predictions is not None:
            native = native_predictions[i]
            if native["priorKey"] != key:
                raise ValueError(f"native prior order/key mismatch at row {i}: {native['priorKey']} != {key}")
            native_deck = np.asarray(native["deckRepresentation"], dtype=np.float64)
            native_source = np.asarray(native["sourceLogits"], dtype=np.float64)
            native_candidate = np.asarray(native["candidateLogits"], dtype=np.float64)
            native_prior = np.asarray(native["normalizedPrior"], dtype=np.float64)
            py_deck = np.asarray(z_student[i], dtype=np.float64)
            if (native_deck.shape != (32,) or native_source.shape != py_student_source.shape
                    or native_candidate.shape != py_student_candidate.shape
                    or native_prior.shape != py_student_prior.shape
                    or not np.isfinite(native_deck).all() or not np.isfinite(native_source).all()
                    or not np.isfinite(native_candidate).all() or not np.isfinite(native_prior).all()):
                raise ValueError(f"native output shape or finite-value mismatch for prior {key}")
            errors = {
                "deck_representation": float(np.max(np.abs(native_deck - py_deck), initial=0.0)),
                "source_policy_logits": float(np.max(np.abs(native_source - py_student_source), initial=0.0)),
                "grouped_candidate_logits": float(np.max(np.abs(native_candidate - py_student_candidate), initial=0.0)),
                "normalized_semantic_prior": float(np.max(np.abs(native_prior - py_student_prior), initial=0.0)),
            }
            for name, error in errors.items():
                native_parity["max_abs_error"][name] = max(native_parity["max_abs_error"][name], error)
            native_parity["source_logit_count"] += len(native_source)
            python_top = int(np.argmax(py_student_prior))
            native_top = int(np.argmax(native_prior))
            if python_top != native_top:
                native_parity["top_semantic_action_mismatches"] += 1
                if len(native_parity["top_semantic_action_mismatch_examples"]) < 16:
                    native_parity["top_semantic_action_mismatch_examples"].append({
                        "prior_key": key, "python_index": python_top, "native_index": native_top,
                        "python_semantic_key": row["candidates"][python_top]["semanticKey"],
                        "native_semantic_key": row["candidates"][native_top]["semanticKey"],
                    })
        captured_teacher_candidate = teacher_candidate_rows[i]
        captured_teacher_prior = teacher_prior_rows[i]
        if len(py_student_prior) != len(captured_teacher_prior):
            raise ValueError(f"semantic candidate count changed for prior {key}")
        metric = prior_metrics(captured_teacher_candidate, py_student_candidate,
                              captured_teacher_prior, py_student_prior)
        metric["python_teacher_candidate_logits"] = python_teacher_candidate_rows[i]
        metric["python_teacher_prior"] = python_teacher_prior_rows[i]
        metric["candidate_representation"] = candidate_representation(row)
        metric["teacher_source_logits"] = np.asarray(teacher_sources[i], dtype=np.float64)
        metric["student_source_logits"] = py_student_source
        metric_rows.append(metric)

    if native_parity is not None:
        native_parity["gates"] = {
            name: error < 1e-4
            for name, error in native_parity["max_abs_error"].items()
        }
        native_parity["top_semantic_action_parity"] = (
            native_parity["top_semantic_action_mismatches"] == 0)
        native_parity["pass"] = (all(native_parity["gates"].values())
                                  and native_parity["top_semantic_action_parity"])

    weights = np.asarray([occurrences[key] for key, _ in records], dtype=np.int32)
    overall_unique = distribution_stats(metric_rows)
    overall_occurrences = distribution_stats(metric_rows, weights)
    screen_metrics = {}
    screen_names = sorted({str(row["screen"]) for row in rows})
    for screen in screen_names:
        idx = [i for i, row in enumerate(rows) if row["screen"] == screen]
        screen_metrics[screen] = {
            "unique": distribution_stats([metric_rows[i] for i in idx]),
            "occurrence_weighted": distribution_stats([metric_rows[i] for i in idx], weights[idx])}

    broad = [name for name in screen_names
             if sum(str(row["screen"]) == name for row in rows) >= 100]
    screen_guard = True
    screen_guard_rows = {}
    for name in broad:
        item = screen_metrics[name]["unique"]
        passed = (item["top_semantic_action_agreement"] >= 0.90
                  and item["total_variation"]["median"] <= 0.05
                  and item["total_variation"]["p90"] <= 0.15)
        screen_guard &= passed
        screen_guard_rows[name] = {**item, "guard_pass": passed}
    gate = {"top_semantic_action_agreement_ge_0_95": overall_unique["top_semantic_action_agreement"] >= 0.95,
            "median_tv_le_0_03": overall_unique["total_variation"]["median"] <= 0.03,
            "p90_tv_le_0_10": overall_unique["total_variation"]["p90"] <= 0.10,
            "no_broad_screen_specific_collapse": screen_guard}
    gate["pass"] = all(gate.values())
    if gate["pass"]:
        classification = "CONTEXTUAL_SEMANTIC_PRIOR_PASS"
    elif (overall_unique["top_semantic_action_agreement"] >= 0.90
          and overall_unique["total_variation"]["median"] <= 0.05
          and overall_unique["total_variation"]["p90"] <= 0.15
          and all(item["top_semantic_action_agreement"] >= 0.80
                  and item["total_variation"]["median"] <= 0.10
                  and item["total_variation"]["p90"] <= 0.20
                  for item in screen_guard_rows.values())):
        classification = "CONTEXTUAL_SEMANTIC_PRIOR_BORDERLINE"
    else:
        classification = "CONTEXTUAL_SEMANTIC_PRIOR_REJECTED"
    shops = examples_for_screen(records, metric_rows, "shop")
    card_rewards = examples_for_screen(records, metric_rows, "card reward")
    map_direct = examples_for_screen(records, metric_rows, "map", "direct")
    grouped_semantics = examples_for_screen(records, metric_rows, representation="grouped")
    stratified_metrics = {}
    buckets = {"2": lambda count: count == 2,
               "3-4": lambda count: 3 <= count <= 4,
               "5-8": lambda count: 5 <= count <= 8,
               "9+": lambda count: count >= 9}
    for name, predicate in buckets.items():
        idx = [i for i, row in enumerate(rows) if predicate(int(row["candidateCount"]))]
        stratified_metrics[f"candidate_count_{name}"] = {
            "unique": distribution_stats([metric_rows[i] for i in idx]),
            "occurrence_weighted": distribution_stats([metric_rows[i] for i in idx], weights[idx])}
    for representation in ("direct", "grouped"):
        idx = [i for i, metric in enumerate(metric_rows)
               if metric["candidate_representation"] == representation]
        stratified_metrics[f"{representation}_semantic_candidates"] = {
            "unique": distribution_stats([metric_rows[i] for i in idx]),
            "occurrence_weighted": distribution_stats([metric_rows[i] for i in idx], weights[idx])}
    artifacts = {"trace_gzip_sha256": sha256(args.trace),
                 "trace_decompressed_sha256": census["decompressed_trace_sha256"],
                 "teacher_sha256": sha256(args.teacher),
                 "student_sha256": sha256(args.student),
                 "semantic_evaluator_sha256": sha256(Path(__file__)),
                 "native_teacher_sha256": NATIVE_SHA256,
                 "source_policy_result_sha256": sha256(args.source_result)}
    if args.native_results is not None:
        artifacts["native_trace_results_sha256"] = sha256(args.native_results)
    result = {"version": "ooc-contextual-semantic-prior-trace-v1",
              "artifacts": artifacts,
              "population": census,
              "python_native_teacher_preflight": parity,
              "native_python_contextual_parity": native_parity,
              "unique_prior_metrics": overall_unique,
              "trace_occurrence_weighted_metrics": overall_occurrences,
              "by_screen": screen_metrics,
              "stratified_metrics": stratified_metrics,
              "broad_screen_guards": screen_guard_rows,
              "classification": classification,
              "shop_examples": shops,
              "card_reward_examples": card_rewards,
              "map_direct_examples": map_direct,
              "grouped_semantic_examples": grouped_semantics,
              "gate": gate,
              "gate_policy": {"overall": "unique canonical priors: top semantic action agreement >= 0.95; median TV <= 0.03; p90 TV <= 0.10",
                              "broad_screens_n_ge_100": "top agreement >= 0.90; median TV <= 0.05; p90 TV <= 0.15",
                              "classification": "CONTEXTUAL_SEMANTIC_PRIOR_PASS when all original gates pass; BORDERLINE when overall top agreement >= 0.90, median TV <= 0.05, p90 TV <= 0.15, and no broad screen is severe (<0.80 top agreement, >0.10 median TV, or >0.20 p90 TV); otherwise REJECTED",
                              "top_prior_probability_error": "absolute student-versus-teacher prior error at the teacher-selected top semantic candidate",
                              "margin": "difference between the highest and second-highest raw candidate logits before primitive multiplicity correction",
                              "multiplicity": "softmax semantic-candidate logits, divide each candidate weight by the count of candidates sharing its primitiveBits, then renormalize"},
              "interpretation": "offline semantic-prior qualification on the captured PR #329 trace; native contextual parity is included only when native results are supplied; no gameplay claim"}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
