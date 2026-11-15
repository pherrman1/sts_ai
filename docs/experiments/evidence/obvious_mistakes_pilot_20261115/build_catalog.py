#!/usr/bin/env python3
"""Issue #1056 pilot: pick the top 50 flagged decisions from analyze.py's output and render the first catalogue.

    python3 -I build_catalog.py REP LAD SRC OUT_DIR NOTES_JSON

Reads OUT_DIR/candidates.json (analyze.py) and the raw pass-1/pass-2 traces again (for the root edges and the played
line of each fight), plus NOTES_JSON: {case_id: {"cat": "bug|misconception|defensible|open", "note": "..."}} written by
hand while reading the cases. Cases without a note keep the rule category below and are marked "auto".

Selection (fixed before reading the cases, so the catalogue is not cherry-picked):
  D  every fight that ended the run (14)
  R  every combat root where the played 16k tree's own max-backed Q prefers the fresh 64k pick by >= 1 (11)
  F  the 6 won fights with the highest HP-loss z against the §782 G16 norm for the encounter (z >= 2.5)
  O  the 19 out-of-combat decisions with the largest critic drop after the decision, net of the mean drop of the same
     screen transition (dv_adj), at most 2 per game
Rule categories (only where no hand note exists): D/F/R -> open; O -> misconception (actor and critic disagree).

Writes OUT_DIR/CATALOG.md and OUT_DIR/catalog.json.
"""
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as A  # noqa: E402

N_F, N_O, O_PER_GAME = 6, 19, 2
CAT_DE = {'bug': 'Bug', 'misconception': 'Fehlvorstellung', 'defensible': 'vertretbar', 'open': 'offen'}


def edge_rows(r, k=6):
    E = r['edges']
    lad = r['ladder'][0]['edge'] if r.get('ladder') else -1
    order = sorted(range(len(E)), key=lambda i: -E[i]['visits'])[:k]
    if r['gumbelChoice'] not in order:
        order.append(r['gumbelChoice'])
    if lad >= 0 and lad not in order:
        order.append(lad)
    rows = []
    for i in order:
        e = E[i]
        tag = ('gespielt' if i == r['gumbelChoice'] else '') + (' 64k' if i == lad else '')
        rows.append('| %s | %s | %d | %s | %s | %.3f |' % (
            A.action_str(e['semantic']), tag.strip(), e['visits'],
            '%.1f' % e['qBacked'] if e.get('qBacked') is not None else '-',
            '%.1f' % e['q'] if e.get('q') is not None else '-', e.get('prior') or 0))
    return ['| Aktion | | Besuche 16k | qBacked | q | Prior |', '|---|---|---|---|---|---|'] + rows


def fight_roots(g, floor, enc):
    return [r for r in g['lad'] if r['kind'] == 'root' and r['floor'] == floor and r['encounter'] == enc]


def turn_line(roots, turn):
    out = []
    for r in roots:
        if r['turn'] != turn:
            continue
        E = r['edges']
        s = A.action_str(E[r['gumbelChoice']]['semantic'])
        lad = r['ladder'][0]['edge'] if r.get('ladder') else -1
        if lad >= 0 and lad != r['gumbelChoice']:
            s += ' [64k: %s]' % A.action_str(E[lad]['semantic'])
        out.append(s)
    return '; '.join(out)


def decisive_turn(roots, died, hp_end):
    """Turn with the largest HP loss between its first root and the next turn's first root (or the fight's end)."""
    first = collections.OrderedDict()
    for r in roots:
        first.setdefault(r['turn'], r)
    turns = list(first)
    best = None
    for k, t in enumerate(turns):
        hp0 = first[t]['hp']
        hp1 = first[turns[k + 1]]['hp'] if k + 1 < len(turns) else (0 if died else hp_end)
        if best is None or hp0 - hp1 > best[1]:
            best = (t, hp0 - hp1)
    return best, first


