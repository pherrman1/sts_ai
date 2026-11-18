// Hidden state the run already rolled but the player has not seen is resampled by search::sampleNoncombatFuture, and
// the out-of-combat chance rule (search::oocStepRevealsHidden) calls its reveal a chance step:
//
//  * Match and Keep: the face-down layout (and the identity of cards never flipped). Two states with the same public
//    view (slot states and the cards seen) but different hidden layouts must resample to the same state with the
//    same sampler seed, so a search cannot read the real layout. Flipping a face-down card is a reveal.
//  * Event fights whose rewards were rolled when the fight was chosen (Colosseum's Nobs, Dead Adventurer, Mind
//    Bloom, Mysterious Sphere): two states that differ only in the hidden relic (and gold) resample to the same
//    rewards. The fight's end is a reveal, and the rewards shown are the ones in the state.
//
// usage: hidden_layout_resample_test [seeds=200]
#include "game/Game.h"
#include "sim/search/OocHiddenFuture.h"
#include "sim/search/OocMctsPlanner.h"

#include <algorithm>
#include <cstdlib>
#include <iostream>
#include <map>
#include <random>
#include <vector>

using namespace sts;
using namespace sts::search;

namespace {

    int g_fail = 0;
    void check(bool ok, const char *what, std::uint64_t seed) {
        if (!ok && ++g_fail <= 30) std::cerr << "FAIL: " << what << " (seed " << seed << ")\n";
    }

    bool sameSlots(const GameContext &a, const GameContext &b) {
        if (a.info.toSelectCards.size() != b.info.toSelectCards.size()) return false;
        for (int i = 0; i < static_cast<int>(a.info.toSelectCards.size()); ++i) {
            const auto &x = a.info.toSelectCards[i], &y = b.info.toSelectCards[i];
            if (x.deckIdx != y.deckIdx || x.card.id != y.card.id || x.card.upgraded != y.card.upgraded) return false;
        }
        return true;
    }

    bool resampleEqual(const GameContext &a, const GameContext &b, std::uint64_t s, bool slots, bool rewards) {
        GameContext x = detachedGameCopy(a), y = detachedGameCopy(b);
        std::mt19937_64 rx(s), ry(s);
        sampleNoncombatFuture(x, rx);
        sampleNoncombatFuture(y, ry);
        if (slots && !sameSlots(x, y)) return false;
        if (rewards) {
            for (int i = 0; i < 2; ++i) if (x.info.bossRelics[i] != y.info.bossRelics[i]) return false;
            if (x.info.gold != y.info.gold) return false;
            if (x.commonRelicPool != y.commonRelicPool || x.uncommonRelicPool != y.uncommonRelicPool
                || x.rareRelicPool != y.rareRelicPool || x.shopRelicPool != y.shopRelicPool) return false;
            x.afterBattle();
            y.afterBattle();
            const auto &rx2 = x.info.rewardsContainer, &ry2 = y.info.rewardsContainer;
            if (rx2.relicCount != ry2.relicCount || rx2.goldRewardCount != ry2.goldRewardCount) return false;
            for (int i = 0; i < rx2.relicCount; ++i) if (rx2.relics[i] != ry2.relics[i]) return false;
            for (int i = 0; i < rx2.goldRewardCount; ++i) if (rx2.gold[i] != ry2.gold[i]) return false;
        }
        return true;
    }

