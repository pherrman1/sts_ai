#!/usr/bin/env python3
"""§501 development-only value-head comparison on the frozen §498 feature cache.

Arms: equal-state baseline, act-1 upweighting, pooled features plus a public
scalar/count block, the block alone, and a source-level learning curve. TRAIN/
VALIDATION only; no TEST reader, encoder forward or gameplay entry point.
"""
import argparse
import json
import math
import os
from pathlib import Path
import time

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

import heart_outcome_value as value
import heart_outcome_weighting as weighting
from heart_outcome_collect import sha, write

REPO = Path(__file__).resolve().parents[1]
PROTOCOL = REPO/'docs/experiments/evidence/heart_outcome_dev_compare_20261017/PROTOCOL.md'
ARMS = ('equal', 'early', 'pooled_plus_public', 'public_only')
CURVE_SOURCES, CURVE_DRAWS = (135, 270, 540), (0, 1)
INITS = (0, 1)
STEPS, EVERY, BATCH, HIDDEN = 2000, 100, 512, 64
ACT1_FACTOR = 2.0
MAX_SECONDS = 900
# Practical margins fixed before any fit (PROTOCOL.md).
REPRESENTATION_MARGIN, EARLY_BCE_MARGIN, CURVE_MARGIN = .003, .002, .002
# §500 visitation arm, selected validation visitation BCE; arm `equal` re-runs it.
REFERENCE_500 = 0.453411
PUBLIC_NAMES = (['hp/100','maxHp/100','hpFraction','gold/500','floor/55','keyRuby','keyEmerald','keySapphire']
    +[f'boss{i}' for i in range(10)]+[f'act{i}' for i in range(1,5)]+[f'screen{i}' for i in range(10)]
    +['deck/30','upgraded/10','relics/20','potionsHeld/3','potionSlots/3'])
EMPTY_POTION = 1


def public_block(record, act):
    """Public scalars and set sizes; mean pooling cannot carry token counts directly."""
    fo = record['obs.fixed_observation']
    value.require(len(fo) == 10 and 1 <= act <= 4 and 0 <= fo[4] < 10 and 0 <= record['screen_state'] < 10,
                  'public block vocabulary')
    hp, max_hp, gold, floor = fo[0], fo[1], fo[2], fo[3]
    row = [hp/100, max_hp/100, hp/max(max_hp, 1), gold/500, floor/55, float(fo[7]), float(fo[8]), float(fo[9])]
    row += [float(fo[4] == i) for i in range(10)] + [float(act == i) for i in range(1, 5)]
    row += [float(record['screen_state'] == i) for i in range(10)]
    potions = record['obs.potions']
    row += [len(record['obs.deck.cards'])/30, sum(u > 0 for u in record['obs.deck.upgrades'])/10,
            len(record['obs.relics.relics'])/20, sum(p != EMPTY_POTION for p in potions)/3, len(potions)/3]
    value.require(len(row) == len(PUBLIC_NAMES) and all(math.isfinite(v) for v in row), 'public block width')
    return row


def public_features(args, manifest, cache):
    """Read development archives only, in cache order; bind (seed, index) per row."""
    out = {}
    for split in value.SPLITS:
        meta, rows = cache[split]['meta'], []
        for i, r in enumerate(value.read_sources(args, manifest, split)):
            value.require(i < len(meta) and (meta[i]['seed'], meta[i]['index']) == (r['seed'], r['index'])
                          and meta[i]['label'] == r['label'] and meta[i]['act'] == r['act'], 'public/cache row order')
            rows.append(public_block(r['record'], r['act']))
        value.require(len(rows) == len(meta), 'public/cache row count')
        out[split] = torch.tensor(rows, dtype=torch.float32)
    return out


def train_weights(meta, arm, sources=None):
    keep = np.array([sources is None or r['seed'] in sources for r in meta])
    value.require(keep.any(), 'empty TRAIN subset')
    w = keep.astype(np.float64)
    if arm == 'early':
        w *= np.array([ACT1_FACTOR if r['act'] == 1 else 1. for r in meta])
    else:
        value.require(arm in ('equal', 'pooled_plus_public', 'public_only'), 'unknown arm')
    return w/w.sum()


def curve_subset(seeds, n, draw):
    order = np.random.default_rng(601+draw).permutation(sorted(set(seeds)))
    value.require(0 < n <= len(order), 'curve size')
    return set(int(s) for s in order[:n])


class Head(nn.Module):
    """Same layout/initialization order as value.ValueHead, with a variable input width."""
    def __init__(self, mean, scale):
        super().__init__()
        self.register_buffer('mean', mean.float().clone());self.register_buffer('scale', scale.float().clone())
        self.layers = nn.Sequential(nn.Linear(len(mean), HIDDEN), nn.ReLU(), nn.Linear(HIDDEN, 1))

    def forward(self, x):
        return self.layers((x-self.mean)/self.scale).squeeze(1)


