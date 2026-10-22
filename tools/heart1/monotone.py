"""Monotonicity rules for the heart1-format value head (distill.py --mono-weight / --mono-rules).

Each rule pairs a collated silverbot batch row with a copy that differs in one variable the run outcome should
never get worse in (out of combat): more current HP (up to max HP), more max HP at fixed HP, more gold, one potion
more, one curse fewer. perturb() returns the copy batch and per-row signs: +1 = the copy is the better state, -1 =
the copy is the worse state, 0 = the rule does not apply to the row (left unchanged). The training penalty is
relu(sign * (v - v_copy)) on value logits, averaged over the rows a rule applies to; violation rates count rows
whose better state gets the strictly lower value.

The edits act on collate_fn's tensors (silverbot @ 84ab3ea network.collate_fn): batch["fixed_obs"]
["fixed_observation"][:, 0..2] = hp, max HP, gold (record fields obs.fixed_observation[0..2]); batch["potions"]
["value"] = potion ids per slot (empty slots carry EMPTY_POTION_SLOT); batch["deck"]["value"][..., 0..1] =
(card id, upgrades) with mask True on padding; batch["extra"]["deck_misc"] (student_inputs) = card misc."""
import torch

RULES = ("hp", "mhp", "gold", "potion", "curse")
HP_CAP, GOLD_CAP = 200, 1800  # silverbot playerHpMax / playerGoldMax: sinusoid limits of the fixed observation
# Curses with no upside that a card removal takes out (Parasite, Necronomicurse, Curse of the Bell, Ascender's
# Bane and Pride have side rules and are left out).
CURSES = ("CLUMSY", "DECAY", "DOUBT", "INJURY", "NORMALITY", "PAIN", "REGRET", "SHAME", "WRITHE")
# Fixed perturbations of the violation report (comparable across runs; -3 HP and +5 max HP match prices.py).
EVAL = {"hp": -3, "mhp": 5, "gold": 50}


def ids(sts):
    """(EMPTY_POTION_SLOT id, curse card ids) from the slaythespire module."""
    return int(sts.Potion.EMPTY_POTION_SLOT), [int(getattr(sts.CardId, c)) for c in CURSES]


def _copy(b, path):
    """Shallow copy of the batch tree with a cloned tensor at path (a tuple of keys); returns (copy, tensor)."""
    out = dict(b); node = out
    for k in path[:-1]:
        node[k] = dict(node[k]); node = node[k]
    node[path[-1]] = node[path[-1]].clone()
    return out, node[path[-1]]


def _uniform(lo, hi, g):
    """Integer per row, uniform on [lo, hi] (hi >= lo elementwise)."""
    u = torch.rand(lo.shape, generator=g, device=lo.device) if g is not None else torch.rand(lo.shape, device=lo.device)
    return lo + (u * (hi - lo + 1).float()).long().clamp(max=(hi - lo).long())


def applies(b, rule, empty_potion, fixed=False):
    """Rows the rule can perturb (independent of the random deltas)."""
    fo = b["fixed_obs"]["fixed_observation"]
    hp, mhp, gold = fo[:, 0].long(), fo[:, 1].long(), fo[:, 2].long()
    if rule == "hp": return hp + EVAL["hp"] >= 1 if fixed else (hp >= 1) & ((hp < mhp) | (hp >= 2))
    if rule == "mhp": return (mhp >= 1) & (mhp + (EVAL["mhp"] if fixed else 1) <= HP_CAP)
    if rule == "gold": return gold + (EVAL["gold"] if fixed else 1) <= GOLD_CAP
    if rule == "potion": return ((~b["potions"]["mask"]) & (b["potions"]["value"] != empty_potion)).any(-1)
    if rule == "curse": return (~b["deck"]["mask"]).sum(-1) < b["deck"]["mask"].size(1)
    raise ValueError(f"unknown monotonicity rule {rule}")


