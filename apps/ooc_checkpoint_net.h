// Native OOC checkpoint utility model.  Compact MLP with GELU activations.
// Loaded from the binary exported by export_ooc_checkpoint.py.
#include <cmath>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <algorithm>

struct OocCheckpointNet {
    static constexpr int NSTATE = 1017, NHIDDEN = 256, NHIDDEN2 = 128;
    static constexpr int NACTION = 32, AHIDDEN = 32, AHIDDEN2 = 16;
    static constexpr int NSCR = 16, SCRDIM = 8, NACT = 4, ACTDIM = 4;
    static constexpr int HEADIN = NHIDDEN2 + AHIDDEN2 + SCRDIM + ACTDIM;  // 156
    static constexpr int HHIDDEN = 96;

    float stateMean[NSTATE], stateInv[NSTATE];

    // state encoder: Linear(1017,256) -> LayerNorm -> GELU -> Dropout -> Linear(256,128) -> GELU
    float s0w[NHIDDEN][NSTATE], s0b[NHIDDEN];
    float s1w[NHIDDEN], s1b[NHIDDEN];               // LayerNorm
    float s4w[NHIDDEN2][NHIDDEN], s4b[NHIDDEN2];

    // action encoder: Linear(32,32) -> GELU -> Linear(32,16)
    float a0w[AHIDDEN][NACTION], a0b[AHIDDEN];
    float a3w[AHIDDEN2][AHIDDEN], a3b[AHIDDEN2];

    // embeddings
    float screenW[NSCR][SCRDIM];
    float actW[NACT][ACTDIM];

    // head: Linear(156,96) -> GELU -> Linear(96,1)
    float h0w[HHIDDEN][HEADIN], h0b[HHIDDEN];
    float h2w[HHIDDEN], h2b;

    bool ok = false;

    bool load(const std::string &path) {
        FILE *f = std::fopen(path.c_str(), "rb");
        if (!f) { std::fprintf(stderr, "[ooc-cp-net] cannot open %s\n", path.c_str()); return false; }
        char hdr[13] = {};
        if (std::fread(hdr, 1, 12, f) != 12 || std::memcmp(hdr, "OOC_CHKPT_V1", 12) != 0) {
            std::fclose(f); return false;
        }
        int dims[4];
        if (std::fread(dims, sizeof(int), 4, f) != 4
            || dims[0] != NSTATE || dims[1] != NHIDDEN || dims[2] != NHIDDEN2 || dims[3] != NACTION) {
            std::fclose(f); return false;
        }
        std::fread(stateMean, sizeof(float), NSTATE, f);
        std::fread(stateInv, sizeof(float), NSTATE, f);
        std::fread(s0w, sizeof(float), NHIDDEN * NSTATE, f);
        std::fread(s0b, sizeof(float), NHIDDEN, f);
        std::fread(s1w, sizeof(float), NHIDDEN, f);
        std::fread(s1b, sizeof(float), NHIDDEN, f);
        std::fread(s4w, sizeof(float), NHIDDEN2 * NHIDDEN, f);
        std::fread(s4b, sizeof(float), NHIDDEN2, f);
        std::fread(a0w, sizeof(float), AHIDDEN * NACTION, f);
        std::fread(a0b, sizeof(float), AHIDDEN, f);
        std::fread(a3w, sizeof(float), AHIDDEN2 * AHIDDEN, f);
        std::fread(a3b, sizeof(float), AHIDDEN2, f);
        std::fread(screenW, sizeof(float), NSCR * SCRDIM, f);
        std::fread(actW, sizeof(float), NACT * ACTDIM, f);
        std::fread(h0w, sizeof(float), HHIDDEN * HEADIN, f);
        std::fread(h0b, sizeof(float), HHIDDEN, f);
        std::fread(h2w, sizeof(float), HHIDDEN, f);
        std::fread(&h2b, sizeof(float), 1, f);
        std::fclose(f);
        ok = true;
        std::cout << "[ooc-cp-net] loaded " << path << "\n";
        return true;
    }

