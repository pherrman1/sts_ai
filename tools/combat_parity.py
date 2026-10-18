#!/usr/bin/env python3
"""Exact one-step combat parity between the real game and the native engine.

Input is a live driver trace recorded with ``--parity-trace`` while the game
runs with ``STS_DIFFERENTIAL_DEBUG_RNG=1``. Each recorded Silver combat
decision becomes one step: the game's raw observation, its hidden RNG and
true draw order, the selected action, and the next recorded observation.
``combat_parity_probe`` replays each step natively from the game's own state;
this tool diffs the two successors and writes a coverage report.

    python3 tools/combat_parity.py run TRACE.jsonl --probe build/.../combat_parity_probe \\
        --out-dir OUT

Steps that cannot be compared are counted by reason, never dropped.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping

# Observer bookkeeping that differs by construction between a native
# successor and a fresh import; never simulator semantics.
IGNORED_KEYS = frozenset({"isolatedSearchSeed", "observedGeneration", "nextUniqueCardId", "uniqueId"})
# Ordered card collections: a difference that is only order is reported
# under its own label, because order can matter (draws, shuffles).
ORDERED_PILES = ("hand",)
OUTCOME_NAMES = {0: "UNDECIDED", 1: "PLAYER_VICTORY", 2: "PLAYER_LOSS"}


def read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def _boundary(row: Mapping[str, Any]) -> str:
    return str(row.get("inspector_boundary") or "")


def _is_pass_through(row: Mapping[str, Any]) -> bool:
    evaluator = row.get("silver_evaluator")
    return isinstance(evaluator, Mapping) and evaluator.get("mode") == "native_pass_through"


def _post_in_combat(row: Mapping[str, Any]) -> bool:
    kind = row.get("post_screen_kind")
    return isinstance(kind, Mapping) and kind.get("combat") is True


def _post_death(row: Mapping[str, Any]) -> bool:
    kind = row.get("post_screen_kind")
    return isinstance(kind, Mapping) and kind.get("terminal") is True and kind.get("outcome") == "death"


def _skippable(row: Mapping[str, Any]) -> bool:
    # Neither changes the simulated state: a UI confirmation the native
    # selection already includes, or a re-read of an unchanged screen.
    return _is_pass_through(row) or row.get("decision_source") == "combat_display_refresh"


def extract_steps(rows: Iterable[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], Counter[str]]:
    """Pair each Silver combat decision with the next recorded observation."""
    rows = [row for row in rows if row.get("record_type") is None]
    steps: list[dict[str, Any]] = []
    skipped: Counter[str] = Counter()
    for index, row in enumerate(rows):
        if _boundary(row) != "combat" or _skippable(row) or not isinstance(row.get("live_observation"), Mapping):
            continue
        evaluator = row.get("silver_evaluator")
        action = evaluator.get("selectedAction") if isinstance(evaluator, Mapping) else None
        if row.get("decision_source") != "silver" or not isinstance(action, str):
            skipped["NO_SEMANTIC_ACTION"] += 1
            continue
        step = {"step": row.get("step"), "session": row.get("inspector_session") or "parity",
                "pre": row["live_observation"], "preRng": row.get("preRng"), "action": action,
                "actionLabel": evaluator.get("selectedLabel")}
        nxt = None
        for later in rows[index + 1:]:
            if _skippable(later):
                continue
            nxt = later
            break
        in_combat = _post_in_combat(row)
        if not in_combat:
            step["postBoundary"] = "death" if _post_death(row) else "ooc"
            if nxt is not None and isinstance(nxt.get("live_observation"), Mapping):
                step["post"] = nxt["live_observation"]
        elif nxt is None:
            skipped["TRACE_ENDED"] += 1
            continue
        elif _boundary(nxt) != "combat" or not isinstance(nxt.get("live_observation"), Mapping):
            # Another click happened before the next recorded combat state.
            skipped["GAP_IN_TRACE"] += 1
            continue
        else:
            step["postBoundary"] = "combat"
            step["post"] = nxt["live_observation"]
            step["postRng"] = nxt.get("preRng")
        steps.append(step)
    return steps, skipped


def run_probe(probe: Path, steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    payload = "".join(json.dumps(step, sort_keys=True) + "\n" for step in steps)
    result = subprocess.run([str(probe)], input=payload, text=True, capture_output=True, check=True)
    return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]


def normalize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: normalize(v) for k, v in value.items() if k not in IGNORED_KEYS}
    if isinstance(value, list):
        return [normalize(v) for v in value]
    return value


def diff(game: Any, native: Any, path: str = "", out: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    out = [] if out is None else out
    if isinstance(game, Mapping) and isinstance(native, Mapping):
        for key in sorted(set(game) | set(native)):
            diff(game.get(key), native.get(key), f"{path}.{key}" if path else key, out)
        return out
    if isinstance(game, list) and isinstance(native, list):
        if path in ORDERED_PILES and game != native and sorted(map(json.dumps, game)) == sorted(map(json.dumps, native)):
            out.append({"path": path + "(order)", "game": game, "native": native})
            return out
        if len(game) != len(native):
            out.append({"path": path + "(length)", "game": game, "native": native})
            return out
        for i, (g, n) in enumerate(zip(game, native)):
            diff(g, n, f"{path}[{i}]", out)
        return out
    if game != native:
        out.append({"path": path, "game": game, "native": native})
    return out


def field_group(path: str) -> str:
    """Collapse indices so mismatches aggregate by field."""
    import re
    return re.sub(r"\[\d+\]", "[]", path)


def compare(step: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    status = result.get("status")
    out: dict[str, Any] = {"step": step.get("step"), "action": result.get("actionLabel") or step.get("actionLabel"),
                           "encounter": result.get("encounter"), "turn": result.get("turn")}
    if status == "SKIPPED":
        out.update(verdict="SKIPPED", category=result.get("category"), reason=result.get("reason"))
        return out
    if status == "COMBAT_END":
        expected = 2 if step.get("postBoundary") == "death" else 1
        native = result.get("nativeOutcome")
        out["verdict"] = "MATCH" if native == expected else "MISMATCH"
        if native != expected:
            out["diffs"] = [{"path": "outcome", "game": OUTCOME_NAMES[expected], "native": OUTCOME_NAMES.get(native)}]
        post = step.get("post")
        if isinstance(post, Mapping) and isinstance(result.get("native"), Mapping):
            # Informational: post-combat heals (Burning Blood ...) apply in Java first.
            out["endHpGameMinusNative"] = (post.get("hp", 0) or 0) - result["native"]["player"]["curHp"]
        return out
    if result.get("mismatch"):
        out.update(verdict="MISMATCH", diffs=[{"path": "outcome", "game": "UNDECIDED",
                                               "native": OUTCOME_NAMES.get(result.get("nativeOutcome"))}])
        return out
    diffs = diff(normalize(result.get("game")), normalize(result.get("native")))
    rng = diff(result.get("gameRng"), result.get("nativeRng"), "rng")
    out["verdict"] = "MATCH" if not diffs and not rng else "MISMATCH"
    if diffs or rng:
        out["diffs"] = diffs + rng
    return out


def _cards_in(observation: Mapping[str, Any]) -> set[str]:
    combat = observation.get("silverRoot", {}).get("combat", {})
    names: set[str] = set()
    for pile in ("hand", "draw", "discard", "exhaust"):
        value = combat.get(pile, [])
        cards = value if isinstance(value, list) else [c for part in ("knownBottom", "unknown", "knownTop")
                                                        for c in value.get(part, [])]
        names.update(f"{c.get('id')}{'+' if c.get('upgraded') else ''}" for c in cards if isinstance(c, Mapping))
    return names


def coverage(steps: list[Mapping[str, Any]], verdicts: list[Mapping[str, Any]]) -> dict[str, dict[str, list[int]]]:
    """Per item: [steps compared, mismatches]."""
    table: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for step, verdict in zip(steps, verdicts):
        if verdict["verdict"] == "SKIPPED":
            continue
        bad = int(verdict["verdict"] == "MISMATCH")
        combat = step["pre"].get("silverRoot", {}).get("combat", {})
        items = {
            "action": [str(verdict.get("action"))],
            "encounter": [str(step["pre"].get("silverRoot", {}).get("encounter"))],
            "relic": [r.get("id") for r in combat.get("relics", []) if isinstance(r, Mapping)],
            "potion": [p.get("id") for p in combat.get("potions", []) if isinstance(p, Mapping)
                       and p.get("id") != "Potion Slot"],
            "playerPower": [p.get("id") for p in combat.get("playerPowers", []) if isinstance(p, Mapping)],
            "monsterPower": [p.get("id") for m in combat.get("monsters", []) if isinstance(m, Mapping)
                             for p in m.get("powers", []) if isinstance(p, Mapping)],
            "card": sorted(_cards_in(step["pre"])),
        }
        for kind, names in items.items():
            for name in set(names):
                cell = table[kind][str(name)]
                cell[0] += 1
                cell[1] += bad
    return {k: dict(v) for k, v in table.items()}


def summarize(verdicts: list[Mapping[str, Any]], extract_skips: Mapping[str, int]) -> dict[str, Any]:
    verdict_counts = Counter(v["verdict"] for v in verdicts)
    skip_counts = Counter(v.get("category") for v in verdicts if v["verdict"] == "SKIPPED")
    skip_counts.update(extract_skips)
    fields: Counter[str] = Counter()
    first: dict[str, Any] = {}
    for v in verdicts:
        for d in v.get("diffs", []):
            key = field_group(d["path"])
            fields[key] += 1
            first.setdefault(key, {"step": v["step"], "action": v["action"], "encounter": v["encounter"], **d})
    return {"schema": "combat_parity_summary_v1", "verdicts": dict(verdict_counts),
            "skipped": dict(skip_counts), "mismatchedFields": dict(fields.most_common()),
            "firstExample": first}


def write_report(out_dir: Path, summary: Mapping[str, Any], cover: Mapping[str, Any]) -> None:
    lines = ["# Combat parity report", "",
             "Verdicts: " + ", ".join(f"{k} {v}" for k, v in sorted(summary["verdicts"].items())), "",
             "## Skipped steps by reason", ""]
    lines += [f"- {k}: {v}" for k, v in sorted(summary["skipped"].items(), key=lambda kv: -kv[1])] or ["- none"]
    lines += ["", "## Mismatched fields", "", "| Field | Steps | First example (step, action) |", "|---|---|---|"]
    for key, count in summary["mismatchedFields"].items():
        ex = summary["firstExample"][key]
        lines.append(f"| `{key}` | {count} | {ex['step']}, {ex['action']} |")
    lines += ["", "## Coverage (steps compared / mismatched)", ""]
    for kind, items in sorted(cover.items()):
        lines += [f"### {kind}", ""]
        lines += [f"- {name}: {n} / {bad}" for name, (n, bad) in sorted(items.items(), key=lambda kv: -kv[1][0])]
        lines.append("")
    (out_dir / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="extract, probe, diff and report")
    run.add_argument("traces", nargs="+", type=Path, help="live driver traces recorded with --parity-trace")
    run.add_argument("--probe", type=Path, required=True, help="combat_parity_probe executable")
    run.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args(argv)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    steps: list[dict[str, Any]] = []
    skips: Counter[str] = Counter()
    for trace in args.traces:
        found, skipped = extract_steps(read_jsonl(trace))
        steps += found
        skips.update(skipped)
    results = run_probe(args.probe, steps)
    if len(results) != len(steps):
        print(f"probe returned {len(results)} rows for {len(steps)} steps", file=sys.stderr)
        return 2
    verdicts = [compare(step, result) for step, result in zip(steps, results)]
    with (args.out_dir / "verdicts.jsonl").open("w", encoding="utf-8") as handle:
        for verdict in verdicts:
            handle.write(json.dumps(verdict, sort_keys=True) + "\n")
    summary = summarize(verdicts, skips)
    cover = coverage(steps, verdicts)
    (args.out_dir / "summary.json").write_text(json.dumps({**summary, "coverage": cover}, indent=1, sort_keys=True) + "\n",
                                               encoding="utf-8")
    write_report(args.out_dir, summary, cover)
    print(json.dumps(summary["verdicts"]), json.dumps(summary["skipped"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
