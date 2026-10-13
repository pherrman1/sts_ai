#include "ooc_native_fallback.h"

#include <algorithm>
#include <array>
#include <charconv>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <random>
#include <sstream>
#include <stdexcept>
#include <utility>

#include "sim/search/GameAction.h"
#include "sim/search/OocSemanticAction.h"

namespace one_combat {
namespace {
thread_local std::uint64_t publicScorerCalls = 0;
thread_local int resampledQueueDepth = 0;
thread_local int greedyShopDepth = 0;

void requireModels(const CompactTreeNet &model) {
    if (!model.ok) throw std::runtime_error("native OOC fallback model unavailable");
}
std::vector<float> features(const sts::GameContext &gc, const PathHistory &path) {
    return richFeatureVec(gc, path);
}

int publicFutureCount() {
    // Default 8: the fallback never reads the realized encounter queue
    // (ledger §434). Explicit 0 restores the legacy hidden-information inputs.
    const char *value = std::getenv("STS_OOC_PUBLIC_FUTURES");
    if (!value) return 8;
    int count = -1;
    const auto parsed = std::from_chars(value, value + std::strlen(value), count);
    if (parsed.ec != std::errc{} || *parsed.ptr != '\0' || count < 0 || count > 256)
        throw std::runtime_error("STS_OOC_PUBLIC_FUTURES requires an integer in 0..256");
    return count;
}

// On by default (ADR-0030); explicit 0 restores the legacy accounting.
bool shopDeckSizeFixEnabled() {
    const char *value = std::getenv("STS_OOC_SHOP_DECK_SIZE_FIX");
    if (!value || std::strcmp(value, "1") == 0) return true;
    if (std::strcmp(value, "0") == 0) return false;
    throw std::runtime_error("STS_OOC_SHOP_DECK_SIZE_FIX must be 0 or 1");
}

// Keep the encounter suffix generation equivalent to sampleNoncombatFuture
// in ooc_mcts_adapter.cpp. Only encounter lists and the private copy's
// monsterRng are needed: no offers, map, relic pools or source RNG are touched.
void sampleEncounterSuffix(sts::GameContext &gc, std::mt19937_64 &rng) {
    if (gc.act < 1 || gc.act > 3)
        throw std::runtime_error("public OOC value: only acts 1..3 are supported");
    const int count = gc.monsterList.size();
    if (gc.monsterListOffset < 0 || gc.monsterListOffset > count
        || gc.eliteMonsterListOffset < 0
        || gc.eliteMonsterListOffset > gc.eliteMonsterList.size())
        throw std::runtime_error("public OOC value: invalid encounter history");
    const auto counter = gc.monsterRng.counter;
    gc.monsterRng = sts::Random(rng());
    gc.monsterRng.counter = counter;
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
        do { draw = sts::MonsterEncounterPool::elites[gc.act - 1][gc.monsterRng.random(2)]; }
        while (i > 0 && draw == gc.eliteMonsterList[i - 1]);
        gc.eliteMonsterList[i] = draw;
    }
}

class PublicValueScorer {
    const CompactTreeNet &model_;
    std::vector<float> base_;
    std::array<int, 4> hidden_{};
    std::vector<std::array<float, 4>> scenarios_;
public:
    PublicValueScorer(const sts::GameContext &gc, const PathHistory &path,
                      const CompactTreeNet &model)
        : model_(model), base_(features(gc, path)) {
        const int count = publicFutureCount();
        // Act 4 has a fixed elite and boss and no hallway queue, so its
        // encounter fields reveal nothing and are scored as they are.
        // Inside an OOC MCTS playout the queue is already a public sample.
        if (count == 0 || gc.act == 4 || resampledQueueDepth > 0) return;
        const auto &idx = richIdxMap();
        hidden_ = {idx.at("nextEliteId"), idx.at("nextFight0"),
                   idx.at("nextFight1"), idx.at("nextFight2")};
        const std::array<int, 8> excluded = {hidden_[0], hidden_[1], hidden_[2], hidden_[3],
            idx.at("remElites"), idx.at("remFights"), idx.at("monOffset"), idx.at("eliteOffset")};
        // Stable public-state seed. The true seed, RNG streams, future queues
        // and all eight historically excluded queue-derived fields are absent.
        std::uint64_t seed = 14695981039346656037ULL;
        const auto hashWord = [&](std::uint32_t word) {
            for (int byte = 0; byte < 4; ++byte) {
                seed ^= (word >> (8 * byte)) & 0xffu;
                seed *= 1099511628211ULL;
            }
        };
        hashWord(0x4f4f4301u); // public OOC encounter-mixture version 1
        hashWord(static_cast<std::uint32_t>(gc.screenState));
        for (int i = 0; i < static_cast<int>(base_.size()); ++i) {
            if (std::find(excluded.begin(), excluded.end(), i) != excluded.end()) continue;
            std::uint32_t bits;
            static_assert(sizeof(bits) == sizeof(float));
            std::memcpy(&bits, &base_[i], sizeof(bits));
            hashWord(bits);
        }
        std::mt19937_64 rng(seed);
        scenarios_.reserve(count);
        for (int future = 0; future < count; ++future) {
            auto sampled = gc;
            sampleEncounterSuffix(sampled, rng);
            const auto row = features(sampled, path);
            scenarios_.push_back({row[hidden_[0]], row[hidden_[1]], row[hidden_[2]], row[hidden_[3]]});
        }
        ++publicScorerCalls;
    }

