#!/usr/bin/env python3
"""Supplemental frozen relic exposure on the original gold-only TEST rows."""
import argparse
import json
import subprocess
from pathlib import Path
import numpy as np
import torch
from tools import combat_transition_composed as c
from tools import combat_transition_composed_evaluate as e
from tools import combat_transition_gold_evaluate as gold


def run(folder, evaluation_sha):
    if e.snapshot() != evaluation_sha or subprocess.check_output(['git', 'status', '--porcelain'], text=True).strip():
        raise ValueError('require clean frozen evaluation SHA')
    output = folder / 'relic_diagnostics.json'
    if output.exists():
        raise ValueError('refusing to overwrite relic diagnostics')
    cache, metadata = gold.load_cache(folder)
    fitted = json.loads((folder / 'fit.json').read_text())
    if fitted['sourceSha'] != metadata['baseline'] or c.base.sha256(folder / 'gold.pt') != fitted['artifactSha256']:
        raise ValueError('gold checkpoint provenance changed')
    if e.verify_data() != metadata['hashes']:
        raise ValueError('frozen upstream provenance changed')
    rows = [json.loads(line) for line in (folder / 'test_rows.jsonl').read_text().splitlines()]
    rows = [r for r in rows if cache['win'][r['local']]]
    ids = np.asarray([r['local'] for r in rows], np.int64)
    if len(ids) != 7190 or not np.all(cache['split'][ids] == 2):
        raise ValueError('gold-only TEST victory accounting changed')
    compatible = {g: np.ones((len(ids), k), bool) for g, k in c.relic.HEAD_CLASSES.items() if g in c.TRAINED_GROUPS}
    observed = np.zeros(len(ids), np.int64)
    for i, row in enumerate(rows):
        pre, post, pi = row['pre'], row['post'], row['predictorInput']
        bloom = any(r['id'] == c.base._RELIC_IDS['MARK_OF_THE_BLOOM'] for r in pre['relics'])
        for group, values in c.relic.trajectory_constraints(pre['relics'], post['relics'], pi['globals']['encounter'], bloom).items():
            if group not in compatible:
                raise ValueError('unqualified observed relic group')
            compatible[group][i] = np.isin(np.arange(c.relic.HEAD_CLASSES[group]), list(values))
            observed[i] += 1
    torch.set_num_threads(4)
    m = c.FrozenModels('cuda')
    arrays, _ = c.base._load_prepared(e.PREPARED)
    potion_z = np.empty((len(ids), 64), np.float32)
    p_delta = np.empty((len(ids), len(m.delta_values)), float)
    teacher = np.empty(len(ids), float)
    with torch.inference_mode():
        for start in range(0, len(ids), 512):
            sl = slice(start, start + 512); sub = ids[sl]
            inputs = c.base._torch_inputs(arrays, cache['ids'][sub], 'cuda', torch, trim_padding=True)
            potion_z[sl] = m.fp32_encoding(m.potion_encoder.encoder, inputs).cpu().numpy()
            p_delta[sl] = e.probabilities(m.max_net.max_hp_delta(m.fp32_encoding(m.max_net.encoder, inputs)))
            rp = e.relic_prob(m, cache['z'][sub], cache['trueSigned'][sub] - c.CLASSES[0], cache['trueHp'][sub] / cache['trueMaxHp'][sub], cache['trueMask'][sub])
            teacher[sl] = e.nll(e.constraint_probability(rp, {g: v[sl] for g, v in compatible.items()}))
        rng = np.random.default_rng(gold.RECIPE['samplingSeed'])
        mass = np.empty((gold.RECIPE['draws'], len(ids)), float)
        for draw in range(gold.RECIPE['draws']):
            for start in range(0, len(ids), 512):
                sl = slice(start, start + 512); sub = ids[sl]
                delta = e.draw_categories(p_delta[sl], rng)
                maximum = cache['preMaxHp'][sub] + m.delta_values[delta]
                hp = e.hp_prob(m, cache['z'][sub], delta, cache['preHp'][sub], maximum)
                signed_class = e.draw_categories(hp, rng)
                ending = cache['preHp'][sub] + c.CLASSES[signed_class]
                pp = e.potion_prob(m, potion_z[sl], cache['prePotions'][sub], cache['capacity'][sub], delta, ending / maximum)
                target_mass = np.zeros(len(sub))
                for mask in range(32):
                    active = pp[:, mask] > 0
                    if active.any():
                        rp = e.relic_prob(m, cache['z'][sub[active]], signed_class[active], ending[active] / maximum[active], np.full(active.sum(), mask, np.int64))
                        target_mass[active] += pp[active, mask] * e.constraint_probability(rp, {g: v[sl][active] for g, v in compatible.items()})
                mass[draw, sl] = target_mass
            print(f'gold relic exposure {draw + 1}/32', flush=True)
    mixture = e.nll(mass.mean(0))
    gap = np.divide(mixture - teacher, observed, out=np.zeros(len(ids)), where=observed > 0)
    diagnostic = np.asarray([r['transmutationPlus'] for r in rows])
    groups = {'GOLD_UNION': ~diagnostic}
    for reason in sorted({reason for r in rows for reason in r['reasons']}):
        groups[reason] = np.asarray([reason in r['reasons'] for r in rows]) & ~diagnostic
    groups['TRANSMUTATION_PLUS_DIAGNOSTIC'] = diagnostic
    result_groups = {}
    for label, selection in groups.items():
        informative = selection & (observed > 0)
        result_groups[label] = dict(rows=int(selection.sum()), informativeRows=int(informative.sum()),
                                   meanExposureGap=float(gap[informative].mean()) if informative.any() else None,
                                   teacherConstraintNll=float(teacher[selection].mean()) if selection.any() else None,
                                   zeroMixtureProbabilityRows=int((mass.mean(0)[selection] == 0).sum()))
    gate = all(v['meanExposureGap'] is None or np.isfinite(v['meanExposureGap']) and v['meanExposureGap'] <= .1
               for k, v in result_groups.items() if k != 'TRANSMUTATION_PLUS_DIAGNOSTIC')
    result = dict(evaluationSha=evaluation_sha, goldSourceSha=fitted['sourceSha'], independentReview=False,
                  classification='RELIC_DEVELOPMENT_EXPOSURE_PASS_PENDING_REVIEW' if gate else 'RELIC_DEVELOPMENT_EXPOSURE_FAIL',
                  relicGate=bool(gate), groups=result_groups, frozenHashes=metadata['hashes'],
                  recipe='32 upstream maxHP/HP draws; exact conditional potion-mask marginal; constraint NLL gap per observed group',
                  supportChanged=False, gameplay=False)
    np.savez_compressed(folder / 'relic_diagnostic_rows.npz', ids=cache['ids'][ids], source=cache['source'][ids], observedGroups=observed,
                        teacherConstraintNll=teacher, mixtureConstraintNll=mixture, perGroupExposureGap=gap, transmutationPlus=diagnostic)
    gold.dump(output, result)
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--evaluation-sha', required=True)
    args = parser.parse_args()
    run(args.output_dir, args.evaluation_sha)
