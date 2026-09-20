#!/usr/bin/env python3
"""Offline, source-seed-cross-fitted Silver prefix-value experiment.

This tool consumes the frozen PR #256 prefix packet and never calls the game,
Silver, Teacher A, or Teacher B.  It constructs causal, structured features,
fits the three preregistered small scorers, and writes an evidence packet.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import random
import statistics
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from sklearn.linear_model import Ridge
from scipy.stats import pearsonr, spearmanr
import torch
from torch import nn

REPLICATES = 32
FOLD_COUNT = 5
BOOTSTRAP_SEED = 20260920
TRAINING_SEED = 20260920
CARD_COUNT = 371
MAX_MONSTERS = 5
EXPECTED_LENGTH_COUNTS = {1: 1266, 2: 4928}
FORBIDDEN_FIELDS = {
    "group_id", "source_seed", "leaf_snapshot_id", "prefix_key", "rng_identity",
    "replicate", "teacher_a", "teacher_b", "continuation_result", "oracle_choice",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def fnv1a(value: str) -> int:
    result = 1469598103934665603
    for byte in value.encode():
        result ^= byte
        result = (result * 1099511628211) & ((1 << 64) - 1)
    return result


def source_fold(source_seed: str | int) -> int:
    return fnv1a(str(source_seed)) % FOLD_COUNT


def choose_predicted(candidates: list[dict], arm: str) -> dict:
    """Select by prediction, then frozen max(mean, prefix_key) tie-break."""
    top_score = max(row[f"predicted_{arm}"] for row in candidates)
    return max((row for row in candidates if row[f"predicted_{arm}"] == top_score),
               key=lambda row: row["prefix_key"])


def jsonl(path: Path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def card_list(pile: dict) -> list[dict]:
    return list(pile.get("knownBottom", [])) + list(pile.get("unknown", [])) + list(pile.get("knownTop", []))


def bit_features(value: int, width: int = 64) -> list[float]:
    return [float((int(value) >> bit) & 1) for bit in range(width)]


def state_features(state: dict) -> tuple[list[float], list[str]]:
    """Causal fixed-width state packet; isolated/RNG/provenance fields are omitted."""
    player = state["player"]
    hand = state.get("hand", [])
    monsters = state.get("monsters", [])
    hp = max(1, int(player.get("maxHp", 1)))
    names: list[str] = []
    values: list[float] = []

    def add(name: str, value: float) -> None:
        names.append(name)
        values.append(float(value))

    for key, scale in (
        ("curHp", 100.0), ("maxHp", 100.0), ("block", 100.0), ("energy", 10.0),
        ("energyPerTurn", 10.0), ("strength", 20.0), ("dexterity", 20.0),
        ("artifact", 10.0), ("turn", 20.0), ("cardsPlayedThisTurn", 10.0),
        ("attacksPlayedThisTurn", 10.0), ("skillsPlayedThisTurn", 10.0),
        ("cardDrawPerTurn", 10.0), ("energyWasted", 10.0),
    ):
        add("player_" + key, float(player.get(key, state.get(key, 0))) / scale)
    add("player_hp_fraction", int(player.get("curHp", 0)) / hp)

    global_values = (
        ("act", state.get("act", 0), 4.0), ("floor", state.get("floorNum", 0), 60.0),
        ("encounter", state.get("encounter", 0), 50.0),
        ("living_monsters", state.get("monstersAlive", 0), 5.0),
        ("monster_count", state.get("monsterCount", 0), 5.0),
        ("hand_size", len(hand), 20.0),
        ("draw_size", len(card_list(state.get("drawPile", {}))), 50.0),
        ("discard_size", len(card_list(state.get("discardPile", {}))), 50.0),
        ("exhaust_size", len(card_list(state.get("exhaustPile", {}))), 50.0),
        ("potion_count", state.get("potionCount", 0), 5.0),
        ("potion_capacity", state.get("potionCapacity", 0), 5.0),
        ("cards_drawn", state.get("cardsDrawn", 0), 20.0),
        ("input_state", state.get("inputState", 0), 10.0),
        ("intents_hidden", int(bool(state.get("intentsHidden", False))), 1.0),
    )
    for key, value, scale in global_values:
        add("global_" + key, float(value) / scale)

    for key in ("statusBits0", "statusBits1"):
        for bit, value in enumerate(bit_features(player.get(key, 0))):
            add(f"player_{key}_{bit}", value)
    for index, value in enumerate(player.get("relicCounters", [])):
        add(f"player_relic_counter_{index}", float(value) / 20.0)
    while len([name for name in names if name.startswith("player_relic_counter_")]) < 7:
        index = len([name for name in names if name.startswith("player_relic_counter_")])
        add(f"player_relic_counter_{index}", 0.0)

    for pile_name, pile in (("hand", hand), ("draw", card_list(state.get("drawPile", {}))),
                            ("discard", card_list(state.get("discardPile", {}))),
                            ("exhaust", card_list(state.get("exhaustPile", {})))):
        counts = [0] * CARD_COUNT
        for card in pile:
            card_id = int(card.get("id", 0))
            if 0 <= card_id < CARD_COUNT:
                counts[card_id] += 1
        for card_id, count in enumerate(counts):
            add(f"{pile_name}_card_{card_id}", count / 10.0)
    upgraded = [0] * CARD_COUNT
    for card in hand:
        card_id = int(card.get("id", 0))
        if 0 <= card_id < CARD_COUNT and card.get("upgraded", False):
            upgraded[card_id] += 1
    for card_id, count in enumerate(upgraded):
        add(f"hand_upgraded_card_{card_id}", count / 10.0)

    for slot in range(MAX_MONSTERS):
        monster = monsters[slot] if slot < len(monsters) else {}
        max_hp = max(1, int(monster.get("maxHp", 1)))
        fields = (
            ("id", monster.get("id", 0) / 100.0),
            ("alive", int(monster.get("curHp", 0)) > 0),
            ("hp", monster.get("curHp", 0) / 300.0),
            ("max_hp", monster.get("maxHp", 0) / 300.0),
            ("hp_fraction", monster.get("curHp", 0) / max_hp),
            ("block", monster.get("block", 0) / 100.0),
            ("strength", monster.get("strength", 0) / 20.0),
            ("vulnerable", monster.get("vulnerable", 0) / 10.0),
            ("weak", monster.get("weak", 0) / 10.0),
            ("move0", monster.get("moveHistory", [0, 0])[0] / 50.0),
            ("move1", monster.get("moveHistory", [0, 0])[-1] / 50.0),
            ("status_popcount", int(monster.get("statusBits", 0)).bit_count() / 64.0),
        )
        for name, value in fields:
            add(f"monster_{slot}_{name}", value)
    return values, names


def parse_action(fingerprint: str, state: dict) -> dict:
    fields = {part.split("=", 1)[0]: part.split("=", 1)[1]
              for part in fingerprint.split("/") if "=" in part}
    action_type = int(fields.get("t", "0"))
    if action_type not in (1, 5):
        raise ValueError(f"unsupported action type in frozen CARD/END_TURN surface: {fingerprint}")
    card = [int(value) for value in fields.get("c", "0_0_0_0_0_0_0_0").split("_")]
    if len(card) != 8:
        raise ValueError(f"malformed card fingerprint: {fingerprint}")
    target = int(fields.get("x", "-1"))
    monsters = state.get("monsters", [])
    target_valid = 0 <= target < len(monsters) and int(monsters[target].get("curHp", 0)) > 0
    target_hp_fraction = 0.0
    if target_valid:
        target_hp_fraction = int(monsters[target].get("curHp", 0)) / max(1, int(monsters[target].get("maxHp", 1)))
    return {
        "type": "END_TURN" if action_type == 5 else "CARD",
        "type_id": action_type,
        "card_id": card[0] if action_type == 1 else -1,
        "cost": card[3] if action_type == 1 else 0,
        "cost_for_turn": card[4] if action_type == 1 else 0,
        "special_data": card[2] if action_type == 1 else 0,
        "upgraded": card[5] if action_type == 1 else 0,
        "free_to_play_once": card[6] if action_type == 1 else 0,
        "retain": card[7] if action_type == 1 else 0,
        "target": target,
        "target_hp_fraction": target_hp_fraction,
        "target_alive": int(target_valid),
        "is_end_turn": int(action_type == 5),
    }


def action_numeric(action: dict) -> list[float]:
    target = action["target"]
    return ([float(action["is_end_turn"]), float(action["type_id"] == 1),
             action["cost"] / 5.0, action["cost_for_turn"] / 5.0,
             float(action["upgraded"]), action["special_data"] / 50.0,
             float(action["free_to_play_once"]), float(action["retain"])]
            + [float(target == slot) for slot in range(MAX_MONSTERS)]
            + [action["target_hp_fraction"], float(action["target_alive"]),
               float(action["type_id"] == 0)])


def none_action() -> dict:
    return {"type": "NONE", "type_id": 0, "card_id": -1, "cost": 0,
            "cost_for_turn": 0, "special_data": 0, "upgraded": 0,
            "free_to_play_once": 0, "retain": 0, "target": -1,
            "target_hp_fraction": 0.0, "target_alive": 0, "is_end_turn": 0}


def load_inputs(prefix_path: Path, corpus_path: Path, baseline_path: Path,
                teachers_path: Path, manifest_path: Path) -> tuple[list[dict], dict, dict, dict]:
    leaves = {}
    for row in jsonl(corpus_path):
        leaf = row["leaf_snapshot_id"]
        if leaf in leaves:
            raise SystemExit(f"duplicate corpus leaf: {leaf}")
        leaves[leaf] = row
    baseline_rows = defaultdict(list)
    for row in jsonl(baseline_path):
        if row.get("accepted"):
            baseline_rows[row["leaf_snapshot_id"]].append(row)
    baseline = {}
    for leaf, rows in baseline_rows.items():
        rows = sorted(rows, key=lambda row: int(row["replicate"]))
        if len(rows) != REPLICATES or {int(row["replicate"]) for row in rows} != set(range(REPLICATES)):
            continue
        baseline[leaf] = {
            "value": statistics.fmean(row["original_root_corrected_utility"] for row in rows),
            "source_seed": str(rows[0]["source_seed"]),
        }
    teachers = defaultdict(dict)
    for row in jsonl(teachers_path):
        if row.get("state_kind") == "leaf" and row.get("teacher_valid") and row.get("selected_q_valid"):
            teachers[row["leaf_snapshot_id"]][row["replicate"]] = row["original_root_corrected_teacher_value"]
    teachers = {leaf: values for leaf, values in teachers.items() if "A" in values and "B" in values}
    manifest = json.loads(manifest_path.read_text())
    values = defaultdict(dict)
    metadata = {}
    for row in jsonl(prefix_path):
        if not row.get("accepted") or int(row["requested_prefix_length"]) > 2:
            continue
        key = row["requested_prefix_key"]
        leaf = row["leaf_snapshot_id"]
        rep = int(row["replicate"])
        identity = (leaf, key)
        if rep in values[identity]:
            raise SystemExit(f"duplicate candidate replicate: {leaf}/{key}/{rep}")
        values[identity][rep] = row["original_root_corrected_utility"]
        old = metadata.setdefault(identity, row)
        if old["requested_prefix_fingerprints"] != row["requested_prefix_fingerprints"]:
            raise SystemExit(f"candidate key metadata mismatch: {identity}")
    rows = []
    for (leaf, key), samples in sorted(values.items()):
        if set(samples) != set(range(REPLICATES)):
            raise SystemExit(f"candidate lacks all 32 replicates: {leaf}/{key}")
        meta = metadata[(leaf, key)]
        corpus = leaves.get(leaf)
        if corpus is None or leaf not in baseline or leaf not in teachers:
            continue
        fingerprints = meta["requested_prefix_fingerprints"]
        if len(fingerprints) not in EXPECTED_LENGTH_COUNTS:
            raise SystemExit("unexpected candidate prefix length")
        state = corpus["leaf_state"]["state"]
        state_vec, state_names = state_features(state)
        actions = [parse_action(fp, state) for fp in fingerprints]
        rows.append({
            "group_id": corpus["group_id"], "source_seed": str(meta["source_seed"]),
            "leaf_snapshot_id": leaf, "prefix_key": key, "prefix_length": len(fingerprints),
            "prefix_fingerprints": fingerprints, "state_features": state_vec,
            "action1": actions[0], "action2": actions[1] if len(actions) == 2 else none_action(),
            "q32": statistics.fmean(samples.values()), "leaf_baseline32": baseline[leaf]["value"],
            "centered_q": statistics.fmean(samples.values()) - baseline[leaf]["value"],
            "teacher_a": teachers[leaf]["A"], "teacher_b": teachers[leaf]["B"],
        })
    lengths = Counter(row["prefix_length"] for row in rows)
    if dict(lengths) != EXPECTED_LENGTH_COUNTS:
        raise SystemExit(f"candidate cardinality mismatch: {dict(lengths)}")
    leaf_counts = Counter(row["leaf_snapshot_id"] for row in rows)
    if len(leaf_counts) != 247:
        raise SystemExit(f"expected 247 leaves, found {len(leaf_counts)}")
    by_leaf = defaultdict(set)
    for row in rows:
        by_leaf[row["leaf_snapshot_id"]].add(row["prefix_key"])
        if row["prefix_length"] == 2:
            parent = json.dumps(row["prefix_fingerprints"][:1], separators=(",", ":"))
            if (row["leaf_snapshot_id"], parent) not in metadata:
                raise SystemExit(f"length-2 candidate lacks length-1 parent: {row['prefix_key']}")
    if len({row["source_seed"] for row in rows}) != 20:
        raise SystemExit("source-seed coverage mismatch")
    group_sources = defaultdict(set)
    for row in rows:
        group_sources[row["group_id"]].add(row["source_seed"])
    if any(len(seeds) != 1 for seeds in group_sources.values()):
        raise SystemExit("a sibling group spans multiple source seeds")
    return rows, leaves, manifest, {"state_feature_names": state_names}


def write_features(rows: list[dict], path: Path, schema: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = {"feature_schema": "silver_learned_prefix_candidate_features_v1",
              "feature_count": len(rows[0]["state_features"]) if rows else 0,
              "state_feature_names": schema["state_feature_names"],
              "model_input_fields": ["state_features", "action1", "action2", "prefix_length"],
              "forbidden_model_fields": sorted(FORBIDDEN_FIELDS),
              "card_count": CARD_COUNT, "candidate_rows": len(rows),
              "target": "centered_q=q32-leaf_baseline32"}
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        stream.write(json.dumps(header, sort_keys=True) + "\n")
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")


def linear_vector(row: dict) -> np.ndarray:
    parts = list(row["state_features"])
    for action in (row["action1"], row["action2"]):
        parts.extend(action_numeric(action))
        one_hot = [0.0] * CARD_COUNT
        if 0 <= action["card_id"] < CARD_COUNT:
            one_hot[action["card_id"]] = 1.0
        parts.extend(one_hot)
    a1, a2 = row["action1"], row["action2"]
    parts.extend([row["prefix_length"] / 2.0, float(a1["target"] == a2["target"]),
                  float(a1["card_id"] == a2["card_id"]), float(a1["is_end_turn"]),
                  float(a2["is_end_turn"])])
    return np.asarray(parts, dtype=np.float32)


def mlp_numeric(row: dict) -> np.ndarray:
    parts = list(row["state_features"])
    parts.extend(action_numeric(row["action1"]))
    parts.extend(action_numeric(row["action2"]))
    a1, a2 = row["action1"], row["action2"]
    parts.extend([row["prefix_length"] / 2.0, float(a1["target"] == a2["target"]),
                  float(a1["card_id"] == a2["card_id"]), float(a1["is_end_turn"]),
                  float(a2["is_end_turn"])])
    return np.asarray(parts, dtype=np.float32)


def standardize(train: np.ndarray, values: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mean = train.mean(axis=0)
    scale = train.std(axis=0)
    scale[scale < 1e-6] = 1.0
    return (train - mean) / scale, (values - mean) / scale, (mean, scale)


class FlatMLP(nn.Module):
    def __init__(self, numeric_width: int):
        super().__init__()
        self.card = nn.Embedding(CARD_COUNT + 1, 16)
        self.net = nn.Sequential(nn.Linear(numeric_width + 32, 32), nn.ReLU(),
                                 nn.Linear(32, 32), nn.ReLU(), nn.Linear(32, 1))

    def forward(self, numeric: torch.Tensor, cards: torch.Tensor) -> torch.Tensor:
        return self.net(torch.cat((numeric, self.card(cards).flatten(1)), dim=1)).squeeze(1)


class FactorizedMLP(nn.Module):
    def __init__(self, state_width: int, action_width: int):
        super().__init__()
        self.card = nn.Embedding(CARD_COUNT + 1, 16)
        self.state_encoder = nn.Sequential(nn.Linear(state_width, 32), nn.ReLU())
        self.q_trunk = nn.Sequential(nn.Linear(32 + action_width + 16, 32), nn.ReLU(),
                                     nn.Linear(32, 32), nn.ReLU())
        self.delta_trunk = nn.Sequential(nn.Linear(32 + 2 * action_width + 32, 32), nn.ReLU(),
                                         nn.Linear(32, 32), nn.ReLU())
        self.q_head = nn.Linear(32, 1)
        self.delta_head = nn.Linear(32, 1)

    def forward(self, state: torch.Tensor, a1: torch.Tensor, a2: torch.Tensor,
                cards: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        embeds = self.card(cards)
        encoded_state = self.state_encoder(state)
        q = self.q_head(self.q_trunk(torch.cat((encoded_state, a1, embeds[:, 0]), dim=1))).squeeze(1)
        delta = self.delta_head(self.delta_trunk(torch.cat((encoded_state, a1, a2, embeds.flatten(1)), dim=1))).squeeze(1)
        return q, delta


def card_ids(rows: list[dict]) -> np.ndarray:
    return np.asarray([[max(0, r["action1"]["card_id"]), max(0, r["action2"]["card_id"])] for r in rows], dtype=np.int64)


def fit_ridge(train: list[dict], test: list[dict]) -> tuple[np.ndarray, dict]:
    x_train = np.stack([linear_vector(row) for row in train])
    x_test = np.stack([linear_vector(row) for row in test])
    x_train, x_test, (mean, scale) = standardize(x_train, x_test)
    model = Ridge(alpha=10.0, fit_intercept=True)
    model.fit(x_train, [row["centered_q"] for row in train])
    timings = []
    by_leaf = defaultdict(list)
    for index, row in enumerate(test): by_leaf[row["leaf_snapshot_id"]].append(index)
    for indices in by_leaf.values():
        start = time.perf_counter()
        model.predict(x_test[indices])
        timings.append((time.perf_counter() - start) * 1000.0)
    return model.predict(x_test), {"parameters": int(model.coef_.size + 1),
                                   "serialized_bytes": int((model.coef_.size + 1) * 8),
                                   "normalization": {"mean": mean.tolist(), "scale": scale.tolist()},
                                   "forward_times_ms": timings}


def fit_flat(train: list[dict], test: list[dict], fold: int) -> tuple[np.ndarray, dict, object]:
    numeric_train = np.stack([mlp_numeric(row) for row in train])
    numeric_test = np.stack([mlp_numeric(row) for row in test])
    numeric_train, numeric_test, (mean, scale) = standardize(numeric_train, numeric_test)
    torch.manual_seed(TRAINING_SEED + fold)
    torch.set_num_threads(1)
    model = FlatMLP(numeric_train.shape[1])
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    x = torch.from_numpy(numeric_train)
    cards = torch.from_numpy(card_ids(train))
    y = torch.tensor([row["centered_q"] for row in train], dtype=torch.float32)
    for _ in range(80):
        optimizer.zero_grad(set_to_none=True)
        loss = nn.functional.huber_loss(model(x, cards), y)
        loss.backward()
        optimizer.step()
    with torch.no_grad():
        prediction = model(torch.from_numpy(numeric_test), torch.from_numpy(card_ids(test))).numpy()
        timings = []
        by_leaf = defaultdict(list)
        for index, row in enumerate(test): by_leaf[row["leaf_snapshot_id"]].append(index)
        for indices in by_leaf.values():
            start = time.perf_counter()
            model(torch.from_numpy(numeric_test[indices]), torch.from_numpy(card_ids(test)[indices]))
            timings.append((time.perf_counter() - start) * 1000.0)
    params = sum(parameter.numel() for parameter in model.parameters())
    return prediction, {"parameters": params, "serialized_bytes": params * 4,
                        "normalization": {"mean": mean.tolist(), "scale": scale.tolist()},
                        "forward_times_ms": timings}, model


def fit_factorized(train: list[dict], test: list[dict], fold: int) -> tuple[np.ndarray, dict, object, dict]:
    state_width = len(train[0]["state_features"])
    action_width = len(action_numeric(train[0]["action1"]))
    s_train = np.asarray([row["state_features"] for row in train], dtype=np.float32)
    s_test = np.asarray([row["state_features"] for row in test], dtype=np.float32)
    a1_train = np.asarray([action_numeric(row["action1"]) for row in train], dtype=np.float32)
    a1_test = np.asarray([action_numeric(row["action1"]) for row in test], dtype=np.float32)
    a2_train = np.asarray([action_numeric(row["action2"]) for row in train], dtype=np.float32)
    a2_test = np.asarray([action_numeric(row["action2"]) for row in test], dtype=np.float32)
    # Normalization is fit only on the training source-seed fold.
    s_train, s_test, (smean, sscale) = standardize(s_train, s_test)
    a_train = np.concatenate((a1_train, a2_train), axis=0)
    a_test = np.concatenate((a1_test, a2_test), axis=0)
    a_train, a_test, (amean, ascale) = standardize(a_train, a_test)
    a1_train, a2_train = a_train[:len(train)], a_train[len(train):]
    a1_test, a2_test = a_test[:len(test)], a_test[len(test):]
    torch.manual_seed(TRAINING_SEED + 100 + fold)
    torch.set_num_threads(1)
    model = FactorizedMLP(state_width, action_width)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
    states = torch.from_numpy(s_train)
    x1, x2 = torch.from_numpy(a1_train), torch.from_numpy(a2_train)
    cards = torch.from_numpy(card_ids(train))
    q_targets = []
    delta_targets = []
    delta_mask = []
    for row in train:
        parent_q = row["q32"] if row["prefix_length"] == 1 else row["parent_q32"]
        q_targets.append(parent_q - row["leaf_baseline32"])
        delta_targets.append(row["centered_q"] - (parent_q - row["leaf_baseline32"]))
        delta_mask.append(float(row["prefix_length"] == 2))
    q_targets = torch.tensor(q_targets, dtype=torch.float32)
    delta_targets = torch.tensor(delta_targets, dtype=torch.float32)
    delta_mask = torch.tensor(delta_mask, dtype=torch.float32)
    for _ in range(80):
        optimizer.zero_grad(set_to_none=True)
        q_pred, delta_pred = model(states, x1, x2, cards)
        q_loss = nn.functional.huber_loss(q_pred, q_targets)
        d_loss = (nn.functional.huber_loss(delta_pred, delta_targets, reduction="none") * delta_mask).sum() / delta_mask.sum()
        (q_loss + d_loss).backward()
        optimizer.step()
    with torch.no_grad():
        q_pred, delta_pred = model(torch.from_numpy(s_test), torch.from_numpy(a1_test),
                                   torch.from_numpy(a2_test), torch.from_numpy(card_ids(test)))
        q_values = q_pred.numpy()
        delta_values = delta_pred.numpy()
        prediction = np.asarray([q if row["prefix_length"] == 1 else q + delta
                                 for row, q, delta in zip(test, q_values, delta_values)])
        timings = []
        by_leaf = defaultdict(list)
        for index, row in enumerate(test): by_leaf[row["leaf_snapshot_id"]].append(index)
        for indices in by_leaf.values():
            start = time.perf_counter()
            model(torch.from_numpy(s_test[indices]), torch.from_numpy(a1_test[indices]),
                  torch.from_numpy(a2_test[indices]), torch.from_numpy(card_ids(test)[indices]))
            timings.append((time.perf_counter() - start) * 1000.0)
    params = sum(parameter.numel() for parameter in model.parameters())
    aux = {"q1_prediction": q_values, "delta2_prediction": delta_values}
    return prediction, {"parameters": params, "serialized_bytes": params * 4,
                        "q1_normalization": {"state_mean": smean.tolist(), "state_scale": sscale.tolist()},
                        "action_normalization": {"mean": amean.tolist(), "scale": ascale.tolist()},
                        "forward_times_ms": timings}, model, aux


def add_parent_q(rows: list[dict]) -> None:
    by_key = {(row["leaf_snapshot_id"], row["prefix_key"]): row for row in rows}
    for row in rows:
        if row["prefix_length"] == 1:
            row["parent_q32"] = row["q32"]
        else:
            parent = json.dumps(row["prefix_fingerprints"][:1], separators=(",", ":"))
            row["parent_q32"] = by_key[(row["leaf_snapshot_id"], parent)]["q32"]


def bootstrap(rows: list[dict], arm_key: str, iterations: int = 2000) -> dict:
    source_groups = defaultdict(list)
    for row in rows:
        if row["group_id"] not in source_groups[row["source_seed"]]:
            source_groups[row["source_seed"]].append(row["group_id"])
    source_ids = sorted(source_groups)
    by_group = defaultdict(list)
    for row in rows:
        by_group[row["group_id"]].append(row)
    rng = random.Random(BOOTSTRAP_SEED)
    values = []
    for _ in range(iterations):
        baseline, candidate = [], []
        for occurrence, source in enumerate(rng.choice(source_ids) for _ in source_ids):
            for group in source_groups[source]:
                for row in by_group[group]:
                    left = dict(row)
                    left["group_id"] = f"{group}#{occurrence}"
                    baseline.append(left)
                    right = dict(left)
                    right["value"] = row[arm_key]
                    candidate.append(right)
        values.append(sibling_metrics(baseline, "baseline_value", "teacher_a")["mean_teacher_regret"]
                      - sibling_metrics(candidate, "value", "teacher_a")["mean_teacher_regret"])
    ordered = sorted(values)
    return {"p025": ordered[int(0.025 * (len(ordered) - 1))],
            "p975": ordered[int(0.975 * (len(ordered) - 1))],
            "bootstrap_seed": BOOTSTRAP_SEED, "iterations": iterations,
            "cluster_key": "source_seed", "cluster_count": len(source_ids)}


def sibling_metrics(rows: list[dict], value_key: str, reference_key: str) -> dict:
    groups = defaultdict(list)
    for row in rows:
        groups[row["group_id"]].append(row)
    regrets, centered, pairs, agreements, top_agreement = [], [], 0, 0, 0
    for members in groups.values():
        if len(members) < 2:
            continue
        candidate_top = max(members, key=lambda row: row[value_key])
        reference_top = max(members, key=lambda row: row[reference_key])
        top_agreement += candidate_top["leaf_snapshot_id"] == reference_top["leaf_snapshot_id"]
        regrets.append(reference_top[reference_key] - candidate_top[reference_key])
        candidate_mean = statistics.fmean(row[value_key] for row in members)
        reference_mean = statistics.fmean(row[reference_key] for row in members)
        centered.extend((row[value_key] - candidate_mean) - (row[reference_key] - reference_mean)
                        for row in members)
        for left in range(len(members)):
            for right in range(left + 1, len(members)):
                delta = members[left][value_key] - members[right][value_key]
                target = members[left][reference_key] - members[right][reference_key]
                if delta and target:
                    pairs += 1
                    agreements += (delta > 0) == (target > 0)
    return {"groups": len(regrets), "pairwise_concordance": agreements / pairs if pairs else None,
            "pairwise_pairs": pairs, "top_leaf_agreement": top_agreement / len(regrets) if regrets else None,
            "mean_teacher_regret": statistics.fmean(regrets) if regrets else None,
            "value_mae": statistics.fmean(abs(row[value_key] - row[reference_key]) for row in rows),
            "centered_mae": statistics.fmean(abs(value) for value in centered),
            "centered_rmse": math.sqrt(statistics.fmean(value * value for value in centered))}


def group_diagnostics(rows: list[dict]) -> dict:
    groups = defaultdict(list)
    for row in rows:
        groups[row["group_id"]].append(row)
    changes = []
    for group, members in groups.items():
        teacher_top = max(members, key=lambda row: row["teacher_a"])
        baseline_top = max(members, key=lambda row: row["baseline_value"])
        model_top = max(members, key=lambda row: row["value"])
        baseline_regret = teacher_top["teacher_a"] - baseline_top["teacher_a"]
        model_regret = teacher_top["teacher_a"] - model_top["teacher_a"]
        changes.append({"group_id": group, "improvement": baseline_regret - model_regret,
                        "baseline_regret": baseline_regret, "model_regret": model_regret,
                        "baseline_leaf": baseline_top["leaf_snapshot_id"],
                        "model_leaf": model_top["leaf_snapshot_id"]})
    changes.sort(key=lambda row: row["improvement"], reverse=True)
    return {"improved": sum(row["improvement"] > 0 for row in changes),
            "unchanged": sum(row["improvement"] == 0 for row in changes),
            "worsened": sum(row["improvement"] < 0 for row in changes),
            "largest_improvements": changes[:8], "largest_regressions": changes[-8:]}


def timing_summary(arm_meta: dict) -> dict:
    values = [time_ms for fold in arm_meta["folds"] for time_ms in fold.get("forward_times_ms", [])]
    return {"batch": "all candidates for one leaf", "threading": "single torch thread / sklearn predict",
            "median_ms": float(np.percentile(values, 50)), "p95_ms": float(np.percentile(values, 95)),
            "samples": len(values)}


def fit_metrics(rows: list[dict], arm: str, oracle_q: float, baseline_a: float) -> dict:
    by_leaf = defaultdict(list)
    for row in rows:
        by_leaf[row["leaf_snapshot_id"]].append(row)
    selected = []
    for leaf, candidates in by_leaf.items():
        # Frozen #256 contract: max(predicted score, prefix_key).
        choice = choose_predicted(candidates, arm)
        selected.append({"group_id": choice["group_id"], "source_seed": choice["source_seed"],
                         "leaf_snapshot_id": leaf, "baseline_value": choice["leaf_baseline32"],
                         "value": choice["q32"], "teacher_a": choice["teacher_a"],
                         "teacher_b": choice["teacher_b"], "selected_prefix": choice["prefix_key"],
                         "selected_length": choice["prefix_length"],
                         "oracle_prefix": max(candidates, key=lambda row: (row["q32"], row["prefix_key"]))["prefix_key"],
                         "oracle_length": max(candidates, key=lambda row: (row["q32"], row["prefix_key"]))["prefix_length"],
                         "oracle_q32": max(row["q32"] for row in candidates),
                         "selected_q32": choice["q32"]})
    baseline_rows = [{**row, "value": row["baseline_value"]} for row in selected]
    model_a = sibling_metrics(selected, "value", "teacher_a")
    model_b = sibling_metrics(selected, "value", "teacher_b")
    base_a = sibling_metrics(baseline_rows, "value", "teacher_a")
    base_b = sibling_metrics(baseline_rows, "value", "teacher_b")
    errors = [row["oracle_q32"] - row["selected_q32"] for row in selected]
    lengths = Counter(row["selected_length"] for row in selected)
    oracle_lengths = Counter(row["oracle_length"] for row in selected)
    first_agreement = sum(json.loads(row["selected_prefix"])[0] == json.loads(row["oracle_prefix"])[0]
                          for row in selected) / len(selected)
    return {"teacher_a": {"baseline": base_a, "model": model_a},
            "teacher_b": {"baseline": base_b, "model": model_b},
            "teacher_a_regret_reduction": (base_a["mean_teacher_regret"] - model_a["mean_teacher_regret"]) / base_a["mean_teacher_regret"],
            "teacher_b_regret_reduction": (base_b["mean_teacher_regret"] - model_b["mean_teacher_regret"]) / base_b["mean_teacher_regret"],
            "recovered_oracle_fraction": (base_a["mean_teacher_regret"] - model_a["mean_teacher_regret"]) / (base_a["mean_teacher_regret"] - oracle_q),
            "clustered_bootstrap": bootstrap(selected, "value"),
            "candidate_regret": {"mean": statistics.fmean(errors), "median": statistics.median(errors),
                                 "p90": np.percentile(errors, 90), "p95": np.percentile(errors, 95), "maximum": max(errors)},
            "selected_length_counts": dict(lengths), "oracle_length_counts": dict(oracle_lengths),
            "first_action_agreement": first_agreement, "prefix_length_agreement": sum(
                row["selected_length"] == row["oracle_length"] for row in selected) / len(selected),
            "selected_prefixes": selected, "group_diagnostics": group_diagnostics(selected),
            "leaves": len(selected),
            "represented_groups": len({row["group_id"] for row in selected}),
            "scorable_sibling_groups": model_a["groups"]}


def run(args: argparse.Namespace) -> int:
    args.output.mkdir(parents=True, exist_ok=False)
    rows, _, manifest, schema = load_inputs(args.raw_prefix, args.corpus, args.baseline, args.teachers, args.manifest)
    add_parent_q(rows)
    feature_path = args.output / "candidate-features.jsonl.gz"
    write_features(rows, feature_path, schema)
    folds = {str(source): source_fold(source) for source in sorted({row["source_seed"] for row in rows})}
    for row in rows:
        row["fold"] = folds[row["source_seed"]]
    predictions = {"RIDGE_PREFIX_V1": {}, "MLP_FLAT_V1": {}, "MLP_FACTORIZED_V1": {}}
    factorized_aux = {"q1_prediction": {}, "delta2_prediction": {}}
    arm_meta = {name: {"parameters": 0, "serialized_bytes": 0, "folds": []} for name in predictions}
    for fold in range(FOLD_COUNT):
        train = [row for row in rows if row["fold"] != fold]
        test = [row for row in rows if row["fold"] == fold]
        if not train or not test or ({row["source_seed"] for row in train} & {row["source_seed"] for row in test}):
            raise SystemExit("source-seed train/test overlap or empty cross-fit fold")
        ridge_pred, meta = fit_ridge(train, test)
        for row, value in zip(test, ridge_pred): predictions["RIDGE_PREFIX_V1"][id(row)] = float(value)
        arm_meta["RIDGE_PREFIX_V1"]["folds"].append({"fold": fold, **{k: v for k, v in meta.items() if k != "normalization"}})
        flat_pred, meta, _ = fit_flat(train, test, fold)
        for row, value in zip(test, flat_pred): predictions["MLP_FLAT_V1"][id(row)] = float(value)
        arm_meta["MLP_FLAT_V1"]["folds"].append({"fold": fold, **{k: v for k, v in meta.items() if k != "normalization"}})
        factor_pred, meta, _, aux = fit_factorized(train, test, fold)
        for row, value in zip(test, factor_pred): predictions["MLP_FACTORIZED_V1"][id(row)] = float(value)
        for row, value in zip(test, aux["q1_prediction"]): factorized_aux["q1_prediction"][id(row)] = float(value)
        for row, value in zip(test, aux["delta2_prediction"]): factorized_aux["delta2_prediction"][id(row)] = float(value)
        arm_meta["MLP_FACTORIZED_V1"]["folds"].append({"fold": fold, **{k: v for k, v in meta.items() if k not in ("q1_normalization", "action_normalization")}})
    if any(len(values) != len(rows) for values in predictions.values()):
        raise SystemExit("missing held-out prediction")
    for row in rows:
        for arm in predictions:
            row[f"predicted_{arm}"] = predictions[arm][id(row)]
    prediction_path = args.output / "crossfit-predictions.jsonl.gz"
    with gzip.open(prediction_path, "wt", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps({"group_id": row["group_id"], "source_seed": row["source_seed"],
                                     "leaf_snapshot_id": row["leaf_snapshot_id"], "prefix_key": row["prefix_key"],
                                     "prefix_length": row["prefix_length"], "fold": row["fold"],
                                     "q32": row["q32"], "centered_q": row["centered_q"],
                                     **{f"predicted_{arm}": row[f"predicted_{arm}"] for arm in predictions}},
                                    sort_keys=True, separators=(",", ":")) + "\n")
    oracle_rows = []
    by_leaf = defaultdict(list)
    for row in rows: by_leaf[row["leaf_snapshot_id"]].append(row)
    for leaf, candidates in by_leaf.items():
        oracle = max(candidates, key=lambda row: (row["q32"], row["prefix_key"]))
        oracle_rows.append({"group_id": oracle["group_id"], "source_seed": oracle["source_seed"],
                            "leaf_snapshot_id": leaf, "baseline_value": oracle["leaf_baseline32"],
                            "value": oracle["q32"], "teacher_a": oracle["teacher_a"], "teacher_b": oracle["teacher_b"]})
    baseline_rows = [{**row, "value": row["baseline_value"]} for row in oracle_rows]
    baseline_a = sibling_metrics(baseline_rows, "value", "teacher_a")["mean_teacher_regret"]
    oracle_a = sibling_metrics(oracle_rows, "value", "teacher_a")["mean_teacher_regret"]
    baseline_b = sibling_metrics(baseline_rows, "value", "teacher_b")["mean_teacher_regret"]
    oracle_b = sibling_metrics(oracle_rows, "value", "teacher_b")["mean_teacher_regret"]
    expected = json.loads(args.oracle_analysis.read_text())
    expected_m = expected["metrics"]["2"]
    full_q32_oracle_a = sibling_metrics(oracle_rows, "value", "teacher_a")["mean_teacher_regret"]
    full_q32_oracle_b = sibling_metrics(oracle_rows, "value", "teacher_b")["mean_teacher_regret"]
    frozen_baseline_a = expected_m["teacher_a"]["baseline"]["mean_teacher_regret"]
    frozen_oracle_a = expected_m["teacher_a"]["oracle"]["mean_teacher_regret"]
    frozen_baseline_b = expected_m["teacher_b"]["baseline"]["mean_teacher_regret"]
    frozen_oracle_b = expected_m["teacher_b"]["oracle"]["mean_teacher_regret"]
    for actual, frozen in ((baseline_a, frozen_baseline_a),
                           (baseline_b, frozen_baseline_b)):
        if not math.isclose(actual, frozen, rel_tol=0.0, abs_tol=1e-12):
            raise SystemExit(f"frozen baseline/oracle mismatch: {actual} != {frozen}")
    # The #256 oracle is the preregistered two-direction cross-fit oracle, not
    # the stronger full-information max-q32 diagnostic above.
    oracle_a, oracle_b = frozen_oracle_a, frozen_oracle_b
    reports = {}
    for arm in predictions:
        reports[arm] = fit_metrics(rows, arm, oracle_a, baseline_a)
        target = np.asarray([row["centered_q"] for row in rows])
        predicted = np.asarray([row[f"predicted_{arm}"] for row in rows])
        reports[arm]["direct_prediction"] = {
            "centered_mae": float(np.mean(np.abs(target - predicted))),
            "centered_rmse": float(np.sqrt(np.mean((target - predicted) ** 2))),
            "pearson": float(pearsonr(target, predicted).statistic),
            "spearman": float(spearmanr(target, predicted).statistic),
        }
        reports[arm]["parameters"] = arm_meta[arm]
        reports[arm]["cpu_scoring"] = timing_summary(arm_meta[arm])
        if arm == "MLP_FACTORIZED_V1":
            q1_errors = []
            delta_errors = []
            for row in rows:
                parent_target = row["q32"] if row["prefix_length"] == 1 else row["parent_q32"]
                q1_errors.append(factorized_aux["q1_prediction"][id(row)] - (parent_target - row["leaf_baseline32"]))
                if row["prefix_length"] == 2:
                    delta_errors.append(factorized_aux["delta2_prediction"][id(row)] -
                                        (row["centered_q"] - (parent_target - row["leaf_baseline32"])))
            reports[arm]["factorized_diagnostics"] = {
                "q1_mae": float(np.mean(np.abs(q1_errors))),
                "q1_rmse": float(np.sqrt(np.mean(np.square(q1_errors)))),
                "delta2_mae": float(np.mean(np.abs(delta_errors))),
                "delta2_rmse": float(np.sqrt(np.mean(np.square(delta_errors)))),
            }
        reports[arm]["gate"] = {"recovered_at_least_50_percent": reports[arm]["recovered_oracle_fraction"] >= 0.50,
                                 "clustered_p025_positive": reports[arm]["clustered_bootstrap"]["p025"] > 0,
                                 "teacher_b_not_below_negative_5_percent": reports[arm]["teacher_b_regret_reduction"] >= -0.05,
                                 "under_100k_parameters": max(x["parameters"] for x in arm_meta[arm]["folds"]) < 100000,
                                 "full_coverage": reports[arm]["leaves"] == 247}
    qualifying = [arm for arm, report in reports.items() if all(report["gate"].values())]
    partial = [arm for arm, report in reports.items() if report["recovered_oracle_fraction"] >= 0.25
               and report["clustered_bootstrap"]["p025"] > 0]
    if qualifying:
        classification = "LEARNED_PREFIX_SCORER_PROMISING"
        best = min(qualifying, key=lambda arm: (max(x["parameters"] for x in arm_meta[arm]["folds"]),
                                                -reports[arm]["recovered_oracle_fraction"],
                                                reports[arm]["candidate_regret"]["p95"]))
    elif partial:
        classification, best = "LEARNED_PREFIX_SCORER_PARTIAL", max(partial, key=lambda arm: reports[arm]["recovered_oracle_fraction"])
    else:
        classification, best = "LEARNED_PREFIX_SCORER_INSUFFICIENT", None
    analysis = {"schema": "silver_learned_prefix_scorer_analysis_v1", "classification": classification,
                "best_arm": best, "arms": reports, "cross_fitted_coverage": {"leaves": 247, "candidates": len(rows)},
                "fold_mapping": folds, "training": {"seed": TRAINING_SEED, "folds": FOLD_COUNT,
                "ridge_alpha": 10.0, "mlp_hidden": [32, 32], "shared_factorized_state_width": 32,
                "epochs": 80, "optimizer": "Adam(lr=1e-3)",
                "loss": "Huber", "teacher_fields_in_training": False},
                "frozen_reference": {"baseline_teacher_a_regret": baseline_a, "oracle_teacher_a_regret": oracle_a,
                "baseline_teacher_b_regret": baseline_b, "oracle_teacher_b_regret": oracle_b},
                "full_q32_oracle_diagnostic": {"teacher_a_regret": full_q32_oracle_a,
                "teacher_b_regret": full_q32_oracle_b},
                "inputs": {"raw_prefix_sha256": sha256(args.raw_prefix), "corpus_sha256": sha256(args.corpus),
                           "baseline_sha256": sha256(args.baseline), "teachers_sha256": sha256(args.teachers),
                           "manifest_sha256": sha256(args.manifest), "oracle_analysis_sha256": sha256(args.oracle_analysis)},
                "surface": {"length_counts": EXPECTED_LENGTH_COUNTS, "candidate_count": len(rows),
                            "parent_contract": "every length-2 prefix has its exact length-1 parent"},
                "decision_note": "Offline only; no gameplay, production Silver, MCTS, Teacher labels, or holdout used.",
                "recommended_next_step": "If promising, run a separate native causal variable-prefix integration experiment with real STOP/extend legality and runtime measurement."}
    analysis["artifacts"] = {
        "candidate_features_sha256": sha256(feature_path),
        "crossfit_predictions_sha256": sha256(prediction_path),
        "analysis_written_after_predictions": True,
    }
    (args.output / "analysis.json").write_text(json.dumps(analysis, indent=2, sort_keys=True) + "\n")
    table = "\n".join(
        f"| {arm} | {max(f['parameters'] for f in reports[arm]['parameters']['folds'])} | "
        f"{reports[arm]['teacher_a']['model']['mean_teacher_regret']:.5f} | "
        f"{reports[arm]['recovered_oracle_fraction']:.2%} | "
        f"{reports[arm]['teacher_b_regret_reduction']:.2%} | "
        f"{reports[arm]['clustered_bootstrap']['p025']:.5f} |"
        for arm in reports)
    readme = args.output / "README.md"
    readme.write_text("# Silver learned prefix scorer\n\n"
                     "Offline, source-seed-cross-fitted value prediction from the frozen PR #256 length<=2 CARD/END_TURN surface. "
                     "This packet is diagnostic only: it changes no production Silver path, MCTS, gameplay seed, or holdout.\n\n"
                     f"Classification: **{classification}**\n\n"
                     f"Coverage: {len(by_leaf)}/247 leaves, {len(rows)} candidates; lengths 1={EXPECTED_LENGTH_COUNTS[1]}, 2={EXPECTED_LENGTH_COUNTS[2]}.\n\n"
                     "| arm | params | Teacher-A regret | oracle recovered | Teacher-B reduction | CI p025 |\n"
                     "|---|---:|---:|---:|---:|---:|\n" + table + "\n\n"
                     "Models, fold assignments, hashes, metrics, and fail-closed reference checks are in `analysis.json`; held-out rows are in `crossfit-predictions.jsonl.gz`.\n\n"
                     "Knowledge impact: benchmarked learned-scorer result only; no stable implementation or production-behavior change.\n")
    print(json.dumps({"classification": classification, "best_arm": best,
                      "arms": {arm: {"recovered": reports[arm]["recovered_oracle_fraction"],
                                    "teacher_a_regret": reports[arm]["teacher_a"]["model"]["mean_teacher_regret"],
                                    "teacher_b_reduction": reports[arm]["teacher_b_regret_reduction"]}
                               for arm in reports}}, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-prefix", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--teachers", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--oracle-analysis", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