def make_head(mean, scale, init, device):
    torch.manual_seed(init)
    head = Head(mean, scale)
    with torch.no_grad(): head.layers[-1].bias.fill_(math.log(weighting.CONSTANT/(1-weighting.CONSTANT)))
    return head.to(device)


def fit(x, y, vx, vy, mean, scale, weights, init, deadline, steps=STEPS, every=EVERY):
    """weighting.fit with a variable-width head; identical sampler/optimizer/selection."""
    head = make_head(mean, scale, init, x.device)
    initial = weighting.tensor_sha(head.state_dict())
    optimizer = torch.optim.AdamW(head.parameters(), lr=.001, weight_decay=.001)
    generator = torch.Generator(device='cpu').manual_seed(init)
    weights = torch.as_tensor(weights, dtype=torch.float64, device='cpu')
    value.require(len(weights) == len(x) and torch.isfinite(weights).all().item() and (weights >= 0).all().item()
                  and abs(weights.sum().item()-1) < 1e-9, 'bad sampling weights')
    history, best = [], None
    for step in range(1, steps+1):
        value.require(time.monotonic() < deadline, 'fitting wall cap')
        ids = torch.multinomial(weights, BATCH, replacement=True, generator=generator).to(x.device)
        optimizer.zero_grad(set_to_none=True)
        loss = F.binary_cross_entropy_with_logits(head(x[ids]), y[ids])
        value.require(torch.isfinite(loss).item(), 'nonfinite fitting loss')
        loss.backward();optimizer.step()
        if step % every == 0 or step == steps:
            with torch.inference_mode():
                vl = F.binary_cross_entropy_with_logits(head(vx), vy, reduction='none').double().mean().item()
            value.require(math.isfinite(vl), 'nonfinite validation loss')
            history.append({'step':step, 'validationVisitationBce':vl})
            if best is None or vl < best['validationVisitationBce']:
                best = {**history[-1], 'state':{k:v.detach().cpu().clone() for k, v in head.state_dict().items()}}
    return best, history, initial


def representation_verdict(comparison):
    point = comparison['treatmentMinusControl'][0];upper = comparison['sourceClusterDescriptive95'][1][0]
    return 'REPRESENTATION_LOSS_SIGNAL' if upper < 0 and point <= -REPRESENTATION_MARGIN else 'REPRESENTATION_LOSS_NOT_SHOWN'


def early_verdict(control, treatment):
    bias = all(abs(treatment['landmarks'][k]['bias']['mean']) < abs(control['landmarks'][k]['bias']['mean'])
               for k in weighting.LANDMARKS)
    bce = treatment['visitation']['bce'] <= control['visitation']['bce']+EARLY_BCE_MARGIN
    return 'EARLY_WEIGHTING_SIGNAL' if bias and bce else 'EARLY_WEIGHTING_NOT_SHOWN'


def curve_verdict(curve, full):
    half = np.mean([c['validationVisitationBce'] for c in curve if c['sources'] == 540])
    return 'MORE_SOURCES_SIGNAL' if half-full >= CURVE_MARGIN else 'MORE_SOURCES_NOT_SHOWN'


