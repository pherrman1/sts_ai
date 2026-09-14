#!/usr/bin/env python3
"""Prespecified frozen attention composition/potion-support diagnostic; never fits.

The consumption-only adapter is opt-in. It certifies the current simulator's
visible absence of potion generators, not arbitrary native transitions.
"""
from __future__ import annotations

import argparse
import copy
import json
import subprocess
import time
from pathlib import Path

import numpy as np

try:
    from tools import combat_transition_attention_ablation as attention
    from tools import combat_transition_surrogate as base
except ModuleNotFoundError:
    import combat_transition_attention_ablation as attention
    import combat_transition_surrogate as base


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_HASHES = {
    "phase2_attention.pt": "66ac8f70da69e29bf9b1364243f6f903e4f74dda1ec8a909ef54a7ea97dc6479",
    "point_control_attention.pt": "2447b2daf1a48a619a5f071488908afd6f0fb83bfd855ee9f379c04120efeaef",
    "prepared.npz": "2badbb85ccd8329bcb886d50ef8a0b9b1bd2c043fda9445de9f9c2e7a4b6f9a5",
    "prepared_manifest.json": "13b2c91fd0ced713f8c429bbf8995ceb58b6e3e57d1555de42f5e67d7f9a389f",
    "target_spec.json": "e2315620d512578542d6b3bfbd362eb07b086f0e9fa7770cc23f4fa4c226e229",
}


def potion_consumption_only(predictor_input: dict) -> bool:
    """Visible-input-only consumption closure for the audited simulator.

    Alchemize is a STS1 potion generator even though its simulator execution
    is unimplemented. All combat random card pools exclude it. Off-color
    cards and random card generators therefore do not invalidate closure.
    Entropic Brew fills empty slots and remains explicitly excluded.
    Ironclad eligibility is retained independently of the card-color rule.
    """
    if int(predictor_input["globals"]["characterClass"]) != base.IRONCLAD_ID:
        return False
    if any(int(card["cardId"]) == base._CARD_IDS["ALCHEMIZE"]
           for card in predictor_input["cards"]):
        return False
    return all(int(potion["potionId"]) != base.ENTROPIC_BREW_ID
               for potion in predictor_input["potions"])


def allowed_potion_support(pre_slots: np.ndarray, capacities: np.ndarray) -> np.ndarray:
    pre_slots = np.asarray(pre_slots)
    capacities = np.asarray(capacities)
    if pre_slots.ndim != 2 or pre_slots.shape[1] != 5 or capacities.shape != (len(pre_slots),):
        raise ValueError("expected N x 5 slots and N capacities")
    if (np.any(pre_slots != pre_slots.astype(np.int64)) or
            np.any(capacities != capacities.astype(np.int64)) or
            np.any(pre_slots < base.EMPTY_POTION_SLOT_ID) or
            np.any(pre_slots >= base.POTION_COUNT) or
            np.any(capacities < 0) or np.any(capacities > 5)):
        raise ValueError("invalid visible potion inventory")
    allowed = np.zeros((*pre_slots.shape, base.POTION_COUNT), dtype=bool)
    rows = np.arange(len(pre_slots))[:, None]
    slots = np.arange(5)[None, :]
    allowed[rows, slots, pre_slots.astype(np.int64)] = True
    allowed[:, :, base.EMPTY_POTION_SLOT_ID] |= slots < capacities[:, None]
    return allowed


def potion_log_probabilities(logits: np.ndarray, pre_slots: np.ndarray,
                             capacities: np.ndarray, certified: np.ndarray | None = None) -> np.ndarray:
    """Stable masked log-softmax, with no zero-mass or uniform fallback.

    None keeps the historical B domain (IDs 1..47 in active slots). C masks
    only certified rows; unavailable slots are exact copy-through in both.
    """
    logits = np.asarray(logits, dtype=np.float64)
    if logits.shape != (*np.asarray(pre_slots).shape, base.POTION_COUNT):
        raise ValueError("potion logits shape mismatch")
    if not np.all(np.isfinite(logits)):
        raise ValueError("nonfinite potion logits")
    consumption = allowed_potion_support(pre_slots, capacities)
    allowed = np.ones_like(consumption)
    allowed[..., 0] = False
    unavailable = np.arange(5)[None, :] >= np.asarray(capacities)[:, None]
    allowed[unavailable] = consumption[unavailable]
    if certified is not None:
        certified = np.asarray(certified, dtype=bool)
        if certified.shape != (len(logits),):
            raise ValueError("certification shape mismatch")
        allowed[certified] = consumption[certified]
    masked = np.where(allowed, logits, -np.inf)
    maximum = masked.max(axis=-1, keepdims=True)
    mass = np.exp(masked - maximum).sum(axis=-1, keepdims=True)
    if not np.all(np.isfinite(maximum)) or not np.all(np.isfinite(mass)) or np.any(mass <= 0):
        raise ValueError("nonfinite or zero allowed potion mass")
    return masked - maximum - np.log(mass)