    const std::vector<float> &base() const { return base_; }

    double predict(const std::vector<float> &row) const {
        if (scenarios_.empty()) return model_.predict(row);
        auto sampled = row;
        double total = 0.0;
        for (const auto &scenario : scenarios_) {
            for (int i = 0; i < 4; ++i) sampled[hidden_[i]] = scenario[i];
            const double value = model_.predict(sampled);
            if (!std::isfinite(value)) throw std::runtime_error("public OOC value: nonfinite prediction");
            total += value;
        }
        // Average predictions, not margins: logistic win models require
        // E[sigmoid(margin)] rather than sigmoid(E[margin]).
        return total / scenarios_.size();
    }

    // Same values as predict() on base with each candidate's values at the
    // distinct varying raw indices (row-major, varying.size() per candidate).
    void predictDeltas(const std::vector<int> &varying, const std::vector<float> &values,
                       std::vector<double> &out) const {
        if (scenarios_.empty()) { model_.predictDeltas(base_, varying, values, out); return; }
        out.clear();
        auto row = base_;
        for (std::size_t at = 0; at < values.size(); at += varying.size()) {
            for (std::size_t j = 0; j < varying.size(); ++j) row[varying[j]] = values[at + j];
            out.push_back(predict(row));
        }
    }
};

// Candidate rows that differ from a base feature row only at a few raw
// indices, stored as those columns (row-major). Declare every column before
// adding rows.
class DeltaRows {
    const std::vector<float> &base_;
    std::vector<int> column_;
public:
    std::vector<int> varying;
    std::vector<float> values;
    explicit DeltaRows(const std::vector<float> &base) : base_(base), column_(base.size(), -1) {}
    int column(int index) {
        if (column_[index] < 0) {
            column_[index] = static_cast<int>(varying.size());
            varying.push_back(index);
        }
        return column_[index];
    }
    // Appends a copy of base at the varying columns and returns it.
    float *addRow() {
        const std::size_t at = values.size();
        for (const int index : varying) values.push_back(base_[index]);
        return values.data() + at;
    }
};
}

int nativeOocPublicFutureCount() { return publicFutureCount(); }
NativeOocResampledQueueScope::NativeOocResampledQueueScope() { ++resampledQueueDepth; }
NativeOocResampledQueueScope::~NativeOocResampledQueueScope() { --resampledQueueDepth; }
NativeOocGreedyShopScope::NativeOocGreedyShopScope() { ++greedyShopDepth; }
NativeOocGreedyShopScope::~NativeOocGreedyShopScope() { --greedyShopDepth; }
bool nativeOocShopDeckSizeFixEnabled() { return shopDeckSizeFixEnabled(); }
bool nativeOocCardWinRankEnabled() {
    const char *value = std::getenv("STS_OOC_CARD_WIN_RANK");
    if (!value || std::strcmp(value, "0") == 0) return false;
    if (std::strcmp(value, "1") == 0) return true;
    throw std::runtime_error("STS_OOC_CARD_WIN_RANK must be 0 or 1");
}
std::uint64_t nativeOocPublicScorerCalls() { return publicScorerCalls; }
void resetNativeOocPublicScorerCalls() { publicScorerCalls = 0; }

double nativeOocValue(const sts::GameContext &gc, const PathHistory &path,
                      const CompactTreeNet &model) {
    requireModels(model);
    const PublicValueScorer scorer(gc, path, model);
    return scorer.predict(scorer.base());
}

