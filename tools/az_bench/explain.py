#!/usr/bin/env python3
"""Decision explainability for AmberNet out of combat (2026-11-21): what does the net's choice at a position owe to
single things the player owns? No LLM, no simulator, CPU only: the script reads positions from a replay window saved
by selfplay.py (--replay-save, without --compact-samples), edits their tokens and runs the net.

Every out-of-combat decision is covered: card rewards, shop, map, campfire, events, Neow, boss relics, chests, card
select screens (upgrade / remove / transform / ...), reward relics / potions / gold / keys, out-of-combat potions.

Per position s, action a, reference action b and owned item k (s \\ k = s without k):

    logit contrast   C(a, b; s)  = z_a(s) - z_b(s)                 (z = policy logits; b = Skip where it exists,
                                                                     else the best other action)
    item effect      dC_k(a, b)  = C(a, b; s) - C(a, b; s \\ k)     (> 0: k pushes a over b)
    placebo          z-score of dC_k among dC_j of ALL owned items j of the same position (median / 1.4826 MAD):
                     "removing k matters more than removing a typical owned item"
    distribution     KL(pi(s) || pi(s \\ k)), rank of a and the top-two margin with and without k
    value            dV_k = P(win)(s) - P(win)(s \\ k) and dHP_k (HP head, end of the floor): what the value heads
                     think k is worth here

dlog pi_k(a) = log pi(a|s) - log pi(a|s \\ k) (ledger section 833) mixes a's own logit with all competitors'; the
contrast against one reference does not. Pairs mode adds the double difference (ledger section 833 follow-up):

    D2 = [C(a, ref; s + k) - C(a, ref; s)] - mean_c [C(a, ref; s + c) - C(a, ref; s)]

with controls c = other owned cards (strong ones and weak filler), and the matched-offer version: k's effect on a
minus its effect on offered cards b of the same type / rarity / cost.

Token edits (AmberGameEncoder.cpp's layout; only out-of-combat positions):
  - remove a deck card: its CARD token goes, later deck cards' index (CARD 11) moves down by one, RUN 29 (deck size
    / 30) drops; a stack of merged copies (--merge-cards, CARD 41 = (copies - 1) / 10) loses one copy instead;
  - remove a relic: its RELIC token goes, later relics' order (RELIC 2) moves down, RUN 30 (relics / 20) drops;
  - remove a potion: its POTION token goes, RUN 27 (potions / 5) drops;
  - an action naming a removed token (a card-select choice of that card, a potion's drink / discard, an event
    option naming it) goes with it; the other actions keep their order;
  - add a deck card / relic: the inverse, with a token of that card / relic copied from another position of the
    window (or, for a card nobody owned, its id with the float pattern of its cost's deck tokens);
  - offer card a: an offered card's token is replaced by a reward token of a from another position, keeping its
    reward slots (CARD 11, 39, 40), so its action stays valid.
Only the item changes: what a relic already did to the state (max HP, gold) stays. Known limit: the net never saw
these edited states in training (out of distribution by construction; the placebo / control columns calibrate it).

Modes:
  table   per sampled decision (any kind): actions with labels, prior, logit vs reference; for the net's top action
          the owned items that push it over the runner-up and those that pull it back, with placebo z, KL, dV.
  survey  per decision kind over many positions: how concentrated the explanations are (share of items with
          |z| > 3, top item's share of the total |dC|, decisions whose top action flips without one item, KL).
  pairs   2x2 test of named pairs "OFFERED<OWNED" in real card rewards (see above), with log pi deltas (section
          833), the contrast deltas against Skip and against the other offers, D2 against strong and filler
          controls, and the matched-offer D2.

usage: explain.py --ckpt CKPT --replay DIR --mode table|survey|pairs [...] [--out FILE.json]
"""

import argparse
import json
import os
import re
import sys

import numpy as np
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import amber_net  # noqa: E402

RUN, PLAYER, STATUS, MONSTER, CARD, RELIC, POTION, OPTION, MAP = range(9)
END_TURN, PLAY_CARD, USE_POTION, DISCARD_POTION = 0, 1, 2, 3
MAP_MOVE, CHOOSE_OPTION, CHOOSE_CARD, SKIP = 10, 11, 12, 13
F_DECK, F_INDEX, F_UPG, F_COPIES, F_REWARD = 10, 11, 12, 41, 38
KEEP_REWARD = (11, 39, 40)
SCREENS = ("EVENT", "REWARDS", "BOSS_RELIC", "CARD_SELECT", "MAP", "TREASURE", "REST", "SHOP", "BATTLE")
SELECT_TYPES = ("TRANSFORM", "TRANSFORM_UPGRADE", "UPGRADE", "REMOVE", "DUPLICATE", "OBTAIN", "BOTTLE",
                "BONFIRE_SPIRITS")
OPT_KINDS = ("gold", "card", "relic", "potion", "emerald key", "sapphire key", "Singing Bowl", "shop card",
             "shop relic", "shop potion", "shop remove", "boss relic", "rest", "Neow", "event", "match slot", "chest")
ROOMS = ("shop", "rest", "event", "elite", "monster", "treasure", "boss", "boss treasure")
REST_OPTS = ("rest", "smith", "recall", "lift", "toke", "dig", "skip")
CHESTS = ("small", "medium", "large")


# ---------------------------------------------------------------------------------------------------- names

def _header(header):
    with open(os.path.join(ROOT, "include", header)) as f:
        return f.read()


def enum_strings(header, name):
    m = re.search(name + r"\s*\[\]\s*=?\s*\{(.*?)\};", _header(header), re.S)
    return re.findall(r'"([^"]*)"', m.group(1))


def enum_members(header, name):
    """Member names of `enum class name` in declaration order (explicit = values only where they restate it)."""
    m = re.search(r"enum class " + name + r"\b[^{]*\{(.*?)\}", _header(header), re.S)
    body = re.sub(r"//[^\n]*", "", m.group(1))
    return [x.split("=")[0].strip() for x in body.split(",") if x.split("=")[0].strip()]


