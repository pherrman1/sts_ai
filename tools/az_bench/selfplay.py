#!/usr/bin/env python3
"""Stage 1 of the Amber-Eye-style self-play loop (2026-11-17): train AmberNet from scratch by self-play on whole A20
Ironclad runs, on one machine with one GPU.

C++ worker threads (az_bench_native.RunDriver, apps/az_bench/az_run_driver.h) play --games runs each with a Gumbel
AlphaZero search per decision; every leaf is a request. One inference thread takes flat batches, runs the inference
copy of the net (fp16, the stage 0 kernels: --varlen-attn / --fused-layer / --pack-step) and posts the policy logits,
F = E[final floor] / 57 and E[HP at the end of the floor] back. Finished runs hand their searched positions back as
samples (improved policy on full moves, final outcome, HP at the end of the floor); they go into a replay window. One
training thread samples minibatches from the window and trains the fp32 copy (bf16 autocast) with
  policy cross-entropy to the improved policy (full-move samples) + outcome cross-entropy (win / death floor, 57
  classes) + HP cross-entropy (256 classes),
keeping trained samples <= --replay-ratio x generated samples, and copies its weights into the inference net every
--sync-steps steps.

--utility amber (2026-11-17, default floor-hp): Amber Eye's early H = 1/56 [(floor - 1) + sum_{f >= floor} E[HP_f] / 255]
instead of H = E[HP at the end of the floor] / max HP (apps/az_bench/az_run_driver.h, Utility). The net gets a 56-scalar
per-floor HP head (E[HP_f] / 255), trained by masked MSE (--w-hp-floor) on the HP at the end of every floor from the
sample's floor on (0 after a death); a keyless act 3 victory keeps its HP. --keyless-hp fixes only that last point for
the default utility. --init-net CKPT starts a new run from a checkpoint's weights (heads of another shape, e.g. the
1-scalar per-floor head, start fresh; new optimizer and counters).

--value-ema-halflife H > 0 (2026-11-17, default 0 = off: the outcome label is the final outcome) replaces the outcome
target by an exponentially weighted average along the run, as Amber Eye's "combination of the search result and an
exponential weighted average of future moves' search outcomes": with lam = 0.5 ** (1 / H) and the run's kept samples
t = 0 .. n-1 in move order, target_n = one_hot(final outcome) and target_t = (1 - lam) * D_t + lam * target_{t+1},
where D_t is the net's outcome distribution at sample t, evaluated once by the training net when the finished run
enters the replay window. The final outcome keeps weight lam ** (n - t); H counts kept samples (full moves with the
default --keep-*). Differences from Amber Eye: D_t is the net's prediction at the searched position, not a
search-backed distribution (the search backs up a scalar utility only), and the HP head keeps its end-of-floor label.
The logged "outcome" loss is always the cross-entropy to the final outcome (comparable across settings);
"outcome_ema" is the trained loss against the EMA target.

From https://8e9f.github.io/amber_eye/: one net, Gumbel AlphaZero 64 / 16 positions per full / fast move with playout
cap randomization 0.25, utility F + H first, the 0.44M net first, no teacher. Our choices: the loss weights, the
optimizer (AdamW), the window, the replay ratio, the sync interval (all flags).

Writes to --out-dir: metrics.jsonl (one line per --report seconds), status.json (latest line), checkpoints
ckpt_<step>.pt (net, optimizer, counters) every --ckpt-minutes and at the end. A file STOP in --out-dir stops the
run cleanly. --resume CKPT continues from a checkpoint (seeds continue after the checkpoint's last started run).

usage: selfplay.py --module-dir BUILD_DIR --out-dir DIR --seed-base N [--hours 24] [--max-runs N] [...]
"""

import argparse
import copy
import importlib.util
import json
import math
import os
import sys
import threading
import time

import numpy as np
import torch
import torch.nn.functional as F

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_spec = importlib.util.spec_from_file_location("amber_net", os.path.join(ROOT, "tools", "az_bench", "amber_net.py"))
amber_net = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(amber_net)

N_CAT, N_FLOAT, N_ACT_FEAT = amber_net.N_CAT, amber_net.N_FLOAT, amber_net.N_ACT_FEAT
OUTCOME_CLASSES, HP_CLASSES = amber_net.OUTCOME_CLASSES, amber_net.HP_CLASSES
TAKE_CHUNK = 1 << 16   # samples per take_samples call (the driver completes the last run; tests lower it)


# --- replay window -------------------------------------------------------------------------------------------------

