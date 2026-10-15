#!/usr/bin/env python3
"""Export silverbot's heart1.pt state dict to the native STS_OOC_HEART1 format.

heart1.pt is the released checkpoint of daniel-ziegler/sts_lightspeed (MIT,
"Silver Automaton"). It is not vendored: fetch it from that repository's
releases page and check its SHA-256 (pinned below). Only torch is needed.

Format: b"HEART1W\\x01", u32 tensor count, then per tensor u32 name length,
UTF-8 name, u32 ndim, u32 dims, float32 little-endian data.

    python3 tools/heart1/export_heart1_weights.py heart1.pt heart1.bin

A distilled student (the heart1-distill thread's distill.py state dict) needs
--allow-other-checkpoint and its head count; --trim-map marks a student trained
on records without the map rows below the current floor. Both are written as
one-element meta.* tensors, which heart1's own export leaves out:

    python3 tools/heart1/export_heart1_weights.py student.pt student.bin \\
        --allow-other-checkpoint --n-heads 4 --trim-map
"""
import argparse
import hashlib
import struct
import sys

HEART1_SHA256 = "deaba59d0c1d13a64578bd770bbcdcee95b1b5ef85e9b732739c89291da237d9"

# silverbot's EmbedCache shares one module between these names; the native
# forward reads only the first of each group, so they must be equal.
SHARED = [
    ("obs_embed.component_embeddings.deck.element_embedding.component_embeddings.0.embedding.weight",
     "choice_embed.component_embeddings.cards.element_embedding.component_embeddings.0.embedding.weight",
     "choice_embed.component_embeddings.fixed.element_embedding.component_embeddings.card.embedding.weight"),
    ("obs_embed.component_embeddings.deck.element_embedding.component_embeddings.1.weight",
     "choice_embed.component_embeddings.cards.element_embedding.component_embeddings.1.weight"),
    ("obs_embed.component_embeddings.relics.element_embedding.embedding.weight",
     "choice_embed.component_embeddings.relics.element_embedding.embedding.weight",
     "choice_embed.component_embeddings.fixed.element_embedding.component_embeddings.relic.embedding.weight"),
    ("obs_embed.component_embeddings.potions.element_embedding.embedding.weight",
     "choice_embed.component_embeddings.potions.element_embedding.embedding.weight"),
]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("checkpoint")
    ap.add_argument("out")
    ap.add_argument("--allow-other-checkpoint", action="store_true",
                    help="export a checkpoint whose SHA-256 is not heart1's")
    ap.add_argument("--n-heads", type=int, help="attention heads (meta.n_heads; the native default is 8)")
    ap.add_argument("--trim-map", action="store_true", help="meta.trim_map = 1")
    args = ap.parse_args()

    digest = sha256(args.checkpoint)
    if digest != HEART1_SHA256 and not args.allow_other_checkpoint:
        sys.exit(f"{args.checkpoint}: sha256 {digest} is not heart1.pt ({HEART1_SHA256})")

    import torch
    state = torch.load(args.checkpoint, map_location="cpu", weights_only=True)
    for group in SHARED:
        for name in group[1:]:
            if not torch.equal(state[group[0]], state[name]):
                sys.exit(f"{name} differs from {group[0]}; the native forward assumes they are shared")
    if any(name.startswith("meta.") for name in state):
        sys.exit("checkpoint already has meta.* tensors")
    state = dict(state)
    if args.n_heads is not None:
        state["meta.n_heads"] = torch.tensor([float(args.n_heads)])
    if args.trim_map:
        state["meta.trim_map"] = torch.tensor([1.0])

    with open(args.out, "wb") as f:
        f.write(b"HEART1W\x01")
        f.write(struct.pack("<I", len(state)))
        for name, tensor in state.items():
            data = tensor.detach().to(torch.float32).contiguous().numpy()
            encoded = name.encode()
            f.write(struct.pack("<I", len(encoded)))
            f.write(encoded)
            f.write(struct.pack("<I", data.ndim))
            f.write(struct.pack(f"<{data.ndim}I", *data.shape))
            f.write(data.astype("<f4").tobytes())
    print(f"{args.out}: {len(state)} tensors from {args.checkpoint} (sha256 {digest}); "
          f"export sha256 {sha256(args.out)}")


if __name__ == "__main__":
    main()
