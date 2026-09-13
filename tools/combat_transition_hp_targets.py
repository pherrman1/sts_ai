#!/usr/bin/env python3
"""Frozen HP-only paired target experiment. No simulator or runtime exports."""
from __future__ import annotations

import argparse
from contextlib import nullcontext
import hashlib
import json
from pathlib import Path
import subprocess
import time

import numpy as np
from tools import combat_transition_attention_ablation as attention
from tools import combat_transition_surrogate as base
from tools import combat_transition_frozen_composition as frozen

ROOT = Path(__file__).resolve().parents[1]
SPLIT = ROOT / 'docs/experiments/evidence/potion_decoder_v1/nested_split.json'
SPLIT_HASH = '58e35f9f85eefd7617e616ddbfa7ee227c429ed4d312f7dacd470828f9a09094'
RECIPE = dict(schema='hp_target_comparison_v1', seeds=[20260912, 20260913, 20260914],
              epochs=10, batch=2048, lr=1e-3, weightDecay=1e-4, clip=1.0,
              precision='amp-fp16', bootstrapReps=1000, bootstrapSeed=20260914,
              maxHpBins=[0, 60, 80, 100, 120, None],
              encoder='AttentionEncoder:64/2/4/128', deltaEmbedding=8,
              head=[72, 64, 1], targetNormalization='TRAIN victories population mean/std',
              conditioning='observed max-HP delta class',
              holdout='reused engineering data; no epoch selection',
              decision='CI strictly one-sided and all three paired seed estimates agree')


def targets(pre, post, maximum):
    return {'fraction': np.asarray(post, dtype=np.float64) / maximum,
            'delta': np.asarray(post, dtype=np.float64) - pre}


def reconstruct(arm, output, mean, std, pre, maximum):
    value = np.asarray(output, dtype=np.float64) * std + mean
    return value * maximum if arm == 'fraction' else pre + value


def normalization(values, train):
    selected = values[train]
    mean, std = float(selected.mean()), float(selected.std())
    if not np.isfinite(std) or std <= 0:
        raise ValueError('degenerate TRAIN target')
    return {'mean': mean, 'std': std}


def metrics(pred, actual, maximum):
    if not len(actual):
        return {'rows': 0}
    error = np.abs(pred - actual)
    legal = np.clip(pred, 1, maximum)
    return dict(rows=len(actual), mae=float(error.mean()),
                rmse=float(np.sqrt(np.mean((pred - actual)**2))),
                medianAbsoluteError=float(np.median(error)),
                clampedMae=float(np.abs(legal-actual).mean()),
                roundedClampedMae=float(np.abs(np.clip(np.floor(pred+0.5), 1, maximum)-actual).mean()),
                fractionMae=float((error/maximum).mean()),
                belowOnePercent=float(100*np.mean(pred < 1)),
                aboveMaxPercent=float(100*np.mean(pred > maximum)))


def bootstrap(sources, differences, reps=1000, seed=20260914):
    unique, inverse = np.unique(sources, return_inverse=True)
    sums = np.bincount(inverse, weights=differences)
    counts = np.bincount(inverse)
    rng = np.random.default_rng(seed)
    draws = []
    for _ in range(reps):
        sample = rng.integers(len(unique), size=len(unique))
        draws.append(float(sums[sample].sum()/counts[sample].sum()))
    return dict(estimate=float(np.mean(differences)),
                ci95=np.quantile(draws, [.025, .975]).tolist(), sources=len(unique), resamples=reps)


def classify(ci, estimates):
    if ci[1] < 0 and all(x < 0 for x in estimates):
        return 'ABSOLUTE_HP_DELTA_WINS'
    if ci[0] > 0 and all(x > 0 for x in estimates):
        return 'HP_FRACTION_WINS'
    return 'HP_TARGET_INCONCLUSIVE'