int nativeFloorCardPick(sts::GameContext &gc, const PathHistory &path,
                        const CompactTreeNet &floor, int rewardIndex, double skipThreshold) {
    requireModels(floor);
    const auto &r = gc.info.rewardsContainer;
    const PublicValueScorer scorer(gc, path, floor);
    const auto &base = scorer.base();
    const auto &idx = richIdxMap();
    const int dsz = idx.at("deckSize");
    double best = -1e100; int bestIdx = 5;
    DeltaRows rows(base);
    const int deckCol = rows.column(dsz);
    std::vector<int> cardCol;
    for (int i = 0; i < r.cardRewards[rewardIndex].size(); ++i) {
        const int cid = static_cast<int>(r.cardRewards[rewardIndex][i].getId());
        const auto it = idx.find("d" + std::to_string(cid));
        cardCol.push_back(it != idx.end() ? rows.column(it->second) : -1);
    }
    rows.addRow();
    for (int i = 0; i < r.cardRewards[rewardIndex].size(); ++i) {
        float *row = rows.addRow();
        if (cardCol[i] >= 0) row[cardCol[i]] += 1.0f;
        row[deckCol] += 1.0f;
    }
    std::vector<double> values;
    scorer.predictDeltas(rows.varying, rows.values, values);
    const double v0 = values[0];
    for (int i = 0; i < r.cardRewards[rewardIndex].size(); ++i) {
        const double marginal = values[i + 1] - v0;
        if (marginal > best) { best = marginal; bestIdx = i; }
    }
    return best < skipThreshold ? 5 : bestIdx;
}

int nativeCardWinRankPick(sts::GameContext &gc, const PathHistory &path,
                         const CompactTreeNet &floor, const CompactTreeNet &win,
                         int rewardIndex, double floorSkipThreshold,
                         NativeCardWinRankTrace *trace) {
    if (!nativeOocCardWinRankEnabled())
        return nativeFloorCardPick(gc, path, floor, rewardIndex, floorSkipThreshold);
    if (publicFutureCount() != 8)
        throw std::runtime_error("STS_OOC_CARD_WIN_RANK requires STS_OOC_PUBLIC_FUTURES=8");
    requireModels(floor);
    requireModels(win);
    if (!win.logistic)
        throw std::runtime_error("STS_OOC_CARD_WIN_RANK requires a logistic win model");
    if (gc.screenState != sts::ScreenState::REWARDS || rewardIndex < 0
        || rewardIndex >= gc.info.rewardsContainer.cardRewardCount
        || !std::isfinite(floorSkipThreshold))
        throw std::runtime_error("STS_OOC_CARD_WIN_RANK invalid reward or floor threshold");
    if (trace) {
        *trace = NativeCardWinRankTrace{};
        trace->scenarioCount = 8;
    }
    const auto &idx = richIdxMap();
    const int dsz = idx.at("deckSize");
    const auto &reward = gc.info.rewardsContainer.cardRewards[rewardIndex];
    const auto rank = [&](const CompactTreeNet &model, double *loggedBase,
                          std::vector<double> *loggedMarginals) {
        // The same public state/path determines the same scenarios for both
        // heads. No candidate changes the scenario seed or the source state.
        const PublicValueScorer scorer(gc, path, model);
        const auto &base = scorer.base();
        double best = -1e100; int bestIdx = 5;
        const double v0 = scorer.predict(base);
        if (!std::isfinite(v0))
            throw std::runtime_error("STS_OOC_CARD_WIN_RANK nonfinite base value");
        if (loggedBase) *loggedBase = v0;
        for (int i = 0; i < reward.size(); ++i) {
            auto row = base;
            const int cid = static_cast<int>(reward[i].getId());
            const auto it = idx.find("d" + std::to_string(cid));
            if (it != idx.end()) row[it->second] += 1.0f;
            row[dsz] += 1.0f;
            const double marginal = scorer.predict(row) - v0;
            if (!std::isfinite(marginal))
                throw std::runtime_error("STS_OOC_CARD_WIN_RANK nonfinite card marginal");
            if (loggedMarginals) loggedMarginals->push_back(marginal);
            if (marginal > best) { best = marginal; bestIdx = i; }
        }
        return std::make_pair(bestIdx, best);
    };
    const auto baseline = rank(floor, trace ? &trace->floorBase : nullptr,
                               trace ? &trace->floorMarginals : nullptr);
    const int floorPick = baseline.second < floorSkipThreshold ? 5 : baseline.first;
    if (trace) trace->baselinePick = trace->chosenPick = floorPick;
    if (floorPick == 5) return 5;
    const auto ranked = rank(win, trace ? &trace->winBase : nullptr,
                             trace ? &trace->winMarginals : nullptr);
    if (trace) {
        trace->winEvaluated = true;
        trace->chosenPick = ranked.first;
    }
    // No win-probability skip threshold: floor already made that decision.
    return ranked.first;
}

