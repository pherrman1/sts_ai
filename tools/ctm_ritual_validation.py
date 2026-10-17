#!/usr/bin/env python3
"""Actual A0 artifact children on preserved VALIDATION: Ritual exposure, no fit."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import signal
import subprocess
import sys
import time
import zipfile
import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPO/'tools'), str(REPO)]
from ctm_development_cache import require, header, selected_rows

ROOT = Path('/home/philippherrmann/Documents/sts/wt-ctm-retrain/build/ctm-retrain-a69f8862')
PARENT = ROOT/'prom'
PINS = ROOT/'pins-12.json'
PINS_SHA = 'c5fc22b3592675bc3b34854d5da59f7755560394e009977d01d5e435a10465db'
PROTOCOL = REPO/'docs/experiments/evidence/ctm_ritual_validation_20261017/PROTOCOL.md'
CUSTODY_RECEIPT = PROTOCOL.parent/'custody.json'
CUSTODY_RECEIPT_SHA = 'f5959d359a761f9dfb3c0eaac563e37b582b50067f37c5bc3052b7cb47403801'
DS, PT = 'full-union-downstream-v1/', 'potion-trajectory-v2/'
DATA = {
    DS+'cache.npz': 'fe4aec50843c151a33e603190358636c9ad74d78948f520a0b58c9efe3c81fa0',
    DS+'affected_rows.jsonl': '4f6d6d5b06fa44534f51de8214dd740f48653f606a283d9ba7d9b76546e164fc',
    PT+'cache.npz': '1171a925195c61437e12988e1822fe39b792371c93e72329b1e88a7a699ab598',
}
ARTIFACTS = {
    'fast': ['combat_transition_deepsets_pathb_r2_lizard.native', 'c6d56bbc959f4d5de8fe1dd57f58a922112cd8323bcbac9711e0aecda93f5a3c'],
    'standard': ['combat_transition_near_full_escape_pathb_r2.native', 'b9188de03ed6cc0611094c108f607a8770a5d5c5f367c157851bc6af91f8d9cf'],
}
DRAWS, SEED, SECONDS, GPU_BYTES, RAM_BYTES = 32, 20260920, 300, 1_900_000_000, 8_000_000_000


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''): h.update(block)
    return h.hexdigest()


def write(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False); stream.write('\n')


def identity():
    def git(*args): return subprocess.check_output(['git', '-C', str(REPO), *args], text=True).strip()
    require(not git('status', '--porcelain'), 'require clean committed source')
    paths = sorted((REPO/'tools').glob('*.py')) + [PROTOCOL, CUSTODY_RECEIPT,
        REPO/'tests/test_ctm_development_cache.py', REPO/'tests/test_ctm_ritual_validation.py',
        REPO/'tests/test_ctm_artifact_torch.py']
    return {'sourceSha': git('rev-parse', 'HEAD'), 'files': {str(p.relative_to(REPO)): sha(p) for p in paths}}


def custody():
    require(sha(PINS) == PINS_SHA and sha(CUSTODY_RECEIPT) == CUSTODY_RECEIPT_SHA, 'historical data/custody pins differ')
    for path, digest in DATA.items(): require(sha(PARENT/path) == digest, 'cache custody differs: '+path)
    for filename, digest in ARTIFACTS.values():
        require(sha(REPO/'selfplay/models'/filename) == digest, 'deployed artifact differs: '+filename)
    return {'data': DATA, 'artifacts': ARTIFACTS, 'dataPinsSha256': PINS_SHA, 'custodyReceiptSha256': CUSTODY_RECEIPT_SHA}


def read_member(path, key, keep=None):
    with zipfile.ZipFile(path) as archive:
        require(archive.namelist().count(key+'.npy') == 1, 'missing/duplicate cache member')
        with archive.open(key+'.npy') as stream:
            shape, dtype = header(stream)
            return selected_rows(stream, shape, dtype, np.ones(shape[0], bool) if keep is None else keep)


def read_records(path, wanted, total):
    """Discard other JSON rows using only their index-first ASCII prefix."""
    records, previous = {}, -1
    with Path(path).open('rb') as stream:
        for raw in stream:
            match = re.match(rb'^\{"index": ([0-9]+),', raw)
            require(match is not None, 'missing index-first record prefix')
            index = int(match.group(1)); require(previous < index < total, 'invalid affected-row order/index')
            previous = index
            if index in wanted:
                record = json.loads(raw); require(record['index'] == index, 'record index differs')
                records[index] = record
    require(set(records) == set(wanted), 'selected validation record missing')
    return records


def extract():
    potion, downstream = PARENT/(PT+'cache.npz'), PARENT/(DS+'cache.npz')
    ids, split, source = (read_member(potion, key) for key in ('ids', 'split', 'source'))
    require(np.array_equal(ids, np.arange(len(ids))) and len(split) == len(source) == len(ids)
            and np.isin(split, [0, 1, 2]).all(), 'source/index contract differs')
    groups = [set(source[split == s].tolist()) for s in range(3)]
    require(all(not groups[a] & groups[b] for a, b in ((0, 1), (0, 2), (1, 2))), 'source overlap')
    val = split == 1
    win = read_member(potion, 'win', val)
    active = read_member(downstream, 'writhing', val) & read_member(downstream, 'dagger', val)
    chosen = ids[val][win & active]
    require(len(chosen) == 143 and len(set(source[chosen])) == 68, 'frozen validation census differs')
    keep = np.zeros(len(ids), bool); keep[chosen] = True
    cache = {'ids': chosen, 'split': split[chosen], 'source': source[chosen]}
    # No historical encoder vectors or posterior weights are reused.
    for key in ('preHp', 'preMax', 'trueHp', 'trueMax', 'potions', 'capacity', 'boss'):
        cache[key] = read_member(potion, key, keep)
    return cache, read_records(PARENT/(DS+'affected_rows.jsonl'), set(chosen.tolist()), len(ids))


def freeze(args):
    ident = identity(); review = json.loads(args.review.read_text())
    require(review.get('verdict') == 'PASS' and review.get('identity') == ident, 'independent review identity differs')
    bound = custody(); cache, records = extract()
    args.out.mkdir(parents=True, exist_ok=False)
    np.savez_compressed(args.out/'validation.npz', **cache); write(args.out/'validation-records.json', records)
    write(args.out/'freeze.json', {'identity': ident, 'custody': bound, 'reviewSha256': sha(args.review),
          'inputs': {n: sha(args.out/n) for n in ('validation.npz', 'validation-records.json')},
          'draws': DRAWS, 'seed': SEED, 'seconds': SECONDS, 'gpuBytes': GPU_BYTES, 'ramBytes': RAM_BYTES,
          'cpuThreads': 4, 'testAccessAuthorized': False, 'fitAuthorized': False, 'supportChanged': False})


def route(pre, brew_id):
    return 'standard' if brew_id in pre['potions'][:pre['potionCapacity']] else 'fast'


def encoding_batch(encoded):
    """Materialize only public component features across the Torch/NumPy API."""
    return (np.concatenate([v['z'].detach().cpu().numpy() for v in encoded]),
            np.concatenate([v['potion_z'].detach().cpu().numpy() for v in encoded]),
            np.concatenate([v['p_delta'] for v in encoded]))


def exclusions(record, relic_ids):
    pre = record['pre']; relics = {r['id']: r['data'] for r in pre['relics']}
    reasons = []
    if pre['smokeBombUsed']: reasons.append('pre_smoke_used')
    if relics.get(relic_ids['LIZARD_TAIL']) == 1 and relic_ids['MARK_OF_THE_BLOOM'] not in relics:
        reasons.append('active_tail_requires_composed_correction')
    return reasons


def target_mass(amounts, probabilities, target):
    if target not in amounts: return 0.
    value = float(probabilities[amounts.index(target)])
    require(np.isfinite(value) and 0 <= value <= 1+1e-6, 'invalid native target mass')
    return value


def teacher_options(artifact, encoded, record, delta, boss, t):
    pre, post = record['pre'], record['post']
    # Reconstruct only the observed generation body (a label), never future
    # model inputs. Current artifact probabilities recompute its exact posterior.
    state = dict(pre['combatRng'][4]); target = post['combatRng'][4]; generated = []
    require(0 <= target['counter']-state['counter'] <= 4096, 'unbounded historical generation body')
    while state['counter'] < target['counter']: generated.append(t.brew.draw_native(state))
    require(state == target, 'historical native generation body differs')
    graph = t.target_graph(pre, post, generated, boss)
    n = len(graph.inventories)
    bit = int(post['smokeBombUsed'] and artifact.escape.eligible(pre['potions'], pre['potionCapacity'], boss))
    lp = t.log_probabilities(artifact.potion_net, np.repeat(encoded['potion_z'][None], n, axis=0),
        graph.inventories, np.full(n, pre['potionCapacity']), np.full(n, delta),
        np.full(n, post['curHp']/post['maxHp']), np.full(n, boss), np.full(n, bit))
    # Structural zeros are explicit evidence, never smoothed or reweighted.
    if not np.any(np.isfinite(lp.detach().cpu().numpy())): return []
    if float(t.target_log_probability(lp, graph, include_generation=False).exp()) == 0: return []
    posterior, total = t.trace_posterior(lp, graph)
    if total <= 0: return []
    return [(dict(initialMask=int(code)&31,
                  consumed=[p for b, p in enumerate(t.EFFECT_IDS) if (int(code)>>5)&(1<<b)],
                  outcome='ESCAPE' if post['smokeBombUsed'] else 'VICTORY'), float(posterior[code]))
            for code in np.flatnonzero(posterior > 0)]


def summary(teacher, mixture, sources, bootstrap):
    require(np.isfinite(teacher).all() and np.isfinite(mixture).all()
            and np.all((teacher >= 0) & (teacher <= 1+1e-6))
            and np.all((mixture >= 0) & (mixture <= 1+1e-6)), 'invalid probability')
    with np.errstate(divide='ignore', invalid='ignore'):
        tnll, mnll = -np.log(teacher), -np.log(mixture); gap = mnll-tnll
    finite = bool(np.isfinite(gap).all())
    return {'rows': len(teacher), 'sources': len(set(sources.tolist())),
            'teacherNll': float(tnll.mean()) if np.isfinite(tnll).all() else None,
            'mixtureNll': float(mnll.mean()) if np.isfinite(mnll).all() else None,
            'meanGap': float(gap.mean()) if finite else None,
            'zeroTeacherMassRows': int((teacher == 0).sum()), 'zeroMixtureMassRows': int((mixture == 0).sum()),
            'sourceBootstrap': bootstrap(sources, gap) if finite else None,
            'finiteGap': finite, 'qualified': False}, tnll, mnll, gap


def run(args):
    frozen = json.loads((args.out/'freeze.json').read_text())
    require(frozen['identity'] == identity() and frozen['custody'] == custody()
            and frozen['reviewSha256'] == sha(args.review)
            and (frozen['draws'], frozen['seed'], frozen['seconds'], frozen['gpuBytes'], frozen['ramBytes'], frozen['cpuThreads'])
            == (DRAWS, SEED, SECONDS, GPU_BYTES, RAM_BYTES, 4)
            and not frozen['testAccessAuthorized'] and not frozen['fitAuthorized'] and not frozen['supportChanged'], 'freeze differs')
    for name, digest in frozen['inputs'].items(): require(sha(args.out/name) == digest, 'sanitized input differs')
    with np.load(args.out/'validation.npz', allow_pickle=False) as z: cache = {k: z[k] for k in z.files}
    require(len(cache['ids']) == 143 and np.all(cache['split'] == 1), 'non-VALIDATION input')
    records = {int(k): v for k, v in json.loads((args.out/'validation-records.json').read_text()).items()}
    write(args.out/'evaluation-started.json', {'sourceSha': frozen['identity']['sourceSha'], 'unixTime': time.time()})
    require(not os.environ.get('STS_CTM_PINS') or Path(os.environ['STS_CTM_PINS']).resolve() == PINS.resolve(), 'conflicting data pins')
    os.environ['STS_CTM_PINS'] = str(PINS)
    import torch
    from tools.ctm_artifact_torch import load_artifact
    from tools import combat_transition_near_full_sampler as s
    from tools import combat_transition_composed_evaluate as e
    t, c = s.trajectory, s.c
    require(torch.cuda.is_available(), 'CUDA required for bounded artifact baseline')
    torch.set_num_threads(4)
    torch.cuda.set_per_process_memory_fraction(min(1., GPU_BYTES/torch.cuda.get_device_properties(0).total_memory))
    started = time.monotonic()
    def stop(_signum, _frame): raise TimeoutError('bounded validation wall exceeded')
    old_handler = signal.signal(signal.SIGALRM, stop); signal.alarm(SECONDS)
    def budget():
        require(time.monotonic()-started < SECONDS and torch.cuda.max_memory_allocated() < GPU_BYTES
                and resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024 < RAM_BYTES, 'resource budget exceeded')
    try:
        artifacts = {name: load_artifact(REPO/'selfplay/models'/file, digest, device='cuda')
                     for name, (file, digest) in ARTIFACTS.items()}
        routes, excluded, rows, positions = [], {}, [], []
        for i, index in enumerate(cache['ids']):
            record = records[int(index)]; reasons = exclusions(record, c.base._RELIC_IDS)
            name = route(record['pre'], t.BREW)
            reasons += s.support.final_reasons(record['pi'], record['pre'], artifacts[name],
                                               escape=True, writhing_ritual=True)
            if reasons: excluded[str(int(index))] = reasons; continue
            rows.append(record); positions.append(i); routes.append(name)
        require(rows, 'empty ordinary-child diagnostic cohort')
        indices = np.asarray(positions); sources = cache['source'][indices]; ids = cache['ids'][indices]
        teacher, mixture = np.zeros(len(rows)), np.zeros(len(rows))
        route_counts = {}; rng = np.random.default_rng(SEED)
        with torch.inference_mode():
            for name, artifact in artifacts.items():
                chosen = np.flatnonzero(np.asarray(routes) == name); route_counts[name] = len(chosen)
                if not len(chosen): continue
                budget(); rr = [rows[i] for i in chosen]
                enc = [artifact.encode_predictor(r['pi']) for r in rr]
                z, zp, pd = encoding_batch(enc); pre = cache['preHp'][indices[chosen]]
                premax = cache['preMax'][indices[chosen]]; boss = cache['boss'][indices[chosen]]
                require(np.array_equal(artifact.classes, c.CLASSES), 'HP class binding differs')
                for j, (i, record) in enumerate(zip(chosen, rr)):
                    actual_delta = record['post']['maxHp']-record['pre']['maxHp']
                    delta_positions = np.flatnonzero(artifact.delta_values == actual_delta)
                    require(len(delta_positions) == 1, 'teacher maxHP target outside artifact')
                    options = teacher_options(artifact, {'potion_z': zp[j]}, record, int(delta_positions[0]), bool(boss[j]), t)
                    for trace, weight in options:
                        amounts, probabilities = s.ritual_probabilities(artifact.ritual_net, z[j], record['pre'], record['pi'],
                            record['post']['curHp'], record['post']['maxHp'], trace['initialMask'], tuple(trace['consumed']), trace['outcome']=='ESCAPE')
                        teacher[i] += weight*target_mass(amounts, probabilities, tuple(record['daggerTarget']))
                eligible = np.asarray([artifact.escape.eligible(r['pre']['potions'], r['pre']['potionCapacity'], bool(b)) for r,b in zip(rr,boss)])
                p_escape = np.where(eligible, artifact.escape_probability(z), 0.)
                for draw in range(DRAWS):
                    budget(); delta = e.draw_categories(pd, rng); maximum = premax+artifact.delta_values[delta]
                    bit = (rng.random(len(rr)) < p_escape).astype(np.int64)
                    hp = artifact.hp_probabilities(z, delta, pre, maximum, bit)
                    ending = pre+artifact.classes[e.draw_categories(hp, rng)]
                    traces = s.sample_potions_batch(artifact.potion_net, zp, [r['pre'] for r in rr], delta,
                                                   ending/maximum, rng, boss, escape=bit)
                    for j, (i, record, trace) in enumerate(zip(chosen, rr, traces)):
                        amounts, probabilities = s.ritual_probabilities(artifact.ritual_net, z[j], record['pre'], record['pi'],
                            ending[j], maximum[j], trace['initialMask'], tuple(trace['consumed']), trace['outcome']=='ESCAPE')
                        mixture[i] += target_mass(amounts, probabilities, tuple(record['daggerTarget']))/DRAWS
                    print(json.dumps({'route': name, 'draw': draw+1, 'rows': len(rr)}), flush=True)
        generated_escape = np.asarray([r['post']['smokeBombUsed'] and not any(p==t.SMOKE for p in r['pre']['potions']) for r in rows])
        ordinary = ~generated_escape
        require(ordinary.any(), 'empty ordinary observation cohort')
        result, tnll, mnll, gap = summary(teacher[ordinary], mixture[ordinary], sources[ordinary], e.source_gap_bootstrap)
        diagnostics = summary(teacher[generated_escape], mixture[generated_escape], sources[generated_escape], e.source_gap_bootstrap)[0] if generated_escape.any() else None
        budget(); np.savez_compressed(args.out/'row-evidence.npz', ids=ids, source=sources, teacherMass=teacher,
            mixtureMass=mixture, brewGeneratedEscape=generated_escape, ordinaryTeacherNll=tnll, ordinaryMixtureNll=mnll, ordinaryGap=gap)
        result.update(classification='CURRENT_CHILD_RITUAL_VALIDATION_DIAGNOSTIC', independentHoldout=False,
            artifacts=ARTIFACTS, routeCounts=route_counts, excludedRows=excluded, frozenRows=143,
            brewGeneratedEscapeDiagnostic=diagnostics, draws=DRAWS, seed=SEED, testEvaluated=False,
            trainingPerformed=False, supportChanged=False, activeTailCorrectionEvaluated=False,
            rowEvidenceSha256=sha(args.out/'row-evidence.npz'), wallSeconds=time.monotonic()-started,
            peakCudaAllocated=torch.cuda.max_memory_allocated(), peakRssBytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
            torchVersion=str(torch.__version__), cudaVersion=torch.version.cuda, device=torch.cuda.get_device_name(0))
        write(args.out/'result.json', result); print(json.dumps(result, indent=2), flush=True)
    finally:
        signal.alarm(0); signal.signal(signal.SIGALRM, old_handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('identity', 'freeze', 'run'))
    parser.add_argument('--out', type=Path); parser.add_argument('--review', type=Path)
    args = parser.parse_args()
    if args.command == 'identity': print(json.dumps(identity(), indent=2))
    else:
        require(args.out is not None and args.review is not None, '--out/--review required')
        (freeze if args.command == 'freeze' else run)(args)


if __name__ == '__main__': main()
