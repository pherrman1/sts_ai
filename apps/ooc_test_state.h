#ifndef STS_LIGHTSPEED_OOC_TEST_STATE_H
#define STS_LIGHTSPEED_OOC_TEST_STATE_H

#include <iomanip>
#include <iterator>
#include <locale>
#include <sstream>
#include <string>
#include <type_traits>

#include "game/GameContext.h"

namespace sts::test {
namespace ooc_state_detail {

// Structured values, not object bytes: no padding, addresses, capacities, or
// unused fixed_list backing storage participate in equality. Fixtures must
// initialize GameContext (including seed, cc and Neow options) before use.
class Writer {
    std::ostringstream out;
public:
    Writer() {
        out.imbue(std::locale::classic());
        out << std::hexfloat;
    }

    template<class T>
    void value(const T &v) {
        if constexpr (std::is_enum_v<T>) {
            out << +static_cast<std::underlying_type_t<T>>(v) << ';';
        } else {
            out << +v << ';';
        }
    }

    void value(const Card &c) { values(c.id, c.misc, c.upgraded); }
    void value(const SelectScreenCard &c) { value(c.card); value(c.deckIdx); }
    void value(const RelicInstance &r) { values(r.id, r.data); }
    void value(const Random &r) { values(r.counter, r.seed0, r.seed1); }
    void value(const Neow::Option &n) { values(n.r, n.d); }
    void value(const CardReward &r) { sequence(r); }

    template<class... Ts>
    void values(const Ts &...vs) { (value(vs), ...); }

    template<class Range>
    void sequence(const Range &r) {
        out << '[';
        value(std::size(r));
        for (const auto &v : r) value(v);
        out << ']';
    }

    void value(const Rewards &r) {
        values(r.goldRewardCount, r.cardRewardCount, r.relicCount, r.potionCount,
               r.emeraldKey, r.sapphireKey);
        // These arrays have deterministic initialized values, even for inactive
        // entries. CardReward's own fixed_list storage is restricted to its size.
        sequence(r.gold);
        sequence(r.cardRewards);
        sequence(r.relics);
        sequence(r.potions);
    }

    void value(const Shop &s) {
        sequence(s.prices);
        value(s.removeCost);
        sequence(s.cards);
        sequence(s.potions);
        sequence(s.relics);
    }

    void value(const MapNode &n) {
        values(n.x, n.y, n.parentCount, n.edgeCount, n.room);
        sequence(n.parents);
        sequence(n.edges);
    }

    void value(const ScreenStateInfo &s) {
        values(s.encounter, s.transformRng, s.selectScreenType, s.toSelectCount);
        sequence(s.toSelectCards);
        sequence(s.haveSelectedCards);
        values(s.eventData, s.hpAmount0, s.hpAmount1, s.hpAmount2, s.phase);
        sequence(s.rewards);
        values(s.upgradeOne, s.cleanUpIsRemoveCard, s.haveGold, s.chestSize,
               s.tier, s.goldLoss, s.potionIdx, s.gold, s.cardIdx,
               s.relicIdx0, s.relicIdx1, s.skillCardDeckIdx,
               s.powerCardDeckIdx, s.attackCardDeckIdx);
        sequence(s.bossRelics);
        sequence(s.neowRewards);
        value(s.rewardsContainer);
        value(s.stolenGold);
        value(s.shop);
    }

    std::string finish() const { return out.str(); }
};
} // namespace ooc_state_detail

// Equality fingerprint for semantic-vs-primitive parity and non-mutation tests.
// Callback presence is observable here; callback captures/type erasure cannot
// be compared portably. Tests must also execute each continuation and compare
// its resulting state. Map ownership identity is intentionally not game state.
inline std::string oocStateFingerprint(const GameContext &g) {
    ooc_state_detail::Writer w;
    w.values(g.noteForYourselfCard, g.skipBattles, g.seed,
             g.aiRng, g.cardRandomRng, g.cardRng, g.eventRng, g.mathUtilRng,
             g.merchantRng, g.miscRng, g.monsterHpRng, g.monsterRng, g.neowRng,
             g.potionRng, g.relicRng, g.shuffleRng, g.treasureRng);
    w.sequence(g.eventList);
    w.sequence(g.shrineList);
    w.sequence(g.specialOneTimeEventList);
    w.sequence(g.commonRelicPool);
    w.sequence(g.uncommonRelicPool);
    w.sequence(g.rareRelicPool);
    w.sequence(g.shopRelicPool);
    w.sequence(g.bossRelicPool);
    w.sequence(g.colorlessCardPool);
    w.value(g.monsterListOffset);
    w.sequence(g.monsterList);
    w.value(g.eliteMonsterListOffset);
    w.sequence(g.eliteMonsterList);
    w.values(g.secondBoss, g.outcome, g.screenState, g.info,
             g.lastRoom, g.curEvent, g.curRoom, g.boss,
             g.monsterChance, g.shopChance, g.treasureChance,
             g.potionChance, g.cardRarityFactor, g.shopRemoveCount, g.speedrunPace,
             g.curMapNodeX, g.curMapNodeY, static_cast<bool>(g.map));
    if (g.map) {
        w.values(g.map->burningEliteX, g.map->burningEliteY, g.map->burningEliteBuff);
        for (const auto &row : g.map->nodes) w.sequence(row);
    }
    w.values(g.act, g.ascension, g.floorNum, g.cc, g.curHp, g.maxHp, g.gold,
             g.potionCount, g.potionCapacity, g.wingBootsCharges);
    w.sequence(g.potions);
    w.sequence(g.relics.relics);
    w.values(g.relics.relicBits0, g.relics.relicBits1, g.relics.relicBits2);
    w.sequence(g.deck.cards);
    w.sequence(g.deck.cardTypeCounts);
    w.sequence(g.deck.bottleIdxs);
    w.values(g.deck.upgradeableCount, g.deck.transformableCount,
             g.blueKey, g.greenKey, g.redKey,
             static_cast<bool>(g.regainControlAction), g.smokeBombUsed);
    return w.finish();
}

inline GameContext cloneOocTestState(const GameContext &source) {
    GameContext copy = source;
    if (source.map) copy.map = std::make_shared<Map>(*source.map);
    return copy;
}

} // namespace sts::test
#endif // STS_LIGHTSPEED_OOC_TEST_STATE_H
