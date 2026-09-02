"""Small fail-closed inference API for combat_evaluator_v1 artifacts."""
from __future__ import annotations
import json, math, hashlib
from pathlib import Path
import numpy as np

class CombatEvaluator:
    def __init__(self, model_dir):
        import xgboost as xgb
        root = Path(model_dir); self.manifest = json.loads((root / "manifest.json").read_text())
        if self.manifest.get("schema_version") != "combat_evaluator_v1": raise ValueError("unsupported evaluator schema")
        fc = self.manifest["feature_contract"]; self.state_names = fc["state_names"]
        if len(self.state_names) != 1017 or not fc.get("one_hot") or len(fc.get("order_hash", "")) != 64: raise ValueError("invalid feature contract")
        self.encounters = list(fc["encounters"]); self.features = list(fc["model_features"])
        if hashlib.sha256(("\n".join(self.state_names + [f"encounter__{x}" for x in self.encounters])).encode()).hexdigest() != fc["order_hash"]: raise ValueError("feature order hash mismatch")
        paths = {"survival":"survival.json", "conditional_win_hp":"conditional_win_hp.json", "conditional_loss_remaining":"conditional_loss_remaining.json"}
        self.models = {k: xgb.Booster() for k in paths}
        for k, m in self.models.items():
            if self.manifest.get("models", {}).get(k) != hashlib.sha256((root / paths[k]).read_bytes()).hexdigest(): raise ValueError(f"model hash mismatch: {k}")
            m.load_model(root / paths[k])
    def predict(self, state_values, encounter):
        if len(state_values) != 1017: raise ValueError("expected exactly 1,017 state values")
        if encounter not in self.encounters: raise ValueError("unknown encounter")
        values = np.asarray(state_values, dtype=np.float32)
        if not np.isfinite(values).all(): raise ValueError("state contains non-finite values")
        row = dict(zip(self.state_names, values.tolist()))
        row.update({f"encounter__{e}": float(e == encounter) for e in self.encounters})
        missing = [f for f in self.features if f not in row]
        if missing: raise ValueError("required feature missing: " + missing[0])
        matrix = np.asarray([[row[f] for f in self.features]], dtype=np.float32)
        import xgboost as xgb
        p = float(self.models["survival"].predict(xgb.DMatrix(matrix, feature_names=self.features))[0])
        w = float(self.models["conditional_win_hp"].predict(xgb.DMatrix(matrix, feature_names=self.features))[0])
        l = float(self.models["conditional_loss_remaining"].predict(xgb.DMatrix(matrix, feature_names=self.features))[0])
        if not all(math.isfinite(x) for x in (p,w,l)): raise ValueError("model returned non-finite output")
        p = float(np.clip(p, 0, 1)); w = float(np.clip(w, 1e-3, 1)); l = float(np.clip(l, 1e-3, 1))
        score = w if p >= .5 else -l; expected = p*w - (1-p)*l
        return {"p_win": p, "predicted_win_hp_frac": w, "predicted_loss_enemy_remaining_frac": l,
                "score": float(np.clip(score, -1, 1)), "expected_score": float(np.clip(expected, -1, 1))}
