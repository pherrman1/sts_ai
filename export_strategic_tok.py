#!/usr/bin/env python3
"""Export V4 attention and contextual OOC strategic artifacts for native C++ inference.

Loads a train_strategic_tok.py checkpoint (OUT.pt) and writes the binary layout
of docs/knowledge-base/architecture/ooc-strategic-v4.md §5, then runs a
32-sample numpy-vs-PyTorch parity check. When the checkpoint is missing (or
EXPORT_TOK_SELFTEST=1), builds a random checkpoint and exports it so the native
loader can be validated without a trained model.

`NpForward` is import-safe: it mirrors the native C++ forward (OocStrategicTokNet)
so offline checks can compare C++ output against numpy on identical inputs.
"""
import argparse, hashlib, json, os, struct, tempfile
from pathlib import Path

import numpy as np
import torch

os.environ.setdefault("STRAT_TOK_RUNG", "4")
from strategic_tok_net import Net, NCARD, NREL, NPOT, MAXD, MAXR, MAXP, NGLOB  # noqa: E402

DIMS = [NGLOB, 256, 128, 32, 32, 16, 8, MAXD, MAXR, MAXP, 41, 17, 9, 37, 32, 16, 184]

W_ORDER = ["E_card.weight", "E_up.weight",
           "deckTok.0.weight", "deckTok.0.bias",
           "deckQkv.weight", "deckQkv.bias",
           "deckProj.weight", "deckProj.bias",
           "deckLn.weight", "deckLn.bias",
           "E_rel.weight", "relTok.0.weight", "relTok.0.bias",
           "E_pot.weight", "potTok.0.weight", "potTok.0.bias",
           "f.0.weight", "f.0.bias", "f.1.weight", "f.1.bias",
           "f.4.weight", "f.4.bias",
           "a_bits.0.weight", "a_bits.0.bias", "a_bits.3.weight", "a_bits.3.bias",
           "a_cat.0.weight", "a_cat.0.bias", "a_cat.2.weight", "a_cat.2.bias",
           "cats.0.weight", "cats.1.weight", "cats.2.weight", "cats.3.weight",
           "cats.4.weight", "cats.5.weight",
           "atype.weight", "screen.weight",
           "ent.0.weight", "ent.0.bias", "ent.2.weight", "ent.2.bias",
           "pol.0.weight", "pol.0.bias", "pol.2.weight", "pol.2.bias"]

CONTEXTUAL_MAGIC = b"OOC_STRAT_C1"
CONTEXTUAL_CHECKPOINT_SHA256 = "bc22f8b03646da79754c1fcfe04f49f20ed5f51ff9ba5250cf715d390d04a761"
DEPLOYED_NATIVE_SHA256 = "e62abd833fc8cb9081a1cec4a1a012832ac3b0e3166da3892841911664f1184c"
DEPLOYED_TEACHER_CHECKPOINT_SHA256 = "5bc14fb437131d4bdc531ea775e22eca1f6834976d4670ec0aabb2fb14b735b8"
DEFAULT_TEACHER_CHECKPOINT = Path(
    "/home/philippherrmann/Documents/Codex/2026-09-25/ooc-contextual-semantic-prior/"
    "deployed_teacher_reconstructed.pt")
DEFAULT_NATIVE_TEACHER = Path("selfplay/models/ooc_strategic_tok_final.native")
CONTEXT_KEYS = {
    "contextDeck.fc1.weight", "contextDeck.fc1.bias",
    "contextDeck.fc2.weight", "contextDeck.fc2.bias",
    "contextDeck.norm.weight", "contextDeck.norm.bias",
}
CONTEXT_NAMES = [
    "contextDeck.fc1.weight", "contextDeck.fc1.bias",
    "contextDeck.fc2.weight", "contextDeck.fc2.bias",
    "contextDeck.norm.weight", "contextDeck.norm.bias",
]


def gelu_np(x):
    return 0.5 * x * (1.0 + np.tanh(np.sqrt(2.0 / np.pi) * (x + 0.044715 * x**3)))


def gelu_exact_np(x):
    values = np.asarray(x, dtype=np.float32)
    return torch.nn.functional.gelu(torch.from_numpy(values)).numpy()


def layer_norm(x, g, b, eps=1e-5):
    mu = x.mean(); var = ((x - mu) ** 2).mean()
    return (x - mu) / np.sqrt(var + eps) * g + b


