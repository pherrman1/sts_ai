#!/usr/bin/env python3
"""Issue #1056 pilot: automatic candidates for "obvious mistakes" in 20 replayed §782 G16 games.

Read-only and offline. Inputs (from replay.sh and ladder.sh):
  REP/G16-SEED.{trace.jsonl.gz, ppo.jsonl.gz, roots.csv.gz, done}   pass 1 (binary 112c0f3a)
  LAD/natural-SEED.{jsonl.gz, done}                                  pass 2 (binary 97aec5b5, 64k ladder)
  BATTLES = ../gumbel_wholerun_trace_20261109/results/battles.csv.gz (§782 per-fight table, norms per encounter)
  SRC/G16-SEED.trace.jsonl.gz                                        §782's own trace (reproduction check)

    python3 -I analyze.py REP LAD SRC OUT_DIR

Writes OUT_DIR/candidates.json (all flags, ranked within each kind) and OUT_DIR/cases.md (the top cases rendered).

Flag kinds (thresholds are pilot choices, not tuned):
  ooc_drop    an out-of-combat decision after which the PPO critic's value falls before any fight happens
              (v[i+1] - v[i] <= -0.02): the actor chose a state its own critic values lower.
  fight_cost  a fight whose HP loss is high against §782's G16 norm for the encounter (z >= 1.5 over won fights),
              or which killed the run; with the critic's value across it.
  death_chain the 8 out-of-combat decisions before each death, ranked by the critic's drop.
  root_64k    a combat root whose 16k pick differs from a fresh 64k Gumbel + max-backup search of the same root, ranked
              by how much the played 16k tree itself prefers the 64k pick (max-backed Q gap >= GAP_MIN, both edges with
              >= MIN_VISITS visits; smaller gaps are counted as root_64k_equiv: order-equivalent or noise) and weighted up in fights that killed the run or were costly.
  cap         a fight of >= 20 turns or a combat abort.
"""
import collections
import csv
import gzip
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..', '..'))
BATTLES = os.path.join(HERE, '..', 'gumbel_wholerun_trace_20261109', 'results', 'battles.csv.gz')
MIN_VISITS = 256   # both edges, so the max-backed values are not single-line maxima
GAP_MIN = 1.0      # root_64k: the played 16k tree prefers the 64k pick by at least this (Silver score units)
SCREENS = ['INVALID', 'EVENT', 'REWARDS', 'BOSS_RELIC', 'CARD_SELECT', 'MAP', 'TREASURE', 'REST', 'SHOP', 'BATTLE']


def enum(rel, name):
    text = open(os.path.join(ROOT, rel)).read()
    m = re.search(r'enum class ' + name + r'\b[^{]*\{(.*?)\};', text, re.S)
    body = re.sub(r'//.*', '', m.group(1))
    out, v = {}, -1
    for tok in body.split(','):
        tok = tok.strip()
        if not tok:
            continue
        if '=' in tok:
            n, val = tok.split('=')
            n, v = n.strip(), int(val.strip(), 0)
        else:
            n, v = tok, v + 1
        out[v] = n
    return out


CARD = enum('include/constants/Cards.h', 'CardId')
RELIC = enum('include/constants/Relics.h', 'RelicId')
POTION = enum('include/constants/Potions.h', 'Potion')
MONSTER = enum('include/constants/MonsterIds.h', 'MonsterId')
MOVE = enum('include/constants/MonsterMoves.h', 'MonsterMoveId')
NEOW = enum('include/game/Neow.h', 'Bonus')
ROOMS = ['SHOP', 'REST', 'EVENT', 'ELITE', 'MONSTER', 'TREASURE', 'BOSS', 'BOSS_TREASURE', 'NONE', 'INVALID']
STATUS = enum('include/constants/PlayerStatusEffects.h', 'PlayerStatus')
FA = {}
for m in re.finditer(r'FA_([A-Z0-9_]+) = (\d+)', open(os.path.join(ROOT, 'apps/one_combat/heart1_policy.cpp')).read()):
    FA[int(m.group(2))] = m.group(1)


