#!/usr/bin/env python3
"""Ritual-only CTM head refit on corrected Ritual coverage pilot rows.

Only the `ritual.*` tensors of each deployed artifact change. Examples are
every corrected pilot fight whose pre-state holds a Ritual Dagger (Writhing
targets and the ordinary fights before them), deduplicated across the pilot's
twelve cells, routed like runtime (Brew held -> standard, else fast), with the
target Dagger increment tuple teacher-forced over the artifact's own exact
potion-trace posterior. Epochs are chosen by source-grouped cross-validation
inside TRAIN; VALIDATION is never read here. TEST sources never occur.

  examples --pilot DIR [--pilot DIR] --out DIR
  fit      --examples DIR --out DIR
  export   --fit DIR --out DIR      (writes candidate .native files)
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import pickle
import sys
import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO/'tools'), str(REPO)]
import ctm_ritual_validation as v
import ctm_ritual_coverage_pilot as pilot

RECIPE = dict(lr=1e-3, weightDecay=1e-4, batchRows=256, maxEpochs=80, folds=5, seed=20261017, clip=1.0)
RITUAL_TENSORS = ('ritual.context.0.weight', 'ritual.context.0.bias', 'ritual.context.2.weight',
                  'ritual.context.2.bias', 'ritual.event.0.weight', 'ritual.event.0.bias')


def sha(path):
    return v.sha(path)


def pins_env():
    import os
    v.require(not os.environ.get('STS_CTM_PINS') or Path(os.environ['STS_CTM_PINS']).resolve() == v.PINS.resolve(),
              'conflicting data pins')
    os.environ['STS_CTM_PINS'] = str(v.PINS)


def dagger_rows(pilot_dirs):
    """All corrected rows holding a Dagger; exact duplicates across cells merged."""
    from tools import combat_transition_sparse_events as events
    from tools import combat_transition_surrogate as b
    dagger = b._CARD_IDS['RITUAL_DAGGER']
    rows, seen, stats = [], {}, dict(units=0, rowsRead=0, withDagger=0, duplicates=0, targetStructureRejected=0)
    for directory in pilot_dirs:
        for unit_dir in sorted(p for p in Path(directory).iterdir() if (p/'result.json').is_file()):
            result = json.loads((unit_dir/'result.json').read_text())
            v.require(result.get('captureValid') is True, 'invalid pilot unit: '+unit_dir.name)
            unit = result['unit']; stats['units'] += 1
            v.require(unit['partition'] in ('TRAIN', 'VALIDATION'), 'non-development partition')
            for line in (unit_dir/'rows.jsonl').read_text().splitlines():
                row = json.loads(line); stats['rowsRead'] += 1
                pre, post = row['transition']['pre'], row['transition']['post']
                if not any(card['id'] == dagger for card in pre['deck']):
                    continue
                stats['withDagger'] += 1
                key = hashlib.sha256(pilot.canonical([row['sourceSeed'], row['fightIdx'], row['predictorInput'],
                                                       row['transition']]).encode()).hexdigest()
                if key in seen:
                    stats['duplicates'] += 1; continue
                writhing = row['encounter'] == b.WRITHING_MASS_ID
                try:
                    if writhing:
                        adjusted = events.writhing_posts(pre)[events.writhing_target(pre, post)]
                        changes = events.ritual_changes(adjusted, post)
                    else:
                        changes = events.ritual_changes(pre, post)
                except ValueError:
                    stats['targetStructureRejected'] += 1; continue
                v.require(all(c['delta'] >= 0 for c in changes), 'negative Dagger growth')
                seen[key] = True
                rows.append(dict(pre=pre, post=post, pi=row['predictorInput'],
                                 daggerTarget=[c['delta'] for c in changes], writhing=writhing,
                                 forcedTarget=writhing and row['act'] == 3 and row['roomClass'] == 'NORMAL',
                                 partition=unit['partition'], source=unit['sourceSeed'], setup=unit['setup'],
                                 fightIdx=row['fightIdx'], key=key, boss=row['roomClass'] == 'BOSS'))
    return rows, stats


def prepare(rows, device):
    """Per row: route, z and teacher-forced trace items for the Ritual head."""
    pins_env()
    import torch
    from tools.ctm_artifact_torch import load_artifact
    from tools import combat_transition_near_full_sampler as s
    from tools import combat_transition_sparse_events as events
    t, c = s.trajectory, s.c
    artifacts = {name: load_artifact(REPO/'selfplay/models'/f, d, device=device) for name, (f, d) in v.ARTIFACTS.items()}
    examples, stats = [], dict(excluded={}, potionUnscoreable=0, targetOutsideClosure=0)
    with torch.inference_mode():
        for r in rows:
            name = v.route(r['pre'], t.BREW); artifact = artifacts[name]
            reasons = v.exclusions(r, c.base._RELIC_IDS) + s.support.final_reasons(
                r['pi'], r['pre'], artifact, escape=True, writhing_ritual=True)
            if reasons:
                for reason in reasons: stats['excluded'][reason] = stats['excluded'].get(reason, 0)+1
                continue
            v.require(np.array_equal(artifact.classes, c.CLASSES), 'HP class binding differs')
            enc = artifact.encode_predictor(r['pi'])
            z, zp, _ = v.encoding_batch([enc])
            boss = r['boss']
            positions = np.flatnonzero(artifact.delta_values == r['post']['maxHp']-r['pre']['maxHp'])
            v.require(len(positions) == 1, 'teacher maxHP target outside artifact')
            try:
                options = v.teacher_options(artifact, {'potion_z': zp[0]}, r, int(positions[0]), bool(boss), t)
            except ValueError as error:
                v.require('trajectory mass' in str(error), str(error)); options = []
            if not options:
                stats['potionUnscoreable'] += 1; continue
            daggers = [card for card in r['pre']['deck'] if card['id'] == c.base._CARD_IDS['RITUAL_DAGGER']]
            items = []
            for trace, weight in options:
                escaped = trace['outcome'] == 'ESCAPE'
                amounts = events.ritual_posts(r['pre'], r['pi'], trace['initialMask'], tuple(trace['consumed']), escaped)
                hp, bits, _, features = s.conditions(r['pre'], r['pi'], r['post']['curHp'], r['post']['maxHp'],
                                                     trace['initialMask'], tuple(trace['consumed']), escaped)
                candidates = np.asarray([[[card['misc']/100, int(card['upgraded']), amount/20]
                                          for card, amount in zip(daggers, values)] for values in amounts], np.float32)
                target = tuple(r['daggerTarget'])
                items.append(dict(weight=float(weight), hp=hp, bits=bits, features=features, candidates=candidates,
                                  grow=np.asarray([any(a) for a in amounts], bool),
                                  target=amounts.index(target) if target in amounts else -1))
            if all(item['target'] < 0 for item in items):
                stats['targetOutsideClosure'] += 1; continue
            examples.append(dict(route=name, z=z[0].astype(np.float32), items=items, partition=r['partition'],
                                 source=r['source'], writhing=r['writhing'], forcedTarget=r['forcedTarget'],
                                 setup=r['setup'], positive=any(r['daggerTarget']),
                                 escaped=bool(r['post']['smokeBombUsed']), key=r['key']))
    return examples, stats


def flatten(examples, all_items=False):
    """Trace items as padded arrays with their row index."""
    items = [(row, item) for row, ex in enumerate(examples) for item in ex['items'] if all_items or item['target'] >= 0]
    width = max(len(item['candidates']) for _, item in items)
    cards = max(item['candidates'].shape[1] for _, item in items)
    cand = np.zeros((len(items), width, cards, 3), np.float32); legal = np.zeros((len(items), width), bool)
    grow = np.zeros((len(items), width), bool)
    for k, (_, item) in enumerate(items):
        n, m = item['candidates'].shape[:2]; cand[k, :n, :m] = item['candidates']; legal[k, :n] = True
        grow[k, :n] = item['grow']
    return dict(row=np.asarray([r for r, _ in items]), z=np.stack([examples[r]['z'] for r, _ in items]),
                hp=np.stack([i['hp'] for _, i in items]), bits=np.stack([i['bits'] for _, i in items]),
                features=np.stack([i['features'] for _, i in items]), candidates=cand, legal=legal,
                target=np.asarray([i['target'] for _, i in items]), grow=grow,
                logWeight=np.log(np.asarray([i['weight'] for _, i in items])))


def row_nll(net, flat, rows, device):
    """-log sum_k w_k p_k(target) for each requested row index."""
    import torch
    mask = np.isin(flat['row'], rows)
    tensor = lambda key, dtype=torch.float32: torch.as_tensor(flat[key][mask], device=device, dtype=dtype)
    lp = net(tensor('z'), tensor('hp'), tensor('bits'), tensor('features'), tensor('candidates'),
             tensor('legal', torch.bool))
    target = torch.as_tensor(flat['target'][mask], device=device)
    item = lp.gather(1, target[:, None])[:, 0] + tensor('logWeight')
    index = torch.as_tensor(np.searchsorted(rows, flat['row'][mask]), device=device)
    out = torch.full((len(rows),), -torch.inf, device=device, dtype=item.dtype)
    out = out.scatter_reduce(0, index, item, reduce='amax', include_self=True)
    total = torch.zeros(len(rows), device=device, dtype=item.dtype).scatter_add(0, index, (item-out[index]).exp())
    return -(out + total.log())


def train(base_net, flat, train_rows, epochs, device, eval_rows=None):
    import torch
    torch.manual_seed(RECIPE['seed']); rng = np.random.default_rng(RECIPE['seed'])
    net = copy.deepcopy(base_net).to(device).train()
    for p in net.parameters(): p.requires_grad_(True)
    opt = torch.optim.AdamW(net.parameters(), lr=RECIPE['lr'], weight_decay=RECIPE['weightDecay'])
    curve = []
    for epoch in range(epochs):
        order = rng.permutation(train_rows)
        for start in range(0, len(order), RECIPE['batchRows']):
            batch = np.sort(order[start:start+RECIPE['batchRows']])
            loss = row_nll(net, flat, batch, device).mean()
            opt.zero_grad(); loss.backward()
            torch.nn.utils.clip_grad_norm_(net.parameters(), RECIPE['clip']); opt.step()
        if eval_rows is not None:
            with torch.no_grad(): curve.append(float(row_nll(net, flat, np.sort(eval_rows), device).mean()))
    return net.eval(), curve


def row_scores(net, flat, n, device):
    """Teacher-forced target NLL (inf if no trace reaches the target) and P(any growth)."""
    import torch
    with torch.no_grad():
        t = lambda key, dtype=torch.float32: torch.as_tensor(flat[key], device=device, dtype=dtype)
        p = net(t('z'), t('hp'), t('bits'), t('features'), t('candidates'), t('legal', torch.bool)).exp().cpu().numpy()
    w = np.exp(flat['logWeight']); target = np.zeros(n); grow = np.zeros(n)
    hit = flat['target'] >= 0
    np.add.at(target, flat['row'][hit], w[hit]*p[hit, flat['target'][hit]])
    np.add.at(grow, flat['row'], w*(p*flat['grow']).sum(-1))
    with np.errstate(divide='ignore'): return -np.log(target), grow


def bootstrap(sources, values, reps=2000, seed=20261017):
    unique, inverse = np.unique(sources, return_inverse=True)
    sums = np.bincount(inverse, weights=values, minlength=len(unique)); counts = np.bincount(inverse).astype(float)
    rng = np.random.default_rng(seed); draws = []
    for _ in range(reps):
        pick = rng.integers(0, len(unique), len(unique)); draws.append(sums[pick].sum()/counts[pick].sum())
    return [float(x) for x in np.quantile(draws, [.025, .975])]


def evaluate(args):
    """Paired deployed-vs-refit scores on VALIDATION examples (preregistered cohorts)."""
    pins_env()
    import torch
    from tools.ctm_artifact_torch import load_artifact
    with open(args.examples/'examples.pkl', 'rb') as stream: examples = pickle.load(stream)
    fitted = json.loads((args.fit/'fit.json').read_text())
    val = [e for e in examples if e['partition'] == args.partition]
    base_nll, cand_nll, base_grow, cand_grow = (np.zeros(len(val)) for _ in range(4))
    for name, (f, d) in v.ARTIFACTS.items():
        idx = [i for i, e in enumerate(val) if e['route'] == name]
        if not idx: continue
        mine = [val[i] for i in idx]; flat = flatten(mine, all_items=True)
        base = load_artifact(REPO/'selfplay/models'/f, d, device=args.device).ritual_net
        cand = copy.deepcopy(base)
        v.require(sha(args.fit/f'{name}-ritual.npz') == fitted['routes'][name]['tensorsSha256'], 'fitted tensors differ')
        with np.load(args.fit/f'{name}-ritual.npz') as z:
            cand.load_state_dict({k.removeprefix('ritual.'): torch.as_tensor(z[k]) for k in RITUAL_TENSORS})
        cand = cand.to(args.device).eval()
        for net, nll, grow in ((base, base_nll, base_grow), (cand, cand_nll, cand_grow)):
            a, b = row_scores(net, flat, len(mine), args.device); nll[idx] = a; grow[idx] = b
    src = np.asarray([e['source'] for e in val]); pos = np.asarray([e['positive'] for e in val], float)
    forced = np.asarray([e['forcedTarget'] for e in val]); esc = np.asarray([e['escaped'] for e in val])
    potion = np.asarray([e['setup'].rsplit('_', 1)[-1] for e in val]); writhing = np.asarray([e['writhing'] for e in val])
    cohorts = {'writhingNotEscaped': forced & ~esc, 'writhingNatural': forced & (potion == 'natural'),
               'writhingBrew': forced & (potion == 'brew'), 'writhingSmokeNotEscaped': forced & (potion == 'smoke') & ~esc,
               'writhingEscaped': forced & esc, 'nonWrithing': ~writhing,
               'fast': np.asarray([e['route'] == 'fast' for e in val]), 'standard': np.asarray([e['route'] == 'standard' for e in val])}
    out = {}
    for name, m in cohorts.items():
        if not m.any(): out[name] = None; continue
        finite = np.isfinite(base_nll[m]) & np.isfinite(cand_nll[m])
        diff = (cand_nll[m]-base_nll[m])[finite]
        out[name] = dict(rows=int(m.sum()), sources=int(len(set(src[m]))), positives=int(pos[m].sum()),
            observedGrowth=float(pos[m].mean()), deployedPredictedGrowth=float(base_grow[m].mean()),
            refitPredictedGrowth=float(cand_grow[m].mean()),
            observedGrowthCI=bootstrap(src[m], pos[m]),
            deployedNll=float(base_nll[m][finite].mean()), refitNll=float(cand_nll[m][finite].mean()),
            nllDifference=float(diff.mean()), nllDifferenceCI=bootstrap(src[m][finite], diff),
            infiniteNllRows=dict(deployed=int((~np.isfinite(base_nll[m])).sum()), refit=int((~np.isfinite(cand_nll[m])).sum())))
    np.savez_compressed(args.out/'validation-row-scores.npz', source=src, positive=pos, deployedNll=base_nll,
                        refitNll=cand_nll, deployedGrowth=base_grow, refitGrowth=cand_grow)
    return out


def fit(args):
    pins_env()
    import torch
    from tools.ctm_artifact_torch import load_artifact
    with open(args.examples/'examples.pkl', 'rb') as stream: examples = pickle.load(stream)
    receipt = dict(recipe=RECIPE, examplesSha256=sha(args.examples/'examples.pkl'), routes={})
    args.out.mkdir(parents=True, exist_ok=False)
    for name, (f, d) in v.ARTIFACTS.items():
        base = load_artifact(REPO/'selfplay/models'/f, d, device=args.device).ritual_net
        mine = [e for e in examples if e['route'] == name and e['partition'] == 'TRAIN']
        v.require(mine, 'no TRAIN rows for route '+name)
        flat = flatten(mine); rows = np.arange(len(mine))
        sources = np.asarray([e['source'] for e in mine]); unique = np.unique(sources)
        fold_of = {s: i % RECIPE['folds'] for i, s in enumerate(np.random.default_rng(RECIPE['seed']).permutation(unique))}
        folds = np.asarray([fold_of[s] for s in sources])
        with torch.no_grad(): base_nll = float(row_nll(base.to(args.device), flat, rows, args.device).mean())
        curves = []
        for k in range(RECIPE['folds']):
            _, curve = train(base, flat, rows[folds != k], RECIPE['maxEpochs'], args.device, rows[folds == k])
            curves.append(curve)
        held = np.asarray(curves).mean(0)
        with torch.no_grad():
            fold_base = float(np.mean([float(row_nll(base, flat, rows[folds == k], args.device).mean()) for k in range(RECIPE['folds'])]))
        epochs = int(np.argmin(held))+1
        net, _ = train(base, flat, rows, epochs, args.device)
        state = {f'ritual.{k}': value.detach().cpu().numpy().astype(np.float32) for k, value in net.state_dict().items()}
        v.require(set(state) == set(RITUAL_TENSORS), 'unexpected Ritual tensor set')
        np.savez(args.out/f'{name}-ritual.npz', **state)
        with torch.no_grad(): final_nll = float(row_nll(net, flat, rows, args.device).mean())
        receipt['routes'][name] = dict(baseArtifact=f, baseArtifactSha256=d, trainRows=len(mine),
            trainPositiveRows=int(sum(e['positive'] for e in mine)), trainSources=int(len(unique)),
            items=int(len(flat['row'])), baseTrainNll=base_nll, cvBaseHeldOutNll=fold_base,
            cvHeldOutCurve=held.tolist(), selectedEpochs=epochs, finalTrainNll=final_nll,
            tensorsSha256=sha(args.out/f'{name}-ritual.npz'))
        print(json.dumps({name: receipt['routes'][name]}, indent=1), flush=True)
    v.write(args.out/'fit.json', receipt)


def export(args):
    """Candidate artifacts: deployed bytes with only `ritual.*` replaced."""
    from ctm_escape import read_artifact, write_artifact
    fitted = json.loads((args.fit/'fit.json').read_text())
    args.out.mkdir(parents=True, exist_ok=False)
    out = {}
    for name, (f, d) in v.ARTIFACTS.items():
        route = fitted['routes'][name]
        v.require(sha(REPO/'selfplay/models'/f) == d == route['baseArtifactSha256'], 'base artifact differs')
        v.require(sha(args.fit/f'{name}-ritual.npz') == route['tensorsSha256'], 'fitted tensors differ')
        metadata, tensors = read_artifact(REPO/'selfplay/models'/f)
        with np.load(args.fit/f'{name}-ritual.npz') as z:
            for key in RITUAL_TENSORS:
                v.require(z[key].shape == tensors[key].shape, 'Ritual tensor shape differs: '+key)
                tensors[key] = z[key]
        metadata = dict(metadata, ritualRefit=dict(baseArtifactSha256=d, fitReceiptSha256=sha(args.fit/'fit.json'),
                        tensorsSha256=route['tensorsSha256'], qualified=False))
        path = args.out/f.replace('.native', '_ritual_refit.native')
        write_artifact(path, metadata, tensors)
        out[name] = [str(path), sha(path)]
    v.write(args.out/'export.json', out); print(json.dumps(out, indent=1))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('command', choices=('examples', 'fit', 'export', 'evaluate'))
    parser.add_argument('--pilot', type=Path, action='append')
    parser.add_argument('--examples', type=Path); parser.add_argument('--fit', type=Path)
    parser.add_argument('--out', type=Path, required=True); parser.add_argument('--device', default='cuda')
    parser.add_argument('--partition', choices=('TRAIN', 'VALIDATION'), default='VALIDATION')
    args = parser.parse_args()
    if args.command == 'examples':
        rows, row_stats = dagger_rows(args.pilot)
        examples, stats = prepare(rows, args.device)
        args.out.mkdir(parents=True, exist_ok=False)
        with open(args.out/'examples.pkl', 'wb') as stream: pickle.dump(examples, stream)
        summary = dict(rowStats=row_stats, prepareStats=stats, examples=len(examples),
                       byPartitionRoute={f'{p}/{r}': sum(e['partition'] == p and e['route'] == r for e in examples)
                                         for p in ('TRAIN', 'VALIDATION') for r in ('fast', 'standard')},
                       positives={p: sum(e['partition'] == p and e['positive'] for e in examples) for p in ('TRAIN', 'VALIDATION')},
                       writhing={p: sum(e['partition'] == p and e['writhing'] for e in examples) for p in ('TRAIN', 'VALIDATION')},
                       examplesSha256=sha(args.out/'examples.pkl'), pilots=[str(p) for p in args.pilot])
        v.write(args.out/'examples.json', summary); print(json.dumps(summary, indent=1))
    elif args.command == 'fit':
        fit(args)
    elif args.command == 'evaluate':
        args.out.mkdir(parents=True, exist_ok=False)
        result = dict(cohorts=evaluate(args), examplesSha256=sha(args.examples/'examples.pkl'),
                      fitSha256=sha(args.fit/'fit.json'), partition=args.partition, testEvaluated=False)
        v.write(args.out/'evaluation.json', result); print(json.dumps(result, indent=1))
    else:
        export(args)


if __name__ == '__main__':
    main()