def lin(x, W, b, out_dim):
    return x @ W.reshape(out_dim, -1).T + b


class NpForward:
    """Numpy reference forward, mirroring OocStrategicTokNet (float32, same op
    order). `fwd` returns (logit, vals[8], q)."""

    def __init__(self, ckpt):
        self.sd = ckpt["state_dict"]
        self.contextual = any(k.startswith("contextDeck.") for k in self.sd)
        self.mean = ckpt["mean"].astype(np.float32)
        self.inv = ckpt["inv"].astype(np.float32)
        assert self.mean.shape[0] == NGLOB and self.inv.shape[0] == NGLOB

    def w(self, name):
        return self.sd[name].numpy().astype(np.float32)

    def fwd(self, glob, dk, rl, pt, action_bits, cats, action_type, screen,
            ent_type, ent_id, gold_ge_price):
        sd = self.sd
        w = self.w
        x = np.clip((np.asarray(glob, np.float32) - self.mean) * self.inv, -8, 8)
        nDk = len(dk); nRl = len(rl); nPt = len(pt)
        tok = np.zeros((MAXD, 32), np.float32)
        for i in range(nDk):
            tid = int(np.clip(dk[i][0], 0, NCARD - 1)); tup = int(np.clip(dk[i][1], 0, 1))
            cf = min(dk[i][2], 9) / 9.0
            tok_in = np.concatenate([w("E_card.weight")[tid], w("E_up.weight")[tup],
                                     np.array([cf], np.float32)])
            tok[i] = gelu_np(lin(tok_in, w("deckTok.0.weight"), w("deckTok.0.bias"), 32))
        z_deck = np.zeros(32, np.float32)
        if nDk > 0:
            if self.contextual:
                context = "contextDeck."
                mean_deck = tok[:nDk].mean(0)
                for i in range(nDk):
                    pair = np.concatenate([tok[i], mean_deck]).astype(np.float32)
                    hidden = gelu_exact_np(lin(pair, w(context + "fc1.weight"),
                                               w(context + "fc1.bias"), 32))
                    delta = lin(hidden, w(context + "fc2.weight"),
                                w(context + "fc2.bias"), 32)
                    tok[i] = layer_norm(tok[i] + delta,
                                        w(context + "norm.weight"),
                                        w(context + "norm.bias"), eps=1e-5)
                z_deck = tok[:nDk].mean(0)
            else:
                qkv = np.zeros((nDk, 96), np.float32)
                for i in range(nDk):
                    qkv[i] = lin(tok[i], w("deckQkv.weight"), w("deckQkv.bias"), 96)
                inv_sqrt = 1.0 / np.sqrt(32.0)
                attn = np.zeros((nDk, 32), np.float32)
                for i in range(nDk):
                    dots = np.array([np.dot(qkv[i][:32], qkv[j][32:64]) for j in range(nDk)],
                                    np.float32) * inv_sqrt
                    smax = dots.max()
                    ws = np.exp(dots - smax)
                    sw = ws.sum()
                    for d in range(32):
                        attn[i][d] = float((ws / sw) @ qkv[:nDk, 64 + d])
                for i in range(nDk):
                    mid = tok[i] + lin(attn[i], w("deckProj.weight"), w("deckProj.bias"), 32)
                    tok[i] = layer_norm(mid, w("deckLn.weight"), w("deckLn.bias"))
                z_deck = tok[:nDk].mean(0)
        z_rel = np.zeros(16, np.float32)
        if nRl > 0:
            rt = np.zeros((nRl, 16), np.float32)
            for i in range(nRl):
                rid = int(np.clip(rl[i][0], 0, NREL - 1))
                df = min(rl[i][1] - 1, 9) / 9.0
                tok_in = np.concatenate([w("E_rel.weight")[rid], np.array([df], np.float32)])
                rt[i] = gelu_np(lin(tok_in, w("relTok.0.weight"), w("relTok.0.bias"), 16))
            z_rel = rt.mean(0)
        z_pot = np.zeros(8, np.float32)
        if nPt > 0:
            ptok = np.zeros((nPt, 8), np.float32)
            for i in range(nPt):
                pid = int(np.clip(pt[i][0], 0, NPOT - 1))
                cf = min(pt[i][1], 9) / 9.0
                tok_in = np.concatenate([w("E_pot.weight")[pid], np.array([cf], np.float32)])
                ptok[i] = gelu_np(lin(tok_in, w("potTok.0.weight"), w("potTok.0.bias"), 8))
            z_pot = ptok.mean(0)
        fuse = np.concatenate([x, z_deck, z_rel, z_pot]).astype(np.float32)
        h = layer_norm(lin(fuse, w("f.0.weight"), w("f.0.bias"), 256), w("f.1.weight"), w("f.1.bias"))
        h = gelu_np(h)
        s = gelu_np(lin(h, w("f.4.weight"), w("f.4.bias"), 128))
        bits = np.array([(action_bits >> i) & 1 for i in range(32)], np.float32)
        b = lin(gelu_np(lin(bits, w("a_bits.0.weight"), w("a_bits.0.bias"), 32)),
                w("a_bits.3.weight"), w("a_bits.3.bias"), 16)
        cat_in = np.concatenate(
            [w(f"cats.{i}.weight")[int(np.clip(cats[i] + 1, 0, 511))] for i in range(6)]
            + [w("atype.weight")[int(np.clip(action_type + 1, 0, 15))]])
        a = lin(gelu_np(lin(cat_in, w("a_cat.0.weight"), w("a_cat.0.bias"), 32)),
                w("a_cat.2.weight"), w("a_cat.2.bias"), 16)
        scr = w("screen.weight")[screen]
        ev = np.zeros(32, np.float32)
        if ent_type == 1:
            ev = w("E_card.weight")[int(np.clip(ent_id, 0, NCARD - 1))]
        elif ent_type == 2:
            ev = np.concatenate([w("E_rel.weight")[int(np.clip(ent_id, 0, NREL - 1))],
                                 np.zeros(16, np.float32)])
        elif ent_type == 3:
            ev = np.concatenate([w("E_pot.weight")[int(np.clip(ent_id, 0, NPOT - 1))],
                                 np.zeros(24, np.float32)])
        eo = np.zeros(4, np.float32); eo[ent_type] = 1.0
        e = lin(gelu_np(lin(np.concatenate([ev, eo, np.array([gold_ge_price], np.float32)]),
                            w("ent.0.weight"), w("ent.0.bias"), 32)),
                w("ent.2.weight"), w("ent.2.bias"), 16)
        z = np.concatenate([s, b, a, scr, e])
        p = gelu_np(lin(z, w("pol.0.weight"), w("pol.0.bias"), 96))
        logit = float(lin(p, w("pol.2.weight"), w("pol.2.bias"), 1)[0])
        qh = gelu_np(lin(z, w("q.0.weight"), w("q.0.bias"), 96))
        q = float(lin(qh, w("q.2.weight"), w("q.2.bias"), 1)[0])
        vs = []
        for hh in range(8):
            v = gelu_np(lin(s, w(f"vals.{hh}.0.weight"), w(f"vals.{hh}.0.bias"), 64))
            vs.append(float(lin(v, w(f"vals.{hh}.2.weight"), w(f"vals.{hh}.2.bias"), 1)[0]))
        return logit, vs, q

    def fwd_value(self, glob, screen):
        """Per-screen value head on the token-free state (mirrors
        OocStrategicTokNet::predictValue, which uses empty token groups)."""
        x = np.clip((np.asarray(glob, np.float32) - self.mean) * self.inv, -8, 8)
        fuse = np.concatenate([x, np.zeros(32, np.float32), np.zeros(16, np.float32),
                               np.zeros(8, np.float32)]).astype(np.float32)
        h = layer_norm(lin(fuse, self.w("f.0.weight"), self.w("f.0.bias"), 256),
                       self.w("f.1.weight"), self.w("f.1.bias"))
        h = gelu_np(h)
        s = gelu_np(lin(h, self.w("f.4.weight"), self.w("f.4.bias"), 128))
        hh = screen - 1
        v = gelu_np(lin(s, self.w(f"vals.{hh}.0.weight"), self.w(f"vals.{hh}.0.bias"), 64))
        return float(lin(v, self.w(f"vals.{hh}.2.weight"), self.w(f"vals.{hh}.2.bias"), 1)[0])