    // ---- Match and Keep ----
    void matchAndKeep(std::uint64_t seed, long &differing, long &flipsChecked) {
        GameContext gc(CharacterClass::IRONCLAD, seed, 20);
        gc.curRoom = Room::EVENT;
        gc.curEvent = Event::MATCH_AND_KEEP;
        gc.setupEvent();
        std::mt19937 rng(static_cast<unsigned>(seed));
        const int clicks = static_cast<int>(rng() % 10);
        for (int c = 0; c < clicks && gc.screenState == ScreenState::EVENT_SCREEN; ++c) {
            std::vector<int> ok;
            for (int i = 0; i < 12; ++i) {
                const int st = gc.info.toSelectCards[i].deckIdx;
                if (st != GameContext::MATCH_AND_KEEP_MATCHED && st != GameContext::MATCH_AND_KEEP_FACE_UP) ok.push_back(i);
            }
            const int idx = ok[rng() % ok.size()];
            const int before = gc.info.toSelectCards[idx].deckIdx;
            const auto snap = captureOocHidden(gc);
            gc.chooseMatchAndKeepSlot(idx);
            const bool revealed = oocStepRevealsHidden(snap, gc);
            if (before == GameContext::MATCH_AND_KEEP_UNSEEN) check(revealed, "a face-down flip is not a reveal", seed);
            else if (gc.screenState == ScreenState::EVENT_SCREEN && !revealed) ++flipsChecked;
            else if (gc.screenState == ScreenState::EVENT_SCREEN) check(false, "flipping a seen card is a reveal", seed);
        }
        if (gc.screenState != ScreenState::EVENT_SCREEN) return;
        // Another hidden layout with the same public view: shuffle the face-down cards over the face-down slots and
        // swap every card never seen (both, or all four, of its copies) for another of its kind.
        GameContext alt = gc;
        auto &slots = alt.info.toSelectCards;
        std::vector<int> unseen;
        std::map<int, int> seenIds;
        for (int i = 0; i < 12; ++i) {
            if (slots[i].deckIdx == GameContext::MATCH_AND_KEEP_UNSEEN) unseen.push_back(i);
            else ++seenIds[static_cast<int>(slots[i].card.id)];
        }
        std::vector<Card> cards;
        for (int i : unseen) cards.push_back(slots[i].card);
        std::shuffle(cards.begin(), cards.end(), rng);
        std::map<int, Card> swap;
        Random r(seed * 31 + 7);
        for (const auto &c : cards) {
            const int id = static_cast<int>(c.id);
            if (seenIds.count(id) || swap.count(id) || c.getRarity() == CardRarity::BASIC) continue;
            Card other = c;
            for (int t = 0; t < 50 && other.id == c.id; ++t)
                other = c.getType() == CardType::CURSE ? Card(getRandomCurse(r))
                                                       : alt.previewObtainCard(getRandomClassCardOfRarity(r, alt.cc, c.getRarity()));
            bool clash = false;   // keep the deal's shape: no swap onto a card already in it
            for (const auto &s : slots) clash = clash || s.card.id == other.id;
            if (!clash) swap[id] = other;
        }
        for (auto &c : cards) if (swap.count(static_cast<int>(c.id))) c = swap[static_cast<int>(c.id)];
        for (std::size_t i = 0; i < unseen.size(); ++i) slots[unseen[i]].card = cards[i];
        if (!sameSlots(gc, alt)) ++differing;
        for (std::uint64_t s = 1; s <= 4; ++s)
            check(resampleEqual(gc, alt, seed * 1000 + s, true, false),
                  "Match and Keep resample depends on the hidden layout", seed);
        // The resample keeps the public view and deals a consistent layout (two of each card id).
        GameContext x = detachedGameCopy(gc);
        std::mt19937_64 rx(seed);
        sampleNoncombatFuture(x, rx);
        std::map<int, int> count;
        for (int i = 0; i < 12; ++i) {
            const auto &a = gc.info.toSelectCards[i], &b = x.info.toSelectCards[i];
            check(a.deckIdx == b.deckIdx, "resample changed a slot state", seed);
            if (a.deckIdx != GameContext::MATCH_AND_KEEP_UNSEEN)
                check(a.card.id == b.card.id && a.card.upgraded == b.card.upgraded, "resample changed a seen card", seed);
            ++count[static_cast<int>(b.card.id)];
        }
        for (const auto &[id, n] : count) check(n == 2 || n == 4, "resampled deal is not in pairs", seed);
    }

