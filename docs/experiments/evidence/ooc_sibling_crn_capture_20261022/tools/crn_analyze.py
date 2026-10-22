#!/usr/bin/env python3
"""Common-seed sibling recapture (ooc_sibling_crn_capture_20261022): rows, label noise and head re-scoring.

usage:
  crn_analyze.py rows EXTRACT OUT_DIR            EXTRACT = verify_campaign.py --extract dir (out/units/<seed>/...)
  crn_analyze.py noise OUT_DIR R2|- OUT.json     R2 = round-2 extracted dir (train/, validation/), for comparison
  crn_analyze.py score ONE_COMBAT OUT_DIR OUT.json NAME=weights.bin[@w] ...

`rows` keeps a capture row when its source is valid (rc 0, outcome complete and integrityPassed) and the row has 32
repeats with no error entry, common seeds, a heart1-public-record-v2 record, X2-B and the heart1 rollout policy; a
root with any bad row is dropped whole. It writes rows.jsonl (no records) and records.jsonl (one heart1 record per row,
same order, with obs.act, for one_combat heart1score). Split: VALIDATION is seed % 4 == 3, TRAIN the rest (PREREG.md).

Groups are one root's children with at least two actions; an action's value is the mean over its rows (chance
outcomes), as in §577. With common seeds, repeat r of every row of a root shares one stream, so per-repeat action
values v[a, r] can be differenced directly.
- noise: split-half agreement of the action order (repeats 0..h-1 vs 16..16+h-1; round 2: 0..h-1 vs 32..32+h-1), per
  root, then per source, then over sources; the ceiling of the §577 concordance for a perfect evaluator, with
  p(pair order wrong) = Phi(-|d| / se(d)) and se(d)^2 = var_r(v[i, r] - v[j, r]) / R (common seeds) or
  se_i^2 + se_j^2 (round 2's independent streams). Two ceilings add a hidden-state term for rows with independent
  hidden states, from hiddenVarSets of same_state_stats (rows with the same action and public record; sameX2b repeats
  it for #812's equal-X2-B sets, with the share that hold one record): ceilingHiddenProp adds c (se_i^2 + se_j^2)
  with independent streams' se, where c = sigma_h^2 / a row's stream variance (#812's f^2 - 1), and
  ceilingHiddenConst adds sigma_h^2 (1/k_i + 1/k_j) for actions over k_i, k_j rows. Siblings of a deterministic action
  share the root's hidden state, so both overstate their noise. pairSe2 is the mean stream variance of a sibling
  difference, pairIndependentSe2 the same with independent streams.
- score: each head's sigmoid(value) on the records, the blend sigmoid((1 - w) logit X2-B + w logit head) for NAME@w,
  §577 concordance and regret (outcome_head_sibling_check.group_metrics), paired source bootstrap against X2-B; on
  VALIDATION also by the root's screen. r0 is the row's own value, the search's single leaf evaluation.
"""
import glob
import gzip
import hashlib
import json
import math
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

REPO = Path(os.environ.get('STS_REPO') or Path(__file__).resolve().parents[5])  # docs/experiments/evidence/<c>/tools/
sys.path.insert(0, str(REPO / 'tools'))
from outcome_head_sibling_check import group_metrics, paired_bootstrap  # noqa: E402

R = 32
JOBS = int(os.environ.get('CRN_JOBS', '4'))
SCREENS = {1: 'event', 2: 'rewards', 3: 'bossRelic', 4: 'cardSelect', 5: 'map', 6: 'treasure', 7: 'rest', 8: 'shop'}
Phi = lambda x: 0.5 * (1 + math.erf(x / math.sqrt(2)))


def split_of(seed):
    return 'validation' if seed % 4 == 3 else 'train'


