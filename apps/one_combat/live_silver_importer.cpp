#include "live_silver_importer.h"

#include <algorithm>
#include <cstdint>
#include <cstdlib>
#include <stdexcept>
#include <map>
#include <set>
#include <sstream>
#include <unordered_map>
#include <limits>
#include <iterator>
#include <optional>
#include <utility>

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
#include "combat/PublicDamageBelief.h"
#include "combat/Monster.h"
#include "combat/BattleContext.h"
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
    if (origin == "HAND_SELECT" && (task == sts::CardSelectTask::WARCRY || task == sts::CardSelectTask::FORETHOUGHT || task == sts::CardSelectTask::EXHAUST_ONE || task == sts::CardSelectTask::ARMAMENTS || task == sts::CardSelectTask::DUAL_WIELD || task == sts::CardSelectTask::GAMBLE || task == sts::CardSelectTask::EXHAUST_MANY))
        return silver_bridge::CardSource::HAND;
    if (origin == "GRID" && (task == sts::CardSelectTask::SECRET_TECHNIQUE || task == sts::CardSelectTask::SECRET_WEAPON))
        return silver_bridge::CardSource::DRAW;
    if (origin == "GRID" && task == sts::CardSelectTask::EXHUME) return silver_bridge::CardSource::EXHAUST;
    if (origin == "GRID" && (task == sts::CardSelectTask::HEADBUTT || task == sts::CardSelectTask::LIQUID_MEMORIES_POTION)) return silver_bridge::CardSource::DISCARD;
    return std::nullopt;
}

bool sourceSelectionOwner(sts::CardSelectTask task,sts::CardId card) {
    using T=sts::CardSelectTask;using C=sts::CardId;
    switch(task) {
        case T::WARCRY:return card==C::WARCRY || card==C::THINKING_AHEAD;
        case T::EXHAUST_ONE:return card==C::TRUE_GRIT || card==C::BURNING_PACT;
        case T::ARMAMENTS:return card==C::ARMAMENTS;
        case T::DUAL_WIELD:return card==C::DUAL_WIELD;
        case T::EXHUME:return card==C::EXHUME;
        case T::HEADBUTT:return card==C::HEADBUTT;
        case T::FORETHOUGHT:return card==C::FORETHOUGHT;
        case T::EXHAUST_MANY:return card==C::PURITY;
        case T::SECRET_TECHNIQUE:return card==C::SECRET_TECHNIQUE;
        case T::SECRET_WEAPON:return card==C::SECRET_WEAPON;
        case T::DISCOVERY:return card==C::DISCOVERY;
        default:return false;
    }
}

