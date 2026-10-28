"""Rebuild heart1/student_sel records at expert decisions from StS run-history files.

usage: reconstruct.py IDMAPS.json MAPS.jsonl OUT.jsonl RAW_RUN.json...

Writes one JSON line per decision: {"run", "floor", "type", "record", "expert": index into the record's
logit order (cards, relics, potions, fixed, paths), "labels": names in that order, "flags": [...]}.
Deck/relic/potion state is replayed from the run log; HP, max HP and gold come from the per-floor arrays.
"""
import collections, json, sys

IDS = json.load(open(sys.argv[1]))
CARD, RELIC, POTION = IDS["cards"], IDS["relics"], IDS["potions"]
MAPS = {}
for line in open(sys.argv[2]):
    m = json.loads(line); MAPS[(m["seed"], m["act"])] = m

SCREEN = {"event": 1, "rewards": 2, "boss_relic": 3, "card_select": 4, "map": 5, "rest": 7, "shop": 8}
SEL_UPGRADE, SEL_REMOVE = 3, 4
FA = {"SKIP": 1, "SINGING_BOWL": 3, "REST": 4, "SMITH": 5, "RECALL": 6, "LIFT": 7, "PURGE": 8, "DIG": 9}
ROOM = {"$": 0, "R": 1, "?": 2, "E": 3, "M": 4, "T": 5}
BOSS = {"Slime Boss": 0, "Hexaghost": 1, "The Guardian": 2, "Champ": 3, "The Champ": 3, "Automaton": 4,
        "Bronze Automaton": 4, "Collector": 5, "The Collector": 5, "Time Eater": 6, "Donu and Deca": 7,
        "Awakened One": 8, "The Heart": 9, "Corrupt Heart": 9}
ACT_BOSSES = {1: (0, 1, 2), 2: (3, 4, 5), 3: (6, 7, 8), 4: (9,)}
CURSES = {"AscendersBane", "Clumsy", "CurseOfTheBell", "Decay", "Doubt", "Injury", "Necronomicurse",
          "Normality", "Pain", "Parasite", "Pride", "Regret", "Shame", "Writhe"}
UNREMOVABLE = {"AscendersBane", "CurseOfTheBell", "Necronomicurse"}
STARTER = ["Strike_R"] * 5 + ["Defend_R"] * 4 + ["Bash", "AscendersBane"]


def parse_card(s):
    """'Inflame+1' -> ('Inflame', 1)."""
    if "+" in s:
        base, up = s.rsplit("+", 1)
        if up.isdigit(): return base, int(up)
    return s, 0


def act_of(floor):
    return 1 if floor <= 17 else 2 if floor <= 34 else 3 if floor <= 51 else 4


class Deck:
    def __init__(self): self.cards = [[c, 0] for c in STARTER]; self.misses = 0

    def add(self, s):
        b, u = parse_card(s)
        if b not in CARD: self.misses += 1; return
        self.cards.append([b, u])

    def remove(self, s):
        b, u = parse_card(s)
        for want_u in (u, None):
            for i, c in enumerate(self.cards):
                if c[0] == b and (want_u is None or c[1] == want_u):
                    del self.cards[i]; return True
        self.misses += 1; return False

    def upgrade(self, s):
        b, u = parse_card(s)
        cands = [c for c in self.cards if c[0] == b]
        for c in sorted(cands, key=lambda c: c[1]):
            if c[1] == 0 or b == "Searing Blow": c[1] += 1; return True
        self.misses += 1; return False

    def multiset(self, with_up=True):
        return collections.Counter((c[0], c[1] if with_up else 0) for c in self.cards)


def upgradeable(c): return c[0] not in CURSES and (c[1] == 0 or c[0] == "Searing Blow")


def map_paths(seed, act, rooms):
    """All x-sequences through act's map whose room symbols match rooms (y = 0..len-1)."""
    m = MAPS[(seed, act)]
    node = {(n[0], n[1]): n for n in m["nodes"]}
    out = []

    def rec(y, x, acc):
        if y == len(rooms): out.append(list(acc)); return
        n = node.get((x, y))
        if n is None or (rooms[y] != "?" and ROOM.get(rooms[y], -9) != n[2] and not (rooms[y] == "E" and n[2] == 3)):
            return
        if rooms[y] == "?" and n[2] != 2: return
        acc.append(x)
        if y + 1 == len(rooms): out.append(list(acc))
        else:
            for e in n[3]: rec(y + 1, e, acc)
        acc.pop()
        if len(out) > 64: return
    for x in range(7):
        if (x, 0) in node: rec(0, x, [])
    return out, m