def compose_predictions(phase2: dict, point_survival: np.ndarray) -> dict:
    p = np.asarray(point_survival)
    if p.shape != phase2["pWin"].shape or not np.all(np.isfinite(p)) or np.any((p < 0) | (p > 1)):
        raise ValueError("invalid frozen point-control survival")
    return {**phase2, "pWin": p}


def outcome_nll(y: np.ndarray, p: np.ndarray) -> np.ndarray:
    p = np.asarray(p, dtype=np.float64)
    # Exact probabilities, no clipping of an impossible observed event.
    with np.errstate(divide="ignore"):
        losses = np.where(y == 1, -np.log(p), -np.log1p(-p))
    if not np.all(np.isfinite(losses)):
        raise ValueError("nonfinite outcome NLL")
    return losses


def joint_nll(arrays: dict, ids: np.ndarray, pred: dict) -> np.ndarray:
    losses = outcome_nll(arrays["y_win"][ids], pred["pWin"])
    win = arrays["y_win"][ids] == 1
    local = np.flatnonzero(win)
    delta = arrays["delta_index"][ids[win]]
    hp = arrays["y_hp_bin"][ids[win]]
    mass_delta = pred["pDelta"][local, delta].astype(np.float64)
    mass_hp = pred["hpConditional"][local, delta, hp].astype(np.float64)
    with np.errstate(divide="ignore"):
        losses[win] -= np.log(mass_delta) + np.log(mass_hp)
    if not np.all(np.isfinite(losses)):
        raise ValueError("nonfinite joint NLL")
    return losses


def paired_bootstrap(seeds: np.ndarray, differences: dict[str, np.ndarray],
                     reps: int = 1000, seed: int = 20260913) -> dict:
    """Resample sources; row-weighted paired means preserve all rows in each source."""
    unique, inverse = np.unique(seeds, return_inverse=True)
    count = np.bincount(inverse).astype(np.float64)
    sums = {name: np.bincount(inverse, weights=values, minlength=len(unique))
            for name, values in differences.items()}
    rng = np.random.default_rng(seed)
    draws = {name: [] for name in sums}
    for _ in range(reps):
        sampled = rng.integers(0, len(unique), len(unique))
        denominator = count[sampled].sum()
        for name, values in sums.items():
            draws[name].append(values[sampled].sum() / denominator)
    return {name: {"mean": float(np.mean(differences[name])),
                   "sourceBootstrap95": np.quantile(draws[name], [0.025, 0.975]).tolist(),
                   "sources": len(unique), "rows": len(seeds), "repetitions": reps}
            for name in draws}


def potion_row_scores(logp: np.ndarray, actual: np.ndarray, pre: np.ndarray,
                      capacities: np.ndarray) -> dict:
    rows = np.arange(len(actual))[:, None]
    slots = np.arange(5)[None, :]
    target_logp = logp[rows, slots, actual]
    if not np.all(np.isfinite(target_logp)):
        raise ValueError("observed potion target has zero probability")
    mode = logp.argmax(-1)
    nochange_prob = np.exp(logp[rows, slots, pre].sum(-1))
    nochange = np.all(actual == pre, axis=1)
    return {"vectorNll": -target_logp.sum(-1), "slotNll": -target_logp,
            "exact": np.all(mode == actual, axis=1).astype(float),
            "noChangeProbability": nochange_prob,
            "noChangeBrier": (nochange_prob - nochange) ** 2,
            "countExact": (np.sum(mode > 1, axis=1) == np.sum(actual > 1, axis=1)).astype(float),
            "changed": ~nochange,
            "active": slots < capacities[:, None]}