def fight_case(g, c, kind):
    roots = fight_roots(g, c['floor'], c['encounter'])
    case = {'id': '%s-%s-F%d-%s' % (kind, c['seed'], c['floor'], c['encounter']), 'group': kind, 'seed': c['seed'],
            'act': c['act'], 'floor': c['floor'], 'what': '%s %s: HP %d -> %d' % (c['room'], c['encounter'], c['hp_pre'], c['hp_post']),
            'pots': '%s -> %s' % (c['pots_pre'], c['pots_post']), 'z': c.get('z'), 'norm': (c.get('norm_mean'), c.get('norm_sd')),
            'v': (c.get('v_before'), c.get('v_after')), 'has_lad': bool(roots)}
    if roots:
        (t, loss), first = decisive_turn(roots, c['died'], c['hp_post'])
        case['decisive_turn'] = t
        case['decisive_loss'] = loss
        case['state'] = A.wire_str(first[t]['wire'])
        case['line'] = turn_line(roots, t)
        case['edges'] = edge_rows(first[t])
        case['n_turns'] = len(first)
        case['n_64k_diff'] = sum(1 for r in roots if r.get('ladder') and r['ladder'][0]['edge'] >= 0 and r['ladder'][0]['edge'] != r['gumbelChoice'])
        case['n_roots'] = len(roots)
    return case


def root_case(g, c):
    r = [x for x in g['lad'] if x['kind'] == 'root' and x['floor'] == c['floor'] and x['decision'] == c['decision']
         and x['turn'] == c['turn'] and x['encounter'] == c['encounter']][0]
    roots = fight_roots(g, c['floor'], c['encounter'])
    return {'id': 'R-%s-F%d-T%d-d%d' % (c['seed'], c['floor'], c['turn'], c['decision']), 'group': 'R', 'seed': c['seed'],
            'act': c['act'], 'floor': c['floor'],
            'what': '%s %s T%d: gespielt %s, 64k %s (16k-qBacked %.1f vs %.1f, Lücke %.1f)' % (
                c['room'], c['encounter'], c['turn'], c['played'], c['pick64k'], c['q_played'], c['q_64k'], c['gap16k']),
            'fight': 'Kampf %s, HP-Verlust %s' % ('gewonnen' if c['fight_won'] else 'verloren', c['fight_loss']),
            'state': A.wire_str(r['wire']), 'line': turn_line(roots, c['turn']), 'edges': edge_rows(r), 'has_lad': True}


def ooc_case(c):
    opts = sorted(c['options'], key=lambda o: -o['p'])[:6]
    rows = ['| Option | | p (Netz) | Logit |', '|---|---|---|---|'] + [
        '| %s | %s | %.3f | %.2f |' % (o['option'], 'gewählt' if o['chosen'] else '', o['p'], o['logit']) for o in opts]
    delta = []
    if c['deck_added']:
        delta.append('+' + ', '.join(c['deck_added']))
    if c['deck_removed']:
        delta.append('-' + ', '.join(c['deck_removed']))
    if c['relics_added']:
        delta.append('Relikt +' + ', '.join(c['relics_added']))
    return {'id': 'O-%s-%d' % (c['seed'], c['idx']), 'group': 'O', 'seed': c['seed'], 'act': c['act'], 'floor': c['floor'],
            'what': '%s%s: Critic %.3f -> %.3f (dv %+.3f, bereinigt %+.3f; Übergang %s, Mittel %+.3f über %d)' % (
                c['screen'], ' ' + c['event'] if c['event'] else '', c['v'], c['v_next'], c['dv'], c['dv_adj'],
                c['transition'], c['transition_mean'], c['transition_n']),
            'state': c['pre'], 'delta': '; '.join(delta), 'edges': rows,
            'deck': ', '.join(c['deck_pre']), 'relics': ', '.join(c['relics_pre'])}


