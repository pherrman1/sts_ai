#!/usr/bin/env python3
"""Issue #1056 paired probes: frozen analysis (PREREG.md). Descriptive; no gate, no default change.

    python3 -I analyze.py UNITS_DIR UNITS_TXT SRC_DIR OUT_JSON [--partial]

UNITS_DIR holds one directory per unit, named as tools/cloud/worker.sh names it (the units.txt line with every character
outside [A-Za-z0-9._-] replaced by '_'), with A-SEED-IDX.* and B-SEED-IDX.* inside, as unpacked from the share tars.
SRC_DIR holds §782's G16 traces (out/units/*/G16-SEED.trace.jsonl.gz). --partial skips the completeness check (for the
live dashboard); the final reading is made without it.
"""
import glob
import gzip
import json
import math
import os
import random
import re
import sys

PATTERNS = ('smith', 'elite', 'corruption', 'runic')
INVALID_SHARE = 0.05      # a pattern whose share of failed validity checks among eligible units exceeds this: INVALID


def read_done(path):
    if not os.path.exists(path):
        return None
    kv = dict(w.split('=', 1) for w in open(path).read().split() if '=' in w)
    return kv


def read_jsonl(path):
    if not os.path.exists(path):
        return None
    with gzip.open(path, 'rt') as f:
        return [json.loads(l) for l in f if l.strip()]


def prefix(trace, index):
    """Records before out-of-combat decision INDEX, plus that decision's pre state."""
    out = []
    for r in trace:
        if r['kind'] == 'ooc' and r['idx'] == index:
            out.append(('pre', r['pre']))
            return out
        out.append(r)
    return None


def unit_result(udir, label, pattern, seed, index, key, src):
    res = {'unit': label, 'pattern': pattern, 'seed': seed, 'idx': index, 'status': 'pending'}
    da = read_done('%s/A-%d-%d.done' % (udir, seed, index))
    db = read_done('%s/B-%d-%d.done' % (udir, seed, index))
    if da is None:
        return res
    if da.get('ineligible') == '1':
        res['status'] = 'ineligible'
        return res
    if db is None:
        return res
    for tag, d in (('A', da), ('B', db)):
        if d.get('rc') != '0':
            res.update(status='drop', why='%s rc=%s' % (tag, d.get('rc')))
            return res
        if d.get('abort') != '0':
            res.update(status='drop', why='%s combat abort' % tag)
            return res
    ta = read_jsonl('%s/A-%d-%d.trace.jsonl.gz' % (udir, seed, index))
    tb = read_jsonl('%s/B-%d-%d.trace.jsonl.gz' % (udir, seed, index))
    pa = read_jsonl('%s/A-%d-%d.ppo.jsonl.gz' % (udir, seed, index))
    pb = read_jsonl('%s/B-%d-%d.ppo.jsonl.gz' % (udir, seed, index))
    if None in (ta, tb, pa, pb):
        res.update(status='invalid', why='missing trace')
        return res
    # validity 1: both games replay §782's game up to decision INDEX
    ps = prefix(src, index)
    if ps is None or prefix(ta, index) != ps or prefix(tb, index) != ps:
        res.update(status='invalid', why='prefix differs from §782')
        return res
    # validity 2: B made the production choice, A the forced token, and they differ
    src_rec = next(r for r in src if r['kind'] == 'ooc' and r['idx'] == index)
    da_ = next((r for r in pa if r.get('type') == 'decision' and r['idx'] == index), None)
    db_ = next((r for r in pb if r.get('type') == 'decision' and r['idx'] == index), None)
    rb = next((r for r in tb if r['kind'] == 'ooc' and r['idx'] == index), None)
    ra = next((r for r in ta if r['kind'] == 'ooc' and r['idx'] == index), None)
    if not (da_ and db_ and ra and rb):
        res.update(status='invalid', why='decision INDEX missing')
        return res
    if da_.get('forced') != key or db_.get('forced') not in (None, '') or da_['chosen'] == db_['chosen']:
        res.update(status='invalid', why='forced token not applied')
        return res
    if rb['post'] != src_rec['post']:
        res.update(status='invalid', why='B decision differs from §782')
        return res
    ga = next((r for r in pa if r.get('type') == 'game'), None)
    gb = next((r for r in pb if r.get('type') == 'game'), None)
    if not (ga and gb):
        res.update(status='invalid', why='no game line')
        return res
    act0 = src_rec['pre']['act']

    def outcome(g):
        o = g['outcome']
        return {'heart': int(bool(o['heart_kill'])), 'floor': o['floor'], 'act': o['act'],
                'past_act': int(bool(o['heart_kill']) or o['act'] > act0)}

    def next_value(p):
        nxt = [r for r in p if r.get('type') == 'decision' and r['idx'] > index and r.get('value') is not None]
        return nxt[0]['value'] if nxt else None

    res.update(status='ok', A=outcome(ga), B=outcome(gb), vA=next_value(pa), vB=next_value(pb),
               chosen_A=da_['chosen'], chosen_B=db_['chosen'], p_B=math.exp(db_['logp']) if db_.get('logp') is not None else None,
               value_at=db_.get('value'))
    return res


