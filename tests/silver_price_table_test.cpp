// Silver price-table leaf (STS_SILVER_PRICE_TABLE_LEAF, research, default off): the C++ port of §732's Feat.row
// and the exported §746 model A against Python on stored Heart-entry states, the GameContext -> state names,
// fixture sanity of the per-fight tables (more HP never lowers the leaf, removing a held potion never raises it),
// the search leaf with and without a table, and the table build time. Run from the repository root.
#include "one_combat/silver_price_table.h"

#include <chrono>
#include <cmath>
#include <fstream>
#include <iostream>
#include <map>

#include "combat/BattleContext.h"
#include "constants/Cards.h"
#include "constants/Potions.h"
#include "constants/Relics.h"
#include "game/GameContext.h"
#include "sim/search/SilverSearcher.h"

namespace {
int failures = 0;
void require(bool ok, const std::string &message) {
    if (!ok) { std::cerr << "FAIL: " << message << '\n'; ++failures; }
}

using namespace sts;
using one_combat::PriceState;

// act4replay's state -> GameContext (apps/one_combat/silver_synth_gen.cpp act4ReplayContext), at Shield & Spear.
GameContext gameFromState(const nlohmann::json &s) {
    static const auto cardIds = [] {
        std::map<std::string, CardId> m;
        for (int i = 1; i < static_cast<int>(std::size(cardNames)); ++i) m[cardNames[i]] = static_cast<CardId>(i);
        return m;
    }();
    GameContext gc(CharacterClass::IRONCLAD, 111459990, 20);
    gc.transitionToAct(4);
    gc.deck = Deck{};
    const auto misc = s.at("deckMisc").get<std::vector<int>>();
    int k = 0;
    for (const auto &entry : s.at("deck")) {
        std::string name = entry.get<std::string>();
        const bool up = !name.empty() && name.back() == '+';
        if (up) name.pop_back();
        Card c(cardIds.at(name));
        if (up) c.upgrade();
        c.misc = static_cast<std::int16_t>(misc[k++]);
        gc.deck.obtainRaw(c);
    }
    gc.relics.relics.clear();
    const auto data = s.at("relicData").get<std::vector<int>>();
    k = 0;
    for (const auto &entry : s.at("relics")) {
        int id = -1;
        for (int i = 0; i < static_cast<int>(std::size(relicEnumNames)) - 1; ++i)
            if (entry.get<std::string>() == relicEnumNames[i]) id = i;
        gc.relics.add({static_cast<RelicId>(id), data[k++]});
    }
    gc.potionCapacity = s.at("potionCapacity").get<int>();
    for (auto &p : gc.potions) p = Potion::EMPTY_POTION_SLOT;
    gc.potionCount = 0;
    for (const auto &entry : s.at("potions"))
        for (int i = 2; i < static_cast<int>(std::size(potionEnumNames)); ++i)
            if (entry.get<std::string>() == potionEnumNames[i]) { gc.potions[gc.potionCount++] = static_cast<Potion>(i); break; }
    for (const auto key : {Key::RUBY_KEY, Key::EMERALD_KEY, Key::SAPPHIRE_KEY}) gc.obtainKey(key);
    gc.maxHp = s.at("maxHp").get<int>();
    gc.curHp = s.at("hp").get<int>();
    gc.curMapNodeX = 3; gc.curMapNodeY = 2; gc.floorNum = 55; gc.curRoom = Room::ELITE;
    gc.enterBattle(MonsterEncounter::SHIELD_AND_SPEAR);
    return gc;
}

bool sameState(const PriceState &a, const PriceState &b) {
    return a.hp == b.hp && a.maxHp == b.maxHp && a.potionCapacity == b.potionCapacity && a.potions == b.potions
        && a.deck == b.deck && a.deckMisc == b.deckMisc && a.relics == b.relics && a.relicData == b.relicData;
}
}  // namespace