def map_record_fields(m, mx, my):
    nodes = sorted(m["nodes"], key=lambda n: (n[1], n[0]))
    xs = [n[0] for n in nodes]; ys = [n[1] for n in nodes]; rooms = [n[2] for n in nodes]; pxs = []
    for n in nodes:
        p = [-1, -1, -1]
        for e in n[3]:
            if n[1] == 14: p[1] = e
            elif e == n[0] - 1: p[0] = e
            elif e == n[0]: p[1] = e
            elif e == n[0] + 1: p[2] = e
        pxs.append(p)
    if any(y == 14 for y in ys):
        xs.append(3); ys.append(15); rooms.append(6); pxs.append([-1, -1, -1])
    return {"obs.map.xs": xs, "obs.map.ys": ys, "obs.map.roomTypes": rooms, "obs.map.pathXs": pxs,
            "obs.map.burningEliteX": m["bx"], "obs.map.burningEliteY": m["by"], "obs.mapX": mx, "obs.mapY": my}


def process(path, out, stats, out_meta, fixes=None):
    d = json.load(open(path))
    if d.get("character_chosen") != "IRONCLAD" or d.get("ascension_level") != 20: stats["skip_not_a20_ic"] += 1; return
    mods = [x.get("id") if isinstance(x, dict) else str(x) for x in (d.get("activemods:active_mods") or [])]
    if "RanwidPlus" in mods: stats["skip_mod"] += 1; return
    run = path.rsplit("/", 1)[-1][:-5]
    seed = d["seed_played"]
    nfl = d["floor_reached"]
    hp, mhp, gold = d["current_hp_per_floor"], d["max_hp_per_floor"], d["gold_per_floor"]
    ppf = d["path_per_floor"]

    # --- timeline of deck/relic/potion events keyed by floor; order within a floor = insertion order.
    ev = collections.defaultdict(list)  # floor -> [(kind, arg)]
    nl = d.get("neow_bonus_log") or {}
    for c in nl.get("cardsRemoved", []): ev[0].append(("rm", c))
    for c in nl.get("cardsTransformed", []): ev[0].append(("rm", c))
    for c in nl.get("cardsObtained", []): ev[0].append(("add", c))
    for c in nl.get("cardsUpgraded", []): ev[0].append(("up", c))
    neow_relics = nl.get("relicsObtained", [])
    if d.get("neow_bonus") == "BOSS_RELIC": ev[0].append(("rlost", "Burning Blood"))
    for r in neow_relics: ev[0].append(("relic", r))
    for c in d["card_choices"]:
        f = int(c["floor"])
        if f == 0 and nl: continue  # Neow card picks are in the Neow log
        if c["picked"] not in ("SKIP", "Singing Bowl"): ev[f].append(("add", c["picked"]))
    for c in d.get("campfire_choices", []):
        f = int(c["floor"])
        if c["key"] == "SMITH": ev[f].append(("up", c["data"]))
        elif c["key"] == "PURGE": ev[f].append(("rm", c["data"]))
        elif c["key"] == "RECALL": ev[f].append(("key", "red"))
        elif c["key"] == "LIFT": ev[f].append(("girya", 1))
    floors = d.get("item_purchase_floors", [])
    for i, it in enumerate(d.get("items_purchased", [])):
        f = int(floors[i]) if i < len(floors) else 0
        if parse_card(it)[0] in CARD: ev[f].append(("add", it))
        elif it in RELIC: ev[f].append(("relic", it))
        elif it in POTION: ev[f].append(("pot", it))
    pf = d.get("items_purged_floors", [])
    for i, it in enumerate(d.get("items_purged", [])):
        ev[int(pf[i]) if i < len(pf) else 0].append(("rm", it))
    for e in d.get("event_choices", []):
        f = int(e["floor"])
        for c in e.get("cards_removed", []): ev[f].append(("rm", c))
        for c in e.get("cards_transformed", []): ev[f].append(("rm", c))
        for c in e.get("cards_obtained", []): ev[f].append(("add", c))
        for c in e.get("cards_upgraded", []): ev[f].append(("up", c))
        for r in e.get("relics_lost", []): ev[f].append(("rlost", r))
        for r in e.get("relics_obtained", []): ev[f].append(("relic", r))
        for p in e.get("potions_obtained", []): ev[f].append(("pot", p))
    for r in d.get("relics_obtained", []): ev[int(r["floor"])].append(("relic", r["key"]))
    boss_floor = {0: 17, 1: 34, 2: 51}
    for i, b in enumerate(d.get("boss_relics", [])):
        if b.get("picked") and b["picked"] != "SKIP": ev[boss_floor.get(i, 51)].append(("relic", b["picked"]))
    for p in d.get("potions_obtained", []): ev[int(p["floor"])].append(("pot", p["key"]))
    puse = d.get("potion_use_per_floor") or []; pdis = d.get("potion_discard_per_floor") or []
    if d.get("green_key_taken_log"): ev[int(d["green_key_taken_log"])].append(("key", "green"))
    bk = d.get("blue_key_relic_skipped_log")
    if bk: ev[int(bk["floor"])].append(("key", "blue"))

    for f, items in (fixes or {}).items(): ev[f].extend(items)
    # Relics in the final list that no log entry explains: acquired after the previous logged relic.
    logged = {}
    for f in sorted(ev):
        for k, a in ev[f]:
            if k == "relic": logged.setdefault(a, f)
    last = 0
    final_relics = d.get("relics", [])
    if d.get("neow_bonus") == "BOSS_RELIC" and "Burning Blood" not in final_relics and final_relics:
        logged.setdefault(final_relics[0], 0); ev[0].append(("relic", final_relics[0]))
    for r in final_relics:
        if r == "Burning Blood": continue
        if r in logged: last = max(last, logged[r])
        else: ev[last].append(("relic", r)); stats["relic_unlogged"] += 1

    # Act bosses seen in fights.
    bosses = {}
    for x in d.get("damage_taken", []):
        if x["enemies"] in BOSS: bosses[act_of(int(x["floor"]))] = BOSS[x["enemies"]]
    bosses[4] = 9

    # Map path per act (path_taken: map nodes + BOSS markers).
    act_rooms, cur = {1: []}, 1
    for r in d.get("path_taken", []):
        if r == "BOSS": cur += 1; act_rooms[cur] = []
        else: act_rooms.setdefault(cur, []).append(r)
    act_paths = {}
    for a in (1, 2, 3):
        rooms = act_rooms.get(a, [])
        if not rooms or (seed, a) not in MAPS: continue
        paths, m = map_paths(seed, a, rooms)
        act_paths[a] = (paths, m, rooms)
        stats["map_unique" if len(paths) == 1 else "map_none" if not paths else "map_ambiguous"] += 1

    # --- state replay
    deck = Deck(); relics = ["Burning Blood"]; potions = []; keys = set(); girya = 0
    state_at = {}

    def apply(f):
        nonlocal girya
        for i, (k, a) in enumerate(ev.get(f, [])):
            if k == "add": deck.add(a)
            elif k == "rm": deck.remove(a)
            elif k == "up": deck.upgrade(a)
            elif k == "relic" and a not in relics:
                relics.append(a)
                if a == "Calling Bell": deck.add("CurseOfTheBell")
                if a == "Necronomicon": deck.add("Necronomicurse")
            elif k == "rlost" and a in relics: relics.remove(a)
            elif k == "pot": potions.append(a)
            elif k == "key": keys.add(a)
            elif k == "girya": girya += 1
        if f - 1 < len(puse) and f >= 1:
            for p in (puse[f - 1] or []) + (pdis[f - 1] if f - 1 < len(pdis) and pdis[f - 1] else []):
                if p in potions: potions.remove(p)

    def obs(f, before=False):
        """State at floor f. before=True: before floor f's own events (rest/shop decisions)."""
        i = f - 2 if before else f - 1
        i = max(0, min(i, len(hp) - 1))
        a = act_of(f)
        cap = 2 + (2 if "Potion Belt" in relics else 0)
        pots = [POTION.get(p, 1) for p in potions[-cap:]] + [1] * max(0, cap - len(potions))
        bs = bosses.get(a)
        rel_ids = [RELIC[r] for r in relics if r in RELIC]
        counters = [girya if r == "Girya" else 0 for r in relics if r in RELIC]
        return {
            "fixed": [min(hp[i], 200), min(mhp[i], 200), min(gold[i], 1800), f, bs, 0, 20,
                      int("red" in keys), int("green" in keys), int("blue" in keys)],
            "obs.deck.cards": [CARD[c[0]] for c in deck.cards], "obs.deck.upgrades": [c[1] for c in deck.cards],
            "obs.deck.misc": [0] * len(deck.cards), "obs.act": a,
            "obs.relics.relics": rel_ids, "obs.relics.relic_counters": counters, "obs.potions": pots,
            "_boss_known": bs is not None, "_act": a,
        }

    def mapfields(f, after_room=True):
        a = act_of(f)
        if a not in act_paths or a == 4: return None, ["no_map"]
        paths, m, rooms = act_paths[a]
        y = f - (a - 1) * 17 - 1
        if not paths: return map_record_fields(m, -1, -1), ["map_unmatched"]
        xs = {p[y] for p in paths} if 0 <= y < len(paths[0]) else {-1}
        x = sorted(xs)[0]
        if not (0 <= y <= 14): return map_record_fields(m, -1, -1 if y < 0 else 15 if False else y), []
        return map_record_fields(m, x, y), ([] if len(xs) == 1 else ["map_x_ambiguous"])

    def emit(f, typ, base, cards=(), cup=(), rel=(), fixed=(), paths=(), screen=2, sel=0, expert=None, labels=(),
             flags=(), mf=None):
        mfields, mflags = mf if mf is not None else mapfields(f)
        if mfields is None:
            mfields = {"obs.map.xs": [], "obs.map.ys": [], "obs.map.roomTypes": [], "obs.map.pathXs": [],
                       "obs.map.burningEliteX": -1, "obs.map.burningEliteY": -1, "obs.mapX": -1, "obs.mapY": -1}
        fixed_obs = list(base["fixed"])
        if sel: fixed_obs[5] = 1
        bosses_try = [fixed_obs[4]] if base["_boss_known"] else list(ACT_BOSSES[base["_act"]])
        for b in bosses_try:
            fo = list(fixed_obs); fo[4] = b
            rec = {"obs.fixed_observation": fo, **{k: v for k, v in base.items() if k.startswith("obs.")}, **mfields,
                   "cards_offered.cards": list(cards), "cards_offered.upgrades": list(cup),
                   "relics_offered": list(rel), "potions_offered": [],
                   "fixed_actions": [{"action": a, "gold": 0, "card": 0, "relic": 180, "info": 0} for a in fixed],
                   "paths_offered": list(paths), "screen_state": screen, "select_screen_type": sel}
            if out is not None: out.write(json.dumps({"run": run, "floor": f, "type": typ, "expert": expert, "labels": list(labels),
                                  "boss_marginal": len(bosses_try), "flags": list(flags) + mflags,
                                  "victory": bool(d.get("victory")), "build": d.get("build_version"),
                                  "record": rec}) + "\n")
        stats["dec_" + typ] += 1

    apply(0)
    cc_by_floor = collections.defaultdict(list)
    for c in d["card_choices"]: cc_by_floor[int(c["floor"])].append(c)
    camp_by_floor = {int(c["floor"]): c for c in d.get("campfire_choices", [])}
    purge_by_floor = collections.defaultdict(list)
    for i, it in enumerate(d.get("items_purged", [])):
        if i < len(pf): purge_by_floor[int(pf[i])].append(it)

    for f in range(1, nfl + 1):
        room = ppf[f - 1] if f - 1 < len(ppf) else None
        # Rest site decision happens before the floor's own events.
        if room == "R" and f < nfl:
            base = obs(f, before=True)
            opts = []
            if "Coffee Dripper" not in relics: opts.append("REST")
            if "Fusion Hammer" not in relics and any(upgradeable(c) for c in deck.cards): opts.append("SMITH")
            if "red" not in keys: opts.append("RECALL")
            if "Girya" in relics and girya < 3: opts.append("LIFT")
            if "Peace Pipe" in relics: opts.append("PURGE")
            if "Shovel" in relics: opts.append("DIG")
            ch = camp_by_floor.get(f)
            choice = ch["key"] if ch else "SKIP"
            if not opts: opts = ["SKIP"]
            if choice in opts and len(opts) > 1:
                emit(f, "rest", base, fixed=[FA[o] for o in opts], screen=SCREEN["rest"],
                     expert=opts.index(choice), labels=opts, mf=mapfields(f))
            elif choice not in opts: stats["rest_choice_unavailable"] += 1
            if ch and ch["key"] == "SMITH":
                up = [c for c in deck.cards if upgradeable(c)]
                b, _ = parse_card(ch["data"])
                idx = next((i for i, c in enumerate(up) if c[0] == b), None)
                if idx is not None and len({c[0] for c in up}) > 1:
                    emit(f, "smith", base, cards=[CARD[c[0]] for c in up], cup=[c[1] for c in up],
                         screen=SCREEN["card_select"], sel=SEL_UPGRADE, expert=idx,
                         labels=[c[0] + ("+%d" % c[1] if c[1] else "") for c in up], mf=mapfields(f))
        if room == "$" and purge_by_floor.get(f):
            base = obs(f, before=True)
            rem = [c for c in deck.cards if c[0] not in UNREMOVABLE]
            b, u = parse_card(purge_by_floor[f][0])
            idx = next((i for i, c in enumerate(rem) if c[0] == b and c[1] == u), None)
            if idx is None: idx = next((i for i, c in enumerate(rem) if c[0] == b), None)
            if idx is not None:
                emit(f, "shop_remove", base, cards=[CARD[c[0]] for c in rem], cup=[c[1] for c in rem],
                     screen=SCREEN["card_select"], sel=SEL_REMOVE, expert=idx,
                     labels=[c[0] + ("+%d" % c[1] if c[1] else "") for c in rem], mf=mapfields(f))
        # Card rewards: state after the floor's fight, before the picks of this floor.
        if cc_by_floor.get(f):
            pre_events = ev.get(f, [])
            # apply non-card-pick events first (relics from combat, potions), then each pick in order
            picks = [c for c in cc_by_floor[f]]
            pending = list(pre_events)
            ev[f] = [e for e in pending if not (e[0] == "add" and any(e[1] == c["picked"] for c in picks))]
            apply(f)
            ev[f] = pending
            for c in picks:
                base = obs(f)
                offered = ([c["picked"]] if c["picked"] not in ("SKIP", "Singing Bowl") else []) + list(c["not_picked"])
                offered = sorted(offered, key=lambda s: s)  # unknown screen order; sorted for stability
                pc = [parse_card(s) for s in offered]
                if any(b not in CARD for b, _ in pc): stats["cc_unknown_card"] += 1; continue
                fixed = (["SINGING_BOWL"] if "Singing Bowl" in relics else []) + ["SKIP"]
                labels = offered + fixed
                if c["picked"] == "SKIP": expert = len(offered) + fixed.index("SKIP")
                elif c["picked"] == "Singing Bowl": expert = len(offered)
                else: expert = offered.index(c["picked"])
                kind = {"M": "card_reward_monster", "E": "card_reward_elite", "B": "card_reward_boss"}.get(room, "card_choice_other")
                emit(f, kind, base, cards=[CARD[b] for b, _ in pc], cup=[u for _, u in pc],
                     fixed=[FA[x] for x in fixed], screen=SCREEN["rewards"], expert=expert, labels=labels)
                if c["picked"] not in ("SKIP", "Singing Bowl"): deck.add(c["picked"])
        else:
            apply(f)
        # Boss relic choice.
        bi = {17: 0, 34: 1, 51: 2}.get(f)
        brs = d.get("boss_relics", [])
        if bi is not None and bi < len(brs):
            b = brs[bi]
            picked = b.get("picked", "SKIP")
            offered = ([picked] if picked != "SKIP" else []) + list(b.get("not_picked", []))
            if all(r in RELIC for r in offered) and len(offered) == 3:
                base = obs(f - 1)  # state after the boss, before the pick
                if picked in relics:
                    base["obs.relics.relics"] = [RELIC[r] for r in relics if r in RELIC and r != picked]
                    base["obs.relics.relic_counters"] = [0] * len(base["obs.relics.relics"])
                offered = sorted(offered)
                labels = offered + ["SKIP"]
                emit(f, "boss_relic", base, rel=[RELIC[r] for r in offered], fixed=[FA["SKIP"]],
                     screen=SCREEN["boss_relic"], expert=labels.index(picked), labels=labels,
                     mf=(None, ["no_map"]))
        # Map move from this floor's node to the next (acts 1-3, y 0..13), and the act's first move.
        a = act_of(f)
        if a in act_paths and act_paths[a][0]:
            paths, m, rooms = act_paths[a]
            y = f - (a - 1) * 17 - 1
            node = {(n[0], n[1]): n for n in m["nodes"]}
            def map_dec(fl, y0, x0, nxt_xs, chosen_xs, base):
                opts = sorted(nxt_xs)
                if len(opts) < 2: return
                if len(chosen_xs) != 1: stats["map_dec_ambiguous"] += 1; return
                mf = map_record_fields(m, x0, y0)
                emit(fl, "map", base, paths=opts, screen=SCREEN["map"], expert=opts.index(next(iter(chosen_xs))),
                     labels=["x%d:%s" % (x, "$R?EMT"[[0, 1, 2, 3, 4, 5].index(node[(x, y0 + 1)][2])] if node[(x, y0 + 1)][2] <= 5 else "?") for x in opts],
                     mf=(mf, []))
            if y == 0 or (a > 1 and f == (a - 1) * 17 + 1):
                pass
            # first move of the act: from y=-1
            if f == (a - 1) * 17 + 1 and len({p[0] for p in paths}) == 1:
                base = obs(max(f - 1, 1)) if a > 1 else obs(1, before=True)
                starts = sorted(x for (x, yy) in node if yy == 0)
                map_dec(f, -1, -1, starts, {paths[0][0]}, base)
            if 0 <= y < 14 and y + 1 < len(rooms) and f < nfl:
                cur = {p[y] for p in paths}
                if len(cur) == 1:
                    x0 = next(iter(cur))
                    nxt = set(node[(x0, y)][3])
                    chosen = {p[y + 1] for p in paths if p[y] == x0}
                    map_dec(f, y, x0, nxt, chosen, obs(f))
    final = collections.Counter((parse_card(c)[0]) for c in d.get("master_deck", []))
    recon = collections.Counter(c[0] for c in deck.cards)
    diff = sum(((final - recon) + (recon - final)).values())
    if out_meta is None: return final - recon, recon - final, d
    stats["runs"] += 1
    stats["deck_exact"] += diff == 0
    stats["deck_diff_le2"] += diff <= 2
    stats["deck_diff_sum"] += diff
    out_meta.write(json.dumps({"run": run, "victory": bool(d.get("victory")), "floor_reached": nfl,
                               "deck_diff": diff, "missing": dict(final - recon), "extra": dict(recon - final),
                               "build": d.get("build_version")}) + "\n")