std::string nativeShopPlan(sts::GameContext &gc, const PathHistory &path,
                           const CompactTreeNet &floor) {
    requireModels(floor);
    const bool fixDeckSize = shopDeckSizeFixEnabled();
    using RT = sts::search::GameAction::RewardsActionType;
    const auto &sh = gc.info.shop;
    const auto &idx = richIdxMap();
    const int goldIdx = idx.at("gold"), dsz = idx.at("deckSize");
    const PublicValueScorer scorer(gc, path, floor);
    const auto &base = scorer.base();
    struct Item { char kind; int slot, price, id; };
    std::vector<Item> items;
    for (int i = 0; i < 7; ++i) if (sh.cardPrice(i) >= 0)
        items.push_back({'c', i, sh.cardPrice(i), static_cast<int>(sh.cards[i].getId())});
    for (int i = 0; i < 3; ++i) {
        const sts::search::GameAction action(RT::RELIC, i);
        if (sh.relicPrice(i) >= 0 && sts::search::isSupportedAutonomousOocAction(gc, action))
            items.push_back({'r', i, sh.relicPrice(i), static_cast<int>(sh.relics[i])});
    }
    if (items.size() > 16) items.resize(16);
    int removeId = -1; double removeGain = 0.0;
    std::vector<double> values;
    // Prices are nonnegative, so an unaffordable removal is in no candidate
    // below and its target need not be ranked.
    if (sh.removeCost >= 0 && sh.removeCost <= gc.gold) {
        DeltaRows rows(base);
        const int deckCol = rows.column(dsz);
        std::vector<int> ids, cols;
        for (int id = 0; id < 372; ++id) {
            const auto it = idx.find("d" + std::to_string(id));
            if (it == idx.end() || base[it->second] <= 0) continue;
            ids.push_back(id); cols.push_back(rows.column(it->second));
        }
        rows.addRow();
        for (const int col : cols) {
            float *row = rows.addRow();
            row[col] -= 1.0f; row[deckCol] -= 1.0f;
        }
        scorer.predictDeltas(rows.varying, rows.values, values);
        const double v0 = values[0];
        for (std::size_t k = 0; k < ids.size(); ++k) {
            const double gain = values[k + 1] - v0;
            if (removeId < 0 || gain > removeGain) { removeId = ids[k]; removeGain = gain; }
        }
    }
    // Candidates differ from base only at gold, deck size and the items' and
    // removed card's features: the same floats and operation order as a full
    // row. They are compared in enumeration order.
    DeltaRows rows(base);
    const int goldCol = rows.column(goldIdx), deckCol = rows.column(dsz);
    std::vector<int> itemCol(items.size(), -1);
    for (std::size_t k = 0; k < items.size(); ++k) {
        const auto it = idx.find((items[k].kind == 'c' ? "d" : "r") + std::to_string(items[k].id));
        if (it != idx.end()) itemCol[k] = rows.column(it->second);
    }
    int removeCol = -1;
    if (removeId >= 0) {
        const auto it = idx.find("d" + std::to_string(removeId));
        if (it != idx.end()) removeCol = rows.column(it->second);
    }
    if (greedyShopDepth > 0) {
        // Greedy: leaving and each affordable single purchase (one item, or the
        // best removal alone), scored against the current state. The caller
        // executes the winner and asks again, so purchases repeat greedily.
        std::vector<int> choices{-1}; // -1 leave, k item k, items.size() removal
        rows.addRow();
        for (std::size_t k = 0; k < items.size(); ++k) {
            if (items[k].price > gc.gold) continue;
            float *row = rows.addRow();
            row[goldCol] -= items[k].price;
            if (!fixDeckSize || items[k].kind == 'c') row[deckCol] += 1.0f;
            if (itemCol[k] >= 0) {
                if (items[k].kind == 'c') row[itemCol[k]] += 1.0f;
                else row[itemCol[k]] = std::max(row[itemCol[k]], 1.0f);
            }
            choices.push_back(static_cast<int>(k));
        }
        if (removeId >= 0) {
            float *row = rows.addRow();
            row[goldCol] -= sh.removeCost;
            if (fixDeckSize) row[deckCol] -= 1.0f;
            if (removeCol >= 0) row[removeCol] -= 1.0f;
            choices.push_back(static_cast<int>(items.size()));
        }
        scorer.predictDeltas(rows.varying, rows.values, values);
        double best = -1e100; int bestChoice = -1;
        for (std::size_t k = 0; k < choices.size(); ++k)
            if (values[k] > best) { best = values[k]; bestChoice = choices[k]; }
        std::ostringstream out;
        if (bestChoice == static_cast<int>(items.size())) out << 'x';
        else if (bestChoice >= 0) out << items[bestChoice].kind << items[bestChoice].slot;
        return out.str();
    }
    struct Candidate { unsigned mask; bool remove; };
    std::vector<Candidate> pending;
    const unsigned total = 1u << items.size();
    for (unsigned mask = 0; mask < total; ++mask) {
        int spend = 0, adds = 0;
        for (unsigned k = 0; k < items.size(); ++k) if (mask & (1u << k)) {
            spend += items[k].price;
            if (!fixDeckSize || items[k].kind == 'c') ++adds;
        }
        for (int rem = 0; rem <= 1; ++rem) {
            if (rem && (sh.removeCost < 0 || removeId < 0)) continue;
            if (spend + (rem ? sh.removeCost : 0) > gc.gold) continue;
            float *row = rows.addRow();
            row[goldCol] -= spend + (rem ? sh.removeCost : 0);
            row[deckCol] += adds - (fixDeckSize ? rem : 0);
            for (unsigned k = 0; k < items.size(); ++k) if ((mask & (1u << k)) && itemCol[k] >= 0) {
                if (items[k].kind == 'c') row[itemCol[k]] += 1.0f;
                else row[itemCol[k]] = std::max(row[itemCol[k]], 1.0f);
            }
            if (rem && removeCol >= 0) row[removeCol] -= 1.0f;
            pending.push_back({mask, rem != 0});
        }
    }
    double best = -1e100; unsigned bestMask = 0; bool bestRemove = false;
    if (!pending.empty()) {
        scorer.predictDeltas(rows.varying, rows.values, values);
        for (std::size_t k = 0; k < pending.size(); ++k)
            if (values[k] > best) { best = values[k]; bestMask = pending[k].mask; bestRemove = pending[k].remove; }
    }
    std::ostringstream out;
    for (unsigned k = 0; k < items.size(); ++k)
        if (bestMask & (1u << k)) out << items[k].kind << items[k].slot << ' ';
    if (bestRemove) out << 'x';
    return out.str();
}

