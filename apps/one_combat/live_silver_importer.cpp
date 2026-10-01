#include "live_silver_importer.h"

#include <algorithm>
#include <cstdint>
#include <map>
#include <set>
#include <sstream>
#include <unordered_map>
#include <limits>
#include <iterator>
#include <optional>

#include "constants/CharacterClasses.h"
#include "constants/Relics.h"
#include "constants/MonsterIds.h"
#include "constants/MonsterMoves.h"
#include "constants/SaveFileMappings.h"
#include "constants/Potions.h"
#include "constants/PlayerStatusEffects.h"
#include "combat/CardSelectInfo.h"
#include "combat/InputState.h"
#include "combat/CardInstance.h"
#include "combat/CardQueue.h"
#include "live_silver_mapping.h"

namespace one_combat::advisor {
namespace {

using json = nlohmann::json;

struct CardRecord {
    std::string uuid;
    silver_bridge::CardWire wire;
};

std::optional<silver_bridge::CardSource> liveSingleSelectionSource(sts::CardSelectTask task,
                                                                  const std::string &origin) {
    if (origin == "HAND_SELECT" && (task == sts::CardSelectTask::WARCRY || task == sts::CardSelectTask::FORETHOUGHT))
        return silver_bridge::CardSource::HAND;
    if (origin == "GRID" && (task == sts::CardSelectTask::SECRET_TECHNIQUE || task == sts::CardSelectTask::SECRET_WEAPON))
        return silver_bridge::CardSource::DRAW;
    return std::nullopt;
}

bool liveSingleChoices(const json &selection, std::map<std::string, int> &choices, bool multiForethought = false) {
    if (selection.value("selectedBits", -1) != 0) return false;
    if (multiForethought) {
        if (selection.value("pickCount", 0) != 99 || !selection.value("canPickZero", false)
            || !selection.value("canPickAnyNumber", false) || selection.value("selectedCount", -1) != 0
            || selection.value("actionClass", std::string()) != "com.megacrit.cardcrawl.actions.unique.ForethoughtAction") return false;
    } else if (selection.value("pickCount", 0) != 1 || selection.value("canPickZero", true)
        || selection.value("canPickAnyNumber", true)) return false;
    const auto list = selection.value("liveChoices", json::array());
    if (!list.is_array() || list.empty()) return false;
    for (std::size_t i = 0; i < list.size(); ++i) {
        const auto &entry = list[i];
        if (!entry.is_object() || !entry.contains("uuid") || !entry["uuid"].is_string()
            || !entry.contains("choiceIndex") || !entry["choiceIndex"].is_number_integer()) return false;
        const auto uuid = entry["uuid"].get<std::string>();
        const int index = entry["choiceIndex"].get<int>();
        if (uuid.empty() || index != static_cast<int>(i) + 1 || !choices.emplace(uuid, index).second) return false;
    }
    return true;
}

std::string fail(const char *reason) { return reason; }

std::uint64_t fnv1a(const std::string &value, std::uint64_t hash = 1469598103934665603ULL) {
    for (unsigned char c : value) { hash ^= c; hash *= 1099511628211ULL; }
    return hash;
}

bool requiredInt(const json &object, const char *name, int &out) {
    if (!object.contains(name) || !object.at(name).is_number_integer()) return false;
    out = object.at(name).get<int>();
    return true;
}

bool requiredBool(const json &object, const char *name, bool &out) {
    if (!object.contains(name) || !object.at(name).is_boolean()) return false;
    out = object.at(name).get<bool>();
    return true;
}

bool hasForbiddenRngField(const json &object) {
    for (const char *name : {"rng", "aiRng", "cardRandomRng", "miscRng", "monsterHpRng",
                             "potionRng", "shuffleRng", "seed"})
        if (object.contains(name)) return true;
    return false;
}

bool parseCard(const json &item, const std::string &location, CardRecord &out) {
    if (!item.is_object() || !item.contains("id") || !item.at("id").is_string()
        || !item.contains("uuid") || !item.at("uuid").is_string()
        || !item.contains("misc") || !item.at("misc").is_number_integer()
        || !item.contains("cost") || !item.at("cost").is_number_integer()
        || !item.contains("costForTurn") || !item.at("costForTurn").is_number_integer()
        || !item.contains("upgraded") || !item.at("upgraded").is_boolean()
        || !item.contains("freeToPlayOnce") || !item.at("freeToPlayOnce").is_boolean()
        || !item.contains("retain") || !item.at("retain").is_boolean()) return false;
    try {
        const auto cardId = item.at("id").get<sts::CardId>();
        if (cardId == sts::CardId::INVALID) return false;
        out.uuid = item.at("uuid").get<std::string>();
        out.wire.id = static_cast<std::int16_t>(cardId);
        out.wire.specialData = item.at("misc").get<std::int16_t>();
        out.wire.cost = item.at("cost").get<std::int16_t>();
        out.wire.costForTurn = item.at("costForTurn").get<std::int16_t>();
        out.wire.upgraded = item.at("upgraded").get<bool>();
        out.wire.freeToPlayOnce = item.at("freeToPlayOnce").get<bool>();
        out.wire.retain = item.at("retain").get<bool>();
        return location == "HAND" || location == "DRAW" || location == "DISCARD" || location == "EXHAUST";
    } catch (...) { return false; }
}

int monsterId(const std::string &id) {
    const auto mapped = live_silver::monsterId(id);
    return mapped ? static_cast<int>(*mapped) : 0;
}

int moveId(const std::string &id, int nextMove) {
    const auto mapped = live_silver::monsterMove(id, nextMove);
    return mapped ? static_cast<int>(*mapped) : 0;
}

bool cardLess(const silver_bridge::CardWire &a, const silver_bridge::CardWire &b) {
    if (a.id != b.id) return a.id < b.id;
    if (a.uniqueId != b.uniqueId) return a.uniqueId < b.uniqueId;
    if (a.specialData != b.specialData) return a.specialData < b.specialData;
    if (a.cost != b.cost) return a.cost < b.cost;
    if (a.costForTurn != b.costForTurn) return a.costForTurn < b.costForTurn;
    if (a.upgraded != b.upgraded) return a.upgraded < b.upgraded;
    if (a.freeToPlayOnce != b.freeToPlayOnce) return a.freeToPlayOnce < b.freeToPlayOnce;
    return a.retain < b.retain;
}

bool isStrike(const silver_bridge::CardWire &wire) {
    sts::CardInstance card(static_cast<sts::CardId>(wire.id));
    return card.isStrikeCard();
}

bool isBlood(const silver_bridge::CardWire &wire) {
    sts::CardInstance card(static_cast<sts::CardId>(wire.id));
    return card.isBloodCard();
}

bool isNormality(const silver_bridge::CardWire &wire) {
    return wire.id == static_cast<std::int16_t>(sts::CardId::NORMALITY);
}

bool isPain(const silver_bridge::CardWire &wire) {
    return wire.id == static_cast<std::int16_t>(sts::CardId::PAIN);
}

bool isOffColorIroncladCard(sts::CardId id) {
    const auto color = sts::getCardColor(id);
    return color == sts::CardColor::GREEN || color == sts::CardColor::BLUE
        || color == sts::CardColor::PURPLE;
}
bool isOffColorIroncladCard(const silver_bridge::CardWire &wire) {
    return isOffColorIroncladCard(static_cast<sts::CardId>(wire.id));
}

bool parseCards(const json &array, const std::string &location, std::vector<CardRecord> &out) {
    if (!array.is_array()) return false;
    for (const auto &item : array) { CardRecord record; if (!parseCard(item, location, record)) return false; out.push_back(std::move(record)); }
    return true;
}

bool optionalInt(const json &object, const char *name, int &out) {
    if (!object.contains(name)) return false;
    if (!object.at(name).is_number_integer()) return false;
    out = object.at(name).get<int>();
    return true;
}

bool optionalBool(const json &object, const char *name, bool &out) {
    if (!object.contains(name)) return false;
    if (!object.at(name).is_boolean()) return false;
    out = object.at(name).get<bool>();
    return true;
}

bool parseGenericCard(const json &item, CardRecord &out) {
    if (!item.is_object() || !item.contains("id") || !item.at("id").is_string()
        || !item.contains("uuid") || !item.at("uuid").is_string()) return false;
    try {
        const auto id = item.at("id").get<sts::CardId>();
        if (id == sts::CardId::INVALID) return false;
        out.uuid = item.at("uuid").get<std::string>();
        if (out.uuid.empty()) return false;
        out.wire.id = static_cast<std::int16_t>(id);
        out.wire.specialData = static_cast<std::int16_t>(item.value("misc", item.value("specialData", 0)));
        out.wire.cost = static_cast<std::int16_t>(item.value("cost", 0));
        out.wire.costForTurn = static_cast<std::int16_t>(item.value("costForTurn", out.wire.cost));
        out.wire.upgraded = item.value("upgraded", false);
        out.wire.freeToPlayOnce = item.value("freeToPlayOnce", false);
        out.wire.retain = item.value("retain", false);
        if (!item.value("upgraded", false) && (!item.contains("upgraded") || !item.at("upgraded").is_boolean())) return false;
        return item.value("cost", 0) >= -2 && item.value("costForTurn", item.value("cost", 0)) >= -2;
    } catch (...) { return false; }
}

struct GenericPile {
    std::vector<CardRecord> bottom, unknown, top;
    bool fullOrderObserved = false;
};

bool parseGenericPile(const json &value, GenericPile &pile) {
    const auto parseArray = [](const json &array, std::vector<CardRecord> &out) {
        if (!array.is_array()) return false;
        for (const auto &item : array) { CardRecord card; if (!parseGenericCard(item, card)) return false; out.push_back(std::move(card)); }
        return true;
    };
    if (value.is_array()) return parseArray(value, pile.unknown);
    if (!value.is_object()) return false;
    if (value.contains("knownBottom") && !parseArray(value.at("knownBottom"), pile.bottom)) return false;
    if (value.contains("unknown") && !parseArray(value.at("unknown"), pile.unknown)) return false;
    if (value.contains("knownTop") && !parseArray(value.at("knownTop"), pile.top)) return false;
    pile.fullOrderObserved = value.value("fullOrderObserved", false);
    return true;
}

void setPlayerPower(silver_bridge::PlayerWire &player, PlayerStatus status, int amount,
                    bool justApplied, int bombDamage = 0) {
    switch (status) {
    case PlayerStatus::ARTIFACT: player.artifact = amount; break;
    case PlayerStatus::DEXTERITY: player.dexterity = amount; break;
    case PlayerStatus::FOCUS: player.focus = amount; break;
    case PlayerStatus::STRENGTH: player.strength = amount; break;
    case PlayerStatus::THE_BOMB:
        // Java's TheBombPower amount is turns remaining, while Silver stores
        // the damage in one of its three future-turn slots.
        if (amount >= 1 && amount <= 3)
            player.bombs[static_cast<std::size_t>(amount - 1)] = static_cast<std::int8_t>(bombDamage);
        break;
    case PlayerStatus::BARRICADE:
    case PlayerStatus::CORRUPTION:
    case PlayerStatus::CONFUSED:
    case PlayerStatus::HEX:
    case PlayerStatus::PEN_NIB:
    case PlayerStatus::SURROUNDED:
    case PlayerStatus::DRAW_REDUCTION:
        // These are active native flags without a statusMap payload.  In
        // particular, Draw Reduction's exact scalar is cardDrawPerTurn and
        // its lifetime is represented by justApplied, not by amount.
        if (static_cast<int>(status) < 64) player.statusBits0 |= 1ULL << static_cast<int>(status);
        else player.statusBits1 |= 1U << (static_cast<int>(status) - 64);
        break;
    default:
        if (static_cast<int>(status) < 64) player.statusBits0 |= 1ULL << static_cast<int>(status);
        else player.statusBits1 |= 1U << (static_cast<int>(status) - 64);
        player.statusMap.emplace_back(static_cast<std::int16_t>(status), static_cast<std::int16_t>(amount));
        break;
    }
    if (justApplied && static_cast<int>(status) < 32)
        player.justAppliedBits |= 1U << static_cast<int>(status);
}

bool setMonsterPower(silver_bridge::MonsterWire &monster, sts::MonsterStatus status, int amount,
                     bool justApplied) {
    const int value = amount;
    // Java boolean powers are presence states.  Vanilla may expose a
    // negative/sentinel amount for them; presence must still set the native
    // status bit before numeric powers are rejected as invalid.
    // Strength is the one signed numeric monster power: Disarm legitimately
    // exposes negative values.  Other negative numeric powers are not a
    // representable Java/native state and must fail closed.
    if (value < 0 && status != sts::MonsterStatus::STRENGTH
        && !sts::isBooleanPower(status)) return false;
    switch (status) {
    case sts::MonsterStatus::ARTIFACT: monster.smallPowers[0] = static_cast<std::int16_t>(value); break;
    case sts::MonsterStatus::BLOCK_RETURN: monster.smallPowers[1] = static_cast<std::int16_t>(value); break;
    case sts::MonsterStatus::CHOKED: monster.smallPowers[2] = static_cast<std::int16_t>(value); break;
    case sts::MonsterStatus::CORPSE_EXPLOSION: monster.smallPowers[3] = static_cast<std::int16_t>(value); break;
    case sts::MonsterStatus::LOCK_ON: monster.smallPowers[4] = static_cast<std::int16_t>(value); break;
    case sts::MonsterStatus::MARK: monster.smallPowers[5] = static_cast<std::int16_t>(value); break;
    case sts::MonsterStatus::METALLICIZE: monster.smallPowers[6] = static_cast<std::int16_t>(value); break;
    case sts::MonsterStatus::PLATED_ARMOR: monster.smallPowers[7] = static_cast<std::int16_t>(value); break;
    case sts::MonsterStatus::POISON: monster.smallPowers[8] = static_cast<std::int16_t>(value); break;
    case sts::MonsterStatus::REGEN: monster.smallPowers[9] = static_cast<std::int16_t>(value); break;
    case sts::MonsterStatus::SHACKLED: monster.smallPowers[10] = static_cast<std::int16_t>(value); break;
    case sts::MonsterStatus::STRENGTH: monster.strength = value; break;
    case sts::MonsterStatus::VULNERABLE: monster.vulnerable = value; break;
    case sts::MonsterStatus::WEAK: monster.weak = value; break;
    case sts::MonsterStatus::INVINCIBLE:
    case sts::MonsterStatus::REACTIVE:
    case sts::MonsterStatus::SHARP_HIDE: monster.uniquePower1 = static_cast<std::int16_t>(value); break;
    case sts::MonsterStatus::ANGRY:
    case sts::MonsterStatus::BEAT_OF_DEATH:
    case sts::MonsterStatus::CURIOSITY:
    case sts::MonsterStatus::CURL_UP:
    case sts::MonsterStatus::ENRAGE:
    case sts::MonsterStatus::FADING:
    case sts::MonsterStatus::FLIGHT:
    case sts::MonsterStatus::GENERIC_STRENGTH_UP:
    case sts::MonsterStatus::INTANGIBLE:
    case sts::MonsterStatus::MALLEABLE:
    case sts::MonsterStatus::MODE_SHIFT:
    case sts::MonsterStatus::RITUAL:
    case sts::MonsterStatus::SLOW:
    case sts::MonsterStatus::SPORE_CLOUD:
    case sts::MonsterStatus::THIEVERY:
    case sts::MonsterStatus::THORNS:
    case sts::MonsterStatus::TIME_WARP: monster.uniquePower0 = value; break;
    default: break;
    }
    // The Java power object establishes presence; its amount is only the
    // associated scalar. Keeping activation amount-dependent is wrong for
    // vanilla powers such as Giant Head Slow(0), Time Eater Time Warp(0),
    // and Writhing Mass Reactive(0).
    if (status != sts::MonsterStatus::STRENGTH) {
        monster.statusBits |= 1ULL << static_cast<int>(status);
    }
    if (justApplied) {
        if (status == sts::MonsterStatus::VULNERABLE) monster.statusBits |= 1ULL << 63;
        if (status == sts::MonsterStatus::WEAK) monster.statusBits |= 1ULL << 62;
        if (status == sts::MonsterStatus::RITUAL) monster.statusBits |= 1ULL << 61;
    }
    return true;
}

template <typename T>
bool parseEnumId(const json &item, const char *name, T &out) {
    if (!item.contains(name) || !item.at(name).is_string()) return false;
    try { out = item.at(name).get<T>(); return out != T::INVALID; } catch (...) { return false; }
}

void appendGenericCards(const GenericPile &pile, std::vector<CardRecord> &all) {
    all.insert(all.end(), pile.bottom.begin(), pile.bottom.end());
    all.insert(all.end(), pile.unknown.begin(), pile.unknown.end());
    all.insert(all.end(), pile.top.begin(), pile.top.end());
}

} // namespace

SilverRootImportResult importSilverRootLegacy(const json &observation) {
    SilverRootImportResult result;
    auto &wire = result.wire;
    const auto unsupported = [&](const char *reason) { result.reason = fail(reason); return result; };
    if (!observation.contains("silverRoot") || !observation.at("silverRoot").is_object()) return unsupported("silver_root_missing");
    const auto &root = observation.at("silverRoot");
    if (hasForbiddenRngField(observation) || hasForbiddenRngField(root)) return unsupported("silver_rng_field");
    int schema = 0, decisionOrdinal = -1, act = 0, floor = 0, ascension = 0;
    int hp = 0, maxHp = 0, gold = 0, potionCapacity = 0;
    bool firstDecision = false, burningElite = false;
    if (!requiredInt(root, "schemaVersion", schema) || schema != 2) return unsupported("silver_schema_version");
    if (!requiredInt(root, "decisionOrdinal", decisionOrdinal)
        || (decisionOrdinal != 0 && decisionOrdinal != 1)) return unsupported("silver_decision_ordinal");
    if (!requiredBool(root, "firstDecision", firstDecision)
        || firstDecision != (decisionOrdinal == 0)) return unsupported("silver_first_decision_flag");
    result.decisionOrdinal = decisionOrdinal;
    result.playerTurn = 1;
    result.decisionInTurn = decisionOrdinal;
    if (!requiredInt(root, "act", act) || act != 1) return unsupported("silver_act");
    if (!requiredInt(root, "floor", floor) || floor < 1) return unsupported("silver_floor");
    if (!requiredInt(root, "ascension", ascension) || !requiredInt(root, "hp", hp)
        || !requiredInt(root, "maxHp", maxHp) || !requiredInt(root, "gold", gold)
        || !requiredInt(root, "potionCapacity", potionCapacity)
        || !requiredBool(root, "burningElite", burningElite)) return unsupported("silver_root_state");
    if (burningElite) return unsupported("silver_burning_elite");
    if (!root.contains("roomClass") || !root.at("roomClass").is_string()) return unsupported("silver_room_class");
    if (observation.value("character", std::string()) != "IRONCLAD"
        || !root.contains("character") || !root.at("character").is_string()
        || root.at("character").get<std::string>() != "IRONCLAD") return unsupported("silver_character");
    if (!root.contains("combat") || !root.at("combat").is_object()) return unsupported("silver_combat_missing");
    const auto &combat = root.at("combat");
    if (hasForbiddenRngField(combat)) return unsupported("silver_rng_field");
    bool runicDome = false, frozenEye = false, cardSelect = false, resolving = false;
    int cardsPlayed = 0;
    if (!requiredBool(combat, "runicDome", runicDome) || runicDome) return unsupported("silver_runic_dome");
    if (!requiredBool(combat, "frozenEye", frozenEye) || frozenEye) return unsupported("silver_frozen_eye");
    if (!requiredInt(combat, "cardsPlayedThisTurn", cardsPlayed)
        || cardsPlayed != decisionOrdinal) return unsupported("silver_cards_played_history");
    if (!combat.contains("playedThisTurn") || !combat.at("playedThisTurn").is_array()
        || combat.at("playedThisTurn").size() != static_cast<std::size_t>(decisionOrdinal))
        return unsupported("silver_played_history");
    if (!combat.contains("playerPowers") || !combat.at("playerPowers").is_array()
        || !combat.at("playerPowers").empty()) return unsupported("silver_unmapped_player_power");
    if (!requiredBool(combat, "cardSelect", cardSelect) || !requiredBool(combat, "resolving", resolving)
        || cardSelect || resolving) return unsupported("silver_card_select");
    int turn = 0, energy = 0, block = 0;
    // Java's GameActionManager is one-based at the first actionable decision;
    // the native simulator's equivalent BattleContext root is zero-based.
    if (!requiredInt(combat, "turn", turn) || !requiredInt(combat, "energy", energy) || !requiredInt(combat, "block", block) || turn != 1)
        return unsupported("silver_first_turn_invariant");
    if (potionCapacity != 3 || !combat.contains("hand") || !combat.contains("draw")
        || !combat.contains("discard") || !combat.contains("exhaust") || !combat.contains("monsters")
        || !combat.contains("relics") || !combat.contains("potions")) return unsupported("silver_missing_state");

    std::vector<CardRecord> cards;
    if (!parseCards(combat.at("hand"), "HAND", cards)
        || !parseCards(combat.at("draw"), "DRAW", cards)
        || !parseCards(combat.at("discard"), "DISCARD", cards)
        || !parseCards(combat.at("exhaust"), "EXHAUST", cards)) return unsupported("silver_unknown_card");
    if (std::any_of(cards.begin(), cards.end(), [](const auto &card) {
            return isOffColorIroncladCard(card.wire);
        }))
        return unsupported("silver_off_color_card");
    if (cards.size() != 10) return unsupported("silver_nonstarter_deck");
    int strikes = 0, defends = 0, bashes = 0;
    for (const auto &card : cards) {
        const auto id = static_cast<sts::CardId>(card.wire.id);
        if (id == sts::CardId::STRIKE_RED) ++strikes;
        else if (id == sts::CardId::DEFEND_RED) ++defends;
        else if (id == sts::CardId::BASH) ++bashes;
        else return unsupported("silver_nonstarter_deck");
        const int expectedCost = id == sts::CardId::BASH ? 2 : 1;
        if (card.wire.upgraded || card.wire.specialData != 0
            || card.wire.cost != expectedCost || card.wire.costForTurn != expectedCost
            || card.wire.freeToPlayOnce || card.wire.retain)
            return unsupported("silver_nonstarter_deck");
    }
    if (strikes != 5 || defends != 4 || bashes != 1)
        return unsupported("silver_nonstarter_deck");
    std::sort(cards.begin(), cards.end(), [](const CardRecord &a, const CardRecord &b) { return a.uuid < b.uuid; });
    std::set<std::string> uuids;
    for (int i = 0; i < static_cast<int>(cards.size()); ++i) {
        if (!uuids.insert(cards[i].uuid).second || cards[i].uuid.empty()) return unsupported("silver_card_identity");
        cards[i].wire.uniqueId = static_cast<std::int16_t>(i);
    }
    if (combat.at("hand").size() != static_cast<std::size_t>(5 - decisionOrdinal))
        return unsupported("silver_hand_size");
    wire.nextUniqueCardId = static_cast<int>(cards.size());
    // Reparse by source so the UUID mapping above is applied without exposing pile order.
    std::unordered_map<std::string, silver_bridge::CardWire> byUuid;
    for (const auto &card : cards) byUuid.emplace(card.uuid, card.wire);
    const auto appendPile = [&](const char *name, std::vector<silver_bridge::CardWire> &target,
                                bool canonicalize) {
        for (const auto &item : combat.value(name, json::array())) {
            const auto uuid = item.value("uuid", std::string());
            target.push_back(byUuid.at(uuid));
        }
        if (canonicalize) std::sort(target.begin(), target.end(), cardLess);
    };
    appendPile("hand", wire.hand, false);
    appendPile("draw", wire.drawPile.unknown, true);
    appendPile("discard", wire.discardPile.unknown, true); appendPile("exhaust", wire.exhaustPile.unknown, true);
    wire.drawPile.valid = wire.discardPile.valid = wire.exhaustPile.valid = true;
    wire.drawPile.fullOrderObserved = wire.discardPile.fullOrderObserved = wire.exhaustPile.fullOrderObserved = false;
    const auto countWire = [](const std::vector<silver_bridge::CardWire> &pile,
                              bool (*predicate)(const silver_bridge::CardWire &)) {
        int count = 0;
        for (const auto &card : pile) if (predicate(card)) ++count;
        return count;
    };
    wire.strikeCount = 0;
    for (const auto &card : cards) if (isStrike(card.wire)) ++wire.strikeCount;
    wire.handNormalityCount = countWire(wire.hand, isNormality);
    wire.handPainCount = countWire(wire.hand, isPain);
    wire.handBloodCardCount = countWire(wire.hand, isBlood);
    wire.drawPileBloodCardCount = countWire(wire.drawPile.unknown, isBlood);
    wire.discardPileBloodCardCount = countWire(wire.discardPile.unknown, isBlood);

    wire.version = silver_bridge::BattleStateWire::kVersion;
    wire.valid = true; wire.fullDrawOrderObserved = false; wire.intentsHidden = false;
    wire.floorNum = floor; wire.act = act; wire.ascension = ascension;
    // BattleContext::init reaches PLAYER_NORMAL after two executeActions loop
    // iterations: the initial draw and the final decision-boundary check.
    wire.turn = 0; wire.cardsDrawn = 5; wire.loopCount = decisionOrdinal == 0 ? 2 : 0; wire.energyWasted = 0;
    wire.outcome = 0; wire.inputState = 1; // PLAYER_NORMAL, proven by the live decision gate
    wire.monsterTurnIdx = 6; wire.endTurnQueued = false; wire.turnHasEnded = false; wire.skipMonsterTurn = false;
    wire.potionCapacity = potionCapacity; wire.potionCount = 0;
    wire.potions.fill(static_cast<std::int16_t>(sts::Potion::EMPTY_POTION_SLOT));
    wire.player.characterClass = static_cast<std::int16_t>(sts::CharacterClass::IRONCLAD);
    wire.player.curHp = hp; wire.player.maxHp = maxHp; wire.player.gold = gold;
    wire.player.energy = energy; wire.player.energyPerTurn = 3; wire.player.cardDrawPerTurn = 5;
    wire.player.lastTargetedMonster = 1; wire.player.block = block;
    wire.player.cardsPlayedThisTurn = static_cast<std::int16_t>(decisionOrdinal);
    wire.player.attacksPlayedThisTurn = 0;
    wire.player.skillsPlayedThisTurn = 0; wire.player.cardsDiscardedThisTurn = 0;
    wire.player.lastAttackUnblockedDamage = 0; wire.player.timesDamagedThisCombat = 0;
    const int burningBlood = static_cast<int>(sts::RelicId::BURNING_BLOOD);
    wire.player.relicBits0 = burningBlood < 64 ? (1ULL << burningBlood) : 0;
    wire.player.relicBits1 = burningBlood >= 64 ? (1ULL << (burningBlood - 64)) : 0;
    if (!combat.at("relics").is_array() || combat.at("relics").size() != 1
        || !combat.at("relics")[0].is_object()
        || combat.at("relics")[0].value("id", std::string()) != "Burning Blood"
        || !combat.at("relics")[0].contains("counter")
        || !combat.at("relics")[0].at("counter").is_number_integer())
        return unsupported("silver_unmapped_relic_state");
    if (!combat.at("potions").is_array() || combat.at("potions").size() != static_cast<std::size_t>(potionCapacity))
        return unsupported("silver_unmapped_potion_state");
    for (std::size_t i = 0; i < combat.at("potions").size(); ++i) {
        const auto &potion = combat.at("potions")[i];
        if (!potion.is_object() || potion.value("slot", -1) != static_cast<int>(i)
            || potion.value("id", std::string()) != "Potion Slot") return unsupported("silver_unmapped_potion_state");
    }

    const auto monsters = combat.value("monsters", json::array());
    if (!monsters.is_array() || monsters.size() != 1) return unsupported("silver_unknown_monster");
    const std::string roomClass = root.at("roomClass").get<std::string>();
    wire.monsterCount = wire.monstersAlive = static_cast<int>(monsters.size());
    for (std::size_t i = 0; i < monsters.size(); ++i) {
        const auto &item = monsters[i];
        if (!item.is_object() || !item.contains("id") || !item.at("id").is_string()
            || !requiredInt(item, "hp", wire.monsters[i].curHp)
            || !requiredInt(item, "maxHp", wire.monsters[i].maxHp)
            || !requiredInt(item, "block", wire.monsters[i].block)
            || !item.contains("nextMove") || !item.at("nextMove").is_number_integer())
            return unsupported("silver_monster_state");
        const auto id = item.at("id").get<std::string>();
        const int canonical = monsterId(id), move = moveId(id, item.at("nextMove").get<int>());
        if (canonical == 0) return unsupported("silver_unknown_monster");
        if (move == 0) return unsupported("silver_unknown_move");
        if ((id == "Gremlin Nob" || id == "GremlinNob") ? roomClass != "ELITE" : roomClass != "MONSTER")
            return unsupported("silver_room_class");
        if (!item.contains("powers") || !item.at("powers").is_array()
            || !item.at("powers").empty()) return unsupported("silver_unmapped_monster_power");
        auto &monster = wire.monsters[i]; monster.idx = static_cast<int>(i); monster.id = canonical;
        monster.moveHistory = {static_cast<std::int16_t>(move), 0};
    }
    if (monsters.size() == 1) {
        const auto id = monsters.front().value("id", std::string());
        if (id == "Cultist") wire.encounter = static_cast<int>(sts::MonsterEncounter::CULTIST);
        else if (id == "JawWorm") wire.encounter = static_cast<int>(sts::MonsterEncounter::JAW_WORM);
        else if (id == "Gremlin Nob" || id == "GremlinNob") wire.encounter = static_cast<int>(sts::MonsterEncounter::GREMLIN_NOB);
    }
    for (auto &stasis : wire.stasisCards) {
        stasis.uniqueId = -1;
        // CardManager initializes the two inactive stasis slots with the
        // default card cost sentinel used by the native first root.
        stasis.cost = 1;
        stasis.costForTurn = 1;
    }
    // CardManager::limbo is a fixed ten-slot array, not a sized container;
    // native first-root conversion therefore carries ten default card slots.
    // Preserve that materialized invariant even though the public observer has
    // no meaningful limbo payload at PLAYER_NORMAL.
    wire.limbo.assign(10, silver_bridge::CardWire{});
    for (auto &card : wire.limbo) card.uniqueId = -1;
    wire.curCardQueueItem.card.uniqueId = -1;
    if (decisionOrdinal == 1) {
        const auto &played = combat.at("playedThisTurn")[0];
        if (!played.is_object() || !played.contains("id") || !played.at("id").is_string()
            || !played.contains("uuid") || !played.at("uuid").is_string()
            || !played.contains("upgraded") || !played.at("upgraded").is_boolean())
            return unsupported("silver_played_card");
        const auto playedId = played.at("id").get<std::string>();
        if (playedId != "Strike_R" && playedId != "Defend_R")
            return unsupported("silver_unsupported_continuation");
        if (played.at("upgraded").get<bool>()) return unsupported("silver_played_card");
        const auto playedUuid = played.at("uuid").get<std::string>();
        const auto mapped = byUuid.find(playedUuid);
        if (playedUuid.empty() || mapped == byUuid.end()) return unsupported("silver_played_card");
        const auto expectedId = playedId == "Strike_R" ? sts::CardId::STRIKE_RED : sts::CardId::DEFEND_RED;
        if (mapped->second.id != static_cast<std::int16_t>(expectedId) || mapped->second.upgraded)
            return unsupported("silver_played_card");
        int discardMatches = 0;
        for (const auto &item : combat.at("discard"))
            if (item.is_object() && item.value("uuid", std::string()) == playedUuid) ++discardMatches;
        if (discardMatches != 1) return unsupported("silver_played_card");
        wire.curCardQueueItem.card = mapped->second;
        wire.curCardQueueItem.target = 0;
        wire.curCardQueueItem.energyOnUse = energy + 1;
        wire.player.lastTargetedMonster = playedId == "Strike_R" ? 0 : 1;
        wire.player.attacksPlayedThisTurn = playedId == "Strike_R" ? 1 : 0;
        wire.player.skillsPlayedThisTurn = playedId == "Defend_R" ? 1 : 0;
        wire.loopCount = 6;
    }
    const auto combatEntryHash = observation.value("combatEntryHash", std::string());
    if (combatEntryHash.empty()) return unsupported("silver_combat_entry_hash");
    wire.isolatedSearchSeed = fnv1a(combatEntryHash + ":silver-live-v2");
    wire.observedGeneration = static_cast<std::uint64_t>(decisionOrdinal + 1);
    result.ok = true;
    return result;
}

// Audited Act 1 monsters whose next roll depends on public executed history.
// Spot Weakness carries only its public attack predicate for the pending roll.
// Generators and unaudited monster lifecycles remain outside this domain.
std::string importBoundedRunicDome(const json &combat, silver_bridge::BattleStateWire &wire) {
    const auto found=combat.find("runicDomeKnowledge");
    if(found==combat.end() || !found->is_object()) return "silver_runic_dome_missing_history";
    const auto validInteger=[](const json &obj,const char *name,std::int64_t lo,std::int64_t hi) {
        return obj.contains(name) && obj.at(name).is_number_integer() && obj.at(name)>=lo && obj.at(name)<=hi;
    };
    if(!validInteger(*found,"schemaVersion",1,2) || !found->contains("complete") || !found->at("complete").is_boolean())
        return "silver_runic_dome_history_schema";
    if(!found->at("complete").get<bool>()) return "silver_runic_dome_incomplete_history";
    const bool multi=found->at("schemaVersion")==2;
    json rows=multi?found->value("monsters",json()):json::array({*found});
    if(!validInteger(*found,"epoch",1,9007199254740991LL) || !rows.is_array()
            || rows.size()!=static_cast<std::size_t>(wire.monsterCount)) return "silver_runic_dome_history_schema";
    if(wire.act!=1 || wire.monsterCount<1 || wire.monsterCount>5) return "silver_runic_dome_encounter_domain";
    for(int slot=0;slot<wire.monsterCount;++slot) {
        const auto &k=rows.at(slot);
        const auto integer=[&](const char *name,std::int64_t lo,std::int64_t hi) {return validInteger(k,name,lo,hi);};
        auto &m=wire.monsters[slot];
        const bool dead=m.curHp<=0;
        if(!k.is_object() || !integer("schemaVersion",1,1) || !integer("epoch",1,9007199254740991LL) || k.at("epoch")!=found->at("epoch")
                || !k.contains("complete") || k.at("complete")!=true || !integer("completedTurns",0,9999)
                || !integer("generation",1,19999) || !integer("slot",slot,slot)
                || !integer("pendingMoveRolls",dead?0:1,dead?0:1)
                || !integer("rollHp",1,999) || !integer("rollMaxHp",1,999)
                || !k.contains("monsterId") || !k.at("monsterId").is_string()
                || !k.contains("executedMoves") || !k.at("executedMoves").is_array())
            return "silver_runic_dome_history_schema";
        const int completed=k.at("completedTurns").get<int>();
        const auto &moves=k.at("executedMoves");
        const auto monsterId=k.at("monsterId").get<std::string>();
        const auto id=live_silver::monsterId(monsterId);
        const bool jaw=monsterId=="JawWorm",cultist=monsterId=="Cultist",fungi=monsterId=="FungiBeast",
            red=monsterId=="SlaverRed",blue=monsterId=="SlaverBlue",acid=monsterId=="AcidSlime_M",
            spike=monsterId=="SpikeSlime_M",smallSpike=monsterId=="SpikeSlime_S",sentry=monsterId=="Sentry",nob=monsterId=="GremlinNob";
        if((!multi && (!(jaw||cultist) || wire.monsterCount!=1 || k.contains("pendingAttackPredicates")))
                || !(jaw||cultist||fungi||red||blue||acid||spike||smallSpike||sentry||nob) || !id || m.id!=static_cast<int>(*id)
                || m.idx!=slot || m.halfDead || m.isEscapingB || m.escapeNext
                || (nob && (wire.monsterCount!=1 || wire.encounter!=static_cast<int>(sts::MonsterEncounter::GREMLIN_NOB))))
            return "silver_runic_dome_encounter_domain";
        const auto generation=k.at("generation").get<int>();
        if((dead?completed>wire.turn:completed!=wire.turn) || generation<2*completed || generation>2*completed+1
                || (!dead && generation!=2*completed+1) || moves.size()!=static_cast<std::size_t>(std::min(completed,2))
                || k.at("rollHp")>k.at("rollMaxHp") || k.at("rollHp")<m.curHp || k.at("rollMaxHp")!=m.maxHp)
            return "silver_runic_dome_history_gap";
        int misc=0;
        if(multi) {
            if(!integer("publicMisc",0,red?1:0)) return "silver_runic_dome_history_schema";
            misc=k.at("publicMisc").get<int>();
            if(red && completed<2 && misc!=0) return "silver_runic_dome_history_gap";
        }
        m.moveHistory.fill(static_cast<std::int16_t>(sts::MonsterMoveId::INVALID));
        for(std::size_t i=0;i<moves.size();++i) {
            if(!moves[i].is_number_integer() || moves[i]<1 || moves[i]>4) return "silver_runic_dome_history_schema";
            const int move=moves[i].get<int>();
            const int execution=completed-static_cast<int>(moves.size())+static_cast<int>(i);
            const bool legal=smallSpike?move==1:sentry?move==((slot+execution)%2==0?3:4):jaw?(execution==0?move==1:move>=1&&move<=3)
                :cultist?move==(execution==0?3:1):nob?(execution==0?move==3:move==1||move==2)
                :red?(execution==0?move==1:move==1||move==2||move==3)
                :(blue||spike)?move==1||move==4:acid?move==1||move==2||move==4:move==1||move==2;
            if(!legal || (red && move==2 && misc!=1)) return "silver_runic_dome_history_gap";
            const auto native=live_silver::monsterMove(monsterId,move);
            if(!native) return "silver_runic_dome_history_schema";
            m.moveHistory[moves.size()-1-i]=static_cast<std::int16_t>(*native);
        }
        std::uint64_t allowed=(1ULL<<static_cast<int>(sts::MonsterStatus::ARTIFACT))
            | (1ULL<<static_cast<int>(sts::MonsterStatus::STRENGTH)) | (1ULL<<static_cast<int>(sts::MonsterStatus::WEAK))
            | (1ULL<<static_cast<int>(sts::MonsterStatus::VULNERABLE)) | (1ULL<<62) | (1ULL<<63);
        if(cultist) allowed|=(1ULL<<static_cast<int>(sts::MonsterStatus::RITUAL)) | (1ULL<<61);
        if(fungi) allowed|=1ULL<<static_cast<int>(sts::MonsterStatus::SPORE_CLOUD);
        if(nob) allowed|=1ULL<<static_cast<int>(sts::MonsterStatus::ENRAGE);
        if((m.statusBits & ~allowed) || m.uniquePower1 || (!(cultist||fungi||nob) && m.uniquePower0))
            return "silver_runic_dome_monster_power_domain";
        for(std::size_t i=1;i<m.smallPowers.size();++i)
            if(m.smallPowers[i]) return "silver_runic_dome_monster_power_domain";
        m.miscInfo=misc; m.pendingMoveRolls=dead?0:1; m.pendingDirectMoveChoice=0;
        auto &inputs=m.pendingRollInputs;
        inputs.curHp=k.at("rollHp").get<int>(); inputs.maxHp=k.at("rollMaxHp").get<int>();
        inputs.knightCurHp=inputs.curHp; inputs.knightMaxHp=inputs.maxHp; inputs.knightAlive=true;
        inputs.aliveCount=1; inputs.monstersAlive=1;
        if(multi) {
            if(!integer("firstHp",0,999) || !integer("firstMaxHp",1,999) || k.at("firstHp")>k.at("firstMaxHp")
                    || !k.contains("firstAlive") || !k.at("firstAlive").is_boolean()
                    || !integer("aliveCount",1,wire.monsterCount)) return "silver_runic_dome_history_schema";
            inputs.knightCurHp=k.at("firstHp").get<int>();inputs.knightMaxHp=k.at("firstMaxHp").get<int>();
            inputs.knightAlive=k.at("firstAlive").get<bool>();inputs.aliveCount=k.at("aliveCount").get<int>();
            inputs.monstersAlive=inputs.aliveCount;
        }
        if(multi && !k.contains("pendingAttackPredicates")) return "silver_runic_dome_predicate_schema";
        if(k.contains("pendingAttackPredicates")) {
            const auto &predicates=k.at("pendingAttackPredicates");
            if(!predicates.is_array() || predicates.size()>1 || (!predicates.empty() && (dead || !predicates[0].is_array()
                    || predicates[0].size()!=2 || !predicates[0][0].is_number_integer() || predicates[0][0]!=1
                    || !predicates[0][1].is_boolean()))) return "silver_runic_dome_predicate_schema";
            if(!predicates.empty()) m.pendingAttackPredicates.emplace_back(1,predicates[0][1].get<bool>());
        }
        inputs.monsterTurnNumber=std::max(1,completed); inputs.miscInfo=misc;
        inputs.playerConstricted=false;inputs.asleep=false;inputs.halfDead=false;
    }
    // A consumed potion can leave a generator power after its source card
    // vanished. Check typed native state as well as the public power names.
    const auto &player=wire.player;
    const std::set<int> statuses={static_cast<int>(PlayerStatus::METALLICIZE),static_cast<int>(PlayerStatus::WEAK),
        static_cast<int>(PlayerStatus::FRAIL),static_cast<int>(PlayerStatus::VULNERABLE),static_cast<int>(PlayerStatus::ENTANGLED)};
    std::uint64_t allowed0=0; std::uint32_t allowed1=0,justApplied=0;
    for(int status:statuses) {if(status<64) allowed0|=1ULL<<status;else allowed1|=1U<<(status-64);}
    for(auto status:{PlayerStatus::WEAK,PlayerStatus::FRAIL,PlayerStatus::VULNERABLE}) justApplied|=1U<<static_cast<int>(status);
    if((player.statusBits0 & ~allowed0) || (player.statusBits1 & ~allowed1) || (player.justAppliedBits & ~justApplied)
            || player.orbSlots || player.stance || player.focus || player.combustHpLoss
            || player.devaFormEnergyPerTurn || player.echoFormCardsDoubled || player.panacheCounter
            || std::any_of(player.bombs.begin(),player.bombs.end(),[](auto value){return value!=0;}))
        return "silver_runic_dome_player_power_domain";
    for(const auto &[status,amount]:player.statusMap)
        if(!statuses.count(status)) return "silver_runic_dome_player_power_domain";
    for(const auto &power:combat.value("playerPowers",json::array())) {
        const auto id=power.value("id",std::string());
        if(id!="Strength" && id!="Dexterity" && id!="Artifact" && id!="Metallicize"
                && id!="Weak" && id!="Frail" && id!="Vulnerable" && id!="Entangled")
            return "silver_runic_dome_player_power_domain";
    }
    const auto cardAllowed=[&](std::int16_t raw) {
        switch(static_cast<sts::CardId>(raw)) {
            case sts::CardId::INVALID: case sts::CardId::STRIKE_RED: case sts::CardId::DEFEND_RED:
            case sts::CardId::BASH: case sts::CardId::ANGER: case sts::CardId::CLEAVE:
            case sts::CardId::CLOTHESLINE: case sts::CardId::HEADBUTT: case sts::CardId::IRON_WAVE:
            case sts::CardId::POMMEL_STRIKE: case sts::CardId::SHRUG_IT_OFF: case sts::CardId::THUNDERCLAP:
            case sts::CardId::TWIN_STRIKE: case sts::CardId::PERFECTED_STRIKE: case sts::CardId::SWORD_BOOMERANG:
            case sts::CardId::HEAVY_BLADE: case sts::CardId::BODY_SLAM: case sts::CardId::INFLAME:
            case sts::CardId::METALLICIZE: case sts::CardId::WOUND: case sts::CardId::SLIMED: case sts::CardId::DAZED: return true;
            case sts::CardId::SPOT_WEAKNESS: return multi;
            default:return false;
        }
    };
    for(const auto *cards:{&wire.hand,&wire.drawPile.knownTop,&wire.drawPile.knownBottom,&wire.drawPile.unknown,
                          &wire.discardPile.unknown,&wire.exhaustPile.unknown,&wire.limbo})
        for(const auto &c:*cards) if(!cardAllowed(c.id)) return "silver_runic_dome_card_domain";
    if(!cardAllowed(wire.curCardQueueItem.card.id)) return "silver_runic_dome_card_domain";
    for(const auto &c:wire.pendingCardQueue) if(!cardAllowed(c.card.id)) return "silver_runic_dome_card_domain";
    for(const auto &c:wire.cardSelect.cards) if(!cardAllowed(c)) return "silver_runic_dome_card_domain";
    bool owned=false;
    for(const auto &relic:combat.at("relics")) {
        sts::RelicId id;
        if(!parseEnumId(relic,"id",id)) return "silver_runic_dome_relic_domain";
        switch(id) {
            case sts::RelicId::RUNIC_DOME: owned=true; break;
            case sts::RelicId::BURNING_BLOOD: case sts::RelicId::VAJRA: case sts::RelicId::ANCHOR:
            case sts::RelicId::BAG_OF_PREPARATION: case sts::RelicId::ORICHALCUM: break;
            default:return "silver_runic_dome_relic_domain";
        }
    }
    if(!owned) return "silver_runic_dome_relic_domain";
    for(const auto raw:wire.potions) {
        switch(static_cast<sts::Potion>(raw)) {
            case sts::Potion::EMPTY_POTION_SLOT: case sts::Potion::FIRE_POTION: case sts::Potion::BLOCK_POTION:
            case sts::Potion::STRENGTH_POTION: case sts::Potion::DEXTERITY_POTION: case sts::Potion::WEAK_POTION:
            case sts::Potion::FEAR_POTION: case sts::Potion::EXPLOSIVE_POTION: case sts::Potion::ENERGY_POTION: break;
            default:return "silver_runic_dome_potion_domain";
        }
    }
    wire.intentsHidden=true;
    return {};
}

SilverRootImportResult importSilverRootGeneric(const json &observation,
                                               SilverImportContext &context) {
    SilverRootImportResult result;
    auto &wire = result.wire;
    const auto unsupported = [&](const std::string &reason) {
        result.reason = reason;
        return result;
    };
    const auto rootIt = observation.find("silverRoot");
    if (rootIt == observation.end() || !rootIt->is_object()) return unsupported("silver_root_missing");
    const auto &root = *rootIt;
    if (hasForbiddenRngField(observation) || hasForbiddenRngField(root)) return unsupported("silver_rng_field");
    if (root.value("schemaVersion", 0) != 4) return unsupported("silver_schema_version");
    if (observation.value("character", std::string()) != "IRONCLAD"
        || root.value("character", std::string()) != "IRONCLAD") return unsupported("silver_character");
    const auto combatIt = root.find("combat");
    if (combatIt == root.end() || !combatIt->is_object()) return unsupported("silver_combat_missing");
    const auto &combat = *combatIt;
    if (hasForbiddenRngField(combat)) return unsupported("silver_rng_field");
    if (combat.contains("pendingCardQueueError"))
        return unsupported("silver_pending_card_queue_unrepresentable");
    const auto selectionIt = combat.find("cardSelect");
    const bool cardSelect = selectionIt != combat.end() && selectionIt->is_object();
    // A stable combat selection is still combat when its action has no native
    // serializer. Reject that explicit support boundary before inspecting the
    // unrelated normal-play state or requiring predecessor reconstruction.
    if (cardSelect && selectionIt->contains("unsupportedReason")) {
        const auto &reason = selectionIt->at("unsupportedReason");
        if (!reason.is_string()) return unsupported("silver_unmapped_selection_task");
        if (!reason.get<std::string>().empty()) return unsupported(reason.get<std::string>());
    }
    if (cardSelect && !live_silver::cardSelectTask(selectionIt->value("task", std::string())))
        return unsupported("silver_unmapped_selection_task");
    if (!combat.contains("damageTrackingExact")
        || !combat.at("damageTrackingExact").is_boolean()
        || !combat.at("damageTrackingExact").get<bool>())
        return unsupported("silver_damage_tracking");

    const std::string entry = root.value("combatInstance",
        observation.value("combatEntryHash", std::string()));
    if (entry.empty()) return unsupported("silver_combat_entry_hash");
    context.reset(observation.value("session", context.session), entry);

    int decision = root.value("decisionInTurn", root.value("decisionOrdinal", 0));
    if (decision < 0) return unsupported("silver_decision_ordinal");
    result.decisionOrdinal = decision;
    result.playerTurn = root.value("playerTurn", combat.value("turn", 1));
    result.decisionInTurn = decision;
    int act = root.value("act", 1), floor = root.value("floor", 0), ascension = root.value("ascension", 0);
    if (floor < 1 || act < 1 || ascension < 0) return unsupported("silver_root_state");
    wire.act = act; wire.floorNum = floor; wire.ascension = ascension;
    wire.turn = std::max(0, root.value("playerTurn", combat.value("turn", 1)) - 1);
    wire.loopCount = combat.value("loopCount", 0);
    wire.energyWasted = combat.value("energyWasted", 0);
    wire.cardsDrawn = combat.value("cardsDrawn", 0);
    // Java omits this native-only field at a stable player decision. Silver's
    // player-turn sentinel is 6; zero would immediately execute monsters after
    // any card action and manufacture chance branches before End Turn.
    wire.monsterTurnIdx = combat.value("monsterTurnIdx", 6);
    wire.endTurnQueued = combat.value("endTurnQueued", false);
    wire.turnHasEnded = combat.value("turnHasEnded", false);
    wire.skipMonsterTurn = combat.value("skipMonsterTurn", false);
    wire.miscBits = static_cast<std::uint32_t>(combat.value("miscBits", 0));
    wire.outcome = combat.value("outcome", 0);
    const auto parseGroupBits = [&](const char *name, std::uint8_t &out) {
        if (!combat.contains(name)) return true;
        if (!combat.at(name).is_number_integer()) return false;
        const int value = combat.at(name).get<int>();
        if (value < 0 || value > 31) return false;
        out = static_cast<std::uint8_t>(value);
        return true;
    };
    if (!parseGroupBits("extraRollMoveOnTurn", wire.extraRollMoveOnTurn)
        || !parseGroupBits("skipMonsterTurnBits", wire.skipMonsterTurnBits))
        return unsupported("silver_unmapped_group_state");

    bool runicDome = combat.value("runicDome", false);

    const bool frozenEye = combat.value("frozenEye", false);
    const auto getPlayer = [&]() -> const json * {
        const auto it = combat.find("player");
        return it != combat.end() && it->is_object() ? &*it : nullptr;
    };
    const json *player = getPlayer();
    const auto valueInt = [&](const char *name, int fallback) {
        if (player != nullptr && player->contains(name)) return player->value(name, fallback);
        return combat.value(name, fallback);
    };
    wire.potionCapacity = root.value("potionCapacity", valueInt("potionCapacity", 3));
    if (wire.potionCapacity < 0 || wire.potionCapacity > static_cast<int>(wire.potions.size()))
        return unsupported("silver_unmapped_potion_state");

    std::vector<CardRecord> allCards;
    std::vector<CardRecord> hand, limbo, stasis;
    std::vector<int> stasisSlots;
    GenericPile draw, discard, exhaust;
    const auto parseVector = [&](const char *name, std::vector<CardRecord> &out) {
        const auto it = combat.find(name);
        if (it == combat.end()) return true;
        if (!it->is_array()) return false;
        for (const auto &item : *it) { CardRecord card; if (!parseGenericCard(item, card)) return false; out.push_back(std::move(card)); }
        return true;
    };
    if (!combat.contains("limbo") || !combat.contains("stasis"))
        return unsupported("silver_unmapped_card_state");
    if (!parseVector("hand", hand) || !parseVector("limbo", limbo)
        || !parseVector("stasis", stasis) || !parseGenericPile(combat.value("draw", json::array()), draw)
        || !parseGenericPile(combat.value("discard", json::array()), discard)
        || !parseGenericPile(combat.value("exhaust", json::array()), exhaust))
        return unsupported("silver_unknown_card");
    if (stasis.size() > wire.stasisCards.size()) return unsupported("silver_unmapped_stasis");
    if (!stasis.empty()) {
        std::array<CardRecord, 2> orderedStasis;
        std::array<bool, 2> seenStasis {};
        const auto &stasisJson = combat.at("stasis");
        for (std::size_t i = 0; i < stasis.size(); ++i) {
            if (!stasisJson[i].is_object() || !stasisJson[i].contains("slot")
                || !stasisJson[i].at("slot").is_number_integer())
                return unsupported("silver_unmapped_stasis");
            const int slot = stasisJson[i].at("slot").get<int>();
            if (slot < 0 || slot >= static_cast<int>(orderedStasis.size()) || seenStasis[slot])
                return unsupported("silver_unmapped_stasis");
            seenStasis[slot] = true;
            orderedStasis[slot] = std::move(stasis[i]);
        }
        stasis.clear();
        for (std::size_t slot = 0; slot < orderedStasis.size(); ++slot) {
            if (!seenStasis[slot]) continue;
            stasis.push_back(std::move(orderedStasis[slot]));
            stasisSlots.push_back(static_cast<int>(slot));
        }
    } else if (!combat.at("stasis").empty()) {
        return unsupported("silver_unmapped_stasis");
    }
    if (!frozenEye && (draw.fullOrderObserved || combat.value("drawOrderVisible", false)))
        return unsupported("silver_hidden_information_required");
    if (frozenEye && draw.fullOrderObserved
        && (!draw.bottom.empty() || !draw.unknown.empty())) {
        // The compact Java producer form is an ordered array.  Under Frozen
        // Eye that order is public, so normalize every supplied segment into
        // the native known-top representation instead of retaining a hidden
        // multiset alongside it.
        std::vector<CardRecord> ordered;
        ordered.reserve(draw.bottom.size() + draw.unknown.size() + draw.top.size());
        ordered.insert(ordered.end(), std::make_move_iterator(draw.bottom.begin()),
                       std::make_move_iterator(draw.bottom.end()));
        ordered.insert(ordered.end(), std::make_move_iterator(draw.unknown.begin()),
                       std::make_move_iterator(draw.unknown.end()));
        ordered.insert(ordered.end(), std::make_move_iterator(draw.top.begin()),
                       std::make_move_iterator(draw.top.end()));
        draw.top = std::move(ordered);
        draw.bottom.clear();
        draw.unknown.clear();
    }
    appendGenericCards(draw, allCards); appendGenericCards(discard, allCards);
    appendGenericCards(exhaust, allCards); allCards.insert(allCards.end(), hand.begin(), hand.end());
    allCards.insert(allCards.end(), limbo.begin(), limbo.end()); allCards.insert(allCards.end(), stasis.begin(), stasis.end());
    if (std::any_of(allCards.begin(), allCards.end(), [](const auto &card) {
            return isOffColorIroncladCard(card.wire);
        }))
        return unsupported("silver_off_color_card");
    std::set<std::string> seen;
    int highestId = -1;
    for (auto &card : allCards) {
        if (!seen.insert(card.uuid).second) return unsupported("silver_card_identity");
        auto id = context.cardIds.find(card.uuid);
        if (id == context.cardIds.end()) {
            if (context.nextUniqueCardId > std::numeric_limits<std::int16_t>::max())
                return unsupported("silver_card_identity");
            id = context.cardIds.emplace(card.uuid, static_cast<std::int16_t>(context.nextUniqueCardId++)).first;
        }
        card.wire.uniqueId = id->second;
        highestId = std::max(highestId, static_cast<int>(id->second));
    }
    const auto indexCards = [&](const std::vector<CardRecord> &records) {
        std::vector<silver_bridge::CardWire> out;
        for (const auto &card : records) {
            const auto id = context.cardIds.find(card.uuid);
            if (id == context.cardIds.end()) continue;
            auto copy = card.wire; copy.uniqueId = id->second; out.push_back(copy);
        }
        return out;
    };
    wire.hand = indexCards(hand);
    wire.limbo.assign(10, silver_bridge::CardWire{});
    for (auto &card : wire.limbo) card.uniqueId = -1;
    const auto indexedLimbo = indexCards(limbo);
    if (indexedLimbo.size() > wire.limbo.size()) return unsupported("silver_unmapped_limbo");
    std::copy(indexedLimbo.begin(), indexedLimbo.end(), wire.limbo.begin());
    wire.stasisCards.fill(silver_bridge::CardWire{});
    for (auto &card : wire.stasisCards) {
        card.uniqueId = -1;
        card.cost = 1;
        card.costForTurn = 1;
    }
    const auto indexedStasis = indexCards(stasis);
    for (std::size_t i = 0; i < indexedStasis.size() && i < stasisSlots.size(); ++i)
        wire.stasisCards[stasisSlots[i]] = indexedStasis[i];
    wire.drawPile.valid = wire.discardPile.valid = wire.exhaustPile.valid = true;
    wire.drawPile.fullOrderObserved = wire.discardPile.fullOrderObserved = wire.exhaustPile.fullOrderObserved = false;
    wire.drawPile.knownBottom = indexCards(draw.bottom); wire.drawPile.unknown = indexCards(draw.unknown);
    wire.drawPile.knownTop = indexCards(draw.top); wire.drawPile.fullOrderObserved = frozenEye;
    if (frozenEye && wire.drawPile.knownTop.empty() && !wire.drawPile.unknown.empty()) {
        wire.drawPile.knownTop = std::move(wire.drawPile.unknown);
        wire.drawPile.unknown.clear();
    }
    wire.discardPile.unknown = indexCards(discard.unknown);
    wire.exhaustPile.unknown = indexCards(exhaust.unknown);
    const auto sortPile = [](std::vector<silver_bridge::CardWire> &cards) {
        std::sort(cards.begin(), cards.end(), cardLess);
    };
    if (!frozenEye) sortPile(wire.drawPile.unknown);
    sortPile(wire.discardPile.unknown); sortPile(wire.exhaustPile.unknown);
    const int declaredNextUniqueCardId = combat.value("nextUniqueCardId", highestId + 1);
    if (declaredNextUniqueCardId < 0) return unsupported("silver_card_identity");
    context.nextUniqueCardId = std::max(context.nextUniqueCardId, declaredNextUniqueCardId);
    wire.nextUniqueCardId = std::max(context.nextUniqueCardId, highestId + 1);
    if (wire.nextUniqueCardId < highestId + 1) return unsupported("silver_card_identity");

    const auto countWire = [](const std::vector<silver_bridge::CardWire> &cards, auto predicate) {
        return static_cast<int>(std::count_if(cards.begin(), cards.end(), predicate));
    };
    wire.strikeCount = combat.value("strikeCount", 0);
    if (!combat.contains("strikeCount")) {
        wire.strikeCount = 0;
        for (const auto &card : allCards) if (isStrike(card.wire)) ++wire.strikeCount;
    }
    wire.handNormalityCount = combat.value("handNormalityCount", countWire(wire.hand, isNormality));
    wire.handPainCount = combat.value("handPainCount", countWire(wire.hand, isPain));
    wire.handBloodCardCount = combat.value("handBloodCardCount", countWire(wire.hand, isBlood));
    wire.drawPileBloodCardCount = combat.value("drawPileBloodCardCount", countWire(wire.drawPile.unknown, isBlood));
    wire.discardPileBloodCardCount = combat.value("discardPileBloodCardCount", countWire(wire.discardPile.unknown, isBlood));

    auto &p = wire.player;
    p.characterClass = static_cast<std::int16_t>(sts::CharacterClass::IRONCLAD);
    p.curHp = root.value("hp", valueInt("curHp", 0)); p.maxHp = root.value("maxHp", valueInt("maxHp", 0));
    p.gold = root.value("gold", valueInt("gold", 0)); p.energy = valueInt("energy", 0);
    const json *turnEnergy = player != nullptr && player->contains("energyPerTurn")
        ? &player->at("energyPerTurn")
        : combat.contains("energyPerTurn") ? &combat.at("energyPerTurn") : nullptr;
    if (turnEnergy && !turnEnergy->is_number_integer())
        return unsupported("silver_unmapped_player_power");
    const auto baseEnergyPerTurn = turnEnergy ? turnEnergy->get<std::int64_t>() : 3;
    if (baseEnergyPerTurn < 0 || baseEnergyPerTurn > 127)
        return unsupported("silver_unmapped_player_power");
    p.energyPerTurn = static_cast<std::int8_t>(baseEnergyPerTurn);
    p.cardDrawPerTurn = static_cast<std::int8_t>(valueInt("cardDrawPerTurn", 5));
    p.block = valueInt("block", 0); p.stance = static_cast<std::int16_t>(valueInt("stance", 0));
    p.lastTargetedMonster = static_cast<std::int8_t>(valueInt("lastTargetedMonster", 1));
    p.orbSlots = static_cast<std::int8_t>(valueInt("orbSlots", 0));
    p.artifact = valueInt("artifact", 0); p.dexterity = valueInt("dexterity", 0);
    p.focus = valueInt("focus", 0); p.strength = valueInt("strength", 0);
    p.cardsPlayedThisTurn = static_cast<std::int16_t>(combat.value("cardsPlayedThisTurn", decision));
    p.attacksPlayedThisTurn = static_cast<std::int16_t>(combat.value("attacksPlayedThisTurn", 0));
    p.skillsPlayedThisTurn = static_cast<std::int16_t>(combat.value("skillsPlayedThisTurn", 0));
    p.cardsDiscardedThisTurn = static_cast<std::int16_t>(combat.value("cardsDiscardedThisTurn", 0));
    p.lastAttackUnblockedDamage = static_cast<std::int16_t>(combat.value("lastAttackUnblockedDamage", 0));
    p.timesDamagedThisCombat = static_cast<std::int16_t>(combat.value("timesDamagedThisCombat", 0));
    p.haveUsedNecronomiconThisTurn = combat.value("haveUsedNecronomiconThisTurn", false);
    p.combustHpLoss = static_cast<std::int8_t>(combat.value("combustHpLoss", 0));
    p.devaFormEnergyPerTurn = static_cast<std::int16_t>(combat.value("devaFormEnergyPerTurn", 0));
    p.echoFormCardsDoubled = static_cast<std::int8_t>(combat.value("echoFormCardsDoubled", 0));
    p.panacheCounter = static_cast<std::int8_t>(combat.value("panacheCounter", 0));
    if (combat.contains("orangePelletsCardTypesPlayed"))
        p.orangePelletsCardTypesPlayed = static_cast<std::uint8_t>(combat.value("orangePelletsCardTypesPlayed", 0));
    if (combat.contains("statusBits0")) p.statusBits0 = combat.value("statusBits0", 0ULL);
    if (combat.contains("statusBits1")) p.statusBits1 = combat.value("statusBits1", 0U);
    if (combat.contains("justAppliedBits")) p.justAppliedBits = combat.value("justAppliedBits", 0U);
    if (combat.contains("statusMap") && combat.at("statusMap").is_array()) {
        for (const auto &item : combat.at("statusMap")) {
            if (!item.is_array() || item.size() != 2 || !item[0].is_number_integer() || !item[1].is_number_integer())
                return unsupported("silver_unmapped_player_power");
            p.statusMap.emplace_back(item[0].get<std::int16_t>(), item[1].get<std::int16_t>());
        }
    }
    if (combat.contains("playerPowers")) {
        if (!combat.at("playerPowers").is_array()) return unsupported("silver_unmapped_player_power");
        for (const auto &power : combat.at("playerPowers")) {
            if (!power.is_object() || !power.contains("id") || !power.at("id").is_string()
                || !power.contains("amount") || !power.at("amount").is_number_integer())
                return unsupported("silver_unmapped_player_power");
            const auto powerId = power.at("id").get<std::string>();
            // Vanilla keeps Berserk outside EnergyManager.energyMaster;
            // native combat folds it into the permanent turn-energy scalar.
            if (powerId == "Berserk") {
                const auto amount = power.at("amount").get<std::int64_t>();
                if (turnEnergy == nullptr || amount <= 0 || amount > 127 - p.energyPerTurn)
                    return unsupported("silver_unmapped_player_power");
                p.energyPerTurn = static_cast<std::int8_t>(p.energyPerTurn + amount);
                continue;
            }
            auto mapped = live_silver::playerStatus(powerId);
            // The vanilla power ID is suffixed with a process-local counter
            // (TheBomb0, TheBomb1, ...), so its mapping cannot be a plain
            // string-table lookup.
            if (!mapped && powerId.rfind("TheBomb", 0) == 0)
                mapped = PlayerStatus::THE_BOMB;
            if (!mapped) return unsupported("silver_unmapped_player_power");
            // These fields are not derivable from a generic Java power ID and
            // amount.  Accept them only when the producer has serialized the
            // native bookkeeping explicitly.
            const bool needsCombust = *mapped == PlayerStatus::COMBUST;
            const bool needsEcho = *mapped == PlayerStatus::ECHO_FORM;
            const bool needsPanache = *mapped == PlayerStatus::PANACHE;
            const bool needsDeva = *mapped == PlayerStatus::DEVA;
            const bool needsBomb = *mapped == PlayerStatus::THE_BOMB;
            const bool needsJustApplied = *mapped == PlayerStatus::DOUBLE_DAMAGE
                || *mapped == PlayerStatus::DRAW_REDUCTION || *mapped == PlayerStatus::FRAIL
                || *mapped == PlayerStatus::INTANGIBLE || *mapped == PlayerStatus::VULNERABLE
                || *mapped == PlayerStatus::WEAK;
            if ((needsCombust && !combat.contains("combustHpLoss"))
                || (needsEcho && !combat.contains("echoFormCardsDoubled"))
                || (needsPanache && !combat.contains("panacheCounter"))
                || (needsDeva && !combat.contains("devaFormEnergyPerTurn"))
                || (needsBomb && (!power.contains("bombDamage")
                    || !power.at("bombDamage").is_number_integer()
                    || power.value("amount", 0) < 1 || power.value("amount", 0) > 3))
                || (*mapped == PlayerStatus::DRAW_REDUCTION && !combat.contains("cardDrawPerTurn"))
                || (needsJustApplied && (!power.contains("justApplied")
                    || !power.at("justApplied").is_boolean())))
                return unsupported("silver_unmapped_player_power");
            const int amount = power.value("amount", 1);
            if (needsBomb) {
                const int damage = power.at("bombDamage").get<int>();
                if (damage <= 0 || damage > 127) return unsupported("silver_unmapped_player_power");
                if (p.bombs[static_cast<std::size_t>(amount - 1)])
                    return unsupported("silver_unmapped_player_power");
                setPlayerPower(p, *mapped, amount, false, damage);
            } else {
                setPlayerPower(p, *mapped, amount, power.value("justApplied", false));
            }
        }
    }

    p.relicBits0 = p.relicBits1 = 0;
    p.relicCounters.fill(0);
    const auto relics = combat.value("relics", json::array());
    if (!relics.is_array()) return unsupported("silver_unmapped_relic_state");
    for (const auto &relic : relics) {
        if (!relic.is_object()) return unsupported("silver_unmapped_relic_state");
        sts::RelicId id; if (!parseEnumId(relic, "id", id)) return unsupported("silver_unmapped_relic_state");
        if (!relic.contains("usedUp") || !relic.at("usedUp").is_boolean()
            || !relic.contains("counter") || !relic.at("counter").is_number_integer())
            return unsupported("silver_unmapped_relic_state");
        if (id == sts::RelicId::NECRONOMICON
            && (!relic.contains("usedThisTurn") || !relic.at("usedThisTurn").is_boolean()))
            return unsupported("silver_unmapped_relic_state");
        if (relic.at("usedUp").get<bool>()) continue;
        const int rid = static_cast<int>(id);
        if (rid < 64) p.relicBits0 |= 1ULL << rid; else p.relicBits1 |= 1ULL << (rid - 64);
        const auto counter = static_cast<std::int8_t>(relic.at("counter").get<int>());
        const std::array<sts::RelicId, 7> counterRelics = {sts::RelicId::HAPPY_FLOWER, sts::RelicId::INCENSE_BURNER,
            sts::RelicId::INK_BOTTLE, sts::RelicId::INSERTER, sts::RelicId::NUNCHAKU, sts::RelicId::PEN_NIB, sts::RelicId::SUNDIAL};
        for (std::size_t i = 0; i < counterRelics.size(); ++i) {
            if (id != counterRelics[i]) continue;
            if (id == sts::RelicId::PEN_NIB && counter == 9) {
                // Vanilla uses counter 9 as the armed sentinel. Silver turns
                // that sentinel into the Pen Nib status bit and stores -1 in
                // its relic counter, matching BattleContext::init.
                p.statusBits0 |= 1ULL << static_cast<int>(PlayerStatus::PEN_NIB);
                p.relicCounters[i] = -1;
            } else {
                p.relicCounters[i] = counter;
            }
        }
        if (id == sts::RelicId::NECRONOMICON) p.haveUsedNecronomiconThisTurn = relic.at("usedThisTurn").get<bool>();
    }

    wire.potions.fill(static_cast<std::int16_t>(sts::Potion::EMPTY_POTION_SLOT));
    const auto potions = combat.value("potions", json::array());
    if (!potions.is_array() || potions.size() < static_cast<std::size_t>(wire.potionCapacity)) return unsupported("silver_unmapped_potion_state");
    for (std::size_t i = 0; i < static_cast<std::size_t>(wire.potionCapacity); ++i) {
        const auto &potion = potions[i];
        const std::string idText = potion.is_string() ? potion.get<std::string>() : potion.value("id", std::string());
        if (!potion.is_string() && (!potion.is_object() || potion.value("slot", static_cast<int>(i)) != static_cast<int>(i))) return unsupported("silver_unmapped_potion_state");
        try {
            const auto id = idText == "Potion Slot" ? sts::Potion::EMPTY_POTION_SLOT : json(idText).get<sts::Potion>();
            if (id == sts::Potion::INVALID) return unsupported("silver_unsupported_potion");
            wire.potions[i] = static_cast<std::int16_t>(id); if (id != sts::Potion::EMPTY_POTION_SLOT) ++wire.potionCount;
        } catch (...) { return unsupported("silver_unsupported_potion"); }
    }

    const auto monsters = combat.value("monsters", json::array());
    if (!monsters.is_array() || monsters.empty() || monsters.size() > wire.monsters.size()) return unsupported("silver_unknown_monster");
    wire.monsterCount = 0; wire.monstersAlive = 0;
    std::array<bool, 5> seenMonsterSlots {};
    for (std::size_t i = 0; i < monsters.size(); ++i) {
        const auto &item = monsters[i]; if (!item.is_object()) return unsupported("silver_monster_state");
        const auto idText = item.value("id", std::string()); const auto id = live_silver::monsterId(idText);
        if (!id) return unsupported("silver_unknown_monster");
        const int slot = item.value("slot", item.value("idx", static_cast<int>(i)));
        const int idx = item.value("idx", slot);
        if (slot < 0 || slot >= static_cast<int>(wire.monsters.size()) || seenMonsterSlots[slot]
            || idx != slot)
            return unsupported("silver_monster_slot");
        seenMonsterSlots[slot] = true;
        wire.monsterCount = std::max(wire.monsterCount, slot + 1);
        auto &m = wire.monsters[slot]; m.idx = idx; m.id = static_cast<std::int16_t>(*id);
        m.curHp = item.value("hp", 0); m.maxHp = item.value("maxHp", 0); m.block = item.value("block", 0);
        m.isEscapingB = item.value("escaping", item.value("escaped", false)); m.halfDead = item.value("halfDead", false);
        m.escapeNext = item.value("escapeNext", false);
        if (!item.contains("miscInfo") || !item.at("miscInfo").is_number_integer())
            return unsupported("silver_unmapped_monster_state");
        m.miscInfo = item.at("miscInfo").get<int>();
        if (item.contains("uniquePower0") && !item.at("uniquePower0").is_number_integer())
            return unsupported("silver_unmapped_monster_state");
        if (item.contains("uniquePower1") && !item.at("uniquePower1").is_number_integer())
            return unsupported("silver_unmapped_monster_state");
        m.uniquePower0 = item.value("uniquePower0", 0);
        m.uniquePower1 = static_cast<std::int16_t>(item.value("uniquePower1", 0));
        if (idText == "Hexaghost" && !item.contains("uniquePower0"))
            return unsupported("silver_unmapped_monster_state");
        m.statusBits = item.value("statusBits", 0ULL); m.strength = item.value("strength", 0);
        m.vulnerable = item.value("vulnerable", 0); m.weak = item.value("weak", 0);
        if (*id == sts::MonsterId::AWAKENED_ONE) {
            if (m.miscInfo < 0 || m.miscInfo > 1 || (m.halfDead && m.miscInfo != 0))
                return unsupported("silver_unmapped_monster_state");
            // Java's phase-two death escapes surviving Cultists. Native
            // rebirth encodes that victory rule as MINION_LEADER; it has no
            // corresponding vanilla power object to serialize.
            if (m.miscInfo == 1)
                m.statusBits |= 1ULL << static_cast<int>(sts::MonsterStatus::MINION_LEADER);
        }
        if (runicDome) {
            for(const char *hidden:{"nextMove","moveHistory","previousMove","intent","intentDamage","uniquePower0","uniquePower1"})
                if(item.contains(hidden)) return unsupported("silver_runic_dome_hidden_field");
            if(m.miscInfo!=0) return unsupported("silver_runic_dome_hidden_field");
        } else {
        int nextMove = item.value("nextMove", 0);
        // Java exposes its history oldest-to-newest as move bytes.  Native
        // Monster stores current-to-previous MonsterMoveId values.  Translate
        // every byte explicitly; copying Java bytes as native IDs silently
        // changes monster behavior whenever the enum layouts differ.
        if (item.contains("moveHistory") && item.at("moveHistory").is_array()) {
            const auto &history = item.at("moveHistory");
            if (history.empty() || history.size() > 2) return unsupported("silver_unmapped_move");
            for (std::size_t j = 0; j < history.size(); ++j) {
                if (!history[j].is_number_integer()) return unsupported("silver_unmapped_move");
                const auto move = live_silver::monsterMove(idText,
                    history[history.size() - 1 - j].get<int>());
                if (!move) return unsupported("silver_unmapped_move");
                m.moveHistory[j] = static_cast<std::int16_t>(*move);
            }
        } else if (nextMove >= 0 && item.contains("nextMove")) {
            const auto move = live_silver::monsterMove(idText, nextMove);
            if (!move) return unsupported("silver_unmapped_move");
            m.moveHistory[0] = static_cast<std::int16_t>(*move);
            const int previous = item.value("previousMove", 0);
            if (item.contains("previousMove")) {
                const auto oldMove = live_silver::monsterMove(idText, previous);
                if (!oldMove) return unsupported("silver_unmapped_move");
                m.moveHistory[1] = static_cast<std::int16_t>(*oldMove);
            }
        } else if (m.curHp > 0 && !item.value("dead", false)) return unsupported("silver_unmapped_move");
        }
        if (item.contains("powers")) {
            if (!item.at("powers").is_array()) return unsupported("silver_unmapped_monster_power");
            for (const auto &power : item.at("powers")) {
                if (!power.is_object() || !power.contains("id") || !power.at("id").is_string()
                    || !power.contains("amount") || !power.at("amount").is_number_integer())
                    return unsupported("silver_unmapped_monster_power");
                const auto powerId = power.at("id").get<std::string>();
                // Vanilla markers whose mechanics are already represented
                // by native monster phase/move state, not status bits.
                if (powerId == "Unawakened") {
                    if (*id != sts::MonsterId::AWAKENED_ONE || m.miscInfo != 0
                        || power.value("amount", 0) != -1)
                        return unsupported("silver_unmapped_monster_power");
                    continue;
                }
                if (powerId == "Explosive") {
                    const auto move = static_cast<sts::MonsterMoveId>(m.moveHistory[0]);
                    const auto previous = static_cast<sts::MonsterMoveId>(m.moveHistory[1]);
                    const int turnsLeft = move == sts::MonsterMoveId::EXPLODER_EXPLODE ? 1
                        : move == sts::MonsterMoveId::EXPLODER_SLAM
                            ? (previous == sts::MonsterMoveId::EXPLODER_SLAM ? 2 : 3) : 0;
                    if (*id != sts::MonsterId::EXPLODER || turnsLeft == 0
                        || power.value("amount", 0) != turnsLeft)
                        return unsupported("silver_unmapped_monster_power");
                    continue;
                }
                const auto mapped = live_silver::monsterStatus(powerId);
                if (!mapped) return unsupported("silver_unmapped_monster_power");
                if ((*mapped == sts::MonsterStatus::VULNERABLE
                        || *mapped == sts::MonsterStatus::WEAK || *mapped == sts::MonsterStatus::RITUAL)
                    && (!power.contains("justApplied") || !power.at("justApplied").is_boolean()))
                    return unsupported("silver_unmapped_monster_power");
                if (powerId == "Compulsive") {
                    // ReactivePower is a boolean Java marker (amount=-1).
                    // Native's scalar counts queued reactive rolls, and is
                    // reset to zero after those actions resolve.
                    if (*id != sts::MonsterId::WRITHING_MASS || power.value("amount", 0) != -1
                        || m.uniquePower1 != 0)
                        return unsupported("silver_unmapped_monster_power");
                    setMonsterPower(m, *mapped, 0, false);
                    continue;
                }
                if (!setMonsterPower(m, *mapped, power.value("amount", 1),
                                     power.value("justApplied", false)))
                    return unsupported("silver_unmapped_monster_power");
            }
        }
        if (m.curHp > 0 && !m.isEscapingB && !m.halfDead && !item.value("dead", false)) ++wire.monstersAlive;
    }
    if (combat.contains("monsterCount")) {
        if (!combat.at("monsterCount").is_number_integer())
            return unsupported("silver_monster_slot");
        const int declaredCount = combat.at("monsterCount").get<int>();
        if (declaredCount < wire.monsterCount
            || declaredCount > static_cast<int>(wire.monsters.size()))
            return unsupported("silver_monster_slot");
        // Native encounters reserve physical positions for future summons
        // (Automaton/Collector/Reptomancer). Preserve that extent even when
        // the corresponding Java objects do not exist yet.
        wire.monsterCount = declaredCount;
    }
    if (combat.contains("monstersAlive")) {
        if (!combat.at("monstersAlive").is_number_integer()
            || combat.at("monstersAlive").get<int>() != wire.monstersAlive)
            return unsupported("silver_monster_state");
    }
    const std::string encounterText = combat.value("encounter", root.value("encounter", std::string()));
    if (!encounterText.empty()) {
        if (encounterText == "FOUR_BYRDS") return unsupported("silver_unsupported_four_byrds");
        const auto encounter = live_silver::encounterId(encounterText);
        if (!encounter) return unsupported("silver_unmapped_encounter");
        wire.encounter = static_cast<int>(*encounter);
    } else if (wire.monsterCount == 1) {
        switch (static_cast<sts::MonsterId>(wire.monsters[0].id)) {
        case sts::MonsterId::CULTIST: wire.encounter = static_cast<int>(sts::MonsterEncounter::CULTIST); break;
        case sts::MonsterId::JAW_WORM: wire.encounter = static_cast<int>(sts::MonsterEncounter::JAW_WORM); break;
        case sts::MonsterId::GREMLIN_NOB: wire.encounter = static_cast<int>(sts::MonsterEncounter::GREMLIN_NOB); break;
        default: return unsupported("silver_unmapped_encounter");
        }
    } else return unsupported("silver_unmapped_encounter");

    wire.inputState = cardSelect ? static_cast<int>(sts::InputState::CARD_SELECT)
                                 : static_cast<int>(sts::InputState::PLAYER_NORMAL);
    if (combat.value("resolving", false)) return unsupported("silver_unstable_boundary");
    if (cardSelect) {
        const auto taskText = selectionIt->value("task", std::string());
        const auto task = live_silver::cardSelectTask(taskText);
        if (!task) return unsupported("silver_unmapped_selection_task");
        wire.cardSelect.task = static_cast<std::int16_t>(*task);
        wire.cardSelect.canPickZero = selectionIt->value("canPickZero", false);
        wire.cardSelect.canPickAnyNumber = selectionIt->value("canPickAnyNumber", false);
        wire.cardSelect.pickCount = selectionIt->value("pickCount", 0);
        wire.cardSelect.data0 = selectionIt->value("data0", 0);
        wire.cardSelect.setCostToZero = selectionIt->value("setCostToZero", true);
        wire.cardSelect.drawAfter = selectionIt->value("drawAfter", 0);
        for (const auto *field : {"drawsAfter", "blocksAfter"}) {
            const auto amounts = selectionIt->find(field);
            if (amounts != selectionIt->end() && (!amounts->is_array() || amounts->size() > 128
                    || std::any_of(amounts->begin(), amounts->end(), [](const auto &n) { return !n.is_number_integer(); })))
                return unsupported("silver_card_reward_pending_actions");
        }
        wire.cardSelect.damageAllBeforeBlocks = selectionIt->value("damageAllBeforeBlocks", 0);
        wire.cardSelect.drawsAfter = selectionIt->value("drawsAfter", std::vector<int>{});
        wire.cardSelect.blocksAfter = selectionIt->value("blocksAfter", std::vector<int>{});
        const auto continuation = selectionIt->value("continuation", std::string());
        if (((wire.cardSelect.damageAllBeforeBlocks != 0 || !wire.cardSelect.drawsAfter.empty() || !wire.cardSelect.blocksAfter.empty())
                && selectionIt->value("origin", std::string()) != "CARD_REWARD")
            || (wire.cardSelect.damageAllBeforeBlocks != 0 && (wire.cardSelect.damageAllBeforeBlocks != 52
                || *task != sts::CardSelectTask::CODEX || continuation != "codex_end_turn"))
            || wire.cardSelect.drawsAfter.size() + wire.cardSelect.blocksAfter.size() + (wire.cardSelect.damageAllBeforeBlocks > 0) > 128
            || (!wire.cardSelect.drawsAfter.empty() && (wire.cardSelect.drawAfter != 0
                || *task != sts::CardSelectTask::DISCOVERY || continuation != "toolbox_draw"))
            || (!wire.cardSelect.blocksAfter.empty() && (*task != sts::CardSelectTask::CODEX || continuation != "codex_end_turn"))
            || std::any_of(wire.cardSelect.drawsAfter.begin(), wire.cardSelect.drawsAfter.end(), [](int n) { return n < 1 || n > 10; })
            || std::any_of(wire.cardSelect.blocksAfter.begin(), wire.cardSelect.blocksAfter.end(), [](int n) { return n < 0 || n > 999; }))
            return unsupported("silver_card_reward_pending_actions");
        if (wire.cardSelect.drawAfter < 0 || wire.cardSelect.drawAfter > 10
            || (wire.cardSelect.drawAfter > 0 && (*task != sts::CardSelectTask::DISCOVERY
                || selectionIt->value("origin", std::string()) != "CARD_REWARD"
                || selectionIt->value("continuation", std::string()) != "toolbox_draw"
                || wire.cardSelect.setCostToZero || wire.cardSelect.canPickZero || wire.cardSelect.data0 != 1)))
            return unsupported("silver_card_reward_pending_actions");
        wire.cardSelect.selectedBits = selectionIt->value("selectedBits", 0);
        const auto origin = selectionIt->value("origin", std::string());
        if (origin == "GRID" || origin == "HAND_SELECT") {
            const auto source = liveSingleSelectionSource(*task, origin);
            std::map<std::string, int> choices;
            const bool multiForethought = *task == sts::CardSelectTask::FORETHOUGHT && wire.cardSelect.canPickAnyNumber;
            if (!source || !liveSingleChoices(*selectionIt, choices, multiForethought))
                return unsupported("silver_selection_live_choices");
            std::vector<CardRecord> candidates;
            if (*source == silver_bridge::CardSource::HAND) candidates = hand;
            else appendGenericCards(draw, candidates);
            std::set<std::string> expected;
            for (const auto &card : candidates) {
                const auto type = sts::CardInstance(static_cast<sts::CardId>(card.wire.id)).getType();
                if ((*task == sts::CardSelectTask::SECRET_TECHNIQUE && type != sts::CardType::SKILL)
                    || (*task == sts::CardSelectTask::SECRET_WEAPON && type != sts::CardType::ATTACK)) continue;
                expected.insert(card.uuid);
            }
            if (expected.size() != choices.size()) return unsupported("silver_selection_live_choices");
            if (multiForethought) for (std::size_t i = 0; i < hand.size(); ++i) {
                const auto found = choices.find(hand[i].uuid);
                if (found == choices.end() || found->second != static_cast<int>(i) + 1)
                    return unsupported("silver_selection_live_choices");
            }
            for (const auto &[uuid, index] : choices)
                if (!expected.count(uuid)) return unsupported("silver_selection_live_choices");
        }
        const auto options = selectionIt->value("cards", json::array());
        if (!options.is_array() || options.size() > wire.cardSelect.cards.size()) return unsupported("silver_unmapped_selection_task");
        const bool offer = *task == sts::CardSelectTask::DISCOVERY || *task == sts::CardSelectTask::CODEX;
        if (offer && options.size() != wire.cardSelect.cards.size())
            return unsupported("silver_card_reward_option_state");
        if (*task == sts::CardSelectTask::DISCOVERY
            && (wire.cardSelect.data0 < 1 || wire.cardSelect.data0 > 2
                || wire.cardSelect.canPickAnyNumber
                || wire.cardSelect.pickCount != 1
                || wire.cardSelect.selectedBits != 0))
            return unsupported("silver_card_reward_selection_state");
        std::set<sts::CardId> offeredIds;
        for (std::size_t i = 0; i < options.size(); ++i) {
            try {
                const std::string cardName = options[i].is_string() ? options[i].get<std::string>() : options[i].value("id", std::string());
                const auto cardId = json(cardName).get<sts::CardId>();
                if (isOffColorIroncladCard(cardId)) return unsupported("silver_off_color_card");
                if (offer && (!options[i].is_string() || cardId == sts::CardId::INVALID
                        || !offeredIds.insert(cardId).second))
                    return unsupported("silver_card_reward_option_state");
                wire.cardSelect.cards[i] = static_cast<std::int16_t>(cardId);
            } catch (...) { return unsupported("silver_unmapped_selection_task"); }
        }
    }

    // Parses one vanilla CardQueueItem projection; an empty string means ok.
    const auto parseQueueItem = [&](const json &item, silver_bridge::CardQueueItemWire &out) -> std::string {
        out.card.uniqueId = -1;
        CardRecord queueCard;
        if (item.contains("card") && item.at("card").is_null()) {
            // Vanilla end-turn autoplay items have no card object.  The
            // remaining public queue flags still belong in the retained
            // native CardQueueItem.
        } else if (item.contains("card") && parseGenericCard(item.at("card"), queueCard)) {
            if (isOffColorIroncladCard(queueCard.wire)) return "silver_off_color_card";
            auto id = context.cardIds.find(queueCard.uuid);
            if (id == context.cardIds.end()) {
                if (context.nextUniqueCardId > std::numeric_limits<std::int16_t>::max())
                    return "silver_card_identity";
                id = context.cardIds.emplace(queueCard.uuid, static_cast<std::int16_t>(context.nextUniqueCardId++)).first;
            }
            wire.nextUniqueCardId = std::max(wire.nextUniqueCardId, context.nextUniqueCardId);
            queueCard.wire.uniqueId = id->second; out.card = queueCard.wire;
        } else if (item.contains("card")) return "silver_played_card";
        out.target = item.value("target", 0);
        out.isEndTurn = item.value("isEndTurn", false);
        out.triggerOnUse = item.value("triggerOnUse", true);
        out.ignoreEnergyTotal = item.value("ignoreEnergyTotal", false);
        out.energyOnUse = item.value("energyOnUse", 0);
        out.freeToPlay = item.value("freeToPlay", false);
        out.randomTarget = item.value("randomTarget", false);
        out.autoplay = item.value("autoplay", false);
        out.regretCardCount = item.value("regretCardCount", 0);
        out.purgeOnUse = item.value("purgeOnUse", false);
        out.exhaustOnUse = item.value("exhaustOnUse", false);
        return {};
    };
    wire.curCardQueueItem.card.uniqueId = -1;
    const auto queueIt = combat.find("curCardQueueItem");
    if (decision > 0 && (queueIt == combat.end() || !queueIt->is_object()
        || !queueIt->contains("card") || queueIt->at("card").is_null()))
        return unsupported("silver_card_queue_item");
    if (queueIt != combat.end() && queueIt->is_object()) {
        if (const auto reason = parseQueueItem(*queueIt, wire.curCardQueueItem); !reason.empty())
            return unsupported(reason);
    }
    // Optional: the vanilla card queue still pending at a selection (Double
    // Tap, Duplication or Necronomicon copies), front first. Without it the
    // search root rebuilds the queue by replaying the interrupted card.
    if (const auto pendingIt = combat.find("pendingCardQueue"); pendingIt != combat.end() && !pendingIt->is_null()) {
        if (!pendingIt->is_array() || pendingIt->size() > static_cast<std::size_t>(sts::CardQueue::capacity))
            return unsupported("silver_card_queue_item");
        std::set<int> noTriggerIds;
        for (const auto &item : *pendingIt) {
            if (!item.is_object()) return unsupported("silver_card_queue_item");
            // Observed pending items replace replayed work, so incomplete or
            // coerced flags must never silently become defaults.
            for (const char *flag : {"isEndTurn", "triggerOnUse", "ignoreEnergyTotal", "freeToPlay",
                                    "randomTarget", "autoplay", "purgeOnUse", "exhaustOnUse"})
                if (!item.contains(flag) || !item.at(flag).is_boolean())
                    return unsupported("silver_card_queue_item");
            for (const char *value : {"target", "energyOnUse", "regretCardCount"})
                if (!item.contains(value) || !item.at(value).is_number_integer())
                    return unsupported("silver_card_queue_item");
            if (!item.contains("card") || item.at("target") < 0 || item.at("target") > 4
                    || item.at("energyOnUse") < 0 || item.at("energyOnUse") > 999
                    || item.at("regretCardCount") < 0 || item.at("regretCardCount") > 10
                    || item.at("isEndTurn").get<bool>() != item.at("card").is_null())
                return unsupported("silver_card_queue_item");
            silver_bridge::CardQueueItemWire parsed;
            if (const auto reason = parseQueueItem(item, parsed); !reason.empty()) return unsupported(reason);
            const bool endTurnAutoPlay = item.value("endTurnAutoPlay",false);
            if (!parsed.triggerOnUse) {
                constexpr int top = static_cast<int>(sts::RelicId::UNCEASING_TOP);
                const bool hasTop = top<64 ? (wire.player.relicBits0 & (1ULL<<(top%64))) : (wire.player.relicBits1 & (1ULL<<(top%64)));
                const bool codexOwner = cardSelect && selectionIt->value("origin",std::string())=="CARD_REWARD"
                    && selectionIt->value("continuation",std::string())=="codex_end_turn"
                    && wire.cardSelect.task==static_cast<std::int16_t>(sts::CardSelectTask::CODEX);
                const bool inHand=std::any_of(wire.hand.begin(),wire.hand.end(),[&](const auto &c){return c==parsed.card;});
                if(!codexOwner || hasTop || !endTurnAutoPlay || item.value("noTriggerOwner",std::string())!="codex_end_turn"
                        || !inHand || !noTriggerIds.insert(parsed.card.uniqueId).second
                        || (parsed.card.id!=static_cast<int>(sts::CardId::BURN) && parsed.card.id!=static_cast<int>(sts::CardId::DECAY))
                        || parsed.isEndTurn || parsed.ignoreEnergyTotal || parsed.freeToPlay || parsed.randomTarget
                        || parsed.autoplay || parsed.purgeOnUse || parsed.exhaustOnUse || parsed.target!=0 || parsed.regretCardCount!=0)
                    return unsupported("silver_card_reward_end_turn_card_queue");
            } else if (endTurnAutoPlay) return unsupported("silver_card_reward_end_turn_card_queue");
            if (!parsed.isEndTurn && !parsed.randomTarget
                    && sts::CardInstance(static_cast<sts::CardId>(parsed.card.id), parsed.card.upgraded).requiresTarget()
                    && (parsed.target >= wire.monsterCount || wire.monsters[parsed.target].idx < 0))
                return unsupported("silver_card_queue_item");
            wire.pendingCardQueue.push_back(parsed);
        }
        wire.pendingCardQueueObserved = true;
    }
    if (cardSelect && selectionIt->value("origin", std::string()) == "CARD_REWARD") {
        const auto continuation = selectionIt->value("continuation", std::string());
        const bool codex = continuation == "codex_end_turn" && wire.cardSelect.task == static_cast<std::int16_t>(sts::CardSelectTask::CODEX);
        if ((!codex && wire.cardSelect.task != static_cast<std::int16_t>(sts::CardSelectTask::DISCOVERY))
            || (!codex && continuation != "none" && continuation != "discovery_card" && continuation != "toolbox_draw")
            || wire.endTurnQueued || wire.turnHasEnded || (!codex && !wire.pendingCardQueue.empty()))
            return unsupported("silver_card_reward_pending_actions");
        if (codex) {
            if (std::any_of(wire.pendingCardQueue.begin(),wire.pendingCardQueue.end(),[](const auto &item){return item.triggerOnUse;}))
                return unsupported("silver_card_reward_end_turn_card_queue");
            constexpr int relic = static_cast<int>(sts::RelicId::NILRYS_CODEX);
            const bool hasCodex = relic < 64 ? (wire.player.relicBits0 & (1ULL << (relic % 64)))
                                            : (wire.player.relicBits1 & (1ULL << (relic % 64)));
            if (!hasCodex || !wire.cardSelect.canPickZero || wire.cardSelect.canPickAnyNumber || wire.cardSelect.pickCount != 1
                || wire.cardSelect.selectedBits != 0 || wire.cardSelect.setCostToZero || wire.cardSelect.drawAfter != 0
                || !wire.cardSelect.drawsAfter.empty() || wire.player.orbSlots != 0 || wire.player.stance != static_cast<int>(Stance::NEUTRAL))
                return unsupported("silver_card_reward_end_turn_continuation");
            if (wire.cardSelect.damageAllBeforeBlocks > 0) {
                const auto hasRelicBit = [&](sts::RelicId id) {
                    const int n = static_cast<int>(id);
                    return n < 64 ? bool(wire.player.relicBits0 & (1ULL << n)) : bool(wire.player.relicBits1 & (1ULL << (n-64)));
                };
                if (!hasRelicBit(sts::RelicId::STONE_CALENDAR))
                    return unsupported("silver_card_reward_damage_continuation");
            }
            wire.endTurnQueued = true;
        }
        if (continuation == "toolbox_draw" && ((wire.cardSelect.drawAfter < 1 && wire.cardSelect.drawsAfter.empty())
                || wire.cardSelect.setCostToZero || wire.cardSelect.canPickZero || wire.cardSelect.data0 != 1))
            return unsupported("silver_card_reward_pending_actions");
        const auto uniqueId = wire.curCardQueueItem.card.uniqueId;
        const auto inPile = [uniqueId](const auto &pile) {
            return std::any_of(pile.begin(), pile.end(), [uniqueId](const auto &card) {
                return card.uniqueId == uniqueId;
            });
        };
        const bool queuedCardInPile = inPile(wire.hand) || inPile(wire.drawPile.unknown)
            || inPile(wire.drawPile.knownTop) || inPile(wire.drawPile.knownBottom)
            || inPile(wire.discardPile.unknown) || inPile(wire.exhaustPile.unknown);
        if (continuation == "discovery_card") {
            if (limbo.size() > 1 || wire.cardSelect.data0 != 1 || queuedCardInPile
                || wire.curCardQueueItem.card.id != static_cast<std::int16_t>(sts::CardId::DISCOVERY)
                || (limbo.size() == 1 && indexedLimbo.front().uniqueId != uniqueId)
                || wire.curCardQueueItem.purgeOnUse || wire.curCardQueueItem.autoplay)
                return unsupported("silver_card_reward_pending_actions");
        } else {
            if (!limbo.empty()) return unsupported("silver_card_reward_pending_actions");
            // The producer proved that this potion offer has no interrupted
            // card cleanup. Its retained last queue item may name a completed
            // power/purged card, which is legitimately absent from all piles;
            // do not let generic card-selection replay execute it again.
            wire.curCardQueueItem = silver_bridge::CardQueueItemWire{};
            wire.curCardQueueItem.card.uniqueId = -1;
        }
    }

    wire.potionCount = std::count_if(wire.potions.begin(), wire.potions.end(), [](auto id) {
        return id != static_cast<std::int16_t>(sts::Potion::EMPTY_POTION_SLOT);
    });
    wire.version = silver_bridge::BattleStateWire::kVersion; wire.valid = true;
    wire.fullDrawOrderObserved = frozenEye; wire.intentsHidden = false;
    if(runicDome) {
        if(const auto reason=importBoundedRunicDome(combat,wire); !reason.empty()) return unsupported(reason);
    }
    wire.isolatedSearchSeed = fnv1a(entry + ":silver-live-v2");
    wire.observedGeneration = observation.value("sequence", 0ULL);
    return (result.ok = true, result);
}

SilverRootImportResult importSilverRoot(const json &observation,
                                        SilverImportContext &context) {
    const auto &root = observation.value("silverRoot", json::object());
    if (root.value("schemaVersion", 0) == 4)
        return importSilverRootGeneric(observation, context);
    return importSilverRootLegacy(observation);
}

SilverRootImportResult importSilverRoot(const json &observation) {
    thread_local SilverImportContext context;
    return importSilverRoot(observation, context);
}

std::string silverActionLabel(const silver_bridge::SemanticAction &action,
                              const silver_bridge::BattleStateWire &state) {
    if (action.type == silver_bridge::SemanticActionType::END_TURN) return "End Turn";
    if (action.type == silver_bridge::SemanticActionType::POTION) {
        std::string label = action.discardPotion ? "Discard " : "Use ";
        if (action.potionId > 0)
            label += sts::getPotionName(static_cast<sts::Potion>(action.potionId));
        else label += "Potion";
        if (action.target >= 0 && action.target < state.monsterCount)
            label += " -> Monster " + std::to_string(action.target + 1);
        return label;
    }
    if (action.type != silver_bridge::SemanticActionType::CARD) return "Card selection";
    const std::string name = action.card.id > 0
        ? sts::getCardName(static_cast<sts::CardId>(action.card.id)) : "Card";
    if (action.target >= 0 && action.target < state.monsterCount) {
        const auto id = state.monsters[action.target].id;
        return name + " -> Monster " + std::to_string(action.target + 1);
    }
    return name;
}

nlohmann::json selectedLiveAction(const silver_bridge::SemanticAction &action,
                                  const SilverImportContext &context,
                                  const nlohmann::json &observation) {
    const auto uuidForId = [&context](const std::int16_t uniqueId) -> std::string {
        for (const auto &[uuid, id] : context.cardIds)
            if (id == uniqueId) return uuid;
        return {};
    };
    const auto targetIndex = [&observation](const int silverSlot) -> std::optional<int> {
        if (silverSlot < 0) return std::nullopt;
        nlohmann::json combat = nlohmann::json::object();
        if (observation.contains("combat") && observation["combat"].is_object()) {
            combat = observation["combat"];
        } else if (observation.contains("silverRoot") && observation["silverRoot"].is_object()) {
            combat = observation["silverRoot"].value("combat", nlohmann::json::object());
        }
        const auto monsters = combat.value("monsters", nlohmann::json::array());
        if (!monsters.is_array() || silverSlot >= static_cast<int>(monsters.size())) return std::nullopt;
        int liveIndex = 0;
        for (int slot = 0; slot < static_cast<int>(monsters.size()); ++slot) {
            const auto &monster = monsters[slot];
            if (!monster.is_object()) return std::nullopt;
            if (!monster.contains("dead") || !monster["dead"].is_boolean()) return std::nullopt;
            const bool dead = monster["dead"].get<bool>();
            if (slot == silverSlot) return dead ? std::nullopt : std::optional<int>(liveIndex + 1);
            if (!dead) ++liveIndex;
        }
        return std::nullopt;
    };
    const auto targetFields = [&action, &targetIndex](nlohmann::json &result) -> bool {
        const auto compact = targetIndex(action.target);
        if (action.target >= 0 && !compact) return false;
        if (compact) result["targetIndex"] = *compact;
        return true;
    };
    using silver_bridge::SemanticActionType;
    switch (action.type) {
    case SemanticActionType::END_TURN:
        return {{"kind", "end_turn"}};
    case SemanticActionType::CARD: {
        const auto uuid = uuidForId(action.card.uniqueId);
        if (uuid.empty()) return nullptr;
        nlohmann::json result = {{"kind", "card"}, {"cardUuid", uuid}};
        if (!targetFields(result)) return nullptr;
        return result;
    }
    case SemanticActionType::POTION: {
        if (action.potionSlot < 0) return nullptr;
        nlohmann::json result = {{"kind", "potion"},
                                 {"potionSlot", action.potionSlot + 1},
                                 {"discard", action.discardPotion}};
        if (!action.discardPotion && !targetFields(result)) return nullptr;
        return result;
    }
    case SemanticActionType::MULTI_CARD_SELECT: {
        // MCPTheSpire exposes a hand selector as repeated choose calls plus a
        // final Proceed. Silver has already searched the complete private
        // transaction; lower only the next still-unselected member of that
        // final subset, or Proceed when the subset is complete.
        nlohmann::json combat = observation.contains("combat") && observation["combat"].is_object()
            ? observation["combat"]
            : observation.value("silverRoot", nlohmann::json::object())
                  .value("combat", nlohmann::json::object());
        const auto hand = combat.value("hand", nlohmann::json::array());
        const auto cardSelect = combat.value("cardSelect", nlohmann::json::object());
        if (cardSelect.value("task", std::string()) == "FORETHOUGHT"
            && cardSelect.value("origin", std::string()) == "HAND_SELECT") {
            std::map<std::string, int> choices;
            if (action.cardSelectTask != static_cast<std::int16_t>(sts::CardSelectTask::FORETHOUGHT)
                || action.source != silver_bridge::CardSource::HAND || !liveSingleChoices(cardSelect, choices, true)
                || !hand.is_array() || hand.size() != choices.size()) return nullptr;
            for (std::size_t i = 0; i < hand.size(); ++i) {
                if (!hand[i].is_object()) return nullptr;
                const auto found = choices.find(hand[i].value("uuid", std::string()));
                if (found == choices.end() || found->second != static_cast<int>(i) + 1) return nullptr;
            }
            std::map<int, std::string> selected;
            for (const auto &card : action.selectedCards) {
                const auto uuid = uuidForId(card.uniqueId);
                const auto found = choices.find(uuid);
                if (found == choices.end() || !selected.emplace(found->second, uuid).second) return nullptr;
            }
            json uuids = json::array();
            for (const auto &[index, uuid] : selected) uuids.push_back(uuid);
            return {{"kind", "card_select"}, {"cardUuids", uuids}};
        }
        const int selectedBits = cardSelect.value("selectedBits", 0);
        for (const auto &selected : action.selectedCards) {
            const auto uuid = uuidForId(selected.uniqueId);
            if (uuid.empty()) return nullptr;
            for (std::size_t i = 0; i < hand.size(); ++i) {
                if (!hand[i].is_object() || hand[i].value("uuid", std::string()) != uuid) continue;
                if ((selectedBits & (1 << static_cast<int>(i))) == 0)
                    return {{"kind", "choose"}, {"choiceIndex", static_cast<int>(i) + 1}};
                break;
            }
        }
        return {{"kind", "proceed"}};
    }
    case SemanticActionType::SINGLE_CARD_SELECT: {
        const auto combat = observation.contains("combat") && observation["combat"].is_object()
            ? observation["combat"] : observation.value("silverRoot", json::object()).value("combat", json::object());
        const auto select = combat.value("cardSelect", json::object());
        if (!select.is_object()) return nullptr;
        const auto task = live_silver::cardSelectTask(select.value("task", std::string()));
        const auto source = task ? liveSingleSelectionSource(*task, select.value("origin", std::string())) : std::nullopt;
        if (source) {
            std::map<std::string, int> choices;
            if (action.skipCardSelect || action.cardSelectTask != static_cast<std::int16_t>(*task)
                || action.source != *source || !liveSingleChoices(select, choices)) return nullptr;
            const auto found = choices.find(uuidForId(action.card.uniqueId));
            return found == choices.end() ? json(nullptr)
                : json{{"kind", "choose"}, {"choiceIndex", found->second}};
        }
        if (!select.is_object() || select.value("origin", std::string()) != "CARD_REWARD"
            || !task || (*task != sts::CardSelectTask::DISCOVERY && *task != sts::CardSelectTask::CODEX)
            || action.cardSelectTask != static_cast<std::int16_t>(*task)
            || action.source != silver_bridge::CardSource::CARD_SELECT_OPTION)
            return nullptr;
        if (action.skipCardSelect)
            return select.value("canPickZero", false) ? json{{"kind", "skip"}} : json(nullptr);
        const auto cards = select.value("cards", json::array());
        if (!cards.is_array() || cards.size() != 3) return nullptr;
        int selected = -1;
        std::set<sts::CardId> offered;
        for (std::size_t i = 0; i < cards.size(); ++i) {
            if (!cards[i].is_string()) return nullptr;
            try {
                const auto id = cards[i].get<sts::CardId>();
                if (id == sts::CardId::INVALID || !offered.insert(id).second) return nullptr;
                if (static_cast<std::int16_t>(id) == action.optionCardId) selected = static_cast<int>(i);
            } catch (...) { return nullptr; }
        }
        return selected < 0 ? json(nullptr) : json{{"kind", "choose"}, {"choiceIndex", selected + 1}};
    }
    case SemanticActionType::INVALID:
        return nullptr;
    }
    return nullptr;
}

} // namespace one_combat::advisor