def compact_potions(scores: dict, subset: np.ndarray) -> dict:
    if not np.any(subset):
        return {"rows": 0}
    out = {"rows": int(subset.sum())}
    for key in ("vectorNll", "exact", "noChangeProbability", "noChangeBrier", "countExact"):
        out[key] = float(scores[key][subset].mean())
    out["perSlot"] = {}
    for slot in range(5):
        active = subset & scores["active"][:, slot]
        out["perSlot"][str(slot)] = {"activeRows": int(active.sum()),
            "activeNll": float(scores["slotNll"][active, slot].mean()) if active.any() else None}
    out["copyThroughExact"] = float((~scores["changed"][subset]).mean())
    out["copyThroughNoChangeEventBrier"] = float(scores["changed"][subset].mean())
    for name, mask in (("changed", scores["changed"]), ("unchanged", ~scores["changed"])):
        chosen = subset & mask
        out[name] = {"rows": int(chosen.sum()),
                       **{key: float(scores[key][chosen].mean()) if chosen.any() else None
                          for key in ("vectorNll", "exact", "noChangeBrier")}}
    return out


def audit_corpus(corpus: Path, arrays: dict, split: dict) -> tuple[np.ndarray, dict, dict]:
    """Audit fixed rule against every supported RAW transition, including deaths.

    Also reconcile actual source/fight order, split membership, global support,
    and potion targets. Predicate is fixed before reading labels.
    """
    certified = np.zeros(len(arrays["sourceSeed"]), dtype=bool)
    membership = {int(s): i for i, name in enumerate(("train", "validation", "test"))
                  for s in split["members"][name]}
    observed_sources = set()
    examples = {}
    seen = 0
    for i, row in enumerate(base.iter_rows(corpus)):
        if i >= len(certified):
            raise ValueError("corpus exceeds prepared arrays")
        pi = row["predictorInput"]
        pre, post = row["transition"]["pre"], row["transition"]["post"]
        source = int(row["sourceSeed"])
        observed_sources.add(source)
        if (source != int(arrays["sourceSeed"][i]) or int(row["fightIdx"]) != int(arrays["fightIdx"][i])
                or membership.get(source) != int(arrays["split_id"][i])
                or base.supported_for_surrogate(pi, pre) != bool(arrays["supported"][i])
                or not np.array_equal(post["potions"], arrays["y_potions"][i])
                or not np.array_equal(pre["potions"], arrays["potions"][i, :, 1])):
            raise ValueError(f"corpus/prepared/split mismatch at row {i}")
        certified[i] = potion_consumption_only(pi)
        if certified[i] and arrays["supported"][i]:
            allowed = allowed_potion_support(np.asarray([pre["potions"]]), np.asarray([pre["potionCapacity"]]))[0]
            if not allowed[np.arange(5), post["potions"]].all():
                raise ValueError(f"CONTRADICTED_RULE row={i} source={source} pre={pre['potions']} post={post['potions']}")
        if arrays["supported"][i] and int(arrays["split_id"][i]) == 2:
            category = "certified" if certified[i] else "uncertified"
            examples.setdefault(category, {"pre": pre, "predictorInput": pi, "rowIndex": i})
        seen += 1
        if seen % 100000 == 0:
            print(f"corpus audit {seen} rows", flush=True)
    if seen != len(certified) or observed_sources != set(membership):
        raise ValueError("corpus rows/source membership differ from frozen split")
    supported = arrays["supported"]
    return certified, {"rows": seen, "sourceGroups": len(observed_sources),
                       "supportedRows": int(supported.sum()),
                       "certifiedSupportedRows": int((certified & supported).sum()),
                       "contradictions": 0, "sourceSplitMembershipVerified": True}, examples


