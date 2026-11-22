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

--hp-ema-search (2026-11-21, default off; needs --value-ema-search and Amber's search rules: --chance-on-reveal,
--cross-combat or --sim-help) trains both HP heads on search-backed EMA targets too, built by the driver
(RunConfig::searchEmaHp in apps/az_bench/az_run_driver.h has the definitions). Amber Eye's page does not name the HP
heads' targets: it stores "labels for the outcome and HP distributions, per-floor HP" with the value distributions in
8-bit fixed point, and its value labels are the search / EMA combination; Philipp decided 2026-11-21 to read that as
both HP heads. The search backs up the floor HP softmax (256 classes) and, with --utility amber*, the per-floor
E[HP_f] / 255 next to the outcome distribution (a leaf past the root's floor counts the real HP its path left that
floor with; a run-ending leaf its real HP, 0 on death). The chains use the outcome chain's moves and half-life. Where
the page is silent (Philipp 2026-11-21): the floor HP chain ends with the floor in the real HP (the head asks about
this floor only), and a per-floor target is the real HP once the run has left that floor. The floor HP target is
kept as round(255 p) over its nonzero interval (the driver rounds; read back renormalised), the per-floor targets
as whole HP (round(255 x), one byte per floor). Losses: "hp" and "hp_floor" stay the losses against the real labels (comparable across settings, as
"outcome"); "hp_ema" (soft cross-entropy) and "hp_floor_ema" (masked MSE) are the trained ones. Inference sends the
driver 256 more floats per row. --replay-load takes a window saved without the flag: its samples keep the real HP
labels as their HP targets (one-hot floor HP, real per-floor HP), only new samples get search targets; the reverse
(a window saved with the flag, loaded without) is refused as another layout. A window saved with another
--replay-soft-bytes / --replay-hp-bytes loads too (2026-11-21): its target bytes are laid out again; a smaller ring
keeps the newest samples that fit.
Selection is unchanged.

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
import shutil
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
                 soft_bytes_per_sample=64, hp_runs_per_sample=0.125, hp_soft=False, hp_bytes_per_sample=96,
                 aux_slots=0):
        if hp_soft and not soft_outcome:
            raise ValueError("replay: hp_soft needs soft_outcome")
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
        # --hp-ema-search (hp_soft): the floor HP target of a sample [256] as round(255 p) and, with hp_floors, its
        # per-floor targets [56] as round(255 x) (x = HP / 255: whole HP; masked before the sample's floor, as the
        # labels). Both arrive with the chunk ("hp_target", "hp_floor_target").
        # compress_targets: the floor HP target's nonzero interval (hq_lo, hq_len) follows the sample's outcome bytes
        # in the byte ring (written by set_soft_outcome); otherwise one dense row per sample. A sample without a
        # floor HP target (hq_len 0 / an all-zero row: not set yet, or loaded from a window saved without hp_soft)
        # reads as the one-hot of its real HP; such a loaded sample's per-floor targets are its real labels.
        self.hp_soft = hp_soft
        self.hq_lo = self.hq_len = None   # no arrays without the option: a saved window's layout stays the same
        if hp_soft and self.soft_q:
            self.hq_lo = np.zeros(self.cs, np.uint8)
            self.hq_len = np.zeros(self.cs, np.uint16)
            soft_bytes_per_sample += hp_bytes_per_sample
        elif hp_soft:
            self.meta["hp_target"] = np.zeros((self.cs, HP_CLASSES), np.uint8)
        if hp_soft and hp_floors:
            self.meta["hp_floor_target"] = np.zeros((self.cs, hp_floors), np.uint8)
        self.migrated_hp = 0   # samples loaded from a window saved without hp_soft (load)
        # --aux-fights: per sample the fight-outcome targets [2 * slots] as round(255 x) (slot k: P(death) at 2 k,
        # HP fraction left at 2 k + 1) and a bit mask of the slots it has (0: none, e.g. combat samples). A window
        # saved without them loads with mask 0 (its samples do not train the aux head).
        if aux_slots:
            self.meta["aux_target"] = np.zeros((self.cs, 2 * aux_slots), np.uint8)
            self.meta["aux_mask"] = np.zeros(self.cs, np.uint8)
        self.missing_aux = False   # load: the saved window had no aux arrays
        self.cq = samples * soft_bytes_per_sample if self.soft_q else 0
        self.sq = np.zeros(self.cq, np.uint8)                                       # quantized targets, byte ring
        self.sq_start = np.zeros(self.cs if self.soft_q else 0, np.int64)
        self.sq_lo = np.zeros(self.cs if self.soft_q else 0, np.uint8)               # first stored class
        self.sq_len = np.zeros(self.cs if self.soft_q else 0, np.uint8)              # 0: not set yet (final outcome)
        self.q_head = 0
        # Quantized targets: set in sample order so far (_soft_bytes_evict), and the end of the samples set.
        self.sq_ordered, self.sq_hi = True, 0
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
        arrs += [self.hq_lo, self.hq_len] if self.hq_lo is not None else []
        arrs += [] if self.compact else [self.tok_type, self.ids, self.f]
        if self.soft_outcome is not None:
            arrs.append(self.soft_outcome)
        return sum(a.nbytes for a in arrs) + (self.store.nbytes if self.compact else 0)

    # Scalar state saved with the arrays (save / load).
    _SCALARS = ("i_head", "r_head", "q_head", "s_head", "s_tail", "t_head", "a_head", "added")
    _VIEWS = ("tok_type", "ids", "f")   # compact: views into the token store (saved through the store)

    def _arrays(self):
        """Name -> array of every ring and per-sample array (compact: without the store views)."""
        out = {k: v for k, v in vars(self).items() if isinstance(v, np.ndarray)
               and not (self.compact and k in self._VIEWS)}
        out.update({"meta." + k: v for k, v in self.meta.items()})
        return out

    _AUX_ARRAYS = ("meta.aux_target", "meta.aux_mask")

    def _layout(self):
        """What a saved window must match to be loaded: every array's shape and dtype, and the switches (without the
        aux arrays while checking a window saved without them, missing_aux)."""
        arr = {k: [list(v.shape), str(v.dtype)] for k, v in sorted(self._arrays().items())
               if not (self.missing_aux and k in self._AUX_ARRAYS)}
        return {"arrays": arr, "compact": self.compact, "compress": self.compress, "hp_runs": self.hp_runs,
                "soft_q": self.soft_q, "store_capacity": self.store.capacity if self.compact else 0}

    def save(self, path, extra=None):
        """Writes the window to directory path (one .npy per array, state.json last; written to path + ".tmp" and
        renamed, so a crash leaves no half-written window at path). extra: JSON-able info kept in state.json."""
        self.missing_aux = False   # a window is saved with all of its arrays
        tmp = path + ".tmp"
        if os.path.exists(tmp):
            shutil.rmtree(tmp)
        os.makedirs(tmp)
        with self.lock:
            for k, v in self._arrays().items():
                np.save(os.path.join(tmp, k + ".npy"), v)
            if self.compact:
                t, ids, f = self.store.views()
                np.save(os.path.join(tmp, "store.tok_type.npy"), t)
                np.save(os.path.join(tmp, "store.ids.npy"), ids)
                np.save(os.path.join(tmp, "store.f.npy"), f.view(np.uint16))
                np.save(os.path.join(tmp, "store.refs.npy"), self.store.refs())
            state = {"layout": self._layout(), "scalars": {k: int(getattr(self, k)) for k in self._SCALARS},
                     "soft_stats": list(self.soft_stats), "extra": extra or {}}
        with open(os.path.join(tmp, "state.json"), "w") as fh:
            json.dump(state, fh)
        if os.path.exists(path):
            shutil.rmtree(path)
        os.replace(tmp, path)

    def check_layout(self, path):
        """Raises ValueError when the window saved at path has another layout than this replay (--window, ring or
        compact options changed); returns state.json."""
        with open(os.path.join(path, "state.json")) as fh:
            state = json.load(fh)
        # --aux-fights: a window saved without the aux arrays is compared (and loaded) without them
        mine_aux = any(k in self._arrays() for k in self._AUX_ARRAYS)
        saved_arr = state["layout"].get("arrays", {})
        self.missing_aux = mine_aux and not any(k in saved_arr for k in self._AUX_ARRAYS)
        if not mine_aux:   # saved with --aux-fights, loaded without: its aux arrays are not read
            for k in self._AUX_ARRAYS:
                saved_arr.pop(k, None)
        if (state["layout"] != self._layout() and not self._migrates_hp(state["layout"])
                and not self._resizes_sq(state["layout"])):
            raise ValueError(f"replay load {path}: saved layout differs from this run's (--window, ring or compact "
                             "options changed)")
        return state

    _HP_SOFT_ARRAYS = ("hq_lo", "hq_len", "meta.hp_target", "meta.hp_floor_target")

    def _migrates_hp(self, saved):
        """True when `saved` (a layout) is this replay's layout without hp_soft: the same arrays but for the HP
        target arrays, with a target byte ring of any size (load then lays the bytes out again)."""
        if not self.hp_soft:
            return False
        mine = self._layout()
        a = {k: v for k, v in mine["arrays"].items() if k not in self._HP_SOFT_ARRAYS}
        b = dict(saved.get("arrays", {}))
        if self.soft_q:
            if b.get("sq", [None, None])[1] != "uint8":
                return False
            a.pop("sq")
            b.pop("sq")
        return a == b and all(mine[k] == saved.get(k) for k in mine if k != "arrays")

    def _resizes_sq(self, saved):
        """True when `saved` (a layout) is this replay's but for the size of the target byte ring
        (--replay-soft-bytes / --replay-hp-bytes changed): load then lays the bytes out again."""
        mine = self._layout()
        if not self.soft_q or saved.get("arrays", {}).get("sq", [None, None])[1] != "uint8":
            return False
        a, b = dict(mine["arrays"]), dict(saved["arrays"])
        a.pop("sq")
        b.pop("sq")
        return a == b and all(mine[k] == saved.get(k) for k in mine if k != "arrays")

    def load(self, path):
        """Restores a window saved by save into this (empty) replay; its layout (--window and the ring / compact
        options) must be the same. Returns state.json's extra."""
        state = self.check_layout(path)
        with self.lock:
            if len(self) or self.added:
                raise ValueError("replay load: the window is not empty")
            self.load_partial = True   # until the whole window is in (a failure in between leaves it unusable)
            # Another layout that check_layout allowed: saved without hp_soft (migrate), or only with another
            # target byte ring size (resize).
            resize = state["layout"] != self._layout() and self._resizes_sq(state["layout"])
            migrate = state["layout"] != self._layout() and not resize
            for k, v in self._arrays().items():
                if (migrate and k in self._HP_SOFT_ARRAYS) or ((migrate or resize) and k == "sq"):
                    continue
                if self.missing_aux and k in self._AUX_ARRAYS:   # saved without --aux-fights: mask 0
                    continue
                np.copyto(v, np.load(os.path.join(path, k + ".npy"), mmap_mode="r"))
            if self.compact:
                ld = lambda n: np.ascontiguousarray(np.load(os.path.join(path, f"store.{n}.npy"), mmap_mode="r"))
                self.store.restore(ld("tok_type"), ld("ids"), ld("f"), ld("refs"))
            for k, v in state["scalars"].items():
                setattr(self, k, v)
            self.soft_stats = list(state["soft_stats"])
            if migrate:
                self._migrate_hp(path)
            elif resize:
                self._relay_bytes(path)
            if self.soft_q:   # the saved window does not say in which order its targets were set: look once
                self.sq_ordered, self.sq_hi = self._sq_starts_rise(), self.s_head
            self.load_partial = False
        return state["extra"]

    def _relay_bytes(self, path, block=1 << 18):
        """The live samples' target bytes (outcome bytes, then floor HP bytes) of the window saved at path, laid out
        again from the start of this replay's byte ring, whose size differs (caller holds the lock; the per-sample
        arrays are loaded). A smaller ring keeps the newest samples that fit."""
        old = np.load(os.path.join(path, "sq.npy"), mmap_mode="r")

        def lens(j):   # a sample's bytes: outcome interval + floor HP interval (none while its target is unset)
            ln = self.sq_len[j].astype(np.int64)
            return ln + (np.where(ln > 0, self.hq_len[j].astype(np.int64), 0) if self.hq_len is not None else 0)

        live = self.s_head - self.s_tail
        over = np.cumsum(lens((self.s_tail + np.arange(live)) % self.cs)[::-1])[::-1] > self.cq
        if over.any():
            self._evict(int(np.flatnonzero(over)[-1]) + 1)
            live = self.s_head - self.s_tail
        head = 0
        for k in range(0, live, block):
            j = (self.s_tail + k + np.arange(min(block, live - k))) % self.cs
            ln = lens(j)
            c = np.arange(int(ln.sum())) - np.repeat(np.cumsum(ln) - ln, ln)
            data = np.asarray(old[(np.repeat(self.sq_start[j], ln) + c) % len(old)]) if len(c) else np.zeros(0, np.uint8)
            self.sq[head:head + len(data)] = data
            self.sq_start[j] = head + np.cumsum(ln) - ln
            head += len(data)
        self.q_head = head

    def _migrate_hp(self, path, block=1 << 18):
        """After loading a window saved without hp_soft (caller holds the lock): the live samples' outcome bytes laid
        out again in this replay's byte ring (_relay_bytes), no floor HP target for them (hq_len 0: read as the real
        HP) and their per-floor targets set to their real labels."""
        if self.soft_q:
            self.hq_len[:] = 0
            self._relay_bytes(path, block)
        live = self.s_head - self.s_tail
        if "hp_floor_target" in self.meta:
            for k in range(0, live, block):
                j = (self.s_tail + k + np.arange(min(block, live - k))) % self.cs
                real = self.hpr[self.hp_ref[j] % self.cr] if self.hp_runs else self.meta["hp_floor"][j]
                self.meta["hp_floor_target"][j] = np.clip(real, 0, 255).astype(np.uint8)
        self.migrated_hp = live

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

    SCAN_BLOCK = 4096   # samples read per step of the eviction scans below (tests lower it)

    def _first_keep(self, live, keep):
        """Number of oldest samples before the first one for which keep(ring rows) holds (live when none does).
        Reads the window from its old end in blocks and stops at that sample: the same result as testing all live
        samples, at a cost that does not grow with the window."""
        k = 0
        while k < live:
            n = min(self.SCAN_BLOCK, live - k)
            ok = keep((self.s_tail + k + np.arange(n)) % self.cs)
            if ok.any():
                return k + int(np.argmax(ok))
            k += n
        return live

    def _soft_bytes_evict(self, live, limit):
        """Number of oldest samples to evict so that no live sample's target bytes start before limit (they are
        about to be overwritten): through the last such sample among the live oldest samples. While targets were
        set in sample order (sq_ordered) their byte starts rise with the sample index, so the scan stops at the
        first block holding a set sample at or after limit; otherwise all live samples are tested."""
        if not self.sq_ordered:
            j = (self.s_tail + np.arange(live)) % self.cs
            bad = (self.sq_len[j] > 0) & (self.sq_start[j] < limit)
            return int(np.flatnonzero(bad)[-1]) + 1 if bad.any() else 0
        k = m = 0
        while k < live:
            n = min(self.SCAN_BLOCK, live - k)
            j = (self.s_tail + k + np.arange(n)) % self.cs
            is_set = self.sq_len[j] > 0
            bad = is_set & (self.sq_start[j] < limit)
            if bad.any():
                m = k + int(np.flatnonzero(bad)[-1]) + 1
            if (is_set & ~bad).any():
                break
            k += n
        return m

    def _sq_starts_rise(self):
        """True when the byte starts of the live samples with a set target rise with the sample index."""
        j = (self.s_tail + np.arange(self.s_head - self.s_tail)) % self.cs
        st = self.sq_start[j][self.sq_len[j] > 0]
        return bool((np.diff(st) >= 0).all())

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
                def keep(j):
                    ok = ((self.idx_start[j] >= self.i_head + n_ref - self.ci)
                          & (self.act_start[j] >= self.a_head + n_act - self.ca))
                    if self.hp_runs:
                        ok &= self.hp_ref[j] >= self.r_head + n_run - self.cr
                    return ok
                self._evict(max(self._first_keep(live, keep), live + S - self.cs))
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
            v = s[k]
            if k == "hp_floor_target":   # HP / 255 (-1 = masked) -> whole HP
                v = np.rint(np.clip(np.asarray(v, np.float32), 0.0, 1.0) * 255.0).astype(np.uint8)
            self._put(ring, self.s_head, v)
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

    def set_soft_outcome(self, first, targets, hp_q=None):
        """Stores the EMA outcome targets of the samples first .. first + len(targets) - 1 (absolute counters, as
        add returned); samples already evicted are skipped. hp_soft with compress_targets: hp_q [S, 256] (uint8,
        the chunk's "hp_target") are their floor HP targets, stored with them."""
        if self.hq_lo is not None and hp_q is None:
            raise ValueError("replay: hp_soft with compress_targets needs the floor HP targets (hp_q)")
        if self.soft_q:
            return self._set_soft_q(first, targets, hp_q if self.hq_lo is not None else None)
        with self.lock:
            lo = max(first, self.s_tail)
            if lo < first + len(targets):
                self._put(self.soft_outcome, lo, np.asarray(targets[lo - first:], np.float16))

    def _set_soft_q(self, first, targets, hp_q=None):
        C = OUTCOME_CLASSES
        q = np.rint(np.asarray(targets, np.float32) * 255.0).clip(0, 255).astype(np.uint8)
        nz = q > 0
        has = nz.any(1)
        a = np.argmax(nz, 1)
        b = C - 1 - np.argmax(nz[:, ::-1], 1)
        ln = np.where(has, b - a + 1, 0)
        cols = np.arange(C)
        keep = (cols[None, :] >= a[:, None]) & (cols[None, :] <= b[:, None]) & has[:, None]
        ln_out = ln
        if hp_q is not None:   # each sample's bytes: its outcome interval, then its floor HP interval
            hp_q = np.asarray(hp_q, np.uint8)
            if hp_q.shape != (len(q), HP_CLASSES) or not has.all() or not (hp_q > 0).any(1).all():
                raise ValueError("replay: floor HP targets need one nonzero [256] row per sample with an outcome target")
            hz = hp_q > 0
            ha = np.argmax(hz, 1)
            hb = HP_CLASSES - 1 - np.argmax(hz[:, ::-1], 1)
            hcols = np.arange(HP_CLASSES)
            keep = np.concatenate([keep, (hcols[None, :] >= ha[:, None]) & (hcols[None, :] <= hb[:, None])], 1)
            q = np.concatenate([q, hp_q], 1)
            ln = ln + (hb - ha + 1)
        data = q[keep]
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
            if lo < self.sq_hi:   # not in sample order: byte starts no longer rise with the sample index
                self.sq_ordered = False
            self.sq_hi = max(self.sq_hi, first + len(targets))
            live = lo - self.s_tail
            if live:   # only samples before lo: the chunk's own samples hold no bytes yet
                self._evict(self._soft_bytes_evict(live, self.q_head + n - self.cq))
            starts = self.q_head + np.concatenate([[0], np.cumsum(ln[k0:])[:-1]]).astype(np.int64)
            self._put(self.sq, self.q_head, data)
            self._put(self.sq_start, lo, starts)
            self._put(self.sq_lo, lo, a[k0:].astype(np.uint8))
            self._put(self.sq_len, lo, ln_out[k0:].astype(np.uint8))
            if hp_q is not None:
                self._put(self.hq_lo, lo, ha[k0:].astype(np.uint8))
                self._put(self.hq_len, lo, (hb - ha + 1)[k0:].astype(np.uint16))
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
            if self.hq_lo is not None:   # floor HP targets: the bytes after the sample's outcome bytes
                ht = np.zeros((B, HP_CLASSES), np.float32)
                hl = np.where(ln > 0, self.hq_len[j].astype(np.int64), 0)
                none = np.flatnonzero(hl == 0)   # no floor HP target: the real HP
                ht[none, b["hp_end"][none].astype(np.int64).clip(0, HP_CLASSES - 1)] = 1.0
                r = np.repeat(np.arange(B), hl)
                c = np.arange(int(hl.sum())) - np.repeat(np.cumsum(hl) - hl, hl)
                ht[r, np.repeat(self.hq_lo[j].astype(np.int64), hl) + c] = (
                    self.sq[(np.repeat(self.sq_start[j] + ln, hl) + c) % self.cq].astype(np.float32))
                b["hp_target"] = ht / ht.sum(-1, keepdims=True)
        if "hp_target" in self.meta:   # dense rows of round(255 p)
            ht = b["hp_target"].astype(np.float32)
            none = np.flatnonzero(ht.sum(-1) == 0)   # no floor HP target: the real HP
            ht[none, b["hp_end"][none].astype(np.int64).clip(0, HP_CLASSES - 1)] = 1.0
            b["hp_target"] = ht / ht.sum(-1, keepdims=True)
        if "hp_floor_target" in b:   # whole HP -> HP / 255, -1 before the sample's floor
            t = b["hp_floor_target"].astype(np.float32) / 255.0
            fl = np.clip(b["floor"].astype(np.int64), 1, t.shape[1])
            b["hp_floor_target"] = np.where(np.arange(1, t.shape[1] + 1)[None, :] >= fl[:, None], t, -1.0).astype(np.float32)
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

