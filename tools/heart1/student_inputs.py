"""Student C input extension: relic counters, act and card misc on top of silverbot's NN.

heart1's record carries relic counters but its network never reads them, and it has no act or card `misc`
(Ritual Dagger damage, Genetic Algorithm block). ExtraInputsNN adds three zero-initialised inputs, so a
student checkpoint loads into it and computes bit-identical logits until fine-tuned:
- x_deck_misc: FixedVecEmbedding of the card's misc (clamped to [-1, 999]) on each deck token;
- x_relic_counter: FixedVecEmbedding of the relic counter (clamped to [-1, 999]) on each relic token;
- x_act: Embedding(5) of the act (clamped to [0, 4]) on the fixed-observation token.
They are added after silverbot's token sum (position embedding included); the native forward
(apps/one_combat/heart1_policy.cpp, Net with x_act.weight present) adds them in the same order.

Training rows: misc from the record's "obs.deck.misc" or the capture row's "deck_misc", act from "obs.act" or
the row's "act"; rows without misc use 0.

Parity with the native forward (on a machine with torch and silverbot built at 84ab3ea):
  python3 tools/heart1/student_inputs.py perturb SILVERBOT_REPO student.pt perturbed.pt   # random x_* weights
  python3 tools/heart1/export_heart1_weights.py perturbed.pt perturbed.bin --allow-other-checkpoint --n-heads 4 --trim-map
  python3 tools/heart1/student_inputs.py score SILVERBOT_REPO perturbed.pt records.jsonl torch.jsonl [--trim-map]
  one_combat heart1score perturbed.bin records.jsonl native.jsonl   # then compare "logits" line by line
records.jsonl: heart1 records with "obs.deck.misc" and "obs.act" (STS_OOC_HEART1_TRACE or a capture's records)."""
import os
import sys

if __name__ == "__main__" and len(sys.argv) > 2:
    sys.path[:0] = [sys.argv[2], os.path.join(sys.argv[2], "build")]
import torch
from torch import nn

from silverbot import network
from silverbot.inputs import FixedVecEmbedding

LIMIT = 999
DECK, RELICS, POTIONS = network.MAX_DECK_SIZE, network.MAX_RELICS, network.sts.MAX_POTION_CAPACITY
FIXED_TOKEN = DECK + RELICS + POTIONS


def zero_fixed_vec(dim):
    e = FixedVecEmbedding(dim, [2 * LIMIT + 1])
    nn.init.zeros_(e.proj.weight); nn.init.zeros_(e.proj.bias)
    return e


def extra_batch(rows):
    """rows: dicts with "record" and optional row-level "act"/"deck_misc". Returns the batch["extra"] tensors."""
    n = len(rows)
    misc = torch.zeros(n, DECK, 1); counter = torch.zeros(n, RELICS, 1); act = torch.zeros(n, dtype=torch.long)
    for i, r in enumerate(rows):
        rec = r["record"]
        m = rec.get("obs.deck.misc") or r.get("deck_misc") or []
        if m: misc[i, :len(m), 0] = torch.tensor(m, dtype=torch.float32).clamp(-1, LIMIT)
        c = rec.get("obs.relics.relic_counters") or []
        if c: counter[i, :len(c), 0] = torch.tensor(c, dtype=torch.float32).clamp(-1, LIMIT)
        act[i] = min(max(int(rec.get("obs.act", r.get("act", 0)) or 0), 0), 4)
    return {"deck_misc": misc, "relic_counter": counter, "act": act}