class Vocab:
    """AmberEncoder.h's shared id space (cards, relics, potions, monsters, events, screens) with names."""

    def __init__(self):
        C = "constants/"
        self.card_enum = enum_strings(C + "Cards.h", "cardEnumStrings")
        self.card_name = enum_strings(C + "Cards.h", "cardNames")
        text = _header(C + "Cards.h")
        self.card_type = re.findall(r"CardType::(\w+)", re.search(r"cardTypes\[\]\s*=\s*\{(.*?)\};", text, re.S).group(1))
        self.card_rarity = re.findall(r"CardRarity::(\w+)",
                                      re.search(r"cardRarities\[\]\s*=\s*\{(.*?)\};", text, re.S).group(1))
        relic_enum = enum_strings(C + "Relics.h", "relicEnumNames")
        relic_name = enum_strings(C + "Relics.h", "relicNames")
        potion_enum = enum_strings(C + "Potions.h", "potionEnumNames")
        potion_name = enum_strings(C + "Potions.h", "potionNames")
        status = enum_members(C + "PlayerStatusEffects.h", "PlayerStatus")
        monsters = enum_members(C + "MonsterIds.h", "MonsterId")
        moves = enum_members(C + "MonsterMoves.h", "MonsterMoveId")
        mstatus = enum_members(C + "MonsterStatusEffects.h", "MonsterStatus")
        events = enum_members(C + "Events.h", "Event")
        event_name = enum_strings(C + "Events.h", "eventGameNames")
        zap = self.card_enum.index("ZAP")
        self.relic_base = 1 + zap
        self.potion_base = self.relic_base + relic_enum.index("RED_CIRCLET") + 1
        status_base = self.potion_base + potion_enum.index("WEAK_POTION") - 1
        self.monster_base = status_base + status.index("THE_BOMB")
        move_base = self.monster_base + monsters.index("WRITHING_MASS")
        mpow_base = move_base + moves.index("WRITHING_MASS_STRONG_STRIKE")
        self.event_base = mpow_base + mstatus.index("TIME_WARP") - mstatus.index("ANGRY") + 1
        self.neow = events.index("NEOW")
        self.screen_base = self.event_base + events.index("WORLD_OF_GOOP") - self.neow + 1
        self.enum, self.name = {}, {}   # id -> CLI name ("relic:DEAD_BRANCH"), id -> display name
        for i in range(1, zap + 1):
            self.enum[i], self.name[i] = self.card_enum[i], self.card_name[i]
        for i, r in enumerate(relic_enum[:-1]):
            self.enum[self.relic_base + i], self.name[self.relic_base + i] = "relic:" + r, relic_name[i]
        for p in range(2, len(potion_enum)):
            self.enum[self.potion_base + p - 2] = "potion:" + potion_enum[p]
            self.name[self.potion_base + p - 2] = potion_name[p]
        for m in range(1, len(monsters)):
            self.enum[self.monster_base + m - 1] = "monster:" + monsters[m]
            self.name[self.monster_base + m - 1] = monsters[m].replace("_", " ").title()
        for e in range(self.neow, len(events)):
            self.enum[self.event_base + e - self.neow] = "event:" + events[e]
            self.name[self.event_base + e - self.neow] = event_name[e] if e < len(event_name) else events[e]
        self.ids = {v: k for k, v in self.enum.items()}
        self.neow_bonus = [s for s in enum_strings("game/Neow.h", "bonusStrings")]
        self.neow_drawback = enum_strings("game/Neow.h", "drawbackStrings")

    def of(self, i):
        return self.name.get(int(i), f"id {int(i)}") if i else ""

    def is_card(self, i):
        return 0 < int(i) < self.relic_base

    def card_info(self, i):
        i = int(i)
        return self.card_type[i], self.card_rarity[i]


# ---------------------------------------------------------------------------------------------------- positions