def sample_prediction(pre: dict, prediction: dict, spec: dict, rng: np.random.Generator) -> dict | None:
    """Narrow draw with exact support: no residual mass assigned to forbidden IDs."""
    if not np.isfinite(prediction["pWin"]) or not 0 <= prediction["pWin"] <= 1:
        raise ValueError("invalid sampler survival")
    for key in ("pDelta", "hpConditional", "potionProbs"):
        p = np.asarray(prediction[key])
        if not np.all(np.isfinite(p)) or np.any(p < 0) or not np.allclose(p.sum(-1), 1, atol=1e-6):
            raise ValueError(f"invalid sampler probabilities: {key}")
    if float(rng.random()) >= float(prediction["pWin"]):
        return None
    def choice(probabilities):
        p = np.asarray(probabilities, dtype=np.float64)
        active = np.flatnonzero(p > 0)
        if not len(active) or not np.all(np.isfinite(p)) or np.any(p < 0):
            raise ValueError("nonfinite or zero sampler mass")
        return int(rng.choice(active, p=p[active] / p[active].sum()))
    delta = choice(prediction["pDelta"])
    post = {key: copy.deepcopy(pre[key]) for key in base.PERSISTENT_KEYS if key != "combatRng"}
    post["maxHp"] = int(pre["maxHp"]) + int(spec["maxHpDeltaValues"][delta])
    if post["maxHp"] <= 0:
        raise ValueError("sampled maxHp is not positive")
    hp_bin = choice(prediction["hpConditional"][delta])
    post["curHp"] = max(1, min(post["maxHp"], base._round_half_up(hp_bin / 100 * post["maxHp"])))
    for slot in range(int(pre["potionCapacity"])):
        p = np.asarray(prediction["potionProbs"][slot], dtype=np.float64)
        if p[0] != 0:
            raise ValueError("INVALID potion has positive probability")
        post["potions"][slot] = choice(p)
    post["potionCount"] = int(sum(p > base.EMPTY_POTION_SLOT_ID for p in post["potions"]))
    for relic in post["relics"]:
        rid = int(relic["id"])
        if rid not in base.CODE_AUDITED_MUTABLE_RELIC_IDS:
            continue
        probs = np.asarray(prediction["relicDeltaProbs"][str(rid)], dtype=np.float64)
        allowed = np.isin(spec["relicDeltaValues"], spec["relicDeltaValuesById"][str(rid)])
        if np.any(probs[~allowed] != 0):
            raise ValueError("forbidden relic delta has positive probability")
        relic["data"] = int(relic["data"]) + int(spec["relicDeltaValues"][choice(probs)])
    return post


def measure_cpu_cost(phase2, point, arrays: dict, examples: dict, spec: dict) -> dict:
    import torch
    torch.set_num_threads(1)
    phase2.net.to("cpu"); phase2.device = torch.device("cpu"); phase2.net.eval()
    point.net.to("cpu"); point.device = torch.device("cpu"); point.net.eval()
    results = {}
    for category, example in examples.items():
        ids = np.asarray([example["rowIndex"]])
        pre = example["pre"]
        slots = arrays["potions"][ids, :, 1]
        cap = arrays["potionCapacity"][ids]
        def draw(arm, rng):
            # Reuse the canonical encoder with dummy bookkeeping/absent labels.
            # Boundary includes visible-input encoding, all forwards, probability
            # conversion/support adapters, and one draw including copied state.
            row = {"predictorInput": example["predictorInput"], "sourceSeed": 0, "fightIdx": 0,
                   "transition": {"combatOutcome": base.DEATH, "post": {}}}
            encoded = base._encode_row(row)
            input_arrays = {key: value[None] for key, value in zip(
                ("globals_continuous", "global_categories", "cards", "relics", "potions", "card_mask", "relic_mask"), encoded[:7])}
            values = base._torch_inputs(input_arrays, np.asarray([0]), "cpu", torch)
            survival, delta, hp, potion, relic = phase2.net(*values)
            pwin = float(torch.sigmoid(survival)[0])
            if arm != "A":
                pwin = float(torch.sigmoid(point.net(*values)[0])[0])
            potion_logits = potion.numpy()
            cert = np.asarray([potion_consumption_only(example["predictorInput"])]) if arm == "C" else None
            logp = potion_log_probabilities(potion_logits, slots, cap, cert)
            relic_logits = relic.numpy()[0]
            relic_map = {}
            for j in np.flatnonzero(arrays["relic_mask"][ids[0]]):
                rid = int(arrays["relics"][ids[0], j, 0])
                if rid not in base.CODE_AUDITED_MUTABLE_RELIC_IDS:
                    continue
                allowed = np.isin(spec["relicDeltaValues"], spec["relicDeltaValuesById"][str(rid)])
                relic_map[str(rid)] = base._softmax(np.where(allowed, relic_logits[j], -np.inf))
            pred = {"pWin": pwin, "pDelta": base._softmax(delta.numpy())[0],
                    "hpConditional": base._softmax(hp.numpy())[0], "potionProbs": np.exp(logp[0]),
                    "relicDeltaProbs": relic_map}
            return sample_prediction(pre, pred, spec, rng)
        results[category] = {}
        with torch.inference_mode():
            for arm in ("A", "B", "C"):
                rng = np.random.default_rng(20260914)
                for _ in range(10):
                    draw(arm, rng)
                times = []
                deaths = 0
                for _ in range(100):
                    start = time.perf_counter()
                    sampled = draw(arm, rng)
                    times.append((time.perf_counter() - start) * 1000)
                    deaths += sampled is None
                results[category][arm] = {"meanMs": float(np.mean(times)), "medianMs": float(np.median(times)),
                    "p95Ms": float(np.quantile(times, .95)), "draws": 100, "deathDraws": deaths}
    return {"device": "cpu", "torchThreads": 1, "batch": 1, "warmup": 10,
            "boundary": "visible predictor-input encoding, required forwards, distribution adapters, one transition draw",
            "fixedWidthInputs": True, "byCertification": results}