def fa_name(a):
    if 10 <= a <= 28:
        return 'NEOW_' + NEOW.get(a - 10, str(a - 10))
    if a in FA:
        return FA[a]
    base = max((k for k in FA if k <= a), default=None)
    return '%s+%d' % (FA[base], a - base) if base is not None else 'FA_%d' % a


def card_name(cid, upg=0):
    n = CARD.get(cid, str(cid))
    return n + ('+' if upg else '')


def options(rec, pre=None):
    """Labels of the PPO choice list, in the order of heart1_policy (cards, relics, potions, fixed, paths)."""
    out = []
    ups = rec.get('cards_offered.upgrades') or []
    for i, c in enumerate(rec.get('cards_offered.cards') or []):
        out.append('card ' + card_name(c, ups[i] if i < len(ups) else 0))
    for r in rec.get('relics_offered') or []:
        out.append('relic ' + RELIC.get(r, str(r)))
    for p in rec.get('potions_offered') or []:
        out.append('potion ' + POTION.get(p, str(p)))
    for fa in rec.get('fixed_actions') or []:
        s = fa_name(fa['action'])
        if fa.get('card'):
            s += ' ' + card_name(fa['card'])
        if fa.get('relic') and fa['relic'] != 180:
            s += ' ' + RELIC.get(fa['relic'], str(fa['relic']))
        if fa.get('gold'):
            s += ' %dg' % fa['gold']
        out.append(s)
    xs, ys, rt = rec.get('obs.map.xs') or [], rec.get('obs.map.ys') or [], rec.get('obs.map.roomTypes') or []
    ny = (pre['y'] + 1) if pre and pre.get('x', -1) >= 0 else 0
    for p in rec.get('paths_offered') or []:
        room = '?'
        for i in range(min(len(xs), len(ys), len(rt))):
            if xs[i] == p and ys[i] == ny:
                room = ROOMS[rt[i]] if 0 <= rt[i] < len(ROOMS) else str(rt[i])
        out.append('path x%s %s' % (p, room))
    return out


def softmax(xs):
    m = max(xs)
    e = [math.exp(x - m) for x in xs]
    s = sum(e)
    return [x / s for x in e]


def jl(path):
    op = gzip.open if path.endswith('.gz') else open
    with op(path, 'rt') as f:
        return [json.loads(l) for l in f if l.strip()]


def state_str(s):
    return 'A%d F%d %s HP %d/%d gold %d deck %d pots [%s] relics %d' % (
        s['act'], s['floor'], s['screen'], s['hp'], s['maxHp'], s['gold'], len(s['deck']),
        ','.join(s['potions']), len(s['relics']))


def wire_str(w, relics=None):
    p = w['player']
    hand = ', '.join(card_name(c['id'], c['upgraded']) + ('(%d)' % c['costForTurn'] if c['costForTurn'] >= 0 else '')
                     for c in w['hand'])
    mons = []
    for m in w['monsters'][:w.get('monsterCount', 5)]:
        if m['curHp'] <= 0 and not m.get('halfDead'):
            continue
        mv = MOVE.get(m['moveHistory'][0], str(m['moveHistory'][0])) if m.get('moveHistory') else '?'
        extra = ''.join(' %s%d' % (k, m[k]) for k in ('block', 'strength', 'vulnerable', 'weak') if m.get(k))
        mons.append('%s %d/%d [%s]%s' % (MONSTER.get(m['id'], m['id']), m['curHp'], m['maxHp'], mv, extra))
    def on(sid):  # Player::hasStatus: the map keeps stale amounts after removeStatus; the bits are the truth
        return bool(p['statusBits0'] >> sid & 1) if sid < 64 else bool(p['statusBits1'] >> (sid - 64) & 1)
    st = ' '.join('%s%d' % (STATUS.get(s, s), a) for s, a in p.get('statusMap', []) if on(s))
    pots = ','.join(POTION.get(x, str(x)) for x in w.get('potions', []) if x and POTION.get(x) != 'EMPTY_POTION_SLOT')
    draw = len(w['drawPile']['unknown']) + len(w['drawPile']['knownTop']) + len(w['drawPile']['knownBottom'])
    disc = len(w['discardPile']['unknown']) + len(w['discardPile']['knownTop']) + len(w['discardPile']['knownBottom'])
    return ('player %d/%d blk %d E %d str %d dex %d %s | pots [%s] | hand: %s | draw %d disc %d | %s' % (
        p['curHp'], p['maxHp'], p['block'], p['energy'], p['strength'], p['dexterity'], st, pots, hand, draw, disc,
        '; '.join(mons)))