def ci_mean(d, rng, n_boot=10000):
    n = len(d)
    if n == 0:
        return None
    m = sum(d) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in d) / (n - 1)) if n > 1 else 0.0
    se = sd / math.sqrt(n) if n else 0.0
    boots = sorted(sum(d[rng.randrange(n)] for _ in range(n)) / n for _ in range(n_boot))
    return {'n': n, 'mean': m, 'se': se, 'ci95_normal': [m - 1.96 * se, m + 1.96 * se],
            'ci95_boot': [boots[int(0.025 * n_boot)], boots[int(0.975 * n_boot) - 1]]}


def sign_test(plus, minus):
    """Two-sided exact binomial p on the discordant pairs (McNemar exact)."""
    n = plus + minus
    if n == 0:
        return 1.0
    k = min(plus, minus)
    p = sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n
    return min(1.0, 2 * p)


def main():
    udir, units_txt, src_dir, out = sys.argv[1:5]
    partial = '--partial' in sys.argv[5:]
    rng = random.Random(1056)
    lines = [l.strip() for l in open(units_txt) if l.strip() and not l.startswith('#')]
    srcs = {}
    rows = []
    for line in lines:
        label, pattern, seed, index, salt, key = line.split()
        seed, index = int(seed), int(index)
        if seed not in srcs:
            f = glob.glob('%s/out/units/*/G16-%d.trace.jsonl.gz' % (src_dir, seed))
            srcs[seed] = read_jsonl(f[0]) if f else None
        if srcs[seed] is None:
            raise SystemExit('no §782 trace for %d' % seed)
        rows.append(unit_result('%s/%s' % (udir, re.sub(r'[^A-Za-z0-9._-]', '_', line)), label, pattern, seed, index, key, srcs[seed]))
    summary = {'partial': partial, 'patterns': {}}
    pvals = {}
    for pat in PATTERNS:
        rs = [r for r in rows if r['pattern'] == pat]
        ok = [r for r in rs if r['status'] == 'ok']
        cnt = {s: sum(r['status'] == s for r in rs) for s in ('ok', 'drop', 'invalid', 'ineligible', 'pending')}
        eligible = len(rs) - cnt['ineligible'] - cnt['pending']
        s = {'counts': cnt, 'units': len(rs)}
        s['valid'] = 'INVALID' if eligible and cnt['invalid'] / eligible > INVALID_SHARE else 'ok'
        d = [r['A']['heart'] - r['B']['heart'] for r in ok]
        plus, minus = sum(x > 0 for x in d), sum(x < 0 for x in d)
        s['heart'] = {'A': sum(r['A']['heart'] for r in ok), 'B': sum(r['B']['heart'] for r in ok),
                      'A_better': plus, 'B_better': minus, 'diff': ci_mean(d, rng),
                      'sign_p': sign_test(plus, minus)}
        pvals[pat] = s['heart']['sign_p']
        s['past_act'] = ci_mean([r['A']['past_act'] - r['B']['past_act'] for r in ok], rng)
        s['floor'] = ci_mean([r['A']['floor'] - r['B']['floor'] for r in ok], rng)
        vv = [r for r in ok if r['vA'] is not None and r['vB'] is not None]
        s['critic_next_gap'] = ci_mean([r['vA'] - r['vB'] for r in vv], rng)
        s['p_production'] = (sum(r['p_B'] for r in ok if r['p_B'] is not None) / len(ok)) if ok else None
        seeds = [r['seed'] for r in rs]
        s['repeated_seeds'] = len(seeds) - len(set(seeds))
        s['drops'] = [(r['unit'], r.get('why')) for r in rs if r['status'] in ('drop', 'invalid')]
        summary['patterns'][pat] = s
    # Holm over the four primary tests
    order = sorted(pvals, key=pvals.get)
    holm, run = {}, 0.0
    for i, pat in enumerate(order):
        run = max(run, min(1.0, (len(order) - i) * pvals[pat]))
        holm[pat] = run
    for pat in PATTERNS:
        s = summary['patterns'][pat]
        s['heart']['holm_p'] = holm[pat]
        diff = s['heart']['diff']
        if s['valid'] == 'INVALID':
            s['reading'] = 'INVALID'
        elif not diff:
            s['reading'] = 'NO_DATA'
        elif holm[pat] < 0.05:
            s['reading'] = 'ALTERNATIVE_BETTER' if diff['mean'] > 0 else 'PRODUCTION_BETTER'
        else:
            s['reading'] = 'NOT_SHOWN'
    if not partial:
        pend = sum(r['status'] == 'pending' for r in rows)
        if pend:
            raise SystemExit('%d units pending; use --partial' % pend)
    summary['rows'] = rows
    with open(out, 'w') as f:
        json.dump(summary, f, indent=1, sort_keys=True)
    for pat in PATTERNS:
        s = summary['patterns'][pat]
        h = s['heart']
        dm = h['diff']
        print('%-10s ok %3d drop %d invalid %d inel %d pending %3d | Heart A %3d B %3d | A-B %s | sign p %.3f holm %.3f | %s'
              % (pat, s['counts']['ok'], s['counts']['drop'], s['counts']['invalid'], s['counts']['ineligible'],
                 s['counts']['pending'], h['A'], h['B'],
                 ('%+.3f [%+.3f, %+.3f]' % (dm['mean'], *dm['ci95_normal'])) if dm else '-',
                 h['sign_p'], h['holm_p'], s['reading']))


if __name__ == '__main__':
    main()