class Row:
    """One position: tokens (type, ids, f) and legal actions, as arrays the edits below copy."""

    def __init__(self, tt, ids, f, a_type, a_src, a_tgt, a_f):
        self.tt, self.ids, self.f = tt, ids, f
        self.a_type, self.a_src, self.a_tgt, self.a_f = a_type, a_src, a_tgt, a_f

    def copy(self):
        return Row(*(x.copy() for x in (self.tt, self.ids, self.f, self.a_type, self.a_src, self.a_tgt, self.a_f)))

    def deck(self):
        return np.flatnonzero((self.tt == CARD) & (self.f[:, F_DECK] == 1))

    def offered(self):
        return np.flatnonzero((self.tt == CARD) & (self.f[:, F_REWARD] == 1))

    def relics(self):
        return np.flatnonzero(self.tt == RELIC)

    def potions(self):
        return np.flatnonzero(self.tt == POTION)

    def action_of(self, tok):
        hit = np.flatnonzero((self.a_type == CHOOSE_CARD) & (self.a_src == tok))
        return int(hit[0]) if len(hit) else -1

    def skip(self):
        hit = np.flatnonzero(self.a_type == SKIP)
        return int(hit[0]) if len(hit) else -1

    def screen(self):
        hot = np.flatnonzero(self.f[0, 5:14])
        return SCREENS[int(hot[0])] if len(hot) else "?"

    def select_type(self):
        hot = np.flatnonzero(self.f[0, 42:50])
        return SELECT_TYPES[int(hot[0])] if len(hot) else "?"

    def copies(self, i):
        return 1 + round(float(self.f[i, F_COPIES]) * 10) if self.tt[i] == CARD and self.f[i, F_DECK] else 1

    def _drop(self, i):
        """Drops token i and every action naming it; returns the kept actions' old indices."""
        keep = np.flatnonzero((self.a_src != i) & (self.a_tgt != i))
        if len(keep) < len(self.a_type):
            self.a_type, self.a_src, self.a_tgt, self.a_f = (x[keep] for x in (self.a_type, self.a_src, self.a_tgt, self.a_f))
        for a in (self.a_src, self.a_tgt):
            a[a > i] -= 1
        self.tt, self.ids, self.f = (np.delete(x, i, 0) for x in (self.tt, self.ids, self.f))
        return keep

    def _insert(self, i, tt, ids, f):
        for a in (self.a_src, self.a_tgt):
            a[a >= i] += 1
        self.tt = np.insert(self.tt, i, tt)
        self.ids = np.insert(self.ids, i, ids, 0)
        self.f = np.insert(self.f, i, f, 0)

    def _bump(self, slot, per, by):
        self.f[0, slot] = np.float16((round(float(self.f[0, slot]) * per) + by) / per)

    def remove_card(self, i):
        """One copy of deck card token i; returns the kept actions' old indices."""
        if round(float(self.f[i, F_COPIES]) * 10) > 0:
            self.f[i, F_COPIES] = np.float16((round(float(self.f[i, F_COPIES]) * 10) - 1) / 10)
            keep = np.arange(len(self.a_type))
        else:
            idx = round(float(self.f[i, F_INDEX]) * 10)
            for j in self.deck():
                k = round(float(self.f[j, F_INDEX]) * 10)
                if k > idx:
                    self.f[j, F_INDEX] = np.float16((k - 1) / 10)
            keep = self._drop(i)
        self._bump(29, 30, -1)
        return keep

    def remove_relic(self, i):
        order = round(float(self.f[i, 2]) * 20)
        for j in self.relics():
            k = round(float(self.f[j, 2]) * 20)
            if k > order:
                self.f[j, 2] = np.float16((k - 1) / 20)
        keep = self._drop(i)
        self._bump(30, 20, -1)
        return keep

    def remove_potion(self, i):
        """A free slot makes reward potions legal (OPTION 31) and shop potions legal where affordable; actions that
        were not legal before cannot appear (the action list is fixed)."""
        keep = self._drop(i)
        self._bump(27, 5, -1)
        for t in np.flatnonzero(self.tt == OPTION):
            if self.f[t, 12 + OPT_KINDS.index("potion")]:
                self.f[t, 31] = 1
            elif self.f[t, 12 + OPT_KINDS.index("shop potion")] and self.f[t, 33]:
                self.f[t, 31] = 1
        return keep

    def remove(self, kind, i):
        return {"card": self.remove_card, "relic": self.remove_relic, "potion": self.remove_potion}[kind](int(i))

    def add_card(self, ids, f):
        """A deck card from a template token (another position's deck token of that card, one copy)."""
        deck = self.deck()
        g = f.copy()
        g[F_INDEX] = g[F_COPIES] = 0
        for j in deck:
            h = self.f[j].copy()
            h[F_INDEX] = h[F_COPIES] = 0
            if (self.ids[j] == ids).all() and (h == g).all() and self._merged():
                self.f[j, F_COPIES] = np.float16((round(float(self.f[j, F_COPIES]) * 10) + 1) / 10)
                self._bump(29, 30, 1)
                return
        n = round(float(self.f[0, 29]) * 30)
        g[F_INDEX] = np.float16(n / 10)
        cards = np.flatnonzero(self.tt == CARD)
        at = int(deck[-1]) + 1 if len(deck) else (int(cards[0]) if len(cards) else int(np.searchsorted(self.tt, CARD)))
        self._insert(at, CARD, ids, g)
        self._bump(29, 30, 1)

    def _merged(self):
        """Whether the position was encoded with --merge-cards (a stack token exists, or no duplicate deck tokens)."""
        d = self.deck()
        if (self.f[d, F_COPIES] > 0).any():
            return True
        keys = [(tuple(self.ids[j]), self.f[j, F_UPG]) for j in d]
        return len(keys) == len(set(keys)) and len(keys) > 10

    def add_relic(self, ids, f):
        rel = self.relics()
        g = f.copy()
        g[2] = np.float16(len(rel) / 20)
        at = int(rel[-1]) + 1 if len(rel) else int(np.searchsorted(self.tt, RELIC))
        self._insert(at, RELIC, ids, g)
        self._bump(30, 20, 1)

    def offer(self, tok, ids, f):
        g = f.copy()
        for s in KEEP_REWARD:
            g[s] = self.f[tok, s]
        self.ids[tok], self.f[tok] = ids, g


def owned_items(r):
    """(kind, token, multiplicity) of every owned thing a position can lose: deck card tokens, relics, potions."""
    return ([("card", int(i), r.copies(i)) for i in r.deck()] + [("relic", int(i), 1) for i in r.relics()]
            + [("potion", int(i), 1) for i in r.potions()])


def item_name(r, kind, i, vocab):
    n = vocab.of(r.ids[i, 0])
    if kind == "card" and r.f[i, F_UPG]:
        n += "+"
    return n


def decision_kind(r):
    """A coarse kind of the decision at r (for grouping): the screen, refined by what the options are."""
    sc = r.screen()
    types = set(int(t) for t in r.a_type)
    if sc == "REWARDS":
        if CHOOSE_CARD in types:
            return "card reward"
        kinds = {OPT_KINDS[int(np.flatnonzero(r.f[t, 12:29])[0])] for t in r.a_src[r.a_type == CHOOSE_OPTION]
                 if t >= 0 and r.f[t, 12:29].any()}
        if kinds:
            return "reward " + "/".join(sorted(kinds))
        return "potion discard" if DISCARD_POTION in types else "reward"
    if sc == "CARD_SELECT":
        return "select " + r.select_type().lower()
    if sc == "EVENT":
        src = r.a_src[(r.a_type == CHOOSE_OPTION) & (r.a_src >= 0)]
        if len(src) and r.f[src, 12 + OPT_KINDS.index("Neow")].any():
            return "Neow"
        return "event"
    return {"BOSS_RELIC": "boss relic", "MAP": "map", "TREASURE": "chest", "REST": "campfire", "SHOP": "shop"}.get(sc, sc)


