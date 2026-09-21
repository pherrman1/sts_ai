"""Whitelisted public-wire projection for a variable-candidate Silver prior.

No labels, provenance, arbitrary UIDs, or random-stream state enter this module's
output. Unknown piles are multisets stored in canonical *feature* order.
"""
from __future__ import annotations

import hashlib
import json

SCHEMA = "silver_prior_observation_v1"
VOCAB_SCHEMA = "silver_prior_cards_v1"


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def vocabulary(census):
    entries = census["domains"]["cards"]["entries"]
    retained = [e for e in entries if e["classification"] != "PROVABLY_UNREACHABLE"]
    body = {"schema": VOCAB_SCHEMA, "absent": None, "padding": None,
            "entries": [{"canonical_id": e["id"], "compact_id": i,
                         "name": e["enumName"], "classification": e["classification"]}
                        for i, e in enumerate(retained)],
            "canonical_to_compact": {str(e["id"]): i for i, e in enumerate(retained)},
            "compact_to_canonical": [e["id"] for e in retained],
            "excluded": [e["id"] for e in entries
                         if e["classification"] == "PROVABLY_UNREACHABLE"],
            "census_cards_sha256": digest(census["domains"]["cards"])}
    return {**body, "sha256": digest(body)}


def validate_vocabulary(vocab):
    require(vocab["schema"] == VOCAB_SCHEMA, "vocabulary schema")
    require(vocab["sha256"] == digest({k: v for k, v in vocab.items() if k != "sha256"}),
            "vocabulary hash")
    require(vocab["absent"] is None and vocab["padding"] is None, "absence semantics")
    for i, e in enumerate(vocab["entries"]):
        require(e["compact_id"] == i and vocab["compact_to_canonical"][i] == e["canonical_id"]
                and vocab["canonical_to_compact"][str(e["canonical_id"])] == i
                and e["canonical_id"] not in vocab["excluded"]
                and e["classification"] in ("REACHABLE", "UNKNOWN"), "vocabulary inverse")
    require(len(vocab["entries"]) == len(vocab["canonical_to_compact"])
            == len(vocab["compact_to_canonical"]), "vocabulary cardinality")


# Explicit field map. Numeric enum IDs in these records are categorical.
GLOBAL = "floorNum encounter energyWasted cardsDrawn act omamoriOwned omamoriValue ascension outcome inputState monsterTurnIdx endTurnQueued turnHasEnded skipMonsterTurn potionCount potionCapacity turn monsterCount monstersAlive handNormalityCount handPainCount strikeCount handBloodCardCount drawPileBloodCardCount discardPileBloodCardCount fullDrawOrderObserved intentsHidden".split()
PLAYER = "characterClass gold curHp maxHp energy energyPerTurn cardDrawPerTurn stance orbSlots block artifact dexterity focus strength haveUsedNecronomiconThisTurn combustHpLoss devaFormEnergyPerTurn echoFormCardsDoubled panacheCounter cardsPlayedThisTurn attacksPlayedThisTurn skillsPlayedThisTurn cardsDiscardedThisTurn lastAttackUnblockedDamage timesDamagedThisCombat".split()
MONSTER = "id curHp maxHp block isEscapingB halfDead escapeNext strength vulnerable weak uniquePower0 uniquePower1 miscInfo".split()
CARD = "specialData cost costForTurn upgraded freeToPlayOnce retain".split()
SMALL_POWERS = "artifact blockReturn choked corpseExplosion lockOn mark metallicize platedArmor poison regen shackled".split()


def fields(obj, names):
    return {name: obj[name] for name in names}


def bits(value, width):
    require(type(value) is int and 0 <= value < (1 << width), "invalid bitfield")
    return [i for i in range(width) if value & (1 << i)]