SA = re.compile(r'sa/t=(\d+)/s=(\d+)/c=([-\d_]+)/o=(-?\d+)/p=(-?\d+)_(-?\d+)/x=(-?\d+)/d=(\d)/k=(\d)/task=(-?\d+)/sel=(.*)')


def action_str(sem):
    m = SA.match(sem or '')
    if not m:
        return sem
    t, s, c, o, pid, pslot, x, d, k, task, sel = m.groups()
    t = int(t)
    cid = int(c.split('_')[0])
    up = c.split('_')[5] == '1' if c.count('_') >= 5 else False
    if t == 1:
        return 'play %s%s' % (card_name(cid, up), ' -> m%s' % x if int(x) >= 0 else '')
    if t == 2:
        return '%s %s%s' % ('discard' if d == '1' else 'drink', POTION.get(int(pid), pid), ' -> m%s' % x if int(x) >= 0 else '')
    if t == 3:
        if k == '1':
            return 'select skip'
        return 'select %s' % (card_name(int(o)) if int(o) > 0 else card_name(cid, up))
    if t == 4:
        return 'select multi ' + sel
    if t == 5:
        return 'end turn'
    return sem


def norms():
    by = collections.defaultdict(list)
    deaths = collections.Counter()
    fights = collections.Counter()
    for r in csv.DictReader(gzip.open(BATTLES, 'rt')):
        if r['arm'] != 'G16':
            continue
        fights[r['encounter']] += 1
        if r['won'] == '1':
            by[r['encounter']].append(int(r['hp_pre']) - int(r['hp_post']))
        elif r['escaped'] == '0':
            deaths[r['encounter']] += 1
    out = {}
    for e, xs in by.items():
        mu = sum(xs) / len(xs)
        sd = (sum((x - mu) ** 2 for x in xs) / max(1, len(xs) - 1)) ** 0.5
        out[e] = {'n': fights[e], 'won': len(xs), 'mean': mu, 'sd': max(sd, 1.0), 'death_rate': deaths[e] / fights[e]}
    return out


def game(rep, lad, src, seed):
    trace = jl(os.path.join(rep, 'G16-%s.trace.jsonl.gz' % seed))
    orig = jl(os.path.join(src, 'G16-%s.trace.jsonl.gz' % seed))
    ppo = jl(os.path.join(rep, 'G16-%s.ppo.jsonl.gz' % seed))
    dec = {d['idx']: d for d in ppo if d['type'] == 'decision'}
    end = [d for d in ppo if d['type'] == 'game'][0]
    ladp = os.path.join(lad, 'natural-%s.jsonl.gz' % seed)
    lrows = jl(ladp) if os.path.exists(ladp) else []
    return {'seed': seed, 'trace': trace, 'repro': trace == orig, 'dec': dec, 'end': end, 'lad': lrows}