// --report STATES.jsonl OUT.jsonl: the fight-start table of every state (act4replay / fit_value.py state JSON) as
// one JSON line each (diagnostics for the evidence README; no checks).
int report(const one_combat::PriceModel &model, const std::string &statesPath, const std::string &outPath) {
    std::ifstream in(statesPath);
    std::ofstream out(outPath);
    int n = 0;
    for (std::string line; std::getline(in, line);) {
        if (line.empty()) continue;
        const auto j = nlohmann::json::parse(line);
        int rows = 0;
        const auto t = one_combat::buildPriceTable(model, one_combat::priceStateFromJson(j), &rows, true);
        nlohmann::json r = {{"i", n++}, {"id", j.value("id", std::string())}, {"hp", j.at("hp")}, {"maxHp", j.at("maxHp")},
                            {"rows", rows}, {"flat", !t}};
        if (t) {
            r["hpUnit"] = t->hpUnit; r["rootWinValue"] = t->rootWinValue;
            r["anchorRaw"] = t->anchorRaw; r["anchorWinBonus"] = t->winBonus;
            r["hpKnots"] = t->hpKnots; r["hpValue"] = t->hpValue;
            r["maxHpPrice"] = t->maxHpPrice; r["goldPrice"] = t->goldPrice;
            nlohmann::json pots = nlohmann::json::object();
            for (int p = 0; p < search::kSilverPotionTypeCount; ++p)
                if (t->potionPriced[p]) pots[potionEnumNames[p]] = t->potionPrice[p];
            r["potionPrice"] = pots;
            nlohmann::json ctr = nlohmann::json::object();
            for (const auto &c : t->counters)
                ctr[relicEnumNames[static_cast<int>(c.relic)]] = {{"root", c.rootValue}, {"price", c.price}};
            r["counters"] = ctr;
        }
        out << r.dump() << '\n';
    }
    std::cout << "report: " << n << " tables -> " << outPath << '\n';
    return 0;
}