def rows_cmd(extract, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stats = defaultdict(int)
    with open(out_dir / 'rows.jsonl', 'w') as rows_out, open(out_dir / 'records.jsonl', 'w') as rec_out:
        for unit in sorted(glob.glob(f'{extract}/out/units/*/')):
            seed = int(Path(unit).name)
            done = open(f'{unit}/S-{seed}.done').read()
            policy = f'{unit}/S-{seed}.jsonl.gz'
            last = json.loads(gzip.open(policy, 'rt').readlines()[-1]) if Path(policy).exists() else {}
            if ' rc=0 ' not in done or not last.get('complete') or not last.get('integrityPassed'):
                stats['invalidSources'] += 1
                continue
            stats['sources'] += 1
            sib = f'{unit}/S-{seed}.sib.jsonl.gz'
            if not Path(sib).exists():
                continue
            accepted, bad = [], set()
            for raw in map(json.loads, gzip.open(sib, 'rt')):
                e, group = raw.get('extra', {}), (seed, raw['decision'], raw['parent'])
                reps = e.get('repeats', [])
                errors = sum('error' in v or 'value' not in v for v in reps)  # evaluateLeafUnobserved threw
                stats['errorRepeats'] += errors
                if (len(reps) != R or errors or raw.get('commonSeeds') is not True or 'record' not in e
                        or 'x2b' not in e or e.get('rolloutPolicy') != 'heart1'
                        or e.get('recordSchema') != 'heart1-public-record-v2'):
                    stats['badRows'] += 1
                    bad.add(group)
                    continue
                accepted.append(({'seed': seed, 'split': split_of(seed), 'group': list(group), 'action': raw['action'],
                                  'act': raw['act'], 'screen': raw['parentScreen'],
                                  'repeats': [float(v['value']) for v in reps], 'x2b': float(e['x2b']),
                                  'r0': float(raw['value']), 'heart': int(bool(last.get('heartKilled')))},
                                 {**e['record'], 'obs.act': raw['act']}))
            stats['droppedRoots'] += len(bad)
            for row, rec in accepted:
                if tuple(row['group']) in bad:
                    continue
                row['target'] = float(np.mean(row['repeats']))
                rows_out.write(json.dumps(row) + '\n')
                rec_out.write(json.dumps(rec) + '\n')
                stats['rows'] += 1
    print(json.dumps(stats))
    return stats


def load_rows(out_dir):
    rows = [json.loads(line) for line in open(Path(out_dir) / 'rows.jsonl')]
    for r in rows:
        r['group'] = tuple(r['group'])
    return rows


def groups_of(rows):
    g = defaultdict(list)
    for i, r in enumerate(rows):
        g[r['group']].append(i)
    return [ids for ids in g.values() if len({rows[i]['action'] for i in ids}) >= 2]


def action_matrix(rows, ids):
    """actions x repeats matrix of action values (mean over the action's rows) and each action's row count."""
    acts = defaultdict(list)
    for i in ids:
        acts[rows[i]['action']].append(rows[i]['repeats'])
    return np.array([np.mean(v, axis=0) for v in acts.values()]), [len(v) for v in acts.values()]


def agreement(a, b):
    ag = [.5 if a[i] == a[j] or b[i] == b[j] else float((a[i] - a[j]) * (b[i] - b[j]) > 0)
          for i in range(len(a)) for j in range(i)]
    return float(np.mean(ag))


def noise_stats(mats, seeds, common, half, hidden):
    """split-half curve and ceilings, per source mean of per-root values, then over sources. mats: (actions x repeats
    matrix, rows per action) per group; hidden: (c, sigma_h^2) for ceilingHiddenProp and ceilingHiddenConst."""
    c, s2h = hidden
    per = defaultdict(lambda: defaultdict(list))
    n = mats[0][0].shape[1] if mats else 0
    for (m, k), seed in zip(mats, seeds):
        src = per[seed]
        for h in sorted({1, 2, 4, 8, 16, half}):
            if 2 * h <= n:
                src[f'splitHalf{h}'].append(agreement(m[:, :h].mean(1), m[:, half:half + h].mean(1)))
        t = m.mean(1)
        pf, pp, pc, se2, ind2 = [], [], [], [], []
        for i in range(len(t)):
            for j in range(i):
                d = abs(t[i] - t[j])
                if d <= 1e-8:
                    continue
                ind2.append((m[i].var(ddof=1) + m[j].var(ddof=1)) / n)
                s2 = np.var(m[i] - m[j], ddof=1) / n if common else ind2[-1]
                se2.append(s2)
                for p, v in ((pf, s2), (pp, s2 + c * ind2[-1]), (pc, s2 + s2h * (1 / k[i] + 1 / k[j]))):
                    p.append(Phi(-d / math.sqrt(v)) if v > 0 else 0.0)
        if pf:
            for key, p in (('ceiling', pf), ('ceilingHiddenProp', pp), ('ceilingHiddenConst', pc)):
                src[key].append(float(np.mean([1 - q for q in p])))
            src['pairSe2'].append(float(np.mean(se2)))
            src['pairIndependentSe2'].append(float(np.mean(ind2)))
    agg = defaultdict(list)
    for d in per.values():
        for k, v in d.items():
            agg[k].append(float(np.mean(v)))
    return {k: {'mean': float(np.mean(v)), 'sources': len(v)} for k, v in sorted(agg.items())}


SIZES = ((2, 2), (3, 4), (5, 8), (9, None))


def same_state_stats(sets, seeds):
    """Rows of one root with the same action and the same public record differ only in hidden state, so their scatter
    is hidden state (#812 sr_noise.py grouped by equal X2-B values instead; most of those sets differ publicly, mostly
    in gold, HP, the boss or the cards offered, which X2-B partly ignores). sets: rows x repeats matrices; seeds: their
    sources.
    f = sqrt(between-row variance of the targets / predicted variance of a mean, sd^2 / n) as in #812, each set counted
    once. Over row pairs, d = v_k - v_l per repeat: E[dbar^2] = 2 sigma_h^2 + E[var(d) / n] for independent and common
    streams alike. hiddenVar = (E[dbar^2] - E[var(d) / n]) / 2 weights every pair equally, so large sets dominate it;
    hiddenVarSets counts each set once, like f, with a 95 % source-bootstrap interval, and rowStreamVar is a row's
    sd^2 / n, counted the same way. With common seeds a pair of identical hidden states has d = 0 in every repeat
    (identicalFraction, per set)."""
    if not sets:
        return {'sets': 0}
    obs, pred, ident, dbar2, dvar, hid, rvar = [], [], [], [], [], [], []
    for m in sets:
        n, t, terms = m.shape[1], m.mean(1), []
        obs.append(t.var(ddof=1))
        pred.append(float(np.mean(m.var(1) / n)))
        ident.append(float(all(np.array_equal(m[0], x) for x in m[1:])))
        rvar.append(float(np.mean(m.var(1, ddof=1) / n)))
        for k in range(len(m)):
            for l in range(k):
                d = m[k] - m[l]
                dbar2.append(d.mean() ** 2)
                dvar.append(d.var(ddof=1) / n)
                terms.append((dbar2[-1] - dvar[-1]) / 2)
        hid.append(float(np.mean(terms)))
    hid, ident, size = np.array(hid), np.array(ident), np.array([len(m) for m in sets])
    by_seed = defaultdict(list)
    for i, seed in enumerate(seeds):
        by_seed[seed].append(i)
    keys, rng = list(by_seed.values()), np.random.default_rng(0)
    boot = [hid[np.concatenate([keys[j] for j in rng.integers(len(keys), size=len(keys))])].mean() for _ in range(1000)]
    by_size = {}
    for lo, hi in SIZES:
        sel = (size >= lo) & (size <= (hi or size.max()))
        if sel.any():
            by_size[f'{lo}-{hi}' if hi else f'{lo}+'] = {'sets': int(sel.sum()),
                                                         'identicalFraction': float(ident[sel].mean()),
                                                         'hiddenVarSets': float(hid[sel].mean())}
    return {'sets': len(sets), 'pairs': len(dbar2), 'identicalFraction': float(ident.mean()),
            'f': math.sqrt(np.mean(obs) / np.mean(pred)), 'hiddenVar': float((np.mean(dbar2) - np.mean(dvar)) / 2),
            'hiddenVarSets': float(hid.mean()), 'hiddenVarSetsCi': [float(x) for x in np.percentile(boot, [2.5, 97.5])],
            'rowStreamVar': float(np.mean(rvar)), 'bySize': by_size, 'meanDbar2': float(np.mean(dbar2)),
            'meanStreamVar': float(np.mean(dvar))}


def hidden_terms(ss):
    """(c, sigma_h^2) for noise_stats from same_state_stats' hiddenVarSets; a negative estimate counts as 0."""
    h = max(ss.get('hiddenVarSets', 0.0), 0.0)
    return (h / ss['rowStreamVar'] if h else 0.0), h


def round2_validation(r2):
    """Round-2 VALIDATION groups as action x 64-repeat matrices (value_leaf_check.load_round2's acceptance), and its
    same-public-record and same-X2-B row sets with their sources."""
    mats, seeds, sets, sets_x2b, same_rec = [], [], [], [], []
    set_seeds, x2b_seeds = [], []
    for path in sorted(glob.glob(f'{r2}/validation/seed-*.sib.jsonl')):
        seed = int(path.split('seed-')[-1].split('.')[0])
        last = json.loads(open(path.replace('.sib.jsonl', '.states.jsonl')).readlines()[-1])
        if last.get('type') != 'outcome' or not last.get('complete') or not last.get('integrityPassed'):
            continue
        roots, bad = defaultdict(lambda: defaultdict(list)), set()
        for raw in map(json.loads, open(path)):
            e, group = raw.get('extra', {}), (raw['decision'], raw['parent'])
            reps = e.get('repeats', [])
            if (len(reps) != 64 or 'record' not in e or 'x2b' not in e or e.get('rolloutPolicy') != 'heart1'
                    or e.get('recordSchema') != 'heart1-public-record-v2'):
                bad.add(group)
                continue
            rec = hashlib.md5(json.dumps(e['record'], sort_keys=True).encode()).hexdigest()
            roots[group][raw['action']].append((rec, float(e['x2b']), [float(v['value']) for v in reps]))
        for group, acts in roots.items():
            if group not in bad and len(acts) >= 2:
                mats.append((np.array([np.mean([v for _, _, v in rs], axis=0) for rs in acts.values()]),
                             [len(rs) for rs in acts.values()]))
                seeds.append(seed)
                new = state_sets([[(h, v) for h, _, v in rs] for rs in acts.values()])
                new_x2b = state_sets([[(x, v) for _, x, v in rs] for rs in acts.values()])
                sets += new
                sets_x2b += new_x2b
                set_seeds += [seed] * len(new)
                x2b_seeds += [seed] * len(new_x2b)
                same_rec += one_record([[(x, h) for h, x, _ in rs] for rs in acts.values()])
    return mats, seeds, (sets, set_seeds), (sets_x2b, x2b_seeds), same_rec


def state_sets(actions):
    """row sets (>= 2 rows) of one root with the same action and key; actions: lists of (key, repeats)."""
    out = []
    for rs in actions:
        same = defaultdict(list)
        for key, v in rs:
            same[key].append(v)
        out += [np.array(v) for v in same.values() if len(v) >= 2]
    return out


def one_record(actions):
    """per same-X2-B row set (>= 2 rows) of one root, whether all its rows share one public record; actions: lists of
    (x2b, record hash)."""
    out = []
    for rs in actions:
        recs, n = defaultdict(set), defaultdict(int)
        for x2b, h in rs:
            recs[x2b].add(h)
            n[x2b] += 1
        out += [len(recs[k]) == 1 for k in recs if n[k] >= 2]
    return out


def record_hashes(out_dir):
    """md5 of each records.jsonl line, in rows.jsonl's order; all records come from one serializer, so equal public
    records give equal lines."""
    return [hashlib.md5(line).hexdigest() for line in open(Path(out_dir) / 'records.jsonl', 'rb')]


def noise_cmd(out_dir, r2, out):
    rows = load_rows(out_dir)
    hashes = record_hashes(out_dir)
    if len(hashes) != len(rows):
        raise ValueError('records.jsonl and rows.jsonl differ in length')
    groups = groups_of(rows)
    res = {}
    for split in ('validation', 'train'):
        gs = [g for g in groups if rows[g[0]]['split'] == split]
        sets, sets_x2b, same_rec, set_seeds, x2b_seeds = [], [], [], [], []
        for g in gs:
            acts, acts_x2b, acts_rec = defaultdict(list), defaultdict(list), defaultdict(list)
            for i in g:
                acts[rows[i]['action']].append((hashes[i], rows[i]['repeats']))
                acts_x2b[rows[i]['action']].append((rows[i]['x2b'], rows[i]['repeats']))
                acts_rec[rows[i]['action']].append((rows[i]['x2b'], hashes[i]))
            new, new_x2b = state_sets(acts.values()), state_sets(acts_x2b.values())
            sets += new
            sets_x2b += new_x2b
            set_seeds += [rows[g[0]]['seed']] * len(new)
            x2b_seeds += [rows[g[0]]['seed']] * len(new_x2b)
            same_rec += one_record(acts_rec.values())
        ss = same_state_stats(sets, set_seeds)
        res[split] = {'groups': len(gs), 'sources': len({rows[g[0]]['seed'] for g in gs}), 'sameState': ss,
                      'sameX2b': {**same_state_stats(sets_x2b, x2b_seeds),
                                  'oneRecordFraction': float(np.mean(same_rec))},
                      **noise_stats([action_matrix(rows, g) for g in gs], [rows[g[0]]['seed'] for g in gs], True,
                                    R // 2, hidden_terms(ss))}
    if r2 and r2 != '-':
        mats, seeds, (sets, set_seeds), (sets_x2b, x2b_seeds), same_rec = round2_validation(r2)
        ss = same_state_stats(sets, set_seeds)
        res['round2Validation'] = {'groups': len(mats), 'sources': len(set(seeds)), 'sameState': ss,
                                   'sameX2b': {**same_state_stats(sets_x2b, x2b_seeds),
                                               'oneRecordFraction': float(np.mean(same_rec))},
                                   **noise_stats(mats, seeds, False, 32, hidden_terms(ss))}
    Path(out).write_text(json.dumps(res, indent=1) + '\n')
    for k, v in res.items():
        print(k, {m: (round(x['mean'], 4) if 'mean' in x else x) if isinstance(x, dict) else x for m, x in v.items()})
    return res


def head_values(binary, out_dir, weights):
    """heart1score's raw value for every line of records.jsonl, cached in values-<stem>.txt. The records are split
    once into JOBS line-aligned parts that are scored in parallel; the bulky score files are deleted."""
    out_dir = Path(out_dir).resolve()
    cache = out_dir / f'values-{Path(weights).stem}.txt'
    if not cache.exists():
        parts = sorted(out_dir.glob('records.part.[0-9][0-9]'))
        if not parts:
            subprocess.run(['split', '-n', f'l/{JOBS}', '-d', str(out_dir / 'records.jsonl'),
                            str(out_dir / 'records.part.')], check=True)
            parts = sorted(out_dir.glob('records.part.[0-9][0-9]'))
        procs = [subprocess.Popen([str(Path(binary).resolve()), 'heart1score', str(Path(weights).resolve()), str(p),
                                   f'{p}.score'], cwd=REPO, stdout=subprocess.DEVNULL)  # models are read from the repo
                 for p in parts]
        if any(q.wait() for q in procs):
            raise RuntimeError(f'heart1score failed for {weights}')
        with open(f'{cache}.tmp', 'w') as f:
            for p in parts:
                for line in open(f'{p}.score'):
                    f.write(repr(float(json.loads(line)['value'])) + '\n')
                os.unlink(f'{p}.score')
        os.replace(f'{cache}.tmp', cache)
    return [float(x) for x in open(cache)]


def score_cmd(binary, out_dir, out, *nets):
    rows = load_rows(out_dir)
    lg = lambda p: math.log(min(max(p, 1e-7), 1 - 1e-7) / (1 - min(max(p, 1e-7), 1 - 1e-7)))
    keys, raw_done = ['x2b', 'r0'], {}
    for spec in nets:
        name, weights = spec.split('=', 1)
        weights, _, w = weights.partition('@')
        if weights not in raw_done:
            raw_done[weights] = head_values(binary, out_dir, weights)
            if len(raw_done[weights]) != len(rows):
                raise ValueError('heart1score row count mismatch')
        w = float(w) if w else None
        for r, v in zip(rows, raw_done[weights]):
            r[name] = 1 / (1 + math.exp(-((1 - w) * lg(r['x2b']) + w * v))) if w is not None else 1 / (1 + math.exp(-v))
        keys.append(name)
    groups = groups_of(rows)
    rep = {'nets': list(nets)}
    for split in ('validation', 'train'):
        gs = [g for g in groups if rows[g[0]]['split'] == split]
        rep[split] = {'groups': len(gs), 'sources': len({rows[g[0]]['seed'] for g in gs}),
                      'all': {k: group_metrics(rows, gs, k)[0] for k in keys},
                      'minusX2b': {k: paired_bootstrap(rows, gs, k, 'x2b') for k in keys if k != 'x2b'}}
    gs = [g for g in groups if rows[g[0]]['split'] == 'validation']
    rep['validation']['byScreen'] = {}
    for code, screen in SCREENS.items():  # the parent screen of the root
        sg = [g for g in gs if rows[g[0]]['screen'] == code]
        if sg:
            rep['validation']['byScreen'][screen] = {
                'groups': len(sg), 'sources': len({rows[g[0]]['seed'] for g in sg}),
                'concordance': {k: group_metrics(rows, sg, k)[0]['concordance'] for k in keys},
                'minusX2b': {k: paired_bootstrap(rows, sg, k, 'x2b')['concordance'] for k in keys if k != 'x2b'}}
    Path(out).write_text(json.dumps(rep, indent=1) + '\n')
    v = rep['validation']
    for k in keys:
        d = v['minusX2b'].get(k, {}).get('concordance')
        print(f"{k:16s} conc {v['all'][k]['concordance']:.4f} regret {v['all'][k]['regret']:.4f}"
              + (f"  - X2-B {d['mean']:+.4f} [{d['ci95'][0]:+.4f}, {d['ci95'][1]:+.4f}]" if d else ''))
    return rep


if __name__ == '__main__':
    cmd, args = (sys.argv[1], sys.argv[2:]) if len(sys.argv) > 1 else ('', [])
    {'rows': rows_cmd, 'noise': noise_cmd, 'score': score_cmd}.get(cmd, lambda *a: sys.exit(__doc__))(*args)