def analyse(G, N):
    cands = collections.defaultdict(list)
    TRANS = collections.defaultdict(list)
    for g in G:
        seed, trace, dec = g['seed'], g['trace'], g['dec']
        outcome = g['end']['outcome']
        # Sequence of events: ooc decisions (with value) and battles.
        seq = []
        for r in trace:
            if r['kind'] == 'ooc':
                d = dec.get(r['idx'])
                seq.append(('ooc', r, d))
            elif r['kind'] == 'battle':
                seq.append(('battle', r, None))
        values = [(i, e[2]['value']) for i, e in enumerate(seq) if e[0] == 'ooc' and e[2] is not None]
        nxt = {}
        for (i, v), (j, w) in zip(values, values[1:]):
            nxt[i] = (j, w)
        # ooc_drop
        for i, v in values:
            if i not in nxt:
                continue
            j, w = nxt[i]
            if any(seq[k][0] == 'battle' for k in range(i + 1, j)):
                continue
            d = seq[i][2]
            key = (SCREENS[d['screen']], SCREENS[seq[j][2]['screen']], seq[i][1]['pre']['act'] != seq[j][1]['pre']['act'])
            TRANS[key].append(w - v)
            if d['n'] < 2:
                continue
            if w - v <= -0.02:
                c = ooc_case(seed, seq[i][1], d, v, w, outcome)
                c['transition'] = key
                cands['ooc_drop'].append(c)
        # fight_cost / cap
        for k, e in enumerate(seq):
            if e[0] != 'battle':
                continue
            b = e[1]
            before = [v for i, v in values if i < k]
            after = [v for i, v in values if i > k]
            vb = before[-1] if before else None
            va = after[0] if after else (1.0 if outcome.get('heart_kill') else 0.0)
            loss = b['pre']['hp'] - b['post']['hp']
            n = N.get(b['encounter'])
            z = (loss - n['mean']) / n['sd'] if (n and b['won']) else None
            died = not b['won'] and not b['escaped']
            case = {'kind': 'fight_cost', 'seed': seed, 'fight': b['fight'], 'act': b['pre']['act'],
                    'floor': b['pre']['floor'], 'room': b['room'], 'encounter': b['encounter'], 'won': b['won'],
                    'turns': b['turns'], 'hp_pre': b['pre']['hp'], 'hp_post': b['post']['hp'], 'loss': loss,
                    'norm_mean': n and round(n['mean'], 2), 'norm_sd': n and round(n['sd'], 2),
                    'norm_death_rate': n and round(n['death_rate'], 4), 'z': z and round(z, 2), 'died': died,
                    'v_before': vb, 'v_after': va, 'dv': (va - vb) if vb is not None else None,
                    'pots_pre': b['pre']['potions'], 'pots_post': b['post']['potions'],
                    'deck': len(b['pre']['deck']), 'relics': b['pre']['relics']}
            if died or (z is not None and z >= 1.5):
                cands['fight_cost'].append(case)
            if b['turns'] >= 20:
                cands['cap'].append(dict(case, kind='cap'))
        # death chain
        if not outcome.get('heart_kill') and outcome.get('hp', 1) <= 0:
            oo = [(i, v) for i, v in values]
            last = oo[-8:]
            for (i, v) in last:
                d = seq[i][2]
                w = nxt.get(i, (None, 0.0))[1]
                if d['n'] >= 2:
                    c = ooc_case(seed, seq[i][1], d, v, w, outcome)
                    c['kind'] = 'death_chain'
                    cands['death_chain'].append(c)
        # root_64k
        fights = {r['fight']: r for r in g['lad'] if r['kind'] == 'fight'}
        flagged = {(c['seed'], c['floor']) for c in cands['fight_cost']}
        for r in g['lad']:
            if r['kind'] != 'root' or not r.get('ladder'):
                continue
            L = r['ladder'][0]
            played = r['gumbelChoice']
            if L['edge'] < 0 or L['edge'] == played:
                continue
            E = r['edges']
            pe, le = E[played], E[L['edge']]
            gap = None
            if pe['visits'] >= MIN_VISITS and le['visits'] >= MIN_VISITS and pe.get('qBacked') is not None and le.get('qBacked') is not None:
                gap = le['qBacked'] - pe['qBacked']
            if gap is None or gap < GAP_MIN:
                cands['root_64k_equiv'].append({'seed': seed, 'floor': r['floor'], 'gap16k': gap})
                continue
            f = fights.get(r['fight'], {})
            died = f.get('won') is False
            key = (seed, r['floor'])
            weight = 2.0 if died else (1.5 if key in flagged else 1.0)
            cands['root_64k'].append({
                'kind': 'root_64k', 'seed': seed, 'fight': r['fight'], 'act': r['act'], 'floor': r['floor'],
                'room': r['room'], 'encounter': r['encounter'], 'turn': r['turn'], 'decision': r['decision'],
                'fight_won': f.get('won'), 'fight_loss': (f.get('preHp', 0) - f.get('endHp', 0)) if f else None,
                'played': action_str(pe['semantic']), 'pick64k': action_str(le['semantic']),
                'q_played': pe.get('qBacked'), 'q_64k': le.get('qBacked'), 'v_played': pe['visits'],
                'v_64k': le['visits'], 'prior_played': pe.get('prior'), 'prior_64k': le.get('prior'),
                'gap16k': gap, 'weight': weight, 'score': (gap or 0) * weight,
                'state': wire_str(r['wire']),
                'edges': sorted([{'a': action_str(x['semantic']), 'visits': x['visits'],
                                  'qBacked': x.get('qBacked') and round(x['qBacked'], 2), 'q': x.get('q') and round(x['q'], 2),
                                  'prior': x.get('prior') and round(x['prior'], 3)} for x in E],
                                key=lambda x: -x['visits'])[:8]})
    # The critic is not screen-invariant (same state, different screen, different value): rank drops by dv minus the
    # mean dv of the same screen transition over all 20 games, so a drop that every REST -> CARD_SELECT shows is not
    # read as a choice the critic dislikes.
    tmean = {k: sum(v) / len(v) for k, v in TRANS.items()}
    for c in cands['ooc_drop']:
        k = c['transition']
        c['transition'] = '%s->%s%s' % (k[0], k[1], ' (act change)' if k[2] else '')
        c['transition_mean'] = round(tmean[k], 4)
        c['transition_n'] = len(TRANS[k])
        c['dv_adj'] = round(c['dv'] - tmean[k], 4)
    cands['ooc_drop'].sort(key=lambda c: c['dv_adj'])
    cands['death_chain'].sort(key=lambda c: (c['seed'], c['idx']))
    cands['fight_cost'].sort(key=lambda c: (not c['died'], -(c['z'] or 0)))
    cands['root_64k'].sort(key=lambda c: -c['score'])
    cands['cap'].sort(key=lambda c: -c['turns'])
    return cands


