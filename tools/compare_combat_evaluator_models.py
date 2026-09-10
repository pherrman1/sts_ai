#!/usr/bin/env python3
"""Compare offline pre-combat combat-value models on the frozen corpus.

This runner is intentionally an experiment, not a runtime model exporter.  It
reuses the frozen semantic-branch corpus and feature construction, chooses all
finalists from validation only, records that freeze, and evaluates the frozen
finalists on TEST exactly once.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import platform
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

TOOLS = str(Path(__file__).resolve().parent)
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

from train_combat_evaluator_semantic_branch import (  # noqa: E402
    EXPECTED_PACKAGE_SHA256,
    STATE_FEATURES,
    build_features,
    load_corpus,
    valid_mask,
)
from train_combat_evaluator import stable_split  # noqa: E402
from combat_evaluator_contract import sha256  # noqa: E402


SEED = 20260910
XGB_SEED = 20260902
EARLY_STOPPING = 75
TARGET_DEATH_RECALL = 0.90

FACTORIAL_GRID: dict[str, dict[str, Any]] = {
    "B0": {"max_depth": 6, "eta": 0.05, "rounds": 300},
    "B1": {"max_depth": 3, "eta": 0.03, "rounds": 800},
    "B2": {"max_depth": 4, "eta": 0.03, "rounds": 800},
    "B3": {"max_depth": 6, "eta": 0.03, "rounds": 800},
    "B4": {"max_depth": 8, "eta": 0.03, "rounds": 800},
    "B5": {"max_depth": 4, "eta": 0.02, "rounds": 1200},
    "B6": {"max_depth": 6, "eta": 0.02, "rounds": 1200},
    "B7": {"max_depth": 8, "eta": 0.02, "rounds": 1200},
}
DIRECT_GRID: dict[str, dict[str, Any]] = {
    "C1": {"max_depth": 4, "eta": 0.03, "rounds": 800},
    "C2": {"max_depth": 6, "eta": 0.03, "rounds": 800},
    "C3": {"max_depth": 4, "eta": 0.02, "rounds": 1200},
    "C4": {"max_depth": 6, "eta": 0.02, "rounds": 1200},
}
NN_GRID: dict[str, tuple[int, ...]] = {
    "D-small": (256, 128),
    "D-medium": (512, 256, 128),
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def reg(y: np.ndarray, prediction: np.ndarray) -> dict[str, Any]:
    if len(y) == 0:
        return {"mae": None, "rmse": None, "n": 0}
    error = np.asarray(prediction, dtype=float) - np.asarray(y, dtype=float)
    return {
        "mae": float(np.abs(error).mean()),
        "rmse": float(np.sqrt(np.mean(error * error))),
        "n": int(len(error)),
    }


def binary_metrics(y: np.ndarray, p_win: np.ndarray) -> dict[str, Any]:
    if len(y) == 0:
        return {"logloss": None, "brier": None, "roc_auc": None, "pr_auc_death": None, "n": 0}
    from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score

    death = 1 - np.asarray(y, dtype=int)
    death_probability = 1.0 - np.asarray(p_win, dtype=float)
    return {
        "logloss": float(log_loss(y, p_win, labels=[0, 1])),
        "brier": float(brier_score_loss(y, p_win)),
        "roc_auc": float(roc_auc_score(y, p_win)) if len(np.unique(y)) == 2 else None,
        "pr_auc_death": float(average_precision_score(death, death_probability))
        if len(np.unique(death)) == 2 else None,
        "n": int(len(y)),
    }


def prediction(booster: Any, matrix: Any) -> np.ndarray:
    end = getattr(booster, "best_iteration", None)
    if end is not None and int(end) >= 0:
        return booster.predict(matrix, iteration_range=(0, int(end) + 1))
    return booster.predict(matrix)


def xgb_params(config: dict[str, Any], threads: int) -> dict[str, Any]:
    return {
        "max_depth": int(config["max_depth"]),
        "eta": float(config["eta"]),
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "seed": XGB_SEED,
        "nthread": threads,
        "tree_method": "hist",
    }


def train_booster(
    frame: pd.DataFrame,
    features: list[str],
    train_mask: pd.Series,
    val_mask: pd.Series,
    label: str,
    objective: str,
    config: dict[str, Any],
    *,
    threads: int,
    weights: np.ndarray | None = None,
    early_stopping: bool,
) -> Any:
    import xgboost as xgb

    require(bool(train_mask.any()), f"no training rows for {label}")
    train_matrix = xgb.DMatrix(
        frame.loc[train_mask, features],
        label=frame.loc[train_mask, label],
        weight=weights,
    )
    params = {
        **xgb_params(config, threads),
        "objective": objective,
        "eval_metric": "logloss" if objective == "binary:logistic" else "rmse",
    }
    if early_stopping:
        require(bool(val_mask.any()), f"no validation rows for {label}")
        validation_matrix = xgb.DMatrix(frame.loc[val_mask, features], label=frame.loc[val_mask, label])
        return xgb.train(
            params,
            train_matrix,
            num_boost_round=int(config["rounds"]),
            evals=[(validation_matrix, "validation")],
            early_stopping_rounds=EARLY_STOPPING,
            verbose_eval=False,
        )
    return xgb.train(params, train_matrix, num_boost_round=int(config["rounds"]), verbose_eval=False)


def factorized_weights(frame: pd.DataFrame, mask: pd.Series) -> np.ndarray:
    selected = frame.loc[mask]
    counts = selected.groupby("sourceSeed")["sourceSeed"].transform("size").to_numpy(dtype=float)
    require(len(counts) == int(mask.sum()), "weight length mismatch")
    return 1.0 / counts


def make_factorized(
    frame: pd.DataFrame,
    split: pd.Series,
    features: list[str],
    config: dict[str, Any],
    *,
    threads: int,
    early_stopping: bool,
    balanced: bool = False,
) -> dict[str, Any]:
    import xgboost as xgb

    valid = valid_mask(frame)
    train = split.eq("train")
    validation = split.eq("validation")
    eligible = {
        "survival": train & valid,
        "conditional_win_hp": train & valid & frame.won.eq(1),
        "conditional_loss_remaining": train & valid & frame.trueDeath.eq(1) & ~frame.progressAmbiguous.eq(1),
    }
    validation_eligible = {
        "survival": validation & valid,
        "conditional_win_hp": validation & valid & frame.won.eq(1),
        "conditional_loss_remaining": validation & valid & frame.trueDeath.eq(1) & ~frame.progressAmbiguous.eq(1),
    }
    specs = {
        "survival": ("won", "binary:logistic"),
        "conditional_win_hp": ("winHpFrac", "reg:squarederror"),
        "conditional_loss_remaining": ("lossRemainingFrac", "reg:squarederror"),
    }
    models: dict[str, Any] = {}
    best_iterations: dict[str, int | None] = {}
    for name, (label, objective) in specs.items():
        weights = factorized_weights(frame, eligible[name]) if balanced else None
        model = train_booster(
            frame, features, eligible[name], validation_eligible[name], label, objective, config,
            threads=threads, weights=weights, early_stopping=early_stopping,
        )
        models[name] = model
        best_iterations[name] = int(model.best_iteration) if getattr(model, "best_iteration", None) is not None else None

    def predict(mask: pd.Series) -> dict[str, np.ndarray]:
        matrix = xgb.DMatrix(frame.loc[mask, features])
        p_win = np.clip(prediction(models["survival"], matrix), 0.0, 1.0)
        win_hp = np.clip(prediction(models["conditional_win_hp"], matrix), 1e-3, 1.0)
        loss = np.clip(prediction(models["conditional_loss_remaining"], matrix), 1e-3, 1.0)
        expected = p_win * win_hp - (1.0 - p_win) * loss
        return {
            "p_win": p_win,
            "predicted_win_hp_frac": win_hp,
            "predicted_loss_remaining_frac": loss,
            "expected_signed_outcome": expected,
            "primary_signed": expected,
        }

    return {
        "kind": "factorized_xgb",
        "models": models,
        "parameters": {**config, "subsample": 0.8, "colsample_bytree": 0.8, "seed": XGB_SEED,
                        "tree_method": "hist", "threads": threads, "early_stopping_rounds": EARLY_STOPPING if early_stopping else None,
                        "balanced_source_weights": balanced},
        "best_iterations": best_iterations,
        "predict": predict,
        "has_factorized": True,
    }


def make_direct(
    frame: pd.DataFrame,
    split: pd.Series,
    features: list[str],
    config: dict[str, Any],
    *,
    threads: int,
) -> dict[str, Any]:
    import xgboost as xgb

    valid = valid_mask(frame)
    model = train_booster(
        frame, features, split.eq("train") & valid, split.eq("validation") & valid,
        "signedOutcome", "reg:squarederror", config, threads=threads, early_stopping=True,
    )

    def predict(mask: pd.Series) -> dict[str, np.ndarray]:
        values = prediction(model, xgb.DMatrix(frame.loc[mask, features]))
        return {"primary_signed": values, "direct_signed_outcome": values}

    return {
        "kind": "direct_signed_xgb", "models": {"direct_signed": model},
        "parameters": {**config, "subsample": 0.8, "colsample_bytree": 0.8, "seed": XGB_SEED,
                        "tree_method": "hist", "threads": threads, "early_stopping_rounds": EARLY_STOPPING},
        "best_iterations": {"direct_signed": int(model.best_iteration) if getattr(model, "best_iteration", None) is not None else None},
        "predict": predict, "has_factorized": False,
    }


class MultiTaskMLP:
    def __init__(self, input_size: int, hidden: tuple[int, ...], seed: int) -> None:
        import torch
        import torch.nn as nn

        torch.manual_seed(seed)
        layers: list[nn.Module] = []
        previous = input_size
        for width in hidden:
            layers.extend([nn.Linear(previous, width), nn.ReLU(), nn.Dropout(0.1)])
            previous = width
        self.net = nn.Sequential(*layers)
        self.heads = nn.ModuleDict({
            "win": nn.Linear(previous, 1), "win_hp": nn.Linear(previous, 1),
            "loss": nn.Linear(previous, 1), "signed": nn.Linear(previous, 1),
        })
        self.module = nn.ModuleDict({"body": self.net, "heads": self.heads})

    def __call__(self, values: Any) -> dict[str, Any]:
        representation = self.net(values)
        return {name: head(representation).squeeze(-1) for name, head in self.heads.items()}


def nn_outputs(model: MultiTaskMLP, values: Any) -> dict[str, np.ndarray]:
    import torch

    model.module.eval()
    with torch.no_grad():
        outputs = model(values)
        p_win = torch.sigmoid(outputs["win"]).cpu().numpy()
        win_hp = torch.sigmoid(outputs["win_hp"]).cpu().numpy()
        loss = torch.sigmoid(outputs["loss"]).cpu().numpy()
        direct = torch.tanh(outputs["signed"]).cpu().numpy()
    expected = p_win * win_hp - (1.0 - p_win) * loss
    return {
        "p_win": p_win, "predicted_win_hp_frac": win_hp,
        "predicted_loss_remaining_frac": loss, "expected_signed_outcome": expected,
        "direct_signed_outcome": direct, "primary_signed": direct,
    }


def train_nn(
    frame: pd.DataFrame,
    split: pd.Series,
    features: list[str],
    hidden: tuple[int, ...],
    *,
    max_epochs: int,
    patience: int,
) -> dict[str, Any]:
    import torch
    import torch.nn.functional as F

    torch.set_num_threads(1)
    train_rows = split.eq("train")
    valid = valid_mask(frame)
    train_valid = train_rows & valid
    validation_valid = split.eq("validation") & valid
    means = frame.loc[train_rows, features].mean().to_numpy(dtype=np.float32)
    std = frame.loc[train_rows, features].std(ddof=0).to_numpy(dtype=np.float32)
    std = np.where(std > 1e-12, std, 1.0)
    normalized = ((frame[features].to_numpy(dtype=np.float32) - means) / std).astype(np.float32)
    x_train = torch.from_numpy(normalized[train_valid.to_numpy()])
    x_validation = torch.from_numpy(normalized[validation_valid.to_numpy()])
    y_train = {name: torch.from_numpy(frame.loc[train_valid, column].to_numpy(dtype=np.float32))
               for name, column in (("win", "won"), ("win_hp", "winHpFrac"), ("loss", "lossRemainingFrac"), ("signed", "signedOutcome"))}
    train_winner = frame.loc[train_valid, "won"].to_numpy(dtype=bool)
    train_death = (frame.loc[train_valid, "trueDeath"].to_numpy(dtype=bool)
                   & ~frame.loc[train_valid, "progressAmbiguous"].to_numpy(dtype=bool))
    y_train["win_hp_eligible"] = torch.from_numpy(train_winner)
    y_train["loss_eligible"] = torch.from_numpy(train_death)
    model = MultiTaskMLP(len(features), hidden, SEED)
    optimizer = torch.optim.AdamW(model.module.parameters(), lr=1e-3, weight_decay=1e-4)
    best_state: dict[str, Any] | None = None
    best_value = math.inf
    stale = 0
    history: list[float] = []
    validation_y = frame.loc[validation_valid, "signedOutcome"].to_numpy(dtype=float)
    for epoch in range(max_epochs):
        model.module.train()
        optimizer.zero_grad(set_to_none=True)
        outputs = model(x_train)
        losses = [F.binary_cross_entropy_with_logits(outputs["win"], y_train["win"])]
        losses.append(F.smooth_l1_loss(torch.sigmoid(outputs["win_hp"])[y_train["win_hp_eligible"]], y_train["win_hp"][y_train["win_hp_eligible"]]))
        losses.append(F.smooth_l1_loss(torch.sigmoid(outputs["loss"])[y_train["loss_eligible"]], y_train["loss"][y_train["loss_eligible"]]))
        losses.append(F.smooth_l1_loss(torch.tanh(outputs["signed"]), y_train["signed"]))
        sum(losses).backward()
        optimizer.step()
        validation_prediction = nn_outputs(model, x_validation)
        value = float(np.mean(np.abs(validation_prediction["expected_signed_outcome"] - validation_y)))
        history.append(value)
        if value < best_value - 1e-10:
            best_value = value
            best_state = copy.deepcopy(model.module.state_dict())
            stale = 0
        else:
            stale += 1
            if stale >= patience:
                break
    require(best_state is not None, "NN did not produce a validation checkpoint")
    model.module.load_state_dict(best_state)

    def predict(mask: pd.Series) -> dict[str, np.ndarray]:
        values = torch.from_numpy(normalized[mask.to_numpy()])
        return nn_outputs(model, values)

    return {
        "kind": "multitask_mlp", "models": {"mlp": model}, "predict": predict,
        "has_factorized": True, "parameters": {"hidden": list(hidden), "dropout": 0.1,
        "optimizer": "AdamW", "learning_rate": 1e-3, "weight_decay": 1e-4,
        "loss_weights": {"survival": 1, "win_hp": 1, "loss": 1, "signed": 1},
        "max_epochs": max_epochs, "patience": patience, "epochs_run": len(history),
        "best_validation_expected_signed_mae": best_value, "normalization_fit": "TRAIN rows only",
        "seed": SEED},
        "normalization": {"mean": means.tolist(), "std": std.tolist()},
    }


def baselines(frame: pd.DataFrame, split: pd.Series) -> dict[str, float]:
    train = split.eq("train") & valid_mask(frame)
    return {
        "survival_prior": float(frame.loc[train, "won"].mean()),
        "win_hp_mean": float(frame.loc[train & frame.won.eq(1), "winHpFrac"].mean()),
        "loss_mean": float(frame.loc[train & frame.trueDeath.eq(1) & ~frame.progressAmbiguous.eq(1), "lossRemainingFrac"].mean()),
        "signed_mean": float(frame.loc[train, "signedOutcome"].mean()),
    }


def evaluate(frame: pd.DataFrame, mask: pd.Series, preds: dict[str, np.ndarray], base: dict[str, float], has_factorized: bool) -> dict[str, Any]:
    valid = mask & valid_mask(frame)
    winners = valid & frame.won.eq(1)
    deaths = valid & frame.trueDeath.eq(1) & ~frame.progressAmbiguous.eq(1)
    local_valid = valid.loc[mask]
    local_winners = winners.loc[mask]
    local_deaths = deaths.loc[mask]
    indices = local_valid.to_numpy()
    truth = frame.loc[valid, "signedOutcome"].to_numpy(dtype=float)
    primary = preds["primary_signed"][indices]
    result: dict[str, Any] = {
        "rows": int(mask.sum()), "valid": int(valid.sum()), "source_seeds": int(frame.loc[mask, "sourceSeed"].nunique()),
        "counts": {"wins": int(winners.sum()), "true_deaths": int((valid & frame.trueDeath.eq(1)).sum()),
                   "nonambiguous_deaths": int(deaths.sum()), "ambiguous": int((valid & frame.progressAmbiguous.eq(1)).sum())},
        "primary_signed": {"model": reg(truth, primary), "train_signed_mean_baseline": reg(truth, np.full(len(truth), base["signed_mean"]))},
        "sign": {"accuracy": float(((primary >= 0) == (truth >= 0)).mean()) if len(truth) else None},
    }
    if not has_factorized:
        result["survival"] = None
        result["winning_hp"] = None
        result["loss_severity"] = None
        result["expected_signed_outcome"] = None
        return result
    p_win = preds["p_win"][indices]
    expected = preds["expected_signed_outcome"][indices]
    result["survival"] = {"model": binary_metrics(frame.loc[valid, "won"].to_numpy(dtype=int), p_win),
                           "train_prior_baseline": binary_metrics(frame.loc[valid, "won"].to_numpy(dtype=int), np.full(len(p_win), base["survival_prior"]))}
    result["winning_hp"] = {"model": reg(frame.loc[winners, "winHpFrac"].to_numpy(dtype=float), preds["predicted_win_hp_frac"][local_winners.to_numpy()]),
                            "train_winner_mean_baseline": reg(frame.loc[winners, "winHpFrac"].to_numpy(dtype=float), np.full(int(winners.sum()), base["win_hp_mean"]))}
    result["loss_severity"] = {"model": reg(frame.loc[deaths, "lossRemainingFrac"].to_numpy(dtype=float), preds["predicted_loss_remaining_frac"][local_deaths.to_numpy()]),
                               "train_death_mean_baseline": reg(frame.loc[deaths, "lossRemainingFrac"].to_numpy(dtype=float), np.full(int(deaths.sum()), base["loss_mean"]))}
    result["expected_signed_outcome"] = {"model": reg(truth, expected), "train_signed_mean_baseline": reg(truth, np.full(len(truth), base["signed_mean"]))}
    return result


def choose_risk_threshold(frame: pd.DataFrame, validation: pd.Series, preds: dict[str, np.ndarray]) -> dict[str, Any]:
    valid = validation & valid_mask(frame)
    local_valid = valid.loc[validation]
    y_death = 1 - frame.loc[valid, "won"].to_numpy(dtype=int)
    death_probability = 1.0 - preds["p_win"][local_valid.to_numpy()]
    thresholds = np.unique(np.r_[0.0, 0.5, death_probability, 1.0])
    acceptable = []
    for threshold in thresholds:
        predicted = death_probability >= threshold
        recall = float((predicted & (y_death == 1)).sum() / max(1, (y_death == 1).sum()))
        if recall >= TARGET_DEATH_RECALL:
            acceptable.append((threshold, recall))
    require(acceptable, "no validation threshold reaches target death recall")
    threshold, validation_recall = max(acceptable, key=lambda x: x[0])
    return {"target_death_recall": TARGET_DEATH_RECALL, "threshold": float(threshold), "validation_death_recall": validation_recall}


def risk_test(frame: pd.DataFrame, test: pd.Series, preds: dict[str, np.ndarray], threshold: float) -> dict[str, Any]:
    valid = test & valid_mask(frame)
    won = frame.loc[valid, "won"].to_numpy(dtype=int)
    death = 1 - won
    death_probability = 1.0 - preds["p_win"][valid.to_numpy()]
    fallback = death_probability >= threshold
    at_half = death_probability >= 0.5
    return {
        "threshold": float(threshold),
        "death_recall": float((fallback & (death == 1)).sum() / max(1, (death == 1).sum())),
        "false_alarm_rate": float((fallback & (won == 1)).sum() / max(1, (won == 1).sum())),
        "fallback_fraction": float(fallback.mean()),
        "death_confusion_at_0.5": [[int(((death == a) & (at_half == b)).sum()) for b in (0, 1)] for a in (0, 1)],
        "n": int(len(won)),
    }


def bootstrap(frame: pd.DataFrame, test: pd.Series, candidate: dict[str, np.ndarray], baseline: dict[str, np.ndarray], metric: str, base: dict[str, float], replicates: int, seed: int) -> dict[str, Any] | None:
    valid = test & valid_mask(frame)
    if metric == "expected_signed_mae":
        selected = valid; values = "primary_signed"; truth_name = "signedOutcome"; base_values = np.full(int(selected.sum()), base["signed_mean"])
    elif metric == "survival_brier":
        selected = valid; values = "p_win"; truth_name = "won"; base_values = np.full(int(selected.sum()), base["survival_prior"])
    elif metric == "win_hp_mae":
        selected = valid & frame.won.eq(1); values = "predicted_win_hp_frac"; truth_name = "winHpFrac"; base_values = np.full(int(selected.sum()), base["win_hp_mean"])
    elif metric == "loss_severity_mae":
        selected = valid & frame.trueDeath.eq(1) & ~frame.progressAmbiguous.eq(1); values = "predicted_loss_remaining_frac"; truth_name = "lossRemainingFrac"; base_values = np.full(int(selected.sum()), base["loss_mean"])
    else:
        raise ValueError(f"unknown bootstrap metric {metric}")
    if not selected.any() or values not in candidate or values not in baseline:
        return None
    indices = selected.to_numpy()
    truth = frame.loc[selected, truth_name].to_numpy(dtype=float)
    candidate_error = np.abs(candidate[values][indices] - truth)
    baseline_error = np.abs(baseline[values][indices] - truth)
    sources = frame.loc[selected, "sourceSeed"].to_numpy(dtype=int)
    unique = np.unique(sources)
    candidate_sums = np.array([candidate_error[sources == source].sum() for source in unique])
    baseline_sums = np.array([baseline_error[sources == source].sum() for source in unique])
    counts = np.array([(sources == source).sum() for source in unique], dtype=float)
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(unique), size=(replicates, len(unique)))
    deltas = candidate_sums[draws].sum(axis=1) / counts[draws].sum(axis=1) - baseline_sums[draws].sum(axis=1) / counts[draws].sum(axis=1)
    return {"metric": metric, "unit": "sourceSeed", "source_groups": int(len(unique)), "replicates": int(replicates),
            "difference": float(candidate_error.mean() - baseline_error.mean()),
            "ci95": [float(np.percentile(deltas, 2.5)), float(np.percentile(deltas, 97.5))]}


def leave_one_loss(frame: pd.DataFrame, test: pd.Series, preds: dict[str, np.ndarray], base: float) -> dict[str, Any] | None:
    selected = test & valid_mask(frame) & frame.trueDeath.eq(1) & ~frame.progressAmbiguous.eq(1)
    if "predicted_loss_remaining_frac" not in preds or not selected.any():
        return None
    sources = sorted(int(x) for x in frame.loc[selected, "sourceSeed"].unique())
    differences = []
    for source in sources:
        keep = selected & frame.sourceSeed.ne(source)
        truth = frame.loc[keep, "lossRemainingFrac"].to_numpy(dtype=float)
        indices = keep.to_numpy()
        differences.append(float(np.abs(preds["predicted_loss_remaining_frac"][indices] - truth).mean() - np.abs(base - truth).mean()))
    return {"independent_death_sources": len(sources), "model_minus_trivial_mae_range": [min(differences), max(differences)]}


def ranking(frame: pd.DataFrame, test: pd.Series, primary: np.ndarray) -> dict[str, Any]:
    from scipy.stats import spearmanr

    selected = test & valid_mask(frame)
    decisions = []
    pairwise: list[float] = []
    spearmans: list[float] = []
    for _, group in frame.loc[selected].groupby(["sourceSeed", "decisionIdx"]):
        if len(group) < 2 or group.signedOutcome.nunique() < 2:
            continue
        indices = group.index.to_numpy()
        truth = group.signedOutcome.to_numpy(dtype=float)
        predicted = primary[indices]
        concordant = 0.0
        comparable = 0
        for left in range(len(truth)):
            for right in range(left + 1, len(truth)):
                true_sign = np.sign(truth[left] - truth[right])
                pred_sign = np.sign(predicted[left] - predicted[right])
                comparable += 1
                concordant += 1.0 if true_sign == pred_sign and pred_sign != 0 else 0.5 if pred_sign == 0 else 0.0
        pairwise.append(concordant / comparable)
        rho = 0.0 if np.all(predicted == predicted[0]) else spearmanr(truth, predicted).statistic
        spearmans.append(0.0 if not np.isfinite(rho) else float(rho))
        decisions.append((int(group.sourceSeed.iloc[0]), int(group.decisionIdx.iloc[0])))
    return {"eligible_decisions": len(decisions), "macro_pairwise_concordance": float(np.mean(pairwise)) if pairwise else None,
            "macro_spearman": float(np.mean(spearmans)) if spearmans else None, "pairwise_definition": "predicted ties count half"}


def model_size_and_latency(arm: dict[str, Any], frame: pd.DataFrame, features: list[str], test: pd.Series, repeats: int) -> dict[str, Any]:
    import xgboost as xgb

    row_mask = pd.Series(False, index=frame.index)
    row_mask.iloc[int(np.flatnonzero(test.to_numpy())[0]) if test.any() else 0] = True
    if arm["kind"] in ("factorized_xgb", "direct_signed_xgb"):
        matrix = xgb.DMatrix(frame.loc[row_mask, features])
        head_samples: dict[str, list[float]] = {name: [] for name in arm["models"]}
        for model_name, model in arm["models"].items():
            for _ in range(100):
                prediction(model, matrix)
            for _ in range(repeats):
                start = time.perf_counter_ns(); prediction(model, matrix)
                head_samples[model_name].append((time.perf_counter_ns() - start) / 1e6)
        heads = {name: {"median_ms": float(np.percentile(values, 50)), "p95_ms": float(np.percentile(values, 95))}
                 for name, values in head_samples.items()}
        median = float(sum(value["median_ms"] for value in heads.values()))
        p95 = float(sum(value["p95_ms"] for value in heads.values()))
        outputs = sorted(arm["models"])
    else:
        import torch
        normalization = arm["normalization"]
        values = ((frame.loc[row_mask, features].to_numpy(dtype=np.float32) - np.asarray(normalization["mean"], dtype=np.float32)) /
                  np.asarray(normalization["std"], dtype=np.float32))
        tensor = torch.from_numpy(values)
        for _ in range(100):
            nn_outputs(arm["models"]["mlp"], tensor)
        samples = []
        for _ in range(repeats):
            start = time.perf_counter_ns(); nn_outputs(arm["models"]["mlp"], tensor)
            samples.append((time.perf_counter_ns() - start) / 1e6)
        median = float(np.percentile(samples, 50)); p95 = float(np.percentile(samples, 95))
        heads = {"multitask_forward": {"median_ms": median, "p95_ms": p95}}
        outputs = ["p_win", "predicted_win_hp_frac", "predicted_loss_remaining_frac", "expected_signed_outcome", "direct_signed_outcome"]
    return {"batch_size": 1, "repeats": repeats, "median_ms": median, "p95_ms": p95,
            "cpu": platform.processor(), "heads": heads, "outputs": outputs}


def save_arm(arm: dict[str, Any], output: Path, name: str, features: list[str]) -> dict[str, Any]:
    paths: dict[str, Any] = {}
    if arm["kind"] in ("factorized_xgb", "direct_signed_xgb"):
        for model_name, model in arm["models"].items():
            path = output / f"{name}.{model_name}.json"
            model.save_model(path)
            paths[model_name] = {"path": str(path.resolve()), "bytes": path.stat().st_size, "sha256": sha256(path)}
    else:
        import torch
        path = output / f"{name}.pt"
        torch.save({"state_dict": arm["models"]["mlp"].module.state_dict(), "features": features,
                    "normalization": arm["normalization"], "parameters": arm["parameters"]}, path)
        paths["mlp"] = {"path": str(path.resolve()), "bytes": path.stat().st_size, "sha256": sha256(path)}
    return paths


def classify(finalists: dict[str, Any], bootstrap_metrics: dict[str, Any]) -> dict[str, Any]:
    improved = []
    for name, values in bootstrap_metrics.items():
        delta = values.get("expected_signed_mae")
        if delta is not None and delta["difference"] < 0 and delta["ci95"][1] < 0:
            improved.append(name)
    test_mae = {name: values["test"]["primary_signed"]["model"]["mae"] for name, values in finalists.items()}
    baseline_mae = test_mae["A"]
    lower_but_uncertain = [name for name, value in test_mae.items() if name != "A" and value < baseline_mae]
    if improved:
        decision = "MODEL IMPROVED"
    elif lower_but_uncertain:
        decision = "NO CLEAR MODEL IMPROVEMENT"
    else:
        decision = "NO CLEAR MODEL IMPROVEMENT"
    loss_weak = []
    for name, values in finalists.items():
        loss = values["test"].get("loss_severity")
        if loss is not None and loss["model"]["mae"] >= loss["train_death_mean_baseline"]["mae"]:
            loss_weak.append(name)
    capacity_signal = any(
        values["train"]["primary_signed"]["model"]["mae"] < finalists["A"]["train"]["primary_signed"]["model"]["mae"]
        and values["test"]["primary_signed"]["model"]["mae"] >= baseline_mae
        for name, values in finalists.items() if name != "A"
    )
    return {
        "decision": decision,
        "strictly_improved_finalists": improved,
        "lower_test_mae_but_uncertain": lower_but_uncertain,
        "loss_tail_failed_to_beat_trivial": loss_weak,
        "capacity_not_the_bottleneck_signal": capacity_signal,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--bootstrap-replicates", type=int, default=5000)
    parser.add_argument("--latency-repeats", type=int, default=2000)
    parser.add_argument("--nn-epochs", type=int, default=600)
    args = parser.parse_args()
    require(args.threads == 1, "scientific run requires one CPU thread")
    require(args.bootstrap_replicates >= 5000, "at least 5,000 bootstrap replicates are required")
    root = args.artifact_root.resolve()
    manifests = sorted((root / "data").glob("shard-*.combat.csv.manifest.json"))
    frame, corpus = load_corpus(manifests, evidence_path=args.evidence.resolve())
    require(corpus["raw_package"] is None, "raw package should not be duplicated into this experiment")
    split = frame.sourceSeed.map(stable_split(frame.sourceSeed))
    features, feature_contract = build_features(frame, split)
    base = baselines(frame, split)
    train = split.eq("train"); validation = split.eq("validation"); test = split.eq("test")
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)

    # Phase 1: fit only enough to select every finalist from validation.
    arms: dict[str, dict[str, Any]] = {}
    selection: dict[str, Any] = {"validation_metric": "expected signed MAE", "early_stopping_rounds": EARLY_STOPPING,
                                 "factorized_candidates": {}, "direct_candidates": {}, "nn_candidates": {}}
    for name, config in FACTORIAL_GRID.items():
        arm = make_factorized(frame, split, features, config, threads=args.threads, early_stopping=(name != "B0"))
        metrics = evaluate(frame, validation, arm["predict"](validation), base, True)
        selection["factorized_candidates"][name] = {"validation_expected_signed_mae": metrics["expected_signed_outcome"]["model"]["mae"],
                                                      "metrics": metrics, "best_iterations": arm["best_iterations"]}
        arms[name] = arm
    best_factorized = min(FACTORIAL_GRID, key=lambda name: selection["factorized_candidates"][name]["validation_expected_signed_mae"])
    selection["factorized_finalist"] = best_factorized

    for name, config in DIRECT_GRID.items():
        arm = make_direct(frame, split, features, config, threads=args.threads)
        metrics = evaluate(frame, validation, arm["predict"](validation), base, False)
        selection["direct_candidates"][name] = {"validation_signed_mae": metrics["primary_signed"]["model"]["mae"],
                                                 "metrics": metrics, "best_iterations": arm["best_iterations"]}
        arms[name] = arm
    best_direct = min(DIRECT_GRID, key=lambda name: selection["direct_candidates"][name]["validation_signed_mae"])
    selection["direct_finalist"] = best_direct

    for name, hidden in NN_GRID.items():
        arm = train_nn(frame, split, features, hidden, max_epochs=args.nn_epochs, patience=EARLY_STOPPING)
        metrics = evaluate(frame, validation, arm["predict"](validation), base, True)
        selection["nn_candidates"][name] = {"validation_factorized_expected_signed_mae": metrics["expected_signed_outcome"]["model"]["mae"],
                                              "validation_direct_signed_mae": metrics["primary_signed"]["model"]["mae"],
                                              "metrics": metrics, "parameters": arm["parameters"]}
        arms[name] = arm
    best_nn = min(NN_GRID, key=lambda name: selection["nn_candidates"][name]["validation_factorized_expected_signed_mae"])
    selection["nn_finalist"] = best_nn
    selection["finalists"] = {"A": "A", "B": best_factorized, "C": best_direct, "D": best_nn, "E": "E-balanced"}
    (output / "selection-freeze.json").write_text(json.dumps(selection, indent=2, sort_keys=True) + "\n")

    # Phase 2: create final predictions only after the finalist freeze record.
    finalists = {
        "A": make_factorized(frame, split, features, FACTORIAL_GRID["B0"], threads=args.threads, early_stopping=False),
        "B": arms[best_factorized],
        "C": arms[best_direct],
        "D": arms[best_nn],
        "E": make_factorized(frame, split, features, FACTORIAL_GRID[best_factorized], threads=args.threads, early_stopping=True, balanced=True),
    }
    predictions = {name: arm["predict"](pd.Series(True, index=frame.index)) for name, arm in finalists.items()}
    validation_thresholds = {}
    for name, arm in finalists.items():
        if "p_win" in predictions[name]:
            validation_thresholds[name] = choose_risk_threshold(frame, validation, arm["predict"](validation))

    # All calls below are TEST evaluation of the already frozen five finalists.
    metrics: dict[str, Any] = {}
    for name, arm in finalists.items():
        split_metrics = {part: evaluate(frame, split.eq(part), arm["predict"](split.eq(part)), base, arm["has_factorized"])
                         for part in ("train", "validation", "test")}
        primary = predictions[name]["primary_signed"]
        loss_tail = leave_one_loss(frame, test, predictions[name], base["loss_mean"])
        if loss_tail is not None:
            trivial_loss = {"predicted_loss_remaining_frac": np.full(len(frame), base["loss_mean"])}
            loss_tail["source_bootstrap_vs_trivial"] = bootstrap(
                frame, test, predictions[name], trivial_loss, "loss_severity_mae", base,
                args.bootstrap_replicates, SEED + 100 + len(metrics),
            )
        model_files = save_arm(arm, output, name, features)
        metrics[name] = {
            "kind": arm["kind"], "parameters": arm["parameters"], "best_iterations": arm.get("best_iterations"),
            "train": split_metrics["train"], "validation": split_metrics["validation"], "test": split_metrics["test"],
            "risk": {"validation": validation_thresholds[name], "test": risk_test(frame, test, predictions[name], validation_thresholds[name]["threshold"])} if name in validation_thresholds else None,
            "loss_tail": loss_tail,
            "ranking": ranking(frame, test, primary),
            "model_files": model_files,
            "model_size_bytes": int(sum(item["bytes"] for item in model_files.values())),
            "latency": model_size_and_latency(arm, frame, features, test, args.latency_repeats),
        }

    bootstrap_metrics = {}
    for name, arm in finalists.items():
        if name == "A":
            continue
        bootstrap_metrics[name] = {metric: bootstrap(frame, test, predictions[name], predictions["A"], metric, base,
                                                      args.bootstrap_replicates, SEED + index)
                                   for index, metric in enumerate(("expected_signed_mae", "survival_brier", "win_hp_mae", "loss_severity_mae"))}

    test_table = frame.loc[test, ["sourceSeed", "decisionIdx", "semanticKey", "branchFightIdx", "encounter", "won", "trueDeath", "progressAmbiguous", "signedOutcome"]].copy()
    for name, values in predictions.items():
        for key in ("primary_signed", "expected_signed_outcome", "direct_signed_outcome", "p_win",
                    "predicted_win_hp_frac", "predicted_loss_remaining_frac"):
            if key in values:
                test_table[f"{name}__{key}"] = values[key][test.to_numpy()]
    test_predictions_path = output / "test_predictions.csv"
    test_table.to_csv(test_predictions_path, index=False)

    report = {
        "experiment": "precombat_combat_evaluator_model_comparison_v2",
        "baseline_main_sha": "b9d9fe16bc58e7060967f6154a2e16acd89500f5",
        "experiment_code_sha": __import__("subprocess").check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "constraints": {"simulator_called": False, "silver_called": False, "new_labels": False, "gameplay_integration": False, "runtime_model_export": False},
        "corpus": corpus, "expected_raw_package_sha256": EXPECTED_PACKAGE_SHA256,
        "feature_contract": feature_contract,
        "split": {name: {"source_seeds": int((split == name).groupby(frame.sourceSeed).any().sum()), "rows": int((split == name).sum())} for name in ("train", "validation", "test")},
        "baselines": base, "candidate_grids": {"factorized": FACTORIAL_GRID, "direct": DIRECT_GRID, "nn": {k: list(v) for k, v in NN_GRID.items()}},
        "selection_freeze": selection, "finalists": metrics, "paired_bootstrap_vs_A": bootstrap_metrics,
        "classification": classify(metrics, bootstrap_metrics),
        "test_predictions": {"path": str(test_predictions_path.resolve()), "bytes": test_predictions_path.stat().st_size, "sha256": sha256(test_predictions_path)},
        "software": {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__},
    }
    (output / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True, default=lambda value: value.item() if isinstance(value, np.generic) else value) + "\n")
    print(json.dumps({"output": str(output), "finalists": selection["finalists"], "test_primary_mae": {name: metrics[name]["test"]["primary_signed"]["model"]["mae"] for name in metrics}}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
