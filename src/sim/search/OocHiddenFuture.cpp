// Moved unchanged from apps/one_combat/ooc_mcts_adapter.cpp (2026-11-17); see sim/search/OocHiddenFuture.h.
#include "sim/search/OocHiddenFuture.h"

#include <algorithm>
#include <cstdlib>
#include <string>
#include <map>
#include <memory>
#include <vector>

#include "constants/MonsterEncounters.h"
#include "constants/Misc.h"
#include "game/Game.h"
#include "game/Map.h"
#include "sim/search/OocMctsPlanner.h"

namespace sts::search {

GameContext detachedGameCopy(const GameContext &parent) {
    GameContext child = parent;
    if (parent.map) child.map = std::make_shared<sts::Map>(*parent.map);
    return child;
}
namespace {

    // STS_HIDDEN_LAYOUT_FIX: unset or 1 = resample the Match and Keep face-down layout and the rewards an event fight
    // rolled when it was chosen (2026-11-18, M1 of the Amber search review); 0 = the earlier sampler, which kept both
    // as the real run rolled them.
    bool hiddenLayoutFix() {
        static const bool on = [] {
            const char *v = std::getenv("STS_HIDDEN_LAYOUT_FIX");
            return !(v && std::string(v) == "0");
        }();
        return on;
    }

    // An event fight whose rewards were rolled when the fight was chosen (the engine keeps them in info, see
    // GameContext::chooseEventOption) and stay hidden until it ends: Colosseum's Nob fight (rare + uncommon relic),
    // Dead Adventurer (relic if one is left, gold), Mind Bloom's boss fight (rare relic), Mysterious Sphere (rare
    // screenless relic, gold), Masked Bandits (gold; the Red Mask relic is fixed) and the mushrooms (gold; Odd
    // Mushroom is fixed). The other event fights roll their rewards when they end.
    enum class EventFightReward { NONE, COLOSSEUM, DEAD_ADVENTURER, MINDBLOOM, MYSTERIOUS_SPHERE, MASKED_BANDITS,
                                  MUSHROOMS };

    EventFightReward eventFightReward(const GameContext &gc) {
        if (gc.screenState != sts::ScreenState::BATTLE || gc.curRoom != sts::Room::EVENT) return EventFightReward::NONE;
        switch (gc.curEvent) {
            case sts::Event::COLOSSEUM:
                return gc.info.eventData == 2 ? EventFightReward::COLOSSEUM : EventFightReward::NONE;
            case sts::Event::DEAD_ADVENTURER: return EventFightReward::DEAD_ADVENTURER;
            case sts::Event::MINDBLOOM: return EventFightReward::MINDBLOOM;
            case sts::Event::MYSTERIOUS_SPHERE: return EventFightReward::MYSTERIOUS_SPHERE;
            case sts::Event::MASKED_BANDITS: return EventFightReward::MASKED_BANDITS;
            case sts::Event::HYPNOTIZING_COLORED_MUSHROOMS: return EventFightReward::MUSHROOMS;
            default: return EventFightReward::NONE;
        }
    }

    // Put a hidden pre-rolled relic back into its pool (the pool shuffle that follows hides where it was).
    void returnToPool(GameContext &gc, sts::RelicId r) {
        std::vector<sts::RelicId> *pool = nullptr;
        switch (sts::getRelicTier(r)) {
            case sts::RelicTier::COMMON: pool = &gc.commonRelicPool; break;
            case sts::RelicTier::UNCOMMON: pool = &gc.uncommonRelicPool; break;
            case sts::RelicTier::RARE: pool = &gc.rareRelicPool; break;
            case sts::RelicTier::SHOP: pool = &gc.shopRelicPool; break;
            case sts::RelicTier::BOSS: pool = &gc.bossRelicPool; break;
            default: return;   // an empty-pool fallback (Circlet): nothing left the pool
        }
        pool->push_back(r);
    }

    bool isMatchAndKeep(const GameContext &gc) {
        return gc.screenState == sts::ScreenState::EVENT_SCREEN && gc.curEvent == sts::Event::MATCH_AND_KEEP
            && gc.info.toSelectCards.size() == 12;
    }

    int unseenMatchSlots(const GameContext &gc) {
        if (!isMatchAndKeep(gc)) return 0;
        int n = 0;
        for (const auto &c : gc.info.toSelectCards) n += c.deckIdx == GameContext::MATCH_AND_KEEP_UNSEEN;
        return n;
    }