def run(args) -> None:
    import torch
    prepared, artifacts, output = map(Path, (args.prepared_dir, args.artifact_dir, args.output_dir))
    output.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for name, expected in EXPECTED_HASHES.items():
        path = (artifacts if name.endswith(".pt") else prepared) / name
        hashes[name] = base.sha256(path)
        if hashes[name] != expected:
            raise ValueError(f"frozen artifact mismatch: {path}")
    manifest = json.loads((prepared / "prepared_manifest.json").read_text())
    corpus_manifest = Path(manifest["corpusManifest"])
    if base.sha256(corpus_manifest) != manifest["corpusManifestSha256"]:
        raise ValueError("corpus manifest mismatch")
    corpus = Path(json.loads(corpus_manifest.read_text())["csv"]["path"])
    hashes["corpus"] = base.sha256(corpus)
    if hashes["corpus"] != attention.EXPECTED_CORPUS_SHA256:
        raise ValueError("corpus hash mismatch")
    split_path = Path(args.split_manifest)
    hashes["sourceSplit"] = base.sha256(split_path)
    if hashes["sourceSplit"] != attention.EXPECTED_SPLIT_SHA256:
        raise ValueError("source split hash mismatch")
    arrays, spec = base._load_prepared(prepared)
    base._prepare_target_indices(arrays, spec)
    groups = [np.flatnonzero((arrays["split_id"] == i) & arrays["supported"]) for i in range(3)]
    if [len(x) for x in groups] != [331225, 41120, 41454]:
        raise ValueError("supported split counts differ")
    # Independently verify source bucket rule against the actual frozen split.
    split = json.loads(split_path.read_text())
    for name, sources in split["members"].items():
        if any(base.split_for_seed(int(s)) != name for s in sources):
            raise ValueError("split membership differs from source hash rule")
    certified, audit, examples = audit_corpus(corpus, arrays, split)
    np.save(output / "certified_rows.npy", certified)
    base.json_dump(output / "corpus_rule_audit.json", audit)
    print("provenance and rule audit passed", flush=True)
    combined = np.concatenate(groups[:2])
    phase2 = attention._load_checkpoint("phase2", artifacts / "phase2_attention.pt", arrays, spec, combined, args, args.device)
    point = attention._load_checkpoint("point", artifacts / "point_control_attention.pt", arrays, spec, combined, args, args.device)
    phase2.net.eval(); point.net.eval()
    if phase2.net.encoder.scalar_mean.data_ptr() == point.net.encoder.scalar_mean.data_ptr():
        raise AssertionError("models share normalization buffers")
    frozen_states = [base._safe_state_dict(model.net) for model in (phase2, point)]
    ids = groups[2]
    with torch.inference_mode():
        metrics_a = base._evaluate_core(phase2, arrays, spec, ids, args.nn_batch, "phase2")
        pred_a = metrics_a.pop("predictions")
        survival_b, _ = base._point_predict(point, arrays, ids, args.nn_batch)
    pred_b = compose_predictions(pred_a, survival_b)
    for key in ("pDelta", "hpConditional", "pHpBins"):
        probabilities = pred_a[key]
        if (not np.all(np.isfinite(probabilities)) or np.any(probabilities < 0)
                or not np.allclose(probabilities.sum(-1), 1, atol=1e-6)):
            raise ValueError(f"unnormalized conditional distribution: {key}")
    np.savez_compressed(output / "frozen_predictions.npz", **pred_a, pointSurvival=survival_b)
    metrics_b = base._core_metrics(arrays, ids, pred_b["pWin"], pred_b["expectedHpFraction"], pred_b["expectedHp"])
    metrics_b["hpDistribution"] = copy.deepcopy(metrics_a["hpDistribution"])
    historical = json.loads((artifacts / "attention_ablation_evidence.json").read_text())
    reproduction = {}
    for group in ("survival", "winningExpectedHpFraction", "jointAliveHpFraction", "winningExpectedHp", "jointAliveHp", "hpDistribution"):
        for metric, value in metrics_a[group].items():
            reference = historical["test"]["phase2"][group].get(metric)
            if isinstance(value, (float, int)) and isinstance(reference, (float, int)):
                delta = abs(value - reference)
                reproduction[f"{group}.{metric}"] = delta
                if delta > 1e-5:
                    raise ValueError(f"A reproduction discrepancy: {group}.{metric} {delta}")
    historical_point = historical["test"]["pointControl"]["survival"]
    for metric in ("brier", "logloss"):
        if abs(metrics_b["survival"][metric] - historical_point[metric]) > 1e-5:
            raise ValueError(f"point survival reproduction discrepancy: {metric}")
    for key in pred_a:
        if key != "pWin" and pred_b[key] is not pred_a[key]:
            raise AssertionError(f"composition changed {key}")
    nll_a, nll_b = joint_nll(arrays, ids, pred_a), joint_nll(arrays, ids, pred_b)
    outcome_delta = outcome_nll(arrays["y_win"][ids], survival_b) - outcome_nll(arrays["y_win"][ids], pred_a["pWin"])
    identity_error = float(np.max(np.abs((nll_b - nll_a) - outcome_delta)))
    if identity_error > 1e-10:
        raise AssertionError("joint NLL identity failed")
    metrics_a["jointOutcomeMaxHpHpBinNll"] = float(nll_a.mean())
    metrics_b["jointOutcomeMaxHpHpBinNll"] = float(nll_b.mean())
    win = arrays["y_win"][ids] == 1
    y = arrays["y_win"][ids]
    target = np.nan_to_num(arrays["y_hp"][ids], nan=0.)
    differences = {"survivalBrier": (survival_b - y) ** 2 - (pred_a["pWin"] - y) ** 2,
        "outcomeNll": outcome_delta, "jointOutcomeMaxHpHpBinNll": nll_b - nll_a,
        "jointAliveHpFractionMae": np.abs(survival_b * pred_a["expectedHpFraction"] - y * target)
            - np.abs(pred_a["pWin"] * pred_a["expectedHpFraction"] - y * target),
        "jointAliveHpMae": np.abs(survival_b * pred_a["expectedHp"] - y * arrays["y_post_hp"][ids])
            - np.abs(pred_a["pWin"] * pred_a["expectedHp"] - y * arrays["y_post_hp"][ids])}
    composition_deltas = paired_bootstrap(arrays["sourceSeed"][ids], differences)
    unchanged_deltas = paired_bootstrap(arrays["sourceSeed"][ids[win]], {
        "winningExpectedHpFractionMae": np.zeros(win.sum()), "winningExpectedHpMae": np.zeros(win.sum()),
        "hpCrps": np.zeros(win.sum())})
    winids = ids[win]
    slots = arrays["potions"][winids, :, 1]
    caps = arrays["potionCapacity"][winids]
    cert = certified[winids]
    actual = arrays["y_potions"][winids]
    logits = pred_a["potionLogits"][win]
    log_b = potion_log_probabilities(logits, slots, caps)
    log_c = potion_log_probabilities(logits, slots, caps, cert)
    if not np.array_equal(log_b[~cert], log_c[~cert]):
        raise AssertionError("C changed uncertified predictions")
    scores_b = potion_row_scores(log_b, actual, slots, caps)
    scores_c = potion_row_scores(log_c, actual, slots, caps)
    if np.any(scores_c["vectorNll"][cert] > scores_b["vectorNll"][cert] + 1e-10):
        raise AssertionError("certified mask worsened NLL")
    masks = {"overall": np.ones(len(winids), dtype=bool), "certified": cert, "uncertified": ~cert}
    potions = {name: {"B": compact_potions(scores_b, mask), "C": compact_potions(scores_c, mask),
        "CminusB": paired_bootstrap(arrays["sourceSeed"][winids[mask]], {
            key: scores_c[key][mask] - scores_b[key][mask]
            for key in ("vectorNll", "exact", "noChangeBrier")}) if mask.any() else {}}
        for name, mask in masks.items()}
    allowed = allowed_potion_support(slots, caps)
    allowed_mass = np.where(allowed, np.exp(log_b), 0.).sum(-1)
    invalid_mass = -np.expm1(np.log(allowed_mass).sum(-1))
    modes = log_b.argmax(-1)
    illegal_mode = ~allowed[np.arange(len(slots))[:, None], np.arange(5)[None, :], modes].all(-1)
    potions["originalInvalidSupport"] = {"certifiedRows": int(cert.sum()),
        "meanInvalidVectorMass": float(invalid_mass[cert].mean()) if cert.any() else None,
        "invalidVectorMassQuantiles": np.quantile(invalid_mass[cert], [.05, .5, .95]).tolist() if cert.any() else [],
        "illegalVectorModeRate": float(illegal_mode[cert].mean()) if cert.any() else None}
    transition = base._transition_metrics(arrays, spec, ids, pred_a, len(ids))
    reference_potion_exact = historical["test"]["transition"]["potions"]["exactFullVectorAccuracy"]
    if abs(scores_b["exact"].mean() - reference_potion_exact) > 1e-5:
        base.json_dump(output / "reproduction_failure.json", {"core": reproduction,
            "currentPotionExact": float(scores_b["exact"].mean()), "historicalPotionExact": reference_potion_exact,
            "helperPotionExact": transition["potions"]["exactFullVectorAccuracy"]})
        raise ValueError(f"historical potion mode reproduction failed: current={scores_b['exact'].mean()} reference={reference_potion_exact} historicalHelper={transition['potions']['exactFullVectorAccuracy']}")
    # Inspect concrete counter restrictions from native code, without expanding
    # the historical adapter. These are residual diagnostic violations only.
    _, relic_mode, _ = base._masked_relic_probabilities(pred_a["relicLogits"][win], arrays, winids, spec)
    counter = arrays["relics"][winids, :, 1].astype(np.int32) + relic_mode
    rid = arrays["relics"][winids, :, 0]
    violations = {}
    for name, lower, upper in (("HAPPY_FLOWER", 0, 2), ("NUNCHAKU", 0, 9), ("INK_BOTTLE", 0, 9), ("SUNDIAL", 0, 2)):
        mask = arrays["relic_mask"][winids] & (rid == base._RELIC_IDS[name])
        invalid = mask & ((counter < lower) | (counter > upper))
        violations[name] = {"presentTokens": int(mask.sum()), "invalidModeCounters": int(invalid.sum()),
            "range": [lower, upper], "examples": [
                {"rowIndex": int(winids[row]), "sourceSeed": int(arrays["sourceSeed"][winids[row]]),
                 "preCounter": int(arrays["relics"][winids[row], token, 1]),
                 "modeDelta": int(relic_mode[row, token]), "modeCounter": int(counter[row, token])}
                for row, token in np.argwhere(invalid)[:3]]}
    validity = {"relicModeCounterRangeViolations": violations,
        "maxHpModeNonpositive": int(np.sum(arrays["preMaxHp"][winids] + np.asarray(spec["maxHpDeltaValues"])[pred_a["pDelta"][win].argmax(-1)] <= 0)),
        "limits": "Historical deltas do not establish state-dependent legality; RNG/native continuation and ancestral qualification remain absent."}
    cost = measure_cpu_cost(phase2, point, arrays, examples, spec)
    for before, model in zip(frozen_states, (phase2, point)):
        after = base._safe_state_dict(model.net)
        if not all(torch.equal(before[key], after[key]) for key in before):
            raise AssertionError("frozen parameters/buffers changed")
    # These diagnostics are finite, prespecified engineering reuse of TEST.
    # A support correction is useful only with accuracy and calibration as well
    # as NLL improvement; residual failure versus copy-through is explicit.
    overall_b = potions["overall"]["B"]
    overall_c = potions["overall"]["C"]
    if not cert.any():
        mask_decision = "UNCERTIFIED/CONTRADICTED_RULE"
    elif (overall_c["vectorNll"] < overall_b["vectorNll"] and
          overall_c["exact"] > overall_b["exact"] and
          overall_c["noChangeBrier"] < overall_b["noChangeBrier"] and
          overall_c["exact"] > overall_c["copyThroughExact"]):
        mask_decision = "USEFUL_SUPPORT_CORRECTION"
    else:
        mask_decision = "INSUFFICIENT_AFTER_CORRECTION"
    evidence = {"schemaVersion": "frozen_survival_potion_diagnostic_v1", "baselineSha": args.baseline_sha,
        "executionSha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "sourceHashes": {str(path.relative_to(ROOT)): base.sha256(path) for path in (
            Path(__file__), ROOT / "tools/combat_transition_attention_ablation.py",
            ROOT / "tools/combat_transition_surrogate.py", ROOT / "include/constants/Cards.h",
            ROOT / "include/constants/CardPools.h", ROOT / "src/game/Game.cpp",
            ROOT / "src/combat/BattleContext.cpp", ROOT / "src/combat/Actions.cpp",
            ROOT / "src/combat/Player.cpp")},
        "hashes": hashes, "preparedArrays": str((prepared / "prepared.npz").resolve()),
        "corpus": str(corpus), "sourceSplit": str(split_path), "ruleAudit": audit,
        "rule": "Ironclad; RED/COLORLESS/CURSE visible cards only; no Entropic Brew; current native pool closure",
        "protocol": {"noTraining": True, "noNewSeeds": True, "fp32Inference": True,
            "device": args.device, "batch": args.nn_batch, "inferenceThreads": args.threads,
            "test": "prespecified engineering diagnostic on reused fixed TEST; final checkpoints fitted on TRAIN+VALIDATION",
            "bootstrap": "1000 paired source resamples; measures TEST-source variability, not training-seed variability"},
        "reproductionAbsoluteDifferences": reproduction, "composition": {"A": metrics_a, "B": metrics_b,
            "BminusA": composition_deltas, "BminusAConditional": unchanged_deltas,
            "jointNllIdentityMaxError": identity_error, "coreAndConditionalPreserved": True,
            "frozenParametersAndBuffersUnchanged": True},
        "potions": potions, "historicalTransitionMetrics": transition, "validity": validity,
        "cost": cost, "decision": {"composition": "REPRODUCED_AND_CORE_PRESERVED",
            "potionMask": mask_decision, "deployment": "NOT_QUALIFIED"}}
    base.json_dump(output / "frozen_composition_evidence.json", evidence)
    np.savez_compressed(output / "paired_row_scores.npz", sourceSeed=arrays["sourceSeed"][ids],
        testRowIndex=ids, victory=win, certified=certified[ids], pWinA=pred_a["pWin"], pWinB=survival_b,
        jointNllA=nll_a, jointNllB=nll_b,
        **{f"potionB_{k}": v for k, v in scores_b.items()},
        **{f"potionC_{k}": v for k, v in scores_c.items()})
    print(json.dumps(evidence["decision"], indent=2), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared-dir", required=True)
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--split-manifest", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    parser.add_argument("--nn-batch", type=int, default=2048)
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--training-seed", type=int, default=20260912,
                        help="loader initialization only; no fitting")
    parser.add_argument("--baseline-sha", required=True)
    args = parser.parse_args()
    args.training_precision = "fp32"
    run(args)


if __name__ == "__main__":
    main()
