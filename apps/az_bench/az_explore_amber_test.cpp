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
    if (fails) return 1;
    std::printf("az explore amber: ok\n");
    return 0;
}