_SEARCH_CONSTS = {}   # (device, dtype) -> (floor value per outcome class, HP per class); see search_values


def search_consts(device, dtype):
    """search_values' two constant vectors on device, built once. Building them per call cost the inference thread
    a wait for the GPU in every batch: an item assignment on a GPU tensor (floors[0] = 57.0) copies a CPU scalar
    synchronously, which waits for everything issued on the stream before it (the batch's whole forward)."""
    key = (device, dtype)
    c = _SEARCH_CONSTS.get(key)
    if c is None:
        with torch.inference_mode(False):   # plain tensors: usable in and outside inference mode
            floors = torch.arange(OUTCOME_CLASSES, dtype=dtype)
            floors[0] = 57.0
            c = (floors.to(device), torch.arange(HP_CLASSES, dtype=dtype).to(device))
        _SEARCH_CONSTS[key] = c
    return c


def search_values(outcome_logits, hp_logits):
    """F = E[final floor] / 57 (a win counts 57; class 0 = win, f = death on floor f) and E[HP] from the heads."""
    p = torch.softmax(outcome_logits.float(), -1)
    floors, hp_steps = search_consts(p.device, p.dtype)
    Fv = (p * floors).sum(-1) / 57.0
    ph = torch.softmax(hp_logits.float(), -1)
    ehp = (ph * hp_steps).sum(-1)
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


def hp_floor_target_loss(pred, target):
    """hp_floor_loss against --hp-ema-search targets [B, 56], already HP / 255 (-1 = masked)."""
    m = (target >= 0).float()
    return (((pred.float() - target.float().clamp(0, 1)) ** 2) * m).sum() / m.sum().clamp(min=1)


def soft_policy_target(policy, a_mask):
    """Amber Eye / KataGo soft policy target: the policy target p raised to the power 1/4 and renormalised over the
    legal actions (rows without a policy target stay 0)."""
    t = policy.float().clamp(min=0).pow(0.25) * a_mask
    return t / t.sum(-1, keepdim=True).clamp(min=1e-12)


def kickstart_targets(b, t_out, lam):
    """--kickstart-mix (Amber Eye "kickstarting": the teacher's prediction mixed into the training labels): the targets
    of batch b as (1 - lam) * label + lam * teacher prediction on the same sample, t_out = the teacher's
    (policy logits, outcome logits, HP logits, per-floor HP) on b. Returns a new batch dict: "policy" (rows with a
    policy target), "soft_outcome" (the EMA target or the final outcome), "hp_soft" (HP classes) and "hp_floor_t"
    (per-floor HP / 255, masked as the labels) mixed; the original labels stay under their keys for the logged
    losses ("policy_label", "hp_end", "outcome", "hp_floor")."""
    tl, to, th, thf = (x.float() for x in t_out[:4])
    has = b["has_policy"].bool()[:, None]
    tp = torch.softmax(tl.masked_fill(~b["a_mask"], -1e4), -1) * b["a_mask"]
    out = dict(b)
    out["policy_label"] = b["policy"]
    out["policy"] = torch.where(has, (1 - lam) * b["policy"].float() + lam * tp, b["policy"].float())
    C = to.shape[-1]
    base = b["soft_outcome"].float() if "soft_outcome" in b else F.one_hot(
        b["outcome"].long().clamp(0, C - 1), C).float()
    out["soft_outcome"] = (1 - lam) * base + lam * torch.softmax(to, -1)
    H = th.shape[-1]
    out["hp_soft"] = ((1 - lam) * F.one_hot(b["hp_end"].long().clamp(0, H - 1), H).float()
                      + lam * torch.softmax(th, -1))
    if "hp_floor" in b:
        lab = b["hp_floor"]
        out["hp_floor_t"] = torch.where(lab >= 0, (1 - lam) * lab.float().clamp(0, 255) / 255.0
                                        + lam * thf.clamp(0, 1), torch.full_like(thf, -1.0))
    return out


AUX_SLOTS = 5   # --aux-fights: boss, elites 1..3, hallway (az_run_driver.h kAuxSlots)


