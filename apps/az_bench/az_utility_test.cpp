// Stage 1 utility (az_run_driver.h, 2026-11-17): Amber Eye's H from per-floor HP, its terminal values and the
// per-floor HP labels. Checks the formula on hand-computed cases, that a state's H equals the terminal H once its
// per-floor HP are the realized ones (no cliff between "about to end" and "ended"), and that a keyless act 3 victory
// is worth more than dying to the act 3 boss.
#include <cmath>
#include <cstdio>
#include <vector>

#include "az_run_driver.h"

using namespace sts::azbench;

namespace {
    int fails = 0;
    void check(bool ok, const char *what) {
        if (!ok) { std::printf("FAIL %s\n", what); ++fails; }
    }
    bool near(double a, double b) { return std::fabs(a - b) < 1e-9; }
}

int main() {
    std::vector<float> hpf(kFloors, 0.f);
    // Floor 1, no HP anywhere: H = 0. Full HP (255) on every floor: H = 1.
    check(near(amberH(1, hpf.data()), 0.0), "H(1, 0) = 0");
    std::vector<float> full(kFloors, 1.f);
    check(near(amberH(1, full.data()), 1.0), "H(1, full) = 1");
    check(near(amberH(30, full.data()), 1.0), "H(30, full) = 1");
    // Floor 10, 51 HP (0.2) on floors 10..20, 0 after: H = (9 + 11 * 0.2) / 56.
    for (int f = 10; f <= 20; ++f) hpf[f - 1] = 0.2f;
    check(std::fabs(amberH(10, hpf.data()) - (9 + 11 * 0.2) / 56) < 1e-6, "H(10) hand case");
    // Floors before the state's floor are ignored (past floors count 1), values are clamped to [0, 1].
    hpf[0] = 5.f;
    hpf[25] = -3.f;
    check(std::fabs(amberH(10, hpf.data()) - (9 + 11 * 0.2) / 56) < 1e-6, "H ignores past floors, clamps");
    check(near(amberH(0, full.data()), amberH(1, full.data())), "floor 0 counts as floor 1");

    // Terminals. Death on floor d: (d - 1) / 56. Keyless victory on floor 51 with 40 HP: (50 + 40 / 255) / 56.
    check(near(amberTerminalH(false, false, 33, 0), 32.0 / 56), "death terminal");
    check(near(amberTerminalH(false, true, 51, 40), (50 + 40 / 255.0) / 56), "keyless victory terminal");
    check(near(amberTerminalH(true, true, 55, 255), (54 + 2.0) / 56), "Heart kill terminal keeps HP to floor 56");
    check(amberTerminalH(false, true, 51, 1) > amberTerminalH(false, false, 50, 0), "keyless victory > act 3 boss death");

    // Consistency: a state whose per-floor predictions equal the realized run has the terminal's H.
    {
        std::vector<float> real(kFloors, 0.f);
        real[50 - 1] = 30 / 255.f;   // HP 30 at the end of floor 50 (boss), then the keyless victory room on 51
        real[51 - 1] = 30 / 255.f;
        check(std::fabs(amberH(51, real.data()) - amberTerminalH(false, true, 51, 30)) < 1e-6, "state = terminal (keyless)");
        std::vector<float> dead(kFloors, 0.f);
        check(near(amberH(33, dead.data()), amberTerminalH(false, false, 33, 0)), "state = terminal (death)");
    }

    // Labels: floor HP 1..3 recorded, death on floor 3; a sample on floor 2 sees -1, hp2, 0, 0, ...
    {
        std::vector<std::int16_t> floorHp(kFloors + 1, -1);
        floorHp[1] = 70;
        floorHp[2] = 60;
        floorHp[3] = 0;
        std::vector<std::int16_t> out(kFloors);
        amberFloorLabels(2, floorHp.data(), 0, out.data());
        check(out[0] == -1 && out[1] == 60 && out[2] == 0 && out[55] == 0, "labels after a death");
        amberFloorLabels(0, floorHp.data(), 0, out.data());
        check(out[0] == 70, "a floor-0 sample is labelled from floor 1");
        floorHp[3] = 50;
        amberFloorLabels(3, floorHp.data(), 50, out.data());
        check(out[1] == -1 && out[2] == 50 && out[55] == 50, "labels after a Heart kill keep the final HP");
    }
    if (fails) return 1;
    std::printf("az_utility_test: ok\n");
    return 0;
}
