#!/usr/bin/env python3
"""CPU speed screen for the qualified shared Attention and DeepSets encoders."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

import numpy as np
import torch

from tools import combat_transition_composed as c
from tools import combat_transition_composed_evaluate as composed_evaluate
from tools import combat_transition_deepset_distill as deepset
from tools import combat_transition_potion_trajectory_evaluate as trajectory
from tools import combat_transition_shared_encoder_distill as reference
from tools import combat_transition_stochastic_hp as stochastic_hp


def _summary(samples):
    values = np.asarray(samples, dtype=np.float64) * 1000.0
    return dict(
        repetitions=int(len(values)), medianMs=float(np.median(values)),
        iqrMs=[float(np.percentile(values, 25)), float(np.percentile(values, 75))],
        madMs=float(np.median(np.abs(values - np.median(values)))),
    )


def _load_models(candidate_dir, control_dir, cache, arrays, train, classes, delta_values):
    mean, std, _ = deepset.normalization_stats(cache, arrays, train)
    candidate = deepset._student_model(torch, mean, std, len(delta_values), classes, 20260912).eval()
    candidate_payload = torch.load(Path(candidate_dir) / "student.pt", map_location="cpu", weights_only=False)
    candidate.load_state_dict(candidate_payload["stateDict"])
    candidate_head = torch.nn.Linear(64, len(delta_values))
    candidate_head.load_state_dict(candidate_payload["maxHpHeadStateDict"])
    candidate_head.eval()

    attention = stochastic_hp.new_model(torch, np.zeros(len(c.base.CONTINUOUS_GLOBAL_FIELDS), np.float32), np.ones(len(c.base.CONTINUOUS_GLOBAL_FIELDS), np.float32), len(delta_values), classes, 20260912).eval()
    attention_payload = torch.load(Path(control_dir) / "best_epoch.pt", map_location="cpu", weights_only=False)
    attention.load_state_dict(attention_payload["stateDict"])
    attention_head = torch.nn.Linear(64, len(delta_values))
    attention_head.load_state_dict(attention_payload["maxHpHeadStateDict"])
    attention_head.eval()
    return {
        "DeepSets": (candidate.encoder, candidate.hp, candidate.delta_embedding, candidate_head),
        "Attention": (attention.encoder, attention.hp, attention.delta_embedding, attention_head),
    }


def run(args):
    torch.set_num_threads(args.threads)
    cache, _, _ = trajectory.load(Path(args.artifact_root) / "potion-trajectory-v2")
    arrays, spec = c.base._load_prepared(composed_evaluate.PREPARED)
    c.base._prepare_target_indices(arrays, spec)
    train = np.flatnonzero(cache["win"] & (cache["split"] == 0))
    validation = np.flatnonzero(cache["win"] & (cache["split"] == 1))
    classes = np.arange(-160, 144, dtype=np.int64)
    delta_values = np.asarray(spec["maxHpDeltaValues"], dtype=np.int64)
    batch_ids = validation[:args.batch]
    inputs = c.base._torch_inputs(arrays, cache["ids"][batch_ids], "cpu", torch, trim_padding=True)
    delta = torch.as_tensor(cache["delta"][batch_ids], dtype=torch.long)
    pre = torch.as_tensor(cache["preHp"][batch_ids], dtype=torch.long)
    maximum = torch.as_tensor(cache["trueMax"][batch_ids], dtype=torch.long)
    legal = torch.as_tensor(stochastic_hp.legal_support(classes, cache["preHp"][batch_ids], cache["trueMax"][batch_ids]))
    models = _load_models(args.candidate_dir, args.control_dir, cache, arrays, train, classes, delta_values)
    result = dict(schema="combat_transition_deepset_speed_screen_v1", candidateSha=args.candidate_sha, controlSha=args.control_sha, corpusRows=0, testInferenceRows=0, batchRows=int(len(batch_ids)), validationRowIdsSha256=deepset.digest_array(cache["ids"][batch_ids]), threads=args.threads, warmups=args.warmups, repetitions=args.repetitions, timings={})

    def encoder_forward(parts):
        encoder, _, _, _ = parts
        with c.attention_backend(torch, False):
            return encoder(*inputs)

    def complete_forward(parts):
        encoder, hp, delta_embedding, max_head = parts
        with c.attention_backend(torch, False):
            z = encoder(*inputs)
            max_logits = max_head(z).float()
            hp_logits = hp(torch.cat((z, delta_embedding(delta)), -1)).float()
        return max_logits, hp_logits.masked_fill(~legal, -torch.inf)

    for name, parts in models.items():
        with torch.inference_mode():
            for _ in range(args.warmups):
                encoder_forward(parts); complete_forward(parts)
            encoder_samples = []
            complete_samples = []
            for _ in range(args.repetitions):
                start = time.perf_counter()
                encoder_forward(parts)
                encoder_samples.append(time.perf_counter() - start)
                start = time.perf_counter()
                complete_forward(parts)
                complete_samples.append(time.perf_counter() - start)
        encoder, hp, delta_embedding, max_head = parts
        result["timings"][name] = dict(
            encoder=_summary(encoder_samples), completeMaxHpHp=_summary(complete_samples),
            parameterCount=dict(encoder=deepset.parameter_count(encoder), hpBranch=deepset.parameter_count(hp) + deepset.parameter_count(delta_embedding), maxHpHead=deepset.parameter_count(max_head), complete=deepset.parameter_count(encoder) + deepset.parameter_count(hp) + deepset.parameter_count(delta_embedding) + deepset.parameter_count(max_head)),
        )
    result["speedup"] = dict(
        encoder=float(result["timings"]["Attention"]["encoder"]["medianMs"] / result["timings"]["DeepSets"]["encoder"]["medianMs"]),
        completeMaxHpHp=float(result["timings"]["Attention"]["completeMaxHpHp"]["medianMs"] / result["timings"]["DeepSets"]["completeMaxHpHp"]["medianMs"]),
    )
    Path(args.output).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--candidate-dir", required=True)
    parser.add_argument("--control-dir", required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--control-sha", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--batch", type=int, default=512)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--warmups", type=int, default=10)
    parser.add_argument("--repetitions", type=int, default=100)
    run(parser.parse_args())
