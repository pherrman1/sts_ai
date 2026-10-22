#ifndef STS_LIGHTSPEED_EXACTCHANCE_H
#define STS_LIGHTSPEED_EXACTCHANCE_H

// Research tooling only (exact_combat_solver). Compiled in only with
// -DSTS_EXACT_CHANCE, which only the exact_combat_solver target sets; every
// other target never sees these hooks.
//
// While g_chanceScript is set, every combat RNG draw on the current thread is
// answered by the script instead of the RNG streams: a draw from the
// information-set draw pile chooses among classes of equivalent cards, a
// monster move roll chooses among its distinct (move, miscInfo) results, and
// any other draw chooses among its equally likely values. A caller enumerates
// every outcome of one engine step exactly by replaying the step: a run
// answers the draws of its prefix as given and every later draw with its first
// possible option, and records those later draws, so the caller can start one
// new run per untried option (enumerate()). Draws the script cannot represent
// (continuous values, raw longs used for Java shuffles) throw, so an
// unsupported mechanic fails closed.

#ifdef STS_EXACT_CHANCE

#include <cstdint>
#include <stdexcept>
#include <string>
#include <vector>

namespace sts::exact {

    class ChanceScript {
    public:
        // Canonical draw order (set by the caller only when draw order cannot
        // matter): consecutive draws from one pile choose non-decreasing card
        // classes, weighted so that every multiset keeps its total probability.
        bool canonicalDraws = false;

        double prob = 1.0;

        void reset(const std::vector<int> &p) {
            prefix_ = p;
            pos_ = 0;
            prob = 1.0;
            recCount_.clear();
            recChosen_.clear();
            recWeights_.clear();
            batchPile_ = nullptr;
            lastWasDraw_ = false;
        }

        // After a run: the prefixes of the outcomes this run did not take.
        void untried(std::vector<std::vector<int>> &stack) const {
            std::vector<int> path = prefix_;
            std::size_t offset = 0;
            for (std::size_t j = 0; j < recCount_.size(); ++j) {
                for (int o = 0; o < recCount_[j]; ++o) {
                    if (o == recChosen_[j] || recWeights_[offset + o] <= 0) continue;
                    auto next = path;
                    next.push_back(o);
                    stack.push_back(std::move(next));
                }
                path.push_back(recChosen_[j]);
                offset += static_cast<std::size_t>(recCount_[j]);
            }
        }

        int choose(const double *weights, int n) {
            lastWasDraw_ = false;
            return pick(weights, n);
        }

        int chooseUniform(int n) {
            if (n <= 0) throw std::runtime_error("exact chance: empty uniform draw");
            lastWasDraw_ = false;
            if (n == 1) return 0;
            uniform_.assign(static_cast<std::size_t>(n), 1.0 / n);
            return pick(uniform_.data(), n);
        }

        // P(nextFloat() < chance) for the engine's 24-bit floats.
        static double booleanProbability(float chance) {
            if (!(chance > 0)) return 0;
            if (chance >= 1) return 1;
            const double scaled = static_cast<double>(chance) * 16777216.0;
            double count = static_cast<double>(static_cast<std::int64_t>(scaled));
            if (count < scaled) count += 1;
            return count / 16777216.0;
        }

        bool chooseBoolean(float chance) {
            lastWasDraw_ = false;
            const double p = booleanProbability(chance);
            if (p <= 0) return false;
            if (p >= 1) return true;
            const double w[2] = {p, 1 - p};
            return pick(w, 2) == 0;
        }