def action_label(r, a, vocab):
    """A short human label of action a of position r."""
    t, s, g = int(r.a_type[a]), int(r.a_src[a]), int(r.a_tgt[a])
    if t == SKIP:
        return {"REWARDS": "skip / leave rewards", "SHOP": "leave shop", "CARD_SELECT": "skip"}.get(r.screen(), "skip")
    if t in (USE_POTION, DISCARD_POTION):
        return ("drink " if t == USE_POTION else "discard ") + (vocab.of(r.ids[s, 0]) if s >= 0 else "potion")
    if t == MAP_MOVE and g >= 0:
        hot = np.flatnonzero(r.f[g, 3:11])
        room = ROOMS[int(hot[0])] if len(hot) else "?"
        if r.f[g, 18]:
            return "map: boss " + vocab.of(r.ids[g, 0])
        x, y = round(float(r.f[g, 0]) * 6), round(float(r.f[g, 1]) * 15)
        jump = " (Wing Boots)" if r.f[g, 21] else ""
        return f"map: {room}{' (burning)' if r.f[g, 16] else ''} x{x} y{y}{jump}"
    if t == CHOOSE_CARD and s >= 0:
        n = vocab.of(r.ids[s, 0]) + ("+" if r.f[s, F_UPG] else "")
        if r.f[s, F_REWARD]:
            return "take " + n
        if r.screen() == "CARD_SELECT":
            return r.select_type().lower() + " " + n
        return n
    if t == CHOOSE_OPTION and s >= 0:
        hot = np.flatnonzero(r.f[s, 12:29])
        kind = OPT_KINDS[int(hot[0])] if len(hot) else "option"
        item = vocab.of(r.ids[s, 0])
        price = f" ({round(float(r.f[s, 32]) * 100)} g)" if r.f[s, 32] else ""
        if kind == "gold":
            return f"gold {round(float(r.f[s, 34]) * 100)}"
        if kind in ("relic", "potion", "boss relic"):
            return f"{'take ' if kind != 'boss relic' else 'boss relic '}{item}" + (" (sapphire key pair)" if r.f[s, 39] else "")
        if kind.startswith("shop"):
            what = "remove a card" if kind == "shop remove" else item + ("+" if r.f[s, 35] else "")
            return f"buy {what}{price}"
        if kind == "rest":
            h = np.flatnonzero(r.f[s, 40:47])
            return "campfire: " + (REST_OPTS[int(h[0])] if len(h) else "?")
        if kind == "chest":
            return "open chest"
        if kind == "Neow":
            b = np.flatnonzero(r.f[s, 40:59])
            d = np.flatnonzero(r.f[s, 59:64])
            text = vocab.neow_bonus[int(b[0])] if len(b) else "?"
            if len(d):
                text += " " + vocab.neow_drawback[int(d[0]) + 2]
            return "Neow: " + text
        if kind == "event":
            h = np.flatnonzero(r.f[s, 40:52])
            extra = f" [{vocab.of(r.ids[s, 1])}]" if r.ids[s, 1] else ""
            return f"{item} option {int(h[0]) if len(h) else '?'}{extra}"
        return kind + (" " + item if item else "")
    return f"action type {t}"


# ---------------------------------------------------------------------------------------------------- data, net

def load_replay(path, extra=False):
    """The saved window's samples as (rows, meta); run = index of the run a sample belongs to (samples arrive run by
    run; a new run starts where the floor falls). extra: also outcome, HP labels, the search policy and value."""
    st = json.load(open(os.path.join(path, "state.json")))
    if st["layout"]["compact"]:
        raise SystemExit("explain.py reads windows saved without --compact-samples")
    ld = lambda k: np.load(os.path.join(path, k + ".npy"), mmap_mode="r")   # noqa: E731
    tt, ids, f = ld("tok_type"), ld("ids"), ld("f")
    a = {k: ld(k) for k in ("a_type", "a_src", "a_tgt", "a_f")}
    ts, nt, as_, na = ld("tok_start"), ld("ntok"), ld("act_start"), ld("nact")
    floor, combat = ld("meta.floor"), ld("meta.combat")
    more = {}
    if extra:
        for k in ("outcome", "hp_end", "max_hp", "has_policy", "search_value"):
            if os.path.exists(os.path.join(path, f"meta.{k}.npy")):
                more[k] = ld("meta." + k)
        pol = ld("policy") if os.path.exists(os.path.join(path, "policy.npy")) else None
    cs, ct, ca = len(nt), len(tt), len(a["a_type"])
    rows, meta, run, last = [], [], -1, 10 ** 9
    for s in range(st["scalars"]["s_tail"], st["scalars"]["s_head"]):
        j = s % cs
        fl = int(floor[j])
        if fl < last:
            run += 1
        last = fl
        ti = (int(ts[j]) + np.arange(int(nt[j]))) % ct
        ai = (int(as_[j]) + np.arange(int(na[j]))) % ca
        rows.append(Row(np.asarray(tt[ti], np.int64), np.asarray(ids[ti], np.int64), np.asarray(f[ti], np.float16),
                        np.asarray(a["a_type"][ai], np.int64), np.asarray(a["a_src"][ai], np.int64),
                        np.asarray(a["a_tgt"][ai], np.int64), np.asarray(a["a_f"][ai], np.float16)))
        m = {"floor": fl, "combat": int(combat[j]), "run": run}
        if extra:
            for k, v in more.items():
                m[k] = float(v[j])
            if pol is not None and m.get("has_policy", 1):
                m["policy"] = np.asarray(pol[ai], np.float32)
        meta.append(m)
    return rows, meta