def perturb(b, rule, empty_potion, curses, g=None, fixed=False, only=None):
    """(copy batch, sign per row) for one rule, on the rows in `only` (bool mask, default all) the rule applies to.
    fixed=True uses the EVAL deltas, the first filled potion slot and the first curse; otherwise deltas, slots and
    curses are drawn per row from g (a torch.Generator on b's device, or None for the global RNG)."""
    fo = b["fixed_obs"]["fixed_observation"]
    n, dev = fo.size(0), fo.device
    hp, mhp, gold = fo[:, 0].long(), fo[:, 1].long(), fo[:, 2].long()
    ok = applies(b, rule, empty_potion, fixed)
    if only is not None: ok = ok & only
    rows = ok.nonzero().squeeze(1)
    one = torch.ones_like(hp)
    if rule in ("hp", "mhp", "gold"):
        if rule == "hp":
            if fixed:
                d = torch.full_like(hp, EVAL["hp"])
            else:  # heal up to max HP when there is room, else lose HP (never below 1)
                up = hp < mhp
                d = torch.where(up, _uniform(one, (mhp - hp).clamp(1, 10), g), -_uniform(one, (hp - 1).clamp(1, 10), g))
        elif rule == "mhp":
            d = torch.full_like(mhp, EVAL["mhp"]) if fixed else _uniform(one, (HP_CAP - mhp).clamp(1, 10), g)
        else:
            d = torch.full_like(gold, EVAL["gold"]) if fixed else _uniform(one, (GOLD_CAP - gold).clamp(1, 100), g)
        c, cfo = _copy(b, ("fixed_obs", "fixed_observation"))
        col = {"hp": 0, "mhp": 1, "gold": 2}[rule]
        cfo[rows, col] += d[rows].to(cfo.dtype)
        return c, torch.where(ok, d.sign(), torch.zeros_like(d))
    sign = torch.where(ok, -one, torch.zeros_like(one))  # potion / curse: the copy is worse
    if rule == "potion":  # empty one filled slot
        pv, pm = b["potions"]["value"], b["potions"]["mask"]
        filled = (~pm) & (pv != empty_potion)
        if fixed:
            slot = filled.long().argmax(-1)
        else:
            r = torch.rand(filled.shape, generator=g, device=dev) if g is not None else torch.rand(filled.shape, device=dev)
            slot = r.masked_fill(~filled, -1.0).argmax(-1)
        c, cpv = _copy(b, ("potions", "value"))
        cpv[rows, slot[rows]] = empty_potion
        return c, sign
    if rule == "curse":  # append one curse to the deck
        dm = b["deck"]["mask"]; length = (~dm).sum(-1)
        cur = torch.tensor(curses, device=dev)
        card = cur[torch.zeros_like(length) if fixed else _uniform(torch.zeros_like(length),
                                                                   torch.full_like(length, len(curses) - 1), g)]
        c, cdv = _copy(b, ("deck", "value"))
        c["deck"]["mask"] = cdm = dm.clone()
        at = length[rows]
        cdv[rows, at, 0] = card[rows].to(cdv.dtype); cdv[rows, at, 1] = 0; cdm[rows, at] = False
        if "extra" in b and "deck_misc" in b["extra"]:
            c, misc = _copy(c, ("extra", "deck_misc"))
            misc[rows, at] = 0
        return c, sign
    raise ValueError(f"unknown monotonicity rule {rule}")


def perturb_mixed(b, rules, empty_potion, curses, g=None):
    """Training copy: one random applicable rule per row, random deltas. Returns (copy batch, sign per row); rows
    no rule applies to keep sign 0 and are unchanged."""
    dev = b["fixed_obs"]["fixed_observation"].device
    can = torch.stack([applies(b, r, empty_potion) for r in rules], 1)
    r = torch.rand(can.shape, generator=g, device=dev) if g is not None else torch.rand(can.shape, device=dev)
    pick = r.masked_fill(~can, -1.0).argmax(-1)
    c, sign = b, torch.zeros(can.size(0), dtype=torch.long, device=dev)
    for j, rule in enumerate(rules):
        c, s = perturb(c, rule, empty_potion, curses, g, only=can.any(-1) & (pick == j))
        sign = sign + s
    return c, sign


def penalty(v, v_copy, sign):
    """Mean hinge relu(sign * (v - v_copy)) over the rows with sign != 0 (value logits)."""
    m = sign != 0
    return (torch.relu(sign.to(v.dtype) * (v - v_copy)) * m).sum() / m.sum().clamp(min=1)


def violations(v, v_copy, sign):
    """Per row (sign != 0): better-state value minus worse-state value (negative = violation)."""
    m = sign != 0
    return (sign.to(v.dtype) * (v_copy - v))[m]
