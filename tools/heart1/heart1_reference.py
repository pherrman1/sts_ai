#!/usr/bin/env python3
"""heart1 parity: silverbot's own encoder and network as the reference.

Runs daniel-ziegler/sts_lightspeed's code (a checkout at commit 84ab3ea with its
`slaythespire` module built, plus heart1.pt) next to our native port
(apps/one_combat/heart1_policy.cpp, STS_OOC_HEART1). No seeds; seeded modes are
in heart1_parity_seeds.py.

  score <silverbot_repo> <heart1.pt> <records.jsonl> <out.json>
      Score records with silverbot's collate_fn and NN. Records are our
      STS_OOC_HEART1_TRACE lines or heart1score inputs. When a line carries our
      native "logits", report the max |difference| and argmax agreement.
"""
import json
import sys

import numpy as np

# collate_fn pads each choice section to a fixed width and DictSpace consumes
# them in this order (silverbot/network.py CHOICE_PATHS_OFFSET).
CHOICE_SECTIONS = (("cards", 96), ("relics", 3), ("potions", 5), ("fixed", 5), ("paths", 7))


def load_silverbot(repo):
    sys.path.insert(0, repo)
    import torch  # noqa: F401
    import slaythespire as sts  # their module, built in their checkout
    from silverbot import network
    return sts, network


def load_net(network, ckpt):
    import torch
    net = network.NN(network.ModelHP(use_value_head=True))
    state = torch.load(ckpt, map_location="cpu", weights_only=True)
    net = network.load_network_backward_compatible(net, state)
    net.eval()
    return net


def record_counts(rec):
    return (len(rec["cards_offered.cards"]), len(rec["relics_offered"]), len(rec["potions_offered"]),
            len(rec["fixed_actions"]), len(rec["paths_offered"]))


def silverbot_score(network, net, records):
    """Logits per valid choice token (token order) and the value, per record."""
    import torch
    batch = [{**rec, "chosen_idx": 0, "outcome": 0.0} for rec in records]
    with torch.no_grad():
        logits, values = net(network.collate_fn(batch))
    out = []
    for i, rec in enumerate(records):
        flat, offset = [], 0
        for (_, width), n in zip(CHOICE_SECTIONS, record_counts(rec)):
            flat.extend(float(v) for v in logits[i, offset:offset + n])
            offset += width
        out.append((flat, float(values[i])))
    return out


def normalize_record(sts, choice):
    """silverbot Choice -> the JSON record our heart1score/replay read and write."""
    from silverbot.playouts import flatten_dict
    d = flatten_dict(choice.as_dict())
    rec = {}
    for k, v in d.items():
        if k == "fixed_actions":
            rec[k] = [{"action": int(f["action"]), "gold": int(f.get("gold", 0)),
                       "card": int(f.get("card", sts.CardId.INVALID)),
                       "relic": int(f.get("relic", sts.RelicId.INVALID)),
                       "info": int(f.get("info", 0))} for f in v]
        elif isinstance(v, np.ndarray):
            rec[k] = v.astype(int).tolist()
        else:
            rec[k] = int(v)
    return rec


def compare(ours, theirs):
    diff = max(abs(a - b) for a, b in zip(ours, theirs)) if ours else 0.0
    return diff, int(np.argmax(ours)) == int(np.argmax(theirs))


def cmd_score(repo, ckpt, records_path, out_path):
    _, network = load_silverbot(repo)
    net = load_net(network, ckpt)
    lines = [json.loads(line) for line in open(records_path) if line.strip()]
    records = [line.get("record", line) for line in lines]
    results, max_diff, max_value_diff, agree, compared = [], 0.0, 0.0, 0, 0
    for start in range(0, len(records), 64):
        for j, (logits, value) in enumerate(silverbot_score(network, net, records[start:start + 64])):
            line = lines[start + j]
            row = {"logits": logits, "value": value}
            if "logits" in line:
                diff, same = compare(line["logits"], logits)
                row.update(max_abs_diff=diff, argmax_agree=same)
                max_diff = max(max_diff, diff)
                max_value_diff = max(max_value_diff, abs(line["value"] - value))
                agree += same
                compared += 1
            results.append(row)
    summary = {"records": len(records), "compared": compared, "argmax_agree": agree,
               "max_abs_logit_diff": max_diff, "max_abs_value_diff": max_value_diff}
    json.dump({"summary": summary, "rows": results}, open(out_path, "w"))
    print(json.dumps(summary))
    return 0 if agree == compared else 1


if __name__ == "__main__":
    if len(sys.argv) != 6 or sys.argv[1] != "score":
        sys.exit(__doc__)
    sys.exit(cmd_score(*sys.argv[2:]))