        // A draw from the `n` unknown cards whose equivalence classes are
        // `keys`; `remaining` draws (this one included) are left in the current
        // multi-card draw (0 when unknown). Returns the offset of the drawn card.
        //
        // Canonical mode draws the batch's multiset in ascending class order: the
        // drawn cards are a uniform subset of the batch's unknown cards, and each
        // step chooses the next class of that subset's sorted class sequence with
        // its exact conditional probability, so every multiset is reached once with
        // its full probability and no order is enumerated.
        int chooseDraw(const void *pile, const std::uint64_t *keys, int n, int remaining, bool fresh) {
            if (n > kMaxClasses) throw std::runtime_error("exact chance: draw pile too large");
            int classCount = 0;
            for (int i = 0; i < n; ++i) {
                int c = 0;
                while (c < classCount && classes_[c] != keys[i]) ++c;
                if (c == classCount) { classes_[c] = keys[i]; counts_[c] = 0; first_[c] = i; ++classCount; }
                ++counts_[c];
            }
            const bool canonical = canonicalDraws && remaining > 0;
            const bool continuing = canonical && !fresh && lastWasDraw_ && pile == batchPile_ && n == batchUnknownAfter_;
            if (!continuing) { batchDraws_ = 0; batchDrawnCount_ = 0; }
            if (!canonical) {
                for (int c = 0; c < classCount; ++c) weights_[c] = static_cast<double>(counts_[c]) / n;
            } else {
                const int r = remaining < n ? remaining : n;
                // Classes above the previous choice (all classes when none).
                auto countAbove = [&](std::uint64_t key, bool inclusive) {
                    int total = 0;
                    for (int c = 0; c < classCount; ++c)
                        if (inclusive ? classes_[c] >= key : classes_[c] > key) total += counts_[c];
                    return total;
                };
                int prevIdx = -1;
                if (continuing) for (int c = 0; c < classCount; ++c) if (classes_[c] == batchLastKey_) prevIdx = c;
                const int j = continuing ? drawnOf(batchLastKey_) : 0;
                const int np = (prevIdx >= 0 ? counts_[prevIdx] : 0) + j;   // the batch's original count
                const int g = continuing ? countAbove(batchLastKey_, false) : n;
                double denom = 0, stay = 0;
                for (int t = 0; t <= r; ++t) {
                    const double ways = binom(np, j + t) * binom(g, r - t);
                    denom += ways;
                    if (t >= 1) stay += ways;
                }
                if (!continuing) { denom = binom(g, r); stay = 0; }
                const double leave = continuing ? binom(np, j) : 1.0;
                for (int c = 0; c < classCount; ++c) {
                    if (c == prevIdx) { weights_[c] = stay / denom; continue; }
                    if (continuing && classes_[c] < batchLastKey_) { weights_[c] = 0; continue; }
                    weights_[c] = leave * (binom(countAbove(classes_[c], true) - (continuing ? 0 : 0), r)
                                           - binom(countAbove(classes_[c], false), r)) / denom;
                }
            }
            const int c = pick(weights_, classCount);
            ++batchDraws_;
            bool found = false;
            for (int i = 0; i < batchDrawnCount_; ++i) if (batchDrawnKey_[i] == classes_[c]) { ++batchDrawnN_[i]; found = true; }
            if (!found) { batchDrawnKey_[batchDrawnCount_] = classes_[c]; batchDrawnN_[batchDrawnCount_] = 1; ++batchDrawnCount_; }
            batchLastKey_ = classes_[c];
            batchPile_ = pile;
            batchUnknownAfter_ = n - 1;
            lastWasDraw_ = canonical;
            return first_[c];
        }

        static double binom(int n, int k) {
            if (k < 0 || n < 0 || k > n) return 0;
            static const auto table = [] {
                std::vector<double> t(static_cast<std::size_t>(kMaxClasses + 1) * (kMaxClasses + 1), 0.0);
                for (int a = 0; a <= kMaxClasses; ++a) {
                    t[a * (kMaxClasses + 1)] = 1;
                    for (int b = 1; b <= a; ++b)
                        t[a * (kMaxClasses + 1) + b] = t[(a - 1) * (kMaxClasses + 1) + b - 1]
                            + (b <= a - 1 ? t[(a - 1) * (kMaxClasses + 1) + b] : 0);
                }
                return t;
            }();
            return table[static_cast<std::size_t>(n) * (kMaxClasses + 1) + k];
        }

    private:
        static constexpr int kMaxClasses = 128;
        std::vector<int> prefix_;
        std::size_t pos_ = 0;
        std::vector<int> recCount_, recChosen_;
        std::vector<double> recWeights_;
        std::vector<double> uniform_;

        std::uint64_t classes_[kMaxClasses]{};
        int counts_[kMaxClasses]{}, first_[kMaxClasses]{};
        double weights_[kMaxClasses]{};

        const void *batchPile_ = nullptr;
        int batchUnknownAfter_ = -1;
        int batchDraws_ = 0;
        std::uint64_t batchLastKey_ = 0;
        std::uint64_t batchDrawnKey_[kMaxClasses]{};
        int batchDrawnN_[kMaxClasses]{};
        int batchDrawnCount_ = 0;
        bool lastWasDraw_ = false;

        int drawnOf(std::uint64_t key) const {
            for (int i = 0; i < batchDrawnCount_; ++i) if (batchDrawnKey_[i] == key) return batchDrawnN_[i];
            return 0;
        }

        int pick(const double *weights, int n) {
            if (pos_ < prefix_.size()) {
                const int k = prefix_[pos_++];
                if (k >= n) throw std::runtime_error("exact chance: replay diverged");
                prob *= weights[k];
                return k;
            }
            int k = 0;
            while (k < n && weights[k] <= 0) ++k;
            if (k == n) {
                // A canonical-order dead end: this run has probability 0. Finish it
                // harmlessly; the caller drops it and still tries its siblings.
                prob = 0;
                k = 0;
            }
            recCount_.push_back(n);
            recChosen_.push_back(k);
            recWeights_.insert(recWeights_.end(), weights, weights + n);
            ++pos_;
            prob *= weights[k];
            return k;
        }
    };

    inline thread_local ChanceScript *g_chanceScript = nullptr;
    // Draws left in the current CardManager::draw call (0 outside one), and
    // whether that call has made no script draw yet.
    inline thread_local int g_drawBatchRemaining = 0;
    inline thread_local bool g_drawBatchFresh = false;

    [[noreturn]] inline void unsupportedDraw(const char *what) {
        throw std::runtime_error(std::string("exact chance: unsupported random draw: ") + what);
    }

}

#endif

#endif //STS_LIGHTSPEED_EXACTCHANCE_H