def project(root, vocab, reference):
    validate_vocabulary(vocab)
    envelope = root["state"]
    require(envelope["corpus_schema"] == "silver_leaf_wire_v1"
            and envelope["wire_version"] == 2, "wire envelope schema")
    w = envelope["state"]
    require(w["valid"] and w["version"] == 2 and w["inputState"] == 1
            and w["outcome"] == 0 and len(root["actions"]) >= 2, "ineligible root")
    require(set(reference) == {"effectiveGold", "maxHp"}
            and reference["maxHp"] == w["player"]["maxHp"], "root reference scalars")
    cards, locations = [], {}

    def card_features(card):
        cid = str(card["id"])
        require(cid in vocab["canonical_to_compact"], f"excluded/unmapped card {cid}")
        return {"card_id": vocab["canonical_to_compact"][cid], **fields(card, CARD)}

    def add_zone(zone, segment, source, ordered=True, allow_absent=False):
        pairs = [(card, None if card["id"] == 0 and allow_absent else card_features(card))
                 for card in source]
        if not ordered:
            pairs.sort(key=lambda pair: canonical(pair[1]))
        refs = []
        for position, (card, feature) in enumerate(pairs):
            if feature is None:
                refs.append(None)
                continue
            ref = len(cards)
            record = {**feature, "ref": ref, "zone": zone, "segment": segment,
                      "position": position if ordered else None}
            cards.append(record)
            locations.setdefault((zone, card["uniqueId"]), []).append((card, ref))
            refs.append(ref)
        return refs

    zones = {zone: add_zone(zone, "observed", w[zone], allow_absent=zone in ("limbo", "stasisCards"))
             for zone in ("hand", "limbo", "stasisCards")}
    piles = {}
    for zone in ("drawPile", "discardPile", "exhaustPile"):
        pile = w[zone]
        require(pile["valid"], "invalid public pile")
        require(not pile["fullOrderObserved"] or not pile["unknown"], "observed/unknown contradiction")
        piles[zone] = {segment: add_zone(zone, segment, pile[segment], segment != "unknown")
                       for segment in ("knownBottom", "unknown", "knownTop")}
        piles[zone]["fullOrderObserved"] = pile["fullOrderObserved"]
    monsters = []
    for slot, m in enumerate(w["monsters"]):
        present = slot < w["monsterCount"] and m["idx"] >= 0
        record = {"ref": slot, "present": present}
        if present:
            require(m["idx"] == slot, "monster slot mismatch")
            record.update(fields(m, MONSTER))
            record.update(alive=m["curHp"] > 0 and not m["isEscapingB"],
                          moveHistory=None if w["intentsHidden"] else m["moveHistory"],
                          powers=bits(m["statusBits"], 64),
                          smallPowers=[{"kind": name, "amount": value}
                                       for name, value in zip(SMALL_POWERS, m["smallPowers"], strict=True)])
        monsters.append(record)
    p = w["player"]
    player = fields(p, PLAYER)
    player.update(statusPresence=bits(p["statusBits0"], 64)
                  + [64 + i for i in bits(p["statusBits1"], 32)],
                  justApplied=bits(p["justAppliedBits"], 32),
                  statusAmounts=[{"kind": k, "amount": v} for k, v in p["statusMap"]],
                  relicPresence=bits(p["relicBits0"], 64)
                  + [64 + i for i in bits(p["relicBits1"], 64)],
                  relicCounters=[{"counter_kind": i, "amount": v}
                                 for i, v in enumerate(p["relicCounters"])],
                  bombs=[{"timing": i, "amount": v} for i, v in enumerate(p["bombs"])],
                  orangePelletsCardTypesPlayed=bits(p["orangePelletsCardTypesPlayed"], 8),
                  lastTargetedMonster=p["lastTargetedMonster"]
                  if 0 <= p["lastTargetedMonster"] < w["monsterCount"] else None)
    require(0 <= w["potionCapacity"] <= len(w["potions"]), "potion capacity")
    potions = [{"slot": i, "available": i < w["potionCapacity"],
                "potion_id": pid, "empty": pid == 1} for i, pid in enumerate(w["potions"])]
    candidates = []
    for a in root["actions"]:
        require(a["type"] in (1, 2, 5) and not a["selectedCards"]
                and a["optionCardId"] == 0 and not a["skipCardSelect"], "unsupported action surface")
        target = a["target"]
        require(target == -1 or (0 <= target < len(monsters) and monsters[target]["present"]),
                "target reference")
        candidate = {"type": a["type"], "source_zone": a["source"], "card_ref": None,
                     "target_ref": None if target == -1 else target,
                     "potion_id": None, "potion_slot": None,
                     "discardPotion": a["discardPotion"], "skipCardSelect": a["skipCardSelect"],
                     "cardSelectTask": a["cardSelectTask"]}
        if a["type"] == 1:
            require(a["source"] == 1, "normal card source must be hand")
            matches = [ref for card, ref in locations.get(("hand", a["card"]["uniqueId"]), [])
                       if card == a["card"]]
            require(len(matches) == 1, "ambiguous/missing card instance")
            candidate["card_ref"] = matches[0]
        elif a["type"] == 2:
            slot = a["potionSlot"]
            require(0 <= slot < w["potionCapacity"] and a["potionId"] not in (0, 1)
                    and w["potions"][slot] == a["potionId"], "potion reference")
            candidate.update(potion_id=a["potionId"], potion_slot=slot)
        candidates.append(candidate)
    return {"schema": SCHEMA, "global": fields(w, GLOBAL), "player": player,
            "cards": cards, "zones": zones, "piles": piles, "monsters": monsters,
            "potions": potions, "evaluation_context": reference, "candidates": candidates,
            "miscFlags": bits(w["miscBits"], 32),
            "extraRollMoveSlots": bits(w["extraRollMoveOnTurn"], 8),
            "skipMonsterTurnSlots": bits(w["skipMonsterTurnBits"], 8)}


def permute_candidates(observation, values, permutation):
    require(sorted(permutation) == list(range(len(observation["candidates"])))
            and len(values) == len(permutation), "candidate/label permutation")
    return ({**observation, "candidates": [observation["candidates"][i] for i in permutation]},
            [values[i] for i in permutation])
