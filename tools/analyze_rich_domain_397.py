#!/usr/bin/env python3
"""#397 Stage 1b: reachable Ironclad deck-card domain of the rich `v_win` state.

The rich state allocates `d0..d371` (owned count) and `u0..u371` (upgraded
count) by `(int)CardId`, and those count only the master deck
(`apps/one_combat/run_features.cpp::richFeatureVec`). This tool derives the
set of card IDs an Ironclad run can put in the master deck from the
simulator's own tables and obtain sites, not from a hand-written color list:

- Ironclad class pools: `TransformCardPool`, `TrulyRandomCardPool` and the
  Ironclad slice of `RarityCardPool` (card rewards, shops, Neow, transforms,
  Library/Match and Keep). `AnyColorTypeCardPool` is reached only through
  Prismatic Shard, which `GameContext::disablePrismaticShard` disables at
  compile time.
- Colorless pools: `baseColorlessPool`, `srcColorlessCardPool`,
  `ColorlessRarityCardPool` (shops, Neow, events, colorless transforms).
- `curseCardPool` (events, curse transforms, Writhing Mass Parasite).
- Every literal `deck.obtain(..., CardId::X` / `obtainCard(CardId::X` in
  `src/` (event cards such as Bite, J.A.X., Apparition, Ritual Dagger;
  starter cards; Ascender's Bane; Curse of the Bell), excluding other
  classes' starter literals from `GameContext::initFromSeed`'s class switch.
- `noteForYourselfCard`'s default from `GameContext.h`.
- Live-game-only additions (`LIVE_ONLY`): cards the real game can put in the
  deck through a path the simulator omits. The live importer accepts them, so
  they stay in the allowlist even though no simulated run produces them.

In-combat generated cards never enter the master deck and are out of scope.
The `--preflight` comparison against an A3 TRAIN variance mask reads only the
mask JSON (no corpus rows). Other-class relic/potion columns are reported for
the same comparison.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CARDS = ROOT / "include/constants/Cards.h"
POOLS = ROOT / "include/constants/CardPools.h"
GC_HEADER = ROOT / "include/game/GameContext.h"
N_CARD_COLUMNS = 372  # one_combat::kNumCardIds
OTHER_CLASS = {"GREEN", "BLUE", "PURPLE"}
# STS1 adds Necronomicurse when Necronomicon is obtained (Cursed Tome); the
# simulator grants the relic (GameContext.cpp Cursed Tome) but never the curse.
LIVE_ONLY = {"NECRONOMICURSE": "Necronomicon pickup in the real game; missing simulator obtain"}


class DomainError(ValueError):
    pass


def _ids(text):
    return re.findall(r"CardId::\s*(\w+)", text)


def _block(text, pattern):
    m = re.search(pattern, text, re.S)
    if not m:
        raise DomainError(f"pattern not found: {pattern}")
    return m.group(1)


def card_tables():
    text = CARDS.read_text()
    enum = _block(text, r"enum class CardId[^{]*\{(.*?)\};")
    names = [x.split("=")[0].strip() for x in re.sub(r"//[^\n]*", "", enum).split(",") if x.strip()]
    def arr(name):
        return [x.strip().split("::")[-1] for x in _block(text, rf"{name}\[\]\s*=\s*\{{(.*?)\}};").split(",") if x.strip()]
    colors, rarities = arr("cardColors"), arr("cardRarities")
    if not (len(names) == len(colors) == len(rarities)):
        raise DomainError("card table length mismatch")
    return names, dict(zip(names, colors)), dict(zip(names, rarities))


def pool_sources():
    text = POOLS.read_text()
    first_row = lambda ns: _ids(_block(text, rf"namespace {ns}\s*\{{.*?\{{\s*\{{(.*?)\}}"))
    rarity_blob = _ids(_block(text, r"namespace RarityCardPool.*?cardBlob\[\]\s*\{(.*?)\};"))
    offsets = _block(text, r"namespace RarityCardPool.*?groupOffset\[4\]\[3\]\s*\{\{(.*?)\}")
    sizes = _block(text, r"namespace RarityCardPool.*?groupSize\[4\]\[3\]\s*\{\{(.*?)\}")
    o, s = [int(x) for x in offsets.split(",") if x.strip()], [int(x) for x in sizes.split(",") if x.strip()]
    ironclad_rarity = rarity_blob[o[0]:o[-1] + s[-1]]
    return {
        "ironclad_transform": first_row("TransformCardPool"),
        "ironclad_truly_random": first_row("TrulyRandomCardPool"),
        "ironclad_rarity": ironclad_rarity,
        "colorless_base": _ids(_block(text, r"baseColorlessPool\s*=\s*\{(.*?)\};")),
        "colorless_src": _ids(_block(text, r"srcColorlessCardPool\[\]\s*=\s*\{(.*?)\};")),
        "colorless_rarity": _ids(_block(text, r"colorlessCardBlob\[\]\s*\{(.*?)\};")),
        "curse_pool": _ids(_block(text, r"curseCardPool\[\]\s*=\s*\{(.*?)\};")),
    }


OBTAIN = re.compile(r"(?:deck\.obtain\(\s*\*?\w+\s*,\s*|obtainCard\(\s*)(?:Card\(\s*)?CardId::(\w+)")


def literal_obtains():
    found = {}
    for path in sorted((ROOT / "src").rglob("*.cpp")):
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            for name in OBTAIN.findall(line):
                found.setdefault(name, []).append(f"{path.relative_to(ROOT)}:{lineno}")
    note = re.search(r"noteForYourselfCard\s*=\s*Card\(CardId::(\w+)\)", GC_HEADER.read_text())
    if not note:
        raise DomainError("noteForYourselfCard default not found")
    found.setdefault(note.group(1), []).append("include/game/GameContext.h noteForYourselfCard")
    return found


def reachable_cards():
    names, colors, rarities = card_tables()
    sources = pool_sources()
    literals = literal_obtains()
    excluded = sorted(n for n in literals if colors.get(n) in OTHER_CLASS)
    for name in excluded:
        if rarities[name] != "BASIC":
            raise DomainError(f"non-starter other-class literal obtain: {name}")
    reach = {}
    for source, ids in sources.items():
        for name in ids:
            reach.setdefault(name, set()).add(source)
    for name in literals:
        if name not in excluded:
            reach.setdefault(name, set()).add("literal_obtain")
    for name in LIVE_ONLY:
        reach.setdefault(name, set()).add("live_game_only")
    unknown = sorted(set(reach) - set(names))
    if unknown:
        raise DomainError(f"unknown card ids: {unknown}")
    for name in sources["ironclad_transform"] + sources["ironclad_rarity"]:
        if colors[name] != "RED":
            raise DomainError(f"non-red card in Ironclad pool: {name}")
    return names, colors, rarities, reach, literals, excluded


def domain_report(selected=None):
    names, colors, rarities, reach, literals, excluded = reachable_cards()
    index = {n: i for i, n in enumerate(names)}
    reachable_idx = sorted(index[n] for n in reach)
    by_color = {}
    for n in reach:
        by_color[colors[n]] = by_color.get(colors[n], 0) + 1
    report = {
        "card_columns_per_block": N_CARD_COLUMNS, "card_enum_size": len(names),
        "reachable_count": len(reachable_idx), "reachable_by_color": dict(sorted(by_color.items())),
        "reachable": [dict(id=index[n], name=n, color=colors[n], rarity=rarities[n],
                           sources=sorted(reach[n])) for n in sorted(reach, key=index.get)],
        "excluded_other_class_starter_literals": excluded,
        "literal_obtain_sites": {n: literals[n] for n in sorted(literals)},
    }
    if selected is not None:
        reach_set = set(reachable_idx)
        for block in ("d", "u"):
            variable = sorted(int(n[1:]) for n in selected if re.fullmatch(rf"{block}\d+", n))
            report[f"{block}_variable"] = len(variable)
            report[f"{block}_variable_unreachable"] = [
                dict(id=i, name=names[i] if i < len(names) else None) for i in variable if i not in reach_set]
            report[f"{block}_reachable_constant"] = [
                names[i] for i in reachable_idx if i not in set(variable)]
    return report


def _self_test():
    names, colors, rarities, reach, literals, excluded = reachable_cards()
    assert names[0] == "INVALID" and len(names) <= N_CARD_COLUMNS
    for n in ("STRIKE_RED", "DEFEND_RED", "BASH", "DEMON_FORM", "BITE", "JAX", "APPARITION",
              "RITUAL_DAGGER", "ASCENDERS_BANE", "CURSE_OF_THE_BELL", "PARASITE", "HAND_OF_GREED",
              "NECRONOMICURSE"):
        assert n in reach, n
    for n in ("STRIKE_GREEN", "NEUTRALIZE", "ZAP", "ERUPTION", "WOUND", "DAZED", "BURN", "SLIMED",
              "SHIV", "INVALID"):
        assert n not in reach, n
    assert set(excluded) >= {"STRIKE_GREEN", "ZAP", "ERUPTION"}
    assert all(colors[n] in ("RED", "COLORLESS", "CURSE") for n in reach), "off-domain color"
    print("rich domain #397 self-test: PASS")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--preflight", help="A3 preflight JSON with selected_feature_names")
    parser.add_argument("--output", help="new JSON report path (refuses overwrite)")
    args = parser.parse_args(argv)
    if args.self_test:
        return _self_test()
    selected = json.loads(Path(args.preflight).read_text())["selected_feature_names"] if args.preflight else None
    report = domain_report(selected)
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        with Path(args.output).open("x") as f:
            f.write(text)
    summary = {k: v for k, v in report.items() if k not in ("reachable", "literal_obtain_sites")}
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