def new_model(torch, mean, std, delta_count, seed):
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    class HpNet(torch.nn.Module):
        def __init__(self):
            super().__init__()
            self.encoder = attention.AttentionEncoder(torch, mean, std).net
            self.delta_embedding = torch.nn.Embedding(delta_count, 8)
            self.hp = torch.nn.Sequential(torch.nn.Linear(72, 64), torch.nn.ReLU(), torch.nn.Linear(64, 1))

        def forward(self, inputs, delta):
            return self.hp(torch.cat((self.encoder(*inputs), self.delta_embedding(delta)), -1)).squeeze(-1)
    return HpNet()


def state_hash(model):
    digest = hashlib.sha256()
    for name, value in model.state_dict().items():
        digest.update(name.encode())
        digest.update(value.detach().cpu().numpy().tobytes())
    return digest.hexdigest()


def load(prepared):
    for name in ('prepared.npz', 'prepared_manifest.json', 'target_spec.json'):
        if base.sha256(prepared/name) != frozen.EXPECTED_HASHES[name]:
            raise ValueError(f'frozen prepared hash differs: {name}')
    if base.sha256(SPLIT) != SPLIT_HASH:
        raise ValueError('nested split hash differs')
    arrays, spec = base._load_prepared(prepared)
    members = json.loads(SPLIT.read_text())['members']
    train_sources = members['train'] + members['validation']
    holdout_sources = members['holdout']
    if len(set(train_sources)) != len(train_sources) or set(train_sources) & set(holdout_sources):
        raise ValueError('source overlap')
    victory = arrays['supported'] & (arrays['y_win'] == 1)
    train = np.flatnonzero(victory & np.isin(arrays['sourceSeed'], train_sources))
    holdout = np.flatnonzero(victory & np.isin(arrays['sourceSeed'], holdout_sources))
    pre = arrays['globals_continuous'][:, base.CONTINUOUS_GLOBAL_FIELDS.index('curHp')].astype(np.float64)
    maximum = arrays['y_post_max_hp'].astype(np.float64)
    post = arrays['y_post_hp'].astype(np.float64)
    if not np.array_equal(maximum, arrays['preMaxHp'] + arrays['y_max_hp_delta']):
        raise ValueError('teacher forced max-HP mismatch')
    delta_values = np.asarray(spec['maxHpDeltaValues'])
    delta = np.searchsorted(delta_values, arrays['y_max_hp_delta'])
    if not np.array_equal(delta_values[delta], arrays['y_max_hp_delta']):
        raise ValueError('delta class mismatch')
    y = targets(pre, post, maximum)
    stats = {arm: normalization(value, train) for arm, value in y.items()}
    metadata = dict(corpusSha256=attention.EXPECTED_CORPUS_SHA256, nestedSplitSha256=SPLIT_HASH,
                    preparedHashes={name:base.sha256(prepared/name) for name in frozen.EXPECTED_HASHES if not name.endswith('.pt')},
                    counts={name:dict(sources=len(src), victorySources=len(np.unique(arrays['sourceSeed'][ids])), victories=len(ids))
                            for name, src, ids in [('train',train_sources,train),('holdout',holdout_sources,holdout)]},
                    normalization=stats, trainSources=train_sources, holdoutSources=holdout_sources,
                    deltaValues=delta_values.tolist(), maxHpModeling='untouched')
    return arrays, train, holdout, pre, post, maximum, delta, y, stats, metadata


