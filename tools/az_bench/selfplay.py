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

--w-soft-policy W > 0 (2026-11-17, default 0 = no head) adds Amber Eye's soft policy head ("Labels", adapted from
KataGo): a second action MLP on the same action vectors e_a, trained in training mode only on the policy target p
raised to 1/4 and renormalised over the legal actions (full-move samples), with loss weight W (KataGo: 8). Inference
never computes it. --init-net from a checkpoint without the head starts the head fresh.

--explore-amber (2026-11-17, default off; not with --explore-c) is Amber Eye's exploration ("Exploration"): an item
(card / option / relic / shop choice) played in fewer than --pick-target of the finished runs is under target; a root
offering one gets a full search in which every under-target item stays a candidate through every halving; after the
search each under-target item (random order) is played instead with probability min(1, c exp(-m / T)), T =
--explore-temp (4), m its gap below the search's pick in policy logits (the net's prior logits; the page: "in terms
of policy logits"), c per item by bisection over all finished runs
so that it would have been played in --pick-target of them (az_run_driver.h RunConfig::exploreAmber, amberExploreC).
Choices where the page is silent (Philipp 2026-11-17): no separate bias, rate counted once per run, all item classes,
samples keep the search policy. Like --explore-c, the counts live in the process (not restored on --resume).

--value-ema-search (2026-11-17, default off; needs --value-ema-halflife H) makes D_t search-backed, as Amber Eye: the
search backs up the outcome distribution alongside the scalar utility (RunConfig::searchEmaLambda in
apps/az_bench/az_run_driver.h). A searched move's search result is the root's mean distribution over the root
evaluation and every simulation's leaf (the net's outcome softmax; one-hot at a run-ending leaf), the same mean as the
scalar search value: a mean over the tree's leaves, not the value of the move played. The driver runs the EMA when
the run ends along the chain's moves: --value-ema-moves full (default) = the run's full-search moves only (Amber Eye
trains on and stores targets / value distributions for full moves only; H counts full moves), all = every searched
move, full and fast (H counts searched moves, ~4x as many at --full-prob 0.25). Kept or not does not matter; a kept
fast move under "full" takes the next full move's target. No extra forward pass of the training net. The HP heads keep
their labels. Selection is unchanged.

From https://8e9f.github.io/amber_eye/: one net, Gumbel AlphaZero 64 / 16 positions per full / fast move with playout
cap randomization 0.25, utility F + H first, the 0.44M net first, no teacher. Our choices: the loss weights, the
optimizer (AdamW), the window, the replay ratio, the sync interval (all flags).