def aux_fight_rows(ch):
    """The fight starts of a take_samples chunk (--aux-fights) as (tok_type, ids, f, tok_off, sample, slot): the
    rows' tokens back to back (compact chunks resolved through each row's sample dictionary), row r's tokens
    tok_off[r] .. tok_off[r + 1] - 1, its sample and its slot."""
    off = np.asarray(ch["aux_off"], np.int64)
    sample = np.repeat(np.arange(len(off) - 1), np.diff(off))
    tok_off = np.asarray(ch["aux_tok_off"], np.int64)
    if "aux_tok_idx" in ch:
        nt = np.diff(tok_off)
        src = np.repeat(np.asarray(ch["tok_base"], np.int64)[sample], nt) + ch["aux_tok_idx"].astype(np.int64)
        tt, ids, f = ch["tok_type"][src], ch["ids"][src], ch["f"][src]
    else:
        tt, ids, f = ch["aux_tok_type"], ch["aux_ids"], ch["aux_f"]
    return tt, ids, f, tok_off, sample, np.asarray(ch["aux_slot"], np.int64)


def aux_fight_batch(tt, ids, f, tok_off, rows):
    """forward_flat's layout for the fight-start rows `rows` (one dummy action each: the heads used here do not
    read actions)."""
    B = len(rows)
    nt = (tok_off[rows + 1] - tok_off[rows]).astype(np.int64)
    T = max(8, -(-int(nt.max()) // 8) * 8)
    r = np.repeat(np.arange(B), nt)
    c = np.arange(int(nt.sum())) - np.repeat(np.cumsum(nt) - nt, nt)
    src = np.repeat(tok_off[rows], nt) + c
    b = {"tok_type": np.zeros((B, T), np.int64), "ids": np.zeros((B, T, N_CAT), np.int64),
         "f": np.zeros((B, T, N_FLOAT), np.float16), "mask": np.zeros((B, T), bool),
         "a_type": np.zeros((B, 1), np.int64), "a_src": np.full((B, 1), -1, np.int64),
         "a_tgt": np.full((B, 1), -1, np.int64), "a_f": np.zeros((B, 1, N_ACT_FEAT), np.float16),
         "a_mask": np.ones((B, 1), bool)}
    b["tok_type"][r, c] = tt[src]
    b["ids"][r, c] = ids[src]
    b["f"][r, c] = f[src]
    b["mask"][r, c] = True
    return b


def aux_fight_labels(hp_probs, max_hp, sample, slot, S):
    """--aux-fights targets of S samples from the floor HP head's distributions hp_probs [R, 256] of their fight
    starts (row r of sample sample[r], slot slot[r]): per slot P(death) = P(HP 0 at the end of the floor) and the
    expected HP left / the sample's max HP, averaged over a slot's rows (the hallway fights), as round(255 x)
    [S, 2 * AUX_SLOTS] uint8, and the bit mask of the slots present [S] uint8."""
    p = np.asarray(hp_probs, np.float64)
    pd = p[:, 0]
    frac = np.clip((p * np.arange(p.shape[1])).sum(-1) / np.maximum(1, np.asarray(max_hp, np.float64)[sample]), 0, 1)
    key = sample * AUX_SLOTS + slot
    n = np.bincount(key, minlength=S * AUX_SLOTS).astype(np.float64)
    sd = np.bincount(key, pd, minlength=S * AUX_SLOTS)
    sf = np.bincount(key, frac, minlength=S * AUX_SLOTS)
    have = n > 0
    t = np.zeros((S * AUX_SLOTS, 2), np.float64)
    t[have, 0] = sd[have] / n[have]
    t[have, 1] = sf[have] / n[have]
    target = np.rint(np.clip(t, 0, 1) * 255).astype(np.uint8).reshape(S, 2 * AUX_SLOTS)
    mask = (have.reshape(S, AUX_SLOTS) * (1 << np.arange(AUX_SLOTS))).sum(-1).astype(np.uint8)
    return target, mask


def aux_fight_loss(aux_out, target, mask):
    """Binary cross-entropy of the aux head's logits [B, 2 * AUX_SLOTS] against the soft targets (uint8 / 255),
    over the slots each sample has (mask bits); summed over the two outputs, mean over the present slots."""
    B = aux_out.shape[0]
    lg = aux_out.float().view(B, AUX_SLOTS, 2)
    t = target.float().view(B, AUX_SLOTS, 2) / 255.0
    m = ((mask.long()[:, None] >> torch.arange(AUX_SLOTS, device=mask.device)) & 1).float()
    l = F.binary_cross_entropy_with_logits(lg, t, reduction="none").sum(-1)
    return (l * m).sum() / m.sum().clamp(min=1)


def losses(net, b, w_policy, w_outcome, w_hp, w_hp_floor=0.0, w_soft_policy=0.0, w_aux=0.0):
    logits, outcome, hp, hpf, *soft = net(b)
    logp = torch.log_softmax(logits.float().masked_fill(~b["a_mask"], -1e4), -1)
    has = b["has_policy"].bool()
    pol = -(b["policy"] * logp).sum(-1)
    l_pol = (pol * has).sum() / has.sum().clamp(min=1)
    kick = "policy_label" in b   # kickstart_targets: train on the mixed targets, log the losses to the labels
    l_pol_label = ((-(b["policy_label"] * logp).sum(-1) * has).sum() / has.sum().clamp(min=1)) if kick else l_pol
    l_soft = None
    if w_soft_policy > 0:   # --w-soft-policy: soft head (AmberNet(soft_policy=True), training mode) on p^(1/4)
        slogp = torch.log_softmax(soft[0].float().masked_fill(~b["a_mask"], -1e4), -1)
        spol = -(soft_policy_target(b["policy"], b["a_mask"]) * slogp).sum(-1)
        l_soft = (spol * has).sum() / has.sum().clamp(min=1)
    l_out = F.cross_entropy(outcome.float(), b["outcome"].long())
    l_hp = F.cross_entropy(hp.float(), b["hp_end"].long().clamp(0, HP_CLASSES - 1))
    parts = {"policy": l_pol_label.detach(), "outcome": l_out.detach(), "hp": l_hp.detach()}
    if "hp_soft" in b:
        l_hp = -(b["hp_soft"] * torch.log_softmax(hp.float(), -1)).sum(-1).mean()
    if "soft_outcome" in b:   # --value-ema-halflife: train on the EMA target; "outcome" stays the final-outcome CE
        l_ema = -(b["soft_outcome"] * torch.log_softmax(outcome.float(), -1)).sum(-1).mean()
        parts["outcome_ema"] = l_ema.detach()
        l_out = l_ema
    if "hp_target" in b:   # --hp-ema-search: train on the search EMA target; "hp" stays the real-HP CE
        l_hp = -(b["hp_target"] * torch.log_softmax(hp.float(), -1)).sum(-1).mean()
        parts["hp_ema"] = l_hp.detach()
    total = w_policy * l_pol + w_outcome * l_out + w_hp * l_hp
    if l_soft is not None:
        total = total + w_soft_policy * l_soft
        parts["soft_policy"] = l_soft.detach()
    if "hp_floor" in b:
        l_hpf = hp_floor_loss(hpf, b["hp_floor"])
        parts["hp_floor"] = l_hpf.detach()
        if "hp_floor_target" in b:   # --hp-ema-search: train on the search EMA targets; "hp_floor" stays the real one
            l_hpf = hp_floor_target_loss(hpf, b["hp_floor_target"])
            parts["hp_floor_ema"] = l_hpf.detach()
        if "hp_floor_t" in b:   # kickstart: train on the mixed per-floor target, log the loss to the label
            m = (b["hp_floor_t"] >= 0).float()
            l_tr = (((hpf.float() - b["hp_floor_t"].clamp(min=0)) ** 2) * m).sum() / m.sum().clamp(min=1)
            total = total + w_hp_floor * l_tr
        else:
            total = total + w_hp_floor * l_hpf
    if "aux_mask" in b and getattr(net, "aux_out", None) is not None:   # --aux-fights
        l_aux = aux_fight_loss(net.aux_out, b["aux_target"], b["aux_mask"])
        parts["aux"] = l_aux.detach()
        total = total + w_aux * l_aux
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


def parse_cpu_list(text):
    """A CPU list as taskset / sysfs write it ("5,11", "0-3", "0-1,6") -> set of ints."""
    cpus = set()
    for part in text.strip().split(","):
        part = part.strip()
        if not part:
            continue
        lo, _, hi = part.partition("-")
        cpus.update(range(int(lo), int(hi or lo) + 1))
    return cpus


def pin_inference_cpus(spec, allowed):
    """--pin-inference: the inference thread's logical CPUs. spec is a CPU list or "auto" (the SMT siblings of the
    highest-numbered allowed CPU: one physical core). They must be allowed CPUs and leave at least one for the other
    threads."""
    allowed = set(allowed)
    if spec == "auto":
        top = max(allowed)
        try:
            with open(f"/sys/devices/system/cpu/cpu{top}/topology/thread_siblings_list") as fh:
                cpus = parse_cpu_list(fh.read()) & allowed
        except (OSError, ValueError):
            cpus = {top}
    else:
        cpus = parse_cpu_list(spec)
    if not cpus:
        raise ValueError("no CPU given")
    if not cpus <= allowed:
        raise ValueError(f"CPUs {sorted(cpus - allowed)} are not in this process's affinity {sorted(allowed)}")
    if not allowed - cpus:
        raise ValueError("no CPU left for the other threads")
    return cpus


def batch_done(ev):
    """--early-finish: whether a launched inference batch is finished (ev: the CUDA event recorded after its last
    output copy; None without a stream, where the forward has already returned)."""
    return ev is None or ev.query()


def pin_threads(infer_tid, infer_cpus, other_cpus):
    """Sets the CPU affinity of every thread of this process: thread infer_tid (native id) to infer_cpus, all others
    to other_cpus. Threads that end meanwhile are skipped. Returns the number of other threads set."""
    n = 0
    for name in os.listdir("/proc/self/task"):
        tid = int(name)
        try:
            os.sched_setaffinity(tid, infer_cpus if tid == infer_tid else other_cpus)
            n += tid != infer_tid
        except OSError:
            pass
    return n


def lap(box, key, t):
    """Phase timers: adds the wall time since t to box[key]; returns now."""
    now = time.perf_counter()
    box[key] += now - t
    return now


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


def enemy_gate_check(train_net, infer, replay, args, dev, hp_floors):
    """--check-enemy-gate: see its help. Returns the result dict."""
    if not args.enemy_tokens or len(replay) == 0:
        raise SystemExit("--check-enemy-gate needs --enemy-tokens and a loaded window (--replay-load)")
    cuda = dev.type == "cuda"
    d, layers = train_net.type_emb.weight.shape[1], len(train_net.trunk.layers)
    base = amber_net.AmberNet(d=d, layers=layers, hp_floors=hp_floors, soft_policy=train_net.pol_soft is not None,
                              aux_slots=AUX_SLOTS if train_net.aux_fight is not None else 0).to(dev)
    base.load_state_dict(train_net.state_dict())
    base.sdpa = True
    base_inf = copy.deepcopy(base).eval()
    base_inf.sdpa = True
    for k in ("varlen_attn", "fused_layer", "row_mean", "packed_heads"):
        setattr(base_inf, k, getattr(infer, k))
    if cuda:
        base_inf = base_inf.half()
    rng = np.random.default_rng(12345)
    names = ("policy", "outcome", "hp", "hp_floor")
    # max |difference| per head: train / infer = gated net on the states vs the net without encounter parts on the
    # stripped states, split by rows with and without encounter tokens; infer_noise = the inference net vs the fp32
    # training net, both without encounter parts on the stripped states (fp16 noise floor of the comparison)
    tags = ("train_enc_rows", "train_other_rows", "infer_enc_rows", "infer_other_rows", "infer_noise",
            "infer_compiled",   # infer_compiled: torch.compile(infer) vs infer, both gated (only with --compile)
            "train_kernel", "train_kernel_bf16")   # --enemy-train-kernel: the training net with its kernels vs the
    # padded SDPA path, in training mode, fp32 (kernel dots in full fp32, AZ_TRAIN_ATTN_IEEE) and under bf16 autocast
    # (as the trainer runs; both paths round to bf16, so about one bf16 step of each head's output scale)
    run_c = torch.compile(copy.deepcopy(infer)) if args.compile else None
    diff = {t: {k: 0.0 for k in names} for t in tags}
    nonfinite = {"train": 0, "infer": 0}   # non-finite outputs of the gated nets
    rows = enc_rows = 0

    def cmp(tag, a, b_, mask_a, sel=None):
        for k, x, y in zip(names, a, b_):
            x, y = x.float(), y.float()
            if sel is not None:
                x, y = x[sel], y[sel]
            if k == "policy":
                m = mask_a if sel is None else mask_a[sel]
                x, y = x[m], y[m]
            diff[tag][k] = max(diff[tag][k], float((x - y).abs().max()) if x.numel() else 0.0)

    def packed(bt):   # forward_packed's inputs on the flat batch (as the inference thread packs them)
        pk, inv = amber_net.pack_index(bt["mask"], 16, inverse=True)
        return dict(bt, pack_idx=pk, unpack_idx=inv, seq_off=amber_net.seq_offsets(bt["mask"]),
                    act_idx=torch.nonzero(bt["a_mask"].reshape(-1)).squeeze(1))

    train_net.eval()
    with torch.no_grad():
        for _ in range(args.check_enemy_gate):
            bt = to_torch(replay.sample(rng, args.train_batch), dev)
            st = amber_net.strip_encounters(bt)
            rows += int(bt["mask"].shape[0])
            has = bt["mask"].sum(1) != st["mask"].sum(1)
            enc_rows += int(has.sum())
            a_, b_ = train_net(bt), base(st)
            nonfinite["train"] += sum(int((~torch.isfinite(o.float())).sum()) for o in a_[1:4])
            cmp("train_enc_rows", a_, b_, bt["a_mask"], has)
            cmp("train_other_rows", a_, b_, bt["a_mask"], ~has)
            hb = {k: (v.half() if cuda and v.is_floating_point() else v) for k, v in bt.items()}
            hs = {k: (v.half() if cuda and v.is_floating_point() else v) for k, v in st.items()}
            ai, bi = infer(packed(hb)), base_inf(packed(hs))
            nonfinite["infer"] += sum(int((~torch.isfinite(o.float())).sum()) for o in ai[1:4])
            cmp("infer_enc_rows", ai, bi, bt["a_mask"], has)
            cmp("infer_other_rows", ai, bi, bt["a_mask"], ~has)
            cmp("infer_noise", bi, b_, bt["a_mask"])
            if run_c is not None:
                xc = packed(hb)
                for k in ("act_idx", "pack_idx"):
                    torch._dynamo.mark_dynamic(xc[k], 0)
                ci = run_c(xc)
                nonfinite["infer"] += sum(int((~torch.isfinite(o.float())).sum()) for o in ci[1:4])
                cmp("infer_compiled", ci, ai, bt["a_mask"])
    train_net.train()
    grad_rel = {}   # --enemy-train-kernel: per parameter max |grad kernel - grad SDPA| / max |grad SDPA| (fp32)
    if train_net.train_attn is not None and args.train_packed:
        ta = train_net.train_attn
        # the fp32 comparison runs the kernels' dots in full fp32 (their TF32 default sits at the fp16 noise level,
        # infer_noise); bf16 inputs are unaffected
        ieee_env = os.environ.get("AZ_TRAIN_ATTN_IEEE")
        os.environ["AZ_TRAIN_ATTN_IEEE"] = "1"
        for i in range(min(3, args.check_enemy_gate)):
            bt = to_torch(replay.sample(rng, args.train_batch), dev)
            bt = dict(bt, pack_idx=amber_net.pack_index(bt["mask"], 16))
            res = []
            for use in (ta, None):
                train_net.train_attn = use
                train_net.zero_grad()
                o = train_net(bt)
                loss = (o[0].float().masked_fill(~bt["a_mask"], 0).sum() + o[1].float().logsumexp(-1).sum()
                        + o[2].float().logsumexp(-1).sum() + o[3].float().sum())
                loss.backward()
                res.append(([x.detach() for x in o],
                            {n_: p_.grad.detach().clone() for n_, p_ in train_net.named_parameters()
                             if p_.grad is not None}))
                if cuda:
                    with torch.no_grad(), torch.autocast("cuda", dtype=torch.bfloat16):
                        res[-1] = res[-1] + ([x.detach() for x in train_net(bt)],)
            cmp("train_kernel", res[0][0], res[1][0], bt["a_mask"])
            if cuda:
                cmp("train_kernel_bf16", res[0][2], res[1][2], bt["a_mask"])
            for n_, gs in res[1][1].items():
                gk = res[0][1].get(n_)
                if gk is None:
                    grad_rel[n_] = float("inf")
                    continue
                rel = float((gk - gs).abs().max()) / max(float(gs.abs().max()), 1e-12)
                grad_rel[n_] = max(grad_rel.get(n_, 0.0), rel)
        train_net.train_attn = ta
        train_net.zero_grad()
        if ieee_env is None:
            os.environ.pop("AZ_TRAIN_ATTN_IEEE", None)
        else:
            os.environ["AZ_TRAIN_ATTN_IEEE"] = ieee_env

    def step_ms(net, strip):
        net.train()
        amp = torch.autocast(dev.type, dtype=torch.bfloat16, enabled=cuda)
        times = []
        for i in range(13):
            bt = to_torch(replay.sample(rng, args.train_batch), dev)
            if strip:
                bt = amber_net.strip_encounters(bt)
            if args.train_packed:
                bt = dict(bt, pack_idx=amber_net.pack_index(bt["mask"], 16))
            if cuda:
                torch.cuda.synchronize()
            t0 = time.perf_counter()
            with amp:
                o = net(bt)
                loss = o[0].float().masked_fill(~bt["a_mask"], 0).sum() + o[1].float().logsumexp(-1).sum()
            loss.backward()
            if cuda:
                torch.cuda.synchronize()
            if i >= 3:
                times.append(1000 * (time.perf_counter() - t0))
            net.zero_grad(set_to_none=True)
        return round(float(np.median(times)), 2)

    res = {"batches": args.check_enemy_gate, "rows": rows, "rows_with_encounter_tokens": enc_rows,
           "gates": [round(float(x), 4) for x in train_net.enemy_gate.detach().float().cpu()],
           "max_abs_diff": diff, "nonfinite_outputs": nonfinite,
           "train_step_ms": {"without_encounter_parts": step_ms(base, True), "with": step_ms(train_net, False)}}
    if grad_rel:   # --enemy-train-kernel: worst parameters first
        top = sorted(grad_rel.items(), key=lambda kv: -kv[1])
        res["train_kernel_grad_rel_max"] = round(top[0][1], 6)
        res["train_kernel_grad_rel_top"] = {n_: round(v, 6) for n_, v in top[:8]}
    if train_net.enemy_bias is not None:   # the same with the gates only (no class bias)
        tab, train_net.enemy_bias = train_net.enemy_bias, None
        try:
            res["train_step_ms"]["with_gates_only"] = step_ms(train_net, False)
        finally:
            train_net.enemy_bias = tab
    train_net.zero_grad(set_to_none=True)
    return res


def extra_param(name):
    """Parameters of the optional parts (--aux-fights head, --enemy-map-bias table, --enemy-tokens gates): the
    optimizer's second group."""
    return name.startswith("aux_fight.") or name in ("enemy_bias", "enemy_gate")


def load_opt_state(opt, saved):
    """Loads an optimizer state into an optimizer whose groups may differ after the first (the main group): group
    k > 0 keeps its saved state when the saved state has a group k with as many parameters, otherwise it starts
    fresh (e.g. the aux head or the --enemy-tokens parts added or dropped); the main group must match. Hyper-
    parameters of the groups (lr_scale, weight_decay) come from this run's optimizer."""
    mine = opt.state_dict()
    mg, sg = mine["param_groups"], saved["param_groups"]
    if len(mg[0]["params"]) != len(sg[0]["params"]):
        raise ValueError("optimizer state: the main parameter group differs")
    state, groups = {}, []
    for k, g in enumerate(mg):
        g = dict(g)
        if k == 0 or (k < len(sg) and len(sg[k]["params"]) == len(g["params"])):
            src = sg[k]
            for a, b in zip(src["params"], g["params"]):
                if a in saved["state"] or str(a) in saved["state"]:
                    state[b] = saved["state"].get(a, saved["state"].get(str(a)))
            if k == 0:
                g = dict(src, params=g["params"])
        groups.append(g)
    opt.load_state_dict({"state": state, "param_groups": groups})


def lr_anneal_factor(step, anneal):
    """--lr-anneal-* / LR_ANNEAL file: the learning rate's factor at training step `step`. anneal = [start, steps,
    final] or None: 1 before `start`, then a cosine from 1 down to `final` over `steps` steps, `final` after them."""
    if not anneal:
        return 1.0
    start, steps, final = anneal
    if start < 0 or steps <= 0 or step < start:
        return 1.0
    t = min(1.0, (step - start) / steps)
    return final + (1.0 - final) * 0.5 * (1.0 + math.cos(math.pi * t))


def weight_ema_update(ema, params, decay, n):
    """--weight-ema: one update of the averaged weights after optimizer step n (0, 1, ...): ema <- d * ema +
    (1 - d) * params with d = min(decay, (1 + n) / (10 + n)) (the warm-up keeps a fresh average from holding on to
    the first weights). Returns d."""
    d = min(decay, (1.0 + n) / (10.0 + n))
    with torch.no_grad():
        torch._foreach_lerp_(ema, [p.detach() for p in params], 1.0 - d)
    return d

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
    ap.add_argument("--replay-save", default="",
                    help="directory: at the final stop the replay window is written there (with the final checkpoint's "
                         "step), so --replay-load can continue with it (2026-11-20, default off)")
    ap.add_argument("--replay-load", default="",
                    help="directory of a --replay-save window: loaded at the start when it exists, was saved at the "
                         "resumed checkpoint's step and has this run's layout (--window, ring and compact options); "
                         "otherwise a warning and the window starts empty")
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
    ap.add_argument("--utility", choices=("floor-hp", "amber", "amber2", "amber2-root"), default="floor-hp",
                    help="H of the search: floor-hp = E[HP end of floor] / max HP; amber = Amber Eye's per-floor H, "
                         "U = F + H; amber2 = Amber Eye's later utility (2026-11-20): out of combat P(win) + 0.25 H, "
                         "in combat F + 0.5 H, by the evaluated state's kind, both / 1.5 (same net and heads as amber, so a run can "
                         "switch from amber to amber2 on resume); amber2-root = the same two utilities, picked once per search by "
                         "the root's kind (no jump at fight boundaries with --cross-combat)")
    ap.add_argument("--keyless-hp", action="store_true",
                    help="floor-hp: a keyless act 3 victory keeps H = HP / max HP (amber always does)")
    ap.add_argument("--w-hp-floor", type=float, default=1.0, help="loss weight of the per-floor HP head (amber)")
    ap.add_argument("--init-net", help="start from this checkpoint's weights (mismatched heads fresh; new counters)")
    ap.add_argument("--init-counters", help="with --init-net: take the counters (step, trained, seeds_used, runs_done, "
                    "ascension, ...) from this checkpoint, so run seeds, the replay window (--replay-load) and the "
                    "curriculum continue it; the LR warmup counts from this start")
    ap.add_argument("--teacher-ckpt", help="kickstarting (Amber Eye): a teacher net (checkpoint 'net') whose prediction "
                    "is mixed into the training labels with weight --kickstart-mix; inference / search unchanged")
    ap.add_argument("--teacher-net", default="0.44M", help="the teacher's shape (amber_net.SIZES key or DxL)")
    ap.add_argument("--kickstart-mix", type=float, default=0.0,
                    help="teacher weight lam in the labels: target = (1 - lam) * label + lam * teacher (policy, "
                    "outcome, HP, per-floor HP). A file KICKSTART_LAMBDA in --out-dir sets it live (read at every "
                    "report); 0 stops the teacher forward")
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
    ap.add_argument("--explore-resume", action="store_true",
                    help="with --resume: load the checkpoint's pick-rate exploration state (saved in every checkpoint "
                         "of a run with exploration since 2026-11-21) instead of starting it empty; refused when the "
                         "state is of the other item rule (--explore-clean-keys) (default off)")
    ap.add_argument("--explore-clean-keys", action="store_true",
                    help="with --explore-amber / --explore-c: a pick-rate item is the choice itself (card, relic, "
                         "potion, event option, Neow bonus + drawback, rest option; reward / shop / boss kinds apart), "
                         "without the shop slot, price and affordability that made nearly every shop offer its own "
                         "item (2026-11-21, default off = the first rule)")
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
    ap.add_argument("--stall-log", action="store_true",
                    help="diagnostic (2026-11-21, default off; play and training unchanged): append one JSON record per "
                         "run ended by a stall guard (a loss: fight past --max-fight-moves decisions, run past 50,000 "
                         "decisions, or no legal action) to <out-dir>/stall_log.jsonl: type, seed, floor, encounter, "
                         "fight state and the last 30 real decisions. The per-type counts are in every metrics row")
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
    ap.add_argument("--rng-fix", action="store_true",
                    help="real runs use the seeding of the RNG Fix mod (2026-11-21, default off; Amber Eye trains and "
                         "evaluates with it): each random stream of the game gets its own seed derived from the run "
                         "seed instead of all sharing it, so the net cannot learn the game's correlated randomness "
                         "(for example an uncommon first card reward implying a potion drop). Changes every run of a "
                         "seed; not restored by --resume (pass it again)")
    ap.add_argument("--force-potions", action="store_true",
                    help="reward potions (2026-11-20, default off; a deviation from Amber Eye, Philipp): on a reward "
                         "screen whose potions all fit into the free slots the potions are taken without a search "
                         "(after the --force-rewards relic rules)")
    ap.add_argument("--ooc-canon", action="store_true",
                    help="identical cards on an out-of-combat card selection screen (smith, purge, transform, events; "
                         "2026-11-20, default off; Amber Eye canonicalizes actions): only the first of equal cards "
                         "(id, upgrade, misc, bottle state) stays selectable")
    ap.add_argument("--heart-arms", default="",
                    help="Heart search probe (diagnostic, default off): FULL:FAST:PROB:MFULL:MFAST,... search budgets; "
                         "each run reaching the Heart plays the fight from the same start once per arm and rep "
                         "(results in heart_probe.jsonl); use with --min-replay above any sample count (frozen net) "
                         "and --keep-full 0")
    ap.add_argument("--heart-reps", type=int, default=1, help="plays per arm and Heart start (--heart-arms)")
    ap.add_argument("--aux-fights", action="store_true",
                    help="fight-outcome aux head (not from Amber Eye; default off): out-of-combat samples also predict "
                         "P(death) and HP left in fights against the act boss, its elites and 4 sampled hallway "
                         "fights, labelled by the net's floor HP head on those fight starts (az_run_driver.h auxFights)")
    ap.add_argument("--w-aux", type=float, default=1.0, help="loss weight of the --aux-fights head")
    ap.add_argument("--enemy-tokens", action="store_true",
                    help="encounter tokens (not from Amber Eye; default off): out-of-combat states also get one MONSTER "
                         "token per fight the act can hold (boss, 3 elites, the strong hallway pool), "
                         "az_run_driver.h enemyTokens; the net gets gates that start at 0 (AmberNet(enemy_gate=True)), "
                         "so a resumed net computes what it did without the tokens until the gates train; not with "
                         "--fused-net")
    ap.add_argument("--enemy-map-bias", action="store_true",
                    help="learned attention bias between encounter tokens and the map's boss / elite / hallway nodes "
                         "(not from Amber Eye; default off; needs --enemy-tokens, not with --fused-net): "
                         "amber_net.AmberNet(enemy_bias=True), zero at the start")
    ap.add_argument("--enemy-gate-key", action="store_true",
                    help="--enemy-tokens: key gate instead of the mix of two attentions: one softmax with log g added "
                         "to the encounter keys' scores (their weights times g; at g = 0 exactly the attention without "
                         "them, as the mix). Cheaper: the mix runs a second softmax on rows with encounter tokens "
                         "(PC 2026-11-22: +30 %% inference GPU per batch at 30 %% such rows)")
    ap.add_argument("--enemy-train-kernel", action="store_true",
                    help="--enemy-tokens with --train-packed: training attention through own Triton kernels with "
                         "gradients on the packed tokens (tools/az_bench/varlen_attn_train.py; bias in the kernel, "
                         "rows attend over their own length) instead of padded SDPA with extra q / k columns")
    ap.add_argument("--enemy-lr-scale", type=float, default=0.01,
                    help="--enemy-tokens / --enemy-map-bias: learning rate of the gates and the bias table as a share "
                         "of --lr (their own optimizer group). Adam moves each by about lr per step whatever the "
                         "gradient's size, so at --lr the gates opened to 0.31 in 5 minutes of the second live test")
    ap.add_argument("--check-enemy-gate", type=int, default=0, metavar="BATCHES",
                    help="offline check of --enemy-tokens instead of a run (needs --enemy-tokens and --replay-load of a "
                         "window with encounter tokens): on BATCHES training batches, the net with the gates at their "
                         "checkpoint values vs the same weights without the encounter parts on the states without the "
                         "tokens (training net fp32, and the inference net), and the training step time of both; with "
                         "--compile also torch.compile of the inference net vs the eager one (infer_compiled); "
                         "writes enemy_gate_check.json to --out-dir and exits")
    ap.add_argument("--batch", type=int, default=2048)
    ap.add_argument("--row-buckets", default="2048", help="batch rows padded to these (one size keeps compiled shapes few)")
    ap.add_argument("--tok-buckets", default="32,40,48,56,64,80,96,128,212")
    ap.add_argument("--act-buckets", default="16,32,64,96")
    ap.add_argument("--pack-step", type=int, default=2048)
    ap.add_argument("--pack-threads", type=int, default=4)
    ap.add_argument("--fused-layer", action="store_true", help="inference: stage 0's three-kernel layers (d <= 128)")
    ap.add_argument("--packed-heads", action="store_true",
                    help="inference on a GPU with --packed-h2d: the heads run on the packed tokens and on the live "
                         "actions only (amber_net.py _heads_packed) instead of the padded [rows, tokens] / [rows, "
                         "actions] layout, and the padding rows of the row bucket get length 0 for the attention "
                         "kernel. Same math per row and action up to float rounding; not with --fused-net")
    ap.add_argument("--act-pack-step", type=int, default=1024,
                    help="--packed-heads: the list of live actions is padded to a multiple of this")
    ap.add_argument("--compile", action="store_true", help="inference: torch.compile")
    ap.add_argument("--attn-row-bounds", action="store_true",
                    help="inference on a GPU: the varlen attention kernel ends each row's key loop at the row's own "
                         "length and skips query blocks past it, instead of running every row to the batch's token "
                         "bucket (varlen_attn.py ROW_BOUNDS; same output values)")
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
    ap.add_argument("--early-finish", action="store_true",
                    help="inference loop: while it waits for the next batch's rows, and again right after packing "
                         "them, hand the previous batch's results to the workers if the GPU has them (default: only "
                         "after the next batch is gathered and launched). Changes when answers arrive, not what "
                         "they are")
    ap.add_argument("--parallel-nodes", type=int, default=0, metavar="P",
                    help="search: up to P evaluations in flight per root candidate's subtree, spread by virtual "
                         "losses (RunConfig::parallelNodes; Amber Eye self-play: 4). Default 0: one evaluation in "
                         "flight per run. Same simulations per move, far fewer round trips; each run then keeps up "
                         "to P x candidates encoded inputs (~60 KB each), so fewer games per worker are needed")
    ap.add_argument("--pin-inference", default="", metavar="CPUS",
                    help="CPU affinity (default off; Linux): the inference thread runs on these logical CPUs (a list "
                         "such as 5,11, or 'auto' = the SMT siblings of the highest-numbered allowed CPU, one "
                         "physical core; the pack threads it starts inherit them) and every other thread of the "
                         "process on the remaining CPUs. Play and training are unchanged")
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
    ap.add_argument("--weight-ema", type=float, default=0.0,
                    help="decay of an exponential moving average of the training net's weights (Polyak averaging; "
                         "e.g. 0.999 = about the last 1,000 optimizer steps), updated after every optimizer step; "
                         "self-play then plays with the averaged weights (published every --sync-steps), training "
                         "goes on with the raw weights. Saved in the checkpoint ('ema'); a resume from a checkpoint "
                         "without it starts the average from the resumed weights. 0 = off (default; not from the "
                         "Amber Eye page, an idea from the STS2 Discord)")
    ap.add_argument("--lr-anneal-start", type=int, default=-1,
                    help="training step at which the learning rate starts a cosine decay to --lr-anneal-final x "
                         "--lr over --lr-anneal-steps steps (-1 = off, default; a resume keeps an anneal in progress "
                         "from its checkpoint). Live: a file LR_ANNEAL in --out-dir with 'STEPS [FINAL]' starts one "
                         "at the current step (renamed LR_ANNEAL.applied)")
    ap.add_argument("--lr-anneal-steps", type=int, default=0, help="--lr-anneal-start: length of the decay in steps")
    ap.add_argument("--lr-anneal-final", type=float, default=0.1,
                    help="--lr-anneal-start: learning rate factor at the end of the decay (kept afterwards)")
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
    ap.add_argument("--hp-ema-search", action="store_true",
                    help="both HP heads train on search-backed EMA targets too (floor HP distribution; per-floor HP "
                         "with --utility amber*), same chain and half-life as the outcome (needs --value-ema-search "
                         "and --chance-on-reveal / --cross-combat / --sim-help)")
    ap.add_argument("--replay-hp-bytes", type=int, default=96,
                    help="--hp-ema-search with --compress-targets: bytes per window sample added to the target byte "
                         "ring for the floor HP targets (metric replay_soft_bytes_mean counts both)")
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
    if args.enemy_map_bias and not args.enemy_tokens:
        ap.error("--enemy-map-bias needs --enemy-tokens")
    if args.enemy_train_kernel and not (args.enemy_tokens and args.train_packed):
        ap.error("--enemy-train-kernel needs --enemy-tokens and --train-packed")
    if args.enemy_gate_key and not args.enemy_tokens:
        ap.error("--enemy-gate-key needs --enemy-tokens")
    if args.enemy_tokens and args.fused_net:
        ap.error("--enemy-tokens excludes --fused-net")
    if args.init_counters and not args.init_net:
        ap.error("--init-counters needs --init-net")
    if args.kickstart_mix and not args.teacher_ckpt:
        ap.error("--kickstart-mix needs --teacher-ckpt")
    if not 0.0 <= args.kickstart_mix <= 1.0:
        ap.error("--kickstart-mix: lam in [0, 1]")
    if args.force_keys == "curriculum" and not args.curriculum:
        ap.error("--force-keys curriculum needs --curriculum")
    if args.value_ema_search and not args.value_ema_halflife > 0:
        ap.error("--value-ema-search needs --value-ema-halflife > 0")
    if args.hp_ema_search and not args.value_ema_search:
        ap.error("--hp-ema-search needs --value-ema-search")
    if args.hp_ema_search and not (args.chance_on_reveal or args.cross_combat or args.sim_help):
        ap.error("--hp-ema-search needs Amber's search rules (--chance-on-reveal, --cross-combat or --sim-help)")
    amber = args.utility in ("amber", "amber2", "amber2-root")   # Amber's per-floor H (heads, labels)
    amber2 = args.utility in ("amber2", "amber2-root")
    hp_floors = 56 if amber else 1
    if not 0.0 <= args.heart_log <= 1.0:
        ap.error("--heart-log: RATE in [0, 1]")
    pin_cpus = other_cpus = cpus_before = None
    if args.pin_inference:
        if not hasattr(os, "sched_setaffinity"):
            ap.error("--pin-inference needs os.sched_setaffinity (Linux)")
        cpus_before = os.sched_getaffinity(0)
        try:
            pin_cpus = pin_inference_cpus(args.pin_inference, cpus_before)
        except ValueError as e:
            ap.error(f"--pin-inference: {e}")
        other_cpus = cpus_before - pin_cpus
    heart_arms = [[float(x) for x in a.split(":")] for a in args.heart_arms.split(",") if a]
    if any(len(a) != 5 for a in heart_arms):
        ap.error("--heart-arms: FULL:FAST:PROB:MFULL:MFAST per arm")

    sys.path.insert(0, args.module_dir)
    import az_bench_native  # noqa: E402

    os.makedirs(args.out_dir, exist_ok=True)
    if pin_cpus:
        # This thread first: the threads it starts from here on (workers, trainer, torch pools) inherit its CPUs.
        os.sched_setaffinity(0, other_cpus)
    dev = torch.device(args.device)
    cuda = dev.type == "cuda"
    torch.manual_seed(args.seed)
    d, layers = amber_net.SIZES.get(args.net) or tuple(int(x) for x in args.net.split("x")[:2])
    train_net = amber_net.AmberNet(d=d, layers=layers, hp_floors=hp_floors, soft_policy=args.w_soft_policy > 0,
                                   aux_slots=AUX_SLOTS if args.aux_fights else 0,
                                   enemy_bias=args.enemy_map_bias, enemy_gate=args.enemy_tokens).to(dev)
    train_net.sdpa = True
    train_net.gate_key = bool(args.enemy_gate_key)   # (deepcopied into the inference net)
    if args.enemy_train_kernel:
        train_net.train_attn = amber_net.load_kernel("varlen_attn_train")
    # --aux-fights / --enemy-map-bias: their parameters are a second group, so a checkpoint without them keeps its
    # optimizer state for the rest (load_opt_state).
    main_params = [p_ for n_, p_ in train_net.named_parameters() if not extra_param(n_)]
    aux_params = [p_ for n_, p_ in train_net.named_parameters() if n_.startswith("aux_fight.")]
    enemy_params = [p_ for n_, p_ in train_net.named_parameters() if n_ in ("enemy_bias", "enemy_gate")]
    opt = torch.optim.AdamW([{"params": main_params}] + ([{"params": aux_params}] if aux_params else [])
                            + ([{"params": enemy_params, "lr_scale": args.enemy_lr_scale, "weight_decay": 0.0}]
                               if enemy_params else []),
                            lr=args.lr, weight_decay=args.weight_decay)
    counters = {"step": 0, "trained": 0, "seeds_used": 0, "runs_done": 0, "wall": 0.0}
    explore_blob = None
    if args.resume:
        ck = torch.load(args.resume, map_location=dev)
        explore_blob = ck.get("explore_state")
        fresh = [k for k in train_net.state_dict() if k not in ck["net"]]
        if any(not extra_param(k) for k in fresh):
            raise SystemExit(f"--resume {args.resume}: the checkpoint lacks {fresh}")
        train_net.load_state_dict(ck["net"], strict=not fresh)
        load_opt_state(opt, ck["opt"])
        if fresh:
            print(f"# resume {args.resume}: not in the checkpoint, starting fresh: "
                  f"{sorted({k.split('.')[0] for k in fresh})}", flush=True)
        counters.update(ck["counters"])
    if args.init_net:
        src = torch.load(args.init_net, map_location=dev)["net"]
        own = train_net.state_dict()
        fresh = [k for k in own if k not in src or src[k].shape != own[k].shape]
        own.update({k: v for k, v in src.items() if k in own and v.shape == own[k].shape})
        train_net.load_state_dict(own)
        print(f"# init-net {args.init_net}: fresh {fresh}", flush=True)
    warm0 = 0
    if args.init_counters:
        counters.update(torch.load(args.init_counters, map_location="cpu", weights_only=False)["counters"])
        warm0 = counters["step"]
        print(f"# init-counters {args.init_counters}: step {counters['step']} seeds_used {counters['seeds_used']} "
              f"runs_done {counters['runs_done']}", flush=True)
    # --weight-ema: the averaged weights (fp32, the training net's parameter order), from the checkpoint if it has
    # them for this net, otherwise from the weights as they are now (after --resume / --init-net).
    ema_params = None
    if args.weight_ema > 0:
        if not args.weight_ema < 1:
            ap.error("--weight-ema: decay in (0, 1)")
        ema_params = [p_.detach().clone().float() for p_ in train_net.parameters()]
        saved_ema = ck.get("ema") if args.resume else None
        if saved_ema is not None and len(saved_ema) == len(ema_params) \
                and all(a.shape == b.shape for a, b in zip(saved_ema, ema_params)):
            for a, b in zip(ema_params, saved_ema):
                a.copy_(b.to(dev))
            print(f"# weight-ema: averaged weights from {args.resume} ({counters.get('ema_updates', 0)} updates)",
                  flush=True)
        else:
            counters["ema_updates"] = 0
            print(f"# weight-ema: decay {args.weight_ema}, average starts from the current weights", flush=True)
        counters.setdefault("ema_updates", 0)
    if args.lr_anneal_start >= 0:
        if args.lr_anneal_steps <= 0:
            ap.error("--lr-anneal-start needs --lr-anneal-steps > 0")
        counters["lr_anneal"] = [args.lr_anneal_start, args.lr_anneal_steps, args.lr_anneal_final]
    if counters.get("lr_anneal"):
        print(f"# lr-anneal: start {counters['lr_anneal'][0]} steps {counters['lr_anneal'][1]} final "
              f"{counters['lr_anneal'][2]}", flush=True)
    teacher = None
    kick = {"lam": args.kickstart_mix}
    if args.teacher_ckpt:
        td, tl = amber_net.SIZES.get(args.teacher_net) or tuple(int(x) for x in args.teacher_net.split("x")[:2])
        teacher = amber_net.AmberNet(d=td, layers=tl, hp_floors=hp_floors, soft_policy=args.w_soft_policy > 0).to(dev)
        teacher.load_state_dict(torch.load(args.teacher_ckpt, map_location=dev, weights_only=False)["net"])
        teacher.sdpa = True
        teacher.eval()
        for p_ in teacher.parameters():
            p_.requires_grad_(False)
        kfile = os.path.join(args.out_dir, "KICKSTART_LAMBDA")
        if os.path.exists(kfile):
            with open(kfile) as fh:
                kick["lam"] = float(fh.read().strip())
        print(f"# kickstart: teacher {args.teacher_ckpt} ({args.teacher_net}), lambda {kick['lam']}", flush=True)
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
    if ema_params is not None:   # self-play plays with the averaged weights from the start
        with torch.no_grad():
            for p_i, p_e in zip(infer.parameters(), ema_params):
                p_i.copy_(p_e)
    infer.sdpa = True
    if cuda:
        infer.varlen_attn = amber_net.load_kernel("varlen_attn")
        sys.modules["az_bench_varlen_attn"].ROW_BOUNDS = bool(args.attn_row_bounds)
        if args.packed_heads:
            if not (args.packed_h2d and args.pack_step) or args.fused_net:
                ap.error("--packed-heads needs --packed-h2d and --pack-step, and excludes --fused-net")
            infer.row_mean = amber_net.load_kernel("row_mean")
            infer.packed_heads = True
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
    hp_ema = bool(args.hp_ema_search)
    drv = az_bench_native.RunDriver(
        workers=args.workers, games=args.games, seed_base=seed_base, max_runs=max_runs, ascension=ascension,
        full_sims=args.full_sims, fast_sims=args.fast_sims, full_prob=args.full_prob,
        full_candidates=args.full_candidates, fast_candidates=args.fast_candidates,
        hp_weight_combat=args.hp_weight_combat, hp_weight_ooc=args.hp_weight_ooc, keep_full=args.keep_full,
        keep_fast=args.keep_fast, search_seed=args.seed + counters["step"], max_fight_moves=args.max_fight_moves,
        test_max_hp=args.test_max_hp, max_pending=args.max_pending,
        explore_c=args.explore_c, pick_target=args.pick_target, c_visit=args.c_visit, c_scale=args.c_scale,
        fast_noise=not args.no_fast_noise, q_rescale=args.q_rescale, utility=3 if args.utility == "amber2-root" else 2 if amber2 else 1 if amber else 0,
        keyless_hp=args.keyless_hp,
        eval_cache=args.eval_cache, eval_cache_cap=args.eval_cache_cap, merge_cards=args.merge_cards,
        chance_on_reveal=args.chance_on_reveal, cross_combat=args.cross_combat, sim_help=args.sim_help,
        explore_amber=args.explore_amber, explore_temp=args.explore_temp,
        **({"search_ema_lambda": ema_lam, "search_ema_full_only": args.value_ema_moves == "full"}
           if ema_search else {}),
        **({"search_ema_hp": True} if hp_ema else {}),
        **({"force_keys": True} if force_keys else {}),
        **({"force_rewards": True} if args.force_rewards else {}),
        **({"force_potions": True} if args.force_potions else {}),
        **({"rng_fix": True} if args.rng_fix else {}),
        **({"ooc_canon": True} if args.ooc_canon else {}),
        **({"parallel_nodes": args.parallel_nodes} if args.parallel_nodes else {}),
        **({"explore_per_offer": True} if args.explore_per_offer else {}),
        **({"explore_gap_search": True} if args.explore_gap_search else {}),
        **({"explore_deck_only": True} if args.explore_deck_only else {}),
        **({"explore_clean_keys": True} if args.explore_clean_keys else {}),
        **({"aux_fights": True} if args.aux_fights else {}),
        **({"enemy_tokens": True} if args.enemy_tokens else {}),
        **({"heart_arms": heart_arms, "heart_reps": args.heart_reps} if heart_arms else {}),
        **({"savescum": True} if savescum else {}),
        **({"compact_samples": True} if args.compact_samples else {}),
        **({"heart_log_rate": args.heart_log} if args.heart_log > 0 else {}),
        **({"stall_log": True} if args.stall_log else {}))
    explore_on = args.explore_amber or args.explore_c > 0
    if args.explore_resume:
        # the checkpoint's pick-rate state (items' picks / offers / gap logs, finished runs): without it every item
        # counts as under target again after a restart
        if not explore_on:
            raise SystemExit("--explore-resume needs --explore-amber or --explore-c")
        if explore_blob is None:
            print("# --explore-resume: the checkpoint has no explore_state, exploration starts empty", flush=True)
        else:
            drv.set_explore_state(explore_blob)   # raises on a state of the other item rule
            print(f"# --explore-resume: loaded explore_state ({len(explore_blob)} bytes)", flush=True)
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
    stall_log_path = os.path.join(args.out_dir, "stall_log.jsonl")
    stall_logged = [0]   # records (this process)

    def drain_stall_log():
        if not args.stall_log:
            return
        recs = drv.take_stall_logs()
        if not recs:
            return
        with open(stall_log_path, "a") as f:
            for r in recs:
                f.write(r + "\n")
        stall_logged[0] += len(recs)
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
                    hp_runs_per_sample=args.replay_hp_runs, hp_soft=hp_ema,
                    hp_bytes_per_sample=args.replay_hp_bytes, aux_slots=AUX_SLOTS if args.aux_fights else 0)
    replay_loaded = 0
    if args.replay_load and os.path.exists(os.path.join(args.replay_load, "state.json")):
        t_load = time.time()
        try:
            with open(os.path.join(args.replay_load, "state.json")) as fh:
                saved = json.load(fh)["extra"]
            if saved.get("step") != counters["step"] and not args.check_enemy_gate:
                raise ValueError(f"saved at step {saved.get('step')}, the resumed checkpoint is at {counters['step']}")
            replay.check_layout(args.replay_load)   # before any array is touched: the window stays empty and usable
            replay.load(args.replay_load)
            if replay.migrated_hp:
                print(f"# replay-load: window saved without --hp-ema-search: its {replay.migrated_hp:,} samples keep "
                      "the real HP labels as HP targets", flush=True)
            # the replay-ratio cap counts the trained samples since this window's first sample was added
            trained0 = counters["trained"] - int(saved["trained_since_window"])
            replay_loaded = len(replay)
            print(f"# replay-load {args.replay_load}: {replay_loaded:,} samples ({replay.added:,} added) in "
                  f"{time.time() - t_load:.0f} s", flush=True)
        except Exception as e:   # the run continues with an empty window
            print(f"# replay-load {args.replay_load}: NOT loaded ({e}); the window starts empty", flush=True)
        if replay_loaded == 0 and getattr(replay, "load_partial", False):   # a load failed part-way: a fresh window
            del replay
            replay = Replay(args.window, hp_floors=56 if amber else 0, soft_outcome=ema_lam > 0,
                            compact=args.compact_samples, dict_tokens_per_sample=args.replay_dict_tokens,
                            token_store=az_bench_native.TokenStore if args.compact_samples else None,
                            tokens_per_sample=args.replay_tokens_per_sample,
                            actions_per_sample=args.replay_actions_per_sample,
                            compress_targets=args.compress_targets, soft_bytes_per_sample=args.replay_soft_bytes,
                            hp_runs_per_sample=args.replay_hp_runs, hp_soft=hp_ema,
                            hp_bytes_per_sample=args.replay_hp_bytes, aux_slots=AUX_SLOTS if args.aux_fights else 0)
    elif args.replay_load:
        print(f"# replay-load {args.replay_load}: no saved window there; the window starts empty", flush=True)
    if args.check_enemy_gate:
        res = enemy_gate_check(train_net, infer, replay, args, dev, hp_floors)
        with open(os.path.join(args.out_dir, "enemy_gate_check.json"), "w") as fh:
            json.dump(res, fh, indent=1)
        print(json.dumps(res), flush=True)
        return 0
    ema_stats = {"samples": 0, "real_weight": 0.0}   # mean weight of the final outcome in the EMA targets
    # --aux-fights: rows labelled, samples with rows, label time, sums of the targets per slot (and their counts)
    aux_stats = {"rows": 0, "samples": 0, "secs": 0.0, "n": np.zeros(AUX_SLOTS), "pd": np.zeros(AUX_SLOTS),
                 "hp": np.zeros(AUX_SLOTS)}
    stop = threading.Event()
    errors = []
    weights_lock = threading.Lock()
    new_weights = [None]          # (state tensors on the GPU, event) published by the trainer
    loss_keys = (("policy", "outcome", "hp") + (("hp_floor",) if amber else ())
                 + (("outcome_ema",) if ema_lam > 0 else ()) + (("soft_policy",) if args.w_soft_policy > 0 else ())
                 + (("hp_ema",) if hp_ema else ()) + (("hp_floor_ema",) if hp_ema and amber else ())
                 + (("aux",) if args.aux_fights else ()))
    lossbox = dict({"n": 0}, **{k: 0.0 for k in loss_keys})
    lossbox_lock = threading.Lock()
    counters.setdefault("nonfinite_skips", 0)
    nonfinite_run = [0]   # consecutive skipped steps
    gradbox = {"n": 0, "sum": 0.0, "max": 0.0}   # gradient norm (before clipping) of the finite steps since the last report
    # tokens: of the rows, packed batches only; early: batches handed back before the next one was gathered
    infer_stats = {"batches": 0, "rows": 0, "syncs": 0, "tokens": 0, "early": 0, "early_packed": 0}
    gpu_ms = {"infer": 0.0, "train": 0.0}   # --gpu-timing: cumulative stream busy time
    # Phase timers (logging only): cumulative wall seconds of the inference thread and of the training thread.
    #   inference: wait_pack = next_flat (waiting for rows + packing; the driver's pack_s is the packing part),
    #     weights = taking over the trainer's weights, h2d = shapes and host-to-GPU copies, forward = dtype casts
    #     and the net (issuing the kernels), out = search values and output copies (issuing), sync = waiting for
    #     the previous batch on the GPU, submit = results to the driver.
    #   training: take_add = finished samples into the window, idle = sleeping (window too small or at the replay
    #     ratio cap), sample = drawing the batch, h2d = copy to the device, fwd_bwd = loss, backward and clipping
    #     (issuing), sync = the gradient-norm / loss read that waits for the GPU (--nonfinite-skip), opt = optimizer
    #     step, loss_read = reading the loss parts, publish = weights hand-over (every --sync-steps).
    infer_s = {k: 0.0 for k in ("wait_pack", "weights", "h2d", "forward", "out", "sync", "submit")}
    train_s = {k: 0.0 for k in ("take_add", "idle", "sample", "h2d", "fwd_bwd", "sync", "opt", "loss_read",
                                "publish")}
    infer_tid = [0]   # native id of the inference thread (--pin-inference)

    row_b = [int(v) for v in args.row_buckets.split(",") if int(v) <= args.batch] or [args.batch]
    if row_b[-1] < args.batch:
        row_b.append(args.batch)
    tok_b = [int(v) for v in args.tok_buckets.split(",")]
    if args.enemy_tokens and tok_b[-1] < 223:   # up to 14 more tokens per row (az AmberTokens kAmberMaxTokens 223)
        tok_b.append(224)
    act_b = [int(v) for v in args.act_buckets.split(",")]
    infer_tok_b = {t: 0 for t in tok_b}   # inference batches per token bucket (the padded length of their rows)
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
        infer_tid[0] = threading.get_native_id()
        if pin_cpus:
            os.sched_setaffinity(0, pin_cpus)   # this thread; the pack threads it starts inherit them
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
                 "act_idx": torch.zeros(R * A, dtype=torch.int32, pin_memory=cuda),
                 "seq_off": torch.zeros(R + 1, dtype=torch.int32, pin_memory=cuda)}
            out = {"logits": torch.zeros(R * A, dtype=torch.float32, pin_memory=cuda),
                   "F": torch.zeros(R, dtype=torch.float32, pin_memory=cuda),
                   "ehp": torch.zeros(R, dtype=torch.float32, pin_memory=cuda)}
            if amber:
                out["hpf"] = torch.zeros(R * 56, dtype=torch.float32, pin_memory=cuda)
            if ema_search or amber2:   # amber2: P(win) = class 0
                out["dist"] = torch.zeros(R * OUTCOME_CLASSES, dtype=torch.float32, pin_memory=cuda)
            if hp_ema:   # the floor HP softmax
                out["hpd"] = torch.zeros(R * HP_CLASSES, dtype=torch.float32, pin_memory=cuda)
            return h, {k: v.numpy() for k, v in h.items()}, out

        sets = [buffers(), buffers()]
        cur, pending = 0, None

        def finish(p):
            ticket, rows, Ap, out, ev, version, ev0 = p
            t = time.perf_counter()
            if ev is not None:
                ev.synchronize()
                if ev0 is not None:
                    gpu_ms["infer"] += ev0.elapsed_time(ev)
            t = lap(infer_s, "sync", t)
            drv.submit(ticket, out["logits"][:rows * Ap].numpy().reshape(rows, Ap), out["F"][:rows].numpy(),
                       out["ehp"][:rows].numpy(), out["hpf"][:rows * 56].numpy().reshape(rows, 56) if amber else None,
                       version, out["dist"][:rows * OUTCOME_CLASSES].numpy().reshape(rows, OUTCOME_CLASSES)
                       if ema_search or amber2 else None,
                       *((out["hpd"][:rows * HP_CLASSES].numpy().reshape(rows, HP_CLASSES),) if hp_ema else ()))
            lap(infer_s, "submit", t)

        while not stop.is_set():
            host, views, out = sets[cur]
            t_ph = time.perf_counter()
            timeout_ms = 5
            if args.early_finish and pending is not None:
                # Wait for the rows in short slices. Once the previous batch is done on the GPU (its event; without a
                # stream it already is), its results go to the workers now: they then work on them while this thread
                # gathers and launches the next batch, instead of sleeping until that launch is over.
                t_end = t_ph + 0.005
                while not stop.is_set():
                    if batch_done(pending[4]):
                        t_ph = lap(infer_s, "wait_pack", t_ph)
                        finish(pending)
                        pending = None
                        infer_stats["early"] += 1
                        t_ph = time.perf_counter()
                        break
                    if drv.wait_requests(min_rows, 200):
                        break
                    if time.perf_counter() >= t_end:   # the 5 ms are over: take what is there
                        timeout_ms = 0
                        break
            if args.packed_h2d:
                got = drv.next_flat(args.batch, min_rows, timeout_ms, row_b, tok_b, act_b, views, args.pack_threads,
                                    packed_tokens=True)
            else:
                got = drv.next_flat(args.batch, min_rows, timeout_ms, row_b, tok_b, act_b, views, args.pack_threads)
            t_ph = lap(infer_s, "wait_pack", t_ph)
            if args.early_finish and pending is not None and batch_done(pending[4]):
                # Second point: the rows were there before the previous batch was done, and it finished while this
                # one was packed. Its results go out before this batch's copies and launch, not after them.
                finish(pending)
                pending = None
                infer_stats["early_packed"] += 1
                t_ph = time.perf_counter()
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
                    t_ph = lap(infer_s, "weights", t_ph)
                    M = Rp * Tp
                    nl = 0
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
                    if infer.packed_heads:
                        # The live actions of the live rows (the driver gives a padding row one live action; it is
                        # not listed), padded with the trash slot Rp * Ap; and the padding rows get length 0, so
                        # the attention and row-mean kernels do nothing for them (their one token becomes a trash
                        # entry of the packed axis; nothing reads their outputs).
                        la = np.flatnonzero(views["a_mask"][:rows * Ap])
                        na = -(-la.size // args.act_pack_step) * args.act_pack_step
                        views["act_idx"][:la.size] = la
                        views["act_idx"][la.size:na] = Rp * Ap
                        shapes["act_idx"] = (na,)
                        views["seq_off"][rows + 1:Rp + 1] = views["seq_off"][rows]
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
                    t_ph = lap(infer_s, "h2d", t_ph)
                    x = {}
                    for k, t in raw.items():
                        if fused is not None:
                            x[k] = t   # the kernel reads the driver's int8 / int16 / fp16 arrays as they are
                            continue
                        if k in ("tok_type", "ids", "a_type", "a_src", "a_tgt", "pack_idx", "act_idx"):
                            t = t.long()
                        elif t.dtype == torch.float16:
                            t = t.to(infer_dtype)
                        x[k] = t
                    if args.compile and "act_idx" in x:
                        torch._dynamo.mark_dynamic(x["act_idx"], 0)
                    if args.compile and "pack_idx" in x:
                        torch._dynamo.mark_dynamic(x["pack_idx"], 0)
                        if args.packed_h2d:
                            for k in ("tok_type", "ids", "f"):
                                torch._dynamo.mark_dynamic(x[k], 0)
                    if fused is not None:
                        lg, outcome, hp, hpf = fused(x, fused_mod.make_tiles(views["seq_off"], rows), rows)
                    else:
                        lg, outcome, hp, hpf = run(x)
                    t_ph = lap(infer_s, "forward", t_ph)
                    Fv, ehp = search_values(outcome[:rows], hp[:rows])
                    out["logits"][:rows * Ap].view(rows, Ap).copy_(lg[:rows].float(), non_blocking=True)
                    out["F"][:rows].copy_(Fv, non_blocking=True)
                    out["ehp"][:rows].copy_(ehp, non_blocking=True)
                    if amber:
                        out["hpf"][:rows * 56].view(rows, 56).copy_(hpf[:rows].float().clamp(0, 1), non_blocking=True)
                    if ema_search or amber2:
                        out["dist"][:rows * OUTCOME_CLASSES].view(rows, OUTCOME_CLASSES).copy_(
                            torch.softmax(outcome[:rows].float(), -1), non_blocking=True)
                    if hp_ema:
                        out["hpd"][:rows * HP_CLASSES].view(rows, HP_CLASSES).copy_(
                            torch.softmax(hp[:rows].float(), -1), non_blocking=True)
                    ev = None
                    if stream is not None:
                        ev = torch.cuda.Event(enable_timing=ev0 is not None)
                        ev.record(stream)
                lap(infer_s, "out", t_ph)
                launched = (ticket, rows, Ap, out, ev, infer_stats["syncs"], ev0)
                infer_stats["batches"] += 1
                infer_stats["rows"] += rows
                infer_stats["tokens"] += max(0, int(nl) - (Rp - rows))   # a padding row has one token (packFlat)
                if Tp in infer_tok_b:   # fixed keys: the report thread copies this dict
                    infer_tok_b[Tp] += 1
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
            t_ph = time.perf_counter()
            ch = drv.take_samples(TAKE_CHUNK)   # whole runs only
            if ch is not None:
                if args.aux_fights:   # the fight starts' labels from the net, before the chunk goes into the window
                    t_aux = time.perf_counter()
                    S = len(ch["outcome"])
                    tt, ids_, f_, tok_off, smp, slot = aux_fight_rows(ch)
                    R = len(smp)
                    probs = np.zeros((R, HP_CLASSES), np.float32)
                    train_net.eval()
                    ctx = torch.cuda.stream(stream) if stream is not None else torch.no_grad()
                    with ctx, torch.no_grad(), amp:
                        for i in range(0, R, args.train_batch):
                            rows = np.arange(i, min(R, i + args.train_batch))
                            _, _, hp_l, _ = train_net(to_torch(aux_fight_batch(tt, ids_, f_, tok_off, rows), dev))
                            probs[rows] = torch.softmax(hp_l.float(), -1).cpu().numpy()
                    train_net.train()
                    ch["aux_target"], ch["aux_mask"] = aux_fight_labels(probs, ch["max_hp"], smp, slot, S)
                    has = (ch["aux_mask"][:, None] >> np.arange(AUX_SLOTS)) & 1
                    aux_stats["rows"] += R
                    aux_stats["samples"] += int((ch["aux_mask"] > 0).sum())
                    aux_stats["n"] += has.sum(0)
                    tq = ch["aux_target"].reshape(S, AUX_SLOTS, 2).astype(np.float64) / 255.0
                    aux_stats["pd"] += (tq[:, :, 0] * has).sum(0)
                    aux_stats["hp"] += (tq[:, :, 1] * has).sum(0)
                    aux_stats["secs"] += time.perf_counter() - t_aux
                first = replay.add(ch)
                if ema_search:   # search-backed EMA targets from the driver (whole runs)
                    replay.set_soft_outcome(first, ch["outcome_target"], ch["hp_target"] if hp_ema else None)
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
            t_ph = lap(train_s, "take_add", t_ph)
            if len(replay) < args.min_replay or counters["trained"] - trained0 >= args.replay_ratio * replay.added:
                time.sleep(0.02)
                lap(train_s, "idle", t_ph)
                continue
            b = replay.sample(rng, args.train_batch, args.policy_frac, packed=args.train_packed)
            t_ph = lap(train_s, "sample", t_ph)
            ctx = torch.cuda.stream(stream) if stream is not None else torch.no_grad()
            with ctx:
                if args.gpu_timing and stream is not None:
                    while timing and timing[0][1].query():
                        e0, e1 = timing.popleft()
                        gpu_ms["train"] += e0.elapsed_time(e1)
                    e0 = torch.cuda.Event(enable_timing=True)
                    e0.record(stream)
                bt = to_torch(b, dev)
                t_ph = lap(train_s, "h2d", t_ph)
                step = counters["step"]
                lr = args.lr * min(1.0, (step - warm0 + 1) / max(1, args.warmup_steps)) \
                    * lr_anneal_factor(step, counters.get("lr_anneal"))
                for g in opt.param_groups:
                    g["lr"] = lr * g.get("lr_scale", 1.0)
                lam = kick["lam"]
                if teacher is not None and lam > 0:
                    with torch.no_grad(), amp:
                        bt = kickstart_targets(bt, teacher(bt), lam)
                with torch.enable_grad(), amp:
                    loss, parts = losses(train_net, bt, args.w_policy, args.w_outcome, args.w_hp, args.w_hp_floor,
                                         args.w_soft_policy, args.w_aux)
                opt.zero_grad(set_to_none=True)
                loss.backward()
                gn = torch.nn.utils.clip_grad_norm_(train_net.parameters(), 1.0)   # norm before clipping
                t_ph = lap(train_s, "fwd_bwd", t_ph)
                gnorm = None
                if args.nonfinite_skip:   # one host sync per step (the loss parts below sync anyway)
                    gnorm = float(gn)
                    lval = float(loss.detach())
                    t_ph = lap(train_s, "sync", t_ph)
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
                if ema_params is not None:
                    weight_ema_update(ema_params, train_net.parameters(), args.weight_ema, counters["ema_updates"])
                    counters["ema_updates"] += 1
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
                t_ph = lap(train_s, "opt", t_ph)
                with lossbox_lock:
                    lossbox["n"] += 1
                    for k, v in parts.items():
                        lossbox[k] += float(v)
                t_ph = lap(train_s, "loss_read", t_ph)
                if counters["step"] % args.sync_steps == 0:
                    with torch.no_grad():
                        src = ema_params if ema_params is not None else train_net.parameters()
                        state = [p.detach().to(infer_dtype).clone() for p in src]
                    ev = None
                    if stream is not None:
                        ev = torch.cuda.Event()
                        ev.record(stream)
                    with weights_lock:
                        new_weights[0] = (state, ev)
                lap(train_s, "publish", t_ph)

    def save_ckpt(tag, s, now):
        # Runs in flight are dropped on resume; their seeds are not reused.
        c = dict(counters, seeds_used=seeds_used0 + s["runs_started"], runs_done=counters["runs_done"] + s["runs_done"],
                 wall=wall0 + now - t_start)
        path = os.path.join(args.out_dir, f"ckpt_{tag}.pt")
        if args.resume and os.path.abspath(path) == os.path.abspath(args.resume):
            path = os.path.join(args.out_dir, f"ckpt_{tag}_r{c['runs_done']}.pt")   # never overwrite the resume source
        tmp = path + ".tmp"
        torch.save({"net": train_net.state_dict(), "opt": opt.state_dict(), "counters": c,
                    **({"ema": [t.detach().clone() for t in ema_params]} if ema_params is not None else {}),
                    "args": vars(args), "net_size": [d, layers],
                    **({"explore_state": drv.explore_state()} if explore_on else {})}, tmp)
        os.replace(tmp, path)
        return path, c

    threads = [threading.Thread(target=guarded(inference_loop), daemon=True),
               threading.Thread(target=guarded(train_loop), daemon=True)]
    for t in threads:
        t.start()
    drv.start()
    pin_others = 0
    if pin_cpus:
        # Threads that existed before the main thread's affinity was set (BLAS pools, ...) and helper threads the
        # inference thread started so far (they inherited its CPUs) go to the other CPUs. Repeated at every report.
        t_wait = time.time()
        while not infer_tid[0] and time.time() - t_wait < 10:
            time.sleep(0.01)
        pin_others = pin_threads(infer_tid[0], pin_cpus, other_cpus)
        print(f"# pin-inference: thread {infer_tid[0]} on CPUs {sorted(pin_cpus)}, {pin_others} other threads on "
              f"{sorted(other_cpus)}", flush=True)
    t_start = time.time()
    wall0 = counters["wall"]
    last_s, last_t = drv.stats(), time.time()
    last_ckpt = t_start
    last_runs = last_s["runs_done"]
    last_outcomes = np.array(last_s["outcomes"])
    last_floors = last_s["floors_sum"]
    last_gpu = dict(gpu_ms)
    last_infer, last_infer_s, last_train_s = dict(infer_stats), dict(infer_s), dict(train_s)
    last_tok_b = dict(infer_tok_b)
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
            if teacher is not None:   # live kickstart weight
                kfile = os.path.join(args.out_dir, "KICKSTART_LAMBDA")
                try:
                    if os.path.exists(kfile):
                        with open(kfile) as fh:
                            v = float(fh.read().strip())
                        if 0.0 <= v <= 1.0 and v != kick["lam"]:
                            print(f"# kickstart lambda {kick['lam']} -> {v}", flush=True)
                            kick["lam"] = v
                except (ValueError, OSError) as e:
                    print(f"# kickstart lambda file: ignored ({e})", flush=True)
            lr_file = os.path.join(args.out_dir, "LR_ANNEAL")
            if os.path.exists(lr_file):   # live LR anneal from the current step: "STEPS [FINAL]"
                try:
                    with open(lr_file) as fh:
                        parts_ = fh.read().split()
                    n_ = int(parts_[0])
                    fin_ = float(parts_[1]) if len(parts_) > 1 else args.lr_anneal_final
                    if n_ <= 0 or not 0.0 <= fin_ <= 1.0:
                        raise ValueError(f"steps {n_} final {fin_}")
                    counters["lr_anneal"] = [counters["step"], n_, fin_]
                    print(f"# lr-anneal file: from step {counters['step']} over {n_} steps to {fin_} x lr", flush=True)
                    os.replace(lr_file, lr_file + ".applied")
                except (ValueError, IndexError, OSError) as e:
                    print(f"# lr-anneal file: ignored ({e})", flush=True)
                    os.replace(lr_file, lr_file + ".rejected")
            asc_file = os.path.join(args.out_dir, "ASCENSION")
            if os.path.exists(asc_file):   # live ascension: runs started from now on (curriculum continues from it)
                try:
                    with open(asc_file) as fh:
                        want = int(fh.read().strip())
                    drv.set_ascension(want)
                    counters["ascension"] = want
                    if want > args.ascension:
                        counters["curriculum_stepped"] = True
                        if args.force_keys == "curriculum" and drv.force_keys():
                            drv.set_force_keys(False)
                    asc_hist = []   # the rolling window restarts at the new ascension
                    print(f"# ascension file: A{want}", flush=True)
                    os.replace(asc_file, asc_file + ".applied")
                except (ValueError, OSError) as e:
                    print(f"# ascension file: ignored ({e})", flush=True)
                    os.replace(asc_file, asc_file + ".rejected")
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
                "samples_added": replay.added, "replay": len(replay), "replay_loaded": replay_loaded, "replay_gb": round(replay.nbytes() / 2 ** 30, 3),
                **({"replay_dict_used": replay.store.used} if replay.compact else {}),
                "replay_rings": replay.ring_stats(),
                **({"replay_soft_bytes_mean": round(replay.soft_stats[1] / max(1, replay.soft_stats[0]), 2)}
                   if replay.soft_q else {}), "train_steps": counters["step"],
                "trained_samples": counters["trained"], "loss": lavg, "grad_norm": gavg,
                "lr": args.lr * lr_anneal_factor(counters["step"], counters.get("lr_anneal")),
                **({"weight_ema_updates": counters["ema_updates"]} if ema_params is not None else {}),
                **({"kickstart_lambda": kick["lam"]} if teacher is not None else {}),
                "nonfinite_skips": counters["nonfinite_skips"], "syncs": infer_stats["syncs"],
                "stalls": s["stalls"], "stalls_by_type": {k: s["stalls_" + k] for k in ("fight_moves", "run_moves", "no_legal")}, "unsupported": s["unsupported"], "knowledge_failures": s["knowledge_failures"], "invalid_actions": s["invalid_actions"], "encode_cut": s["encode_cut"], "encode_cut_ooc": s["encode_cut_ooc"],
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
            # Where the time goes (logging only). Inference batches and their mean rows; wall ms per s of wall clock by
            # phase of the inference thread and of the training thread (each sums to about 1000; see infer_s / train_s
            # above); CPU s per s of all worker threads together ("search" is their whole search loop and includes
            # "step" = simulator steps and expansions and "encode" = token encoding) and wall s per s spent packing.
            d_b = infer_stats["batches"] - last_infer["batches"]
            row["infer_batches_per_s"] = round(d_b / dt, 1)
            row["infer_rows_per_batch"] = round((infer_stats["rows"] - last_infer["rows"]) / max(1, d_b), 1)
            # Live tokens per row (0 when the batches are not packed) and batches per token bucket: the padded
            # length every row of a batch is laid out to (the bucket of its longest row).
            row["infer_tokens_per_row"] = round((infer_stats["tokens"] - last_infer["tokens"])
                                                / max(1, infer_stats["rows"] - last_infer["rows"]), 2)
            now_tok_b = dict(infer_tok_b)
            row["infer_tok_bucket_batches"] = {str(t): n - last_tok_b[t] for t, n in now_tok_b.items()
                                               if n - last_tok_b[t]}
            last_tok_b = now_tok_b
            # --early-finish: share of the batches whose results went to the workers before the next batch was gathered
            # (while waiting for rows) and, of the rest, right after the next batch was packed
            row["infer_early_per_batch"] = round((infer_stats["early"] - last_infer["early"]) / max(1, d_b), 3)
            row["infer_early_packed_per_batch"] = round((infer_stats["early_packed"] - last_infer["early_packed"])
                                                        / max(1, d_b), 3)
            row["infer_ms_per_s"] = {k: round(1000 * (v - last_infer_s[k]) / dt, 1) for k, v in infer_s.items()}
            row["train_ms_per_s"] = {k: round(1000 * (v - last_train_s[k]) / dt, 1) for k, v in train_s.items()}
            row["worker_cpu_s_per_s"] = {k: round((s[k + "_cpu"] - last_s[k + "_cpu"]) / dt, 3)
                                         for k in ("search", "step", "encode")}
            row["pack_s_per_s"] = round((s["pack_s"] - last_s["pack_s"]) / dt, 4)
            last_infer, last_infer_s, last_train_s = dict(infer_stats), dict(infer_s), dict(train_s)
            if pin_cpus:   # threads started since the last report too (they inherit their creator's CPUs)
                pin_others = pin_threads(infer_tid[0], pin_cpus, other_cpus)
                row["pin_inference"] = {"cpus": sorted(pin_cpus), "other_cpus": sorted(other_cpus),
                                        "other_threads": pin_others}
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
            if args.force_potions:   # real reward potions taken by the rule (cumulative)
                row["forced_potions"] = s["forced_potions"]
            if args.parallel_nodes:   # evaluations in flight per run and wave; simulations that waited, per 1,000
                d_w = s["waves"] - last_s["waves"]
                d_sims = max(1, s["evals"] + s["cache_hits"] - last_s["evals"] - last_s["cache_hits"])
                row["parallel_nodes"] = {"flights_per_wave": round((s["wave_flights"] - last_s["wave_flights"])
                                                                   / max(1, d_w), 2),
                                         "collisions_per_k": round(1000 * (s["sim_collisions"] - last_s["sim_collisions"])
                                                                   / d_sims, 1),
                                         "flight_slots": s["mem"]["flights"]}
            if args.ooc_canon:   # real card selection screens with a duplicate removed, actions removed (cumulative)
                canon = s["ooc_canon"]
                row["ooc_canon"] = {"screens": canon[0], "removed": canon[1]}
            if pre_trim is not None:
                row["rss_gb_pre_trim"] = pre_trim
            row["relics_per_run"], row["deck_per_run"] = per_run_means(pw)
            row["economy_per_run"] = economy_per_run(pw)
            if args.explore_amber:   # forcing attempts, of which c = 0 / infinity; logged natural items, unplayed (0)
                row["explore_amber"] = {k: s["explore_" + k] for k in
                                        ("attempts", "c_zero", "c_inf", "natural", "natural_unplayed")}
            if ema_lam > 0:
                row["value_ema"] = {"halflife": args.value_ema_halflife, "search": ema_search,
                                    "moves": args.value_ema_moves if ema_search else None, "hp": hp_ema,
                                    "labelled": ema_stats["samples"],
                                    "real_weight_mean": round(ema_stats["real_weight"] / max(1, ema_stats["samples"]), 4)}
            if args.aux_fights:   # fight starts labelled so far, their samples, mean P(death) / HP left per slot
                n_ = np.maximum(1, aux_stats["n"])
                row["aux_fights"] = {"rows": aux_stats["rows"], "samples": aux_stats["samples"],
                                     "driver_rows": s["aux_fights"], "label_s": round(aux_stats["secs"], 1),
                                     "p_death": [round(float(x), 4) for x in aux_stats["pd"] / n_],
                                     "hp_left": [round(float(x), 4) for x in aux_stats["hp"] / n_]}
            if args.enemy_tokens:   # the gates of the encounter tokens (per layer, then the summary), 0 at the start
                gates = train_net.enemy_gate.detach().float().clamp(0, 1).cpu()
                row["enemy_gate"] = [round(float(x), 4) for x in gates]
            if args.enemy_map_bias:   # the learned table: mean |entry| and the enemy <-> map node pairs per kind
                tab = train_net.enemy_bias.detach().float().cpu()
                row["enemy_bias"] = {"abs_mean": round(float(tab.abs().mean()), 5),
                                     "enemy_to_node": [round(float(tab[:, :, k, k + 3].mean()), 5) for k in (1, 2, 3)],
                                     "node_to_enemy": [round(float(tab[:, :, k + 3, k].mean()), 5) for k in (1, 2, 3)]}
            if args.stall_log:
                drain_stall_log()
                row["stall_log"] = stall_logged[0]
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
        drain_stall_log()
        path, c = save_ckpt(counters["step"], drv.stats(), time.time())
        print(json.dumps({"final_checkpoint": path, "errors": errors, "counters": c}), flush=True)
        if args.replay_save:
            t_save = time.time()
            replay.save(args.replay_save, extra={"step": c["step"], "checkpoint": path,
                                                 "trained_since_window": c["trained"] - trained0})
            print(f"# replay-save {args.replay_save}: {len(replay):,} samples in {time.time() - t_save:.0f} s",
                  flush=True)
        metrics.close()
        if pin_cpus:   # in-process callers get their threads' CPUs back
            pin_threads(0, cpus_before, cpus_before)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