    // ---- Event fights with pre-rolled rewards ----
    GameContext fightStart(Event ev, std::uint64_t seed, bool &ok) {
        GameContext gc(CharacterClass::IRONCLAD, seed, 20);
        gc.curRoom = Room::EVENT;
        gc.curEvent = ev;
        gc.floorNum = 10;
        ok = true;
        if (ev == Event::DEAD_ADVENTURER) {
            for (int tries = 0; tries < 50; ++tries) {
                GameContext g = gc;
                g.miscRng = Random(seed * 977 + tries);
                g.setupEvent();
                g.chooseEventOption(0);
                if (g.screenState == ScreenState::BATTLE) return g;
            }
            ok = false;
            return gc;
        }
        gc.setupEvent();
        if (ev == Event::COLOSSEUM) {
            gc.chooseEventOption(0);              // the slaver fight
            gc.regainControlAction(gc);           // won: the event reopens
        }
        gc.chooseEventOption(ev == Event::COLOSSEUM ? 1 : 0);
        ok = gc.screenState == ScreenState::BATTLE;
        return gc;
    }

    std::vector<RelicId> &poolOf(GameContext &gc, RelicId r) {
        switch (getRelicTier(r)) {
            case RelicTier::COMMON: return gc.commonRelicPool;
            case RelicTier::UNCOMMON: return gc.uncommonRelicPool;
            case RelicTier::SHOP: return gc.shopRelicPool;
            default: return gc.rareRelicPool;
        }
    }

    void eventFight(Event ev, std::uint64_t seed, long &cases) {
        bool ok = false;
        GameContext gc = fightStart(ev, seed, ok);
        if (!ok) return;
        ++cases;
        // The fight's end shows the rewards kept in info.
        {
            GameContext end = gc;
            const auto snap = captureOocHidden(end);
            end.afterBattle();
            check(oocStepRevealsHidden(snap, end), "the end of an event fight is not a reveal", seed);
            const auto &rw = end.info.rewardsContainer;
            const int want = (gc.info.bossRelics[0] != RelicId::INVALID) + (gc.info.bossRelics[1] != RelicId::INVALID);
            check(rw.relicCount == want, "event fight reward relic count", seed);
            for (int i = 0; i < rw.relicCount && i < 2; ++i)
                check(rw.relics[i] == gc.info.bossRelics[i], "event fight reward is not the state's relic", seed);
        }
        // Another hidden roll: swap each hidden relic for another one still in its pool, and change the gold.
        GameContext alt = gc;
        for (int i = 0; i < 2; ++i) {
            const RelicId r = alt.info.bossRelics[i];
            if (r == RelicId::INVALID || getRelicTier(r) == RelicTier::SPECIAL) continue;
            auto &pool = poolOf(alt, r);
            if (pool.empty()) continue;
            const RelicId other = pool.back();
            pool.pop_back();
            pool.push_back(r);
            alt.info.bossRelics[i] = other;
        }
        if (ev == Event::DEAD_ADVENTURER || ev == Event::MYSTERIOUS_SPHERE) alt.info.gold += 3;
        for (std::uint64_t s = 1; s <= 4; ++s)
            check(resampleEqual(gc, alt, seed * 1000 + s, false, true),
                  "event fight resample depends on the hidden rewards", seed);
    }

}

int main(int argc, char **argv) {
    const int seeds = argc > 1 ? std::atoi(argv[1]) : 200;
    long differing = 0, flips = 0, fights = 0;
    for (int i = 0; i < seeds; ++i) {
        const std::uint64_t seed = 1 + i;
        try {
            matchAndKeep(seed, differing, flips);
            for (const Event ev : {Event::COLOSSEUM, Event::DEAD_ADVENTURER, Event::MINDBLOOM, Event::MYSTERIOUS_SPHERE})
                eventFight(ev, seed, fights);
        } catch (const OocSearchUnsupported &e) {
            check(false, e.what(), seed);
        }
    }
    std::cout << "seeds " << seeds << " match-and-keep hidden variants " << differing << " seen-card flips " << flips
              << " event fights " << fights << "\n";
    if (differing == 0 || flips == 0 || fights == 0) { std::cerr << "FAIL: no coverage\n"; ++g_fail; }
    std::cout << (g_fail ? "FAIL" : "ok") << "\n";
    return g_fail ? 1 : 0;
}