class Replay:
    """FIFO window of ragged samples: token / action rings plus per-sample metadata. Old samples are evicted when
    the sample, token or action capacity would overflow. Thread-safe (one lock)."""

    def __init__(self, samples, tokens_per_sample=48, actions_per_sample=12, hp_floors=0, soft_outcome=False):
        self.cs = samples
        self.ct = samples * tokens_per_sample
        self.ca = samples * actions_per_sample
        self.tok_type = np.zeros(self.ct, np.int8)
        self.ids = np.zeros((self.ct, N_CAT), np.int16)
        self.f = np.zeros((self.ct, N_FLOAT), np.float16)
        self.a_type = np.zeros(self.ca, np.int16)
        self.a_src = np.zeros(self.ca, np.int16)
        self.a_tgt = np.zeros(self.ca, np.int16)
        self.a_f = np.zeros((self.ca, N_ACT_FEAT), np.float16)
        self.policy = np.zeros(self.ca, np.float32)
        self.tok_start = np.zeros(self.cs, np.int64)
        self.ntok = np.zeros(self.cs, np.int32)
        self.act_start = np.zeros(self.cs, np.int64)
        self.nact = np.zeros(self.cs, np.int32)
        self.meta = {k: np.zeros(self.cs, dt) for k, dt in
                     (("outcome", np.int16), ("hp_end", np.int16), ("max_hp", np.int16), ("floor", np.int16),
                      ("combat", np.uint8), ("has_policy", np.uint8), ("search_value", np.float32))}
        if hp_floors:   # utility amber: per-floor HP labels [S, 56] (-1 = masked)
            self.meta["hp_floor"] = np.zeros((self.cs, hp_floors), np.int16)
        # EMA outcome targets (--value-ema-halflife): one distribution per sample, written by set_soft_outcome.
        self.soft_outcome = np.zeros((self.cs, OUTCOME_CLASSES), np.float16) if soft_outcome else None
        self.s_head = self.s_tail = 0     # absolute sample counters
        self.t_head = self.a_head = 0     # absolute token / action counters
        self.added = 0
        self.lock = threading.Lock()

    def __len__(self):
        return self.s_head - self.s_tail

    @staticmethod
    def _put(ring, start, values):
        n, cap = len(values), len(ring)
        i = start % cap
        k = min(n, cap - i)
        ring[i:i + k] = values[:k]
        if k < n:
            ring[:n - k] = values[k:]

    def add(self, s):
        S = len(s["outcome"])
        nt = np.diff(s["tok_off"]).astype(np.int32)
        na = np.diff(s["act_off"]).astype(np.int32)
        if nt.sum() > self.ct or na.sum() > self.ca or S > self.cs:
            raise ValueError("replay: one take_samples chunk larger than the window")
        with self.lock:
            t0, a0 = self.t_head, self.a_head
            for ring, key in ((self.tok_type, "tok_type"), (self.ids, "ids"), (self.f, "f")):
                self._put(ring, t0, s[key])
            for ring, key in ((self.a_type, "a_type"), (self.a_src, "a_src"), (self.a_tgt, "a_tgt"),
                              (self.a_f, "a_f"), (self.policy, "policy")):
                self._put(ring, a0, s[key])
            self.t_head += int(nt.sum())
            self.a_head += int(na.sum())
            self._put(self.tok_start, self.s_head, t0 + s["tok_off"][:-1])
            self._put(self.ntok, self.s_head, nt)
            self._put(self.act_start, self.s_head, a0 + s["act_off"][:-1])
            self._put(self.nact, self.s_head, na)
            for k, ring in self.meta.items():
                self._put(ring, self.s_head, s[k])
            first = self.s_head
            if self.soft_outcome is not None:   # until set_soft_outcome: the final outcome
                oh = np.zeros((S, OUTCOME_CLASSES), np.float16)
                oh[np.arange(S), np.asarray(s["outcome"]).astype(np.int64).clip(0, OUTCOME_CLASSES - 1)] = 1
                self._put(self.soft_outcome, first, oh)
            self.s_head += S
            self.added += S
            # Evict the oldest samples whose rows were overwritten (or that exceed the sample capacity).
            while self.s_head - self.s_tail > self.cs or (
                    self.s_tail < self.s_head and (self.tok_start[self.s_tail % self.cs] < self.t_head - self.ct
                                                   or self.act_start[self.s_tail % self.cs] < self.a_head - self.ca)):
                self.s_tail += 1
        return first

    def set_soft_outcome(self, first, targets):
        """Stores the EMA outcome targets of the samples first .. first + len(targets) - 1 (absolute counters, as
        add returned); samples already evicted are skipped."""
        with self.lock:
            lo = max(first, self.s_tail)
            if lo < first + len(targets):
                self._put(self.soft_outcome, lo, np.asarray(targets[lo - first:], np.float16))

    def rows(self, first, n):
        """The samples first .. first + n - 1 (absolute counters, all live) as one batch in forward_flat's layout."""
        with self.lock:
            if first < self.s_tail or first + n > self.s_head:
                raise ValueError("replay.rows: samples not in the window")
            return self._gather((first + np.arange(n)) % self.cs)

    def sample(self, rng, B, policy_frac=0.0):
        """A training batch in forward_flat's layout (numpy), B rows drawn uniformly from the window. policy_frac > 0
        draws at least that share of rows among samples with a policy target (rejection on the uniform draw)."""
        with self.lock:
            n = len(self)
            j = (self.s_tail + rng.integers(0, n, B)) % self.cs
            if policy_frac > 0:
                hp = self.meta["has_policy"][j].astype(bool)
                need = int(policy_frac * B) - int(hp.sum())
                for _ in range(8):
                    if need <= 0:
                        break
                    cand = (self.s_tail + rng.integers(0, n, 4 * B)) % self.cs
                    cand = cand[self.meta["has_policy"][cand] == 1][:need]
                    repl = np.flatnonzero(~hp)[:len(cand)]
                    j[repl] = cand
                    hp[repl] = True
                    need -= len(cand)
            return self._gather(j)

    def _gather(self, j):
        """Rows j (ring positions) in forward_flat's layout; the caller holds the lock."""
        B = len(j)
        nt, na = self.ntok[j], self.nact[j]
        T, A = int(nt.max()), int(na.max())
        T = -(-T // 8) * 8
        A = -(-A // 8) * 8
        rows_t = np.repeat(np.arange(B), nt)
        cols_t = np.arange(int(nt.sum())) - np.repeat(np.cumsum(nt) - nt, nt)
        src_t = (np.repeat(self.tok_start[j], nt) + cols_t) % self.ct
        rows_a = np.repeat(np.arange(B), na)
        cols_a = np.arange(int(na.sum())) - np.repeat(np.cumsum(na) - na, na)
        src_a = (np.repeat(self.act_start[j], na) + cols_a) % self.ca
        b = {"tok_type": np.zeros((B, T), np.int64), "ids": np.zeros((B, T, N_CAT), np.int64),
             "f": np.zeros((B, T, N_FLOAT), np.float16), "mask": np.zeros((B, T), bool),
             "a_type": np.zeros((B, A), np.int64), "a_src": np.full((B, A), -1, np.int64),
             "a_tgt": np.full((B, A), -1, np.int64), "a_f": np.zeros((B, A, N_ACT_FEAT), np.float16),
             "a_mask": np.zeros((B, A), bool), "policy": np.zeros((B, A), np.float32)}
        b["tok_type"][rows_t, cols_t] = self.tok_type[src_t]
        b["ids"][rows_t, cols_t] = self.ids[src_t]
        b["f"][rows_t, cols_t] = self.f[src_t]
        b["mask"][rows_t, cols_t] = True
        b["a_type"][rows_a, cols_a] = self.a_type[src_a]
        b["a_src"][rows_a, cols_a] = self.a_src[src_a]
        b["a_tgt"][rows_a, cols_a] = self.a_tgt[src_a]
        b["a_f"][rows_a, cols_a] = self.a_f[src_a]
        b["a_mask"][rows_a, cols_a] = True
        b["policy"][rows_a, cols_a] = self.policy[src_a]
        for k, ring in self.meta.items():
            b[k] = ring[j].copy()
        if self.soft_outcome is not None:
            b["soft_outcome"] = self.soft_outcome[j].astype(np.float32)
        return b


def ema_outcome_targets(dist, outcome, run, lam):
    """EMA outcome targets of whole runs (see --value-ema-halflife): dist [S, C] the net's outcome distributions,
    outcome [S] the final outcome class, run [S] the run id; each run's samples are contiguous and in move order.
    target_t = (1 - lam) * dist_t + lam * target_{t+1}, with one_hot(outcome) after a run's last sample. Returns
    (targets [S, C] float32, weight of the final outcome per sample [S])."""
    dist = np.asarray(dist, np.float32)
    S, C = dist.shape
    run = np.asarray(run)
    outcome = np.asarray(outcome).astype(np.int64).clip(0, C - 1)
    if S == 0:
        return dist.copy(), np.zeros(0, np.float32)
    starts = np.flatnonzero(np.concatenate([[True], run[1:] != run[:-1]]))
    if len(np.unique(run[starts])) != len(starts):
        raise ValueError("ema_outcome_targets: a run's samples are not contiguous")
    ends = np.append(starts[1:], S)                      # exclusive end of each sample's run
    end_of = np.repeat(ends, np.diff(np.append(starts, S)))
    back = end_of - 1 - np.arange(S)                     # samples after this one in its run
    out = np.empty_like(dist)
    nxt = np.zeros((S, C), np.float32)
    nxt[np.arange(S), outcome] = 1.0                     # target after the last sample: the final outcome
    order = np.argsort(back, kind="stable")
    bounds = np.searchsorted(back[order], np.arange(back.max() + 2))
    for r in range(back.max() + 1):                      # last samples first, then one step earlier each round
        idx = order[bounds[r]:bounds[r + 1]]
        tail = nxt[idx] if r == 0 else out[idx + 1]
        out[idx] = (1.0 - lam) * dist[idx] + lam * tail
    return out, (lam ** (back + 1)).astype(np.float32)


# --- heads -> search values ----------------------------------------------------------------------------------------

def search_values(outcome_logits, hp_logits):
    """F = E[final floor] / 57 (a win counts 57; class 0 = win, f = death on floor f) and E[HP] from the heads."""
    p = torch.softmax(outcome_logits.float(), -1)
    floors = torch.arange(OUTCOME_CLASSES, device=p.device, dtype=p.dtype)
    floors[0] = 57.0
    Fv = (p * floors).sum(-1) / 57.0
    ph = torch.softmax(hp_logits.float(), -1)
    ehp = (ph * torch.arange(HP_CLASSES, device=ph.device, dtype=ph.dtype)).sum(-1)
    return Fv, ehp


def amber_h(floor, hpf):
    """Amber H (az_run_driver.h amberH) from per-floor predictions hpf [B, 56] = E[HP_f] / 255; reference for tests."""
    fl = floor.clamp(1, 56)
    f = torch.arange(1, 57, device=hpf.device)
    keep = (f[None, :] >= fl[:, None]).to(hpf.dtype)
    return ((fl - 1).to(hpf.dtype) + (hpf.clamp(0, 1) * keep).sum(-1)) / 56.0


def hp_floor_loss(pred, label):
    """Masked MSE of the per-floor HP head (pred [B, 56] ~ HP / 255) against labels [B, 56] (HP, -1 = masked)."""
    m = (label >= 0).float()
    t = label.float().clamp(0, 255) / 255.0
    return (((pred.float() - t) ** 2) * m).sum() / m.sum().clamp(min=1)


def losses(net, b, w_policy, w_outcome, w_hp, w_hp_floor=0.0):
    logits, outcome, hp, hpf = net(b)
    logp = torch.log_softmax(logits.float().masked_fill(~b["a_mask"], -1e4), -1)
    has = b["has_policy"].bool()
    pol = -(b["policy"] * logp).sum(-1)
    l_pol = (pol * has).sum() / has.sum().clamp(min=1)
    l_out = F.cross_entropy(outcome.float(), b["outcome"].long())
    l_hp = F.cross_entropy(hp.float(), b["hp_end"].long().clamp(0, HP_CLASSES - 1))
    parts = {"policy": l_pol.detach(), "outcome": l_out.detach(), "hp": l_hp.detach()}
    if "soft_outcome" in b:   # --value-ema-halflife: train on the EMA target; "outcome" stays the final-outcome CE
        l_ema = -(b["soft_outcome"] * torch.log_softmax(outcome.float(), -1)).sum(-1).mean()
        parts["outcome_ema"] = l_ema.detach()
        l_out = l_ema
    total = w_policy * l_pol + w_outcome * l_out + w_hp * l_hp
    if "hp_floor" in b:
        l_hpf = hp_floor_loss(hpf, b["hp_floor"])
        total = total + w_hp_floor * l_hpf
        parts["hp_floor"] = l_hpf.detach()
    return total, parts


def to_torch(b, dev):
    out = {}
    for k, v in b.items():
        t = torch.from_numpy(v)
        if t.dtype == torch.float16:
            t = t.float()
        out[k] = t.to(dev, non_blocking=True)
    return out


# --- main ----------------------------------------------------------------------------------------------------------


def progress_window(s, last_s):
    """Run progress counters (keys, campfire choices, elites, Act 4, Heart) of the runs finished since last_s, per
    ascension that finished runs: {"A": {"runs": n, "ruby": .., ...}} (driver stats() progress_asc deltas)."""
    out = {}
    cur, prev = s.get("progress_asc") or {}, last_s.get("progress_asc") or {}
    for a, (n1, n0) in enumerate(zip(s["runs_done_asc"], last_s["runs_done_asc"])):
        if n1 - n0 <= 0:
            continue
        e = {"runs": n1 - n0}
        for k, v in cur.items():
            e[k] = v[a] - (prev.get(k) or [0] * len(v))[a]
        out[str(a)] = e
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--module-dir", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--seed-base", type=int, required=True, help="first run seed (runs use consecutive seeds)")
    ap.add_argument("--max-runs", type=int, default=-1)
    ap.add_argument("--hours", type=float, default=24.0)
    ap.add_argument("--net", default="0.44M")
    ap.add_argument("--ascension", type=int, default=20, help="ascension of the runs (curriculum: the starting one)")
    ap.add_argument("--curriculum", action="store_true",
                    help="raise the ascension by one once the Heart-kill rate at the current one reaches "
                         "--curriculum-winrate over its last --curriculum-runs finished runs (up to 20)")
    ap.add_argument("--curriculum-winrate", type=float, default=0.10)
    ap.add_argument("--curriculum-runs", type=int, default=10000)
    ap.add_argument("--workers", type=int, default=11)
    ap.add_argument("--games", type=int, default=700, help="runs in flight per worker")
    ap.add_argument("--full-sims", type=int, default=64)
    ap.add_argument("--fast-sims", type=int, default=16)
    ap.add_argument("--full-prob", type=float, default=0.25)
    ap.add_argument("--hp-weight-combat", type=float, default=1.0)
    ap.add_argument("--hp-weight-ooc", type=float, default=1.0)
    ap.add_argument("--utility", choices=("floor-hp", "amber"), default="floor-hp",
                    help="H of the search: floor-hp = E[HP end of floor] / max HP; amber = Amber Eye's per-floor H")
    ap.add_argument("--keyless-hp", action="store_true",
                    help="floor-hp: a keyless act 3 victory keeps H = HP / max HP (amber always does)")
    ap.add_argument("--w-hp-floor", type=float, default=1.0, help="loss weight of the per-floor HP head (amber)")
    ap.add_argument("--init-net", help="start from this checkpoint's weights (mismatched heads fresh; new counters)")
    ap.add_argument("--keep-full", type=float, default=1.0, help="keep probability of a full-search position")
    ap.add_argument("--keep-fast", type=float, default=0.0, help="keep probability of a fast-search position")
    ap.add_argument("--max-fight-moves", type=int, default=400)
    ap.add_argument("--max-pending", type=int, default=300000,
                    help="samples of unfinished runs held for their labels; above it keep probabilities shrink")
    ap.add_argument("--explore-c", type=float, default=0.0, help="pick-rate exploration strength (0 = off)")
    ap.add_argument("--pick-target", type=float, default=0.01, help="pick-rate target per item and run")
    ap.add_argument("--c-visit", type=float, default=50.0, help="Gumbel sigma: (c_visit + max N) * c_scale")
    ap.add_argument("--c-scale", type=float, default=1.0, help="Gumbel sigma scale (mctx uses 0.1 with --q-rescale)")
    ap.add_argument("--no-fast-noise", action="store_true", help="no Gumbel noise on fast moves (Amber Eye)")
    ap.add_argument("--q-rescale", action="store_true",
                    help="completed Q as in Gumbel MuZero: mixed value for unvisited edges, min-max rescale per node")
    ap.add_argument("--batch", type=int, default=2048)
    ap.add_argument("--row-buckets", default="2048", help="batch rows padded to these (one size keeps compiled shapes few)")
    ap.add_argument("--tok-buckets", default="32,40,48,56,64,80,96,128,212")
    ap.add_argument("--act-buckets", default="16,32,64,96")
    ap.add_argument("--pack-step", type=int, default=2048)
    ap.add_argument("--pack-threads", type=int, default=4)
    ap.add_argument("--fused-layer", action="store_true", help="inference: stage 0's three-kernel layers (d <= 128)")
    ap.add_argument("--compile", action="store_true", help="inference: torch.compile")
    ap.add_argument("--window", type=int, default=500000, help="replay window (samples)")
    ap.add_argument("--min-replay", type=int, default=20000, help="samples before training starts")
    ap.add_argument("--train-batch", type=int, default=1024)
    ap.add_argument("--replay-ratio", type=float, default=2.0, help="max trained / generated samples")
    ap.add_argument("--policy-frac", type=float, default=0.0, help="min share of policy rows per train batch")
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--weight-decay", type=float, default=1e-4)
    ap.add_argument("--warmup-steps", type=int, default=500)
    ap.add_argument("--w-policy", type=float, default=1.0)
    ap.add_argument("--w-outcome", type=float, default=1.0)
    ap.add_argument("--w-hp", type=float, default=1.0)
    ap.add_argument("--value-ema-halflife", type=float, default=0.0,
                    help="EMA outcome labels: half-life in kept samples of a run (0 = off: final outcome)")
    ap.add_argument("--sync-steps", type=int, default=50, help="copy trained weights to the inference net every N steps")
    ap.add_argument("--report", type=float, default=30.0)
    ap.add_argument("--ckpt-minutes", type=float, default=30.0)
    ap.add_argument("--resume")
    ap.add_argument("--seed", type=int, default=0, help="weight init / search / sampling seed (not a run seed)")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--test-max-hp", type=int, default=0, help="tests only")
    args = ap.parse_args(argv)
    if args.init_net and args.resume:
        ap.error("--init-net and --resume exclude each other")
    amber = args.utility == "amber"
    hp_floors = 56 if amber else 1

    sys.path.insert(0, args.module_dir)
    import az_bench_native  # noqa: E402

    os.makedirs(args.out_dir, exist_ok=True)
    dev = torch.device(args.device)
    cuda = dev.type == "cuda"
    torch.manual_seed(args.seed)
    d, layers = amber_net.SIZES.get(args.net) or tuple(int(x) for x in args.net.split("x")[:2])
    train_net = amber_net.AmberNet(d=d, layers=layers, hp_floors=hp_floors).to(dev)
    train_net.sdpa = True
    opt = torch.optim.AdamW(train_net.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    counters = {"step": 0, "trained": 0, "seeds_used": 0, "runs_done": 0, "wall": 0.0}
    if args.resume:
        ck = torch.load(args.resume, map_location=dev)
        train_net.load_state_dict(ck["net"])
        opt.load_state_dict(ck["opt"])
        counters.update(ck["counters"])
    if args.init_net:
        src = torch.load(args.init_net, map_location=dev)["net"]
        own = train_net.state_dict()
        fresh = [k for k in own if k not in src or src[k].shape != own[k].shape]
        own.update({k: v for k, v in src.items() if k in own and v.shape == own[k].shape})
        train_net.load_state_dict(own)
        print(f"# init-net {args.init_net}: fresh {fresh}", flush=True)
    # A curriculum checkpoint carries its current ascension; otherwise --ascension.
    ascension = counters.get("ascension", args.ascension) if args.curriculum else args.ascension
    counters["ascension"] = ascension
    seeds_used0 = counters["seeds_used"]
    trained0 = counters["trained"]   # the replay window starts empty on resume: the ratio cap counts from here
    seed_base = args.seed_base + seeds_used0
    max_runs = -1 if args.max_runs < 0 else max(0, args.max_runs - counters["seeds_used"])

    # Inference copy: fp16 weights, packed forward with the stage 0 kernels.
    infer = copy.deepcopy(train_net).eval()
    infer.sdpa = True
    if cuda:
        infer.varlen_attn = amber_net.load_kernel("varlen_attn")
        if args.fused_layer:
            infer.fused_layer = amber_net.load_fused_layer()
        infer = infer.half()
    infer_dtype = torch.float16 if cuda else torch.float32
    if args.compile:
        # Static shapes except the packed-token count N (pack_idx), marked dynamic per batch: otherwise every
        # (rows, tokens, actions, N) combination is its own graph and the cache limit is hit within minutes.
        import torch._dynamo as dynamo
        dynamo.config.cache_size_limit = 1024
        dynamo.config.accumulated_cache_size_limit = 4096
        dynamo.config.automatic_dynamic_shapes = False
        run = torch.compile(infer)
    else:
        run = infer

    if args.q_rescale and args.c_scale == 1.0:
        print("warning: --q-rescale with --c-scale 1.0: sigma ~50+ on [0, 1] Q makes the improved policy nearly "
              "argmax (Gumbel MuZero / mctx use --c-scale 0.1)", file=sys.stderr, flush=True)
    drv = az_bench_native.RunDriver(
        workers=args.workers, games=args.games, seed_base=seed_base, max_runs=max_runs, ascension=ascension,
        full_sims=args.full_sims, fast_sims=args.fast_sims, full_prob=args.full_prob,
        hp_weight_combat=args.hp_weight_combat, hp_weight_ooc=args.hp_weight_ooc, keep_full=args.keep_full,
        keep_fast=args.keep_fast, search_seed=args.seed + counters["step"], max_fight_moves=args.max_fight_moves,
        test_max_hp=args.test_max_hp, max_pending=args.max_pending,
        explore_c=args.explore_c, pick_target=args.pick_target, c_visit=args.c_visit, c_scale=args.c_scale,
        fast_noise=not args.no_fast_noise, q_rescale=args.q_rescale, utility=1 if amber else 0,
        keyless_hp=args.keyless_hp)
    ema_lam = 0.5 ** (1.0 / args.value_ema_halflife) if args.value_ema_halflife > 0 else 0.0
    replay = Replay(args.window, hp_floors=56 if amber else 0, soft_outcome=ema_lam > 0)
    ema_stats = {"samples": 0, "real_weight": 0.0}   # mean weight of the final outcome in the EMA targets
    stop = threading.Event()
    errors = []
    weights_lock = threading.Lock()
    new_weights = [None]          # (state tensors on the GPU, event) published by the trainer
    loss_keys = (("policy", "outcome", "hp") + (("hp_floor",) if amber else ())
                 + (("outcome_ema",) if ema_lam > 0 else ()))
    lossbox = dict({"n": 0}, **{k: 0.0 for k in loss_keys})
    lossbox_lock = threading.Lock()
    infer_stats = {"batches": 0, "rows": 0, "syncs": 0}

    row_b = [int(v) for v in args.row_buckets.split(",") if int(v) <= args.batch] or [args.batch]
    if row_b[-1] < args.batch:
        row_b.append(args.batch)
    tok_b = [int(v) for v in args.tok_buckets.split(",")]
    act_b = [int(v) for v in args.act_buckets.split(",")]
    min_rows = max(1, min(args.batch, args.workers * args.games) // 2)

    def guarded(fn):
        def wrap():
            try:
                fn()
            except BaseException as e:
                errors.append(f"{fn.__name__}: {e!r}")
                stop.set()
                raise
        return wrap

    # ---- inference: two-deep pipeline as stage 0's flat_pipe_loop ----
    def inference_loop():
        stream = torch.cuda.Stream(dev) if cuda else None
        R, T, A = row_b[-1], tok_b[-1], act_b[-1]

        def buffers():
            h = {"tok_type": torch.zeros(R * T, dtype=torch.int8, pin_memory=cuda),
                 "ids": torch.zeros(R * T * 4, dtype=torch.int16, pin_memory=cuda),
                 "f": torch.zeros(R * T * 64, dtype=torch.float16, pin_memory=cuda),
                 "mask": torch.zeros(R * T, dtype=torch.bool, pin_memory=cuda),
                 "a_type": torch.zeros(R * A, dtype=torch.int16, pin_memory=cuda),
                 "a_src": torch.zeros(R * A, dtype=torch.int16, pin_memory=cuda),
                 "a_tgt": torch.zeros(R * A, dtype=torch.int16, pin_memory=cuda),
                 "a_f": torch.zeros(R * A * 8, dtype=torch.float16, pin_memory=cuda),
                 "a_mask": torch.zeros(R * A, dtype=torch.bool, pin_memory=cuda),
                 "pack_idx": torch.zeros(R * T, dtype=torch.int32, pin_memory=cuda),
                 "seq_off": torch.zeros(R + 1, dtype=torch.int32, pin_memory=cuda)}
            out = {"logits": torch.zeros(R * A, dtype=torch.float32, pin_memory=cuda),
                   "F": torch.zeros(R, dtype=torch.float32, pin_memory=cuda),
                   "ehp": torch.zeros(R, dtype=torch.float32, pin_memory=cuda)}
            if amber:
                out["hpf"] = torch.zeros(R * 56, dtype=torch.float32, pin_memory=cuda)
            return h, {k: v.numpy() for k, v in h.items()}, out

        sets = [buffers(), buffers()]
        cur, pending = 0, None

        def finish(p):
            ticket, rows, Ap, out, ev = p
            if ev is not None:
                ev.synchronize()
            drv.submit(ticket, out["logits"][:rows * Ap].numpy().reshape(rows, Ap), out["F"][:rows].numpy(),
                       out["ehp"][:rows].numpy(), out["hpf"][:rows * 56].numpy().reshape(rows, 56) if amber else None)

        while not stop.is_set():
            host, views, out = sets[cur]
            got = drv.next_flat(args.batch, min_rows, 5, row_b, tok_b, act_b, views, args.pack_threads)
            launched = None
            if got is not None:
                ticket, rows, Rp, Tp, Ap = got
                ctx = torch.cuda.stream(stream) if stream is not None else torch.no_grad()
                with ctx, torch.inference_mode():
                    with weights_lock:
                        nw = new_weights[0]
                        new_weights[0] = None
                    if nw is not None:   # trainer's weights: copy on this stream after the trainer's copy finished
                        state, ev_w = nw
                        if stream is not None:
                            stream.wait_event(ev_w)
                        for p_i, p_s in zip(infer.parameters(), state):
                            p_i.copy_(p_s)
                            if stream is not None:   # p_s came from the trainer's stream: keep it alive for this copy
                                p_s.record_stream(stream)
                        infer_stats["syncs"] += 1
                    x = {}
                    shapes = {"tok_type": (Rp, Tp), "ids": (Rp, Tp, 4), "f": (Rp, Tp, 64), "mask": (Rp, Tp),
                              "a_type": (Rp, Ap), "a_src": (Rp, Ap), "a_tgt": (Rp, Ap), "a_f": (Rp, Ap, 8),
                              "a_mask": (Rp, Ap)}
                    for k, shp in shapes.items():
                        n = int(np.prod(shp))
                        t = host[k][:n].to(dev, non_blocking=True).view(shp)
                        if k in ("tok_type", "ids", "a_type", "a_src", "a_tgt"):
                            t = t.long()
                        elif t.dtype == torch.float16:
                            t = t.to(infer_dtype)
                        x[k] = t
                    if args.pack_step:
                        M = Rp * Tp
                        live = np.flatnonzero(views["mask"][:M])
                        nl = live.size
                        npad = -(-nl // args.pack_step) * args.pack_step
                        views["pack_idx"][:nl] = live
                        views["pack_idx"][nl:npad] = M
                        x["pack_idx"] = host["pack_idx"][:npad].to(dev, non_blocking=True).long()
                        if args.compile:
                            torch._dynamo.mark_dynamic(x["pack_idx"], 0)
                        if infer.varlen_attn is not None:
                            so = views["seq_off"]
                            so[0] = 0
                            np.cumsum(views["mask"][:M].reshape(Rp, Tp).sum(1), out=so[1:Rp + 1])
                            x["seq_off"] = host["seq_off"][:Rp + 1].to(dev, non_blocking=True)
                    lg, outcome, hp, hpf = run(x)
                    Fv, ehp = search_values(outcome[:rows], hp[:rows])
                    out["logits"][:rows * Ap].view(rows, Ap).copy_(lg[:rows].float(), non_blocking=True)
                    out["F"][:rows].copy_(Fv, non_blocking=True)
                    out["ehp"][:rows].copy_(ehp, non_blocking=True)
                    if amber:
                        out["hpf"][:rows * 56].view(rows, 56).copy_(hpf[:rows].float().clamp(0, 1), non_blocking=True)
                    ev = None
                    if stream is not None:
                        ev = torch.cuda.Event()
                        ev.record(stream)
                launched = (ticket, rows, Ap, out, ev)
                infer_stats["batches"] += 1
                infer_stats["rows"] += rows
            if pending is not None:
                finish(pending)
            pending = launched
            if launched is not None:
                cur ^= 1
        if pending is not None:
            finish(pending)

    # ---- training ----
    def train_loop():
        rng = np.random.default_rng(args.seed + 1)
        stream = torch.cuda.Stream(dev) if cuda else None
        amp = torch.autocast(dev.type, dtype=torch.bfloat16, enabled=cuda)
        train_net.train()
        last_run = [-1]
        while not stop.is_set():
            ch = drv.take_samples(TAKE_CHUNK)   # whole runs only
            if ch is not None:
                first = replay.add(ch)
                if ema_lam > 0:
                    if len(ch["run"]) and int(ch["run"][0]) == last_run[0]:
                        raise RuntimeError("take_samples split a run across chunks")
                    last_run[0] = int(ch["run"][-1]) if len(ch["run"]) else last_run[0]
                    S = len(ch["outcome"])
                    dist = np.empty((S, OUTCOME_CLASSES), np.float32)
                    train_net.eval()
                    ctx = torch.cuda.stream(stream) if stream is not None else torch.no_grad()
                    with ctx, torch.no_grad(), amp:
                        for i in range(0, S, args.train_batch):
                            k = min(args.train_batch, S - i)
                            _, o, _, _ = train_net(to_torch(replay.rows(first + i, k), dev))
                            dist[i:i + k] = torch.softmax(o.float(), -1).cpu().numpy()
                    train_net.train()
                    tgt, real_w = ema_outcome_targets(dist, ch["outcome"], ch["run"], ema_lam)
                    replay.set_soft_outcome(first, tgt)
                    ema_stats["samples"] += S
                    ema_stats["real_weight"] += float(real_w.sum())
            if len(replay) < args.min_replay or counters["trained"] - trained0 >= args.replay_ratio * replay.added:
                time.sleep(0.02)
                continue
            b = replay.sample(rng, args.train_batch, args.policy_frac)
            ctx = torch.cuda.stream(stream) if stream is not None else torch.no_grad()
            with ctx:
                bt = to_torch(b, dev)
                step = counters["step"]
                lr = args.lr * min(1.0, (step + 1) / max(1, args.warmup_steps))
                for g in opt.param_groups:
                    g["lr"] = lr
                with torch.enable_grad(), amp:
                    loss, parts = losses(train_net, bt, args.w_policy, args.w_outcome, args.w_hp, args.w_hp_floor)
                opt.zero_grad(set_to_none=True)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(train_net.parameters(), 1.0)
                opt.step()
                counters["step"] += 1
                counters["trained"] += args.train_batch
                with lossbox_lock:
                    lossbox["n"] += 1
                    for k, v in parts.items():
                        lossbox[k] += float(v)
                if counters["step"] % args.sync_steps == 0:
                    with torch.no_grad():
                        state = [p.detach().to(infer_dtype).clone() for p in train_net.parameters()]
                    ev = None
                    if stream is not None:
                        ev = torch.cuda.Event()
                        ev.record(stream)
                    with weights_lock:
                        new_weights[0] = (state, ev)

    def save_ckpt(tag, s, now):
        # Runs in flight are dropped on resume; their seeds are not reused.
        c = dict(counters, seeds_used=seeds_used0 + s["runs_started"], runs_done=counters["runs_done"] + s["runs_done"],
                 wall=wall0 + now - t_start)
        path = os.path.join(args.out_dir, f"ckpt_{tag}.pt")
        if args.resume and os.path.abspath(path) == os.path.abspath(args.resume):
            path = os.path.join(args.out_dir, f"ckpt_{tag}_r{c['runs_done']}.pt")   # never overwrite the resume source
        tmp = path + ".tmp"
        torch.save({"net": train_net.state_dict(), "opt": opt.state_dict(), "counters": c,
                    "args": vars(args), "net_size": [d, layers]}, tmp)
        os.replace(tmp, path)
        return path, c

    threads = [threading.Thread(target=guarded(inference_loop), daemon=True),
               threading.Thread(target=guarded(train_loop), daemon=True)]
    for t in threads:
        t.start()
    drv.start()
    t_start = time.time()
    wall0 = counters["wall"]
    last_s, last_t = drv.stats(), time.time()
    last_ckpt = t_start
    last_runs = last_s["runs_done"]
    last_outcomes = np.array(last_s["outcomes"])
    last_floors = last_s["floors_sum"]
    asc_hist = []   # (runs, wins) per report window at the current ascension (curriculum)
    print(f"# selfplay net {args.net} ({sum(p.numel() for p in train_net.parameters())} params) workers {args.workers} "
          f"games {args.games} seed_base {seed_base} out {args.out_dir}", flush=True)
    metrics = open(os.path.join(args.out_dir, "metrics.jsonl"), "a")
    try:
        while not stop.is_set():
            time.sleep(1.0)
            now = time.time()
            s = drv.stats()
            done = (max_runs >= 0 and s["runs_done"] >= max_runs) or now - t_start > args.hours * 3600 \
                or os.path.exists(os.path.join(args.out_dir, "STOP"))
            if now - last_t < args.report and not done:
                continue
            dt = now - last_t
            oc = np.array(s["outcomes"])
            d_oc = oc - last_outcomes
            d_runs = s["runs_done"] - last_runs
            with lossbox_lock:
                n = max(1, lossbox["n"])
                lavg = {k: round(lossbox[k] / n, 4) for k in loss_keys} if lossbox["n"] else None
                lossbox.update(dict({"n": 0}, **{k: 0.0 for k in loss_keys}))
            asc = drv.ascension()
            a_runs = s["runs_done_asc"][asc] - last_s["runs_done_asc"][asc]
            a_wins = s["wins_asc"][asc] - last_s["wins_asc"][asc]
            a_floors = s["floors_sum_asc"][asc] - last_s["floors_sum_asc"][asc]
            asc_hist.append((a_runs, a_wins))
            tot = wins = 0
            for r_, w_ in reversed(asc_hist):
                tot += r_
                wins += w_
                if tot >= args.curriculum_runs:
                    break
            rolling = wins / tot if tot else 0.0
            if args.curriculum and asc < 20 and tot >= args.curriculum_runs and rolling >= args.curriculum_winrate:
                drv.set_ascension(asc + 1)
                counters["ascension"] = asc + 1
                asc_hist = []
                print(f"# curriculum: A{asc} Heart kills {wins}/{tot} -> A{asc + 1}", flush=True)
            row = {
                "time": time.strftime("%Y-%m-%d %H:%M:%S"), "hours": round((wall0 + now - t_start) / 3600, 3),
                "positions_per_s": round((s["evals"] - last_s["evals"]) / dt),
                "moves_per_s": round((s["moves"] - last_s["moves"]) / dt),
                "runs_done": counters["runs_done"] + s["runs_done"],
                "runs_window": d_runs,
                "win_rate_window": round(float(d_oc[0]) / max(1, d_runs), 4),
                "mean_floor_window": round((s["floors_sum"] - last_floors) / max(1, d_runs), 2),
                "wins_total": s["wins"],
                "death_floors_window": {int(k): int(v) for k, v in enumerate(d_oc) if v and k},
                "samples_added": replay.added, "replay": len(replay), "train_steps": counters["step"],
                "trained_samples": counters["trained"], "loss": lavg, "syncs": infer_stats["syncs"],
                "stalls": s["stalls"], "unsupported": s["unsupported"], "knowledge_failures": s["knowledge_failures"], "invalid_actions": s["invalid_actions"], "encode_cut": s["encode_cut"], "encode_cut_ooc": s["encode_cut_ooc"],
                "samples_pending": s["samples_pending"],
                "ascension": asc, "asc_runs_window": a_runs,
                "asc_win_rate_window": round(a_wins / max(1, a_runs), 4),
                "asc_mean_floor_window": round(a_floors / max(1, a_runs), 2),
                "asc_win_rate_rolling": round(rolling, 4), "asc_rolling_runs": tot,
                "ooc_roots": s["ooc_roots"], "explore_roots": s["explore_roots"], "forced_picks": s["forced_picks"],
                # [full, fast] cumulative: searched OOC roots, picks off the best visited mean Q, mean visited-Q spread
                "ooc_searched": list(s["ooc_searched"]), "ooc_not_best_q": list(s["ooc_not_best_q"]),
                "ooc_q_spread_mean": [round(s["ooc_q_spread_sum"][k] / max(1, s["ooc_q_spread_n"][k]), 5) for k in (0, 1)],
                "progress_window": progress_window(s, last_s),
            }
            if ema_lam > 0:
                row["value_ema"] = {"halflife": args.value_ema_halflife, "labelled": ema_stats["samples"],
                                    "real_weight_mean": round(ema_stats["real_weight"] / max(1, ema_stats["samples"]), 4)}
            print(json.dumps(row), flush=True)
            metrics.write(json.dumps(row) + "\n")
            metrics.flush()
            with open(os.path.join(args.out_dir, "status.json.tmp"), "w") as f:
                json.dump(row, f)
            os.replace(os.path.join(args.out_dir, "status.json.tmp"), os.path.join(args.out_dir, "status.json"))
            last_s, last_t, last_runs, last_outcomes, last_floors = s, now, s["runs_done"], oc, s["floors_sum"]
            if now - last_ckpt > args.ckpt_minutes * 60:
                save_ckpt(counters["step"], s, now)
                last_ckpt = now
            if done:
                break
    finally:
        stop.set()
        for t in threads:
            t.join(timeout=60)
        drv.stop()
        path, c = save_ckpt(counters["step"], drv.stats(), time.time())
        print(json.dumps({"final_checkpoint": path, "errors": errors, "counters": c}), flush=True)
        metrics.close()
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