Writes to --out-dir: metrics.jsonl (one line per --report seconds), status.json (latest line), checkpoints
ckpt_<step>.pt (net, optimizer, counters) every --ckpt-minutes and at the end. A file STOP in --out-dir stops the
run cleanly; with --savescum a file SAVESCUM_OFF there turns savescum off (every run from its next searched move; recorded in
the checkpoint counters, so a --resume stays off; savescum samples stay in the replay window until evicted). --resume CKPT continues from a checkpoint (seeds continue after the checkpoint's last started run).

usage: selfplay.py --module-dir BUILD_DIR --out-dir DIR --seed-base N [--hours 24] [--max-runs N] [...]
"""

import argparse
import collections
import contextlib
import copy
import gzip
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
    the sample, token or action capacity would overflow. Thread-safe (one lock).

    compact=True (--compact-samples; Amber Eye: "keeping a common dictionary of tokens which are referenced by index
    in replay buffer states. Most tokens, especially cards and relics, are shared between many different states"):
    one dictionary of distinct tokens for the whole window (token_store, the native TokenStore class: slots with
    reference counts, dict_tokens_per_sample slots per window sample) and an index ring (tokens_per_sample int32 per
    sample) holding each sample's tokens as dictionary slots. An evicted sample releases its references; a token no
    live sample uses frees its slot. When a chunk needs more free slots than there are, the oldest samples are
    evicted first. Batches are the same as without it (the slots are resolved in _gather).

    compress_targets=True (with compact; --compress-targets; Amber Eye: "The value distributions were quantized to an
    8-bit fixed-point format [...]. Only the nonzero interval of each value distribution was stored."): the EMA
    outcome targets are kept as round(255 p) in uint8, only from the first to the last nonzero entry, in a byte ring
    (soft_bytes_per_sample per sample of capacity), and read back as q / 255 renormalised to sum 1; the per-floor HP
    labels are kept once per run (they are the same for every sample of a run from its floor on, masked before; a
    ring of hp_runs_per_sample runs per window sample) instead of once per sample (lossless)."""

    def __init__(self, samples, tokens_per_sample=48, actions_per_sample=12, hp_floors=0, soft_outcome=False,
                 compact=False, dict_tokens_per_sample=8, token_store=None, compress_targets=False,
                 soft_bytes_per_sample=64, hp_runs_per_sample=0.125):
        self.cs = samples
        self.compact = compact
        if compress_targets and not compact:
            raise ValueError("replay: compress_targets needs compact")
        self.compress = compress_targets
        self.ci = samples * tokens_per_sample if compact else 0
        self.tok_idx = np.zeros(self.ci, np.int32)   # compact: index ring (dictionary slots)
        self.idx_start = np.zeros(self.cs if compact else 0, np.int64)
        self.i_head = 0
        self.ca = samples * actions_per_sample
        if compact:
            if token_store is None:
                raise ValueError("replay: compact needs token_store (az_bench_native.TokenStore)")
            self.store = token_store(samples * dict_tokens_per_sample)
            self.tok_type, self.ids, self.f = self.store.views()
            self.ct = self.store.capacity
        else:
            self.store = None
            self.ct = samples * tokens_per_sample
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
        self.hp_runs = bool(hp_floors) and compress_targets   # per-run HP labels
        self.soft_q = soft_outcome and compress_targets       # quantized EMA targets
        if hp_floors and not self.hp_runs:   # utility amber: per-floor HP labels [S, 56] (-1 = masked)
            self.meta["hp_floor"] = np.zeros((self.cs, hp_floors), np.int16)
        self.cr = max(1, int(samples * hp_runs_per_sample)) if self.hp_runs else 0
        self.hpr = np.zeros((self.cr, hp_floors if self.hp_runs else 0), np.int16)   # run ring: HP at the end of floor f
        self.hp_ref = np.zeros(self.cs if self.hp_runs else 0, np.int64)            # sample -> its run (absolute)
        self.r_head = 0
        self.cq = samples * soft_bytes_per_sample if self.soft_q else 0
        self.sq = np.zeros(self.cq, np.uint8)                                       # quantized targets, byte ring
        self.sq_start = np.zeros(self.cs if self.soft_q else 0, np.int64)
        self.sq_lo = np.zeros(self.cs if self.soft_q else 0, np.uint8)               # first stored class
        self.sq_len = np.zeros(self.cs if self.soft_q else 0, np.uint8)              # 0: not set yet (final outcome)
        self.q_head = 0
        self.soft_stats = [0, 0]   # (samples, bytes) written by set_soft_outcome, compressed
        # EMA outcome targets (--value-ema-halflife): one distribution per sample, written by set_soft_outcome.
        self.soft_outcome = (np.zeros((self.cs, OUTCOME_CLASSES), np.float16)
                             if soft_outcome and not self.soft_q else None)
        self.s_head = self.s_tail = 0     # absolute sample counters
        self.t_head = self.a_head = 0     # absolute token / action counters
        self.added = 0
        self.lock = threading.Lock()

    def __len__(self):
        return self.s_head - self.s_tail

    def ring_stats(self):
        """Live window: tokens and actions per sample (mean, max) and how full the token / action rings are (share of
        capacity between the oldest live sample and the head; 1.0 = the ring, not --window, decides eviction)."""
        with self.lock:
            n = len(self)
            if n == 0:
                return None
            j = (self.s_tail + np.arange(n)) % self.cs
            nt, na = self.ntok[j], self.nact[j]
            t0 = self.idx_start[j[0]] if self.compact else self.tok_start[j[0]]
            th, tc = (self.i_head, self.ci) if self.compact else (self.t_head, self.ct)
            return {"tok_mean": round(float(nt.mean()), 2), "tok_max": int(nt.max()),
                    "act_mean": round(float(na.mean()), 2), "act_max": int(na.max()),
                    "tok_ring_fill": round(float(th - t0) / tc, 3),
                    "act_ring_fill": round(float(self.a_head - self.act_start[j[0]]) / self.ca, 3)}

    def nbytes(self):
        """Memory of the window's arrays (allocated up front, so the same however full it is)."""
        arrs = [self.a_type, self.a_src, self.a_tgt, self.a_f, self.policy,
                self.tok_start, self.ntok, self.act_start, self.nact, self.tok_idx, self.idx_start,
                self.hpr, self.hp_ref, self.sq, self.sq_start, self.sq_lo, self.sq_len, *self.meta.values()]
        arrs += [] if self.compact else [self.tok_type, self.ids, self.f]
        if self.soft_outcome is not None:
            arrs.append(self.soft_outcome)
        return sum(a.nbytes for a in arrs) + (self.store.nbytes if self.compact else 0)

    @staticmethod
    def _put(ring, start, values):
        n, cap = len(values), len(ring)
        i = start % cap
        k = min(n, cap - i)
        ring[i:i + k] = values[:k]
        if k < n:
            ring[:n - k] = values[k:]

    @staticmethod
    def expand_chunk(s):
        """A compact take_samples chunk ("tok_idx" / "tok_base") with each sample's tokens copied out of the
        dictionaries (the copied layout); other chunks unchanged."""
        if "tok_idx" not in s:
            return s
        nt = np.diff(s["tok_off"]).astype(np.int64)
        src = np.repeat(np.asarray(s["tok_base"], np.int64), nt) + np.asarray(s["tok_idx"], np.int64)
        out = {k: v for k, v in s.items() if k not in ("tok_idx", "tok_base")}
        for key in ("tok_type", "ids", "f"):
            out[key] = np.asarray(s[key])[src]
        return out

    def _evict(self, m):
        """Compact: evicts the m oldest samples, releasing their dictionary references (caller holds the lock)."""
        if m <= 0:
            return
        j = (self.s_tail + np.arange(m)) % self.cs
        nt = self.ntok[j].astype(np.int64)
        cols = np.arange(int(nt.sum())) - np.repeat(np.cumsum(nt) - nt, nt)
        self.store.release(self.tok_idx[(np.repeat(self.idx_start[j], nt) + cols) % self.ci])
        self.s_tail += m

    def _add_compact(self, s):
        S = len(s["outcome"])
        if "tok_idx" not in s:   # copied chunk: each sample's tokens as its own rows
            s = dict(s, tok_idx=np.arange(int(s["tok_off"][-1])) - np.repeat(s["tok_off"][:-1], np.diff(s["tok_off"])),
                     tok_base=np.asarray(s["tok_off"][:-1], np.int64))
        nt = np.diff(s["tok_off"]).astype(np.int32)
        na = np.diff(s["act_off"]).astype(np.int32)
        n_ref, n_act = int(nt.sum()), int(na.sum())
        if n_ref > self.ci or n_act > self.ca or S > self.cs:
            raise ValueError("replay: one take_samples chunk larger than the window")
        rows = np.repeat(np.asarray(s["tok_base"], np.int64), nt) + np.asarray(s["tok_idx"], np.int64)
        tt = np.ascontiguousarray(s["tok_type"], np.int8)
        ids = np.ascontiguousarray(s["ids"], np.int16)
        f16 = np.ascontiguousarray(s["f"], np.float16).view(np.uint16)
        counts = np.bincount(rows, minlength=len(tt)).astype(np.int64)
        if self.hp_runs:   # one HP vector per run; each sample's labels are its run's from its floor on
            run = np.asarray(s["run"])
            starts = np.flatnonzero(np.concatenate([[True], run[1:] != run[:-1]])) if S else np.zeros(0, np.int64)
            run_of = np.cumsum(np.isin(np.arange(S), starts)) - 1
            hp = np.asarray(s["hp_floor"], np.int16)
            vec = np.maximum.reduceat(hp, starts, axis=0) if S else hp
            if not np.array_equal(self._hp_labels(vec[run_of], s["floor"]), hp):
                raise ValueError("replay: per-floor HP labels differ within a run")
            if len(starts) > self.cr:
                raise ValueError("replay: one take_samples chunk has more runs than the HP run ring")
        n_run = len(starts) if self.hp_runs else 0
        with self.lock:
            # Room in the sample, index, action and run rings: the oldest samples whose rows the chunk overwrites go.
            live = self.s_head - self.s_tail
            if live:
                j = (self.s_tail + np.arange(live)) % self.cs
                ok = ((self.idx_start[j] >= self.i_head + n_ref - self.ci)
                      & (self.act_start[j] >= self.a_head + n_act - self.ca))
                if self.hp_runs:
                    ok &= self.hp_ref[j] >= self.r_head + n_run - self.cr
                k = int(np.argmax(ok)) if ok.any() else live
                self._evict(max(k, live + S - self.cs))
            # Room in the dictionary: the oldest samples go until the chunk's new tokens fit.
            # count_new is recomputed after each eviction: an evicted sample can free a token this chunk uses, which
            # it then needs a slot for. Margin 16: count_new may undercount by a hash collision inside the chunk.
            new = self.store.count_new(tt, ids, f16, counts) + 16
            while self.store.free < new and len(self):
                self._evict(min(len(self), max(S, len(self) // 32)))
                new = self.store.count_new(tt, ids, f16, counts) + 16
            if self.store.free < new - 16:
                raise ValueError("replay: one take_samples chunk has more distinct tokens than the dictionary")
            slots = self.store.intern(tt, ids, f16, counts)
            for ring, key in ((self.a_type, "a_type"), (self.a_src, "a_src"), (self.a_tgt, "a_tgt"),
                              (self.a_f, "a_f"), (self.policy, "policy")):
                self._put(ring, self.a_head, s[key])
            a0, i0 = self.a_head, self.i_head
            self.a_head += n_act
            self._put(self.tok_idx, i0, slots[rows])
            self.i_head += n_ref
            self._put(self.idx_start, self.s_head, i0 + s["tok_off"][:-1])
            if self.hp_runs:
                self._put(self.hpr, self.r_head, vec)
                self._put(self.hp_ref, self.s_head, self.r_head + run_of)
                self.r_head += n_run
            if self.soft_q:
                self._put(self.sq_len, self.s_head, np.zeros(S, np.uint8))
            return self._add_meta(s, S, nt, na, a0)

    @staticmethod
    def _hp_labels(vec, floor):
        """Per-floor HP labels [S, 56] from run vectors [S, 56]: masked (-1) before the sample's floor."""
        fl = np.clip(np.asarray(floor, np.int64), 1, vec.shape[1])
        keep = np.arange(1, vec.shape[1] + 1)[None, :] >= fl[:, None]
        return np.where(keep, vec, -1).astype(np.int16)

    def add(self, s):
        if self.compact:
            return self._add_compact(s)
        S = len(s["outcome"])
        s = self.expand_chunk(s)
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
            return self._add_meta(s, S, nt, na, a0)

    def _add_meta(self, s, S, nt, na, a0):
        """The per-sample rows of a chunk and the eviction of overwritten samples (caller holds the lock)."""
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
        # Evict the oldest samples whose rows were overwritten (or that exceed the sample capacity); compact
        # evicted before writing (references released).
        while not self.compact and (self.s_head - self.s_tail > self.cs or (
                self.s_tail < self.s_head and (self.tok_start[self.s_tail % self.cs] < self.t_head - self.ct
                                               or self.act_start[self.s_tail % self.cs] < self.a_head - self.ca))):
            self.s_tail += 1
        return first

    def set_soft_outcome(self, first, targets):
        """Stores the EMA outcome targets of the samples first .. first + len(targets) - 1 (absolute counters, as
        add returned); samples already evicted are skipped."""
        if self.soft_q:
            return self._set_soft_q(first, targets)
        with self.lock:
            lo = max(first, self.s_tail)
            if lo < first + len(targets):
                self._put(self.soft_outcome, lo, np.asarray(targets[lo - first:], np.float16))

    def _set_soft_q(self, first, targets):
        C = OUTCOME_CLASSES
        q = np.rint(np.asarray(targets, np.float32) * 255.0).clip(0, 255).astype(np.uint8)
        nz = q > 0
        has = nz.any(1)
        a = np.argmax(nz, 1)
        b = C - 1 - np.argmax(nz[:, ::-1], 1)
        ln = np.where(has, b - a + 1, 0)
        cols = np.arange(C)
        data = q[(cols[None, :] >= a[:, None]) & (cols[None, :] <= b[:, None]) & has[:, None]]
        if len(data) > self.cq:
            raise ValueError("replay: one chunk's quantized targets larger than the byte ring")
        with self.lock:
            lo = max(first, self.s_tail)
            k0 = lo - first
            if k0 >= len(targets):
                return
            n = int(ln[k0:].sum())
            data = data[int(ln[:k0].sum()):]
            # The oldest samples whose target bytes are overwritten go (samples not set yet hold no bytes).
            live = lo - self.s_tail
            if live:
                j = (self.s_tail + np.arange(live)) % self.cs
                bad = (self.sq_len[j] > 0) & (self.sq_start[j] < self.q_head + n - self.cq)
                if bad.any():   # only samples before lo: the chunk's own samples hold no bytes yet
                    self._evict(int(np.flatnonzero(bad)[-1]) + 1)
            starts = self.q_head + np.concatenate([[0], np.cumsum(ln[k0:])[:-1]]).astype(np.int64)
            self._put(self.sq, self.q_head, data)
            self._put(self.sq_start, lo, starts)
            self._put(self.sq_lo, lo, a[k0:].astype(np.uint8))
            self._put(self.sq_len, lo, ln[k0:].astype(np.uint8))
            self.q_head += n
            self.soft_stats[0] += len(ln) - k0
            self.soft_stats[1] += n

    def rows(self, first, n):
        """The samples first .. first + n - 1 (absolute counters, all live) as one batch in forward_flat's layout."""
        with self.lock:
            if first < self.s_tail or first + n > self.s_head:
                raise ValueError("replay.rows: samples not in the window")
            return self._gather((first + np.arange(n)) % self.cs)

    def sample(self, rng, B, policy_frac=0.0, packed=False, pack_step=1):
        """A training batch in forward_flat's layout (numpy), B rows drawn uniformly from the window. policy_frac > 0
        draws at least that share of rows among samples with a policy target (rejection on the uniform draw).
        packed=True: tok_type / ids / f hold only the live tokens ([N], row after row, as forward_packed takes them)
        with pack_idx [N] (their slots in the [B, T] layout); N is padded to a multiple of pack_step with trash
        entries (pack_idx = B * T, zero inputs)."""
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
            return self._gather(j, packed, pack_step)

    def _gather(self, j, packed=False, pack_step=1):
        """Rows j (ring positions) in forward_flat's layout (packed: see sample); the caller holds the lock."""
        B = len(j)
        nt, na = self.ntok[j], self.nact[j]
        T, A = int(nt.max()), int(na.max())
        T = -(-T // 8) * 8
        A = -(-A // 8) * 8
        rows_t = np.repeat(np.arange(B), nt)
        cols_t = np.arange(int(nt.sum())) - np.repeat(np.cumsum(nt) - nt, nt)
        if self.compact:
            src_t = self.tok_idx[(np.repeat(self.idx_start[j], nt) + cols_t) % self.ci].astype(np.int64)
        else:
            src_t = (np.repeat(self.tok_start[j], nt) + cols_t) % self.ct
        rows_a = np.repeat(np.arange(B), na)
        cols_a = np.arange(int(na.sum())) - np.repeat(np.cumsum(na) - na, na)
        src_a = (np.repeat(self.act_start[j], na) + cols_a) % self.ca
        b = {"mask": np.zeros((B, T), bool),
             "a_type": np.zeros((B, A), np.int64), "a_src": np.full((B, A), -1, np.int64),
             "a_tgt": np.full((B, A), -1, np.int64), "a_f": np.zeros((B, A, N_ACT_FEAT), np.float16),
             "a_mask": np.zeros((B, A), bool), "policy": np.zeros((B, A), np.float32)}
        if packed:
            n = int(nt.sum())
            npad = -(-n // pack_step) * pack_step
            b["tok_type"] = np.zeros(npad, np.int64)
            b["ids"] = np.zeros((npad, N_CAT), np.int64)
            b["f"] = np.zeros((npad, N_FLOAT), np.float16)
            b["pack_idx"] = np.full(npad, B * T, np.int64)
            b["tok_type"][:n] = self.tok_type[src_t]
            b["ids"][:n] = self.ids[src_t]
            b["f"][:n] = self.f[src_t]
            b["pack_idx"][:n] = rows_t * T + cols_t
        else:
            b["tok_type"] = np.zeros((B, T), np.int64)
            b["ids"] = np.zeros((B, T, N_CAT), np.int64)
            b["f"] = np.zeros((B, T, N_FLOAT), np.float16)
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
        if self.hp_runs:
            b["hp_floor"] = self._hp_labels(self.hpr[self.hp_ref[j] % self.cr], b["floor"])
        if self.soft_q:
            C = OUTCOME_CLASSES
            so = np.zeros((B, C), np.float32)
            ln = self.sq_len[j].astype(np.int64)
            unset = np.flatnonzero(ln == 0)   # before set_soft_outcome: the final outcome
            so[unset, b["outcome"][unset].astype(np.int64).clip(0, C - 1)] = 1.0
            r = np.repeat(np.arange(B), ln)
            c = np.arange(int(ln.sum())) - np.repeat(np.cumsum(ln) - ln, ln)
            so[r, np.repeat(self.sq_lo[j].astype(np.int64), ln) + c] = (
                self.sq[(np.repeat(self.sq_start[j], ln) + c) % self.cq].astype(np.float32) / 255.0)
            b["soft_outcome"] = so / so.sum(-1, keepdims=True)
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


def soft_policy_target(policy, a_mask):
    """Amber Eye / KataGo soft policy target: the policy target p raised to the power 1/4 and renormalised over the
    legal actions (rows without a policy target stay 0)."""
    t = policy.float().clamp(min=0).pow(0.25) * a_mask
    return t / t.sum(-1, keepdim=True).clamp(min=1e-12)


def losses(net, b, w_policy, w_outcome, w_hp, w_hp_floor=0.0, w_soft_policy=0.0):
    logits, outcome, hp, hpf, *soft = net(b)
    logp = torch.log_softmax(logits.float().masked_fill(~b["a_mask"], -1e4), -1)
    has = b["has_policy"].bool()
    pol = -(b["policy"] * logp).sum(-1)
    l_pol = (pol * has).sum() / has.sum().clamp(min=1)
    l_soft = None
    if w_soft_policy > 0:   # --w-soft-policy: soft head (AmberNet(soft_policy=True), training mode) on p^(1/4)
        slogp = torch.log_softmax(soft[0].float().masked_fill(~b["a_mask"], -1e4), -1)
        spol = -(soft_policy_target(b["policy"], b["a_mask"]) * slogp).sum(-1)
        l_soft = (spol * has).sum() / has.sum().clamp(min=1)
    l_out = F.cross_entropy(outcome.float(), b["outcome"].long())
    l_hp = F.cross_entropy(hp.float(), b["hp_end"].long().clamp(0, HP_CLASSES - 1))
    parts = {"policy": l_pol.detach(), "outcome": l_out.detach(), "hp": l_hp.detach()}
    if "soft_outcome" in b:   # --value-ema-halflife: train on the EMA target; "outcome" stays the final-outcome CE
        l_ema = -(b["soft_outcome"] * torch.log_softmax(outcome.float(), -1)).sum(-1).mean()
        parts["outcome_ema"] = l_ema.detach()
        l_out = l_ema
    total = w_policy * l_pol + w_outcome * l_out + w_hp * l_hp
    if l_soft is not None:
        total = total + w_soft_policy * l_soft
        parts["soft_policy"] = l_soft.detach()
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


def per_run_means(pw):
    """Relics held and deck size at the run's end, mean per run finished in this window over all ascensions
    (progress_window relics_sum / deck_size_sum): (relics_per_run, deck_per_run), None where no run finished or the
    driver has no such counter."""
    n = sum(e["runs"] for e in pw.values())
    def mean(k):
        if not n or not all(k in e for e in pw.values()):
            return None
        return round(sum(e[k] for e in pw.values()) / n, 3)
    return mean("relics_sum"), mean("deck_size_sum")


ECONOMY_KEYS = ("chests", "chests_skipped", "relics_taken_elite", "relics_taken_chest", "relics_taken_other",
                "relics_left_elite", "relics_left_chest", "relics_left_other", "shops", "shop_cards", "shop_relics",
                "shop_potions", "shop_removes", "boss_relic_skips", "gold_gained", "gold_lost",
                "sapphire_relic_forfeits")


def economy_per_run(pw):
    """Economy / relic-source counters (2026-11-19, logging only) per run finished in this window over all ascensions
    (progress_window sums / runs), or None where no run finished or the driver has no such counters."""
    n = sum(e["runs"] for e in pw.values())
    if not n or not all(k in e for e in pw.values() for k in ECONOMY_KEYS):
        return None
    return {k: round(sum(e[k] for e in pw.values()) / n, 3) for k in ECONOMY_KEYS}


def malloc_trim():
    """glibc malloc_trim(0): hand freed heap memory of all arenas back to the OS (2026-11-18: the C++ workers'
    malloc arenas grew ~0.9 GB/h by fragmentation with all data structures flat). Returns True if it ran."""
    try:
        import ctypes
        ctypes.CDLL("libc.so.6").malloc_trim(0)
        return True
    except (OSError, AttributeError):
        return False


def rss_gb():
    """Resident set size of this process in GB (Linux /proc; None elsewhere)."""
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return round(int(line.split()[1]) / 1048576, 2)
    except OSError:
        pass
    return None


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
    ap.add_argument("--full-candidates", type=int, default=16,
                    help="Gumbel root candidates m of a full move (sequential halving over ceil(log2 m) rounds; our "
                         "choice, the Amber Eye page names no m)")
    ap.add_argument("--fast-candidates", type=int, default=4, help="Gumbel root candidates m of a fast move")
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
                    help="samples of unfinished runs held for their labels; above it keep probabilities shrink "
                         "(<= 0: no cap, every full move is trained on, as Amber Eye; memory ~5.5 KB per held sample)")
    ap.add_argument("--compact-samples", action="store_true",
                    help="Amber Eye's compact storage: samples waiting for labels and the replay window keep each "
                         "run's distinct tokens once and refer to them by index (same training data, a fraction of "
                         "the memory; lets --max-pending 0 fit)")
    ap.add_argument("--replay-dict-tokens", type=int, default=8,
                    help="--compact-samples: slots of the window's token dictionary per window sample (too few "
                         "evicts early: the metric replay then stays below --window; replay_dict_used shows the use)")
    ap.add_argument("--compress-targets", action="store_true",
                    help="with --compact-samples: Amber Eye's target compression in the replay window (EMA outcome "
                         "targets 8-bit fixed point, nonzero interval only; per-floor HP labels once per run)")
    ap.add_argument("--replay-soft-bytes", type=int, default=64,
                    help="--compress-targets: target byte ring per window sample (64 holds a full 57-bin interval; metric replay_soft_bytes_mean)")
    ap.add_argument("--replay-hp-runs", type=float, default=0.125,
                    help="--compress-targets: HP run ring slots per window sample (runs with fewer samples evict early)")
    ap.add_argument("--replay-tokens-per-sample", type=int, default=48,
                    help="token (index) ring slots per window sample")
    ap.add_argument("--replay-actions-per-sample", type=int, default=12,
                    help="action ring slots per window sample")
    ap.add_argument("--explore-c", type=float, default=0.0, help="pick-rate exploration strength (0 = off)")
    ap.add_argument("--pick-target", type=float, default=0.01, help="pick-rate target per item and run")
    ap.add_argument("--explore-amber", action="store_true",
                    help="Amber Eye exploration (RunConfig::exploreAmber): under-target items stay search candidates "
                         "and are played with probability min(1, c exp(-m / T)), c per item by bisection to hit "
                         "--pick-target of runs; not with --explore-c")
    ap.add_argument("--explore-temp", type=float, default=4.0, help="T of --explore-amber (Amber Eye: 4)")
    ap.add_argument("--explore-per-offer", action="store_true",
                    help="with --explore-amber: the --pick-target rate counts the runs that OFFERED the item, not all "
                         "runs, so rarely offered items are no longer forced at every offer (2026-11-19, default off; "
                         "a deviation from Amber Eye's text, Philipp)")
    ap.add_argument("--explore-gap-search", action="store_true",
                    help="with --explore-amber: the gap m is taken in the search's final root score (Gumbel + logit + "
                         "sigma(Q)) instead of the net's prior logits (2026-11-19, default off; Philipp decides)")
    ap.add_argument("--explore-deck-only", action="store_true",
                    help="with --explore-amber: only cards, relics and potions are pick-rate items; event / campfire "
                         "options are never forced (2026-11-19, default off; Philipp decides)")
    ap.add_argument("--eval-cache", action="store_true",
                    help="per-run evaluation cache: a leaf whose net input this run already had evaluated with the "
                         "current inference weights reuses that result (exact; RunConfig::evalCache)")
    ap.add_argument("--eval-cache-cap", type=int, default=1024, help="cache entries per run (emptied when full)")
    ap.add_argument("--c-visit", type=float, default=50.0, help="Gumbel sigma: (c_visit + max N) * c_scale")
    ap.add_argument("--c-scale", type=float, default=1.0, help="Gumbel sigma scale (mctx uses 0.1 with --q-rescale)")
    ap.add_argument("--no-fast-noise", action="store_true", help="no Gumbel noise on fast moves (Amber Eye)")
    ap.add_argument("--q-rescale", action="store_true",
                    help="completed Q as in Gumbel MuZero: mixed value for unvisited edges, min-max rescale per node")
    ap.add_argument("--merge-cards", action="store_true",
                    help="net input: identical cards as one CARD token with a copy count (search::amberMergeCards); "
                         "changes what the net sees, so a run uses it from its start (a warm start sees count 0 = the "
                         "old single-card encoding)")
    ap.add_argument("--chance-on-reveal", action="store_true",
                    help="Amber Eye: an out-of-combat search edge is a chance edge only when its step reveals hidden "
                         "information (an RNG draw, a pre-shuffled pool / encounter queue, a fight start, a new act)")
    ap.add_argument("--cross-combat", action="store_true",
                    help="Amber Eye: one search over combat and out-of-combat states (fight starts and won fights are "
                         "expanded instead of being net-valued leaves)")
    ap.add_argument("--sim-help", action="store_true",
                    help="Amber Eye's simulator help: reward gold taken automatically, forced positions skipped also "
                         "inside the search, buying Prismatic Shard banned")
    ap.add_argument("--heart-log", type=float, default=0.0, metavar="RATE",
                    help="diagnostic (2026-11-19, default 0 = off; play and training unchanged): append one JSON record "
                         "per finished run that fought the Heart to <out-dir>/heart_runs.jsonl.gz: every kill, other "
                         "Heart runs with probability RATE (by a hash of the seed). Record: entry HP, deck, relics, "
                         "potions, Heart HP left, turns, per-floor HP, and the net's / search's P(win), E[final floor] "
                         "and value at the first searched move of each act and of the Heart fight (-1 without "
                         "--value-ema-search's outcome distributions)")
    ap.add_argument("--savescum", action="store_true",
                    help="Amber Eye's early-training savescum: the search steps the real run with its real RNG and "
                         "hidden state (no resampling, no chance edges); the net still sees the public view. Off "
                         "(every run, from its next searched move) once a file SAVESCUM_OFF is in --out-dir, also "
                         "when it is there at start or a resume")
    ap.add_argument("--force-keys", choices=("off", "curriculum", "on"), default="off",
                    help="curriculum: the ADR-0063 Heart-key backstops (Act-3 treasure-row Sapphire, Recall at the last "
                         "Act-3 campfire, Act-3 route kept on the burning elite) are forced moves until the first "
                         "curriculum step-up (needs --curriculum; a deviation from Amber Eye, Philipp 2026-11-18); on: forced at every "
                         "ascension, also after curriculum step-ups (Philipp 2026-11-19)")
    ap.add_argument("--force-rewards", action="store_true",
                    help="forced reward choices (2026-11-19, default off; a deviation from Amber Eye, Philipp): chests "
                         "opened unless we hold Cursed Key, every relic on a reward screen (elites, chests, event "
                         "fights; boss relics stay learned) taken unless on the reviewed list (Bottled x3, Dead Branch, "
                         "Tungsten Rod, Unceasing Top, Juzu Bracelet); Ceramic Fish / eggs / Potion Belt before the "
                         "card reward, Whetstone / War Paint after it")
    ap.add_argument("--heart-arms", default="",
                    help="Heart search probe (diagnostic, default off): FULL:FAST:PROB:MFULL:MFAST,... search budgets; "
                         "each run reaching the Heart plays the fight from the same start once per arm and rep "
                         "(results in heart_probe.jsonl); use with --min-replay above any sample count (frozen net) "
                         "and --keep-full 0")
    ap.add_argument("--heart-reps", type=int, default=1, help="plays per arm and Heart start (--heart-arms)")
    ap.add_argument("--batch", type=int, default=2048)
    ap.add_argument("--row-buckets", default="2048", help="batch rows padded to these (one size keeps compiled shapes few)")
    ap.add_argument("--tok-buckets", default="32,40,48,56,64,80,96,128,212")
    ap.add_argument("--act-buckets", default="16,32,64,96")
    ap.add_argument("--pack-step", type=int, default=2048)
    ap.add_argument("--pack-threads", type=int, default=4)
    ap.add_argument("--fused-layer", action="store_true", help="inference: stage 0's three-kernel layers (d <= 128)")
    ap.add_argument("--compile", action="store_true", help="inference: torch.compile")
    ap.add_argument("--fused-net", action="store_true",
                    help="inference: the whole net as one Triton kernel per batch (tools/az_bench/fused_net.py; same "
                         "math, fp32 residual stream); needs --packed-h2d, not with --compile")
    ap.add_argument("--gpu-timing", action="store_true",
                    help="log GPU time per second of the inference forward and of the training steps (CUDA events on "
                         "each thread's stream; the two streams run concurrently, so each figure is the busy time of "
                         "its stream including time the other stream's kernels hold the GPU)")
    ap.add_argument("--packed-h2d", action="store_true",
                    help="inference: the driver packs only the live tokens (tok_type / ids / f [N], pack_idx, seq_off "
                         "from C++), so the host-to-GPU copy has no dead slots (needs --pack-step; same outputs)")
    ap.add_argument("--copy-stream", action="store_true",
                    help="inference: host-to-GPU copies on their own CUDA stream, overlapping the previous batch's "
                         "forward (same outputs)")
    ap.add_argument("--window", type=int, default=500000, help="replay window (samples)")
    ap.add_argument("--min-replay", type=int, default=20000, help="samples before training starts")
    ap.add_argument("--train-batch", type=int, default=1024)
    ap.add_argument("--train-packed", action="store_true",
                    help="training: batches with only the live tokens (forward_packed: per-token work without the "
                         "padding to the longest sample; same loss up to float rounding)")
    ap.add_argument("--replay-ratio", type=float, default=2.0, help="max trained / generated samples")
    ap.add_argument("--policy-frac", type=float, default=0.0, help="min share of policy rows per train batch")
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--weight-decay", type=float, default=1e-4)
    ap.add_argument("--warmup-steps", type=int, default=500)
    ap.add_argument("--w-policy", type=float, default=1.0)
    ap.add_argument("--w-soft-policy", type=float, default=0.0,
                    help="loss weight of the soft policy head (Amber Eye / KataGo: target p^(1/4); 0 = no head; "
                         "KataGo uses 8)")
    ap.add_argument("--w-outcome", type=float, default=1.0)
    ap.add_argument("--w-hp", type=float, default=1.0)
    ap.add_argument("--value-ema-halflife", type=float, default=0.0,
                    help="EMA outcome labels: half-life in kept samples of a run (0 = off: final outcome); with "
                         "--value-ema-search in searched moves")
    ap.add_argument("--value-ema-search", action="store_true",
                    help="EMA outcome labels from the search-backed root outcome distributions (Amber Eye), computed "
                         "by the driver (needs --value-ema-halflife)")
    ap.add_argument("--value-ema-moves", choices=("full", "all"), default="full",
                    help="--value-ema-search: the EMA chain over full-search moves only (Amber Eye; half-life in full "
                         "moves) or over all searched moves (half-life in searched moves)")
    ap.add_argument("--sync-steps", type=int, default=50, help="copy trained weights to the inference net every N steps")
    ap.add_argument("--report", type=float, default=30.0)
    ap.add_argument("--no-nonfinite-skip", dest="nonfinite_skip", action="store_false",
                    help="do not skip training steps whose loss or gradient norm is non-finite (default: skip them: no "
                         "optimizer step, counted as nonfinite_skips; 2026-11-19 one NaN step turned all weights NaN)")
    ap.add_argument("--nonfinite-abort-after", type=int, default=50,
                    help="stop the run cleanly after this many consecutive skipped non-finite steps (final checkpoint "
                         "without the skipped steps; 0 = never)")
    ap.add_argument("--malloc-trim", action="store_true",
                    help="call glibc malloc_trim(0) at every report and log RSS before / after (rss_gb_pre_trim)")
    ap.add_argument("--ckpt-minutes", type=float, default=30.0)
    ap.add_argument("--resume")
    ap.add_argument("--seed", type=int, default=0, help="weight init / search / sampling seed (not a run seed)")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--test-max-hp", type=int, default=0, help="tests only")
    args = ap.parse_args(argv)
    if args.packed_h2d and not args.pack_step:
        ap.error("--packed-h2d needs --pack-step")
    if args.init_net and args.resume:
        ap.error("--init-net and --resume exclude each other")
    if args.force_keys == "curriculum" and not args.curriculum:
        ap.error("--force-keys curriculum needs --curriculum")
    if args.value_ema_search and not args.value_ema_halflife > 0:
        ap.error("--value-ema-search needs --value-ema-halflife > 0")
    amber = args.utility == "amber"
    hp_floors = 56 if amber else 1
    if not 0.0 <= args.heart_log <= 1.0:
        ap.error("--heart-log: RATE in [0, 1]")
    heart_arms = [[float(x) for x in a.split(":")] for a in args.heart_arms.split(",") if a]
    if any(len(a) != 5 for a in heart_arms):
        ap.error("--heart-arms: FULL:FAST:PROB:MFULL:MFAST per arm")

    sys.path.insert(0, args.module_dir)
    import az_bench_native  # noqa: E402

    os.makedirs(args.out_dir, exist_ok=True)
    dev = torch.device(args.device)
    cuda = dev.type == "cuda"
    torch.manual_seed(args.seed)
    d, layers = amber_net.SIZES.get(args.net) or tuple(int(x) for x in args.net.split("x")[:2])
    train_net = amber_net.AmberNet(d=d, layers=layers, hp_floors=hp_floors,
                                   soft_policy=args.w_soft_policy > 0).to(dev)
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
    # The curriculum has stepped up once (recorded at the step-up; older checkpoints: ascension above --ascension).
    counters["curriculum_stepped"] = bool(counters.get("curriculum_stepped", ascension > args.ascension))
    force_keys = args.force_keys == "on" or (args.force_keys == "curriculum" and not counters["curriculum_stepped"])
    if args.savescum and os.path.exists(os.path.join(args.out_dir, "SAVESCUM_OFF")):
        counters["savescum_off"] = True   # the file was there before this start: no run plays savescum
    savescum = args.savescum and not counters.get("savescum_off", False)
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
    fused = None
    if args.fused_net:
        if not args.packed_h2d or args.compile:
            ap.error("--fused-net needs --packed-h2d and excludes --compile")
        fused = amber_net.load_kernel("fused_net")(infer)
        fused_mod = sys.modules["az_bench_fused_net"]
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
    ema_lam = 0.5 ** (1.0 / args.value_ema_halflife) if args.value_ema_halflife > 0 else 0.0
    ema_search = bool(args.value_ema_search)
    drv = az_bench_native.RunDriver(
        workers=args.workers, games=args.games, seed_base=seed_base, max_runs=max_runs, ascension=ascension,
        full_sims=args.full_sims, fast_sims=args.fast_sims, full_prob=args.full_prob,
        full_candidates=args.full_candidates, fast_candidates=args.fast_candidates,
        hp_weight_combat=args.hp_weight_combat, hp_weight_ooc=args.hp_weight_ooc, keep_full=args.keep_full,
        keep_fast=args.keep_fast, search_seed=args.seed + counters["step"], max_fight_moves=args.max_fight_moves,
        test_max_hp=args.test_max_hp, max_pending=args.max_pending,
        explore_c=args.explore_c, pick_target=args.pick_target, c_visit=args.c_visit, c_scale=args.c_scale,
        fast_noise=not args.no_fast_noise, q_rescale=args.q_rescale, utility=1 if amber else 0,
        keyless_hp=args.keyless_hp,
        eval_cache=args.eval_cache, eval_cache_cap=args.eval_cache_cap, merge_cards=args.merge_cards,
        chance_on_reveal=args.chance_on_reveal, cross_combat=args.cross_combat, sim_help=args.sim_help,
        explore_amber=args.explore_amber, explore_temp=args.explore_temp,
        **({"search_ema_lambda": ema_lam, "search_ema_full_only": args.value_ema_moves == "full"}
           if ema_search else {}),
        **({"force_keys": True} if force_keys else {}),
        **({"force_rewards": True} if args.force_rewards else {}),
        **({"explore_per_offer": True} if args.explore_per_offer else {}),
        **({"explore_gap_search": True} if args.explore_gap_search else {}),
        **({"explore_deck_only": True} if args.explore_deck_only else {}),
        **({"heart_arms": heart_arms, "heart_reps": args.heart_reps} if heart_arms else {}),
        **({"savescum": True} if savescum else {}),
        **({"compact_samples": True} if args.compact_samples else {}),
        **({"heart_log_rate": args.heart_log} if args.heart_log > 0 else {}))
    heart_log_path = os.path.join(args.out_dir, "heart_runs.jsonl.gz")
    heart_logged = [0, 0]   # records, of which kills (this process)

    def drain_heart_log():
        # appends a gzip member per call (gzip.open reads all members); nothing is written without records
        if args.heart_log <= 0:
            return
        recs = drv.take_heart_run_logs()
        if not recs:
            return
        with gzip.open(heart_log_path, "at") as f:
            for r in recs:
                f.write(json.dumps(r) + "\n")
        heart_logged[0] += len(recs)
        heart_logged[1] += sum(r["win"] for r in recs)
    if args.savescum:
        print(f"# savescum: {'on until a file SAVESCUM_OFF appears in --out-dir' if savescum else 'off (SAVESCUM_OFF seen before this resume)'}",
              flush=True)
    if args.force_keys != "off":
        print(f"# force-keys {args.force_keys}: {'on at every ascension' if args.force_keys == 'on' else 'on until the first curriculum step-up' if force_keys else 'off (the curriculum already stepped up)'}",
              flush=True)
    replay = Replay(args.window, hp_floors=56 if amber else 0, soft_outcome=ema_lam > 0,
                    compact=args.compact_samples, dict_tokens_per_sample=args.replay_dict_tokens,
                    token_store=az_bench_native.TokenStore if args.compact_samples else None,
                    tokens_per_sample=args.replay_tokens_per_sample, actions_per_sample=args.replay_actions_per_sample,
                    compress_targets=args.compress_targets, soft_bytes_per_sample=args.replay_soft_bytes,
                    hp_runs_per_sample=args.replay_hp_runs)
    ema_stats = {"samples": 0, "real_weight": 0.0}   # mean weight of the final outcome in the EMA targets
    stop = threading.Event()
    errors = []
    weights_lock = threading.Lock()
    new_weights = [None]          # (state tensors on the GPU, event) published by the trainer
    loss_keys = (("policy", "outcome", "hp") + (("hp_floor",) if amber else ())
                 + (("outcome_ema",) if ema_lam > 0 else ()) + (("soft_policy",) if args.w_soft_policy > 0 else ()))
    lossbox = dict({"n": 0}, **{k: 0.0 for k in loss_keys})
    lossbox_lock = threading.Lock()
    counters.setdefault("nonfinite_skips", 0)
    nonfinite_run = [0]   # consecutive skipped steps
    gradbox = {"n": 0, "sum": 0.0, "max": 0.0}   # gradient norm (before clipping) of the finite steps since the last report
    infer_stats = {"batches": 0, "rows": 0, "syncs": 0}
    gpu_ms = {"infer": 0.0, "train": 0.0}   # --gpu-timing: cumulative stream busy time

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
        copy_stream = torch.cuda.Stream(dev) if cuda and args.copy_stream else None
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
            if ema_search:
                out["dist"] = torch.zeros(R * OUTCOME_CLASSES, dtype=torch.float32, pin_memory=cuda)
            return h, {k: v.numpy() for k, v in h.items()}, out

        sets = [buffers(), buffers()]
        cur, pending = 0, None

        def finish(p):
            ticket, rows, Ap, out, ev, version, ev0 = p
            if ev is not None:
                ev.synchronize()
                if ev0 is not None:
                    gpu_ms["infer"] += ev0.elapsed_time(ev)
            drv.submit(ticket, out["logits"][:rows * Ap].numpy().reshape(rows, Ap), out["F"][:rows].numpy(),
                       out["ehp"][:rows].numpy(), out["hpf"][:rows * 56].numpy().reshape(rows, 56) if amber else None,
                       version, out["dist"][:rows * OUTCOME_CLASSES].numpy().reshape(rows, OUTCOME_CLASSES)
                       if ema_search else None)

        while not stop.is_set():
            host, views, out = sets[cur]
            if args.packed_h2d:
                got = drv.next_flat(args.batch, min_rows, 5, row_b, tok_b, act_b, views, args.pack_threads,
                                    packed_tokens=True)
            else:
                got = drv.next_flat(args.batch, min_rows, 5, row_b, tok_b, act_b, views, args.pack_threads)
            launched = None
            if got is not None:
                ticket, rows, Rp, Tp, Ap = got[:5]
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
                        if fused is not None:
                            fused.refresh()   # the kernel's stacked weight copy, on this stream after the copy
                        # Evaluation cache: results of the old weights are not reused from now on.
                        drv.set_weights_version(infer_stats["syncs"])
                    M = Rp * Tp
                    if args.packed_h2d:
                        # The driver wrote the N live tokens packed, pack_idx [N] and seq_off; entries N..npad of
                        # the packed arrays are trash (stale but valid values), their pack_idx the trash slot M.
                        nl = got[5]
                        npad = -(-nl // args.pack_step) * args.pack_step
                        views["pack_idx"][nl:npad] = M
                        shapes = {"tok_type": (npad,), "ids": (npad, 4), "f": (npad, 64), "pack_idx": (npad,)}
                    else:
                        shapes = {"tok_type": (Rp, Tp), "ids": (Rp, Tp, 4), "f": (Rp, Tp, 64)}
                    shapes.update({"mask": (Rp, Tp), "a_type": (Rp, Ap), "a_src": (Rp, Ap), "a_tgt": (Rp, Ap),
                                   "a_f": (Rp, Ap, 8), "a_mask": (Rp, Ap)})
                    if args.pack_step and not args.packed_h2d:
                        live = np.flatnonzero(views["mask"][:M])
                        nl = live.size
                        npad = -(-nl // args.pack_step) * args.pack_step
                        views["pack_idx"][:nl] = live
                        views["pack_idx"][nl:npad] = M
                        shapes["pack_idx"] = (npad,)
                        if infer.varlen_attn is not None:
                            so = views["seq_off"]
                            so[0] = 0
                            np.cumsum(views["mask"][:M].reshape(Rp, Tp).sum(1), out=so[1:Rp + 1])
                    if args.pack_step and (infer.varlen_attn is not None or fused is not None):
                        shapes["seq_off"] = (Rp + 1,)
                    if fused is not None:   # the kernel tiles rows by seq_off; it reads neither mask nor pack_idx
                        shapes.pop("mask")
                        shapes.pop("pack_idx", None)
                    # Host-to-GPU copies (on copy_stream when --copy-stream: the forward waits for them).
                    raw = {}
                    with (torch.cuda.stream(copy_stream) if copy_stream is not None else contextlib.nullcontext()):
                        for k, shp in shapes.items():
                            raw[k] = host[k][:int(np.prod(shp))].to(dev, non_blocking=True).view(shp)
                    if copy_stream is not None:
                        ev_c = torch.cuda.Event()
                        ev_c.record(copy_stream)
                        stream.wait_event(ev_c)
                        for t in raw.values():
                            t.record_stream(stream)
                    ev0 = None
                    if args.gpu_timing and stream is not None:
                        ev0 = torch.cuda.Event(enable_timing=True)
                        ev0.record(stream)
                    x = {}
                    for k, t in raw.items():
                        if fused is not None:
                            x[k] = t   # the kernel reads the driver's int8 / int16 / fp16 arrays as they are
                            continue
                        if k in ("tok_type", "ids", "a_type", "a_src", "a_tgt", "pack_idx"):
                            t = t.long()
                        elif t.dtype == torch.float16:
                            t = t.to(infer_dtype)
                        x[k] = t
                    if args.compile and "pack_idx" in x:
                        torch._dynamo.mark_dynamic(x["pack_idx"], 0)
                        if args.packed_h2d:
                            for k in ("tok_type", "ids", "f"):
                                torch._dynamo.mark_dynamic(x[k], 0)
                    if fused is not None:
                        lg, outcome, hp, hpf = fused(x, fused_mod.make_tiles(views["seq_off"], rows), rows)
                    else:
                        lg, outcome, hp, hpf = run(x)
                    Fv, ehp = search_values(outcome[:rows], hp[:rows])
                    out["logits"][:rows * Ap].view(rows, Ap).copy_(lg[:rows].float(), non_blocking=True)
                    out["F"][:rows].copy_(Fv, non_blocking=True)
                    out["ehp"][:rows].copy_(ehp, non_blocking=True)
                    if amber:
                        out["hpf"][:rows * 56].view(rows, 56).copy_(hpf[:rows].float().clamp(0, 1), non_blocking=True)
                    if ema_search:
                        out["dist"][:rows * OUTCOME_CLASSES].view(rows, OUTCOME_CLASSES).copy_(
                            torch.softmax(outcome[:rows].float(), -1), non_blocking=True)
                    ev = None
                    if stream is not None:
                        ev = torch.cuda.Event(enable_timing=ev0 is not None)
                        ev.record(stream)
                launched = (ticket, rows, Ap, out, ev, infer_stats["syncs"], ev0)
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
        timing = collections.deque()   # --gpu-timing: (start, end) events of steps not yet finished on the GPU
        while not stop.is_set():
            ch = drv.take_samples(TAKE_CHUNK)   # whole runs only
            if ch is not None:
                first = replay.add(ch)
                if ema_search:   # search-backed EMA targets from the driver (whole runs)
                    replay.set_soft_outcome(first, ch["outcome_target"])
                    ema_stats["samples"] += len(ch["outcome"])
                    ema_stats["real_weight"] += float(ch["ema_real_weight"].sum())
                elif ema_lam > 0:
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
            b = replay.sample(rng, args.train_batch, args.policy_frac, packed=args.train_packed)
            ctx = torch.cuda.stream(stream) if stream is not None else torch.no_grad()
            with ctx:
                if args.gpu_timing and stream is not None:
                    while timing and timing[0][1].query():
                        e0, e1 = timing.popleft()
                        gpu_ms["train"] += e0.elapsed_time(e1)
                    e0 = torch.cuda.Event(enable_timing=True)
                    e0.record(stream)
                bt = to_torch(b, dev)
                step = counters["step"]
                lr = args.lr * min(1.0, (step + 1) / max(1, args.warmup_steps))
                for g in opt.param_groups:
                    g["lr"] = lr
                with torch.enable_grad(), amp:
                    loss, parts = losses(train_net, bt, args.w_policy, args.w_outcome, args.w_hp, args.w_hp_floor,
                                         args.w_soft_policy)
                opt.zero_grad(set_to_none=True)
                loss.backward()
                gn = torch.nn.utils.clip_grad_norm_(train_net.parameters(), 1.0)   # norm before clipping
                gnorm = None
                if args.nonfinite_skip:   # one host sync per step (the loss parts below sync anyway)
                    gnorm = float(gn)
                    lval = float(loss.detach())
                    if not (math.isfinite(gnorm) and math.isfinite(lval)):
                        # A non-finite loss or gradient would write NaN into the weights and Adam's moments: skip it.
                        opt.zero_grad(set_to_none=True)
                        counters["nonfinite_skips"] += 1
                        nonfinite_run[0] += 1
                        k = nonfinite_run[0]
                        if k <= 3 or k & (k - 1) == 0:   # log the first 3 of a streak, then at powers of two
                            print(f"# nonfinite step skipped at step {counters['step']}: loss {lval} grad norm {gnorm} "
                                  f"parts {({n: float(v) for n, v in parts.items()})} (streak {k}, total "
                                  f"{counters['nonfinite_skips']})", flush=True)
                        if args.nonfinite_abort_after and k >= args.nonfinite_abort_after:
                            raise RuntimeError(f"{k} consecutive non-finite training steps at step {counters['step']}: "
                                               "stopping (the final checkpoint holds the weights before them)")
                        continue
                    nonfinite_run[0] = 0
                opt.step()
                if gnorm is not None:
                    with lossbox_lock:
                        gradbox["n"] += 1
                        gradbox["sum"] += gnorm
                        gradbox["max"] = max(gradbox["max"], gnorm)
                if args.gpu_timing and stream is not None:
                    e1 = torch.cuda.Event(enable_timing=True)
                    e1.record(stream)
                    timing.append((e0, e1))
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
    last_gpu = dict(gpu_ms)
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
            if args.savescum and drv.savescum() and os.path.exists(os.path.join(args.out_dir, "SAVESCUM_OFF")):
                drv.set_savescum(False)   # every run plays fair from its next searched move
                counters["savescum_off"] = True
                print(f"# savescum: off from run {s['runs_started']} (SAVESCUM_OFF)", flush=True)
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
                gavg = ({"mean": round(gradbox["sum"] / gradbox["n"], 4), "max": round(gradbox["max"], 4)}
                        if gradbox["n"] else None)
                gradbox.update({"n": 0, "sum": 0.0, "max": 0.0})
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
                counters["curriculum_stepped"] = True
                if args.force_keys == "curriculum" and drv.force_keys():
                    drv.set_force_keys(False)   # runs started from now on play without the key backstops
                    print("# force-keys: off from the first curriculum step-up", flush=True)
                asc_hist = []
                print(f"# curriculum: A{asc} Heart kills {wins}/{tot} -> A{asc + 1}", flush=True)
            pw = progress_window(s, last_s)
            pre_trim = None
            if args.malloc_trim:   # RSS before the trim; "rss_gb" below is after it
                pre_trim = rss_gb()
                malloc_trim()
            row = {
                "time": time.strftime("%Y-%m-%d %H:%M:%S"), "hours": round((wall0 + now - t_start) / 3600, 3),
                "positions_per_s": round((s["evals"] - last_s["evals"]) / dt),
                "cache_hits_per_s": round((s["cache_hits"] - last_s["cache_hits"]) / dt),
                "moves_per_s": round((s["moves"] - last_s["moves"]) / dt),
                "runs_done": counters["runs_done"] + s["runs_done"],
                "runs_window": d_runs,
                "win_rate_window": round(float(d_oc[0]) / max(1, d_runs), 4),
                "mean_floor_window": round((s["floors_sum"] - last_floors) / max(1, d_runs), 2),
                "wins_total": s["wins"],
                "death_floors_window": {int(k): int(v) for k, v in enumerate(d_oc) if v and k},
                "samples_added": replay.added, "replay": len(replay), "replay_gb": round(replay.nbytes() / 2 ** 30, 3),
                **({"replay_dict_used": replay.store.used} if replay.compact else {}),
                "replay_rings": replay.ring_stats(),
                **({"replay_soft_bytes_mean": round(replay.soft_stats[1] / max(1, replay.soft_stats[0]), 2)}
                   if replay.soft_q else {}), "train_steps": counters["step"],
                "trained_samples": counters["trained"], "loss": lavg, "grad_norm": gavg,
                "nonfinite_skips": counters["nonfinite_skips"], "syncs": infer_stats["syncs"],
                "stalls": s["stalls"], "unsupported": s["unsupported"], "knowledge_failures": s["knowledge_failures"], "invalid_actions": s["invalid_actions"], "encode_cut": s["encode_cut"], "encode_cut_ooc": s["encode_cut_ooc"],
                "samples_pending": s["samples_pending"], "rss_gb": rss_gb(),
                "ascension": asc, "asc_runs_window": a_runs,
                "asc_win_rate_window": round(a_wins / max(1, a_runs), 4),
                "asc_mean_floor_window": round(a_floors / max(1, a_runs), 2),
                "asc_win_rate_rolling": round(rolling, 4), "asc_rolling_runs": tot,
                "ooc_roots": s["ooc_roots"], "explore_roots": s["explore_roots"], "forced_picks": s["forced_picks"],
                # cumulative per class: card, deck_edit, relic, potion, event, rest, other_option, other
                "forced_by_class": list(s.get("forced_by_class", [])),
                "explore_attempts_by_class": list(s.get("explore_attempts_by_class", [])),
                # [full, fast] cumulative: searched OOC roots, picks off the best visited mean Q, mean visited-Q spread
                "ooc_searched": list(s["ooc_searched"]), "ooc_not_best_q": list(s["ooc_not_best_q"]),
                "ooc_q_spread_mean": [round(s["ooc_q_spread_sum"][k] / max(1, s["ooc_q_spread_n"][k]), 5) for k in (0, 1)],
                "progress_window": pw,
                # Amber search rules (cumulative): first expansions of OOC edges [deterministic, chance]
                # (--chance-on-reveal), fights started / won inside the search (--cross-combat)
                "ooc_edges_det_chance": list(s["ooc_edges_det_chance"]),
                "tree_fight_starts": s["tree_fight_starts"], "tree_fight_exits": s["tree_fight_exits"],
                "auto_gold": s["auto_gold"],   # --sim-help: reward gold taken automatically (real runs)
                # lowest Heart HP left at the end of any Heart fight so far (None before the first Heart fight);
                # the per-window histogram is in progress_window (heart_hp_00 .. heart_hp_15, 50-HP bins)
                "heart_hp_min": None if s.get("heart_hp_min", -1) < 0 else s["heart_hp_min"],
                # driver memory gauges (current values): node-pool slots and the states they hold, buffer capacities
                **({"mem": dict(s["mem"])} if "mem" in s else {}),
            }
            if fused is not None:   # rows above the big tile that went through forward_packed (cumulative)
                row["fused_long_rows"] = fused.long_rows
            if args.gpu_timing:
                # ms of GPU time per s of wall clock (1000 = that stream busy all the time)
                row["gpu_ms_per_s"] = {k: round((v - last_gpu[k]) / dt, 1) for k, v in gpu_ms.items()}
                last_gpu.update(gpu_ms)
            if args.savescum:   # state for new runs; runs started with it; checks of the search's child vs the real next state
                row["savescum"] = {"active": drv.savescum(), "runs": s["savescum_runs"],
                                   "checks": s["savescum_checks"], "mismatches": s["savescum_mismatches"]}
            if args.force_keys != "off":   # key backstops: state for new runs; real forced moves, narrowed routes (cumulative)
                row["force_keys"] = {"active": drv.force_keys(), "sapphire": s["forced_keys"][0],
                                     "ruby": s["forced_keys"][1], "emerald": s["forced_keys"][2],
                                     "route_masked": s["key_route_masked"]}
            if args.force_rewards:   # real forced moves (cumulative): chests opened, relics taken, card-first relics
                fr = s["forced_rewards"]   # held back during a card decision / taken on leaving the screen
                row["force_rewards"] = {"chests": fr[0], "relics": fr[1], "deferred": fr[2], "on_leave": fr[3]}
            if pre_trim is not None:
                row["rss_gb_pre_trim"] = pre_trim
            row["relics_per_run"], row["deck_per_run"] = per_run_means(pw)
            row["economy_per_run"] = economy_per_run(pw)
            if args.explore_amber:   # forcing attempts, of which c = 0 / infinity; logged natural items, unplayed (0)
                row["explore_amber"] = {k: s["explore_" + k] for k in
                                        ("attempts", "c_zero", "c_inf", "natural", "natural_unplayed")}
            if ema_lam > 0:
                row["value_ema"] = {"halflife": args.value_ema_halflife, "search": ema_search,
                                    "moves": args.value_ema_moves if ema_search else None,
                                    "labelled": ema_stats["samples"],
                                    "real_weight_mean": round(ema_stats["real_weight"] / max(1, ema_stats["samples"]), 4)}
            if args.heart_log > 0:
                drain_heart_log()
                row["heart_log"] = {"records": heart_logged[0], "kills": heart_logged[1]}
            if heart_arms:   # Heart probe: all plays so far (rewritten each report)
                hr = drv.heart_results()
                row["heart_probe_plays"] = len(hr)
                with open(os.path.join(args.out_dir, "heart_probe.jsonl.tmp"), "w") as f:
                    for r in hr:
                        f.write(json.dumps(r) + "\n")
                os.replace(os.path.join(args.out_dir, "heart_probe.jsonl.tmp"),
                           os.path.join(args.out_dir, "heart_probe.jsonl"))
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
        drain_heart_log()
        path, c = save_ckpt(counters["step"], drv.stats(), time.time())
        print(json.dumps({"final_checkpoint": path, "errors": errors, "counters": c}), flush=True)
        metrics.close()
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
