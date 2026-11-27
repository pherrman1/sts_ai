"""Builds the training net of a selfplay.py checkpoint as selfplay.main does (flags from ck["args"]) and returns
(net, params in optimizer-group order, the optimizer's param_groups / state)."""
import torch


def build(sp, ck):
    a = ck["args"]
    A = (lambda k, d=None: a.get(k, d)) if isinstance(a, dict) else (lambda k, d=None: getattr(a, k, d))
    am = sp.amber_net
    d, layers = am.SIZES.get(A("net")) or tuple(int(x) for x in A("net").split("x")[:2])
    kw = dict(d=d, layers=layers, hp_floors=56, soft_policy=A("w_soft_policy", 0) > 0,
              aux_slots=sp.AUX_SLOTS if A("aux_fights") else 0,
              enemy_bias=bool(A("enemy_map_bias")), enemy_gate=bool(A("enemy_tokens")))
    if A("intent_emb") is not None:
        kw["intent_emb"] = bool(A("intent_emb"))
    if A("select_many_bits") is not None:
        kw["mask_bits"] = bool(A("select_many_bits"))
    net = am.AmberNet(**kw)
    net.sdpa = True
    net.gate_key = bool(A("enemy_gate_key"))
    net.load_state_dict(ck["net"])
    if hasattr(am, "input_options_from_ckpt"):
        am.input_options_from_ckpt(net, ck)
    named = list(net.named_parameters())
    fix = getattr(am, "INPUT_FIX_PARAMS", ())
    order = ([p for n, p in named if not sp.extra_param(n) and n not in fix]
             + [p for n, p in named if n.startswith("aux_fight.")]
             + [p for n, p in named if n in ("enemy_bias", "enemy_gate")]
             + [p for n, p in named if n in fix])
    names = {id(p): n for n, p in named}
    W = dict(w_policy=A("w_policy", 1.0), w_outcome=A("w_outcome", 1.0), w_hp=A("w_hp", 1.0),
             w_hp_floor=A("w_hp_floor", 1.0), w_soft_policy=A("w_soft_policy", 0.0), w_aux=A("w_aux", 1.0))
    return net, order, [names[id(p)] for p in order], W, A