def run(args):
    value.require(not value.git(REPO, 'status', '--porcelain'), 'clean committed source required')
    args.out.mkdir(parents=True, exist_ok=False)
    ident = weighting.identity(args)
    for p in (Path(__file__), REPO/'tests/test_heart_outcome_dev_compare.py', PROTOCOL):
        ident['tools'][str(p.relative_to(REPO))] = sha(p)
    cache, norm, custody = weighting.inputs(args)
    manifest, archive_custody = value.audit_inputs(args)
    write(args.out/'started.json', {'schema':'heart-outcome-dev-compare-start-v1', 'identity':ident, 'custody':custody,
        'archiveCustody':archive_custody, 'pid':os.getpid(), 'testRead':False})
    start = time.monotonic();deadline = start+MAX_SECONDS
    public = public_features(args, manifest, cache)
    read_seconds = time.monotonic()-start
    torch.set_num_threads(2);torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = False;torch.backends.cudnn.allow_tf32 = False
    tmeta, vmeta = cache['train']['meta'], cache['validation']['meta']
    value.require(sum(r['label'] for r in {r['seed']:r for r in tmeta}.values()) == 126, 'TRAIN class rate changed')
    # Public block normalization: TRAIN equal-state moments, no labels or validation rows.
    pmean = public['train'].double().mean(0);pscale = public['train'].double().std(0, unbiased=False).clamp_min(1e-6)
    def tensors(kind):
        if kind == 'pooled':
            return [cache[s]['x'] for s in ('train', 'validation')], norm['mean'], norm['scale']
        if kind == 'public':
            return [public[s] for s in ('train', 'validation')], pmean.float(), pscale.float()
        return ([torch.cat((cache[s]['x'], public[s]), 1) for s in ('train', 'validation')],
                torch.cat((norm['mean'], pmean.float())), torch.cat((norm['scale'], pscale.float())))
    y, vy = (torch.tensor([r['label'] for r in m], device='cuda', dtype=torch.float32) for m in (tmeta, vmeta))
    kinds = {'equal':'pooled', 'early':'pooled', 'pooled_plus_public':'both', 'public_only':'public'}
    jobs = [(arm, kinds[arm], arm, None, None) for arm in ARMS]
    jobs += [(f'curve-{n}-{d}', 'pooled', 'equal', n, d) for n in CURVE_SOURCES for d in CURVE_DRAWS]
    selected, candidates, predictions = {}, [], {}
    for name, kind, arm, n, draw in jobs:
        (x, vx), mean, scale = tensors(kind);x, vx = x.cuda(), vx.cuda()
        sources = None if n is None else curve_subset([r['seed'] for r in tmeta], n, draw)
        weights = train_weights(tmeta, arm, sources)
        for init in INITS:
            best, history, initial = fit(x, y, vx, vy, mean, scale, weights, init, deadline)
            state = best.pop('state');path = args.out/f'{name}-{init}.pt';torch.save(state, path)
            record = {'job':name, 'arm':arm, 'inputs':kind, 'sources':n or 1080, 'draw':draw, 'init':init, **best,
                      'history':history, 'sha256':sha(path), 'initialTensorSha256':initial, 'inputWidth':len(mean)}
            candidates.append(record)
            if name not in selected or weighting.selection_key(record) < weighting.selection_key(selected[name]):
                selected[name] = {k:v for k, v in record.items() if k != 'history'}
            print(json.dumps({k:v for k, v in record.items() if k != 'history'}), flush=True)
        if n is None:
            chosen = selected[name];head = make_head(mean, scale, 0, 'cuda')
            head.load_state_dict(torch.load(args.out/f"{name}-{chosen['init']}.pt", weights_only=True), strict=True)
            head.eval()
            with torch.inference_mode(): predictions[name] = {'train':head(x).cpu(), 'validation':head(vx).cpu()}
    value.require(time.monotonic() < deadline, 'fitting wall cap')
    arms = {a:{s:weighting.diagnostics(cache[s]['meta'], predictions[a][s].numpy()) for s in ('train', 'validation')}
            for a in ARMS}
    for a in ARMS:
        value.require(abs(arms[a]['validation']['visitation']['bce']-selected[a]['validationVisitationBce']) < 1e-6,
                      'selection/report mismatch')
    vp = {a:predictions[a]['validation'].numpy() for a in ARMS}
    comparisons = {a:weighting.compare(vmeta, vp['equal'], vp[a]) for a in ARMS if a != 'equal'}
    curve = [{'sources':s['sources'], 'draw':s['draw'], 'init':s['init'], 'step':s['step'],
              'validationVisitationBce':s['validationVisitationBce']} for k, s in selected.items() if k.startswith('curve-')]
    full = selected['equal']['validationVisitationBce']
    verdicts = {'representation':representation_verdict(comparisons['pooled_plus_public']),
                'earlyWeighting':early_verdict(arms['equal']['validation'], arms['early']['validation']),
                'sourceCurve':curve_verdict(curve, full)}
    torch.save(predictions, args.out/'predictions.pt')
    value.require(weighting.inputs(args)[2] == custody and value.audit_inputs(args)[1] == archive_custody,
                  'inputs changed during run')
    report = {'schema':'heart-outcome-dev-compare-result-v1', 'verdicts':verdicts, 'arms':arms, 'selected':selected,
        'candidates':candidates, 'validationComparisonsVsEqual':comparisons,
        'learningCurve':curve+[{'sources':1080, 'draw':None, 'validationVisitationBce':full}],
        'reproducesSection500':{'expected':REFERENCE_500, 'actual':full, 'absDiff':abs(full-REFERENCE_500)},
        'publicBlock':{'names':PUBLIC_NAMES, 'trainMean':pmean.tolist(), 'trainScale':pscale.tolist()},
        'constant':{s:value.metric([r['label'] for r in cache[s]['meta']], np.full(len(cache[s]['meta']), weighting.CONSTANT),
                                   np.ones(len(cache[s]['meta']))) for s in ('train', 'validation')},
        'archiveReadSeconds':read_seconds, 'seconds':time.monotonic()-start, 'predictionsSha256':sha(args.out/'predictions.pt'),
        'sourceSha':ident['sourceSha'], 'testRead':False, 'encoderForward':False, 'nativeIntegration':False,
        'runtimePromotion':False, 'bootstrapSelectionAdjusted':False}
    write(args.out/'result.json', report)
    print(json.dumps({'verdicts':verdicts, 'curve':report['learningCurve'],
                      'validation':{a:arms[a]['validation']['visitation'] for a in ARMS}}, default=str), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('parent', 'import-root', 'checkpoint', 'silverbot', 'out'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    try: run(args)
    except Exception as exc:
        if args.out.is_dir() and not (args.out/'failure.json').exists():
            write(args.out/'failure.json', {'type':type(exc).__name__, 'message':str(exc)})
        raise


if __name__ == '__main__': main()