    using CardKey = std::pair<int, int>;   // card id, upgraded
    CardKey key(const sts::Card &c) { return {static_cast<int>(c.id), c.upgraded ? 1 : 0}; }

    // Match and Keep deals two copies each of a class rare, uncommon and common card, a colorless uncommon (a curse
    // from A15), a curse and the class's starter card, shuffled into 12 face-down slots; flipping a slot uses no RNG.
    // Re-deal what the player has not seen from its posterior: roles seen keep their card, unseen class and
    // colorless roles are drawn fresh, the curse roles (which can hold the same curse twice) are drawn by rejection
    // with the likelihood of the seen slots, and the cards left over are shuffled over the unseen slots.
    void resampleMatchAndKeep(GameContext &gc, std::mt19937_64 &rng) {
        auto &slots = gc.info.toSelectCards;
        std::vector<int> unseen;
        std::map<CardKey, int> seen;      // card -> slots showing it
        std::map<CardKey, sts::Card> cardOf;
        for (int i = 0; i < 12; ++i) {
            if (slots[i].deckIdx == GameContext::MATCH_AND_KEEP_UNSEEN) { unseen.push_back(i); continue; }
            ++seen[key(slots[i].card)];
            cardOf[key(slots[i].card)] = slots[i].card;
        }
        if (unseen.empty()) return;
        const bool unfavorable = gc.ascension >= 15;
        // Roles 0..5 as dealt in GameContext::setupEvent.
        std::array<sts::Card, 6> role{};
        std::array<bool, 6> known{};
        std::vector<CardKey> seenCurses;
        for (const auto &[k, n] : seen) {
            const sts::Card c = cardOf[k];
            if (n > (c.getType() == sts::CardType::CURSE && unfavorable ? 4 : 2))
                throw OocSearchUnsupported("invalid_match_and_keep");
            int r = -1;
            if (c.getType() == sts::CardType::CURSE) { seenCurses.push_back(k); continue; }
            switch (c.getRarity()) {
                case sts::CardRarity::RARE: r = 0; break;
                case sts::CardRarity::UNCOMMON:
                    r = sts::getCardColor(c.id) == sts::CardColor::COLORLESS ? 3 : 1; break;
                case sts::CardRarity::COMMON: r = 2; break;
                case sts::CardRarity::BASIC: r = 5; break;
                default: break;
            }
            if (r < 0 || known[r] || (r == 3 && unfavorable)) throw OocSearchUnsupported("invalid_match_and_keep");
            role[r] = c;
            known[r] = true;
        }
        sts::Random cardRng(rng());
        const sts::CardRarity classRarity[3] = {sts::CardRarity::RARE, sts::CardRarity::UNCOMMON, sts::CardRarity::COMMON};
        for (int r = 0; r < 3; ++r)
            if (!known[r]) role[r] = gc.previewObtainCard(sts::getRandomClassCardOfRarity(cardRng, gc.cc, classRarity[r]));
        if (!unfavorable && !known[3]) role[3] = gc.previewObtainCard(gc.returnColorlessCard(sts::CardRarity::UNCOMMON));
        if (!known[5]) role[5] = gc.previewObtainCard(sts::getStartCardForEvent(gc.cc));
        // Curse roles: 4 (and 3 from A15). Weight of a draw = prod over seen curses of n!/(n-o)! (ordered ways the seen
        // slots can show them), bounded by the same with n at its maximum.
        const auto falling = [](int n, int o) { double f = 1; for (int i = 0; i < o; ++i) f *= n - i; return f; };
        const int maxCopies = unfavorable ? 4 : 2;
        double bound = 1;
        for (const auto &k : seenCurses) bound *= falling(maxCopies, seen[k]);
        std::uniform_real_distribution<double> u(0.0, 1.0);
        for (int tries = 0;; ++tries) {
            if (tries > 200000) throw OocSearchUnsupported("match_and_keep_resample");
            const sts::Card c4 = sts::getRandomCurse(cardRng);
            const sts::Card c3 = unfavorable ? sts::Card(sts::getRandomCurse(cardRng)) : role[3];
            double w = 1;
            for (const auto &k : seenCurses) {
                const int n = 2 * (key(c4) == k) + 2 * (unfavorable && key(c3) == k);
                w *= falling(n, seen[k]);
            }
            if (w > 0 && u(rng) * bound < w) {
                role[4] = c4;
                if (unfavorable) role[3] = c3;
                break;
            }
        }
        // The deal's cards minus those showing, shuffled over the unseen slots.
        std::map<CardKey, int> left;
        for (const auto &c : role) left[key(c)] += 2, cardOf[key(c)] = c;
        for (const auto &[k, n] : seen)
            if ((left[k] -= n) < 0) throw OocSearchUnsupported("invalid_match_and_keep");
        std::vector<sts::Card> rest;
        for (const auto &[k, n] : left)
            for (int i = 0; i < n; ++i) rest.push_back(cardOf[k]);
        if (rest.size() != unseen.size()) throw OocSearchUnsupported("invalid_match_and_keep");
        std::shuffle(rest.begin(), rest.end(), rng);
        for (std::size_t i = 0; i < unseen.size(); ++i) slots[unseen[i]].card = rest[i];
    }

}

// Re-determinize only a detached hypothetical state. Published offers, the
// current map/boss, selected cards, and observed encounter history stay fixed.
// A fresh seed also covers native per-floor RNG resets and next-act map setup.
void sampleNoncombatFuture(GameContext &gc, std::mt19937_64 &rng) {
    gc.seed = rng();
    for (auto stream : {&gc.aiRng, &gc.cardRandomRng, &gc.cardRng, &gc.eventRng,
            &gc.mathUtilRng, &gc.merchantRng, &gc.miscRng, &gc.monsterHpRng,
            &gc.monsterRng, &gc.neowRng, &gc.potionRng, &gc.relicRng,
            &gc.shuffleRng, &gc.treasureRng}) {
        const auto counter = stream->counter;
        *stream = sts::Random(rng());
        stream->counter = counter; // native thresholds depend on past draw counts
    }
    // Relics an event fight rolled when it was chosen are hidden until it ends: back into their pools, drawn
    // again below from the shuffled pools.
    const auto fightReward = hiddenLayoutFix() ? eventFightReward(gc) : EventFightReward::NONE;
    if (fightReward == EventFightReward::COLOSSEUM) {
        returnToPool(gc, gc.info.bossRelics[1]);
        returnToPool(gc, gc.info.bossRelics[0]);
    } else if ((fightReward == EventFightReward::DEAD_ADVENTURER || fightReward == EventFightReward::MINDBLOOM
                || fightReward == EventFightReward::MYSTERIOUS_SPHERE)
               && gc.info.bossRelics[0] != sts::RelicId::INVALID) {
        returnToPool(gc, gc.info.bossRelics[0]);
    }
    const auto shuffleUnknown = [&](auto &pool) {
        // Canonicalize first so the actual hidden ordering cannot affect samples.
        std::sort(pool.begin(), pool.end());
        std::shuffle(pool.begin(), pool.end(), rng);
    };
    for (auto pool : {&gc.commonRelicPool, &gc.uncommonRelicPool, &gc.rareRelicPool,
                     &gc.shopRelicPool, &gc.bossRelicPool}) shuffleUnknown(*pool);
    shuffleUnknown(gc.colorlessCardPool);
    // Event pools are eligible sets, not queues. Canonical order removes any
    // dependence on an unobserved representation without changing membership.
    std::sort(gc.eventList.begin(), gc.eventList.end());
    std::sort(gc.shrineList.begin(), gc.shrineList.end());
    std::sort(gc.specialOneTimeEventList.begin(), gc.specialOneTimeEventList.end());
    if (gc.act >= 1 && gc.act <= 3) {
        const int count = gc.monsterList.size();
        if (gc.monsterListOffset < 0 || gc.monsterListOffset > count
            || gc.eliteMonsterListOffset < 0 || gc.eliteMonsterListOffset > gc.eliteMonsterList.size())
            throw OocSearchUnsupported("invalid_hidden_encounter_history");
        const int weakCount = gc.act == 1 ? 3 : 2;
        gc.monsterList.resize(gc.monsterListOffset);
        for (int i = gc.monsterListOffset; i < count; ++i) {
            const int act = gc.act - 1;
            if (i < weakCount)
                gc.populateMonsterList(sts::MonsterEncounterPool::weakEnemies[act],
                    sts::MonsterEncounterPool::weakWeights[act], sts::MonsterEncounterPool::weakCount[act], 1);
            else if (i == weakCount)
                gc.populateFirstStrongEnemy(sts::MonsterEncounterPool::strongEnemies[act],
                    sts::MonsterEncounterPool::strongWeights[act], sts::MonsterEncounterPool::strongCount[act]);
            else
                gc.populateMonsterList(sts::MonsterEncounterPool::strongEnemies[act],
                    sts::MonsterEncounterPool::strongWeights[act], sts::MonsterEncounterPool::strongCount[act], 1);
        }
        for (int i = gc.eliteMonsterListOffset; i < gc.eliteMonsterList.size(); ++i) {
            sts::MonsterEncounter draw;
            do { draw = sts::MonsterEncounterPool::elites[gc.act-1][gc.monsterRng.random(2)]; }
            while (i > 0 && draw == gc.eliteMonsterList[i-1]);
            gc.eliteMonsterList[i] = draw;
        }
        // The second A20 boss is hidden until the first boss falls; once its
        // fight has started (a BATTLE leaf after a sampled first-boss win) it is
        // revealed, and Silver reads gc.secondBoss to recognise the final fight.
        const bool secondBossRevealed = gc.screenState == sts::ScreenState::BATTLE
            && gc.info.encounter == gc.secondBoss;
        if (gc.act == 3 && gc.ascension >= 20 && !secondBossRevealed) {
            const sts::MonsterEncounter bosses[] = {sts::MonsterEncounter::AWAKENED_ONE,
                sts::MonsterEncounter::TIME_EATER, sts::MonsterEncounter::DONU_AND_DECA};
            do { gc.secondBoss = bosses[gc.monsterRng.random(2)]; } while (gc.secondBoss == gc.boss);
        }
    }
    if (gc.screenState == sts::ScreenState::TREASURE_ROOM) {
        // Chest size is visible; contents are not. Keep native gold/tier
        // correlation from the single roll used by setupTreasureRoom().
        const int size = int(gc.info.chestSize);
        if (size < 0 || size >= 3) throw OocSearchUnsupported("invalid_hidden_chest");
        const int roll = gc.treasureRng.random(99);
        gc.info.haveGold = roll < sts::chestGoldChances[size];
        const auto chances = sts::chestRelicTierChances[size];
        gc.info.tier = roll < chances[0] ? sts::RelicTier::COMMON
            : roll < chances[0] + chances[1] ? sts::RelicTier::UNCOMMON : sts::RelicTier::RARE;
    }
    if (gc.screenState == sts::ScreenState::EVENT_SCREEN && gc.curEvent == sts::Event::DEAD_ADVENTURER) {
        // The description reveals the encounter, but unsearched rewards remain hidden.
        if (gc.info.phase < 0 || gc.info.phase > int(gc.info.rewards.size()))
            throw OocSearchUnsupported("invalid_hidden_event_history");
        auto first = gc.info.rewards.begin() + gc.info.phase;
        std::sort(first, gc.info.rewards.end());
        std::shuffle(first, gc.info.rewards.end(), rng);
    }
    // The same draws as GameContext::chooseEventOption, from the resampled streams and pools.
    switch (fightReward) {
        case EventFightReward::COLOSSEUM:
            gc.info.bossRelics[0] = gc.returnRandomRelic(sts::RelicTier::RARE);
            gc.info.bossRelics[1] = gc.returnRandomRelic(sts::RelicTier::UNCOMMON);
            break;
        case EventFightReward::DEAD_ADVENTURER: {
            // Every reward not yet found comes with the fight, so which ones is known; amounts and relic are not.
            if (gc.info.phase < 0 || gc.info.phase > 3) throw OocSearchUnsupported("invalid_hidden_event_history");
            int gold = gc.miscRng.random(25, 35);
            bool relic = false;
            for (int i = gc.info.phase; i < 3; ++i) {
                if (gc.info.rewards[i] == 0) gold += 30;
                else if (gc.info.rewards[i] == 2) relic = true;
            }
            gc.info.gold = gold;
            gc.info.bossRelics[0] = relic ? gc.returnRandomRelic(sts::returnRandomRelicTier(gc.relicRng, 1))
                                          : sts::RelicId::INVALID;
            break;
        }
        case EventFightReward::MINDBLOOM:
            gc.info.bossRelics[0] = gc.returnRandomRelic(sts::RelicTier::RARE);
            break;
        case EventFightReward::MYSTERIOUS_SPHERE:
            gc.info.gold = gc.miscRng.random(45, 55);
            gc.info.bossRelics[0] = gc.returnRandomScreenlessRelic(sts::RelicTier::RARE);
            break;
        case EventFightReward::MASKED_BANDITS:
            gc.info.gold = gc.miscRng.random(25, 35);
            break;
        case EventFightReward::MUSHROOMS:
            gc.info.gold = gc.miscRng.random(20, 30);
            break;
        case EventFightReward::NONE: break;
    }
    if (hiddenLayoutFix() && isMatchAndKeep(gc)) resampleMatchAndKeep(gc, rng);
}

namespace {
    template <class F> void forStreams(F &&f, const GameContext &gc) {
        int i = 0;
        for (auto stream : {&gc.aiRng, &gc.cardRandomRng, &gc.cardRng, &gc.eventRng,
                &gc.mathUtilRng, &gc.merchantRng, &gc.miscRng, &gc.monsterHpRng,
                &gc.monsterRng, &gc.neowRng, &gc.potionRng, &gc.relicRng,
                &gc.shuffleRng, &gc.treasureRng}) f(i++, *stream);
    }
}

OocHiddenSnapshot captureOocHidden(const GameContext &gc) {
    OocHiddenSnapshot s;
    forStreams([&](int i, const sts::Random &r) { s.streams[i] = r; }, gc);
    s.relicPoolSizes = {static_cast<int>(gc.commonRelicPool.size()), static_cast<int>(gc.uncommonRelicPool.size()),
                        static_cast<int>(gc.rareRelicPool.size()), static_cast<int>(gc.shopRelicPool.size()),
                        static_cast<int>(gc.bossRelicPool.size())};
    s.colorless = gc.colorlessCardPool;
    s.monsterListSize = gc.monsterList.size();
    s.monsterListOffset = gc.monsterListOffset;
    s.eliteListSize = gc.eliteMonsterList.size();
    s.eliteListOffset = gc.eliteMonsterListOffset;
    s.secondBoss = gc.secondBoss;
    s.act = gc.act;
    s.matchUnseen = unseenMatchSlots(gc);
    s.matchAndKeep = isMatchAndKeep(gc);
    s.eventFightReward = eventFightReward(gc) != EventFightReward::NONE;
    return s;
}

bool oocStepRevealsHidden(const OocHiddenSnapshot &before, const GameContext &after) {
    if (after.screenState == sts::ScreenState::BATTLE && after.outcome == sts::GameOutcome::UNDECIDED) return true;
    // A Match and Keep flip shows a face-down card (leaving the event conservatively counts as one).
    if (before.matchAndKeep && before.matchUnseen > 0
        && (!isMatchAndKeep(after) || unseenMatchSlots(after) < before.matchUnseen)) return true;
    // The end of an event fight shows the rewards rolled when it was chosen.
    if (before.eventFightReward && eventFightReward(after) == EventFightReward::NONE) return true;
    if (after.act != before.act || after.secondBoss != before.secondBoss) return true;
    if (after.monsterList.size() != before.monsterListSize || after.monsterListOffset != before.monsterListOffset
        || after.eliteMonsterList.size() != before.eliteListSize
        || after.eliteMonsterListOffset != before.eliteListOffset) return true;
    const std::array<int, 5> pools = {static_cast<int>(after.commonRelicPool.size()),
        static_cast<int>(after.uncommonRelicPool.size()), static_cast<int>(after.rareRelicPool.size()),
        static_cast<int>(after.shopRelicPool.size()), static_cast<int>(after.bossRelicPool.size())};
    if (pools != before.relicPoolSizes || after.colorlessCardPool != before.colorless) return true;
    // forStreams order: 1 card-random, 6 misc, 12 shuffle (the three a new floor reseeds out of combat). They share
    // one state in the vanilla game and have one each with GameContext::rngFix.
    const sts::Random reseededCardRandom = after.floorRng(GameContext::FLOOR_CARD_RANDOM);
    const sts::Random reseededMisc = after.floorRng(GameContext::FLOOR_MISC);
    const sts::Random reseededShuffle = after.floorRng(GameContext::FLOOR_SHUFFLE);
    bool used = false;
    forStreams([&](int i, const sts::Random &r) {
        if (r == before.streams[i]) return;
        // a new floor's reseed of misc / shuffle / card-random, nothing drawn
        if (after.rngFix ? (i == 1 && r == reseededCardRandom) || (i == 6 && r == reseededMisc)
                               || (i == 12 && r == reseededShuffle)
                         : r == reseededMisc) return;
        used = true;
    }, after);
    return used;
}

}