bool liveSingleChoices(const json &selection, std::map<std::string, int> &choices, bool multiForethought = false) {
    if (selection.value("selectedBits", -1) != 0) return false;
    if (multiForethought) {
        const auto task = selection.value("task", std::string());
        const auto count = selection.value("pickCount", 0);
        const std::string owner = task == "FORETHOUGHT" ? "com.megacrit.cardcrawl.actions.unique.ForethoughtAction"
            : task == "GAMBLE" ? "com.megacrit.cardcrawl.actions.unique.GamblingChipAction"
            : task == "EXHAUST_MANY" ? "com.megacrit.cardcrawl.actions.common.ExhaustAction" : "";
        if (owner.empty() || (task == "EXHAUST_MANY" ? count != 3 && count != 5 && count != 99 : count != 99)
            || !selection.value("canPickZero", false)
            || !selection.value("canPickAnyNumber", false) || selection.value("selectedCount", -1) != 0
            || selection.value("actionClass", std::string()) != owner) return false;
    } else if (selection.value("task", std::string()) == "LIQUID_MEMORIES_POTION") {
        if ((selection.value("pickCount", 0) != 1 && selection.value("pickCount", 0) != 2)
                || selection.value("canPickZero", true) || selection.value("canPickAnyNumber", true)
                || selection.value("selectedCount", -1) != 0 || selection.value("optional",true)
                || !selection.value("setCostToZero",false) || selection.value("newCost",-1) != 0
                || selection.value("actionClass",std::string()) != "com.megacrit.cardcrawl.actions.common.BetterDiscardPileToHandAction") return false;
    } else if (selection.value("pickCount", 0) != 1 || selection.value("canPickZero", true)
        || selection.value("canPickAnyNumber", true)) return false;
    const auto list = selection.value("liveChoices", json::array());
    if (!list.is_array() || list.empty()
            || (selection.value("task",std::string()) == "LIQUID_MEMORIES_POTION"
                && list.size() <= static_cast<std::size_t>(selection.value("pickCount",0)))) return false;
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
    // exposes negative values, and Mode Shift goes negative when a hit crosses
    // the threshold (TheGuardian.damage subtracts the HP lost; the queued shift
    // is checked against the pending tail).  Other negative numeric powers are
    // not a representable Java/native state and must fail closed.
    if (value < 0 && status != sts::MonsterStatus::STRENGTH && status != sts::MonsterStatus::MODE_SHIFT
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

// STS_IMPORTER_HIGH_RELIC_FIX: unset/1 (default) = relics with enum index >= 128
// get no combat relic bit (the combat Player has 128 bits and no combat code
// reads them); 0 = legacy aliasing, where the out-of-range shift set the bit of
// relic index - 64 (e.g. Thread and Needle -> Strike Dummy, Maw Bank -> Wrist Blade).
bool highRelicFix() {
    const char *value = std::getenv("STS_IMPORTER_HIGH_RELIC_FIX");
    if (!value || !*value || std::string(value) == "1") return true;
    if (std::string(value) == "0") return false;
    throw std::runtime_error("STS_IMPORTER_HIGH_RELIC_FIX must be 0 or 1");
}

// STS_IMPORTER_PEN_NIB_PENDING_FIX: unset/1 (default) = Pen Nib at counter 9
// with its PenNibPower still queued (a pending BUFF_PLAYER Pen Nib, no Pen Nib
// power yet) imports without the Pen Nib status bit, as native holds it until
// the queued BuffPlayer runs (live parity problem 54, seed 111200445: Headbutt
// armed Pen Nib behind its grid); 0 = legacy, where the counter sentinel set
// the bit at once.
bool penNibPendingFix() {
    const char *value = std::getenv("STS_IMPORTER_PEN_NIB_PENDING_FIX");
    if (!value || !*value || std::string(value) == "1") return true;
    if (std::string(value) == "0") return false;
    throw std::runtime_error("STS_IMPORTER_PEN_NIB_PENDING_FIX must be 0 or 1");
}

// STS_IMPORTER_ESCAPING_MONSTER_FIX: unset/1 (default) = a monster that Java
// reports dead (isDeadOrEscaped) with HP left, not half dead and not yet
// "escaping" (the escape animation is still running) is imported as escaping;
// 0 = legacy, where it stayed a targetable live monster natively while the
// live target list had already dropped it (silver_live_action_lowering).
bool escapingMonsterFix() {
    const char *value = std::getenv("STS_IMPORTER_ESCAPING_MONSTER_FIX");
    if (!value || !*value || std::string(value) == "1") return true;
    if (std::string(value) == "0") return false;
    throw std::runtime_error("STS_IMPORTER_ESCAPING_MONSTER_FIX must be 0 or 1");
}

// STS_IMPORTER_BACK_ATTACK_FIX: unset/1 (default) = Spire Shield/Spear's
// BackAttack marker (Java AbstractMonster.applyBackAttack: the monster behind
// the Surrounded player) sets native lastTargetedMonster to the monster the
// player faces; 0 = legacy, BackAttack is silver_unmapped_monster_power.
bool backAttackFix() {
    const char *value = std::getenv("STS_IMPORTER_BACK_ATTACK_FIX");
    if (!value || !*value || std::string(value) == "1") return true;
    if (std::string(value) == "0") return false;
    throw std::runtime_error("STS_IMPORTER_BACK_ATTACK_FIX must be 0 or 1");
}

// STS_SILVER_STASIS_RETURN_QUEUE: unset/1 (default) = a Bronze Orb killed by
// a source card queues StasisPower.onDeath's MakeTempCardInHandAction behind
// it; native returnStasisCard puts the card in hand at the death, so the
// importer folds it into the hand (the producer's STASIS_RETURN, problem 88);
// 0 = legacy refusal (silver_unmapped_stasis).
bool stasisReturnQueue() {
    const char *value = std::getenv("STS_SILVER_STASIS_RETURN_QUEUE");
    if (!value || !*value || std::string(value) == "1") return true;
    if (std::string(value) == "0") return false;
    throw std::runtime_error("STS_SILVER_STASIS_RETURN_QUEUE must be 0 or 1");
}

// STS_SILVER_SPIRE_DEATH_QUEUE: unset/1 (default) = a Spire Shield/Spear that
// died to a source card queues RemoveSpecificPowerAction(player, "Surrounded")
// (and the survivor's "BackAttack") behind it (SpireShield/SpireSpear.die());
// native removes Surrounded at the death, so the importer folds both, and a
// dead Spire monster's leftover BackAttack marker is ignored (problem 81);
// 0 = legacy refusals (silver_selection_pending_actions / silver_back_attack_facing).
bool spireDeathQueue() {
    const char *value = std::getenv("STS_SILVER_SPIRE_DEATH_QUEUE");
    if (!value || !*value || std::string(value) == "1") return true;
    if (std::string(value) == "0") return false;
    throw std::runtime_error("STS_SILVER_SPIRE_DEATH_QUEUE must be 0 or 1");
}

// STS_IMPORTER_CENTENNIAL_USED_FIX: unset/1 (default) = Centennial Puzzle
// needs the producer's usedThisCombat and gets no relic bit once it fired, as
// native clears the bit on its first HP loss; 0 = legacy, the bit stays set and
// every later root expects another free 3-card draw.
bool centennialUsedFix() {
    const char *value = std::getenv("STS_IMPORTER_CENTENNIAL_USED_FIX");
    if (!value || !*value || std::string(value) == "1") return true;
    if (std::string(value) == "0") return false;
    throw std::runtime_error("STS_IMPORTER_CENTENNIAL_USED_FIX must be 0 or 1");
}

// STS_IMPORTER_MINION_LEADER_FIX: unset/1 (default) = the importer sets the
// native MINION_LEADER victory marker on Gremlin Leader, Reptomancer, The
// Collector and Bronze Automaton, as their native preBattleAction does. Java
// has no power for it (die() makes the other monsters escape or die), so
// imported states lacked it and killing the leader left the fight UNDECIDED;
// 0 = legacy import without the marker.
// STS_SILVER_LEADER_ESCAPE_PASS_THROUGH: unset/1 (default) = a Headbutt grid
// whose pending tail is GremlinLeader.die()'s Shout + Escape for every
// surviving minion is passed through with the first card (the combat ends
// after the grid whatever is picked); 0 = legacy refusal as
// silver_selection_pending_actions (live problem 72).
bool leaderEscapePassThrough() {
    const char *value = std::getenv("STS_SILVER_LEADER_ESCAPE_PASS_THROUGH");
    if (!value || !*value || std::string(value) == "1") return true;
    if (std::string(value) == "0") return false;
    throw std::runtime_error("STS_SILVER_LEADER_ESCAPE_PASS_THROUGH must be 0 or 1");
}

bool minionLeaderFix() {
    const char *value = std::getenv("STS_IMPORTER_MINION_LEADER_FIX");
    if (!value || !*value || std::string(value) == "1") return true;
    if (std::string(value) == "0") return false;
    throw std::runtime_error("STS_IMPORTER_MINION_LEADER_FIX must be 0 or 1");
}

// STS_IMPORTER_LAGAVULIN_SLEEP_FIX: unset/1 (default) = outside Runic Dome a
// Lagavulin whose public intent is IDLE (5) is imported ASLEEP; 0 = legacy
// import without ASLEEP (native then treats it as awake and stunned).
bool lagavulinSleepFix() {
    const char *value = std::getenv("STS_IMPORTER_LAGAVULIN_SLEEP_FIX");
    if (!value || !*value || std::string(value) == "1") return true;
    if (std::string(value) == "0") return false;
    throw std::runtime_error("STS_IMPORTER_LAGAVULIN_SLEEP_FIX must be 0 or 1");
}

// STS_SELECTION_TOY_HEAL_FIX: unset/1 (default) = a live selection whose
// public pending tail holds Toy Ornithopter's queued potion heal (tested for
// Gambler's Brew) imports with that heal; 0 = legacy refusal as
// silver_selection_pending_actions.
bool selectionToyHealFix() {
    const char *value = std::getenv("STS_SELECTION_TOY_HEAL_FIX");
    if (!value || !*value || std::string(value) == "1") return true;
    if (std::string(value) == "0") return false;
    throw std::runtime_error("STS_SELECTION_TOY_HEAL_FIX must be 0 or 1");
}

// STS_SILVER_HALF_DEAD_SET_MOVE_QUEUE: unset/1 (default) = a source-card
// selection whose pending tail holds a half-dead Darkling's queued
// SetMoveAction (Headbutt killing a Darkling) imports it as a native
// SetMonsterMove; 0 = legacy refusal as silver_selection_pending_actions.
bool halfDeadSetMoveQueue() {
    const char *value = std::getenv("STS_SILVER_HALF_DEAD_SET_MOVE_QUEUE");
    if (!value || !*value || std::string(value) == "1") return true;
    if (std::string(value) == "0") return false;
    throw std::runtime_error("STS_SILVER_HALF_DEAD_SET_MOVE_QUEUE must be 0 or 1");
}

// STS_SILVER_AWAKENED_REBIRTH_QUEUE: unset/1 (default) = a source-card
// selection whose pending tail holds Awakened One's first-form death
// SetMoveAction(3) (Headbutt killing it, problem 90) imports it as a native
// SetMonsterMove(Rebirth), and under Runic Dome accepts the row from before
// that duplicate setter; 0 = legacy refusal as silver_selection_pending_actions.
bool awakenedRebirthQueue() {
    const char *value = std::getenv("STS_SILVER_AWAKENED_REBIRTH_QUEUE");
    if (!value || !*value || std::string(value) == "1") return true;
    if (std::string(value) == "0") return false;
    throw std::runtime_error("STS_SILVER_AWAKENED_REBIRTH_QUEUE must be 0 or 1");
}

// STS_SILVER_DARKLING_DOME_REGROW_QUEUE: unset/1 (default) = under Runic
// Dome, a source-card selection whose pending tail holds a half-dead
// Darkling's duplicate SetMoveAction(4) (Headbutt killing it, problem 104)
// imports the row from before that duplicate setter; 0 = legacy refusal as
// silver_selection_pending_actions / silver_runic_dome_incomplete_history.
bool darklingDomeRegrowQueue() {
    const char *value = std::getenv("STS_SILVER_DARKLING_DOME_REGROW_QUEUE");
    if (!value || !*value || std::string(value) == "1") return true;
    if (std::string(value) == "0") return false;
    throw std::runtime_error("STS_SILVER_DARKLING_DOME_REGROW_QUEUE must be 0 or 1");
}

// STS_SILVER_LAGAVULIN_OPEN_QUEUE: unset/1 (default) = a source-card
// selection whose pending tail holds the ChangeStateAction("OPEN") of a
// Lagavulin woken by the hit folds its Metallicize reduction into the
// imported monster, as native applies it at the hit; 0 = legacy refusal as
// silver_selection_pending_actions.
bool lagavulinOpenQueue() {
    const char *value = std::getenv("STS_SILVER_LAGAVULIN_OPEN_QUEUE");
    if (!value || !*value || std::string(value) == "1") return true;
    if (std::string(value) == "0") return false;
    throw std::runtime_error("STS_SILVER_LAGAVULIN_OPEN_QUEUE must be 0 or 1");
}

// STS_SILVER_SLIME_SPLIT_QUEUE: unset/1 (default) = a source-card selection
// whose pending tail holds a large slime's or Slime Boss's queued split
// SetMoveAction (the hit took it to half HP) folds it into the imported
// monster's move history, as native sets the split at the hit; 0 = legacy
// refusal as silver_selection_pending_actions.
bool slimeSplitQueue() {
    const char *value = std::getenv("STS_SILVER_SLIME_SPLIT_QUEUE");
    if (!value || !*value || std::string(value) == "1") return true;
    if (std::string(value) == "0") return false;
    throw std::runtime_error("STS_SILVER_SLIME_SPLIT_QUEUE must be 0 or 1");
}

// STS_SILVER_HEX_DAZED_QUEUE: unset/1 (default) = a pending tail holding
// Hex's queued Dazed (HexPower.onUseCard for a non-Attack, e.g. Discovery's
// choice under Hex) imports it as a native MakeTempCardInDrawPile(Dazed);
// 0 = legacy refusal (silver_selection_pending_actions).
bool hexDazedQueue() {
    const char *value = std::getenv("STS_SILVER_HEX_DAZED_QUEUE");
    if (!value || !*value || std::string(value) == "1") return true;
    if (std::string(value) == "0") return false;
    throw std::runtime_error("STS_SILVER_HEX_DAZED_QUEUE must be 0 or 1");
}

// STS_SILVER_VOID_ENERGY_QUEUE: unset/1 (default) = a pending tail holding
// Void's queued LoseEnergyAction(1) (VoidCard.triggerWhenDrawn, e.g. Warcry
// drawing Void before its put-on-top choice) folds the loss into the imported
// energy, as native CardManager::draw applies it at the draw; 0 = legacy
// refusal (silver_selection_pending_actions).
bool voidEnergyQueue() {
    const char *value = std::getenv("STS_SILVER_VOID_ENERGY_QUEUE");
    if (!value || !*value || std::string(value) == "1") return true;
    if (std::string(value) == "0") return false;
    throw std::runtime_error("STS_SILVER_VOID_ENERGY_QUEUE must be 0 or 1");
}

// STS_SILVER_CARD_REWARD_PUBLIC_ACTIONS: unset/1 (default) = a potion's
// Discovery card reward (Attack/Skill/Power/Colorless Potion) whose typed
// public tail (Toy Ornithopter's heal) is queued behind the choice imports
// that tail; 0 = legacy refusal (silver_selection_pending_actions).
bool cardRewardPublicActions() {
    const char *value = std::getenv("STS_SILVER_CARD_REWARD_PUBLIC_ACTIONS");
    if (!value || !*value || std::string(value) == "1") return true;
    if (std::string(value) == "0") return false;
    throw std::runtime_error("STS_SILVER_CARD_REWARD_PUBLIC_ACTIONS must be 0 or 1");
}

// STS_SILVER_LETHAL_REACTION_QUEUE: unset/1 (default) = a source-card
// selection whose hit killed a Byrd or Shelled Parasite still carries the
// queued Flight / Plated Armor ReducePowerAction; it folds into the dead
// monster like a living one (native applies the loss at the hit); 0 = legacy
// refusal (silver_selection_pending_actions).
bool lethalReactionQueue() {
    const char *value = std::getenv("STS_SILVER_LETHAL_REACTION_QUEUE");
    if (!value || !*value || std::string(value) == "1") return true;
    if (std::string(value) == "0") return false;
    throw std::runtime_error("STS_SILVER_LETHAL_REACTION_QUEUE must be 0 or 1");
}

// STS_SILVER_BYRD_GROUNDING_QUEUE: unset/1 (default) = a source-card
// selection whose non-lethal hit took a living Byrd's Flight from 1 to 0
// still carries the queued ReducePowerAction (Java grounds the Byrd only when
// it runs); it folds into the Byrd as native applies it at the hit: Flight
// removed, any deferred Runic Dome roll cancelled, Stunned next (live problem
// 80); 0 = legacy refusal (silver_selection_pending_actions).
bool byrdGroundingQueue() {
    const char *value = std::getenv("STS_SILVER_BYRD_GROUNDING_QUEUE");
    if (!value || !*value || std::string(value) == "1") return true;
    if (std::string(value) == "0") return false;
    throw std::runtime_error("STS_SILVER_BYRD_GROUNDING_QUEUE must be 0 or 1");
}

// STS_SILVER_PLATED_ARMOR_REMOVAL_QUEUE: unset/1 (default) = a queued
// Plated Armor reduction from 1 on a monster other than Shelled Parasite
// (whose stun stays unsupported), e.g. Donu after Headbutt, removes the power
// as native does at the hit; 0 = legacy refusal (silver_selection_pending_actions).
bool platedArmorRemovalQueue() {
    const char *value = std::getenv("STS_SILVER_PLATED_ARMOR_REMOVAL_QUEUE");
    if (!value || !*value || std::string(value) == "1") return true;
    if (std::string(value) == "0") return false;
    throw std::runtime_error("STS_SILVER_PLATED_ARMOR_REMOVAL_QUEUE must be 0 or 1");
}

// STS_IMPORTER_THIEF_GOLD_FIX: unset/1 (default) = a Looter or Mugger holding
// stolen gold (Java stolenGold, native miscInfo) sets miscBits bit 0, the
// native stolen-gold check that Java has no field for; without it Silver's
// effectiveGold ignores the gold a kill returns. 0 = legacy, bit only from an
// explicit combat.miscBits.
bool thiefGoldFix() {
    const char *value = std::getenv("STS_IMPORTER_THIEF_GOLD_FIX");
    if (!value || !*value || std::string(value) == "1") return true;
    if (std::string(value) == "0") return false;
    throw std::runtime_error("STS_IMPORTER_THIEF_GOLD_FIX must be 0 or 1");
}

// STS_IMPORTER_ORANGE_PELLETS_FIX: unset/1 (default) = import the live mod's
// combat.orangePelletsCardTypesPlayed (bit 0 Attack, 1 Skill, 2 Power), read
// from the OrangePellets relic's static ATTACK/SKILL/POWER flags (live seed
// 111200414, problem 32: the older mod looked for a nonexistent power and never
// exported it). 0 = legacy, the field is ignored and always imports as 0.
bool orangePelletsFix() {
    const char *value = std::getenv("STS_IMPORTER_ORANGE_PELLETS_FIX");
    if (!value || !*value || std::string(value) == "1") return true;
    if (std::string(value) == "0") return false;
    throw std::runtime_error("STS_IMPORTER_ORANGE_PELLETS_FIX must be 0 or 1");
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
        if (item.contains("occupantGeneration")) {
            if (!item.at("occupantGeneration").is_number_integer()
                || item.at("occupantGeneration") < 1 || item.at("occupantGeneration") > 1000000)
                return unsupported("silver_monster_occupant_binding");
            monster.occupantGeneration = item.at("occupantGeneration").get<std::uint32_t>();
        }
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

// STS_IMPORTER_RUNIC_DOME_WIRE_FIX: unset/1 (default) = read the live mod's
// Runic Dome rows as the mod writes them (live seeds 111194466/111194467,
// where every first-turn Dome root was refused):
// - the pending roll of an initial occupant that has not executed yet is its
//   combat-start roll, imported at global turn 0 like the native one
//   (monsterTurnNumber 1 either way); the mod stamps it with
//   GameActionManager.turn, which already reads 1
//   (silver_runic_dome_occupant_schema);
// - Gson omits null members, so a missing knownNextMove/knownRollPredecessor
//   of a monster that carries them is null (silver_runic_dome_known_next_schema).
// 0 = legacy strict reading.
bool domeWireFix() {
    const char *value = std::getenv("STS_IMPORTER_RUNIC_DOME_WIRE_FIX");
    if (!value || !*value || std::string(value) == "1") return true;
    if (std::string(value) == "0") return false;
    throw std::runtime_error("STS_IMPORTER_RUNIC_DOME_WIRE_FIX must be 0 or 1");
}

// STS_IMPORTER_RUNIC_DOME_REACTIVE_FIX: unset/1 (default) = a Writhing Mass
// hit by an interrupted source card (Headbutt GRID) under Runic Dome keeps the
// queued Reactive reroll folded from the observed pending queue (live seed
// 111200416, problem 34). Native defers that reroll under hidden intents with
// the inputs of the moment the queued action runs, as Java's RollMoveAction
// rolls then; the mod's history has not counted it yet. 0 = legacy refusal
// (silver_runic_dome_monster_power_domain).
bool domeReactiveFix() {
    const char *value = std::getenv("STS_IMPORTER_RUNIC_DOME_REACTIVE_FIX");
    if (!value || !*value || std::string(value) == "1") return true;
    if (std::string(value) == "0") return false;
    throw std::runtime_error("STS_IMPORTER_RUNIC_DOME_REACTIVE_FIX must be 0 or 1");
}

// Runic Dome history for the Act 4 fights (Corrupt Heart, Spire Shield and
// Spear; Philipp 2026-10-21). Their every turn ends in RollMoveAction, but only
// one roll per three-move cycle is random. =0 restores the legacy refusal of
// Act 4 under Runic Dome (silver_runic_dome_encounter_domain).
bool domeAct4Fix() {
    const char *value = std::getenv("STS_IMPORTER_RUNIC_DOME_ACT4");
    if (!value || !*value || std::string(value) == "1") return true;
    if (std::string(value) == "0") return false;
    throw std::runtime_error("STS_IMPORTER_RUNIC_DOME_ACT4 must be 0 or 1");
}

// STS_IMPORTER_RUNIC_DOME_REBIRTH_ROLL: unset/1 (default) accepts Awakened One's
// pending roll made right after its Rebirth executed with rollHp 0: the REBIRTH
// changeState queues the heal behind takeTurn's RollMoveAction, and phase two's
// first move (Dark Echo) does not depend on HP (live problem 91, seed 111200541).
// =0 restores the refusal (silver_runic_dome_history_gap).
// STS_IMPORTER_NECRONOMICON_READY_FIX: unset/1 (default) = vanilla's private
// Necronomicon.activated is true while the copy is still available this turn,
// so it imports as !haveUsedNecronomiconThisTurn (problem 96); 0 restores the
// legacy reading, which imported the ready relic as spent.
bool necronomiconReadyFix() {
    const char *value = std::getenv("STS_IMPORTER_NECRONOMICON_READY_FIX");
    if (!value || !*value || std::string(value) == "1") return true;
    if (std::string(value) == "0") return false;
    throw std::runtime_error("STS_IMPORTER_NECRONOMICON_READY_FIX must be 0 or 1");
}

bool domeRebirthRollFix() {
    const char *value = std::getenv("STS_IMPORTER_RUNIC_DOME_REBIRTH_ROLL");
    if (!value || !*value || std::string(value) == "1") return true;
    if (std::string(value) == "0") return false;
    throw std::runtime_error("STS_IMPORTER_RUNIC_DOME_REBIRTH_ROLL must be 0 or 1");
}

// The public result of the Act 4 roll made after `done` executions (Java
// getMove), 0 if that roll is random, or -1 if it needs an unknown last move.
int domeAct4Cycle(const std::string &id,int done,int last) {
    if(id=="CorruptHeart") {
        if(done==0) return 3;
        const int mc=(done-1)%3;
        return mc==2?4:mc==1?(last<0?-1:last==2?1:2):0;
    }
    const int mc=done%3;
    if(id=="SpireShield") return mc==2?3:mc==1?(last<0?-1:last==1?2:1):0;
    if(id=="SpireSpear") return mc==1?3:mc==0?(done==0?1:last<0?-1:last==1?2:1):0;
    return 0;
}

// A split/summon child rolls its first move in init(), before SpawnMonsterAction
// adds it to the group, so that roll's aliveCount can be 0 (live problem 63:
// the first Slime Boss child sees only the dead boss). =0 restores the legacy
// aliveCount >= 1 requirement for every row.
bool domeNewbornAliveFix() {
    const char *value = std::getenv("STS_IMPORTER_RUNIC_DOME_NEWBORN_ALIVE_FIX");
    if (!value || !*value || std::string(value) == "1") return true;
    if (std::string(value) == "0") return false;
    throw std::runtime_error("STS_IMPORTER_RUNIC_DOME_NEWBORN_ALIVE_FIX must be 0 or 1");
}

// Audited stable-slot monsters whose next roll depends on public executed history.
// Spot Weakness carries only its public attack predicate for the pending roll.
// Generators and unaudited monster lifecycles remain outside this domain.
std::string importBoundedRunicDome(const json &combat, silver_bridge::BattleStateWire &wire) {
    const auto found=combat.find("runicDomeKnowledge");
    if(found==combat.end() || !found->is_object()) return "silver_runic_dome_missing_history";
    const auto validInteger=[](const json &obj,const char *name,std::int64_t lo,std::int64_t hi) {
        return obj.contains(name) && obj.at(name).is_number_integer() && obj.at(name)>=lo && obj.at(name)<=hi;
    };
    if(!validInteger(*found,"schemaVersion",1,3) || !found->contains("complete") || !found->at("complete").is_boolean())
        return "silver_runic_dome_history_schema";
    if(!found->at("complete").get<bool>()) return "silver_runic_dome_incomplete_history";
    const bool bound=found->at("schemaVersion")==3;
    const bool multi=found->at("schemaVersion")>=2;
    json rows=multi?found->value("monsters",json()):json::array({*found});
    if(!validInteger(*found,"epoch",1,9007199254740991LL) || !rows.is_array()
            || rows.size()!=static_cast<std::size_t>(wire.monsterCount)) return "silver_runic_dome_history_schema";
    const bool act4Fight=wire.act==4 && domeAct4Fix() && ((wire.encounter==static_cast<int>(sts::MonsterEncounter::THE_HEART) && wire.monsterCount==1)
            || (wire.encounter==static_cast<int>(sts::MonsterEncounter::SHIELD_AND_SPEAR) && wire.monsterCount==2));
    if((!act4Fight && (wire.act<1 || wire.act>3)) || wire.monsterCount<1 || wire.monsterCount>5) return "silver_runic_dome_encounter_domain";
    for(int slot=0;slot<wire.monsterCount;++slot) {
        auto k=rows.at(slot);
        if(bound && k.is_object() && k.value("absent",false)) {
            if(k.size()!=3 || !validInteger(k,"slot",slot,slot) || !validInteger(k,"occupantGeneration",0,0)
                    || wire.monsters[slot].id!=static_cast<int>(sts::MonsterId::INVALID))return "silver_runic_dome_occupant_schema";
            wire.monsters[slot].occupantGeneration=0;continue;
        }
        int birthTurn=0,rollTurn=0,lastExecution=-1;bool unexecutedInitial=false,newbornRoll=false;
        if(bound) {
            if(!validInteger(k,"schemaVersion",4,4) || !validInteger(k,"historySchemaVersion",1,3)
                    || !validInteger(k,"occupantGeneration",1,1000000) || !validInteger(k,"birthGlobalTurn",0,wire.turn)
                    || !validInteger(k,"rollGlobalTurn",0,1000000) || !validInteger(k,"lastExecutionGlobalTurn",-1,wire.turn)
                    || !validInteger(k,"birthParentSlot",-1,4) || !validInteger(k,"birthParentGeneration",0,1000000)
                    || !k.contains("birthKind") || !k.at("birthKind").is_string())return "silver_runic_dome_occupant_schema";
            birthTurn=k.at("birthGlobalTurn");rollTurn=k.at("rollGlobalTurn");lastExecution=k.at("lastExecutionGlobalTurn");
            const auto kind=k.at("birthKind").get<std::string>();
            // The first roll of an initial occupant that has not executed yet is its combat-start roll.
            unexecutedInitial=kind=="initial" && lastExecution==-1 && k.contains("completedTurns") && k.at("completedTurns")==0
                && domeWireFix();
            if(unexecutedInitial && (k.at("historySchemaVersion")==1 || (k.contains("totalRolls") && k.at("totalRolls")==1))) {
                rollTurn=0;k["rollGlobalTurn"]=0;
            }
            if(rollTurn>wire.turn+1)return "silver_runic_dome_occupant_schema";
            if((kind=="initial"?(birthTurn!=0 || k.at("occupantGeneration")!=1 || k.at("birthParentSlot")!=-1 || k.at("birthParentGeneration")!=0)
                    :((kind!="split" && kind!="summon") || birthTurn<1 || k.at("birthParentSlot")==-1 || k.at("birthParentGeneration")==0))
                    || rollTurn<birthTurn || (lastExecution!=-1 && lastExecution<birthTurn))return "silver_runic_dome_occupant_schema";
            newbornRoll=kind!="initial" && rollTurn==birthTurn && domeNewbornAliveFix();
            wire.monsters[slot].occupantGeneration=k.at("occupantGeneration").get<std::uint32_t>();
            k["schemaVersion"]=k.at("historySchemaVersion");
        }
        const auto integer=[&](const char *name,std::int64_t lo,std::int64_t hi) {return validInteger(k,name,lo,hi);};
        auto &m=wire.monsters[slot];
        const bool dead=(m.curHp<=0 && !m.halfDead) || m.isEscapingB;
        if(!k.is_object() || !integer("schemaVersion",1,3) || !integer("epoch",1,9007199254740991LL) || k.at("epoch")!=found->at("epoch")
                || !k.contains("complete") || k.at("complete")!=true || !integer("completedTurns",0,9999)
                || !integer("generation",1,1000000) || !integer("slot",slot,slot)
                || !integer("pendingMoveRolls",0,255)
                || !integer("rollHp",0,999) || !integer("rollMaxHp",1,999)
                || !k.contains("monsterId") || !k.at("monsterId").is_string()
                || !k.contains("executedMoves") || !k.at("executedMoves").is_array())
            return "silver_runic_dome_history_schema";
        const int completed=k.at("completedTurns").get<int>();
        const auto &moves=k.at("executedMoves");
        const auto monsterId=k.at("monsterId").get<std::string>();
        const auto id=live_silver::monsterId(monsterId);
        const bool jaw=monsterId=="JawWorm",cultist=monsterId=="Cultist",fungi=monsterId=="FungiBeast",
            red=monsterId=="SlaverRed",blue=monsterId=="SlaverBlue",acid=monsterId=="AcidSlime_M",smallAcid=monsterId=="AcidSlime_S",
            spike=monsterId=="SpikeSlime_M",smallSpike=monsterId=="SpikeSlime_S",sentry=monsterId=="Sentry",nob=monsterId=="GremlinNob";
        const std::set<std::string> ordinary={"Centurion","Healer","Chosen","SnakePlant","Snecko","SphericGuardian",
            "Exploder","Repulsor","Maw","Nemesis","Orb Walker","GiantHead","Donu","Deca","Spiker","Serpent","SlaverBoss",
            "GremlinFat","BookOfStabbing","TimeEater","GremlinThief","GremlinWarrior","GremlinWizard",
            "GremlinTsundere","BanditBear","BanditLeader","BanditChild","Transient","WrithingMass","Champ","Byrd","Shelled Parasite","TheGuardian","Hexaghost","Lagavulin","Looter","Mugger","AwakenedOne","AcidSlime_L","SpikeSlime_L","SlimeBoss","BronzeAutomaton","BronzeOrb","GremlinLeader","Reptomancer","Dagger","TheCollector","TorchHead","FuzzyLouseNormal","FuzzyLouseDefensive","Darkling",
            "CorruptHeart","SpireShield","SpireSpear"};
        const bool slimeBoss=monsterId=="SlimeBoss",split=slimeBoss||monsterId=="AcidSlime_L"||monsterId=="SpikeSlime_L";
        const bool darkling=monsterId=="Darkling",lice=monsterId=="FuzzyLouseNormal"||monsterId=="FuzzyLouseDefensive",latent=darkling||lice;
        const bool automaton=monsterId=="BronzeAutomaton",orb=monsterId=="BronzeOrb",torch=monsterId=="TorchHead";
        const bool remaining=split||latent||automaton||orb||torch||monsterId=="GremlinLeader"||monsterId=="Reptomancer"||monsterId=="Dagger"||monsterId=="TheCollector";
        if(remaining && !bound)return "silver_runic_dome_occupant_schema";
        const bool expanded=ordinary.count(monsterId),book=monsterId=="BookOfStabbing",spiker=monsterId=="Spiker",timeEater=monsterId=="TimeEater";
        if((!multi && (!(jaw||cultist) || wire.monsterCount!=1 || k.contains("pendingAttackPredicates")))
                || !(jaw||cultist||fungi||red||blue||acid||smallAcid||spike||smallSpike||sentry||nob||expanded) || !id || m.id!=static_cast<int>(*id)
                || m.idx!=slot || (m.halfDead && monsterId!="AwakenedOne" && !darkling) || (m.isEscapingB && monsterId!="Looter" && monsterId!="Mugger") || m.escapeNext
                || (nob && !((wire.monsterCount==1 && wire.encounter==static_cast<int>(sts::MonsterEncounter::GREMLIN_NOB))
                    || (wire.monsterCount==2 && slot==1 && wire.monsters[0].id==static_cast<int>(sts::MonsterId::TASKMASTER)
                        && wire.encounter==static_cast<int>(sts::MonsterEncounter::COLOSSEUM_EVENT_NOBS)))))
            return "silver_runic_dome_encounter_domain";
        const bool heart=monsterId=="CorruptHeart",act4=heart || monsterId=="SpireShield" || monsterId=="SpireSpear";
        if(act4!=act4Fight || (act4 && slot!=(monsterId=="SpireSpear"?1:0)))
            return "silver_runic_dome_encounter_domain";
        if(monsterId=="Healer" && (wire.monsterCount!=2 || slot!=1
                || wire.monsters[0].id!=static_cast<int>(sts::MonsterId::CENTURION)))
            return "silver_runic_dome_encounter_domain";
        const bool reactive=monsterId=="WrithingMass",champ=monsterId=="Champ";
        const bool byrd=monsterId=="Byrd",shelled=monsterId=="Shelled Parasite",guardian=monsterId=="TheGuardian",hex=monsterId=="Hexaghost",laga=monsterId=="Lagavulin",thief=monsterId=="Looter" || monsterId=="Mugger",awakened=monsterId=="AwakenedOne",dynamic=byrd||shelled||guardian||hex||laga||thief||awakened||remaining||act4;
        if(bound && rollTurn>wire.turn && !reactive)return "silver_runic_dome_occupant_schema";
        if(k.at("schemaVersion")!=(dynamic?3:reactive?2:1)) return "silver_runic_dome_history_schema";
        const int pending=k.at("pendingMoveRolls").get<int>();
        if(!reactive && pending>1) return "silver_runic_dome_history_schema";
        const bool wizard=monsterId=="GremlinWizard",shield=monsterId=="GremlinTsundere";
        const bool deterministic=torch || slimeBoss || smallAcid || wizard || shield || monsterId=="GremlinThief" || monsterId=="GremlinWarrior"
                || monsterId=="BanditBear" || monsterId=="BanditLeader" || monsterId=="BanditChild" || monsterId=="Transient";
        const bool hardJaw=jaw && wire.encounter==static_cast<int>(sts::MonsterEncounter::JAW_WORM_HORDE);
        if((jaw && wire.act!=1 && !hardJaw) || ((monsterId=="Donu" || monsterId=="Deca") && (wire.monsterCount!=2
                || wire.monsters[0].id!=static_cast<int>(sts::MonsterId::DECA) || wire.monsters[1].id!=static_cast<int>(sts::MonsterId::DONU))))
            return "silver_runic_dome_encounter_domain";
        if(hardJaw && (wire.monsterCount!=3 || std::any_of(wire.monsters.begin(),wire.monsters.begin()+3,
                [](const auto &member){return member.id!=static_cast<int>(sts::MonsterId::JAW_WORM);})))
            return "silver_runic_dome_encounter_domain";
        int direct=0;
        if(thief) {
            if(!integer("pendingDirectMoveChoice",0,1) || !integer("directChoices",0,1)
                    || k.at("directChoices")!=(completed>=2?1:0)) return "silver_runic_dome_history_schema";
            direct=k.at("pendingDirectMoveChoice").get<int>();
            if(direct!=(completed==2 && !dead?1:0) || (completed>0 && pending)) return "silver_runic_dome_history_gap";
        } else if(k.contains("pendingDirectMoveChoice") || k.contains("directChoices")) return "silver_runic_dome_history_schema";
        const bool knownNext=!dead && !direct && ((deterministic && completed>0) || (dynamic && pending==0));
        if((dead || knownNext || direct)?pending!=0:(reactive?pending<1:pending!=1)) return "silver_runic_dome_history_gap";
        if(act4 && !dead && knownNext!=(domeAct4Cycle(monsterId,completed,moves.empty() || !moves.back().is_number_integer()?-1:moves.back().get<int>())!=0))
            return "silver_runic_dome_history_gap";
        if(domeWireFix()) {
            if((deterministic || dynamic) && !k.contains("knownNextMove")) k["knownNextMove"]=nullptr;
            if(dynamic && !k.contains("knownRollPredecessor")) k["knownRollPredecessor"]=nullptr;
        }
        if(deterministic || dynamic) {
            if(!k.contains("knownNextMove")) return "silver_runic_dome_known_next_schema";
            const auto &proof=k.at("knownNextMove");
            if(knownNext) {
                if(!proof.is_object() || proof.size()!=2 || !proof.contains("kind")
                        || !validInteger(proof,"move",1,guardian?7:hex?6:dynamic?4:3)
                        || (!dynamic && proof.at("kind")!=(smallAcid?"acid_slime_s_alternation":"public_deterministic_transition_v1"))
                        || (dynamic && (act4?proof.at("kind")!="act4_public_cycle":remaining?(proof.at("kind")!=(split?(slimeBoss && proof.value("move",0)!=3?"slime_boss_public_cycle":"public_split_override"):darkling?"darkling_public_regrow":"public_deterministic_transition_v1")):awakened?proof.at("kind")!="awakened_public_rebirth":thief?proof.at("kind")!="thief_public_cycle":laga?(proof.at("kind")!="public_stun_override" && proof.at("kind")!="lagavulin_awake_event" && proof.at("kind")!="lagavulin_natural_wake"):hex?proof.at("kind")!="hexaghost_activate":guardian?(proof.at("kind")!="guardian_defensive_override" && proof.at("kind")!="guardian_public_cycle")
                            :(proof.at("kind")!="public_stun_override" && proof.at("kind")!="byrd_headbutt_fly"))))
                    return "silver_runic_dome_known_next_schema";
            } else if(!proof.is_null()) return "silver_runic_dome_known_next_schema";
        } else if(k.contains("knownNextMove")) return "silver_runic_dome_known_next_schema";
        const auto generation=k.at("generation").get<int>();
        const bool generationValid=dynamic
            ? integer("totalRolls",1,1000000) && integer("knownTransitions",0,1000000)
                && generation==completed+k.at("totalRolls").get<int>()+k.at("knownTransitions").get<int>()+(thief?k.at("directChoices").get<int>():0)
            : reactive
            ? integer("totalRolls",std::max(1,completed+(dead?0:1)),1000000) && generation==completed+k.at("totalRolls").get<int>()
                && pending<=k.at("totalRolls").get<int>()-completed
            : generation>=2*completed && generation<=2*completed+1 && (dead || generation==2*completed+1);
        if((bound?(completed>wire.turn-birthTurn || (completed==0?lastExecution!=-1:lastExecution<birthTurn)
                || (!dead && !(lastExecution==wire.turn || (completed==0 && birthTurn==wire.turn)))):(dead?completed>wire.turn:completed!=wire.turn)) || !generationValid || moves.size()!=static_cast<std::size_t>(std::min(completed,2))
                || k.at("rollHp")>k.at("rollMaxHp") || k.at("rollMaxHp")!=m.maxHp)
            return "silver_runic_dome_history_gap";
        int misc=0;
        if(multi) {
            if(!integer("publicMisc",book?1:0,book?completed+1:(guardian||hex)?10000:thief?completed*(wire.ascension>=17?20:15):champ?6:wizard?3:spiker?6:automaton?5:(red||timeEater||reactive||awakened||orb)?1:0)) return "silver_runic_dome_history_schema";
            misc=k.at("publicMisc").get<int>();
            if(red && completed<2 && misc!=0) return "silver_runic_dome_history_gap";
        }
        m.moveHistory.fill(static_cast<std::int16_t>(sts::MonsterMoveId::INVALID));
        for(std::size_t i=0;i<moves.size();++i) {
            if(!moves[i].is_number_integer() || moves[i]<0 || moves[i]>(awakened?8:(champ||guardian)?7:(byrd||hex||laga)?6:5)) return "silver_runic_dome_history_schema";
            const int move=moves[i].get<int>();
            const int execution=completed-static_cast<int>(moves.size())+static_cast<int>(i);
            bool legal=smallAcid?(move==1||move==2):smallSpike?move==1:sentry?move==((slot+execution)%2==0?3:4):jaw?(execution==0&&!hardJaw?move==1:move>=1&&move<=3)
                :cultist?move==(execution==0?3:1):nob?(execution==0?move==3:move==1||move==2)
                :red?(execution==0?move==1:move==1||move==2||move==3)
                :(blue||spike)?move==1||move==4:acid?move==1||move==2||move==4:move==1||move==2;
            if(expanded) {
                if(remaining) legal=live_silver::monsterMove(monsterId,move).has_value();
                else if(awakened) legal=move==1 || move==2 || move==3 || move==5 || move==6 || move==8;
                else if(thief) legal=execution<2?move==1:move>=2 && move<=4;
                else if(laga) legal=move==1 || move==3 || move==4 || move==5 || move==6;
                else if(hex) {const int cycle[]={4,2,4,3,2,4,6};legal=move==(execution==0?5:execution==1?1:cycle[(execution-2)%7]);}
                else if(guardian) legal=move>=1 && move<=7;
                else if(monsterId=="Centurion" || monsterId=="Healer" || monsterId=="Serpent") legal=move>=1 && move<=3;
                else if(monsterId=="Chosen") legal=execution==0?move==(wire.ascension>=17?4:5):move>=1 && move<=5;
                else if(monsterId=="SnakePlant" || monsterId=="Repulsor" || monsterId=="Orb Walker" || spiker || book) legal=move==1 || move==2;
                else if(monsterId=="Snecko") legal=execution==0?move==1:move==2 || move==3;
                else if(monsterId=="SphericGuardian") legal=move==(execution==0?2:execution==1?4:execution%2==0?1:3);
                else if(monsterId=="Exploder") legal=move==(execution<2?1:2);
                else if(monsterId=="Maw") legal=execution==0?move==2:move>=3 && move<=5;
                else if(monsterId=="Nemesis") legal=move>=2 && move<=4;
                else if(monsterId=="GiantHead") legal=execution>=(wire.ascension>=18?3:4)?move==2:move==1 || move==3;
                else if(monsterId=="Donu") legal=move==(execution%2==0?2:0);
                else if(monsterId=="Deca") legal=move==(execution%2==0?0:2);
                else if(monsterId=="SlaverBoss" || monsterId=="GremlinFat") legal=move==2;
                else if(wizard) legal=move==(wire.ascension>=17?(execution<3?2:1):(execution%4<3?2:1));
                else if(shield) legal=execution==0?move==1:move==1 || move==2;
                else if(monsterId=="GremlinThief" || monsterId=="GremlinWarrior" || monsterId=="BanditChild" || monsterId=="Transient") legal=move==1;
                else if(monsterId=="BanditBear") legal=move==(execution==0?2:execution%2==1?3:1);
                else if(monsterId=="BanditLeader") legal=move==(execution==0?2:wire.ascension>=17?(execution%3==1?3:1):(execution%2==1?3:1));
                else if(byrd) legal=move>=1 && move<=6;
                else if(shelled) legal=move>=1 && move<=4;
                else if(champ) legal=move>=1 && move<=7 && (move!=2 || (misc & 3)>0) && (move!=7 || (misc & 4)!=0);
                else if(reactive) legal=move>=0 && move<=4 && (move!=4 || misc==1);
                else if(timeEater) legal=move>=2 && move<=5 && (move!=5 || misc==1);
                else if(act4) {
                    const int known=domeAct4Cycle(monsterId,execution,i>0?moves[i-1].get<int>():-1);
                    legal=known>0?move==known:move==1 || move==2;
                }
            }
            if(!legal || (smallAcid && ((i>0 && moves[i-1]==move)
                    || (wire.ascension>=17 && move!=(execution%2==0?2:1)))) || (red && move==2 && misc!=1)) return "silver_runic_dome_history_gap";
            const auto native=live_silver::monsterMove(monsterId,move);
            if(!native) return "silver_runic_dome_history_schema";
            m.moveHistory[moves.size()-1-i]=static_cast<std::int16_t>(*native);
        }
        if(hardJaw && completed==0) m.moveHistory[0]=static_cast<std::int16_t>(sts::MonsterMoveId::DARKLING_REGROW);
        if(awakened) {
            if(wire.encounter!=static_cast<int>(sts::MonsterEncounter::AWAKENED_ONE)
                    || (wire.monsterCount!=1 && (wire.monsterCount!=3 || slot!=2
                        || wire.monsters[0].id!=static_cast<int>(sts::MonsterId::CULTIST)
                        || wire.monsters[1].id!=static_cast<int>(sts::MonsterId::CULTIST)))) return "silver_runic_dome_encounter_domain";
            // Under a source card's grid the duplicate Rebirth setter is still
            // queued (problem 90): one known transition, with the pending item.
            const auto queue=combat.find("pendingActionQueue");
            const bool rebirthWindow=m.halfDead && queue!=combat.end() && queue->is_array() && awakenedRebirthQueue()
                && std::any_of(queue->begin(),queue->end(),[&](const json &item) {
                    return item.is_object() && item.value("kind","")=="MONSTER_SET_MOVE"
                        && item.value("move",-1)==3 && item.value("slot",-1)==slot;});
            if((m.halfDead && (misc!=0 || m.curHp>0 || !knownNext))
                    || (knownNext && !m.halfDead) || k.at("knownTransitions")!=((misc || m.halfDead)?(rebirthWindow?1:2):0)) return "silver_runic_dome_history_gap";
            if(!misc && std::any_of(moves.begin(),moves.end(),[](const json &v){return v!=1 && v!=2;})) return "silver_runic_dome_history_gap";
        }
        if(laga) {
            if(wire.monsterCount!=1 || (wire.encounter!=static_cast<int>(sts::MonsterEncounter::LAGAVULIN)
                    && wire.encounter!=static_cast<int>(sts::MonsterEncounter::LAGAVULIN_EVENT))) return "silver_runic_dome_encounter_domain";
            if(!integer("publicSleepTurns",0,3) || k.at("publicSleepTurns")>completed
                    || !k.contains("publicAsleep") || !k.at("publicAsleep").is_boolean()) return "silver_runic_dome_history_schema";
            const bool asleep=k.at("publicAsleep").get<bool>();
            if((asleep && (k.at("publicSleepTurns")>=3 || wire.encounter==static_cast<int>(sts::MonsterEncounter::LAGAVULIN_EVENT)))
                    || k.at("publicSleepTurns").get<int>()<std::count(moves.begin(),moves.end(),json(5))) return "silver_runic_dome_history_gap";
            if(asleep) m.statusBits|=1ULL<<static_cast<int>(sts::MonsterStatus::ASLEEP);
        }
        if(darkling) {
            // Each half-death adds two known transitions: Darkling.damage's
            // setMove(4) and its queued duplicate. An odd count is the window
            // under a source card's grid, with that duplicate still pending.
            const auto queue=combat.find("pendingActionQueue");
            const bool regrowQueued=queue!=combat.end() && queue->is_array()
                && std::any_of(queue->begin(),queue->end(),[&](const json &item) {
                    return item.is_object() && item.value("kind","")=="MONSTER_SET_MOVE"
                        && item.value("move",-1)==4 && item.value("slot",-1)==slot;});
            const bool window=k.at("knownTransitions").get<int>()%2==1;
            if(window && (!darklingDomeRegrowQueue() || !regrowQueued || !knownNext))return "silver_runic_dome_history_gap";
            if(regrowQueued && !window)return "silver_runic_dome_history_gap";
        }
        if(darkling && ((knownNext && (!m.halfDead || m.curHp!=0))
                || (!knownNext && m.halfDead && (moves.empty() || moves.back()!=4 || k.at("rollHp")!=0))))return "silver_runic_dome_history_gap";
        if(split && knownNext && k.at("knownNextMove").at("move")==3 && m.curHp*2>m.maxHp)return "silver_runic_dome_history_gap";
        const bool rebirthRoll=awakened && misc==1 && !m.halfDead && pending==1 && !moves.empty() && moves.back()==3
                && domeRebirthRollFix();
        if(k.at("rollHp")==0 && !(darkling && m.halfDead) && !rebirthRoll)return "silver_runic_dome_history_gap";
        if(hex && (completed==0?misc!=0:misc<1 || misc>834)) return "silver_runic_dome_history_gap";
        if(guardian && (misc<(wire.ascension>=19?40:wire.ascension>=9?35:30)
                || (misc-(wire.ascension>=19?40:wire.ascension>=9?35:30))%10 || misc>(wire.ascension>=19?40:wire.ascension>=9?35:30)+10*completed))
            return "silver_runic_dome_history_gap";
        if(champ && ((misc & 3)>2 || (misc & 3)>completed || (misc & 3)<std::count(moves.begin(),moves.end(),json(2))))
            return "silver_runic_dome_history_gap";
        if(book && ((wire.ascension>=18 && misc!=completed+1)
                || (wire.ascension<18 && misc<1+std::count(moves.begin(),moves.end(),json(1)))))
            return "silver_runic_dome_history_gap";
        if(spiker && (misc>completed || misc<std::count(moves.begin(),moves.end(),json(2))))
            return "silver_runic_dome_history_gap";
        if(monsterId=="Exploder" && !dead) {
            for(const auto &power:combat.at("monsters").at(slot).value("powers",json::array()))
                if(power.value("id",std::string())=="Explosive" && power.value("amount",0)!=3-completed)
                    return "silver_runic_dome_monster_power_domain";
        }
        if(wizard && misc!=(wire.ascension>=17?(completed<=3?completed:0):completed%4))
            return "silver_runic_dome_history_gap";
        if(knownNext) {
            const int last=moves.empty()?0:moves.back().get<int>();int derived=1;
            if(dynamic) {
                const auto &proof=k.at("knownNextMove");
                if(act4) {
                    derived=domeAct4Cycle(monsterId,completed,moves.empty()?-1:last);
                    if(derived<=0) return "silver_runic_dome_known_next_schema";
                } else if(remaining) {
                    if(split)derived=slimeBoss && k.at("knownNextMove").at("kind")=="slime_boss_public_cycle"?(last==4?2:last==2?1:4):3;
                    else if(darkling)derived=4;else if(torch)derived=1;else return "silver_runic_dome_known_next_schema";
                } else if(awakened) {derived=3;} else if(thief) {
                    if(completed<1) return "silver_runic_dome_known_next_schema";
                    derived=last==1?1:last==4?2:3;
                } else if(laga) {
                    if(k.at("publicAsleep")==true) return "silver_runic_dome_known_next_schema";
                    if(proof.at("kind")=="public_stun_override") derived=4;
                    else if(proof.at("kind")=="lagavulin_awake_event") {
                        if(completed || wire.encounter!=static_cast<int>(sts::MonsterEncounter::LAGAVULIN_EVENT)) return "silver_runic_dome_known_next_schema";
                        derived=1;
                    } else {
                        if(k.at("publicSleepTurns")!=3 || last!=5) return "silver_runic_dome_known_next_schema";
                        derived=3;
                    }
                } else if(hex) {
                    if(completed!=1 || last!=5) return "silver_runic_dome_known_next_schema";
                    derived=1;
                } else if(guardian) {
                    if(proof.at("kind")=="guardian_defensive_override") {
                        if(m.statusBits & (1ULL<<static_cast<int>(sts::MonsterStatus::MODE_SHIFT))) return "silver_runic_dome_known_next_schema";
                        derived=1;
                    } else {
                        if(last<1 || last>7) return "silver_runic_dome_known_next_schema";
                        const int next[]={0,3,7,4,5,6,2,5};derived=next[last];
                    }
                } else if(proof.at("kind")=="public_stun_override") {
                    if((byrd && (m.statusBits & (1ULL<<static_cast<int>(sts::MonsterStatus::FLIGHT))))
                            || (shelled && m.smallPowers[static_cast<int>(sts::MonsterStatus::PLATED_ARMOR)]!=0))
                        return "silver_runic_dome_known_next_schema";
                    derived=4;
                } else {
                    if(!byrd || last!=5) return "silver_runic_dome_known_next_schema";
                    derived=2;
                }
            } else if(smallAcid) derived=3-last;
            else if(monsterId=="BanditBear") derived=last==3?1:3;
            else if(monsterId=="BanditLeader") derived=last==3?1:last==1 && wire.ascension>=17
                    && (moves.size()<2 || moves.front()!=1)?1:3;
            else if(wizard) derived=misc>=3 || (last==1 && wire.ascension>=17)?1:2;
            else if(shield) {
                if(!integer("aliveCount",1,wire.monsterCount)) return "silver_runic_dome_history_schema";
                derived=last==2 || k.at("aliveCount")==1?2:1;
            }
            if(k.at("knownNextMove").at("move")!=derived) return "silver_runic_dome_known_next_schema";
            m.moveHistory[1]=m.moveHistory[0];
            m.moveHistory[0]=static_cast<std::int16_t>(*live_silver::monsterMove(monsterId,derived));
            if(awakened || darkling || (split && derived==3)) m.moveHistory[1]=m.moveHistory[0];
        }
        if(dynamic) {
            if(!k.contains("knownRollPredecessor")) return "silver_runic_dome_known_next_schema";
            const bool predecessor=!knownNext && !dead && ((shelled && !moves.empty() && moves.back()==4)
                    || (hex && completed>=2 && (completed-2)%7==6)
                    || (laga && !moves.empty() && (moves.back()==5 || moves.back()==6)));
            if(predecessor) {
                if(k.at("knownRollPredecessor")!=(laga?"lagavulin_sleep_predecessor":hex?"hexaghost_inferno_predecessor":"shelled_stun_fell")) return "silver_runic_dome_known_next_schema";
                m.moveHistory[1]=m.moveHistory[0];m.moveHistory[0]=static_cast<std::int16_t>(laga?(moves.back()==5?sts::MonsterMoveId::LAGAVULIN_SLEEP:sts::MonsterMoveId::LAGAVULIN_ATTACK):hex?sts::MonsterMoveId::HEXAGHOST_INFERNO:sts::MonsterMoveId::SHELLED_PARASITE_FELL);
            } else if(torch && completed==0 && pending==1 && k.at("knownRollPredecessor")=="torch_constructor_tackle") {
                m.moveHistory[0]=static_cast<std::int16_t>(sts::MonsterMoveId::TORCH_HEAD_TACKLE);
            } else if(darkling && knownNext && k.at("knownRollPredecessor")=="darkling_reincarnate_before_regrow") {
                m.moveHistory[1]=static_cast<std::int16_t>(sts::MonsterMoveId::DARKLING_REINCARNATE);
            } else if((torch && completed==0 && !dead) || !k.at("knownRollPredecessor").is_null()) return "silver_runic_dome_known_next_schema";
        } else if(k.contains("knownTransitions") || k.contains("knownRollPredecessor")) return "silver_runic_dome_history_schema";
        // Generic import validates public scalar powers. Only class-specific
        // unique powers below may carry a monster's lifecycle state.
        std::uint64_t allowed=(1ULL<<(static_cast<int>(sts::MonsterStatus::WEAK)+1))-1;
        allowed|=(1ULL<<62) | (1ULL<<63);
        if(cultist) allowed|=(1ULL<<static_cast<int>(sts::MonsterStatus::RITUAL)) | (1ULL<<61);
        if(fungi) allowed|=1ULL<<static_cast<int>(sts::MonsterStatus::SPORE_CLOUD);
        if(nob) allowed|=1ULL<<static_cast<int>(sts::MonsterStatus::ENRAGE);
        const auto allow=[&](sts::MonsterStatus status) {allowed|=1ULL<<static_cast<int>(status);};
        if(monsterId=="SnakePlant") allow(sts::MonsterStatus::MALLEABLE);
        if(monsterId=="SphericGuardian") allow(sts::MonsterStatus::BARRICADE);
        if(monsterId=="Orb Walker") allow(sts::MonsterStatus::GENERIC_STRENGTH_UP);
        if(monsterId=="Nemesis") allow(sts::MonsterStatus::INTANGIBLE);
        if(monsterId=="GiantHead") allow(sts::MonsterStatus::SLOW);
        if(monsterId=="Donu" || monsterId=="Deca") allow(sts::MonsterStatus::PLATED_ARMOR);
        if(spiker) allow(sts::MonsterStatus::THORNS);
        if(book) allow(sts::MonsterStatus::PAINFUL_STABS);
        if(timeEater) allow(sts::MonsterStatus::TIME_WARP);
        if(lice)allow(sts::MonsterStatus::CURL_UP);
        if(darkling)allow(sts::MonsterStatus::REGROW);
        if(orb)allow(sts::MonsterStatus::STASIS);
        if(monsterId=="GremlinLeader" || monsterId=="Reptomancer" || monsterId=="TheCollector" || automaton)allow(sts::MonsterStatus::MINION_LEADER);
        if(bound)allow(sts::MonsterStatus::MINION);
        if(awakened) {allow(sts::MonsterStatus::CURIOSITY);allow(sts::MonsterStatus::MINION_LEADER);}
        if(thief) allow(sts::MonsterStatus::THIEVERY);
        if(laga) allow(sts::MonsterStatus::ASLEEP);
        if(byrd) allow(sts::MonsterStatus::FLIGHT);
        if(guardian) {allow(sts::MonsterStatus::MODE_SHIFT);allow(sts::MonsterStatus::SHARP_HIDE);}
        if(heart) {allow(sts::MonsterStatus::BEAT_OF_DEATH);allow(sts::MonsterStatus::INVINCIBLE);allow(sts::MonsterStatus::PAINFUL_STABS);}
        if(reactive) {allow(sts::MonsterStatus::MALLEABLE);allow(sts::MonsterStatus::REACTIVE);}
        if(monsterId=="GremlinWarrior") allow(sts::MonsterStatus::ANGRY);
        if(monsterId=="Transient") {allow(sts::MonsterStatus::FADING);allow(sts::MonsterStatus::SHIFTING);}
        const auto uniqueMask=((1ULL<<(static_cast<int>(sts::MonsterStatus::TIME_WARP)+1))-1)
                ^ ((1ULL<<static_cast<int>(sts::MonsterStatus::ANGRY))-1);
        // Generic import maps Compulsive to 0; a nonzero count can only be the
        // folded REACTIVE_ROLL_MOVE of the pending queue.
        const bool queuedReroll=reactive && domeReactiveFix() && m.uniquePower1>0
            && std::any_of(wire.pendingActionQueue.begin(),wire.pendingActionQueue.end(),[](const auto &action) {
                return action.kind==silver_bridge::PendingActionKind::REACTIVE_ROLL_MOVE;});
        if((m.statusBits & ~allowed) || (!guardian && !heart && !queuedReroll && m.uniquePower1) || (!(m.statusBits & uniqueMask) && m.uniquePower0))
            return "silver_runic_dome_monster_power_domain";
        for(std::size_t i=1;i<m.smallPowers.size();++i)
            if(m.smallPowers[i] && !(allowed & (1ULL<<i))) return "silver_runic_dome_monster_power_domain";
        if(hex) m.uniquePower0=completed==1?6:completed>=2?(completed-2)%7:0;
        if(awakened && misc) m.statusBits|=1ULL<<static_cast<int>(sts::MonsterStatus::MINION_LEADER);
        if(thief && misc>0) wire.miscBits|=1U;
        if(automaton && misc!=(completed==0?0:((completed-1)%6==5?0:(completed-1)%6)))return "silver_runic_dome_history_gap";
        if(torch && (k.at("totalRolls")!=1 || k.at("knownTransitions")!=completed+1))return "silver_runic_dome_history_gap";
        if(orb && (misc<std::count(moves.begin(),moves.end(),json(3)) || (completed==0 && misc)))return "silver_runic_dome_history_gap";
        if(latent) {
            const unsigned prior=sts::Monster::latentDamagePrior(*id,wire.ascension);
            if(!integer("latentDamageMask",1,65535) || (k.at("latentDamageMask").get<unsigned>() & ~prior)
                    || !k.contains("latentDamageObservations") || !k.at("latentDamageObservations").is_array())return "silver_runic_dome_latent_damage_schema";
            std::uint16_t posterior=static_cast<std::uint16_t>(prior);
            if(!integer("latentDamageExecutions",std::count(moves.begin(),moves.end(),json(3)),completed)
                    || k.at("latentDamageObservations").size()!=k.at("latentDamageExecutions").get<std::size_t>())return "silver_runic_dome_latent_damage_schema";
            for(const auto &o:k.at("latentDamageObservations")) {
                if(!o.is_object() || o.size()!=17)return "silver_runic_dome_latent_damage_schema";
                for(const char *field:{"beforeHp","afterHp","beforeBlock","afterBlock","beforeBuffer","afterBuffer","maxHp","strength","reviveHp"})
                    if(!validInteger(o,field,std::string(field)=="strength"?-999:0,99999))return "silver_runic_dome_latent_damage_schema";
                for(const char *field:{"weak","vulnerable","intangible","oddMushroom","paperKrane","torii","tungstenRod","wrath"})
                    if(!o.contains(field) || !o.at(field).is_boolean())return "silver_runic_dome_latent_damage_schema";
                sts::PublicDamageObservation observation;
                observation.beforeHp=o.at("beforeHp");observation.afterHp=o.at("afterHp");observation.beforeBlock=o.at("beforeBlock");observation.afterBlock=o.at("afterBlock");
                observation.beforeBuffer=o.at("beforeBuffer");observation.afterBuffer=o.at("afterBuffer");observation.maxHp=o.at("maxHp");observation.strength=o.at("strength");observation.reviveHp=o.at("reviveHp");
                observation.weak=o.at("weak");observation.vulnerable=o.at("vulnerable");observation.intangible=o.at("intangible");observation.oddMushroom=o.at("oddMushroom");
                observation.paperKrane=o.at("paperKrane");observation.torii=o.at("torii");observation.tungstenRod=o.at("tungstenRod");observation.wrath=o.at("wrath");
                try {posterior=sts::filterPublicDamageBelief(posterior,observation);}catch(const std::exception &){return "silver_runic_dome_latent_damage_observation";}
            }
            if(posterior!=k.at("latentDamageMask"))return "silver_runic_dome_latent_damage_observation";
            m.latentDamageMask=posterior;
        } else if(k.contains("latentDamageMask") || k.contains("latentDamageObservations") || k.contains("latentDamageExecutions"))return "silver_runic_dome_latent_damage_schema";
        m.miscInfo=misc; m.pendingMoveRolls=pending; m.pendingDirectMoveChoice=direct?(monsterId=="Looter"?1:2):0;
        auto &inputs=m.pendingRollInputs;
        inputs.curHp=k.at("rollHp").get<int>(); inputs.maxHp=k.at("rollMaxHp").get<int>();
        inputs.knightCurHp=inputs.curHp; inputs.knightMaxHp=inputs.maxHp; inputs.knightAlive=true;
        inputs.aliveCount=1; inputs.monstersAlive=1;
        if(multi) {
            if(!integer("firstHp",0,999) || !integer("firstMaxHp",1,999) || k.at("firstHp")>k.at("firstMaxHp")
                    || !k.contains("firstAlive") || !k.at("firstAlive").is_boolean()
                    || !integer("aliveCount",newbornRoll?0:1,wire.monsterCount)) return "silver_runic_dome_history_schema";
            inputs.knightCurHp=k.at("firstHp").get<int>();inputs.knightMaxHp=k.at("firstMaxHp").get<int>();
            inputs.knightAlive=k.at("firstAlive").get<bool>();inputs.aliveCount=k.at("aliveCount").get<int>();
            inputs.monstersAlive=inputs.aliveCount;
        }
        if(multi && !k.contains("pendingAttackPredicates")) return "silver_runic_dome_predicate_schema";
        if(k.contains("pendingAttackPredicates")) {
            const auto &predicates=k.at("pendingAttackPredicates");int previous=0;
            if(!predicates.is_array() || predicates.size()>static_cast<std::size_t>(pending+direct)) return "silver_runic_dome_predicate_schema";
            for(const auto &predicate:predicates) {
                if(!predicate.is_array() || predicate.size()!=2 || !predicate[0].is_number_integer()
                        || predicate[0]<=previous || predicate[0]>pending+direct || !predicate[1].is_boolean())
                    return "silver_runic_dome_predicate_schema";
                previous=predicate[0].get<int>();m.pendingAttackPredicates.emplace_back(previous,predicate[1].get<bool>());
            }
        }
        inputs.monsterTurnNumber=std::max(1,bound?rollTurn:completed); inputs.miscInfo=misc;
        if(monsterId=="Serpent" && (!k.contains("playerConstricted") || !k.at("playerConstricted").is_boolean()))
            return "silver_runic_dome_history_schema";
        inputs.playerConstricted=k.value("playerConstricted",false);inputs.asleep=laga && k.at("publicAsleep").get<bool>();inputs.halfDead=darkling && m.halfDead;
        if(reactive) {
            if(!k.contains("pendingRollInputs") || !k.at("pendingRollInputs").is_array()
                    || k.at("pendingRollInputs").size()!=static_cast<std::size_t>(pending))
                return "silver_runic_dome_history_schema";
            bool front=true;
            for(auto r:k.at("pendingRollInputs")) {
                const bool initialRow=std::exchange(front,false) && unexecutedInitial && pending==k.at("totalRolls").get<int>();
                if(initialRow && r.is_object() && r.contains("rollGlobalTurn")) r["rollGlobalTurn"]=0;
                if(!r.is_object() || r.size()!=(bound?8:7) || !validInteger(r,"rollHp",1,999) || !validInteger(r,"rollMaxHp",1,999)
                        || r.at("rollHp")>r.at("rollMaxHp") || r.at("rollMaxHp")!=m.maxHp
                        || !validInteger(r,"firstHp",0,999) || !validInteger(r,"firstMaxHp",1,999)
                        || r.at("firstHp")>r.at("firstMaxHp") || !validInteger(r,"aliveCount",1,wire.monsterCount)
                        || !r.contains("firstAlive") || !r.at("firstAlive").is_boolean()
                        || !r.contains("playerConstricted") || !r.at("playerConstricted").is_boolean())
                    return "silver_runic_dome_history_schema";
                auto step=inputs;
                if(bound) {
                    if(!validInteger(r,"rollGlobalTurn",birthTurn,wire.turn+1))return "silver_runic_dome_history_schema";
                    step.monsterTurnNumber=std::max(1,r.at("rollGlobalTurn").get<int>());
                }
                step.curHp=r.at("rollHp").get<int>();step.maxHp=r.at("rollMaxHp").get<int>();
                step.knightCurHp=r.at("firstHp").get<int>();step.knightMaxHp=r.at("firstMaxHp").get<int>();
                step.knightAlive=r.at("firstAlive").get<bool>();step.aliveCount=r.at("aliveCount").get<int>();
                step.monstersAlive=step.aliveCount;step.playerConstricted=r.at("playerConstricted").get<bool>();
                m.pendingRollInputHistory.push_back(step);
            }
            if(pending) m.pendingRollInputs=m.pendingRollInputHistory.front();
        } else if(k.contains("pendingRollInputs") || (!dynamic && k.contains("totalRolls"))) return "silver_runic_dome_history_schema";

    }
    // Card/power/relic/potion support is validated by the generic importer.
    // Spot Weakness, including generated copies, is the only native Ironclad
    // intent query and carries an indexed public predicate above.
    bool owned=false;
    for(const auto &relic:combat.at("relics")) {
        sts::RelicId id;
        if(!parseEnumId(relic,"id",id)) return "silver_runic_dome_relic_domain";
        owned |= id==sts::RelicId::RUNIC_DOME;
    }
    if(!owned) return "silver_runic_dome_relic_domain";
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
    if (combat.contains("orphanedHandSelection"))
        return unsupported("silver_orphaned_hand_selection");
    if (combat.contains("occupantBindingError")) return unsupported("silver_monster_occupant_binding");
    if (combat.contains("pendingActionQueueError")) return unsupported("silver_selection_pending_actions");
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
    if (cardSelect && (selectionIt->value("task",std::string())=="ARMAMENTS" || selectionIt->value("task",std::string())=="EXHUME" || selectionIt->value("task",std::string())=="DUAL_WIELD")) {
        const bool armaments=selectionIt->at("task")=="ARMAMENTS", dualWield=selectionIt->at("task")=="DUAL_WIELD";
        const auto held=selectionIt->find("heldCards");
        if(held==selectionIt->end() || !held->is_array() || held->size()>128
                || selectionIt->value("origin",std::string())!=(armaments || dualWield?"HAND_SELECT":"GRID")
                || selectionIt->value("actionClass",std::string())!=(armaments?"com.megacrit.cardcrawl.actions.unique.ArmamentsAction":dualWield?"com.megacrit.cardcrawl.actions.unique.DualWieldAction":"com.megacrit.cardcrawl.actions.unique.ExhumeAction")
                || !selectionIt->contains("upgradeVariant") || selectionIt->at("upgradeVariant")!=false)
            return unsupported("silver_selection_held_cards");
        for(const auto &item:*held) {
            CardRecord card;if(!parseGenericCard(item,card))return unsupported("silver_selection_held_cards");
            const sts::CardInstance native(static_cast<sts::CardId>(card.wire.id),card.wire.upgraded);
            if(armaments?native.canUpgrade():dualWield?native.getType()==sts::CardType::ATTACK || native.getType()==sts::CardType::POWER:native.id!=sts::CardId::EXHUME)return unsupported("silver_selection_held_cards");
            if(armaments || dualWield)hand.push_back(card);else exhaust.unknown.push_back(card);
        }
    }
    if (stasis.size() > wire.stasisCards.size()) return unsupported("silver_unmapped_stasis");
    // Stasis returns still queued behind a source card (STASIS_RETURN).
    std::array<bool, 2> stasisReturnPending {}, stasisReturnFolded {};
    if (stasisReturnQueue() && combat.contains("pendingActionQueue") && combat.at("pendingActionQueue").is_array())
        for (const auto &entry : combat.at("pendingActionQueue")) {
            if (!entry.is_object() || entry.value("kind", std::string()) != "STASIS_RETURN") continue;
            const auto slot = entry.find("slot");
            if (slot == entry.end() || !slot->is_number_integer() || *slot < 0 || *slot > 1
                || stasisReturnPending[slot->get<int>()]) return unsupported("silver_selection_pending_actions");
            stasisReturnPending[slot->get<int>()] = true;
        }
    if (!stasis.empty()) {
        std::array<CardRecord, 2> orderedStasis;
        std::array<bool, 2> seenStasis {};
        const auto &stasisJson = combat.at("stasis");
        const json monstersJson = combat.value("monsters", json::array());
        const auto returnedElsewhere = [&](const std::string &uuid) {
            const auto has = [&](const std::vector<CardRecord> &cards) {
                return std::any_of(cards.begin(), cards.end(),
                                   [&](const CardRecord &card) { return card.uuid == uuid; });
            };
            return has(hand) || has(limbo) || has(draw.bottom) || has(draw.unknown) || has(draw.top)
                || has(discard.bottom) || has(discard.unknown) || has(discard.top)
                || has(exhaust.bottom) || has(exhaust.unknown) || has(exhaust.top);
        };
        for (std::size_t i = 0; i < stasis.size(); ++i) {
            if (!stasisJson[i].is_object() || !stasisJson[i].contains("slot")
                || !stasisJson[i].at("slot").is_number_integer())
                return unsupported("silver_unmapped_stasis");
            const int slot = stasisJson[i].at("slot").get<int>();
            if (slot < 0 || slot >= static_cast<int>(orderedStasis.size()) || seenStasis[slot])
                return unsupported("silver_unmapped_stasis");
            // Java StasisPower.onDeath returns the card with its own UUID,
            // but the dead orb keeps listing it until its powers are
            // cleared.  Native returnStasisCard empties the slot.
            bool orbDead = false;
            for (std::size_t m = 0; monstersJson.is_array() && m < monstersJson.size(); ++m) {
                const auto &orb = monstersJson[m];
                if (!orb.is_object()
                    || orb.value("slot", orb.value("idx", static_cast<int>(m))) != slot * 2) continue;
                orbDead = orb.value("dead", false)
                    || (orb.value("hp", 1) <= 0 && !orb.value("halfDead", false));
            }
            if (orbDead && stasisReturnPending[slot]) {
                // StasisPower.onDeath with fewer than 10 cards in hand queued
                // MakeTempCardInHandAction(card, false, true); native
                // returnStasisCard already moved it to hand. Under Corruption
                // that runs the onCardDrawOrDiscard pass over the hand's
                // Skills (STS_CORRUPTION_HAND_COST_FIX; legacy: the returned
                // Skill's costForTurn only).
                if (returnedElsewhere(stasis[i].uuid) || hand.size() >= 10) return unsupported("silver_unmapped_stasis");
                const json playerPowers = combat.value("playerPowers", json::array());
                const bool corruption = playerPowers.is_array() && std::any_of(playerPowers.begin(), playerPowers.end(),
                    [](const json &power) { return power.is_object() && power.value("id", std::string()) == "Corruption"; });
                const auto skill = [](const CardRecord &card) {
                    return sts::CardInstance(static_cast<sts::CardId>(card.wire.id)).getType() == sts::CardType::SKILL;
                };
                hand.push_back(std::move(stasis[i]));
                if (corruption && sts::corruptionHandCostFix()) {
                    for (auto &card : hand) {
                        if (!skill(card) || card.wire.costForTurn == 0) continue;
                        // CardInstance::modifyCostForCombat(-9)
                        auto &w = card.wire;
                        if (w.costForTurn > 0) { w.costForTurn = 0; w.cost = 0; }
                        else if (w.cost >= 0) { w.cost = 0; w.costForTurn = 0; }
                    }
                } else if (corruption && hand.back().wire.costForTurn >= 0 && skill(hand.back())) {
                    hand.back().wire.costForTurn = 0;
                }
                stasisReturnFolded[slot] = true;
                continue;
            }
            if (orbDead) {
                if (!returnedElsewhere(stasis[i].uuid)) return unsupported("silver_unmapped_stasis");
                continue;
            }
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
        // STS_STRIKE_COUNT_FIX=0 restores the legacy recount, one too high
        // per exhausted Strike or Strike held by a Stasis orb.
        if (sts::strikeCountFix()) {
            for (const auto *pile : {&exhaust.bottom, &exhaust.unknown, &exhaust.top, &stasis})
                for (const auto &card : *pile) if (isStrike(card.wire)) --wire.strikeCount;
        }
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
    if (orangePelletsFix() && combat.contains("orangePelletsCardTypesPlayed"))
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
            // Java PanachePower.amount is the cards-until-damage countdown;
            // the damage is a separate private field. Native keeps the damage
            // as the status amount and the countdown in panacheCounter.
            const bool needsPanache = *mapped == PlayerStatus::PANACHE;
            const bool needsDeva = *mapped == PlayerStatus::DEVA;
            const bool needsBomb = *mapped == PlayerStatus::THE_BOMB;
            const bool needsJustApplied = *mapped == PlayerStatus::DOUBLE_DAMAGE
                || *mapped == PlayerStatus::DRAW_REDUCTION || *mapped == PlayerStatus::FRAIL
                || *mapped == PlayerStatus::INTANGIBLE || *mapped == PlayerStatus::VULNERABLE
                || *mapped == PlayerStatus::WEAK;
            if ((needsCombust && !combat.contains("combustHpLoss"))
                || (needsEcho && !combat.contains("echoFormCardsDoubled"))
                || (needsPanache && (!power.contains("panacheDamage")
                    || !power.at("panacheDamage").is_number_integer()
                    || power.value("panacheDamage", 0) < 1 || power.value("panacheDamage", 0) > 127
                    || power.value("amount", 0) < 1 || power.value("amount", 0) > 5))
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
            } else if (needsPanache) {
                p.panacheCounter = static_cast<std::int8_t>(amount);
                setPlayerPower(p, *mapped, power.at("panacheDamage").get<int>(), false);
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
        // The producer exports the raw vanilla field as "activated"; older
        // producers sent the same value under "usedThisTurn".
        const char *necronomiconField = relic.contains("activated") ? "activated" : "usedThisTurn";
        if (id == sts::RelicId::NECRONOMICON
            && (!relic.contains(necronomiconField) || !relic.at(necronomiconField).is_boolean()))
            return unsupported("silver_unmapped_relic_state");
        if (id == sts::RelicId::CENTENNIAL_PUZZLE && centennialUsedFix()) {
            if (!relic.contains("usedThisCombat") || !relic.at("usedThisCombat").is_boolean())
                return unsupported("silver_unmapped_relic_state");
            if (relic.at("usedThisCombat").get<bool>()) continue;
        }
        if (relic.at("usedUp").get<bool>()) continue;
        const int rid = static_cast<int>(id);
        if (rid < 64) p.relicBits0 |= 1ULL << rid;
        else if (rid < 128) p.relicBits1 |= 1ULL << (rid - 64);
        else if (!highRelicFix()) p.relicBits1 |= 1ULL << (rid - 128);
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
        if (id == sts::RelicId::NECRONOMICON) {
            const bool activated = relic.at(necronomiconField).get<bool>();
            p.haveUsedNecronomiconThisTurn = necronomiconReadyFix() ? !activated : activated;
        }
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
    int backAttackSlot = -1;
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
        if(item.contains("occupantGeneration")) {
            if(!item.at("occupantGeneration").is_number_integer() || item.at("occupantGeneration")<1 || item.at("occupantGeneration")>1000000)return unsupported("silver_monster_occupant_binding");
            m.occupantGeneration=item.at("occupantGeneration").get<std::uint32_t>();
        }
        m.curHp = item.value("hp", 0); m.maxHp = item.value("maxHp", 0); m.block = item.value("block", 0);
        m.isEscapingB = item.value("escaping", item.value("escaped", false)); m.halfDead = item.value("halfDead", false);
        // Java's "escaping" is AbstractMonster.escaped, set only when the
        // escape animation ends; "dead" is isDeadOrEscaped(), which already
        // includes isEscaping. A fleeing monster with HP left is untargetable.
        if (escapingMonsterFix() && !m.isEscapingB && !m.halfDead && m.curHp > 0
            && item.value("dead", false))
            m.isEscapingB = true;
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
        if (idText == "Hexaghost" && !runicDome && !item.contains("uniquePower0"))
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
        if ((*id == sts::MonsterId::GREMLIN_LEADER || *id == sts::MonsterId::REPTOMANCER
                || *id == sts::MonsterId::THE_COLLECTOR || *id == sts::MonsterId::BRONZE_AUTOMATON)
            && minionLeaderFix())
            m.statusBits |= 1ULL << static_cast<int>(sts::MonsterStatus::MINION_LEADER);
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
        // Java Lagavulin has no sleep power: its sleep is the private isOut
        // flag, public only as the IDLE intent (5) that it rolls exactly
        // while asleep. Waking sets OPEN (4, stun) or ATTACK (3).
        if (*id == sts::MonsterId::LAGAVULIN && item.contains("nextMove") && nextMove == 5
                && lagavulinSleepFix())
            m.statusBits |= 1ULL << static_cast<int>(sts::MonsterStatus::ASLEEP);
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
                if (powerId == "BackAttack" && backAttackFix()) {
                    // A marker without hooks; native derives it from facing.
                    // A dead monster never attacks; Java leaves its marker.
                    if ((m.curHp <= 0 || item.value("dead", false)) && spireDeathQueue()
                        && (*id == sts::MonsterId::SPIRE_SHIELD || *id == sts::MonsterId::SPIRE_SPEAR)
                        && power.value("amount", 0) == -1)
                        continue;
                    if ((*id != sts::MonsterId::SPIRE_SHIELD && *id != sts::MonsterId::SPIRE_SPEAR)
                        || power.value("amount", 0) != -1 || backAttackSlot >= 0)
                        return unsupported("silver_unmapped_monster_power");
                    backAttackSlot = slot;
                    continue;
                }
                if (powerId == "Explosive") {
                    // Dome validates this public countdown against captured executions below.
                    if(runicDome && *id==sts::MonsterId::EXPLODER) continue;
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
        if ((*id == sts::MonsterId::LOOTER || *id == sts::MonsterId::MUGGER) && m.miscInfo > 0 && thiefGoldFix())
            wire.miscBits |= 1U;
    }
    // A pending Spire death removes Surrounded (folded below), so facing no
    // longer affects damage.
    bool spireDeathPending = false;
    if (spireDeathQueue() && combat.contains("pendingActionQueue") && combat.at("pendingActionQueue").is_array())
        for (const auto &entry : combat.at("pendingActionQueue"))
            if (entry.is_object() && entry.value("kind", std::string()) == "PLAYER_REMOVE_SURROUNDED") spireDeathPending = true;
    if (backAttackFix() && !spireDeathPending) {
        // Java applyBackAttack: with Surrounded, the monster behind the player
        // deals 1.5x. Native's equivalent is "not lastTargetedMonster", so
        // the player faces the alive Spire monster without the marker. The
        // live driver's target tracker is not Java's flipHorizontal.
        const bool surrounded = (p.statusBits0 >> static_cast<int>(PlayerStatus::SURROUNDED)) & 1ULL;
        const auto alive = [&](int slot) {
            const auto &m = wire.monsters[slot];
            return m.curHp > 0 && !m.isEscapingB && !m.halfDead;
        };
        const bool spirePair = wire.monsterCount == 2
            && wire.monsters[0].id == static_cast<std::int16_t>(sts::MonsterId::SPIRE_SHIELD)
            && wire.monsters[1].id == static_cast<std::int16_t>(sts::MonsterId::SPIRE_SPEAR)
            && alive(0) && alive(1);
        if (backAttackSlot >= 0 || (surrounded && spirePair)) {
            if (!surrounded || !spirePair || backAttackSlot < 0)
                return unsupported("silver_back_attack_facing");
            p.lastTargetedMonster = static_cast<std::int8_t>(1 - backAttackSlot);
        }
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
        if (*task == sts::CardSelectTask::DUAL_WIELD && (wire.cardSelect.data0 < 1 || wire.cardSelect.data0 > 2))
            return unsupported("silver_selection_copy_count");
        wire.cardSelect.selectedBits = selectionIt->value("selectedBits", 0);
        const auto origin = selectionIt->value("origin", std::string());
        if (origin == "GRID" || origin == "HAND_SELECT") {
            const auto source = liveSingleSelectionSource(*task, origin);
            std::map<std::string, int> choices;
            const bool multiForethought = (*task == sts::CardSelectTask::FORETHOUGHT || *task == sts::CardSelectTask::GAMBLE || *task == sts::CardSelectTask::EXHAUST_MANY) && wire.cardSelect.canPickAnyNumber;
            if (!source || !liveSingleChoices(*selectionIt, choices, multiForethought))
                return unsupported("silver_selection_live_choices");
            std::vector<CardRecord> candidates;
            if (*source == silver_bridge::CardSource::HAND) candidates = hand;
            else if (*source == silver_bridge::CardSource::DISCARD) appendGenericCards(discard, candidates);
            else if (*source == silver_bridge::CardSource::EXHAUST) appendGenericCards(exhaust, candidates);
            else appendGenericCards(draw, candidates);
            std::set<std::string> expected;
            for (const auto &card : candidates) {
                const auto type = sts::CardInstance(static_cast<sts::CardId>(card.wire.id)).getType();
                if ((*task == sts::CardSelectTask::SECRET_TECHNIQUE && type != sts::CardType::SKILL)
                    || (*task == sts::CardSelectTask::SECRET_WEAPON && type != sts::CardType::ATTACK)) continue;
                const sts::CardInstance native(static_cast<sts::CardId>(card.wire.id),card.wire.upgraded);
                if ((*task == sts::CardSelectTask::ARMAMENTS && !native.canUpgrade())
                    || (*task == sts::CardSelectTask::EXHUME && native.id == sts::CardId::EXHUME)
                    || (*task == sts::CardSelectTask::DUAL_WIELD && type != sts::CardType::ATTACK && type != sts::CardType::POWER)) continue;
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
                const bool codexOwner = cardSelect && selectionIt->value("origin",std::string())=="CARD_REWARD"
                    && selectionIt->value("continuation",std::string())=="codex_end_turn"
                    && wire.cardSelect.task==static_cast<std::int16_t>(sts::CardSelectTask::CODEX);
                const bool inHand=std::any_of(wire.hand.begin(),wire.hand.end(),[&](const auto &c){return c==parsed.card;});
                if(!codexOwner || !endTurnAutoPlay || item.value("noTriggerOwner",std::string())!="codex_end_turn"
                        || !inHand || !noTriggerIds.insert(parsed.card.uniqueId).second
                        || (parsed.card.id!=static_cast<int>(sts::CardId::BURN) && parsed.card.id!=static_cast<int>(sts::CardId::DECAY)
                            && parsed.card.id!=static_cast<int>(sts::CardId::DOUBT) && parsed.card.id!=static_cast<int>(sts::CardId::SHAME)
                            && parsed.card.id!=static_cast<int>(sts::CardId::REGRET))
                        || parsed.isEndTurn || parsed.ignoreEnergyTotal || parsed.freeToPlay || parsed.randomTarget
                        || parsed.autoplay || parsed.purgeOnUse || parsed.exhaustOnUse || parsed.target!=0
                        || (parsed.card.id!=static_cast<int>(sts::CardId::REGRET) && parsed.regretCardCount!=0))
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
    bool guardianShift=false;
    std::vector<int> groundedByrds;
    if (combat.contains("pendingActionQueue")) {
        using K=silver_bridge::PendingActionKind;
        const auto &queue=combat.at("pendingActionQueue");
        const auto continuation=cardSelect?selectionIt->value("continuation",std::string()):"";
        const bool sourceCard=continuation=="source_card_actions";
        const auto sourceOrigin=cardSelect?selectionIt->value("origin",std::string()):"";
        if(sourceCard && !(liveSingleSelectionSource(static_cast<sts::CardSelectTask>(wire.cardSelect.task),sourceOrigin)
                || (sourceOrigin=="CARD_REWARD" && wire.cardSelect.task==static_cast<int>(sts::CardSelectTask::DISCOVERY)
                    && wire.cardSelect.data0==1 && wire.cardSelect.setCostToZero && !wire.cardSelect.canPickZero)))
            return unsupported("silver_selection_pending_actions");
        const bool rewardPublic=cardSelect && sourceOrigin=="CARD_REWARD" && cardRewardPublicActions()
            && wire.cardSelect.task==static_cast<int>(sts::CardSelectTask::DISCOVERY);
        if (!cardSelect || (continuation=="public_actions" && !rewardPublic
                    && wire.cardSelect.task!=static_cast<int>(sts::CardSelectTask::GAMBLE)
                    && wire.cardSelect.task!=static_cast<int>(sts::CardSelectTask::EXHAUST_MANY)
                    && wire.cardSelect.task!=static_cast<int>(sts::CardSelectTask::LIQUID_MEMORIES_POTION))
                || (continuation=="toolbox_actions" && selectionIt->value("origin",std::string())!="CARD_REWARD")
                || !queue.is_array() || queue.size()>128 || queue.empty()
                || (continuation!="public_actions" && continuation!="toolbox_actions" && !sourceCard)
                || wire.endTurnQueued || wire.turnHasEnded || (!sourceCard && (!limbo.empty() || !wire.pendingCardQueue.empty()))
                || wire.cardSelect.drawAfter!=0 || !wire.cardSelect.drawsAfter.empty()
                || !wire.cardSelect.blocksAfter.empty() || wire.cardSelect.damageAllBeforeBlocks!=0)
            return unsupported("silver_selection_pending_actions");
        const std::map<std::string,K> kinds={{"DRAW",K::DRAW},{"GAIN_BLOCK",K::GAIN_BLOCK},{"GAIN_ENERGY",K::GAIN_ENERGY},
            {"DAMAGE_ALL",K::DAMAGE_ALL},{"DAMAGE_RANDOM",K::DAMAGE_RANDOM},{"GAMBLE",K::GAMBLE},
            {"UPGRADE_RANDOM",K::UPGRADE_RANDOM},{"BUFF_PLAYER",K::BUFF_PLAYER},{"DEBUFF_PLAYER",K::DEBUFF_PLAYER},
            {"DEBUFF_ALL_ENEMY",K::DEBUFF_ALL_ENEMY},{"SHUFFLE_WOUNDS",K::SHUFFLE_WOUNDS},{"SHUFFLE_DAZED",K::SHUFFLE_DAZED},{"USE_CARD",K::USE_CARD},
            {"REMOVE_PEN_NIB",K::REMOVE_PEN_NIB},{"REMOVE_PLAYER_DEBUFFS",K::REMOVE_PLAYER_DEBUFFS}};
        int cleanups=0;
        bool reactiveRoll=false;
        for(const auto &entry:queue) {
            if(!entry.is_object() || !entry.contains("kind") || !entry.at("kind").is_string()) return unsupported("silver_selection_pending_actions");
            // Monster on-hit reactions (Java addToBot) queued behind an
            // interrupted source card such as Headbutt. Native applies Plated
            // Armor loss at the hit, so the queued reduction is folded into
            // the imported monster instead of replayed.
            const auto kindName=entry.at("kind").get<std::string>();
            if(kindName=="STASIS_RETURN") {
                // Folded into the hand with the stasis slots above.
                int slot=-1;
                if(!sourceCard || !requiredInt(entry,"slot",slot) || slot<0 || slot>1 || !stasisReturnFolded[slot])
                    return unsupported("silver_selection_pending_actions");
                continue;
            }
            if(kindName=="PLAYER_REMOVE_SURROUNDED" || kindName=="MONSTER_REMOVE_BACK_ATTACK") {
                // SpireShield/SpireSpear.die() queue these behind the killing
                // card; native removes Surrounded at the death itself.
                int survivor=-1,dead=0;
                for(int slot=0;slot<wire.monsterCount;++slot) {
                    const auto &monster=wire.monsters[slot];
                    if(monster.id!=static_cast<std::int16_t>(sts::MonsterId::SPIRE_SHIELD)
                            && monster.id!=static_cast<std::int16_t>(sts::MonsterId::SPIRE_SPEAR)) continue;
                    if(monster.curHp>0 && !monster.isEscapingB && !monster.halfDead) survivor=survivor<0?slot:-2;
                    else ++dead;
                }
                const auto surroundedBit=1ULL<<static_cast<int>(PlayerStatus::SURROUNDED);
                if(!sourceCard || !spireDeathPending || !sts::spireSurroundedDeathFix() || survivor<0 || dead!=1)
                    return unsupported("silver_selection_pending_actions");
                if(kindName=="PLAYER_REMOVE_SURROUNDED") {
                    if(!(p.statusBits0 & surroundedBit)) return unsupported("silver_selection_pending_actions");
                    p.statusBits0 &= ~surroundedBit;
                } else {
                    // Java queues it after the Surrounded removal; the marker
                    // has no native state once Surrounded is gone.
                    int slot=-1;
                    if(!requiredInt(entry,"slot",slot) || slot!=survivor || backAttackSlot!=survivor
                            || (p.statusBits0 & surroundedBit)) return unsupported("silver_selection_pending_actions");
                }
                continue;
            }
            if(kindName=="MONSTER_SPLIT_SET_MOVE") {
                // The split is already the current move (Java setMove at the
                // hit); native's onHpLost also writes it as the previous move,
                // which the queued SetMoveAction does in Java
                // (STS_SLIME_SPLIT_RNG_FIX).
                int slot=-1;
                if(!sourceCard || !slimeSplitQueue() || !sts::slimeSplitRngFix() || !requiredInt(entry,"slot",slot)
                        || slot<0 || slot>=wire.monsterCount)
                    return unsupported("silver_selection_pending_actions");
                auto &monster=wire.monsters[slot];
                const auto id=static_cast<sts::MonsterId>(monster.id);
                const auto split=id==sts::MonsterId::SPIKE_SLIME_L?sts::MonsterMoveId::SPIKE_SLIME_L_SPLIT
                    :id==sts::MonsterId::ACID_SLIME_L?sts::MonsterMoveId::ACID_SLIME_L_SPLIT
                    :id==sts::MonsterId::SLIME_BOSS?sts::MonsterMoveId::SLIME_BOSS_SPLIT:sts::MonsterMoveId::INVALID;
                if(split==sts::MonsterMoveId::INVALID || monster.idx!=slot || monster.curHp<=0 || monster.halfDead
                        || monster.isEscapingB || monster.curHp>monster.maxHp/2
                        || monster.moveHistory[0]!=static_cast<std::int16_t>(split))
                    return unsupported("silver_selection_pending_actions");
                monster.moveHistory[1]=static_cast<std::int16_t>(split);
                continue;
            }
            if(kindName=="MONSTER_SET_MOVE") {
                // Darkling.damage sets Regrow at the half-death and queues the
                // same SetMoveAction behind the card; native does the same.
                int slot=-1,move=-1;
                if(!sourceCard || !requiredInt(entry,"slot",slot) || !requiredInt(entry,"move",move)
                        || slot<0 || slot>=wire.monsterCount)
                    return unsupported("silver_selection_pending_actions");
                const auto &monster=wire.monsters[slot];
                // AwakenedOne.damage at the first-form death likewise sets
                // Rebirth and queues the same SetMoveAction(3) (problem 90).
                if(move==3) {
                    if(!awakenedRebirthQueue() || monster.idx!=slot || monster.id!=static_cast<std::int16_t>(sts::MonsterId::AWAKENED_ONE)
                            || !monster.halfDead || monster.curHp>0 || monster.miscInfo!=0
                            // Under Runic Dome the history import below derives
                            // Rebirth and requires this item for its row.
                            || (!runicDome && monster.moveHistory[0]!=static_cast<std::int16_t>(sts::MonsterMoveId::AWAKENED_ONE_REBIRTH)))
                        return unsupported("silver_selection_pending_actions");
                    silver_bridge::PendingActionWire action;action.kind=K::MONSTER_SET_MOVE;
                    action.amount=static_cast<int>(sts::MonsterMoveId::AWAKENED_ONE_REBIRTH);action.monster=slot;
                    wire.pendingActionQueue.push_back(action);
                    continue;
                }
                if(!halfDeadSetMoveQueue() || move!=4)
                    return unsupported("silver_selection_pending_actions");
                // Under Runic Dome the history import below derives Regrow
                // and requires this item for its row (problem 104).
                if(monster.idx!=slot || monster.id!=static_cast<std::int16_t>(sts::MonsterId::DARKLING) || !monster.halfDead
                        || (!(runicDome && darklingDomeRegrowQueue())
                            && monster.moveHistory[0]!=static_cast<std::int16_t>(sts::MonsterMoveId::DARKLING_REGROW)))
                    return unsupported("silver_selection_pending_actions");
                silver_bridge::PendingActionWire action;action.kind=K::MONSTER_SET_MOVE;
                action.amount=static_cast<int>(sts::MonsterMoveId::DARKLING_REGROW);action.monster=slot;
                wire.pendingActionQueue.push_back(action);
                continue;
            }
            if(kindName=="MONSTER_GAIN_BLOCK" || kindName=="REACTIVE_ROLL_MOVE" || kindName=="MONSTER_REDUCE_PLATED_ARMOR"
                    || kindName=="MONSTER_REDUCE_FLIGHT" || kindName=="MONSTER_THORNS" || kindName=="MONSTER_CURL_UP"
                    || kindName=="GUARDIAN_DEFENSIVE_SHIFT" || kindName=="MONSTER_LAGAVULIN_OPEN") {
                int slot=-1,amount=0;
                if(!sourceCard || !requiredInt(entry,"slot",slot) || slot<0 || slot>=wire.monsterCount)
                    return unsupported("silver_selection_pending_actions");
                auto &monster=wire.monsters[slot];
                const bool lethalReduce=monster.curHp<=0 && lethalReactionQueue()
                    && (kindName=="MONSTER_REDUCE_FLIGHT" || kindName=="MONSTER_REDUCE_PLATED_ARMOR");
                if(monster.idx!=slot || (monster.curHp<=0 && !lethalReduce) || monster.isEscapingB || monster.halfDead)
                    return unsupported("silver_selection_pending_actions");
                const auto has=[&](sts::MonsterStatus status){return (monster.statusBits & (1ULL<<static_cast<int>(status)))!=0;};
                if(kindName=="REACTIVE_ROLL_MOVE") {
                    if(slot!=0 || monster.id!=static_cast<std::int16_t>(sts::MonsterId::WRITHING_MASS)
                            || !has(sts::MonsterStatus::REACTIVE) || monster.uniquePower1>=8)
                        return unsupported("silver_selection_pending_actions");
                    ++monster.uniquePower1;
                    if(!reactiveRoll) {
                        silver_bridge::PendingActionWire action;action.kind=K::REACTIVE_ROLL_MOVE;
                        wire.pendingActionQueue.push_back(action);
                    }
                    reactiveRoll=true;
                    continue;
                }
                if(kindName=="GUARDIAN_DEFENSIVE_SHIFT") {
                    // Java queues the shift last (ChangeStateAction "Defensive
                    // Mode"); the wire settles an exhausted Mode Shift itself and
                    // queues the 20 block behind the observed tail.
                    if(slot!=0 || &entry!=&queue.back() || monster.id!=static_cast<std::int16_t>(sts::MonsterId::THE_GUARDIAN)
                            || !has(sts::MonsterStatus::MODE_SHIFT) || monster.uniquePower0>0)
                        return unsupported("silver_selection_pending_actions");
                    guardianShift=true;
                    continue;
                }
                if(!requiredInt(entry,"amount",amount)) return unsupported("silver_selection_pending_actions");
                if(kindName=="MONSTER_CURL_UP") {
                    // Native removes Curl Up at the hit and queues its block.
                    if((monster.id!=static_cast<std::int16_t>(sts::MonsterId::RED_LOUSE)
                                && monster.id!=static_cast<std::int16_t>(sts::MonsterId::GREEN_LOUSE))
                            || !has(sts::MonsterStatus::CURL_UP) || amount<1 || amount!=monster.uniquePower0)
                        return unsupported("silver_selection_pending_actions");
                    monster.statusBits&=~(1ULL<<static_cast<int>(sts::MonsterStatus::CURL_UP));
                    silver_bridge::PendingActionWire action;action.kind=K::MONSTER_GAIN_BLOCK;
                    action.amount=amount;action.monster=slot;
                    wire.pendingActionQueue.push_back(action);
                    continue;
                }
                if(kindName=="MONSTER_LAGAVULIN_OPEN") {
                    // Native wakes the Lagavulin at the hit (Monster::
                    // wakeMetallicize, the same rule in both states of
                    // STS_LAGAVULIN_WAKE_METALLICIZE_FIX); the producer has
                    // already set OPEN, so only the reduction is pending.
                    // ReducePowerAction removes the power when 8 or less.
                    auto &metallicize=monster.smallPowers[6];
                    if(!lagavulinOpenQueue() || slot!=0 || monster.id!=static_cast<std::int16_t>(sts::MonsterId::LAGAVULIN)
                            || has(sts::MonsterStatus::ASLEEP) || !has(sts::MonsterStatus::METALLICIZE)
                            || monster.moveHistory[0]!=static_cast<std::int16_t>(sts::MonsterMoveId::LAGAVULIN_SLEEP)
                            || amount<1 || amount!=metallicize)
                        return unsupported("silver_selection_pending_actions");
                    metallicize=sts::lagavulinWakeMetallicizeFix() && metallicize>8?metallicize-8:0;
                    if(metallicize==0) monster.statusBits&=~(1ULL<<static_cast<int>(sts::MonsterStatus::METALLICIZE));
                    continue;
                }
                if(kindName=="MONSTER_THORNS") {
                    // Native Sharp Hide reads monster 0's scalar.
                    if(slot!=0 || monster.id!=static_cast<std::int16_t>(sts::MonsterId::THE_GUARDIAN)
                            || !has(sts::MonsterStatus::SHARP_HIDE) || amount<1 || amount!=monster.uniquePower1)
                        return unsupported("silver_selection_pending_actions");
                    silver_bridge::PendingActionWire action;action.kind=K::MONSTER_THORNS;action.amount=amount;
                    wire.pendingActionQueue.push_back(action);
                    continue;
                }
                if(kindName=="MONSTER_REDUCE_FLIGHT") {
                    // Native Flight loss happens at the hit, like Plated Armor;
                    // reaching 0 grounds (stuns) the Byrd: native sets the stun
                    // and Flight 0 at the hit, before a lethal hit's death (live
                    // seed 111200460) and on a living Byrd (problem 80).
                    auto &flight=monster.uniquePower0;
                    if(amount!=1 || monster.id!=static_cast<std::int16_t>(sts::MonsterId::BYRD)
                            || !has(sts::MonsterStatus::FLIGHT) || flight<1
                            || (flight==1 && !lethalReduce && (monster.curHp<=0 || !byrdGroundingQueue())))
                        return unsupported("silver_selection_pending_actions");
                    if(flight==1) {
                        // Under Runic Dome the history import below rebuilds
                        // the moves and the deferred roll; the stun follows it.
                        if(runicDome && monster.curHp>0) groundedByrds.push_back(slot);
                        monster.moveHistory[1]=monster.moveHistory[0];
                        monster.moveHistory[0]=static_cast<std::int16_t>(sts::MonsterMoveId::BYRD_STUNNED);
                        // Native removes the grounded Byrd's Flight (STS_BYRD_GROUNDED_FLIGHT_FIX).
                        if(sts::byrdGroundedFlightFix())
                            monster.statusBits&=~(1ULL<<static_cast<int>(sts::MonsterStatus::FLIGHT));
                    }
                    --flight;
                    continue;
                }
                if(kindName=="MONSTER_REDUCE_PLATED_ARMOR") {
                    auto &plated=monster.smallPowers[7];
                    const bool removal=plated==1 && platedArmorRemovalQueue()
                        && monster.id!=static_cast<std::int16_t>(sts::MonsterId::SHELLED_PARASITE);
                    if(amount!=1 || !has(sts::MonsterStatus::PLATED_ARMOR) || (plated<=1 && !removal))
                        return unsupported("silver_selection_pending_actions");
                    --plated;
                    if(removal) monster.statusBits&=~(1ULL<<static_cast<int>(sts::MonsterStatus::PLATED_ARMOR));
                    continue;
                }
                if(amount<0 || amount>999) return unsupported("silver_selection_pending_actions");
                silver_bridge::PendingActionWire action;action.kind=K::MONSTER_GAIN_BLOCK;
                action.amount=amount;action.monster=slot;
                wire.pendingActionQueue.push_back(action);
                continue;
            }
            if(kindName=="LOSE_ENERGY") {
                // Java loses the energy only after the earlier tail items; the
                // fold is exact while none of them can gain energy.
                int amount=0;
                if(!voidEnergyQueue() || !requiredInt(entry,"amount",amount) || amount!=1
                        || std::any_of(wire.pendingActionQueue.begin(),wire.pendingActionQueue.end(),
                            [](const auto &item){return item.kind==K::GAIN_ENERGY;}))
                    return unsupported("silver_selection_pending_actions");
                wire.player.energy=std::max(0,wire.player.energy-amount);
                continue;
            }
            const auto kind=kinds.find(kindName);
            silver_bridge::PendingActionWire action;
            if(kind==kinds.end()) {
                if(kindName!="HEAL_PLAYER" || !selectionToyHealFix()
                        || !requiredInt(entry,"amount",action.amount) || action.amount!=5)
                    return unsupported("silver_selection_pending_actions");
                action.kind=K::HEAL_PLAYER;wire.pendingActionQueue.push_back(action);continue;
            }
            action.kind=kind->second;
            const bool noAmount=action.kind==K::GAMBLE || action.kind==K::UPGRADE_RANDOM || action.kind==K::USE_CARD
                || action.kind==K::REMOVE_PEN_NIB || action.kind==K::REMOVE_PLAYER_DEBUFFS;
            if(!noAmount && (!requiredInt(entry,"amount",action.amount) || action.amount<0 || action.amount>999
                    || (action.kind==K::DRAW && action.amount>10))) return unsupported("silver_selection_pending_actions");
            if(action.kind==K::USE_CARD) {
                const auto &current=wire.curCardQueueItem;
                const auto uuid=entry.value("uuid",std::string());
                const auto identity=context.cardIds.find(uuid);
                if(!sourceCard || ++cleanups!=1 || !wire.pendingCardQueueObserved
                        || !sourceSelectionOwner(static_cast<sts::CardSelectTask>(wire.cardSelect.task),static_cast<sts::CardId>(current.card.id))
                        || current.isEndTurn || !current.triggerOnUse || current.card.uniqueId<0
                        || identity==context.cardIds.end() || identity->second!=current.card.uniqueId
                        || entry.value("actionClass",std::string())!="com.megacrit.cardcrawl.actions.utility.UseCardAction"
                        || limbo.size()>1 || (limbo.size()==1 && indexedLimbo.front().uniqueId!=current.card.uniqueId))
                    return unsupported("silver_selection_pending_actions");
                for(const auto &[field,expected]:std::vector<std::pair<const char*,bool>>{{"unstarted",true},{"returnToHand",false},
                        {"reboundCard",false},{"triggerOnUse",true},{"exhaustOnUse",current.exhaustOnUse},
                        {"purgeOnUse",current.purgeOnUse},{"autoplay",current.autoplay}}) {
                    bool value;if(!requiredBool(entry,field,value) || value!=expected)return unsupported("silver_selection_pending_actions");
                }
                const auto contains=[&](const auto &pile){return std::any_of(pile.begin(),pile.end(),[&](const auto &card){return card.uniqueId==current.card.uniqueId;});};
                // Vanilla purge copies keep the original UUID. The producer
                // proved physical-object absence, while the original may
                // already be in discard during the copied selector.
                const bool purgeCopy=current.purgeOnUse && current.autoplay && current.ignoreEnergyTotal;
                if(!purgeCopy && (contains(wire.hand) || contains(wire.drawPile.unknown) || contains(wire.drawPile.knownTop)
                        || contains(wire.drawPile.knownBottom) || contains(wire.discardPile.unknown) || contains(wire.exhaustPile.unknown)))
                    return unsupported("silver_selection_pending_actions");
            }
            if(action.kind==K::SHUFFLE_WOUNDS && action.amount!=2)return unsupported("silver_selection_pending_actions");
            // Native Hex is a flag that always makes one Dazed.
            constexpr int hex=static_cast<int>(PlayerStatus::HEX);
            if(action.kind==K::SHUFFLE_DAZED && (!hexDazedQueue() || action.amount!=1
                    || !(hex<64 ? (wire.player.statusBits0>>hex)&1ULL : (wire.player.statusBits1>>(hex-64))&1U)))
                return unsupported("silver_selection_pending_actions");
            if(action.kind==K::DEBUFF_ALL_ENEMY) {
                const auto power=entry.value("power",std::string());
                const auto status=live_silver::monsterStatus(power);
                if(!status || !(power=="Vulnerable" && action.amount==1 || power=="Weakened" && action.amount==1 || power=="Poison" && action.amount==4)
                        || !requiredBool(entry,"sourceMonster",action.sourceMonster) || action.sourceMonster) return unsupported("silver_selection_pending_actions");
                action.status=static_cast<int>(*status);
            }
            if(action.kind==K::BUFF_PLAYER || action.kind==K::DEBUFF_PLAYER) {
                const auto power=entry.value("power",std::string());
                const std::set<std::string> buffs={"Strength","Dexterity","Artifact","Buffer","Plated Armor","Thorns","Vigor","IntangiblePlayer","Pen Nib"};
                const auto status=live_silver::playerStatus(power);
                if(!status || action.amount==0 || (power=="Pen Nib" && action.amount!=1) || (action.kind==K::BUFF_PLAYER?!buffs.count(power):!(power=="Flex" || power=="Weakened" && action.amount==1))
                        || !requiredBool(entry,"sourceMonster",action.sourceMonster) || action.sourceMonster)
                    return unsupported("silver_selection_pending_actions");
                action.status=static_cast<int>(*status);
            }
            wire.pendingActionQueue.push_back(action);
        }
        if(sourceCard && cleanups!=1)return unsupported("silver_selection_pending_actions");
        wire.pendingActionQueueObserved=true;
        // Pen Nib's counter-9 sentinel set the status bit above; while its
        // PenNibPower is still queued, native has not applied it yet.
        constexpr int penNib=static_cast<int>(PlayerStatus::PEN_NIB);
        const bool penNibPower=combat.contains("playerPowers") && std::any_of(combat.at("playerPowers").begin(),
            combat.at("playerPowers").end(),[](const auto &power){return power.value("id",std::string())=="Pen Nib";});
        if(penNibPendingFix() && !penNibPower && std::any_of(wire.pendingActionQueue.begin(),wire.pendingActionQueue.end(),
                [&](const auto &action){return action.kind==K::BUFF_PLAYER && action.status==penNib;}))
            wire.player.statusBits0&=~(1ULL<<penNib);
    }
    // An exhausted Mode Shift must come with its queued shift
    // (GUARDIAN_DEFENSIVE_SHIFT); Java resolves the shift before any other
    // decision, so anywhere else it is not a representable state.
    for(int i=0;i<wire.monsterCount;++i) {
        const auto &m=wire.monsters[i];
        if(!guardianShift && m.id==static_cast<std::int16_t>(sts::MonsterId::THE_GUARDIAN) && m.curHp>0
                && (m.statusBits & (1ULL<<static_cast<int>(sts::MonsterStatus::MODE_SHIFT))) && m.uniquePower0<=0)
            return unsupported(combat.contains("pendingActionQueue")?"silver_selection_pending_actions":"silver_unmapped_monster_power");
    }
    if(cardSelect && (selectionIt->value("continuation",std::string())=="public_actions"
            || selectionIt->value("continuation",std::string())=="toolbox_actions"
            || selectionIt->value("continuation",std::string())=="source_card_actions") && !wire.pendingActionQueueObserved)
        return unsupported("silver_selection_pending_actions");
    if (cardSelect && selectionIt->value("origin", std::string()) == "CARD_REWARD") {
        const auto continuation = selectionIt->value("continuation", std::string());
        const bool codex = continuation == "codex_end_turn" && wire.cardSelect.task == static_cast<std::int16_t>(sts::CardSelectTask::CODEX);
        if ((!codex && wire.cardSelect.task != static_cast<std::int16_t>(sts::CardSelectTask::DISCOVERY))
            || (!codex && continuation != "none" && continuation != "discovery_card" && continuation != "toolbox_draw" && continuation != "toolbox_actions" && continuation != "source_card_actions"
                && !(continuation == "public_actions" && cardRewardPublicActions() && wire.pendingActionQueueObserved))
            || wire.endTurnQueued || wire.turnHasEnded || (!codex && continuation!="source_card_actions" && !wire.pendingCardQueue.empty()))
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
        if (continuation=="toolbox_actions" && (wire.cardSelect.setCostToZero || wire.cardSelect.canPickZero
                || wire.cardSelect.data0!=1 || !wire.pendingActionQueueObserved
                || std::none_of(wire.pendingActionQueue.begin(),wire.pendingActionQueue.end(),[](const auto &action) {
                    return action.kind==silver_bridge::PendingActionKind::DRAW && action.amount>0;
                }))) return unsupported("silver_card_reward_pending_actions");
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
        } else if(continuation!="source_card_actions") {
            if (!limbo.empty()) return unsupported("silver_card_reward_pending_actions");
            // The producer proved that this potion offer has no interrupted
            // card cleanup. Its retained last queue item may name a completed
            // power/purged card, which is legitimately absent from all piles;
            // do not let generic card-selection replay execute it again.
            wire.curCardQueueItem = silver_bridge::CardQueueItemWire{};
            wire.curCardQueueItem.card.uniqueId = -1;
        }
    }

    if (cardSelect && ((selectionIt->value("origin",std::string()) == "GRID"
                && wire.cardSelect.task == static_cast<std::int16_t>(sts::CardSelectTask::LIQUID_MEMORIES_POTION))
            || (selectionIt->value("origin", std::string()) == "HAND_SELECT"
            && (wire.cardSelect.task == static_cast<std::int16_t>(sts::CardSelectTask::GAMBLE)
                || wire.cardSelect.task == static_cast<std::int16_t>(sts::CardSelectTask::EXHAUST_MANY))))) {
        const auto continuation = selectionIt->value("continuation", std::string());
        if (wire.endTurnQueued || wire.turnHasEnded) return unsupported("silver_selection_pending_actions");
        if (continuation == "none" || continuation == "public_actions") {
            if (!limbo.empty() || !wire.pendingCardQueue.empty()) return unsupported("silver_selection_pending_actions");
            wire.curCardQueueItem = silver_bridge::CardQueueItemWire{};
            wire.curCardQueueItem.card.uniqueId = -1;
        } else if (continuation != "source_card_actions" && (continuation != "purity_card"
                || wire.cardSelect.task != static_cast<std::int16_t>(sts::CardSelectTask::EXHAUST_MANY)
                || wire.curCardQueueItem.card.id != static_cast<std::int16_t>(sts::CardId::PURITY)))
            return unsupported("silver_selection_pending_actions");
    }

    wire.potionCount = std::count_if(wire.potions.begin(), wire.potions.end(), [](auto id) {
        return id != static_cast<std::int16_t>(sts::Potion::EMPTY_POTION_SLOT);
    });
    wire.version = silver_bridge::BattleStateWire::kVersion; wire.valid = true;
    wire.fullDrawOrderObserved = frozenEye; wire.intentsHidden = false;
    if(runicDome) {
        if(const auto reason=importBoundedRunicDome(combat,wire); !reason.empty()) return unsupported(reason);
        // Native Monster::damage cancels the deferred roll before the stun.
        for(const int slot:groundedByrds) {
            auto &m=wire.monsters[slot];
            m.pendingMoveRolls=0; m.pendingDirectMoveChoice=0; m.pendingRollInputs={};
            m.pendingRollInputHistory.clear(); m.pendingAttackPredicates.clear();
            m.moveHistory[1]=m.moveHistory[0];
            m.moveHistory[0]=static_cast<std::int16_t>(sts::MonsterMoveId::BYRD_STUNNED);
        }
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

int minionLeaderEscapeChoice(const json &observation) {
    if (!leaderEscapePassThrough()) return 0;
    // Every field is read type-checked: outside this one grid the mod sends
    // cardSelect as false, and any other shape must fall through to the
    // ordinary import (live problem 77).
    static const json missing;
    const auto field = [](const json &value, const char *key) -> const json & {
        if (!value.is_object()) return missing;
        const auto it = value.find(key);
        return it == value.end() ? missing : *it;
    };
    const auto text = [&](const json &value, const char *key) {
        const auto &v = field(value, key);
        return v.is_string() ? v.get<std::string>() : std::string();
    };
    const auto flag = [&](const json &value, const char *key) {
        const auto &v = field(value, key);
        return v.is_boolean() && v.get<bool>();
    };
    const auto &combat = field(observation, "combat").is_object()
        ? field(observation, "combat") : field(field(observation, "silverRoot"), "combat");
    if (!combat.is_object()) return 0;
    const auto &select = field(combat, "cardSelect");
    const auto &choices = field(select, "liveChoices");
    if (text(select, "task") != "HEADBUTT" || text(select, "origin") != "GRID"
        || text(select, "continuation") != "source_card_actions"
        || !choices.is_array() || choices.empty()) return 0;
    for (std::size_t i = 0; i < choices.size(); ++i) {
        const auto &index = field(choices[i], "choiceIndex");
        if (!field(choices[i], "uuid").is_string() || !index.is_number_integer()
            || index.get<long long>() != static_cast<long long>(i) + 1) return 0;
    }
    const auto &pending = field(combat, "pendingActionQueue");
    if (!pending.is_array() || pending.size() != 2
        || text(pending[0], "kind") != "USE_CARD" || text(pending[1], "kind") != "MINION_LEADER_ESCAPE") return 0;
    const auto &slots = field(pending[1], "slots");
    if (!slots.is_array() || slots.empty()) return 0;
    std::set<long long> escaping;
    for (const auto &slot : slots)
        if (!slot.is_number_integer() || !escaping.insert(slot.get<long long>()).second) return 0;
    const auto &monsters = field(combat, "monsters");
    if (!monsters.is_array()) return 0;
    int leaders = 0;
    std::set<long long> alive;
    for (std::size_t i = 0; i < monsters.size(); ++i) {
        const auto &m = monsters[i];
        if (!m.is_object()) return 0;
        const auto &slotField = field(m, "slot");
        const auto &idxField = field(m, "idx");
        const long long slot = slotField.is_number_integer() ? slotField.get<long long>()
            : idxField.is_number_integer() ? idxField.get<long long>() : static_cast<long long>(i);
        const auto id = live_silver::monsterId(text(m, "id"));
        const auto &hp = field(m, "hp");
        const bool gone = !hp.is_number() || hp.get<double>() <= 0 || flag(m, "dead")
            || flag(m, "escaping") || flag(m, "escaped") || flag(m, "halfDead");
        if (id == sts::MonsterId::GREMLIN_LEADER) {
            if (!gone) return 0;
            ++leaders;
        } else if (!gone) {
            if (id != sts::MonsterId::MAD_GREMLIN && id != sts::MonsterId::SNEAKY_GREMLIN && id != sts::MonsterId::FAT_GREMLIN
                && id != sts::MonsterId::SHIELD_GREMLIN && id != sts::MonsterId::GREMLIN_WIZARD) return 0;
            alive.insert(slot);
        }
    }
    return leaders == 1 && alive == escaping ? 1 : 0;
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
    const auto cardName = [](const silver_bridge::CardWire &card) {
        if (card.id <= 0) return std::string("Card");
        return std::string(sts::getCardName(static_cast<sts::CardId>(card.id))) + (card.upgraded ? "+" : "");
    };
    if (action.type == silver_bridge::SemanticActionType::SINGLE_CARD_SELECT) {
        // The overlay must say which card the selection picks (Armaments,
        // Headbutt, Exhume, Dual Wield, Attack Potion ...), not only that one is due.
        if (action.skipCardSelect) return "Select: skip";
        if (action.source == silver_bridge::CardSource::CARD_SELECT_OPTION)
            return "Select " + (action.optionCardId > 0
                ? std::string(sts::getCardName(static_cast<sts::CardId>(action.optionCardId))) : std::string("option"));
        return "Select " + cardName(action.card);
    }
    if (action.type == silver_bridge::SemanticActionType::MULTI_CARD_SELECT) {
        if (action.selectedCards.empty()) return "Select: none";
        std::string label = "Select ";
        for (std::size_t i = 0; i < action.selectedCards.size(); ++i)
            label += (i ? ", " : "") + cardName(action.selectedCards[i]);
        return label;
    }
    if (action.type != silver_bridge::SemanticActionType::CARD) return "Card selection";
    const std::string name = cardName(action.card);
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
        if (!monsters.is_array() || silverSlot >= 5) return std::nullopt;
        std::array<std::optional<int>,5> targets {};
        std::array<bool,5> seen {};
        int liveIndex = 0;
        for (std::size_t i = 0; i < monsters.size(); ++i) {
            const auto &monster = monsters[i];
            if (!monster.is_object() || !monster.contains("dead") || !monster["dead"].is_boolean())
                return std::nullopt;
            // Java's array follows the physical live list. Native slots can
            // have holes after a split/summon removes its original occupant.
            // Use the same explicit slot/idx contract as the root importer.
            for (const char *key : {"slot","idx"})
                if (monster.contains(key) && !monster[key].is_number_integer()) return std::nullopt;
            const int slot = monster.value("slot",monster.value("idx",static_cast<int>(i)));
            if (slot < 0 || slot >= 5 || seen[slot] || monster.value("idx",slot)!=slot)
                return std::nullopt;
            seen[slot]=true;
            if (!monster["dead"].get<bool>()) targets[slot]=++liveIndex;
        }
        return targets[silverSlot];
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
        if (cardSelect.value("task",std::string()) == "LIQUID_MEMORIES_POTION"
                && cardSelect.value("origin",std::string()) == "GRID") {
            std::map<std::string,int> choices;
            if (action.cardSelectTask != static_cast<std::int16_t>(sts::CardSelectTask::LIQUID_MEMORIES_POTION)
                    || action.source != silver_bridge::CardSource::DISCARD || action.selectedCards.size()!=2
                    || cardSelect.value("pickCount",0)!=2 || !liveSingleChoices(cardSelect,choices)) return nullptr;
            json uuids=json::array();
            for(const auto &card:action.selectedCards) {
                const auto uuid=uuidForId(card.uniqueId);
                if(!choices.count(uuid) || (!uuids.empty() && uuids[0]==uuid)) return nullptr;
                uuids.push_back(uuid);
            }
            return {{"kind","grid_card_select"},{"cardUuids",uuids}};
        }
        const auto task = live_silver::cardSelectTask(cardSelect.value("task", std::string()));
        if (task && (*task == sts::CardSelectTask::FORETHOUGHT || *task == sts::CardSelectTask::GAMBLE || *task == sts::CardSelectTask::EXHAUST_MANY)
            && cardSelect.value("origin", std::string()) == "HAND_SELECT") {
            std::map<std::string, int> choices;
            if (action.cardSelectTask != static_cast<std::int16_t>(*task)
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
            if (selected.size() > static_cast<std::size_t>(cardSelect.value("pickCount", 0))) return nullptr;
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