def main():
    rep, lad, src, out, notes_path = sys.argv[1:6]
    cands = json.load(open(os.path.join(out, 'candidates.json')))['candidates']
    notes = json.load(open(notes_path)) if os.path.exists(notes_path) else {}
    seeds = sorted({c['seed'] for k in cands for c in cands[k] if 'seed' in c})
    G = {s: A.game(rep, lad, src, s) for s in seeds}
    outcome = {s: G[s]['end']['outcome'] for s in seeds}
    cases = []
    for c in cands['fight_cost']:
        if c['died']:
            cases.append(fight_case(G[c['seed']], c, 'D'))
    for c in cands['root_64k']:
        cases.append(root_case(G[c['seed']], c))
    won = sorted([c for c in cands['fight_cost'] if not c['died'] and (c['z'] or 0) >= 2.5], key=lambda c: -c['z'])[:N_F]
    for c in won:
        cases.append(fight_case(G[c['seed']], c, 'F'))
    per = collections.Counter()
    for c in cands['ooc_drop']:
        if len([x for x in cases if x['group'] == 'O']) >= N_O:
            break
        if per[c['seed']] >= O_PER_GAME:
            continue
        per[c['seed']] += 1
        cases.append(ooc_case(c))
    for x in cases:
        n = notes.get(x['id'])
        x['cat'] = n['cat'] if n else ('misconception' if x['group'] == 'O' else 'open')
        x['note'] = n['note'] if n else ''
        x['auto'] = n is None
        o = outcome[x['seed']]
        x['game'] = 'Herz-Sieg' if o.get('heart_kill') else 'Tod F%d' % o['floor']
    json.dump(cases, open(os.path.join(out, 'catalog.json'), 'w'), indent=1)
    cnt = collections.Counter(x['cat'] for x in cases)
    L = ['# Katalog: offensichtliche Fehler, Pilot #1056 (20 G16-Spiele aus §782)', '',
         'Jeder Eintrag ist eine Hypothese, keine Wahrheit. Kategorien: Bug (Engine oder Such-Implementierung macht etwas '
         'anderes als das Spiel), Fehlvorstellung (Netz oder Suche bewertet falsch, die Regeln stimmen), vertretbar '
         '(bei genauem Hinsehen kein Fehler oder nicht entscheidbar), offen (nicht ohne gepaarte Probe entscheidbar).', '',
         '%d Einträge: %s.' % (len(cases), ', '.join('%s %d' % (CAT_DE[k], v) for k, v in cnt.most_common())), '',
         'Gruppen: D = Kampf, der den Lauf beendet hat; R = Kampfwurzel, an der der 16k-Baum selbst die 64k-Wahl höher '
         'bewertet; F = gewonnener Kampf mit hohem HP-Verlust gegen die §782-Norm; O = Entscheidung außerhalb des Kampfes, '
         'nach der der Critic fällt (bereinigt um den mittleren Sprung desselben Bildschirmwechsels).', '',
         'Werte: p und Logit sind die PPO-Policy (net-0420, Temperatur 0, also wird immer die höchste p gewählt); der '
         'Critic schätzt P(Herz-Kill). Kampfwerte stammen aus dem 16k-Baum der gespielten Suche (Besuche, max-backed Q '
         'und mittleres q in Silver-Punkten, Prior); "64k" ist die Wahl einer frischen 64k-Suche derselben Wurzel, deren '
         'Q-Werte nicht aufgezeichnet sind.', '']
    for x in cases:
        L.append('## %s · %s · %s' % (x['id'], CAT_DE[x['cat']] + (' (Regel)' if x['auto'] else ''), x['game']))
        L.append('')
        L.append('- A%d F%d: %s' % (x['act'], x['floor'], x['what']))
        for k, lab in (('fight', ''), ('pots', 'Tränke'), ('delta', 'Änderung')):
            if x.get(k):
                L.append('- %s%s' % (lab + ': ' if lab else '', x[k]))
        if x.get('z') is not None:
            L.append('- z %.2f gegen Norm %.1f ± %.1f' % (x['z'], x['norm'][0], x['norm'][1]))
        if x.get('v') and x['v'][0] is not None:
            L.append('- Critic vor/nach dem Kampf: %.3f / %.3f' % (x['v'][0], x['v'][1]))
        if x.get('decisive_turn') is not None:
            L.append('- Entscheidender Zug T%d (%d HP verloren); %d von %d Wurzeln mit anderer 64k-Wahl' % (
                x['decisive_turn'], x['decisive_loss'], x['n_64k_diff'], x['n_roots']))
        if x['group'] in ('D', 'F') and not x.get('has_lad'):
            L.append('- Pass 2 (64k) für dieses Spiel noch nicht ausgewertet')
        if x.get('state'):
            L.append('- Zustand: `%s`' % x['state'])
        if x.get('line'):
            L.append('- Gespielte Linie im Zug: %s' % x['line'])
        if x.get('relics'):
            L.append('- Relikte: %s' % x['relics'])
        if x.get('deck'):
            L.append('- Deck: %s' % x['deck'])
        if x.get('edges'):
            L.append('')
            L.extend(x['edges'])
        L.append('')
        L.append('**Einschätzung:** ' + (x['note'] or '(nur Regel, nicht von Hand gelesen)'))
        L.append('')
    open(os.path.join(out, 'CATALOG.md'), 'w').write('\n'.join(L) + '\n')
    print(len(cases), dict(cnt))


if __name__ == '__main__':
    main()