class ExtraInputsNN(network.NN):
    def __init__(self, H):
        super().__init__(H)
        self.x_deck_misc = zero_fixed_vec(H.dim)
        self.x_relic_counter = zero_fixed_vec(H.dim)
        self.x_act = nn.Embedding(5, H.dim)
        nn.init.zeros_(self.x_act.weight)

    def forward(self, batch: dict):
        """silverbot NN.forward (84ab3ea) without its debug checks, aux and fork options, plus the extra inputs."""
        ex = batch["extra"]
        obs_embed, obs_mask = self.obs_embed(batch)
        choice_embed, choice_mask = self.choice_embed(batch["choices"])
        obs_embed = obs_embed.clone()
        obs_embed[:, :DECK] = obs_embed[:, :DECK] + self.x_deck_misc(ex["deck_misc"])
        obs_embed[:, DECK:DECK + RELICS] = obs_embed[:, DECK:DECK + RELICS] + self.x_relic_counter(ex["relic_counter"])
        obs_embed[:, FIXED_TOKEN] = obs_embed[:, FIXED_TOKEN] + self.x_act(ex["act"])
        x = torch.cat([obs_embed, choice_embed], dim=1)
        pos_mask = torch.cat([obs_mask, choice_mask], dim=1)
        assert self.H.num_value_layers == 0
        for i, l in enumerate(self.layers):
            x = torch.utils.checkpoint.checkpoint(l, x, pos_mask, use_reentrant=False) if i < len(self.layers) - 1 \
                else l(x, pos_mask)
        xn = self.norm(x)
        choice_logits = self.choice_logits(xn[:, obs_mask.size(1):, :]).squeeze(-1).float()
        choice_logits = choice_logits.masked_fill(choice_mask, float("-inf"))
        value_xn = self.value_head_norm(xn)
        seq_lengths = (~pos_mask).sum(dim=1, keepdim=True).float()
        pooled = value_xn.masked_fill(pos_mask.unsqueeze(-1), 0).sum(dim=1) / seq_lengths
        return choice_logits.clone(), self.value_head(pooled).squeeze(-1).float().clone()


def _hp(state):
    dim = state["norm.w"].shape[0]
    layers = sum(1 for k in state if k.endswith(".norm1.w"))
    mult = state["layers.0.mlp.w1.weight"].shape[0] // dim
    return network.ModelHP(dim=dim, n_layers=layers, mlp_dim_mult=mult, n_heads=4, use_value_head=True)


def main():
    cmd, _repo, ckpt, *rest = sys.argv[1:]
    state = torch.load(ckpt, map_location="cpu")
    net = ExtraInputsNN(_hp(state))
    missing, unexpected = net.load_state_dict(state, strict=False)
    assert not unexpected and all(k.startswith("x_") for k in missing), (missing, unexpected)
    if cmd == "perturb":
        g = torch.Generator().manual_seed(1)
        with torch.no_grad():
            for name, p in net.named_parameters():
                if name.startswith("x_"): p.copy_(0.05 * torch.randn(p.shape, generator=g))
        torch.save(net.state_dict(), rest[0])
    elif cmd == "score":
        import json
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        records_path, out_path, *flags = rest
        recs = [json.loads(l) for l in open(records_path) if l.strip()]
        recs = [r.get("record", r) for r in recs]
        if "--trim-map" in flags:
            def trim(rec):
                y0 = rec["obs.mapY"]
                if y0 < 0: return rec
                keep = [i for i, y in enumerate(rec["obs.map.ys"]) if y >= y0]
                return {**rec, **{k: [rec[k][i] for i in keep]
                                  for k in ("obs.map.xs", "obs.map.ys", "obs.map.roomTypes", "obs.map.pathXs")}}
            recs = [trim(r) for r in recs]
        net.eval()
        with open(out_path, "w") as out, torch.no_grad():
            for rec in recs:
                b = network.collate_fn([{**rec, "chosen_idx": 0, "outcome": 0.0}])
                b["extra"] = extra_batch([{"record": rec}])
                logits, value = net(b)
                n = len(rec["cards_offered.cards"]) + len(rec["relics_offered"]) + len(rec["potions_offered"]) \
                    + len(rec["fixed_actions"]) + len(rec["paths_offered"])
                lg = logits[0][torch.isfinite(logits[0])].tolist()
                assert len(lg) == n
                out.write(json.dumps({"logits": lg, "value": float(value[0])}) + "\n")
    else:
        sys.exit(f"unknown command {cmd}")


if __name__ == "__main__":
    main()
