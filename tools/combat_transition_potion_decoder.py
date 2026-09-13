#!/usr/bin/env python3
"""Prospective TRAIN-nested potion decoder experiment. No simulator collection.

Separate prepare/fit commands freeze source membership and recipe before fitting.
HOLDOUT is scored only after validation epochs are committed to selection.json.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import time
from pathlib import Path
import numpy as np
try:
    from tools import combat_transition_surrogate as base
    from tools import combat_transition_attention_ablation as attention
    from tools import combat_transition_frozen_composition as frozen
except ModuleNotFoundError:
    import combat_transition_surrogate as base
    import combat_transition_attention_ablation as attention
    import combat_transition_frozen_composition as frozen

SALT = 'sts-potion-decoder-nested-v1-20260913'
RECIPE = {'schema': 'potion_decoder_v1', 'salt': SALT, 'seed': 20260912,
          'precision': 'fp32', 'encoderEpochs': 10, 'width': 64,
          'layers': 2, 'heads': 4, 'ffWidth': 128,
          'decoderHidden': 64, 'potionEmbedding': 8, 'slotEmbedding': 4,
          'deltaEmbedding': 8, 'optimizer': 'AdamW', 'lr': 1e-3,
          'weightDecay': 1e-4, 'batch': 2048, 'maxEpochs': 12,
          'patience': 3, 'selection': 'validation joint mask NLL; earliest strict minimum',
          'refit': 'decoder TRAIN+VALIDATION; encoder remains TRAIN only',
          'bootstrapReps': 1000, 'bootstrapSeed': 20260913,
          'ancestralDraws': 16, 'samplingSeed': 20260914,
          'ancestralGapRule': 'exposure gap if ancestral mixture target NLL exceeds teacher-forced NLL by >0.1 for primary preferred decoder'}
BITS = ((np.arange(32)[:, None] >> np.arange(5)) & 1).astype(bool)

def nested_manifest(original: dict) -> dict:
    members = {'train': [], 'validation': [], 'holdout': []}
    sources = sorted(map(int, original['members']['train']))
    if len(sources) != len(set(sources)):
        raise ValueError('duplicate original TRAIN source')
    for source in sources:
        value = int.from_bytes(hashlib.sha256(f'{SALT}:{source}'.encode()).digest()[:8], 'big') / 2**64
        name = 'train' if value < .8 else 'validation' if value < .9 else 'holdout'
        members[name].append(source)
    return {'schema': 'source_grouped_nested_decoder_v1', 'salt': SALT,
            'originalSplitSha256': attention.EXPECTED_SPLIT_SHA256, 'members': members}

def legal_masks(pre, capacity):
    pre, capacity = np.asarray(pre), np.asarray(capacity)
    frozen.allowed_potion_support(pre, capacity)  # strict native domain checks
    active = (pre > base.EMPTY_POTION_SLOT_ID) & (np.arange(5) < capacity[:, None])
    return ~np.any(BITS[None] & ~active[:, None], axis=-1)

def encode_masks(pre, post, capacity):
    pre, post = np.asarray(pre), np.asarray(post)
    allowed = frozen.allowed_potion_support(pre, capacity)
    if post.shape != pre.shape or not np.array_equal(post, post.astype(np.int64)) or np.any(post < 1) or np.any(post >= base.POTION_COUNT):
        raise ValueError('invalid potion target')
    if not allowed[np.arange(len(pre))[:, None], np.arange(5), post.astype(int)].all():
        raise ValueError('potion creation/swap or unavailable mutation')
    consumed = pre != post
    masks = (consumed * (1 << np.arange(5))).sum(-1).astype(np.int64)
    if not legal_masks(pre, capacity)[np.arange(len(pre)), masks].all():
        raise ValueError('unrepresentable potion target')
    return masks

def decode_masks(pre, capacity, masks):
    masks = np.asarray(masks)
    if masks.shape != (len(pre),) or np.any(masks != masks.astype(int)) or np.any((masks < 0) | (masks > 31)):
        raise ValueError('invalid mask')
    masks = masks.astype(int)
    if not legal_masks(pre, capacity)[np.arange(len(pre)), masks].all():
        raise ValueError('impossible mask')
    return np.where(BITS[masks], base.EMPTY_POTION_SLOT_ID, pre)

def new_decoder(kind, delta_count, seed=20260912):
    import torch
    from torch import nn
    if kind not in ('independent', 'joint'):
        raise ValueError('unknown decoder')
    torch.manual_seed(seed)
    class Decoder(nn.Module):
        def __init__(self):
            super().__init__()
            self.delta = nn.Embedding(delta_count, 8)
            self.potion = nn.Embedding(base.POTION_COUNT, 8)
            self.slot = nn.Embedding(5, 4)
            self.mlp = nn.Sequential(nn.Linear(64 + 8 + 1 + (12 if kind == 'independent' else 60), 64), nn.ReLU(), nn.Linear(64, 1 if kind == 'independent' else 32))
        def forward(self, z, pre, capacity, delta, hp):
            shared = torch.cat((z.detach(), self.delta(delta), hp[:, None]), -1)
            inventory = torch.cat((self.potion(pre), self.slot.weight[None].expand(len(z), -1, -1)), -1)
            active = (pre > 1) & (torch.arange(5, device=z.device)[None] < capacity[:, None])
            bits = torch.as_tensor(BITS, device=z.device)
            if kind == 'independent':
                logits = self.mlp(torch.cat((shared[:, None].expand(-1, 5, -1), inventory), -1)).squeeze(-1)
                yes = torch.nn.functional.logsigmoid(logits)
                no = torch.nn.functional.logsigmoid(-logits)
                terms = torch.where(bits[None], yes[:, None], no[:, None])
                logp = torch.where(active[:, None], terms, 0).sum(-1)
            else:
                logp = self.mlp(torch.cat((shared, inventory.flatten(1)), -1))
            legal = ~torch.any(bits[None] & ~active[:, None], -1)
            return torch.log_softmax(logp.masked_fill(~legal, -torch.inf), -1)
    return Decoder()

def conditioning(arrays, ids, sampled=None):
    """Teacher-forced by default; ancestral values must be supplied explicitly."""
    if sampled is None:
        return arrays['delta_index'][ids].astype(np.int64), arrays['y_hp'][ids].astype(np.float32)
    delta, hp = sampled
    if np.asarray(delta).shape != (len(ids),) or np.asarray(hp).shape != (len(ids),) or not np.isfinite(hp).all() or np.any((hp < 0) | (hp > 1)):
        raise ValueError('invalid sampled conditioning')
    return np.asarray(delta, dtype=np.int64), np.asarray(hp, dtype=np.float32)

def decoder_inputs(arrays, z, ids, device, sampled=None):
    import torch
    delta, hp = conditioning(arrays, ids, sampled)
    data = (z[ids], arrays['potions'][ids, :, 1].astype(np.int64), arrays['potionCapacity'][ids].astype(np.int64), delta, hp)
    return tuple(torch.from_numpy(x).to(device) for x in data)

def predict(model, arrays, z, ids, sampled=None):
    import torch
    model.eval()
    out = []
    with torch.inference_mode():
        for start in range(0, len(ids), RECIPE['batch']):
            subset = ids[start:start + RECIPE['batch']]
            upstream = None if sampled is None else tuple(x[start:start + len(subset)] for x in sampled)
            out.append(model(*decoder_inputs(arrays, z, subset, next(model.parameters()).device, upstream)).cpu().numpy().astype(np.float64))
    return np.concatenate(out)

def train_decoder(kind, arrays, spec, z, targets, train, validation, device, epochs=None):
    import torch
    model = new_decoder(kind, len(spec['maxHpDeltaValues'])).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=RECIPE['lr'], weight_decay=RECIPE['weightDecay'])
    rng = np.random.default_rng(RECIPE['seed'])
    history, best, selected, stale = [], float('inf'), None, 0
    for epoch in range(1, (epochs or RECIPE['maxEpochs']) + 1):
        model.train()
        for ids in base._batches(train, RECIPE['batch'], rng):
            logp = model(*decoder_inputs(arrays, z, ids, device))
            y = torch.from_numpy(targets[ids]).to(device)
            loss = -logp[torch.arange(len(ids), device=device), y].mean()
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.)
            optimizer.step()
        if epochs is not None:
            continue
        logp = predict(model, arrays, z, validation)
        nll = float(-logp[np.arange(len(validation)), targets[validation]].mean())
        history.append({'epoch': epoch, 'jointNll': nll})
        print(kind, history[-1], flush=True)
        if nll < best:
            best, selected, stale = nll, epoch, 0
        else:
            stale += 1
        if stale >= RECIPE['patience']:
            break
    return model, selected, history

def scores(logp, target):
    prob = np.exp(logp)
    mode = logp.argmax(-1)
    counts = BITS.sum(-1)
    return {'jointNll': -logp[np.arange(len(target)), target],
            'exact': (mode == target).astype(float), 'changed': target != 0,
            'noChangeBrier': (prob[:, 0] - (target == 0))**2,
            'zeroProbability': prob[:, 0], 'countExact': (counts[mode] == counts[target]).astype(float)}

def compact(logp, targets):
    s = scores(logp, targets)
    result = {k: float(v.mean()) for k, v in s.items() if k != 'changed'}
    result['rows'] = len(targets)
    result['copyThroughExact'] = float((targets == 0).mean())
    for name, mask in [('changed', targets != 0), ('unchanged', targets == 0)]:
        result[name] = {'rows': int(mask.sum()), 'exact': float(s['exact'][mask].mean()) if mask.any() else None}
    counts = BITS.sum(-1)
    countp = np.stack([np.exp(logp)[:, counts == n].sum(-1) for n in range(6)], -1)
    result['countCalibration'] = [{'count': n, 'meanProbability': float(countp[:, n].mean()), 'observedFrequency': float((counts[targets] == n).mean()), 'brier': float(((countp[:, n] - (counts[targets] == n))**2).mean())} for n in range(6)]
    mode_counts = counts[logp.argmax(-1)]
    result['calibrationByPredictedCount'] = [{'predictedModeCount': n, 'rows': int((mode_counts == n).sum()),
        'meanObservedCount': float(counts[targets][mode_counts == n].mean()) if np.any(mode_counts == n) else None,
        'meanExpectedCount': float((countp[mode_counts == n] * np.arange(6)).sum(-1).mean()) if np.any(mode_counts == n) else None} for n in range(6)]
    result['copyThroughNoChangeBrier'] = float((targets != 0).mean())
    return result

def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')

def prepare(args):
    original_path, prepared, output = Path(args.split_manifest), Path(args.prepared_dir), Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    if base.sha256(original_path) != attention.EXPECTED_SPLIT_SHA256:
        raise ValueError('original split hash differs')
    manifest = nested_manifest(json.loads(original_path.read_text()))
    arrays, _ = base._load_prepared(prepared)
    for key in ('prepared.npz', 'prepared_manifest.json', 'target_spec.json'):
        if base.sha256(prepared / key) != frozen.EXPECTED_HASHES[key]:
            raise ValueError('prepared hash differs')
    manifest['rowCounts'] = {name: int(np.isin(arrays['sourceSeed'], sources).sum()) for name, sources in manifest['members'].items()}
    manifest['supportedRowCounts'] = {name: int((np.isin(arrays['sourceSeed'], sources) & arrays['supported']).sum()) for name, sources in manifest['members'].items()}
    for name, value in [('nested_split.json', manifest), ('recipe.json', RECIPE)]:
        path = output / name
        if path.exists() and json.loads(path.read_text()) != value:
            raise ValueError('refusing to replace frozen preregistration')
        write(path, value)
    print(json.dumps({'splitSha256': base.sha256(output / 'nested_split.json'), 'recipeSha256': base.sha256(output / 'recipe.json'), 'sources': {k: len(v) for k, v in manifest['members'].items()}, 'rows': manifest['rowCounts']}))

def ancestral(model, arrays, z, ids, upstream, targets, spec):
    rng = np.random.default_rng(RECIPE['samplingSeed'])
    draws, changed_mode, consumed, nochange, invalid = [], [], [], [], 0
    truth_mode = predict(model, arrays, z, ids).argmax(-1)
    for _ in range(RECIPE['ancestralDraws']):
        delta = np.array([rng.choice(len(p), p=p / p.sum()) for p in upstream['pDelta']], dtype=np.int64)
        bins = np.array([rng.choice(base.HP_BIN_COUNT, p=p / p.sum()) for p in upstream['hpConditional'][np.arange(len(ids)), delta]])
        maxhp = arrays['preMaxHp'][ids] + np.asarray(spec['maxHpDeltaValues'])[delta]
        if np.any(maxhp <= 0):
            raise ValueError('invalid ancestral maxHP')
        rawhp = np.maximum(1, np.minimum(maxhp, base._round_half_up_vector(bins / 100 * maxhp)))
        hp = (rawhp / maxhp).astype(np.float32)
        logp = predict(model, arrays, z, ids, (delta, hp))
        draws.append(logp)
        changed_mode.append((logp.argmax(-1) != truth_mode).mean())
        prob = np.exp(logp)
        mask = np.array([rng.choice(32, p=p / p.sum()) for p in prob])
        post = decode_masks(arrays['potions'][ids, :, 1], arrays['potionCapacity'][ids], mask)
        if not np.array_equal(encode_masks(arrays['potions'][ids, :, 1], post, arrays['potionCapacity'][ids]), mask):
            invalid += 1
        consumed.append(BITS[mask].sum(-1))
        nochange.append((mask == 0).mean())
    stacked = np.stack(draws)
    maximum = stacked.max(0)
    finite = np.isfinite(maximum)
    safe_max = np.where(finite, maximum, 0)
    with np.errstate(divide='ignore'):
        mixture = safe_max + np.log(np.exp(stacked - safe_max).mean(0))
    mixture[~finite] = -np.inf
    conditional = [-p[np.arange(len(ids)), targets].mean() for p in draws]
    return {'drawsPerRow': RECIPE['ancestralDraws'], 'structurallyInvalid': invalid, 'identityCreationOrSwap': 0,
            'meanConditionalJointNll': float(np.mean(conditional)),
            'mixtureJointNll': float(-mixture[np.arange(len(ids)), targets].mean()),
            'modeChangeFraction': float(np.mean(changed_mode)), 'noChangeFrequency': float(np.mean(nochange)),
            'consumedCountFrequency': (np.bincount(np.concatenate(consumed), minlength=6) / (len(ids) * RECIPE['ancestralDraws'])).tolist()}

def sample_composed(pre, pwin, upstream, decoder, z, spec, rng):
    """Early death termination; never calls a decoder or upstream draw on death."""
    if not np.isfinite(pwin) or not 0 <= pwin <= 1:
        raise ValueError('invalid survival')
    if rng.random() >= pwin:
        return None
    import torch
    delta = int(rng.choice(len(upstream['pDelta']), p=upstream['pDelta']))
    hpbin = int(rng.choice(base.HP_BIN_COUNT, p=upstream['hpConditional'][delta]))
    maxhp = int(pre['maxHp']) + int(spec['maxHpDeltaValues'][delta])
    if maxhp <= 0:
        raise ValueError('invalid sampled maxHP')
    hp = max(1, min(maxhp, base._round_half_up(hpbin / 100 * maxhp)))
    device = next(decoder.parameters()).device
    args = (np.asarray(z, dtype=np.float32)[None], np.asarray(pre['potions'], dtype=np.int64)[None], np.asarray([pre['potionCapacity']], dtype=np.int64), np.asarray([delta], dtype=np.int64), np.asarray([hp / maxhp], dtype=np.float32))
    with torch.inference_mode():
        prob = decoder(*(torch.from_numpy(v).to(device) for v in args)).exp().cpu().numpy()[0].astype(float)
    mask = int(rng.choice(32, p=prob / prob.sum()))
    return {'curHp': hp, 'maxHp': maxhp, 'potions': decode_masks(args[1], args[2], [mask])[0].tolist(), 'mask': mask}

def composed_latency(models, encoder, phase2, point, arrays, ids, spec, corpus):
    import copy
    import torch
    try:
        from tools import combat_transition_relic_legality as relic
    except ModuleNotFoundError:
        import combat_transition_relic_legality as relic
    row_id = int(ids[0])
    source, fight = int(arrays['sourceSeed'][row_id]), int(arrays['fightIdx'][row_id])
    fixture = next(row for row in base.iter_rows(corpus) if int(row['sourceSeed']) == source and int(row['fightIdx']) == fight)
    pre = fixture['transition']['pre']
    for wrapper in (encoder, phase2, point): wrapper.net.cpu().eval()
    results = {}
    def draw(model, rng):
        # Include visible-input encoding, three distinct frozen encoder forwards,
        # adapters and one complete supported persistent-state draw (RNG excluded).
        g, gc, c, r, p, cm, rm = base._encode_row(fixture)[:7]
        tensors = tuple(torch.from_numpy(np.asarray(x)[None]).cpu() for x in (g,gc,c,r,p,cm,rm))
        survival, _ = point.net(*tensors)
        pwin = float(torch.sigmoid(survival)[0])
        if rng.random() >= pwin: return None
        z = encoder.net.encoder(*tensors)[0].numpy()
        _, dl, hp, _, rl = phase2.net(*tensors)
        upstream = {'pDelta': base._softmax(dl.numpy())[0], 'hpConditional': base._softmax(hp.numpy())[0]}
        sampled = sample_composed(pre, 1., upstream, model, z, spec, rng)
        post = {key: copy.deepcopy(pre[key]) for key in base.PERSISTENT_KEYS}
        post.update({key: sampled[key] for key in ('curHp','maxHp','potions')})
        post['potionCount'] = sum(p > 1 for p in post['potions'])
        for token, entry in enumerate(post['relics']):
            rid = int(entry['id'])
            if rid not in relic.NAMES: continue
            logits = rl[0,token].numpy()
            legacy = np.isin(spec['relicDeltaValues'], spec['relicDeltaValuesById'][str(rid)])
            # Native legality helper rejects nonfinite inputs, so form intersection
            # explicitly here, preserving historical per-relic delta support.
            legal = np.isin(entry['data'] + np.asarray(spec['relicDeltaValues']), list(relic.legal_posts(rid, entry['data'], fixture['predictorInput']['globals']['encounter'], any(r['relicId'] == base._RELIC_IDS['MARK_OF_THE_BLOOM'] for r in fixture['predictorInput']['relics'])))) & legacy
            if not legal.any(): raise ValueError('empty relic intersection')
            mass = base._softmax(np.where(legal, logits, -np.inf)).astype(float)
            delta = rng.choice(spec['relicDeltaValues'], p=mass/mass.sum())
            entry['data'] += int(delta)
        return post
    with torch.inference_mode():
        for kind, model in models.items():
            model.cpu().eval()
            rng = np.random.default_rng(RECIPE['samplingSeed'])
            for _ in range(10): draw(model, rng)
            times, deaths = [], 0
            for _ in range(100):
                start = time.perf_counter()
                post = draw(model, rng)
                times.append((time.perf_counter()-start)*1000)
                deaths += post is None
            results[kind] = {'meanMs': float(np.mean(times)), 'p95Ms': float(np.quantile(times,.95)), 'draws':100, 'warmups':10, 'deathDraws':deaths, 'batch':1, 'threads':1,
                             'boundary': 'visible encoding, frozen point survival, TRAIN-only state encoder, frozen Phase-2 upstream, decoder, constrained relics, persistent-state draw; RNG excluded'}
    return results

def validate_review_sha(code, reviewed, current):
    if not code or not reviewed or reviewed != code or code != current:
        raise ValueError('fit requires the current frozen independently reviewed SHA')

def fit(args):
    import torch
    try:
        from tools import combat_transition_relic_legality as relic
    except ModuleNotFoundError:
        import combat_transition_relic_legality as relic
    output, prepared, artifacts = Path(args.output_dir), Path(args.prepared_dir), Path(args.artifact_dir)
    validate_review_sha(args.code_sha, args.reviewed_sha, __import__('subprocess').check_output(['git', 'rev-parse', 'HEAD'], text=True).strip())
    if __import__('subprocess').check_output(['git', 'status', '--porcelain'], text=True).strip():
        raise ValueError('fit requires a clean reviewed checkout')
    if (output / 'selection.json').exists() or (output / 'encoder.pt').exists():
        raise ValueError('refusing to repeat or overwrite frozen experiment')
    if json.loads((output / 'recipe.json').read_text()) != RECIPE:
        raise ValueError('recipe differs from frozen implementation')
    if base.sha256(Path(args.split_manifest)) != attention.EXPECTED_SPLIT_SHA256:
        raise ValueError('original source split changed')
    original = json.loads(Path(args.split_manifest).read_text())
    manifest = json.loads((output / 'nested_split.json').read_text())
    expected = nested_manifest(original)
    if manifest['members'] != expected['members'] or manifest['salt'] != SALT:
        raise ValueError('nested split differs')
    for name, expected_hash in frozen.EXPECTED_HASHES.items():
        if base.sha256((artifacts if name.endswith('.pt') else prepared) / name) != expected_hash:
            raise ValueError(f'frozen artifact differs: {name}')
    arrays, spec = base._load_prepared(prepared)
    base._prepare_target_indices(arrays, spec)
    pm = json.loads((prepared / 'prepared_manifest.json').read_text())
    corpus = Path(json.loads(Path(pm['corpusManifest']).read_text())['csv']['path'])
    if base.sha256(corpus) != attention.EXPECTED_CORPUS_SHA256:
        raise ValueError('corpus hash differs')
    audit = relic.audit(corpus)
    write(output / 'relic-audit-fit.json', audit)
    if audit['contradictionCount'] or audit['futureSilverRequired']:
        raise ValueError('native relic gate failed; do not fit')
    certified, potion_audit, _ = frozen.audit_corpus(corpus, arrays, original)
    if int(arrays['supported'].sum()) != 413799:
        raise ValueError('global support changed')
    all_certified = np.flatnonzero(arrays['supported'] & certified)
    targets = np.zeros(len(arrays['y_win']), dtype=np.int64)
    targets[all_certified] = encode_masks(arrays['potions'][all_certified, :, 1], arrays['y_potions'][all_certified], arrays['potionCapacity'][all_certified])
    groups = {name: np.flatnonzero(np.isin(arrays['sourceSeed'], sources) & arrays['supported']) for name, sources in manifest['members'].items()}
    decoder_groups = {name: ids[certified[ids] & (arrays['y_win'][ids] == 1)] for name, ids in groups.items()}
    if any(not len(x) for x in decoder_groups.values()):
        raise ValueError('empty nested group')
    device = base._resolve_device(torch, args.device)
    torch.set_num_threads(args.threads)
    encoder_args = argparse.Namespace(threads=args.threads, training_seed=RECIPE['seed'], nn_batch=RECIPE['batch'], training_precision='fp32')
    # Exactly ten fixed epochs; no validation call and no epoch selection.
    encoder = attention._refit_one('point', arrays, spec, groups['train'], 10, encoder_args, device)
    encoder.net.eval()
    encoder.net.requires_grad_(False)
    for parameter in encoder.net.parameters():
        parameter.grad = None
    torch.save({'family': 'point_control', 'encoder': 'phase1_attention', 'stateDict': base._safe_state_dict(encoder.net), 'recipe': RECIPE, 'trainSources': manifest['members']['train'], 'nestedSplitSha256': base.sha256(output / 'nested_split.json'), 'codeSha': args.code_sha}, output / 'encoder.pt')
    z = np.zeros((len(arrays['y_win']), 64), dtype=np.float32)
    # No HOLDOUT target or scoring is accessed during encoder feature generation.
    with torch.inference_mode():
        for ids in groups.values():
            for start in range(0, len(ids), RECIPE['batch']):
                subset = ids[start:start + RECIPE['batch']]
                z[subset] = encoder.net.encoder(*base._torch_inputs(arrays, subset, device, torch, trim_padding=True)).cpu().numpy()
    np.save(output / 'state_embeddings.npy', z)
    frozen_state = base._safe_state_dict(encoder.net)
    selections = {}
    for kind in ('independent', 'joint'):
        _, epochs, history = train_decoder(kind, arrays, spec, z, targets, decoder_groups['train'], decoder_groups['validation'], device)
        selections[kind] = {'epochs': epochs, 'validationHistory': history}
    write(output / 'selection.json', selections)  # Epoch counts frozen before HOLDOUT prediction.
    models = {}
    combined = np.concatenate([decoder_groups['train'], decoder_groups['validation']])
    for kind in selections:
        models[kind], _, _ = train_decoder(kind, arrays, spec, z, targets, combined, None, device, selections[kind]['epochs'])
        torch.save(models[kind].state_dict(), output / f'{kind}.pt')
    if any(p.grad is not None for p in encoder.net.parameters()) or any(not torch.equal(v, encoder.net.state_dict()[k].cpu()) for k, v in frozen_state.items()):
        raise ValueError('encoder changed or received decoder gradients')
    ids = decoder_groups['holdout']
    predictions = {kind: predict(model, arrays, z, ids) for kind, model in models.items()}
    metrics = {kind: compact(logp, targets[ids]) for kind, logp in predictions.items()}
    differences = scores(predictions['joint'], targets[ids])['jointNll'] - scores(predictions['independent'], targets[ids])['jointNll']
    ci = frozen.paired_bootstrap(arrays['sourceSeed'][ids], {'jointMinusIndependentNll': differences}, RECIPE['bootstrapReps'], RECIPE['bootstrapSeed'])['jointMinusIndependentNll']
    lo, hi = ci['sourceBootstrap95']
    decision = 'JOINT_MASK_WINS' if hi < 0 else 'INDEPENDENT_MASK_WINS' if lo > 0 else 'NO_CLEAR_JOINT_GAIN'
    evidence = {'baselineSha': 'cee9a97a152671bc01c93527307f7d24e2241909', 'reviewedSha': args.reviewed_sha, 'primaryClassification': decision, 'teacherForced': metrics, 'pairedSourceBootstrap': ci,
                'nestedSplitSha256': base.sha256(output / 'nested_split.json'), 'recipeSha256': base.sha256(output / 'recipe.json'), 'encoderSha256': base.sha256(output / 'encoder.pt'), 'encoderTrainSourcesOnly': True, 'encoderUnchangedAndNoGradients': True,
                'selectedEpochs': {k: v['epochs'] for k, v in selections.items()}, 'decoderRows': {k: len(v) for k, v in decoder_groups.items()}, 'potionAudit': potion_audit,
                'parameterCounts': {k: sum(p.numel() for p in m.parameters()) for k, m in models.items()}, 'rngContinuation': 'combatRng[6] remains unmodeled; no native continuation qualification'}
    # Freeze teacher-forced decision before ancestral qualification.
    write(output / 'teacher_forced_decision.json', evidence)
    historical_train = np.flatnonzero(arrays['supported'] & (arrays['split_id'] < 2))
    phase2 = attention._load_checkpoint('phase2', artifacts / 'phase2_attention.pt', arrays, spec, historical_train, encoder_args, device)
    phase2.net.eval()
    upstream = base._evaluate_core(phase2, arrays, spec, ids, RECIPE['batch'], 'phase2')['predictions']
    evidence['ancestral'] = {k: ancestral(m, arrays, z, ids, upstream, targets[ids], spec) for k, m in models.items()}
    preferred = 'joint' if decision == 'JOINT_MASK_WINS' else 'independent'
    gap = evidence['ancestral'][preferred]['mixtureJointNll'] - metrics[preferred]['jointNll']
    evidence['ancestralClassification'] = 'ANCESTRAL_EXPOSURE_GAP' if gap > .1 else 'ANCESTRAL_OK'
    evidence['exposureGapNll'] = gap
    categories = list(base.GLOBAL_CATEGORY_COUNTS)
    evidence['slices'] = {}
    for name, values in [('act', arrays['globals_continuous'][ids, list(base.CONTINUOUS_GLOBAL_FIELDS).index('act')]), ('roomClass', arrays['global_categories'][ids, categories.index('roomClass')]), ('encounter', arrays['global_categories'][ids, categories.index('encounter')]), ('prePotionCount', (arrays['potions'][ids, :, 1] > 1).sum(-1)), ('SacredBark', np.any((arrays['relics'][ids, :, 0] == base._RELIC_IDS['SACRED_BARK']) & arrays['relic_mask'][ids], -1).astype(int))]:
        evidence['slices'][name] = {str(value): {kind: compact(logp[values == value], targets[ids][values == value]) for kind, logp in predictions.items()} for value in np.unique(values)}
    torch.set_num_threads(1)
    sample_id = ids[:1]
    evidence['decoderCpuLatency'] = {}
    for kind, model in models.items():
        model.cpu().eval()
        inputs = decoder_inputs(arrays, z, sample_id, 'cpu')
        with torch.inference_mode():
            for _ in range(10): model(*inputs)
            times = []
            for _ in range(100):
                start = time.perf_counter(); model(*inputs); times.append((time.perf_counter()-start)*1000)
        evidence['decoderCpuLatency'][kind] = {'meanMs': float(np.mean(times)), 'p95Ms': float(np.quantile(times, .95)), 'batch': 1, 'threads': 1, 'warmups': 10, 'draws': 100}
    point = attention._load_checkpoint('point', artifacts / 'point_control_attention.pt', arrays, spec, historical_train, encoder_args, 'cpu')
    evidence['fullComposedCpuLatency'] = composed_latency(models, encoder, phase2, point, arrays, ids, spec, corpus)
    write(output / 'decoder_evidence.json', evidence)
    np.savez_compressed(output / 'holdout_predictions.npz', ids=ids, targets=targets[ids], **predictions)
    print(json.dumps({'decision': decision, 'ancestral': evidence['ancestralClassification'], 'ci': ci}))

def parser():
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest='command', required=True)
    for command in ('prepare', 'fit'):
        child = sub.add_parser(command)
        child.add_argument('--prepared-dir', required=True)
        child.add_argument('--split-manifest', required=True)
        child.add_argument('--output-dir', required=True)
        if command == 'fit':
            child.add_argument('--artifact-dir', required=True)
            child.add_argument('--code-sha', required=True)
            child.add_argument('--reviewed-sha', required=True)
            child.add_argument('--device', choices=('cpu','cuda','auto'), default='cuda')
            child.add_argument('--threads', type=int, default=8)
    return root

if __name__ == '__main__':
    args = parser().parse_args()
    (prepare if args.command == 'prepare' else fit)(args)
