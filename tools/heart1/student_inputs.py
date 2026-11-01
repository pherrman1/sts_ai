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
records.jsonl: heart1 records with "obs.deck.misc" and "obs.act" (STS_OOC_HEART1_TRACE or a capture's records).

v2 inputs (ExtraInputsV2NN, `perturb --v2`): public run state the v1 record leaves out, also zero-initialised and
added after the v1 extras (native: Net with x2_run.proj.weight present):
- x2_run: FixedVecEmbedding of "obs.v2.run_counters" (removals bought, shop removal price; clamped to
  [-1, 999]; missing = all -1) on the fixed-observation token;
- x2_fought: Embedding(80) summed over "obs.v2.fought" (encounters already fought this act) on that token;
- x2_price: FixedVecEmbedding of "offer_prices" (shop price per offered card/relic/potion token, clamped to
  [-1, 999]; missing = -1) on the card, relic and potion choice tokens."""
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
RUN_COUNTERS, FOUGHT_ROWS, MAX_FOUGHT = 2, 80, 32
CARD_CHOICES, RELIC_CHOICES = network.MAX_DECK_SIZE, 3   # silverbot collate_fn choice layout: cards, relics, potions, ...


def zero_fixed_vec(dim, n=1):
    e = FixedVecEmbedding(dim, [2 * LIMIT + 1] * n)
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


def extra_batch_v2(rows):
    """v2 tensors: run counters, fought encounters (padded with -1) and per-choice offer prices."""
    n = len(rows)
    run = torch.full((n, RUN_COUNTERS), -1.0); fought = torch.full((n, MAX_FOUGHT), -1, dtype=torch.long)
    nchoice = CARD_CHOICES + RELIC_CHOICES + POTIONS
    price = torch.full((n, nchoice, 1), -1.0)
    for i, r in enumerate(rows):
        rec = r["record"]
        c = rec.get("obs.v2.run_counters") or []
        if c: run[i, :len(c)] = torch.tensor(c, dtype=torch.float32).clamp(-1, LIMIT)
        f = (rec.get("obs.v2.fought") or [])[:MAX_FOUGHT]
        if f: fought[i, :len(f)] = torch.tensor(f, dtype=torch.long)
        pr = rec.get("offer_prices") or []
        nc, nr = len(rec["cards_offered.cards"]), len(rec["relics_offered"])
        slots = list(range(nc)) + [CARD_CHOICES + k for k in range(nr)] \
            + [CARD_CHOICES + RELIC_CHOICES + k for k in range(len(rec["potions_offered"]))]
        for j, s in enumerate(slots):
            if j < len(pr): price[i, s, 0] = float(min(max(pr[j], -1), LIMIT))
    return {"run": run, "fought": fought, "price": price}


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


class ExtraInputsV2NN(ExtraInputsNN):
    """ExtraInputsNN plus the v2 inputs; a v1 checkpoint loads into it with bit-identical logits."""
    def __init__(self, H):
        super().__init__(H)
        self.x2_run = zero_fixed_vec(H.dim, RUN_COUNTERS)
        self.x2_price = zero_fixed_vec(H.dim)
        self.x2_fought = nn.Embedding(FOUGHT_ROWS, H.dim)
        nn.init.zeros_(self.x2_fought.weight)

    def forward(self, batch: dict):
        ex, v2 = batch["extra"], batch["extra_v2"]
        obs_embed, obs_mask = self.obs_embed(batch)
        choice_embed, choice_mask = self.choice_embed(batch["choices"])
        obs_embed = obs_embed.clone()
        obs_embed[:, :DECK] = obs_embed[:, :DECK] + self.x_deck_misc(ex["deck_misc"])
        obs_embed[:, DECK:DECK + RELICS] = obs_embed[:, DECK:DECK + RELICS] + self.x_relic_counter(ex["relic_counter"])
        fought = v2["fought"]
        fsum = (self.x2_fought(fought.clamp(min=0)) * (fought >= 0).unsqueeze(-1)).sum(1)
        obs_embed[:, FIXED_TOKEN] = obs_embed[:, FIXED_TOKEN] + self.x_act(ex["act"]) + self.x2_run(v2["run"]) + fsum
        choice_embed = choice_embed.clone()
        k = v2["price"].shape[1]
        on = (v2["price"][..., 0] >= 0).unsqueeze(-1)
        choice_embed[:, :k] = choice_embed[:, :k] + self.x2_price(v2["price"]) * on
        return self._trunk(obs_embed, obs_mask, choice_embed, choice_mask)

    def _trunk(self, obs_embed, obs_mask, choice_embed, choice_mask):
        x = torch.cat([obs_embed, choice_embed], dim=1)
        pos_mask = torch.cat([obs_mask, choice_mask], dim=1)
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
    v2 = "--v2" in rest
    rest = [a for a in rest if a != "--v2"]
    state = torch.load(ckpt, map_location="cpu")
    v2 = v2 or any(k.startswith("x2_") for k in state)
    net = (ExtraInputsV2NN if v2 else ExtraInputsNN)(_hp(state))
    missing, unexpected = net.load_state_dict(state, strict=False)
    assert not unexpected and all(k.startswith("x_") or k.startswith("x2_") for k in missing), (missing, unexpected)
    if cmd == "perturb":
        g = torch.Generator().manual_seed(1)
        with torch.no_grad():
            for name, p in net.named_parameters():
                if name.startswith("x_") or name.startswith("x2_"): p.copy_(0.05 * torch.randn(p.shape, generator=g))
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
                if v2: b["extra_v2"] = extra_batch_v2([{"record": rec}])
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
