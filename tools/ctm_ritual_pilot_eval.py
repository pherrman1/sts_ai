#!/usr/bin/env python3
"""Score deployed (or candidate) CTM Ritual heads on corrected pilot rows; no fit.

Reads the controlled Ritual coverage pilot outputs (RAW rows plus per-unit
analysis), keeps ordinary-child Writhing targets, and reports per row the
teacher-forced Ritual target mass, the 32-draw ancestral mixture mass, and the
teacher-forced probability of any Dagger growth. Development evidence only:
TRAIN/VALIDATION sources, no TEST, no support change.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO/'tools'), str(REPO)]
import ctm_ritual_validation as v
import ctm_ritual_coverage_pilot as pilot

DRAWS, SEED = 32, 20261017


def sha(path):
    return v.sha(path)


def load_rows(pilot_dirs):
    """Ordinary-child Writhing targets with their pilot unit identity."""
    rows = []
    for directory in pilot_dirs:
        for unit_dir in sorted(p for p in Path(directory).iterdir() if (p/'result.json').is_file()):
            result = json.loads((unit_dir/'result.json').read_text())
            v.require(result.get('captureValid') is True, 'invalid pilot unit: '+unit_dir.name)
            unit = result['unit']
            targets = {t['fightIdx']: t for t in result['targets']}
            for line in (unit_dir/'rows.jsonl').read_text().splitlines():
                row = json.loads(line)
                target = targets.get(row['fightIdx'])
                if target is None or not (row['act'] == 3 and row['roomClass'] == 'NORMAL'):
                    continue
                if not target['ordinaryChild']:
                    continue
                changes, _, _ = pilot.legal_growth(row)
                rows.append(dict(pre=row['transition']['pre'], post=row['transition']['post'],
                                 pi=row['predictorInput'], daggerTarget=[c['delta'] for c in changes],
                                 partition=unit['partition'], source=unit['sourceSeed'], setup=unit['setup'],
                                 fightIdx=row['fightIdx'], unitId=unit['id'], pilot=Path(directory).name))
    v.require(not any(r['partition'] not in ('TRAIN', 'VALIDATION') for r in rows), 'non-development partition')
    return rows


def evaluate(rows, artifacts_spec, device):
    import os
    # The deployed artifacts' HP classes come from the same retrain pins (§511).
    v.require(not os.environ.get('STS_CTM_PINS') or Path(os.environ['STS_CTM_PINS']).resolve() == v.PINS.resolve(),
              'conflicting data pins')
    os.environ['STS_CTM_PINS'] = str(v.PINS)
    import torch
    from tools.ctm_artifact_torch import load_artifact
    from tools import combat_transition_near_full_sampler as s
    from tools import combat_transition_composed_evaluate as e
    t, c = s.trajectory, s.c
    artifacts = {name: load_artifact(Path(path), digest, device=device) for name, (path, digest) in artifacts_spec.items()}
    keep, routes, excluded = [], [], 0
    for r in rows:
        name = v.route(r['pre'], t.BREW)
        reasons = v.exclusions(r, c.base._RELIC_IDS) + s.support.final_reasons(
            r['pi'], r['pre'], artifacts[name], escape=True, writhing_ritual=True)
        if reasons:
            excluded += 1; continue
        keep.append(r); routes.append(name)
    n = len(keep)
    teacher, mixture, p_grow = np.zeros(n), np.zeros(n), np.zeros(n)
    unscoreable = np.zeros(n, bool)
    rng = np.random.default_rng(SEED)
    with torch.inference_mode():
        for name, artifact in artifacts.items():
            chosen = np.flatnonzero(np.asarray(routes) == name)
            if not len(chosen): continue
            rr = [keep[i] for i in chosen]
            z, zp, pd = v.encoding_batch([artifact.encode_predictor(r['pi']) for r in rr])
            pre = np.asarray([r['pre']['curHp'] for r in rr], float)
            premax = np.asarray([r['pre']['maxHp'] for r in rr], float)
            boss = np.zeros(len(rr), bool)
            v.require(np.array_equal(artifact.classes, c.CLASSES), 'HP class binding differs')
            for j, (i, r) in enumerate(zip(chosen, rr)):
                delta = r['post']['maxHp']-r['pre']['maxHp']
                positions = np.flatnonzero(artifact.delta_values == delta)
                v.require(len(positions) == 1, 'teacher maxHP target outside artifact')
                try:
                    options = v.teacher_options(artifact, {'potion_z': zp[j]}, r, int(positions[0]), False, t)
                except ValueError as error:
                    # The potion head gives the observed trajectory zero mass; the
                    # Ritual head cannot be teacher-forced on it. Counted, not scored.
                    v.require('trajectory mass' in str(error), str(error))
                    options = []
                unscoreable[i] = not options
                for trace, weight in options:
                    amounts, probabilities = s.ritual_probabilities(artifact.ritual_net, z[j], r['pre'], r['pi'],
                        r['post']['curHp'], r['post']['maxHp'], trace['initialMask'], tuple(trace['consumed']),
                        trace['outcome'] == 'ESCAPE')
                    teacher[i] += weight*v.target_mass(amounts, probabilities, tuple(r['daggerTarget']))
                    p_grow[i] += weight*float(sum(p for a, p in zip(amounts, probabilities) if any(a)))
            eligible = np.asarray([artifact.escape.eligible(r['pre']['potions'], r['pre']['potionCapacity'], False) for r in rr])
            p_escape = np.where(eligible, artifact.escape_probability(z), 0.)
            for draw in range(DRAWS):
                delta = e.draw_categories(pd, rng); maximum = premax+artifact.delta_values[delta]
                bit = (rng.random(len(rr)) < p_escape).astype(np.int64)
                hp = artifact.hp_probabilities(z, delta, pre, maximum, bit)
                ending = pre+artifact.classes[e.draw_categories(hp, rng)]
                traces = s.sample_potions_batch(artifact.potion_net, zp, [r['pre'] for r in rr], delta,
                                               ending/maximum, rng, boss, escape=bit)
                for j, (i, r, trace) in enumerate(zip(chosen, rr, traces)):
                    amounts, probabilities = s.ritual_probabilities(artifact.ritual_net, z[j], r['pre'], r['pi'],
                        ending[j], maximum[j], trace['initialMask'], tuple(trace['consumed']), trace['outcome'] == 'ESCAPE')
                    mixture[i] += v.target_mass(amounts, probabilities, tuple(r['daggerTarget']))/DRAWS
    scored = ~unscoreable
    return ([r for r, k in zip(keep, scored) if k], [x for x, k in zip(routes, scored) if k], excluded,
            teacher[scored], mixture[scored], p_grow[scored], int(unscoreable.sum()))


def cohort(mask, keep, teacher, mixture, p_grow):
    from tools import combat_transition_composed_evaluate as e
    if not mask.any(): return None
    sources = np.asarray([r['source'] for r in keep])[mask]
    out, *_ = v.summary(teacher[mask], mixture[mask], sources, e.source_gap_bootstrap)
    positive = np.asarray([any(r['daggerTarget']) for r in keep])[mask]
    out.update(observedGrowthRate=float(positive.mean()), meanPredictedGrowth=float(p_grow[mask].mean()),
               positiveRows=int(positive.sum()),
               positiveTeacherNll=float(-np.log(np.maximum(teacher[mask][positive], 1e-300)).mean()) if positive.any() else None,
               zeroTeacherNll=float(-np.log(np.maximum(teacher[mask][~positive], 1e-300)).mean()) if (~positive).any() else None)
    out.pop('qualified', None)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pilot', type=Path, action='append', required=True)
    parser.add_argument('--fast', nargs=2, metavar=('PATH', 'SHA256'),
                        default=[str(REPO/'selfplay/models'/v.ARTIFACTS['fast'][0]), v.ARTIFACTS['fast'][1]])
    parser.add_argument('--standard', nargs=2, metavar=('PATH', 'SHA256'),
                        default=[str(REPO/'selfplay/models'/v.ARTIFACTS['standard'][0]), v.ARTIFACTS['standard'][1]])
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--device', default='cuda')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    rows = load_rows(args.pilot)
    spec = {'fast': args.fast, 'standard': args.standard}
    keep, routes, excluded, teacher, mixture, p_grow, unscoreable = evaluate(rows, spec, args.device)
    potion = np.asarray([r['setup'].rsplit('_', 1)[-1] for r in keep])
    part = np.asarray([r['partition'] for r in keep]); route = np.asarray(routes)
    escaped = np.asarray([bool(r['post']['smokeBombUsed']) for r in keep])
    cohorts = {}
    for p in ('TRAIN', 'VALIDATION'):
        base = part == p
        cohorts[p] = cohort(base, keep, teacher, mixture, p_grow)
        for k in ('natural', 'brew', 'smoke'):
            cohorts[f'{p}/{k}'] = cohort(base & (potion == k), keep, teacher, mixture, p_grow)
        cohorts[f'{p}/smoke_escaped'] = cohort(base & (potion == 'smoke') & escaped, keep, teacher, mixture, p_grow)
        cohorts[f'{p}/smoke_not_escaped'] = cohort(base & (potion == 'smoke') & ~escaped, keep, teacher, mixture, p_grow)
        cohorts[f'{p}/pooled_not_escaped'] = cohort(base & ~escaped, keep, teacher, mixture, p_grow)
        for name in ('fast', 'standard'):
            cohorts[f'{p}/{name}'] = cohort(base & (route == name), keep, teacher, mixture, p_grow)
    np.savez_compressed(args.out/'row-evidence.npz', teacher=teacher, mixture=mixture, pGrow=p_grow,
                        source=np.asarray([r['source'] for r in keep]), partition=part, route=route, potion=potion,
                        escaped=escaped, unit=np.asarray([r['unitId'] for r in keep]),
                        fightIdx=np.asarray([r['fightIdx'] for r in keep]))
    result = dict(artifacts=spec, pilots=[str(p) for p in args.pilot], loadedRows=len(rows), excludedRows=excluded, potionUnscoreableRows=unscoreable,
                  scoredRows=len(keep), draws=DRAWS, seed=SEED, cohorts=cohorts,
                  rowEvidenceSha256=sha(args.out/'row-evidence.npz'), wallSeconds=time.monotonic()-started,
                  testEvaluated=False, trainingPerformed=False, supportChanged=False)
    v.write(args.out/'result.json', result)
    print(json.dumps(result, indent=1))


if __name__ == '__main__':
    main()