class ContextualDeck(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.fc1 = torch.nn.Linear(64, 32)
        self.fc2 = torch.nn.Linear(32, 32)
        self.norm = torch.nn.LayerNorm(32, eps=1e-5)

    def forward(self, tokens, mask):
        counts = mask.sum(1, keepdim=True)
        mean = (tokens * mask.unsqueeze(-1)).sum(1) / counts.clamp_min(1)
        pair = torch.cat((tokens, mean[:, None, :].expand_as(tokens)), -1)
        delta = self.fc2(torch.nn.functional.gelu(self.fc1(pair)))
        normalized = self.norm(tokens + delta)
        return (normalized * mask.unsqueeze(-1)).sum(1) / counts.clamp_min(1)


class ContextualTorchNet(Net):
    def __init__(self):
        super().__init__()
        self.contextual_deck = None

    def deck_encode(self, ids, ups, cfs):
        if self.contextual_deck is None:
            return super().deck_encode(ids, ups, cfs)
        tokens = self.deck_tokens(ids, ups, cfs)
        return self.contextual_deck(tokens, ids >= 0)


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require_native_teacher_matches(native_path, teacher_ckpt):
    data = Path(native_path).read_bytes()
    if data[:12] != b"OOC_STRAT_V4":
        raise ValueError("deployed native teacher does not use OOC_STRAT_V4")
    offset = 12
    dims_bytes = len(DIMS) * 4
    if len(data) < offset + dims_bytes:
        raise ValueError("deployed native teacher header is truncated")
    dims = list(struct.unpack("17i", data[offset:offset + dims_bytes]))
    if dims != DIMS:
        raise ValueError(f"deployed native teacher dimensions differ: {dims}")
    offset += dims_bytes
    teacher_sd = teacher_ckpt["state_dict"]

    def take(name, shape):
        nonlocal offset
        count = int(np.prod(shape))
        size = count * 4
        if len(data) < offset + size:
            raise ValueError(f"deployed native teacher is truncated before {name}")
        actual = np.frombuffer(data, dtype="<f4", count=count, offset=offset).reshape(shape)
        expected = teacher_sd[name].detach().cpu().numpy().astype(np.float32, copy=False)
        if not np.array_equal(actual, expected):
            raise ValueError(f"deployed native teacher tensor differs from teacher checkpoint: {name}")
        offset += size

    for name in ("mean", "inv"):
        size = NGLOB * 4
        if len(data) < offset + size:
            raise ValueError(f"deployed native teacher is truncated before {name}")
        actual = np.frombuffer(data, dtype="<f4", count=NGLOB, offset=offset)
        expected = np.asarray(teacher_ckpt[name], dtype=np.float32)
        if not np.array_equal(actual, expected):
            raise ValueError(f"deployed native teacher {name} differs from teacher checkpoint")
        offset += size

    for name in W_ORDER:
        take(name, tuple(teacher_sd[name].shape))
    for suffix in ("0.weight", "0.bias", "2.weight", "2.bias"):
        for head in range(8):
            name = f"vals.{head}.{suffix}"
            take(name, tuple(teacher_sd[name].shape))
    for name in ("q.0.weight", "q.0.bias", "q.2.weight", "q.2.bias"):
        take(name, tuple(teacher_sd[name].shape))
    if offset != len(data):
        raise ValueError(f"deployed native teacher has {len(data) - offset} unexpected trailing bytes")


def validate_contextual_artifacts(checkpoint_path, checkpoint,
                                 teacher_checkpoint_path, native_teacher_path):
    checkpoint_sha = sha256_file(checkpoint_path)
    if checkpoint_sha != CONTEXTUAL_CHECKPOINT_SHA256:
        raise ValueError(f"contextual checkpoint SHA-256 mismatch: {checkpoint_sha}")
    native_sha = sha256_file(native_teacher_path)
    if native_sha != DEPLOYED_NATIVE_SHA256:
        raise ValueError(f"deployed native teacher SHA-256 mismatch: {native_sha}")
    teacher_sha = sha256_file(teacher_checkpoint_path)
    if teacher_sha != DEPLOYED_TEACHER_CHECKPOINT_SHA256:
        raise ValueError(f"deployed teacher checkpoint SHA-256 mismatch: {teacher_sha}")

    teacher_checkpoint = torch.load(teacher_checkpoint_path, map_location="cpu", weights_only=False)
    teacher_sd = teacher_checkpoint.get("state_dict", {})
    student_sd = checkpoint.get("state_dict", {})
    embedded_teacher_sd = checkpoint.get("teacher_state_dict", {})
    added = {key for key in student_sd if key.startswith("contextDeck.")}
    shared = {key: value for key, value in student_sd.items() if not key.startswith("contextDeck.")}
    if (len(teacher_sd) != 115 or len(embedded_teacher_sd) != 115
            or len(shared) != 115 or set(shared) != set(teacher_sd)
            or set(embedded_teacher_sd) != set(teacher_sd)):
        raise ValueError("contextual export requires exactly 115 shared teacher tensors")
    if added != CONTEXT_KEYS or len(student_sd) != 121:
        raise ValueError(f"contextual export requires exactly six contextDeck tensors: {sorted(added)}")
    if any(not torch.equal(shared[name], embedded_teacher_sd[name]) for name in teacher_sd):
        raise ValueError("student changed one or more of its 115 embedded frozen teacher tensors")
    if any(not torch.equal(shared[name], teacher_sd[name]) for name in teacher_sd):
        raise ValueError("student shared teacher tensors differ from the deployed teacher checkpoint")
    context_params = sum(int(student_sd[name].numel()) for name in added)
    if context_params != 3200 or checkpoint.get("trainable_parameter_count") != 3200:
        raise ValueError(f"contextual parameter count must equal 3200; found {context_params}")
    if checkpoint.get("native_sha256") != DEPLOYED_NATIVE_SHA256:
        raise ValueError("contextual checkpoint provenance does not name the deployed native teacher")
    if teacher_checkpoint.get("native_sha256") != DEPLOYED_NATIVE_SHA256:
        raise ValueError("deployed teacher checkpoint provenance does not name the tracked native teacher")
    for name in ("mean", "inv"):
        if (name in checkpoint and not np.array_equal(np.asarray(checkpoint[name], dtype=np.float32),
                              np.asarray(teacher_checkpoint[name], dtype=np.float32))):
            raise ValueError(f"contextual checkpoint {name} differs from the deployed teacher")
        checkpoint[name] = np.asarray(teacher_checkpoint[name], dtype=np.float32)
    expected_context = {name.removeprefix("contextDeck.") for name in CONTEXT_KEYS}
    if (checkpoint.get("contextual_deck_state_dict") is None
            or set(checkpoint["contextual_deck_state_dict"]) != expected_context):
        raise ValueError("contextual checkpoint secondary tensor inventory is missing or unexpected")
    for name in CONTEXT_KEYS:
        short_name = name.removeprefix("contextDeck.")
        if not torch.equal(student_sd[name], checkpoint["contextual_deck_state_dict"][short_name]):
            raise ValueError(f"contextual checkpoint tensor copies differ: {name}")
    _require_native_teacher_matches(native_teacher_path, teacher_checkpoint)
    return {"checkpoint_sha256": checkpoint_sha,
            "native_teacher_sha256": native_sha,
            "teacher_checkpoint_sha256": teacher_sha,
            "shared_teacher_tensors": len(shared),
            "context_tensors": len(added),
            "context_parameters": context_params}


def write_native(path, checkpoint, magic):
    state = checkpoint["state_dict"]
    base_state = {name: value for name, value in state.items()
                  if not name.startswith("contextDeck.")}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(magic)
            stream.write(struct.pack("17i", *DIMS))
            stream.write(np.asarray(checkpoint["mean"], dtype=np.float32).tobytes())
            stream.write(np.asarray(checkpoint["inv"], dtype=np.float32).tobytes())
            for name in W_ORDER:
                stream.write(base_state[name].detach().cpu().numpy().astype(np.float32).tobytes())
            for suffix in ("0.weight", "0.bias", "2.weight", "2.bias"):
                for head in range(8):
                    name = f"vals.{head}.{suffix}"
                    stream.write(base_state[name].detach().cpu().numpy().astype(np.float32).tobytes())
            for name in ("q.0.weight", "q.0.bias", "q.2.weight", "q.2.bias"):
                stream.write(base_state[name].detach().cpu().numpy().astype(np.float32).tobytes())
            if magic == CONTEXTUAL_MAGIC:
                for name in CONTEXT_NAMES:
                    stream.write(state[name].detach().cpu().numpy().astype(np.float32).tobytes())
        return Path(temporary)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkpoint", nargs="?", help="source checkpoint (default: selfplay/models/ooc_strategic_tok.pt)")
    parser.add_argument("output", nargs="?", help="native artifact output path")
    parser.add_argument("--teacher-checkpoint", default=str(DEFAULT_TEACHER_CHECKPOINT),
                        help="deployed-teacher reconstruction used for contextual fail-closed checks")
    parser.add_argument("--native-teacher", default=str(DEFAULT_NATIVE_TEACHER),
                        help="tracked deployed native V4 teacher")
    args = parser.parse_args()
    requested_checkpoint = args.checkpoint
    PT = requested_checkpoint or "selfplay/models/ooc_strategic_tok.pt"
    OUT = args.output or PT.replace(".pt", ".native")
    SELFTEST = os.environ.get("EXPORT_TOK_SELFTEST", "0") == "1"
    if requested_checkpoint and not os.path.isfile(PT):
        raise SystemExit(f"[export-strategic-tok] requested checkpoint is absent: {PT}")
    if not os.path.exists(PT) and not SELFTEST:
        print(f"[export-strategic-tok] {PT} not found; running SELFTEST instead", flush=True)
        SELFTEST = True
    if SELFTEST:
        if requested_checkpoint:
            raise SystemExit("[export-strategic-tok] explicit checkpoint cannot be replaced by SELFTEST")
        torch.manual_seed(0)
        m = Net()
        PT = "/tmp/opencode/tok_selftest.pt"
        Path(PT).parent.mkdir(parents=True, exist_ok=True)
        torch.save({"state_dict": m.state_dict(),
                    "mean": np.random.randn(NGLOB).astype(np.float32),
                    "inv": np.abs(np.random.randn(NGLOB)).astype(np.float32) + 0.5,
                    "metrics": {}, "rung": 4, "nrows": 0, "features": 473}, PT)
        print(f"[export-strategic-tok] selftest checkpoint -> {PT}", flush=True)

    ckpt = torch.load(PT, map_location="cpu", weights_only=False)
    sd = ckpt["state_dict"]
    contextual = any(name.startswith("contextDeck.") for name in sd)
    provenance = None
    if contextual:
        provenance = validate_contextual_artifacts(PT, ckpt, args.teacher_checkpoint, args.native_teacher)
    mean = ckpt["mean"].astype(np.float32)
    inv = ckpt["inv"].astype(np.float32)
    assert mean.shape[0] == NGLOB and inv.shape[0] == NGLOB
    rung = int(ckpt.get("rung", 4))
    if contextual and rung != 4:
        raise SystemExit(f"[export-strategic-tok] contextual checkpoint rung must equal 4; found {rung}")
    if rung != 4:
        print(f"[export-strategic-tok] WARNING: checkpoint rung={rung}; exporting anyway", flush=True)
    # The binary layout below supports only the default topology. Non-default
    # configs (STRAT_TOK_TRANSFORMER/QUANTILES/CROSS, TOK_PROBES_FILE) change
    # the ent/fusion input widths and head set; exporting them silently would
    # write a misaligned artifact, so fail loudly instead.
    nquants = int(ckpt.get("nquants", 0))
    ncross = int(ckpt.get("ncross", 0))
    nprobes = int(ckpt.get("nprobes", 0))
    if bool(ckpt.get("transformer", False)) or nquants or ncross or nprobes:
        raise SystemExit(
            f"[export-strategic-tok] unsupported checkpoint config: "
            f"transformer={ckpt.get('transformer', False)} nquants={nquants} "
            f"ncross={ncross} nprobes={nprobes}; the native export contract "
            f"only covers the default topology (no quantiles/cross/probes/transformer).")

    base_sd = {name: value for name, value in sd.items() if not name.startswith("contextDeck.")}
    model = ContextualTorchNet()
    model.load_state_dict(base_sd if contextual else sd, strict=True)
    model.eval()
    if contextual:
        context = ContextualDeck()
        context.load_state_dict({name.removeprefix("contextDeck."): sd[name]
                                 for name in CONTEXT_NAMES}, strict=True)
        context.eval()
        model.contextual_deck = context

    npf = NpForward(ckpt)

    CARD = {0: (0, 0), 1: (NCARD, 1), 2: (NREL, 2), 3: (NPOT, 3)}

    def torch_fwd(sv, dk, rl, pt, ab, cv, at, si, et, ei, gg):
        normed = np.clip((np.asarray(sv, np.float32) - mean) * inv, -8, 8)
        nDk = len(dk); nRl = len(rl); nPt = len(pt)
        dk_ids = np.full((1, MAXD), -1, np.int64); dk_ups = np.zeros((1, MAXD), np.int64)
        dk_cf = np.zeros((1, MAXD), np.float32)
        if nDk:
            dk_ids[0, :nDk] = [t[0] for t in dk]; dk_ups[0, :nDk] = [t[1] for t in dk]
            dk_cf[0, :nDk] = [min(t[2], 9) / 9.0 for t in dk]
        rl_ids = np.full((1, MAXR), -1, np.int64); rl_df = np.zeros((1, MAXR), np.float32)
        if nRl:
            rl_ids[0, :nRl] = [t[0] for t in rl]; rl_df[0, :nRl] = [min(t[1] - 1, 9) / 9.0 for t in rl]
        pt_ids = np.full((1, MAXP), -1, np.int64); pt_cf = np.zeros((1, MAXP), np.float32)
        if nPt:
            pt_ids[0, :nPt] = [t[0] for t in pt]; pt_cf[0, :nPt] = [min(t[1], 9) / 9.0 for t in pt]
        bits = np.array([(int(ab) >> j) & 1 for j in range(32)], np.float32)[None]
        cv = np.array([np.clip(cv + 1, 0, 511)], np.int64)   # trainer/C++ lookup convention: +1
        with torch.no_grad():
            l, v, q, _ = model(torch.from_numpy(normed[None]),
                            torch.from_numpy(dk_ids), torch.from_numpy(dk_ups),
                            torch.from_numpy(dk_cf),
                            torch.from_numpy(rl_ids), torch.from_numpy(rl_df),
                            torch.from_numpy(pt_ids), torch.from_numpy(pt_cf),
                            torch.from_numpy(bits), torch.from_numpy(cv),
                            torch.tensor([at + 1]), torch.tensor([si]),
                            torch.tensor([et]), torch.tensor([ei]), torch.tensor([gg]))
        return float(l[0]), float(v[0]), float(q[0])

    max_err_logit = 0.0; max_err_val = 0.0; max_err_q = 0.0
    for i in range(32):
        np.random.seed(i); torch.manual_seed(i)
        sv = np.random.randn(NGLOB).astype(np.float32) * 2
        nDk = np.random.randint(0, 48); nRl = np.random.randint(0, 40); nPt = np.random.randint(0, 5)
        dk = [(int(np.random.randint(0, NCARD)), int(np.random.randint(0, 2)),
               int(np.random.randint(1, 12))) for _ in range(nDk)]
        rl = [(int(np.random.randint(0, NREL)), int(np.random.randint(1, 12))) for _ in range(nRl)]
        pt = [(int(np.random.randint(0, NPOT)), int(np.random.randint(1, 4))) for _ in range(nPt)]
        ab = np.random.randint(0, 2**32, dtype=np.uint32)
        cv = np.random.randint(0, 511, size=6)
        at = np.random.randint(0, 15); si = np.random.randint(1, 9)
        rng, et = CARD[np.random.randint(0, 4)]
        ei = np.random.randint(0, rng) if rng else -1
        gg = float(np.random.randint(0, 2))
        py_l, py_v, py_q = torch_fwd(sv, dk, rl, pt, ab, cv, at, si, et, ei, gg)
        na_l, na_v, na_q = npf.fwd(sv, dk, rl, pt, ab, cv, at, si, et, ei, gg)
        err_logit = abs(py_l - na_l)
        err_val = abs(py_v - na_v[si - 1])   # torch returns only the head for `screen` (index screen-1)
        err_q = abs(py_q - na_q)
        max_err_logit = max(max_err_logit, err_logit); max_err_val = max(max_err_val, err_val)
        max_err_q = max(max_err_q, err_q)
        assert err_logit < 1e-4 and err_val < 2e-4 and err_q < 2e-4, \
            f"mismatch sample {i}: py_logit={py_l:.6f} native_logit={na_l:.6f} " \
            f"err_val={err_val:.6f} err_q={err_q:.6f}"
    magic = CONTEXTUAL_MAGIC if contextual else b"OOC_STRAT_V4"
    temporary = write_native(OUT, ckpt, magic)
    try:
        os.replace(temporary, OUT)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    print(f"exported {OUT}: 32 parity checks passed "
          f"(max err logit {max_err_logit:.2e}, value {max_err_val:.2e}, Q {max_err_q:.2e})")
    print(f"artifact format: {magic.decode('ascii')}")
    if provenance:
        print("contextual provenance: " + json.dumps(provenance, sort_keys=True))
    print(f"file size: {os.path.getsize(OUT):,} bytes")


if __name__ == "__main__":
    main()