    // State encoder: Linear -> LayerNorm -> GELU -> Linear -> GELU
    void encodeState(const float *x, float *out) const {
        float h[NHIDDEN];
        // Linear(1017,256)
        for (int j = 0; j < NHIDDEN; ++j) {
            float s = s0b[j];
            for (int i = 0; i < NSTATE; ++i) s += s0w[j][i] * x[i];
            h[j] = s;
        }
        // LayerNorm
        float mu = 0; for (int j = 0; j < NHIDDEN; ++j) mu += h[j]; mu /= NHIDDEN;
        float var = 0; for (int j = 0; j < NHIDDEN; ++j) { float d = h[j] - mu; var += d * d; }
        var = var / NHIDDEN + 1e-5f; float invStd = 1.0f / std::sqrt(var);
        for (int j = 0; j < NHIDDEN; ++j) h[j] = (h[j] - mu) * invStd * s1w[j] + s1b[j];
        // GELU
        for (int j = 0; j < NHIDDEN; ++j) h[j] = gelu(h[j]);
        // Linear(256,128) -> GELU
        for (int j = 0; j < NHIDDEN2; ++j) {
            float s = s4b[j];
            for (int i = 0; i < NHIDDEN; ++i) s += s4w[j][i] * h[i];
            out[j] = gelu(s);
        }
    }

    // Action encoder: Linear(32,32) -> GELU -> Linear(32,16)
    void encodeAction(const float *bits, float *out) const {
        float h[AHIDDEN];
        for (int j = 0; j < AHIDDEN; ++j) {
            float s = a0b[j];
            for (int i = 0; i < NACTION; ++i) s += a0w[j][i] * bits[i];
            h[j] = gelu(s);
        }
        for (int j = 0; j < AHIDDEN2; ++j) {
            float s = a3b[j];
            for (int i = 0; i < AHIDDEN; ++i) s += a3w[j][i] * h[i];
            out[j] = s;
        }
    }

    // Full forward pass
    float predict(const float *state, std::uint32_t actionBits, int screen, int act) const {
        // Normalize state
        float x[NSTATE];
        for (int i = 0; i < NSTATE; ++i)
            x[i] = std::clamp((state[i] - stateMean[i]) * stateInv[i], -8.0f, 8.0f);

        float sOut[NHIDDEN2], aOut[AHIDDEN2];
        encodeState(x, sOut);

        float bits[NACTION];
        for (int i = 0; i < NACTION; ++i) bits[i] = (float)((actionBits >> i) & 1u);
        encodeAction(bits, aOut);

        // Combined
        float z[HEADIN];
        int p = 0;
        for (int i = 0; i < NHIDDEN2; ++i) z[p++] = sOut[i];
        for (int i = 0; i < AHIDDEN2; ++i) z[p++] = aOut[i];
        if (screen >= 0 && screen < NSCR)
            for (int i = 0; i < SCRDIM; ++i) z[p++] = screenW[screen][i];
        else
            for (int i = 0; i < SCRDIM; ++i) z[p++] = 0.0f;
        if (act >= 0 && act < NACT)
            for (int i = 0; i < ACTDIM; ++i) z[p++] = actW[act][i];
        else
            for (int i = 0; i < ACTDIM; ++i) z[p++] = 0.0f;

        // Head: Linear(156,96) -> GELU -> Linear(96,1)
        float hh[HHIDDEN];
        for (int j = 0; j < HHIDDEN; ++j) {
            float s = h0b[j];
            for (int i = 0; i < HEADIN; ++i) s += h0w[j][i] * z[i];
            hh[j] = gelu(s);
        }
        float out = h2b;
        for (int i = 0; i < HHIDDEN; ++i) out += h2w[i] * hh[i];
        return out;
    }

    static float gelu(float x) {
        const float a = x * x * x * 0.044715f;
        return 0.5f * x * (1.0f + std::tanh(0.7978845608028654f * (x + a)));
    }
};

static OocCheckpointNet g_oocCheckpointNet;
