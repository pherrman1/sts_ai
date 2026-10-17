#include "ritual_writhing_setup.h"
#include "combat_transition.h"
#include <algorithm>
#include <stdexcept>
#include <vector>

namespace one_combat {
namespace {
using namespace sts;
void require(bool ok, const char *message) {
    if (!ok) throw std::runtime_error(message);
}
nlohmann::json rngState(const GameContext &g) {
    nlohmann::json out = nlohmann::json::array();
    for (const Random *r : {&g.aiRng, &g.cardRandomRng, &g.cardRng, &g.eventRng,
         &g.mathUtilRng, &g.merchantRng, &g.miscRng, &g.monsterHpRng, &g.monsterRng,
         &g.neowRng, &g.potionRng, &g.relicRng, &g.shuffleRng, &g.treasureRng})
        out.push_back({r->counter, r->seed0, r->seed1});
    return out;
}
void validate(const GameContext &g) {
    const auto &d = g.deck;
    std::array<int,4> types{};
    int upgradeable = 0, transformable = 0;
    for (int i = 0; i < d.size(); ++i) {
        const auto &c = d.cards[i];
        const int type = static_cast<int>(c.getType());
        require(type >= 0 && type < 4, "controlled Ritual setup: invalid card type");
        if (c.getType() != CardType::CURSE || c.canTransform()) ++types[type];
        upgradeable += c.canUpgrade();
        transformable += c.canTransform() && !d.isCardBottled(i);
    }
    for (int type = 0; type < 3; ++type) {
        const int idx = d.bottleIdxs[type];
        require(idx == -1 || (idx >= 0 && idx < d.size()
            && static_cast<int>(d.cards[idx].getType()) == type),
            "controlled Ritual setup: invalid bottle index");
    }
    require(types == d.cardTypeCounts && upgradeable == d.upgradeableCount
            && transformable == d.transformableCount,
            "controlled Ritual setup: deck cache mismatch");
    require(g.potionCapacity >= 1 && g.potionCapacity <= static_cast<int>(g.potions.size()),
            "controlled Ritual setup: invalid potion capacity");
    int count = 0;
    for (int i = 0; i < static_cast<int>(g.potions.size()); ++i) {
        require(i < g.potionCapacity || g.potions[i] == Potion::EMPTY_POTION_SLOT,
                "controlled Ritual setup: potion outside active capacity");
        count += g.potions[i] != Potion::EMPTY_POTION_SLOT;
    }
    require(count == g.potionCount, "controlled Ritual setup: potion count mismatch");
}
}
std::optional<RitualWrithingSetup> parseRitualWrithingSetup(const std::string &name) {
    for (bool upgraded : {false, true}) for (int copies : {1,2})
        for (Potion potion : {Potion::EMPTY_POTION_SLOT, Potion::ENTROPIC_BREW, Potion::SMOKE_BOMB}) {
            const std::string expected = std::string("ritual_writhing_v2_")
                + (upgraded ? "upgraded_" : "base_") + (copies == 1 ? "single_" : "double_")
                + (potion == Potion::EMPTY_POTION_SLOT ? "natural" : potion == Potion::ENTROPIC_BREW ? "brew" : "smoke");
            if (name == expected) return RitualWrithingSetup{name, upgraded, copies, potion};
        }
    return std::nullopt;
}
nlohmann::json ritualWrithingDescriptor(const RitualWrithingSetup &s) {
    return {{"schema", "ritual_writhing_public_intervention_v1"}, {"researchOnly", true},
        {"setup", s.name}, {"upgraded", s.upgraded}, {"copies", s.copies},
        {"damageByOrdinal", s.copies == 1 ? nlohmann::json{15} : nlohmann::json{15,30}},
        {"forcedPotion", static_cast<int>(s.potion)},
        {"timing", "each_act3_hallway_before_predictor_and_raw_pre_capture"},
        {"daggerPolicy", "retain_first_remove_surplus_append_missing_reset_damage_and_upgrade"},
        {"potionPolicy", "held_then_lowest_free_else_last_active_overwrite_direct_even_sozu"},
        {"physicalIdentity", "current_master_deck_index_per_fight"},
        {"sourceGrouping", "sourceSeed_across_all_variants_and_fights"},
        {"changesSelectedActions", false}, {"consumesRng", false},
        {"rngStreamOrder", {"ai", "cardRandom", "card", "event", "mathUtil", "merchant", "misc",
            "monsterHp", "monster", "neow", "potion", "relic", "shuffle", "treasure"}},
        {"rootStages", "before_original_public_state_then_after_normalized_root_then_predictor_and_raw_pre"}};
}
nlohmann::json applyRitualWrithingSetup(sts::GameContext &gc, const RitualWrithingSetup &s) {
    const auto parsed = parseRitualWrithingSetup(s.name);
    require(parsed && parsed->upgraded == s.upgraded && parsed->copies == s.copies
            && parsed->potion == s.potion, "controlled Ritual setup: inconsistent descriptor");
    require(gc.act == 3 && gc.curRoom == Room::MONSTER && gc.screenState == ScreenState::BATTLE,
            "controlled Ritual setup: not an Act-3 hallway battle");
    validate(gc);
    // Commit only after every mutation and invariant has passed.
    GameContext next = gc;
    nlohmann::json receipt{{"originalEncounter", static_cast<int>(gc.info.encounter)},
        {"before", combatTransitionStateJson(captureCombatTransitionState(gc))},
        {"rngBefore", rngState(gc)}, {"operations", nlohmann::json::array()}};
    auto &ops = receipt["operations"];
    next.info.encounter = MonsterEncounter::WRITHING_MASS;
    std::vector<int> daggers;
    for (int i = 0; i < next.deck.size(); ++i)
        if (next.deck.cards[i].id == CardId::RITUAL_DAGGER) daggers.push_back(i);
    for (int i = static_cast<int>(daggers.size())-1; i >= s.copies; --i) {
        ops.push_back({{"kind", "remove"}, {"deckIndexBeforeRemoval", daggers[i]}});
        next.deck.remove(next, daggers[i]);
    }
    daggers.resize(std::min(static_cast<int>(daggers.size()), s.copies));
    while (static_cast<int>(daggers.size()) < s.copies) {
        require(next.deck.size() < Deck::MAX_SIZE, "controlled Ritual setup: deck capacity exceeded");
        const int idx = next.deck.size();
        Card card(CardId::RITUAL_DAGGER, s.upgraded);
        next.deck.cards.push_back(card);
        ++next.deck.cardTypeCounts[static_cast<int>(CardType::ATTACK)];
        ++next.deck.transformableCount;
        next.deck.upgradeableCount += card.canUpgrade();
        daggers.push_back(idx);
        ops.push_back({{"kind", "append_without_acquisition_hooks"}, {"deckIndex", idx}});
    }
    receipt["daggers"] = nlohmann::json::array();
    for (int ordinal = 0; ordinal < s.copies; ++ordinal) {
        const int idx = daggers[ordinal];
        auto &card = next.deck.cards[idx];
        const bool wasUpgradeable = card.canUpgrade();
        const int oldDamage = card.misc;
        const bool oldUpgrade = card.upgraded;
        card.upgraded = s.upgraded; card.misc = ordinal == 0 ? 15 : 30;
        next.deck.upgradeableCount += int(card.canUpgrade()) - int(wasUpgradeable);
        receipt["daggers"].push_back({{"ordinal", ordinal}, {"deckIndex", idx}, {"misc", card.misc}, {"upgraded", card.upgraded}});
        ops.push_back({{"kind", "reset"}, {"deckIndex", idx}, {"oldMisc", oldDamage},
            {"oldUpgraded", oldUpgrade}, {"misc", card.misc}, {"upgraded", card.upgraded}});
    }
    int slot = -1;
    std::string potionAction = "natural_unchanged";
    if (s.potion != Potion::EMPTY_POTION_SLOT) {
        for (int i = 0; i < next.potionCapacity; ++i) if (next.potions[i] == s.potion) { slot = i; break; }
        potionAction = "already_held";
        if (slot < 0) {
            for (int i = 0; i < next.potionCapacity; ++i)
                if (next.potions[i] == Potion::EMPTY_POTION_SLOT) { slot = i; break; }
            potionAction = slot < 0 ? "overwrite_last_active" : "fill_lowest_free";
            if (slot < 0) slot = next.potionCapacity-1;
            next.potions[slot] = s.potion;
            next.potionCount = 0;
            for (int i = 0; i < next.potionCapacity; ++i)
                next.potionCount += next.potions[i] != Potion::EMPTY_POTION_SLOT;
        }
    }
    receipt["potionOverride"] = {{"action", potionAction}, {"slot", slot},
        {"sozu", next.hasRelic(RelicId::SOZU)}, {"directPublicStatePlacement", true}};
    validate(next);
    receipt["after"] = combatTransitionStateJson(captureCombatTransitionState(next));
    receipt["rngAfter"] = rngState(next);
    require(receipt["rngBefore"] == receipt["rngAfter"], "controlled Ritual setup changed RNG");
    receipt["assertionsPassed"] = true;
    gc = std::move(next);
    return receipt;
}
bool guardRitualWrithingSource(const sts::GameContext &gc, std::uint64_t sourceSeed,
        const int &fightIdx, const std::string &stage, const nlohmann::json &attempt,
        nlohmann::json &failures, const std::function<void()> &work) {
    try { work(); return true; }
    catch (const std::exception &error) {
        failures.push_back({{"sourceSeed", sourceSeed}, {"fightIdx", fightIdx}, {"stage", stage},
            {"error", error.what()}, {"attempt", attempt}, {"terminalInvalid", true},
            {"stateAtFailure", combatTransitionStateJson(captureCombatTransitionState(gc))},
            {"rngAtFailure", rngState(gc)}});
    } catch (...) {
        failures.push_back({{"sourceSeed", sourceSeed}, {"fightIdx", fightIdx}, {"stage", stage},
            {"error", "unknown exception"}, {"attempt", attempt}, {"terminalInvalid", true},
            {"stateAtFailure", combatTransitionStateJson(captureCombatTransitionState(gc))},
            {"rngAtFailure", rngState(gc)}});
    }
    return false;
}

}
