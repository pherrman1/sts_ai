"""#401b ctm_a20: shared helpers. Loads the deployed artifacts with the repo's own Torch
reconstruction (tools/ctm_artifact_torch.py, sha256-checked) and evaluates heads in batches."""
import sys
import numpy as np
import torch
sys.path.insert(0, "/home/user/sts_ai")
from tools import ctm_artifact_torch as cat
from tools import combat_transition_composed as composed
torch.set_num_threads(1)
FAST = ("/home/user/sts_ai/selfplay/models/combat_transition_deepsets_pathb_a20_lizard.native",
        "ae785ec2e28ceb3755fb63a71534f873ed61a069a6c2e107ef4131a788af7b6b")
STD = ("/home/user/sts_ai/selfplay/models/combat_transition_near_full_escape_pathb_a20.native",
       "e338506ddf14177bec27cfe174670bd9dcac333c26b30416b9f0c76717392b0d")
BOSS_SHIFT = -0.18325317250506112   # §470 manifest bossSurvivalLogitShift (added to the death logit of bosses)
KEYS = ("globals_continuous", "global_categories", "cards", "relics", "potions", "card_mask", "relic_mask")

def load(which="fast"):
    path, sha = FAST if which == "fast" else STD
    return cat.load_artifact(path, sha)

def _batch(arrs, idx):
    b = {k: arrs[k][idx] for k in KEYS}
    for d, m in (("cards", "card_mask"), ("relics", "relic_mask")):
        cols = np.flatnonzero(b[m].any(0)); w = int(cols[-1]) + 1 if len(cols) else 1
        b[d] = b[d][:, :w]; b[m] = b[m][:, :w]
    return [torch.from_numpy(np.ascontiguousarray(b[k])) for k in KEYS]

@torch.inference_mode()
def encode(model, arrs, names=("survival", "max_hp", "hp", "potion_encoder"), bs=4096):
    n = len(arrs["globals_continuous"]); out = {k: [] for k in names}
    for i in range(0, n, bs):
        x = _batch(arrs, np.arange(i, min(n, i + bs)))
        for k in names:
            with composed.attention_backend(torch, k != "hp"):
                out[k].append(model.encoders[k](*x).float())
    return {k: torch.cat(v) for k, v in out.items()}

@torch.inference_mode()
def survival_logit(model, z):
    return model.survival_head(z).flatten().double().numpy()