TRANSFORMERS = ("Pandora's Box", "Astrolabe", "Empty Cage")


def corrections(d, missing, extra):
    """Place unexplained deck differences (mostly unlogged transforms/removals) at their likely floor."""
    floor = None
    rel = d.get("relics", [])
    if d.get("neow_bonus") == "BOSS_RELIC" and rel and rel[0] in TRANSFORMERS: floor = 0
    for i, b in enumerate(d.get("boss_relics", [])):
        if floor is not None: break
        if b.get("picked") in TRANSFORMERS: floor = {0: 17, 1: 34, 2: 51}.get(i); break
    nb = d.get("neow_bonus", "")
    if floor is None and ("TRANSFORM" in nb or "REMOVE" in nb): floor = 0
    if floor is None: return {}
    fx = []
    for c, n in extra.items():
        if c in CURSES: continue
        fx += [("rm", c)] * n
    for c, n in missing.items():
        if c in ("CurseOfTheBell", "Necronomicurse"): continue
        fx += [("add", c)] * n
    return {floor: fx}


if __name__ == "__main__":
    stats = collections.Counter()
    with open(sys.argv[3], "w") as out, open(sys.argv[3] + ".meta.jsonl", "w") as out_meta:
        for p in sys.argv[4:]:
            try:
                r = process(p, None, collections.Counter(), None)
                if r is None: stats["skip"] += 1; continue
                missing, extra, d = r
                process(p, out, stats, out_meta, corrections(d, missing, extra))
            except Exception as e:
                stats["error"] += 1; print("ERR", p, repr(e), file=sys.stderr)
    print(json.dumps(stats, indent=1))
