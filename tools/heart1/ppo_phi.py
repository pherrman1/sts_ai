"""Potentials Phi(s) for potential-based reward shaping (ppo_train.py --reward heart_phi), computed in Python.

Phi is computed from public facts of each net decision line (its "floor" and the run state in its "record"), so
no change to one_combat is needed. A model is a JSON file:
  {"kind": "floor_table", "table": [p_0, p_1, ...]}        Phi = table[min(floor, len - 1)]
  {"kind": "logistic", "table": [...], "features": [...], "mean": [...], "scale": [...], "coef": [...],
   "intercept": b}                                         Phi = sigmoid(b + coef . (x - mean) / scale)
The logistic model's first feature is logit(table[floor]), so it nests the floor table. `features()` is the one
definition shared by the fit (ppo_phi_fit.py) and the learner.

With gamma = 1 and Phi(terminal) = 0 the shaping telescopes: a game's shaped return is 1{Heart} - Phi(s_0), the
same for every policy (s_0 is the first decision state), so the objective stays the Heart rate (Ng et al. 1999).
"""
import hashlib
import json
import math

FEATURES = ("logit_floor", "hp_frac", "max_hp", "gold", "keys", "deck", "relics", "potions", "act")


def load(path, sha256=None):
    raw = open(path, "rb").read()
    if sha256 and hashlib.sha256(raw).hexdigest() != sha256:
        raise ValueError(f"{path}: sha256 {hashlib.sha256(raw).hexdigest()} != {sha256}")
    m = json.loads(raw)
    if m.get("kind") not in ("floor_table", "logistic"):
        raise ValueError(f"{path}: unknown phi kind {m.get('kind')}")
    if m["kind"] == "logistic" and list(m["features"]) != list(FEATURES):
        raise ValueError(f"{path}: features {m['features']} are not {list(FEATURES)}")
    return m


def _table(m, floor):
    t = m["table"]
    return float(t[max(0, min(int(floor), len(t) - 1))])


def _logit(p):
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def features(table_model, row, rec):
    """Feature vector (FEATURES order) of one decision line `row` with its record `rec`."""
    fo = rec["obs.fixed_observation"]   # hp, max hp, gold, floor, boss, toSelect, ascension, 3 keys
    hp, max_hp, gold = float(fo[0]), float(fo[1]), float(fo[2])
    return [_logit(_table(table_model, row["floor"])),
            hp / max(max_hp, 1.0), max_hp / 100.0, gold / 1000.0, float(fo[7] + fo[8] + fo[9]),
            len(rec["obs.deck.cards"]) / 40.0, len(rec["obs.relics.relics"]) / 20.0,
            sum(1 for p in rec["obs.potions"] if p > 1) / 5.0,   # potion ids: 0 invalid, 1 empty slot
            float(rec["obs.act"])]


def value(m, row, rec):
    if m["kind"] == "floor_table":
        return _table(m, row["floor"])
    x = features(m, row, rec)
    z = m["intercept"] + sum(c * (v - mu) / s for c, v, mu, s in zip(m["coef"], x, m["mean"], m["scale"]))
    return 1.0 / (1.0 + math.exp(-z))