int main(int argc, char **argv) {
    one_combat::PriceModel model;
    if (!model.load("models/candidates/silver_price_a746.trees", "models/candidates/silver_price_a746.vocab.json")) {
        std::cerr << "FAIL: cannot load the a746 model (run from the repository root)\n";
        return 1;
    }
    if (argc == 4 && std::string(argv[1]) == "--report") return report(model, argv[2], argv[3]);
    std::ifstream in("tests/data/silver_price_a746.parity.jsonl");
    require(bool(in), "parity file");
    std::vector<nlohmann::json> states;
    int rows = 0, featureMismatch = 0;
    double maxMarginDiff = 0;
    for (std::string line; std::getline(in, line);) {
        if (line.empty()) continue;
        const auto j = nlohmann::json::parse(line);
        const PriceState s = one_combat::priceStateFromJson(j.at("state"));
        int unknown = 0;
        const auto x = model.features.row(s, &unknown);
        std::vector<float> want(x.size(), 0.0f);
        for (const auto &[k, v] : j.at("x").items()) want.at(std::stoul(k)) = v.get<float>();
        if (x != want || unknown != 0) ++featureMismatch;
        maxMarginDiff = std::max(maxMarginDiff, std::abs(model.net.margin(x) - j.at("margin").get<double>()));
        states.push_back(j.at("state"));
        ++rows;
    }
    require(rows >= 256, "parity rows");
    require(featureMismatch == 0, "feature rows equal Python's Feat.row (" + std::to_string(featureMismatch) + " differ)");
    require(maxMarginDiff < 1e-4, "margin parity with XGBoost (max diff " + std::to_string(maxMarginDiff) + ")");

    // GameContext -> state: the names and values make_variants.py writes.
    int gameMismatch = 0;
    for (std::size_t i = 0; i < 32 && i < states.size(); ++i) {
        const GameContext gc = gameFromState(states[i]);
        if (!sameState(one_combat::priceStateFromGame(gc), one_combat::priceStateFromJson(states[i]))) ++gameMismatch;
    }
    require(gameMismatch == 0, "priceStateFromGame matches the stored state (" + std::to_string(gameMismatch) + " differ)");

    // Fixture sanity on every stored state's fight-start table.
    int tables = 0, flat = 0, hpDown = 0, potionUp = 0, rowsSum = 0;
    double potionMin = 1e9, maxHpMin = 1e9, maxHpMax = -1e9;
    const auto t0 = std::chrono::steady_clock::now();
    for (const auto &j : states) {
        int n = 0;
        const auto t = one_combat::buildPriceTable(model, one_combat::priceStateFromJson(j), &n);
        rowsSum += n;
        if (!t) { ++flat; continue; }
        ++tables;
        require(std::abs(t->hpValue.front() - 1) < 1e-12 && t->hpKnots.front() == 1, "U(1) = 1");
        for (std::size_t k = 1; k < t->hpValue.size(); ++k) if (t->hpValue[k] < t->hpValue[k - 1]) ++hpDown;
        for (int p = 0; p < search::kSilverPotionTypeCount; ++p)
            if (t->potionPriced[p]) { potionMin = std::min(potionMin, t->potionPrice[p]); if (t->potionPrice[p] < 0) ++potionUp; }
        maxHpMin = std::min(maxHpMin, t->maxHpPrice); maxHpMax = std::max(maxHpMax, t->maxHpPrice);
    }
    const double us = std::chrono::duration<double, std::micro>(std::chrono::steady_clock::now() - t0).count()
        / std::max<std::size_t>(states.size(), 1);
    require(tables > 0, "tables built");
    require(hpDown == 0, "more HP never lowers the HP curve (" + std::to_string(hpDown) + " segments fall)");
    require(potionUp == 0, "removing a held potion never raises the value (" + std::to_string(potionUp) + " negative prices)");
    std::cout << "tables " << tables << " flat " << flat << " model rows/table " << double(rowsSum) / states.size()
              << " build " << us << " us/table; potion price min " << potionMin << " HP; max-HP price ["
              << maxHpMin << ", " << maxHpMax << "] HP/pt\n";
    require(us < 20000, "table build under 20 ms");

    // The search leaf: no table = Silver's default win leaf; with a table, more HP never lowers a win and
    // removing a held potion never raises it.
    int leafChecks = 0, anchorInside = 0;
    for (std::size_t i = 0; i < 16 && i < states.size(); ++i) {
        GameContext gc = gameFromState(states[i]);
        BattleContext bc;
        bc.init(gc);
        search::SilverSearchContext ctx;
        ctx.act = 4;
        search::SilverSearcher plain(bc, ctx), priced(bc, ctx);
        priced.priceTable = one_combat::buildPriceTable(model, one_combat::priceStateFromGame(gc));
        if (!priced.priceTable) continue;
        BattleContext a = bc;
        const double p0 = plain.winNowValue(a);
        // Default leaf at the fight-start state: winBonus + HP + 11 per potion + death saves (weights' defaults).
        double want = 53.0 + bc.player.curHp + 11.0 * bc.potionCount - 0.4 * bc.turn;
        bool fairy = false;
        for (int k = 0; k < bc.potionCapacity; ++k) fairy |= bc.potions[k] == Potion::FAIRY_POTION;
        if (!bc.player.hasRelic<RelicId::MARK_OF_THE_BLOOM>()) {
            if (fairy) want += bc.player.maxHp * (bc.player.hasRelic<RelicId::SACRED_BARK>() ? 0.6 : 0.3);
            if (bc.player.hasRelic<RelicId::LIZARD_TAIL>()) want += 0.5 * bc.player.maxHp;
        }
        require(std::abs(p0 - want) < 1e-9, "no table: the default win leaf");
        double prev = -1e18;
        for (int hp = 1; hp <= bc.player.maxHp; ++hp) {
            BattleContext b = bc; b.player.curHp = hp;
            const double v = priced.winNowValue(b);
            require(v >= prev - 1e-9, "table leaf: more HP never lowers a win");
            prev = v;
        }
        for (int k = 0; k < bc.potionCapacity; ++k) {
            if (bc.potions[k] == Potion::EMPTY_POTION_SLOT) continue;
            BattleContext b = bc, c = bc;
            c.potions[k] = Potion::EMPTY_POTION_SLOT; --c.potionCount;
            require(priced.winNowValue(c) <= priced.winNowValue(b) + 1e-9, "table leaf: removing a potion never raises a win");
        }
        BattleContext b = bc;
        require(std::abs(priced.winNowValue(b) - (53.0 + priced.priceTable->stateValue(bc, bc.player.curHp) - 0.4 * bc.turn)) < 1e-9,
                "table leaf at the root: winBonus + U(hp) + potions + counters");
        // Anchored: winBonus + stateValue(root) = V(root) / scale before the clamp; the leaf uses the clamped bonus.
        auto anchored = one_combat::buildPriceTable(model, one_combat::priceStateFromGame(gc), nullptr, true);
        require(anchored && std::isnan(priced.priceTable->winBonus), "unanchored table keeps the default win bonus");
        // The start state's table value (HP + potions; counters at their start value price 0).
        double start = anchored->hpCurve(bc.player.curHp);
        for (int k = 0; k < bc.potionCapacity; ++k) {
            const auto t = static_cast<int>(bc.potions[k]);
            if (bc.potions[k] == Potion::EMPTY_POTION_SLOT || t >= search::kSilverPotionTypeCount) continue;
            start += anchored->potionPriced[t] ? anchored->potionPrice[t] : anchored->unpricedPotion;
        }
        require(std::abs(anchored->anchorRaw + start - anchored->rootWinValue) < 1e-9,
                "anchor: raw bonus + the start state's table value = V(root) / scale");
        require(anchored->winBonus >= 53.0 - 1e-12 && anchored->winBonus <= one_combat::kAnchorCapFactor * 53.0 + 1e-12,
                "anchor: clamped to [53, 212]");
        search::SilverSearcher anchoredSearch(bc, ctx);
        anchoredSearch.priceTable = anchored;
        BattleContext c = bc;
        require(std::abs(anchoredSearch.winNowValue(c) - (anchored->winBonus + anchored->stateValue(bc, bc.player.curHp)
                                                          - 0.4 * bc.turn)) < 1e-9,
                "anchored leaf at the root uses the table's win bonus");
        if (anchored->anchorRaw >= 53.0 && anchored->anchorRaw <= one_combat::kAnchorCapFactor * 53.0) ++anchorInside;
        // Counters only: the default win leaf plus the counter prices; no Lizard Tail counter.
        auto ctr = one_combat::buildPriceTable(model, one_combat::priceStateFromGame(gc), nullptr, false, true);
        require(ctr && ctr->countersOnly, "counters-only table built");
        for (const auto &cc : ctr->counters) require(cc.relic != RelicId::LIZARD_TAIL, "counters only: no Lizard Tail counter");
        search::SilverSearcher ctrSearch(bc, ctx);
        ctrSearch.priceTable = ctr;
        BattleContext e = bc;
        require(std::abs(ctrSearch.winNowValue(e) - (p0 + ctr->counterValue(bc))) < 1e-9,
                "counters-only leaf = default leaf + counter prices");
        ++leafChecks;
    }
    require(leafChecks > 0, "leaf checks ran");
    std::cout << "anchor unclamped at " << anchorInside << " of " << leafChecks << " leaf-check states\n";
    if (failures) return 1;
    std::cout << "PASS silver price table (" << rows << " parity rows, max margin diff " << maxMarginDiff << ")\n";
    return 0;
}