def ooc_case(seed, r, d, v, w, outcome):
    labels = options(d['record'], r['pre'])
    p = softmax(d['logits'])
    opts = []
    for k, lg in enumerate(d['logits']):
        opts.append({'option': labels[k] if k < len(labels) else '#%d' % k, 'logit': round(lg, 3), 'p': round(p[k], 4),
                     'chosen': k == d['chosen']})
    return {'kind': 'ooc_drop', 'seed': seed, 'idx': r['idx'], 'act': r['pre']['act'], 'floor': r['pre']['floor'],
            'screen': SCREENS[d['screen']], 'event': r['pre']['event'], 'v': round(v, 4), 'v_next': round(w, 4),
            'dv': round(w - v, 4), 'pre': state_str(r['pre']), 'post': state_str(r['post']),
            'offer': r['offer'], 'deck_pre': r['pre']['deck'], 'relics_pre': r['pre']['relics'],
            'deck_added': sorted((collections.Counter(r['post']['deck']) - collections.Counter(r['pre']['deck'])).elements()),
            'deck_removed': sorted((collections.Counter(r['pre']['deck']) - collections.Counter(r['post']['deck'])).elements()),
            'relics_added': [x for x in r['post']['relics'] if x not in r['pre']['relics']],
            'options': opts, 'game_heart_kill': outcome.get('heart_kill'), 'game_floor': outcome.get('floor')}