def slices(arrays, ids, pre, post):
    hpfrac = pre[ids]/arrays['preMaxHp'][ids]
    result = {}
    for low, high in [(0,.25),(.25,.5),(.5,.75),(.75,1)]:
        result[f'preFraction:{low}-{high}'] = (hpfrac >= low) & (hpfrac <= high if high == 1 else hpfrac < high)
    bins = RECIPE['maxHpBins']
    for low, high in zip(bins[:-1], bins[1:]):
        result[f'preMaxHp:{low}-{high}'] = (arrays['preMaxHp'][ids]>=low) & (True if high is None else arrays['preMaxHp'][ids]<high)
    for field in ('act','roomClass'):
        for value in np.unique(arrays[field][ids]):
            result[f'{field}:{value}'] = arrays[field][ids] == value
    change = post[ids]-pre[ids]
    result.update(lost=change<0, unchanged=change==0, gained=change>0,
                  zeroMaxDelta=arrays['y_max_hp_delta'][ids]==0,
                  nonzeroMaxDelta=arrays['y_max_hp_delta'][ids]!=0)
    return result


def distribution(value, covariates):
    return dict(mean=float(value.mean()), std=float(value.std()), median=float(np.median(value)),
                quantiles=dict(zip(['p5','p25','p75','p95'],np.quantile(value,[.05,.25,.75,.95]).tolist())),
                correlations={name:float(np.corrcoef(value,other)[0,1]) for name,other in covariates.items()})