def load_net(ckpt):
    sd = torch.load(ckpt, map_location="cpu", weights_only=False)["net"]
    d = sd["type_emb.weight"].shape[1]
    layers = 1 + max(int(k.split(".")[2]) for k in sd if k.startswith("trunk.layers."))
    net = amber_net.AmberNet(d=d, layers=layers, hp_floors=sd["hp_floor.2.weight"].shape[0],
                             soft_policy=any(k.startswith("pol_soft.") for k in sd),
                             aux_slots=(sd["aux_fight.2.weight"].shape[0] // 2) if "aux_fight.2.weight" in sd else 0)
    net.load_state_dict(sd)
    net.sdpa = True
    return net.eval()


def batch_of(chunk):
    B, T, A = len(chunk), max(len(r.tt) for r in chunk), max(len(r.a_type) for r in chunk)
    b = {"tok_type": torch.zeros(B, T, dtype=torch.long), "ids": torch.zeros(B, T, 4, dtype=torch.long),
         "f": torch.zeros(B, T, 64), "mask": torch.zeros(B, T, dtype=torch.bool),
         "a_type": torch.zeros(B, A, dtype=torch.long), "a_src": torch.full((B, A), -1, dtype=torch.long),
         "a_tgt": torch.full((B, A), -1, dtype=torch.long), "a_f": torch.zeros(B, A, 8),
         "a_mask": torch.zeros(B, A, dtype=torch.bool)}
    for i, r in enumerate(chunk):
        n, m = len(r.tt), len(r.a_type)
        b["tok_type"][i, :n] = torch.from_numpy(r.tt)
        b["ids"][i, :n] = torch.from_numpy(r.ids)
        b["f"][i, :n] = torch.from_numpy(r.f.astype(np.float32))
        b["mask"][i, :n] = True
        b["a_type"][i, :m] = torch.from_numpy(r.a_type)
        b["a_src"][i, :m] = torch.from_numpy(r.a_src)
        b["a_tgt"][i, :m] = torch.from_numpy(r.a_tgt)
        b["a_f"][i, :m] = torch.from_numpy(r.a_f.astype(np.float32))
        b["a_mask"][i, :m] = True
    return b


class Eval:
    """The net's outputs at one position: logits z [A], log pi [A], outcome distribution [57] (0 = win, f = death
    on floor f), HP distribution [256] (end of the floor), per-floor HP [56] (HP / 255)."""
    __slots__ = ("z", "lp", "dist", "hpd", "hpf")

    def __init__(self, z, dist, hpd, hpf):
        self.z = z
        self.lp = z - np.logaddexp.reduce(z)
        self.dist, self.hpd, self.hpf = dist, hpd, hpf

    @property
    def pwin(self):
        return float(self.dist[0])

    @property
    def hp(self):
        return float(self.hpd @ np.arange(len(self.hpd)))

    @property
    def efloor(self):
        w = np.arange(len(self.dist), dtype=np.float64)
        w[0] = 57
        return float(self.dist @ w)


@torch.no_grad()
def evaluate(net, rows, batch=256):
    out = []
    for s in range(0, len(rows), batch):
        chunk = rows[s:s + batch]
        o = net(batch_of(chunk))
        z = o[0].float().numpy().astype(np.float64)
        dist = torch.softmax(o[1].float(), -1).numpy().astype(np.float64)
        hpd = torch.softmax(o[2].float(), -1).numpy().astype(np.float64)
        hpf = o[3].float().numpy()
        out += [Eval(z[i, :len(r.a_type)].copy(), dist[i], hpd[i], hpf[i]) for i, r in enumerate(chunk)]
    return out


# ---------------------------------------------------------------------------------------------------- measures

def robust_z(x):
    """(x - median) / (1.4826 MAD), the scale floored at 0.05 logits (all-equal effects give z = 0)."""
    x = np.asarray(x, float)
    med = np.median(x)
    mad = 1.4826 * np.median(np.abs(x - med))
    return (x - med) / max(mad, 0.05)


def kl(p_log, q_log):
    p = np.exp(p_log)
    return float((p * (p_log - q_log)).sum())


def reference(r, ev, a):
    """The reference action of a: Skip where it exists (and a is not Skip), else the best other action."""
    sk = r.skip()
    if sk >= 0 and sk != a:
        return sk
    order = np.argsort(-ev.z)
    return int(order[0] if order[0] != a else order[1])


def explain_position(net, r, vocab, items=None):
    """Leave-one-out over the owned items of position r (each loses one copy).

    Returns base (Eval), items [(kind, tok, name, copies)], evs [Eval per item, over the item's kept actions], keep
    [kept action indices per item]."""
    items = owned_items(r) if items is None else items
    variants, keeps = [], []
    for kind, i, _ in items:
        v = r.copy()
        keeps.append(v.remove(kind, i))
        variants.append(v)
    ev = evaluate(net, [r] + variants)
    return ev[0], [(k, i, item_name(r, k, i, vocab), c) for k, i, c in items], ev[1:], keeps


def contrast_effects(base, evs, keeps, a, b):
    """dC_k(a, b) per item (nan where a or b went with the item)."""
    out = np.full(len(evs), np.nan)
    c0 = base.z[a] - base.z[b]
    for k, (e, keep) in enumerate(zip(evs, keeps)):
        pos = {int(o): n for n, o in enumerate(keep)}
        if a in pos and b in pos:
            out[k] = c0 - (e.z[pos[a]] - e.z[pos[b]])
    return out


def position_report(net, r, m, vocab, top=4):
    base, items, evs, keeps = explain_position(net, r, vocab)
    A = len(r.a_type)
    order = [int(x) for x in np.argsort(-base.z)]
    best, second = order[0], order[1] if A > 1 else order[0]
    acts = []
    for a in order:
        ref = reference(r, base, a)
        acts.append({"action": int(a), "label": action_label(r, a, vocab), "prior": float(np.exp(base.lp[a])),
                     "logit": float(base.z[a]), "ref": action_label(r, ref, vocab),
                     "vs_ref": float(base.z[a] - base.z[ref])})
    rep = {"kind": decision_kind(r), "floor": m["floor"], "run": m["run"], "p_win": base.pwin, "hp": base.hp,
           "deck": int(sum(r.copies(i) for i in r.deck())), "relics": len(r.relics()), "actions": acts}
    if A < 2 or not items:
        return rep, None
    dc = contrast_effects(base, evs, keeps, best, second)
    ok = ~np.isnan(dc)
    z = np.full(len(dc), np.nan)
    if ok.sum() >= 3:
        z[ok] = robust_z(dc[ok])
    info = []
    for k, ((kind, i, name, c), e, keep) in enumerate(zip(items, evs, keeps)):
        pos = {int(o): n for n, o in enumerate(keep)}
        lp0 = base.lp[keep] - np.logaddexp.reduce(base.lp[keep])
        top_wo = int(keep[int(np.argmax(e.z))])
        info.append({"kind": kind, "item": name, "copies": c, "dC": float(dc[k]), "z": float(z[k]),
                     "kl": kl(lp0, e.lp), "top_without": action_label(r, top_wo, vocab),
                     "flips": best in pos and top_wo != best,   # an item whose removal takes the action does not count
                     "dpwin": base.pwin - e.pwin, "dhp": base.hp - e.hp,
                     "dlogpi_best": float(base.lp[best] - e.lp[pos[best]]) if best in pos else float("nan")})
    good = [x for x in info if not np.isnan(x["dC"])]
    good.sort(key=lambda x: -x["dC"])
    rep["best"], rep["runner_up"] = action_label(r, best, vocab), action_label(r, second, vocab)
    rep["supports"] = good[:top]
    rep["opposes"] = [x for x in good[::-1][:top] if x["dC"] < 0]
    rep["value_items"] = sorted(info, key=lambda x: -abs(x["dpwin"]))[:top]
    rep["flips"] = [x["item"] for x in info if x["flips"]]
    return rep, info


def print_report(rep):
    print(f"\n[{rep['kind']}] floor {rep['floor']}  P(win) {rep['p_win']:.3f}  HP {rep['hp']:.0f}  deck {rep['deck']}"
          f"  relics {rep['relics']}")
    for a in rep["actions"][:8]:
        print(f"   {a['prior']:6.3f}  {a['label']:<44} {a['vs_ref']:+6.2f} vs {a['ref']}")
    if "supports" not in rep:
        return
    f = lambda x: f"{x['item']} {x['dC']:+.2f} (z {x['z']:+.1f})"   # noqa: E731
    print(f"   {rep['best']} over {rep['runner_up']}:")
    print("     for:     " + ", ".join(f(x) for x in rep["supports"]))
    print("     against: " + ", ".join(f(x) for x in rep["opposes"]))
    print("     value:   " + ", ".join(f"{x['item']} {x['dpwin']:+.3f} P(win) {x['dhp']:+.1f} HP" for x in rep["value_items"]))
    if rep["flips"]:
        print("     top action changes without: " + ", ".join(rep["flips"]))


def decisions(rows, meta):
    """Out-of-combat positions with at least two legal actions."""
    return [i for i, (r, m) in enumerate(zip(rows, meta)) if not m["combat"] and len(r.a_type) >= 2]


def mode_table(net, rows, meta, vocab, args, rng):
    pool = decisions(rows, meta)
    if args.kinds:
        want = set(args.kinds.split(","))
        pool = [i for i in pool if decision_kind(rows[i]) in want]
    pick = rng.choice(pool, min(args.states, len(pool)), replace=False)
    out = []
    for si in sorted(pick):
        rep, _ = position_report(net, rows[si], meta[si], vocab, args.top)
        rep["sample"] = int(si)
        print_report(rep)
        out.append(rep)
    return out


def mode_survey(net, rows, meta, vocab, args, rng):
    """Per decision kind: how concentrated the leave-one-out explanations are."""
    by = {}
    for i in decisions(rows, meta):
        by.setdefault(decision_kind(rows[i]), []).append(i)
    out = {}
    print(f"{'kind':<28} {'pos':>5} {'n':>4} {'items':>5} {'|z|>3':>6} {'top share':>9} {'flip':>5} "
          f"{'KL top':>7} {'|dC| top':>8} {'|dPwin| top':>11}")
    for kind in sorted(by, key=lambda k: -len(by[k])):
        idx = by[kind]
        pick = rng.choice(idx, min(args.states, len(idx)), replace=False)
        share, big, flip, kls, dcs, dvs, nitems = [], [], [], [], [], [], []
        for si in pick:
            rep, info = position_report(net, rows[si], meta[si], vocab, args.top)
            if not info:
                continue
            dc = np.array([x["dC"] for x in info])
            zs = np.array([x["z"] for x in info])
            ok = ~np.isnan(dc)
            if ok.sum() < 3:
                continue
            nitems.append(int(ok.sum()))
            a = np.abs(dc[ok])
            share.append(float(a.max() / max(a.sum(), 1e-9)))
            big.append(float((np.abs(zs[ok]) > 3).mean()))
            flip.append(float(bool(rep["flips"])))
            j = int(np.nanargmax(np.abs(dc)))
            kls.append(info[j]["kl"])
            dcs.append(float(a.max()))
            dvs.append(float(max(abs(x["dpwin"]) for x in info)))
        if not nitems:
            continue
        res = {"positions": len(idx), "n": len(nitems), "items": float(np.mean(nitems)),
               "share_abs_z_gt3": float(np.mean(big)), "top_item_share": float(np.mean(share)),
               "flip_rate": float(np.mean(flip)), "kl_top": float(np.mean(kls)),
               "abs_dc_top": float(np.mean(dcs)), "abs_dpwin_top": float(np.mean(dvs))}
        out[kind] = res
        print(f"{kind:<28} {res['positions']:5d} {res['n']:4d} {res['items']:5.1f} {res['share_abs_z_gt3']:6.2f} "
              f"{res['top_item_share']:9.2f} {res['flip_rate']:5.2f} {res['kl_top']:7.3f} {res['abs_dc_top']:8.2f} "
              f"{res['abs_dpwin_top']:11.4f}")
    return out


# ---------------------------------------------------------------------------------------------------- pairs

def templates(rows, meta):
    """Tokens to copy: deck[(id, upgraded)] (a single-copy deck token), reward[(id, upgraded)], relic[id]."""
    deck, reward, relic = {}, {}, {}
    for r, m in zip(rows, meta):
        if m["combat"]:
            continue
        for i in r.deck():
            if r.f[i, F_COPIES] == 0 and not r.f[i, [32, 35, 36]].any():   # not bottled / selectable / picked
                deck.setdefault((int(r.ids[i, 0]), int(r.f[i, F_UPG])), (r.ids[i].copy(), r.f[i].copy()))
        for i in r.offered():
            reward.setdefault((int(r.ids[i, 0]), int(r.f[i, F_UPG])), (r.ids[i].copy(), r.f[i].copy()))
        for i in r.relics():
            relic.setdefault(int(r.ids[i, 0]), (r.ids[i].copy(), r.f[i].copy()))
    return deck, reward, relic


class Templates:
    """Owned / offered tokens by CLI name ("BARRICADE", "relic:DEAD_BRANCH") from a window's positions."""

    def __init__(self, rows, meta, vocab):
        self.vocab = vocab
        self.deck, self.reward, self.relic = templates(rows, meta)
        self.built = set()

    def offer(self, spec):
        return self.reward.get((self.vocab.ids[spec], 0))

    def owned(self, spec):
        """(kind, (ids, f)) of an owned card / relic, (kind, None) if the window has no token for it."""
        ids_of = self.vocab.ids
        if spec.startswith("relic:"):
            return ("relic", self.relic.get(ids_of[spec]))
        t = self.deck.get((ids_of[spec], 0))
        if t is None and (ids_of[spec], 0) in self.reward:
            # No position owns this card: its deck token is the id plus the floats every plain deck card of its
            # cost has (checked: one float pattern per cost among the window's plain deck tokens).
            cost = self.reward[(ids_of[spec], 0)][1][13]
            same = set()
            for (_, u), (_, f) in self.deck.items():
                if u == 0 and f[13] == cost and f[33] == 1:
                    g = f.copy()
                    g[F_INDEX] = 0
                    same.add(g.tobytes())
            if len(same) == 1:
                ids = np.zeros(4, np.int64)
                ids[0] = ids_of[spec]
                t = (ids, np.frombuffer(same.pop(), np.float16).copy())
                self.built.add(spec)
        return ("card", t)

    def add(self, row, spec):
        kind, tpl = self.owned(spec)
        if tpl is None:
            raise KeyError(f"no token for {spec}")
        v = row.copy()
        (v.add_relic if kind == "relic" else v.add_card)(*tpl)
        return v


def card_rewards(rows, meta):
    return [i for i, (r, m) in enumerate(zip(rows, meta)) if not m["combat"] and len(r.offered())
            and all(r.action_of(t) >= 0 for t in r.offered())]


def boot_ci(x, run, rng, n=2000):
    """Mean and a 95 % interval from a bootstrap over runs (positions of one run are not independent)."""
    x, run = np.asarray(x, float), np.asarray(run)
    ok = ~np.isnan(x)
    x, run = x[ok], run[ok]
    if not len(x):
        return float("nan"), float("nan"), float("nan")
    ids = np.unique(run)
    sums = np.array([x[run == i].sum() for i in ids])
    cnt = np.array([(run == i).sum() for i in ids])
    pick = rng.integers(0, len(ids), (n, len(ids)))
    m = sums[pick].sum(1) / cnt[pick].sum(1)
    return float(x.mean()), float(np.quantile(m, 0.025)), float(np.quantile(m, 0.975))


def mode_pairs(net, rows, meta, vocab, args, rng):
    ids_of = vocab.ids
    tp = Templates(rows, meta, vocab)
    reward_t, owned_template, built = tp.reward, tp.owned, tp.built
    cr = card_rewards(rows, meta)

    def add(row, kind, tpl):
        v = row.copy()
        (v.add_relic if kind == "relic" else v.add_card)(*tpl)
        return v

    def matched(a_name):
        """Reward templates of other cards with a's type, rarity and cost (P0-2 matched control offers)."""
        a_id = ids_of[a_name]
        cost = reward_t[(a_id, 0)][1][13]
        ty, ra = vocab.card_info(a_id)
        out = [(vocab.enum[c], t) for (c, u), t in reward_t.items()
               if u == 0 and c != a_id and vocab.card_info(c) == (ty, ra) and t[1][13] == cost]
        return out[:args.matched]

    controls = [(c, owned_template(c)) for c in args.controls.split(",") if c]
    controls = [(c, t) for c, t in controls if t[1] is not None]
    fillers = [(c, owned_template(c)) for c in args.fillers.split(",") if c]
    fillers = [(c, t) for c, t in fillers if t[1] is not None]
    report = []
    f3 = lambda t: f"{t[0]:+.3f} [{t[1]:+.3f}, {t[2]:+.3f}]"   # noqa: E731
    for pair in args.pairs.split(","):
        a_name, k_name = pair.split("<")
        a_tpl = reward_t.get((ids_of[a_name], 0))
        k_kind, k_tpl = owned_template(k_name)
        if a_tpl is None or k_tpl is None:
            print(f"{pair}: no template in the window ({'offered' if a_tpl is None else 'owned'} side), skipped")
            report.append({"pair": pair, "skipped": True})
            continue
        a_id, k_id = ids_of[a_name], ids_of[k_name]
        ctl = [(c, t) for c, t in controls if c not in (a_name, k_name)]
        fil = [(c, t) for c, t in fillers if c not in (a_name, k_name)]
        mat = [(c, t) for c, t in matched(a_name) if c != k_name]
        batch, index = [], []
        for si in cr:
            r = rows[si]
            have = {int(x) for x in r.ids[np.concatenate([r.deck(), r.offered(), r.relics()]), 0]}
            if a_id in have or k_id in have or len(r.offered()) < 2 or len(r.offered()) > 4 or r.skip() < 0:
                continue
            s0 = r.copy()
            tok = int(rng.choice(s0.offered()))
            s0.offer(tok, *a_tpl)
            a = s0.action_of(tok)
            others = [s0.action_of(t) for t in s0.offered() if t != tok]
            cs = [add(s0, t[0], t[1]) for c, t in ctl if ids_of[c] not in have]
            fs = [add(s0, t[0], t[1]) for c, t in fil]
            ms = []
            for c, t in mat:   # offer b instead of a, without / with k
                if ids_of[c] in have:
                    continue
                m0 = r.copy()
                m0.offer(tok, *t)
                ms += [m0, add(m0, k_kind, k_tpl)]
            index.append((si, len(batch), a, others, len(cs), len(fs), len(ms) // 2))
            batch += [s0, add(s0, k_kind, k_tpl)] + cs + fs + ms
        if not index:
            print(f"{pair}: no base position")
            continue
        ev = evaluate(net, batch)
        col = {k: [] for k in ("d_k", "d_c", "spec", "p0", "p1", "run", "cs_k", "cs_c", "cs_f", "co_k", "co_c",
                               "d2_skip", "d2_other", "d2_fill", "d2_match")}
        for si, at, a, others, nc, nf, nm in index:
            e0, e1 = ev[at], ev[at + 1]
            sk = rows[si].skip()   # offer() and add_*() keep the actions, so Skip keeps its index
            cskip = lambda e: e.z[a] - e.z[sk]   # noqa: E731
            coth = lambda e: e.z[a] - np.mean(e.z[others])   # noqa: E731
            ce = ev[at + 2: at + 2 + nc]
            fe = ev[at + 2 + nc: at + 2 + nc + nf]
            me = ev[at + 2 + nc + nf: at + 2 + nc + nf + 2 * nm]
            col["d_k"].append(e1.lp[a] - e0.lp[a])
            col["d_c"].append(np.mean([e.lp[a] - e0.lp[a] for e in ce]) if nc else np.nan)
            col["spec"].append((e1.lp[a] - e0.lp[a]) - np.mean([e1.lp[o] - e0.lp[o] for o in others]))
            col["p0"].append(np.exp(e0.lp[a]))
            col["p1"].append(np.exp(e1.lp[a]))
            col["run"].append(meta[si]["run"])
            col["cs_k"].append(cskip(e1) - cskip(e0))
            col["cs_c"].append(np.mean([cskip(e) - cskip(e0) for e in ce]) if nc else np.nan)
            col["cs_f"].append(np.mean([cskip(e) - cskip(e0) for e in fe]) if nf else np.nan)
            col["co_k"].append(coth(e1) - coth(e0))
            col["co_c"].append(np.mean([coth(e) - coth(e0) for e in ce]) if nc else np.nan)
            col["d2_skip"].append(col["cs_k"][-1] - col["cs_c"][-1])
            col["d2_other"].append(col["co_k"][-1] - col["co_c"][-1])
            col["d2_fill"].append(col["cs_k"][-1] - col["cs_f"][-1])
            # matched offers: k's effect on b's contrast vs Skip (b sits in a's slot, same action index)
            mb = [(me[2 * j + 1].z[a] - me[2 * j + 1].z[sk]) - (me[2 * j].z[a] - me[2 * j].z[sk]) for j in range(nm)]
            col["d2_match"].append(col["cs_k"][-1] - np.mean(mb) if nm else np.nan)
        d_k, d_c, run = np.array(col["d_k"]), np.array(col["d_c"]), np.array(col["run"])
        res = {"pair": pair, "n": len(d_k), "runs": len(set(run)), "prior_without": float(np.mean(col["p0"])),
               "prior_with": float(np.mean(col["p1"])), "delta": boot_ci(d_k, run, rng),
               "delta_control": boot_ci(d_c, run, rng), "delta_minus_control": boot_ci(d_k - d_c, run, rng),
               "specificity": boot_ci(col["spec"], run, rng),
               "skip_contrast": boot_ci(col["cs_k"], run, rng), "skip_contrast_control": boot_ci(col["cs_c"], run, rng),
               "d2_skip": boot_ci(col["d2_skip"], run, rng), "d2_other": boot_ci(col["d2_other"], run, rng),
               "d2_filler": boot_ci(col["d2_fill"], run, rng), "d2_matched": boot_ci(col["d2_match"], run, rng),
               "matched_offers": [c for c, _ in mat], "owned_token_built": k_name in built}
        report.append(res)
        print(f"{pair:<32} n {res['n']:4d} runs {res['runs']:2d}  dlogpi-ctl {f3(res['delta_minus_control'])}  "
              f"D2 skip {f3(res['d2_skip'])}  D2 other {f3(res['d2_other'])}  D2 filler {f3(res['d2_filler'])}  "
              f"D2 matched {f3(res['d2_matched'])} ({len(mat)})")
    return report


DEFAULT_PAIRS = ("CORRUPTION<DARK_EMBRACE,CORRUPTION<FEEL_NO_PAIN,CORRUPTION<relic:DEAD_BRANCH,"
                 "DARK_EMBRACE<CORRUPTION,FEEL_NO_PAIN<CORRUPTION,"
                 "BARRICADE<ENTRENCH,BARRICADE<BODY_SLAM,ENTRENCH<BARRICADE,BODY_SLAM<BARRICADE,"
                 "LIMIT_BREAK<INFLAME,LIMIT_BREAK<DEMON_FORM,LIMIT_BREAK<SPOT_WEAKNESS,HEAVY_BLADE<INFLAME,"
                 "RUPTURE<BLOODLETTING,RUPTURE<OFFERING")
DEFAULT_CONTROLS = ("SHRUG_IT_OFF,POMMEL_STRIKE,METALLICIZE,FLAME_BARRIER,SHOCKWAVE,UPPERCUT,DISARM,BATTLE_TRANCE,"
                    "CARNAGE,TWIN_STRIKE,ARMAMENTS,THUNDERCLAP")
DEFAULT_FILLERS = "STRIKE_RED,DEFEND_RED"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--replay", required=True)
    ap.add_argument("--mode", choices=("table", "survey", "pairs"), required=True)
    ap.add_argument("--states", type=int, default=10, help="table: decisions to show; survey: decisions per kind")
    ap.add_argument("--kinds", default="", help="table: only these decision kinds (comma separated)")
    ap.add_argument("--top", type=int, default=4)
    ap.add_argument("--pairs", default=DEFAULT_PAIRS, help="OFFERED<OWNED,... (OWNED may be relic:NAME)")
    ap.add_argument("--controls", default=DEFAULT_CONTROLS, help="owned control cards")
    ap.add_argument("--fillers", default=DEFAULT_FILLERS, help="owned weak filler control cards")
    ap.add_argument("--matched", type=int, default=6, help="pairs: matched control offers per pair (at most)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--threads", type=int, default=1)
    ap.add_argument("--out")
    args = ap.parse_args()
    torch.set_num_threads(args.threads)
    rng = np.random.default_rng(args.seed)
    vocab = Vocab()
    net = load_net(args.ckpt)
    rows, meta = load_replay(args.replay)
    print(f"# {len(rows)} positions, {meta[-1]['run'] + 1} runs, {len(decisions(rows, meta))} out-of-combat "
          f"decisions, {len(card_rewards(rows, meta))} card rewards")
    rep = {"table": mode_table, "survey": mode_survey, "pairs": mode_pairs}[args.mode](net, rows, meta, vocab, args, rng)
    if args.out:
        with open(args.out, "w") as fh:
            json.dump({"ckpt": args.ckpt, "replay": args.replay, "mode": args.mode, "seed": args.seed,
                       "report": rep}, fh, indent=1, default=float)


if __name__ == "__main__":
    main()