def sheet(g):
    """The whole game in order: each out-of-combat decision (options, p, critic value) and each fight (its played
    line from pass 2, with the 64k pick where it differs and the 16k tree's max-backed Q of both)."""
    L = []
    roots = collections.defaultdict(list)
    for r in g['lad']:
        if r['kind'] == 'root':
            roots[r['floor']].append(r)
    end = g['end']['outcome']
    L.append('# %s: %s, floor %d, HP %d' % (g['seed'], 'HEART KILL' if end.get('heart_kill') else 'death', end['floor'], end['hp']))
    for r in g['trace']:
        if r['kind'] == 'ooc':
            d = g['dec'].get(r['idx'])
            if d is None or d['n'] < 2:
                continue
            labels = options(d['record'], r['pre'])
            p = softmax(d['logits'])
            opts = '; '.join('%s%s %.2f' % ('**' if k == d['chosen'] else '', labels[k] if k < len(labels) else '#%d' % k, p[k])
                             for k in sorted(range(len(p)), key=lambda k: -p[k])[:6])
            add = sorted((collections.Counter(r['post']['deck']) - collections.Counter(r['pre']['deck'])).elements())
            rem = sorted((collections.Counter(r['pre']['deck']) - collections.Counter(r['post']['deck'])).elements())
            rel = [x for x in r['post']['relics'] if x not in r['pre']['relics']]
            delta = ''.join([' +' + ','.join(add) if add else '', ' -' + ','.join(rem) if rem else '', ' relic+' + ','.join(rel) if rel else ''])
            L.append('- [%d] F%d %s%s v=%.3f HP %d/%d g%d | %s |%s' % (r['idx'], r['pre']['floor'], SCREENS[d['screen']],
                     ' ' + r['pre']['event'] if r['pre']['event'] else '', d['value'], r['pre']['hp'], r['pre']['maxHp'],
                     r['pre']['gold'], opts, delta))
        else:
            b = r
            L.append('- FIGHT F%d %s %s: HP %d -> %d, %d turns, pots %s -> %s, deck %d, relics %s' % (
                b['pre']['floor'], b['room'], b['encounter'], b['pre']['hp'], b['post']['hp'], b['turns'],
                b['pre']['potions'], b['post']['potions'], len(b['pre']['deck']), ','.join(b['pre']['relics'])))
            if b['room'] == 'BOSS' or not b['won'] or b['pre']['hp'] - b['post']['hp'] >= 15:
                L.append('  - deck: ' + ', '.join(b['pre']['deck']))
            for rr in roots.get(b['pre']['floor'], []):
                E = rr['edges']
                pc = E[rr['gumbelChoice']]
                lad = rr['ladder'][0]['edge'] if rr.get('ladder') else None
                line = '  - T%d %s' % (rr['turn'], action_str(pc['semantic']))
                if lad is not None and lad >= 0 and lad != rr['gumbelChoice']:
                    le = E[lad]
                    line += '   [64k picks %s; 16k tree qB 64k-pick %.1f vs played %.1f, visits %d vs %d]' % (action_str(le['semantic']), le['qBacked'] or 0, pc['qBacked'] or 0, le['visits'], pc['visits'])
                if rr['decision'] == 1 or (rr is roots[b['pre']['floor']][0]) or 'end turn' in L[-1]:
                    L.append('    ' + wire_str(rr['wire']))
                L.append(line)
    return '\n'.join(L) + '\n'


def main():
    rep, lad, src, out = sys.argv[1:5]
    os.makedirs(out, exist_ok=True)
    seeds = sorted(f.split('-')[1].split('.')[0] for f in os.listdir(rep) if f.endswith('.done'))
    G = [game(rep, lad, src, s) for s in seeds]
    N = norms()
    cands = analyse(G, N)
    summary = {'games': len(G), 'repro_trace_identical': sum(g['repro'] for g in G),
               'non_repro': [g['seed'] for g in G if not g['repro']],
               'ladder_games': sum(1 for g in G if g['lad']),
               'roots_with_ladder': sum(1 for g in G for r in g['lad'] if r['kind'] == 'root' and r.get('ladder')),
               'roots_64k_differs': len(cands['root_64k']) + len(cands['root_64k_equiv']),
               'roots_64k_gap_ge_min': len(cands['root_64k']),
               'counts': {k: len(v) for k, v in cands.items()}}
    json.dump({'summary': summary, 'candidates': cands}, open(os.path.join(out, 'candidates.json'), 'w'), indent=1)
    os.makedirs(os.path.join(out, 'sheets'), exist_ok=True)
    for g in G:
        open(os.path.join(out, 'sheets', '%s.md' % g['seed']), 'w').write(sheet(g))
    print(json.dumps(summary, indent=1))


if __name__ == '__main__':
    main()