def run(args):
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    data = load(Path(args.prepared_dir))
    arrays, train, holdout, pre, post, maximum, delta, y, stats, metadata = data
    recipe = dict(RECIPE, baselineSha=args.baseline_sha)
    if args.command == 'prepare':
        for name, value in [('recipe.json',recipe),('preflight.json',metadata)]:
            path = output/name
            if path.exists():
                raise ValueError('refusing to overwrite preflight')
            base.json_dump(path,value)
        print(json.dumps({k:v for k,v in metadata.items() if k not in ('trainSources','holdoutSources')}), flush=True)
        return
    current = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    if current != args.reviewed_sha or subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip():
        raise ValueError('fit requires clean reviewed SHA')
    if json.loads((output/'recipe.json').read_text()) != recipe or json.loads((output/'preflight.json').read_text()) != metadata:
        raise ValueError('preflight changed')
    if list(output.glob('*.pt')) or (output/'results.json').exists():
        raise ValueError('refusing to overwrite fit')
    import torch
    if not torch.cuda.is_available():
        raise ValueError('frozen AMP protocol requires CUDA')
    torch.set_num_threads(4)
    # Disable eval-only fused Transformer path: AMP and its FP32 weights must agree.
    torch.backends.mha.set_fastpath_enabled(False)
    mean = arrays['globals_continuous'][train].mean(0)
    std = arrays['globals_continuous'][train].std(0)
    all_predictions, audits = {}, []
    for seed in RECIPE['seeds']:
        paired = {}
        for arm in ('fraction','delta'):
            started = time.monotonic()
            model = new_model(torch,mean,std,len(metadata['deltaValues']),seed).cuda()
            initial = state_hash(model)
            optimizer = torch.optim.AdamW(model.parameters(),lr=RECIPE['lr'],weight_decay=RECIPE['weightDecay'])
            scaler = torch.amp.GradScaler('cuda',init_scale=16384)
            rng = np.random.default_rng(seed)
            batch_hash, condition_hash = hashlib.sha256(), hashlib.sha256()
            history = []
            for epoch in range(RECIPE['epochs']):
                model.train()
                total = 0.
                for ids in base._batches(train,RECIPE['batch'],rng):
                    batch_hash.update(ids.tobytes())
                    condition_hash.update(delta[ids].tobytes())
                    inputs = base._torch_inputs(arrays,ids,'cuda',torch,trim_padding=True)
                    d = torch.as_tensor(delta[ids],device='cuda',dtype=torch.long)
                    target = torch.as_tensor((y[arm][ids]-stats[arm]['mean'])/stats[arm]['std'],device='cuda',dtype=torch.float32)
                    optimizer.zero_grad(set_to_none=True)
                    with torch.autocast('cuda',dtype=torch.float16):
                        loss = torch.nn.functional.mse_loss(model(inputs,d),target)
                    if not torch.isfinite(loss):
                        raise ValueError('nonfinite loss')
                    scaler.scale(loss).backward()
                    scaler.unscale_(optimizer)
                    norm = torch.nn.utils.clip_grad_norm_(model.parameters(),1.)
                    if not torch.isfinite(norm):
                        raise ValueError('nonfinite gradient; fixed recipe aborted')
                    scaler.step(optimizer)
                    scaler.update()
                    total += float(loss.detach())*len(ids)
                history.append(total/len(train))
                print(json.dumps(dict(seed=seed,arm=arm,epoch=epoch+1,loss=history[-1],seconds=time.monotonic()-started)),flush=True)
            torch.save(dict(state_dict=base._safe_state_dict(model),metadata=metadata,recipe=recipe,reviewedSha=current,arm=arm,seed=seed),output/f'{seed}-{arm}.pt')
            paired[arm] = dict(initialization=initial,batches=batch_hash.hexdigest(),conditioning=condition_hash.hexdigest())
            model.eval()
            values=[]
            with torch.no_grad():
                for start in range(0,len(holdout),RECIPE['batch']):
                    ids=holdout[start:start+RECIPE['batch']]
                    with torch.autocast('cuda',dtype=torch.float16):
                        pred=model(base._torch_inputs(arrays,ids,'cuda',torch,trim_padding=True),torch.as_tensor(delta[ids],device='cuda',dtype=torch.long))
                    values.append(pred.float().cpu().numpy())
            all_predictions[f'{seed}-{arm}'] = reconstruct(arm,np.concatenate(values),**stats[arm],pre=pre[holdout],maximum=maximum[holdout])
            del model,optimizer
            torch.cuda.empty_cache()
        if paired['fraction'] != paired['delta']:
            raise ValueError('paired provenance differs')
        audits.append(dict(seed=seed,proof=paired))
    np.savez(output/'predictions.npz',rowIds=holdout,sourceSeed=arrays['sourceSeed'][holdout],**all_predictions)
    actual,maxhp = post[holdout],maximum[holdout]
    masks=slices(arrays,holdout,pre,post)
    scores={key:dict(overall=metrics(value,actual,maxhp),slices={name:metrics(value[mask],actual[mask],maxhp[mask]) for name,mask in masks.items()}) for key,value in all_predictions.items()}
    differences=np.stack([np.abs(all_predictions[f'{s}-delta']-actual)-np.abs(all_predictions[f'{s}-fraction']-actual) for s in RECIPE['seeds']])
    estimates=differences.mean(1).tolist()
    aggregate=bootstrap(arrays['sourceSeed'][holdout],differences.mean(0))
    fraction_mae=float(np.mean([scores[f'{s}-fraction']['overall']['mae'] for s in RECIPE['seeds']]))
    covariates=dict(preCurHp=pre[holdout],preMaxHp=arrays['preMaxHp'][holdout],preFraction=pre[holdout]/arrays['preMaxHp'][holdout])
    results=dict(reviewedSha=current,recipe=recipe,provenance=metadata,pairedAudits=audits,
                 seedDifferences=estimates,aggregate=aggregate,relativeMaeChange=aggregate['estimate']/fraction_mae,
                 classification=classify(aggregate['ci95'],estimates),metrics=scores,
                 distributions={arm:distribution(value[holdout],covariates) for arm,value in y.items()})
    base.json_dump(output/'results.json',results)
    base.json_dump(output/'artifact-hashes.json',{path.name:base.sha256(path) for path in output.iterdir() if path.is_file() and path.name != 'artifact-hashes.json' and path.suffix != '.log'})
    print(json.dumps(dict(classification=results['classification'],aggregate=aggregate,seedDifferences=estimates)),flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['prepare','fit'])
    parser.add_argument('--prepared-dir',required=True)
    parser.add_argument('--output-dir',required=True)
    parser.add_argument('--baseline-sha',required=True)
    parser.add_argument('--reviewed-sha')
    run(parser.parse_args())