int nativeFloorRemovePick(const sts::GameContext &gc, const PathHistory &path,
                           const CompactTreeNet &floor, const std::vector<int> &cardIds) {
    requireModels(floor);
    const auto &idx = richIdxMap();
    const int dsz = idx.at("deckSize");
    const PublicValueScorer scorer(gc, path, floor);
    const auto &base = scorer.base();
    DeltaRows rows(base);
    const int deckCol = rows.column(dsz);
    std::vector<int> cardCol;
    for (int i = 0; i < static_cast<int>(cardIds.size()); ++i) {
        const auto it = idx.find("d" + std::to_string(cardIds[i]));
        cardCol.push_back(it != idx.end() ? rows.column(it->second) : -1);
    }
    rows.addRow();
    for (int i = 0; i < static_cast<int>(cardIds.size()); ++i) {
        float *row = rows.addRow();
        if (cardCol[i] >= 0) row[cardCol[i]] -= 1.0f;
        row[deckCol] -= 1.0f;
    }
    std::vector<double> values;
    scorer.predictDeltas(rows.varying, rows.values, values);
    const double v0 = values[0];
    double best = -1e100; int bestIdx = 0;
    for (int i = 0; i < static_cast<int>(cardIds.size()); ++i) {
        const double gain = values[i + 1] - v0;
        if (gain > best) { best = gain; bestIdx = i; }
    }
    return bestIdx;
}

double nativeWinHealGain(sts::GameContext &gc, const PathHistory &path,
                         const CompactTreeNet &win, int healAmount) {
    requireModels(win);
    const PublicValueScorer scorer(gc, path, win);
    const double before = scorer.predict(scorer.base());
    auto healed = scorer.base();
    healed[richIdxMap().at("curHp")] = std::min(gc.maxHp, gc.curHp + healAmount);
    return scorer.predict(healed) - before;
}

