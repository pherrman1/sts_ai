// Amber Eye exploration (az_run_driver.h amberExploreC, 2026-11-17): the per-item c solves
// natural + sum_b n_b min(1, c exp(-m_b / T)) = need. Checks hand cases, the 0 / infinity ends, monotonicity in the
// target, and that the solved c reproduces `need` on the logged gaps.
#include <cmath>
#include <cstdio>

#include "az_run_driver.h"

using namespace sts::azbench;

namespace {
    int fails = 0;
    void check(bool ok, const char *what) {
        if (!ok) { std::printf("FAIL %s\n", what); ++fails; }
    }
    double picked(const AmberGapHist &h, double c, double T) {
        double x = static_cast<double>(h.natural);
        for (int b = 0; b < AmberGapHist::kBins; ++b)
            x += h.n[b] * std::min(1.0, c * std::exp(-(b + 0.5) * AmberGapHist::kBin / T));
        return x;
    }
}

int main() {
    const double T = 4.0;
    AmberGapHist h;
    // Empty log: nothing can be picked -> infinity for any positive need, 0 for need 0.
    check(std::isinf(amberExploreC(h, 1.0, T)), "empty log -> infinity");
    check(amberExploreC(h, 0.0, T) == 0.0, "need 0 -> 0");
    // Natural picks already reach the need: c = 0 (no boost).
    h.add(0.0); h.add(0.0); h.add(0.0);
    check(h.natural == 3, "m = 0 counts as natural");
    check(amberExploreC(h, 3.0, T) == 0.0, "natural >= need -> 0");
    // One run with gap 2.0 (bin centre 2.025): need 3.5 -> c exp(-2.025 / 4) = 0.5.
    h.add(2.0);
    const double c1 = amberExploreC(h, 3.5, T);
    check(std::fabs(c1 - 0.5 * std::exp(2.025 / T)) < 1e-9, "single gap hand case");
    // Need above everything logged (3 natural + 1): infinity.
    check(std::isinf(amberExploreC(h, 4.5, T)), "need above all logged runs -> infinity");
    // explorePerOffer (2026-11-19): runs counts every logged run; need = target * runs is always reachable (finite c).
    check(h.runs == 4, "runs counts natural and gap runs");
    check(std::isfinite(amberExploreC(h, 0.99 * static_cast<double>(h.runs), T)), "per-offer need below runs -> finite");
    // Many gaps: the solved c reproduces need, and c grows with need.
    AmberGapHist g;
    for (int i = 0; i < 1000; ++i) g.add(0.013 * i);   // gaps 0 .. 13
    g.add(100.0);                                        // far gap -> last bin
    check(g.n[AmberGapHist::kBins - 1] == 1, "far gap in the last bin");
    double prev = 0;
    for (double need : {5.0, 50.0, 200.0, 600.0}) {
        const double c = amberExploreC(g, need, T);
        check(std::fabs(picked(g, c, T) - need) < 1e-6 * need, "solved c reproduces need");
        check(c > prev, "c increases with need");
        prev = c;
    }
    // exploreItemHash (2026-11-21): the clean rule names the choice, not its slot / price / affordability.
    {
        using sts::search::AmberToken;
        const std::uint16_t one = 0x3c00, half = 0x3800, quarter = 0x3400;   // float16 1.0, 0.5, 0.25
        const int kChooseOption = 11, kChooseCard = 12;
        auto opt = [&](int kind, int id) { AmberToken t{}; t.ids[0] = static_cast<std::int16_t>(id); t.f[3] = one;
                                           t.f[12 + kind] = one; t.f[31] = one; return t; };
        AmberToken a = opt(8, 300), b = opt(8, 300);          // the same shop relic ...
        a.f[30] = quarter; a.f[32] = half; a.f[33] = one;     // ... in another slot, at another price
        b.f[30] = half; b.f[32] = one;
        check(exploreItemHash(kChooseOption, a, true, true) == exploreItemHash(kChooseOption, b, true, true),
              "clean: one shop relic at two prices / slots is one item");
        check(exploreItemHash(kChooseOption, a, true, false) != exploreItemHash(kChooseOption, b, true, false),
              "first rule: price / slot split the item");
        check(exploreItemHash(kChooseOption, a, true, true)
              != exploreItemHash(kChooseOption, opt(8, 301), true, true), "clean: another relic is another item");
        check(exploreItemHash(kChooseOption, opt(8, 300), true, true)
              != exploreItemHash(kChooseOption, opt(2, 300), true, true), "clean: shop relic != reward relic");
        check(exploreItemHash(kChooseOption, opt(8, 300), true, true)
              != exploreItemHash(kChooseOption, opt(11, 300), true, true), "clean: shop relic != boss relic");
        AmberToken e0 = opt(14, 960), e1 = opt(14, 960), e0b = opt(14, 960);   // one event, options 0 and 1
        e0.f[40] = one; e1.f[41] = one; e0b.f[40] = one; e0b.ids[1] = 7; e0b.f[34] = half;
        check(exploreItemHash(kChooseOption, e0, true, true) != exploreItemHash(kChooseOption, e1, true, true),
              "clean: event options differ by index");
        check(exploreItemHash(kChooseOption, e0, true, true) == exploreItemHash(kChooseOption, e0b, true, true),
              "clean: the deck card / gold an event option names does not split it");
        AmberToken n15 = opt(13, 0), n16 = opt(13, 0), n15d = opt(13, 0);     // Neow bonuses past index 11
        n15.f[40 + 15] = one; n16.f[40 + 16] = one; n15d.f[40 + 15] = one; n15d.f[59] = one;
        check(exploreItemHash(kChooseOption, n15, true, false) == exploreItemHash(kChooseOption, n16, true, false),
              "first rule: Neow bonuses 15 and 16 collide");
        check(exploreItemHash(kChooseOption, n15, true, true) != exploreItemHash(kChooseOption, n16, true, true),
              "clean: Neow bonuses differ");
        check(exploreItemHash(kChooseOption, n15, true, true) != exploreItemHash(kChooseOption, n15d, true, true),
              "clean: Neow drawbacks differ");
        AmberToken r0 = opt(12, 0), r1 = opt(12, 0);
        r0.f[40] = one; r1.f[41] = one;
        check(exploreItemHash(kChooseOption, r0, true, true) != exploreItemHash(kChooseOption, r1, true, true),
              "clean: rest options differ");
        AmberToken c1{}, c2{}, c3{};                               // card rewards: the card id only
        c1.ids[0] = 40; c2.ids[0] = 40; c2.f[12] = one; c2.f[11] = half; c3.ids[0] = 41;
        check(exploreItemHash(kChooseCard, c1, false, true) == exploreItemHash(kChooseCard, c2, false, true)
              && exploreItemHash(kChooseCard, c1, false, true) != exploreItemHash(kChooseCard, c3, false, true),
              "clean: a card reward is its card id");
        AmberToken sc = opt(7, 40);
        check(exploreItemHash(kChooseOption, sc, true, true) != exploreItemHash(kChooseCard, c1, false, true),
              "clean: shop card != card reward");
    }
    // Utility AMBER2 (2026-11-20): out of combat (P(win) + 0.25 H) / 1.25, in combat (F + 0.5 H) / 1.5.
    check(std::fabs(amber2Value(false, 0.9, 0.2, 0.6) - (0.2 + 0.25 * 0.6) / 1.5) < 1e-12, "amber2 out of combat");
    check(std::fabs(amber2Value(true, 0.9, 0.2, 0.6) - (0.9 + 0.5 * 0.6) / 1.5) < 1e-12, "amber2 in combat");
    check(std::fabs(amber2Value(false, 0.0, 1.0, 1.0) - 1.25 / 1.5) < 1e-12 && amber2Value(true, 1.0, 0.0, 1.0) == 1.0,
          "amber2 max: combat 1, out of combat 1.25 / 1.5 (Amber's ratio)");
    check(amber2Value(false, 1.0, 0.0, 0.0) == 0.0, "amber2 out of combat ignores F");
    // A Heart kill (H of a kill on floor 55 with 60 HP) beats any death out of combat; a later death beats an earlier
    // one only through H.
    const double kill = amber2Value(false, 1.0, 1.0, amberTerminalH(true, true, 55, 60));
    const double die54 = amber2Value(false, 54 / 57.0, 0.0, amberTerminalH(false, false, 54, 0));
    const double die20 = amber2Value(false, 20 / 57.0, 0.0, amberTerminalH(false, false, 20, 0));
    check(kill > die54 && die54 > die20, "amber2 terminal order");
    if (fails) return 1;
    std::printf("az explore amber: ok\n");
    return 0;
}