int nativeWinUpgradePick(const sts::GameContext &gc, const PathHistory &path,
                         const CompactTreeNet &win, const std::vector<int> &cardIds,
                         double *gain) {
    requireModels(win);
    const auto &idx = richIdxMap();
    const PublicValueScorer scorer(gc, path, win);
    const auto &base = scorer.base();
    const double before = scorer.predict(base);
    double best = -1e100; int bestIdx = 0;
    for (int i = 0; i < static_cast<int>(cardIds.size()); ++i) {
        auto row = base;
        const auto it = idx.find("u" + std::to_string(cardIds[i]));
        if (it != idx.end()) row[it->second] += 1.0f;
        const double delta = scorer.predict(row) - before;
        if (delta > best) { best = delta; bestIdx = i; }
    }
    if (std::abs(best) < 1e-6) {
        best = -1e100; bestIdx = 0;
        for (int i = 0; i < static_cast<int>(cardIds.size()); ++i) {
            auto row = base;
            const auto it = idx.find("d" + std::to_string(cardIds[i]));
            if (it != idx.end()) row[it->second] -= 1.0f;
            const auto ds = idx.find("deckSize");
            if (ds != idx.end()) row[ds->second] -= 1.0f;
            const double delta = before - scorer.predict(row);
            if (delta > best) { best = delta; bestIdx = i; }
        }
    }
    if (gain) *gain = best;
    return bestIdx;
}

bool nativeWinRestStep(sts::GameContext &gc, const PathHistory &path,
                       const CompactTreeNet &win, bool collectKeys) {
    requireModels(win);
    if (collectKeys && gc.act >= 3 && !gc.hasKey(sts::Key::RUBY_KEY)) {
        sts::search::GameAction(2, 0).execute(gc);
        return true;
    }
    const bool canRest = !gc.hasRelic(sts::RelicId::COFFEE_DRIPPER);
    const bool canSmith = !gc.relics.has(sts::RelicId::FUSION_HAMMER)
        && gc.deck.getUpgradeableCount() > 0;
    if (!(canRest && canSmith)) return false;
    const int healAmount = static_cast<int>(std::lround(0.30 * gc.maxHp))
        + (gc.hasRelic(sts::RelicId::REGAL_PILLOW) ? 15 : 0);
    const double healGain = nativeWinHealGain(gc, path, win, healAmount);
    std::vector<int> ids;
    for (int i = 0; i < gc.deck.size(); ++i) {
        if (!gc.deck.cards[i].canUpgrade()) continue;
        const int id = static_cast<int>(gc.deck.cards[i].getId());
        if (std::find(ids.begin(), ids.end(), id) == ids.end()) ids.push_back(id);
    }
    double upgradeGain = 0.0;
    if (!ids.empty()) nativeWinUpgradePick(gc, path, win, ids, &upgradeGain);
    sts::search::GameAction(healGain >= upgradeGain ? 0 : 1, 0).execute(gc);
    return true;
}

void nativeWinUpgradeSelectStep(sts::GameContext &gc, const PathHistory &path,
                                const CompactTreeNet &win) {
    std::vector<int> ids;
    for (int i = 0; i < gc.info.toSelectCards.size(); ++i)
        ids.push_back(static_cast<int>(gc.info.toSelectCards[i].card.getId()));
    double gain = 0.0;
    const int choice = ids.empty() ? 0 : nativeWinUpgradePick(gc, path, win, ids, &gain);
    sts::search::GameAction(choice, 0).execute(gc);
}

void nativeFloorShopStep(sts::GameContext &gc, const PathHistory &path,
                         const CompactTreeNet &floor) {
    using RT = sts::search::GameAction::RewardsActionType;
    const std::string plan = nativeShopPlan(gc, path, floor);
    std::istringstream is(plan);
    std::string token;
    if (!(is >> token) || token.empty()) {
        sts::search::GameAction(RT::SKIP).execute(gc); return;
    }
    const int idx = token.size() > 1 ? std::atoi(token.c_str() + 1) : 0;
    if (token[0] == 'c') sts::search::GameAction(RT::CARD, idx).execute(gc);
    else if (token[0] == 'r') {
        const sts::search::GameAction action(RT::RELIC, idx);
        if (sts::search::isSupportedAutonomousOocAction(gc, action)) action.execute(gc);
        else sts::search::GameAction(RT::SKIP).execute(gc);
    } else if (token[0] == 'x') sts::search::GameAction(RT::CARD_REMOVE).execute(gc);
    else sts::search::GameAction(RT::SKIP).execute(gc);
}

} // namespace one_combat
