// Native OOC strategic model.  Multi-head policy/value net with GELU activations.
// Loaded from the binary exported by export_strategic.py.
#pragma once
#include <cstdio>
#include <cstring>
#include <cstdint>
#include <cmath>
#include <string>

struct OocStrategicNet {
    static constexpr int NSTATE = 1017, NHIDDEN = 256, NHIDDEN2 = 128;
    static constexpr int NBITS = 32, AHIDDEN = 32, AHIDDEN2 = 16;
    static constexpr int NCAT = 6, CATVOCAB = 512, CATDIM = 4;
    static constexpr int ATYPEVOCAB = 16, ATYPEDIM = 8;
    static constexpr int NSCR = 16, SCRDIM = 8;
    static constexpr int CATIN = NCAT * CATDIM + ATYPEDIM;  // 32
    static constexpr int POLIN = NHIDDEN2 + AHIDDEN2 + AHIDDEN2 + SCRDIM;  // 168
    static constexpr int POLHID = 96, VALHID = 64;

    float stateMean[NSTATE], stateInv[NSTATE];

    // state encoder: Linear(1017,256) -> LayerNorm -> GELU -> Dropout -> Linear(256,128) -> GELU
    float s0w[NHIDDEN][NSTATE], s0b[NHIDDEN];
    float s1w[NHIDDEN], s1b[NHIDDEN];               // LayerNorm
    float s4w[NHIDDEN2][NHIDDEN], s4b[NHIDDEN2];

    // action bit encoder: Linear(32,32) -> GELU -> Dropout -> Linear(32,16)  (no final GELU)
    float a0w[AHIDDEN][NBITS], a0b[AHIDDEN];
    float a3w[AHIDDEN2][AHIDDEN], a3b[AHIDDEN2];

    // action category encoder: Linear(32,32) -> GELU -> Linear(32,16)  (no final GELU)
    float cat0w[AHIDDEN][CATIN], cat0b[AHIDDEN];
    float cat3w[AHIDDEN2][AHIDDEN], cat3b[AHIDDEN2];

    // embeddings
    float cw[NCAT][CATVOCAB][CATDIM];
    float atypeW[ATYPEVOCAB][ATYPEDIM];
    float screenW[NSCR][SCRDIM];

    // policy head: Linear(168,96) -> GELU -> Linear(96,1)
    float pol0w[POLHID][POLIN], pol0b[POLHID];
    float pol2w[POLHID], pol2b;

    // one value head per screen (screens 1..8 -> index 0..7):
    // Linear(128,64) -> GELU -> Linear(64,1)
    float val0w[8][VALHID][NHIDDEN2], val0b[8][VALHID];
    float val2w[8][VALHID], val2b[8];

    // Q head: Linear(168,96) -> GELU -> Linear(96,1) on the same z concat as the policy head
    float q0w[POLHID][POLIN], q0b[POLHID];
    float q2w[POLHID], q2b;

    // Q_win format (OOC_STRAT_V5): sigmoided probability outputs, plus two
    // auxiliary probability heads Q_HP / Q_floor on the same concat.
    bool probQ = false;
    float qhp0w[POLHID][POLIN], qhp0b[POLHID];
    float qhp2w[POLHID], qhp2b;
    float qfl0w[POLHID][POLIN], qfl0b[POLHID];
    float qfl2w[POLHID], qfl2b;

    // Map-DAG encoder (OOC_STRAT_V6, 5.3.2): bottom-up reverse-DAG route
    // encoder over the visible 15x7 map + zero-init residual adapter into the
    // POLIN concat, applied to MAP-screen candidates. Mirrors the trainer's
    // FullMapGraphEncoder / map_adapter (train_strategic.py).
    static constexpr int MAPDN = 32, MAPDU = 64, MAPDR = 128, MAPDOUT = 96;
    float mapRoomW[10][MAPDN], mapRowW[15][MAPDN], mapColW[7][MAPDN], mapBurnW[2][MAPDN];
    float mapUp0w[MAPDU][3 * MAPDN + 1], mapUp0b[MAPDU];
    float mapUp1w[MAPDU], mapUp1b[MAPDU];
    float mapUp3w[MAPDN][MAPDU], mapUp3b[MAPDN];
    float mapNormW[MAPDN], mapNormB[MAPDN];
    float mapRo0w[MAPDR][2 * MAPDN], mapRo0b[MAPDR];
    float mapRo1w[MAPDR], mapRo1b[MAPDR];
    float mapRo3w[MAPDOUT][MAPDR], mapRo3b[MAPDOUT];
    float mapAd0w[POLIN][MAPDOUT], mapAd0b[POLIN];
    float mapAd2w[POLIN][POLIN], mapAd2b[POLIN];
    bool mapEnc = false;

    bool ok = false;

    bool load(const std::string &path) {
        FILE *f = std::fopen(path.c_str(), "rb");
        if (!f) { std::fprintf(stderr, "[ooc-strat-net] cannot open %s\n", path.c_str()); return false; }
        auto readBlock = [f](void *dst, size_t count) -> bool {
            return std::fread(dst, 1, count, f) == count;
        };
        char hdr[13] = {};
        if (!readBlock(hdr, 12)
            || (std::memcmp(hdr, "OOC_STRAT_V3", 12) != 0
                && std::memcmp(hdr, "OOC_STRAT_V5", 12) != 0
                && std::memcmp(hdr, "OOC_STRAT_V6", 12) != 0)) {
            std::fprintf(stderr, "[ooc-strat-net] truncated payload in %s\n", path.c_str());
            std::fclose(f); return false;
        }
        const bool v6 = std::memcmp(hdr, "OOC_STRAT_V6", 12) == 0;
        probQ = std::memcmp(hdr, "OOC_STRAT_V5", 12) == 0 || v6;
        mapEnc = v6;
        int dims[4];
        if (!readBlock(dims, sizeof(dims))
            || dims[0] != NSTATE || dims[1] != NHIDDEN || dims[2] != NHIDDEN2 || dims[3] != NBITS) {
            std::fprintf(stderr, "[ooc-strat-net] truncated payload in %s\n", path.c_str());
            std::fclose(f); return false;
        }
        bool complete =
               readBlock(stateMean, sizeof(stateMean))
            && readBlock(stateInv, sizeof(stateInv))
            && readBlock(s0w, sizeof(s0w))
            && readBlock(s0b, sizeof(s0b))
            && readBlock(s1w, sizeof(s1w))
            && readBlock(s1b, sizeof(s1b))
            && readBlock(s4w, sizeof(s4w))
            && readBlock(s4b, sizeof(s4b))
            && readBlock(a0w, sizeof(a0w))
            && readBlock(a0b, sizeof(a0b))
            && readBlock(a3w, sizeof(a3w))
            && readBlock(a3b, sizeof(a3b))
            && readBlock(cat0w, sizeof(cat0w))
            && readBlock(cat0b, sizeof(cat0b))
            && readBlock(cat3w, sizeof(cat3w))
            && readBlock(cat3b, sizeof(cat3b))
            && readBlock(cw, sizeof(cw))
            && readBlock(atypeW, sizeof(atypeW))
            && readBlock(screenW, sizeof(screenW))
            && readBlock(pol0w, sizeof(pol0w))
            && readBlock(pol0b, sizeof(pol0b))
            && readBlock(pol2w, sizeof(pol2w))
            && readBlock(&pol2b, sizeof(pol2b))
            && readBlock(val0w, sizeof(val0w))
            && readBlock(val0b, sizeof(val0b))
            && readBlock(val2w, sizeof(val2w))
            && readBlock(val2b, sizeof(val2b))
            && readBlock(q0w, sizeof(q0w))
            && readBlock(q0b, sizeof(q0b))
            && readBlock(q2w, sizeof(q2w))
            && readBlock(&q2b, sizeof(q2b));
        if (complete && probQ) {
            complete = readBlock(qhp0w, sizeof(qhp0w))
                    && readBlock(qhp0b, sizeof(qhp0b))
                    && readBlock(qhp2w, sizeof(qhp2w))
                    && readBlock(&qhp2b, sizeof(qhp2b))
                    && readBlock(qfl0w, sizeof(qfl0w))
                    && readBlock(qfl0b, sizeof(qfl0b))
                    && readBlock(qfl2w, sizeof(qfl2w))
                    && readBlock(&qfl2b, sizeof(qfl2b));
        }
        if (complete && v6) {
            complete = readBlock(mapRoomW, sizeof(mapRoomW))
                    && readBlock(mapRowW, sizeof(mapRowW))
                    && readBlock(mapColW, sizeof(mapColW))
                    && readBlock(mapBurnW, sizeof(mapBurnW))
                    && readBlock(mapUp0w, sizeof(mapUp0w))
                    && readBlock(mapUp0b, sizeof(mapUp0b))
                    && readBlock(mapUp1w, sizeof(mapUp1w))
                    && readBlock(mapUp1b, sizeof(mapUp1b))
                    && readBlock(mapUp3w, sizeof(mapUp3w))
                    && readBlock(mapUp3b, sizeof(mapUp3b))
                    && readBlock(mapNormW, sizeof(mapNormW))
                    && readBlock(mapNormB, sizeof(mapNormB))
                    && readBlock(mapRo0w, sizeof(mapRo0w))
                    && readBlock(mapRo0b, sizeof(mapRo0b))
                    && readBlock(mapRo1w, sizeof(mapRo1w))
                    && readBlock(mapRo1b, sizeof(mapRo1b))
                    && readBlock(mapRo3w, sizeof(mapRo3w))
                    && readBlock(mapRo3b, sizeof(mapRo3b))
                    && readBlock(mapAd0w, sizeof(mapAd0w))
                    && readBlock(mapAd0b, sizeof(mapAd0b))
                    && readBlock(mapAd2w, sizeof(mapAd2w))
                    && readBlock(mapAd2b, sizeof(mapAd2b));
        }
        std::fclose(f);
        if (!complete) {
            std::fprintf(stderr, "[ooc-strat-net] truncated payload in %s\n", path.c_str());
            return false;
        }
        ok = true;
        std::printf("[ooc-strat-net] loaded %s (%s)\n", path.c_str(),
                    mapEnc ? "OOC_STRAT_V6 Q_win + map-DAG encoder"
                           : (probQ ? "OOC_STRAT_V5 Q_win" : "OOC_STRAT_V3"));
        return true;
    }

    // State encoder: Linear -> LayerNorm(eps=1e-5) -> GELU -> Linear -> GELU
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

    float predictValue(const float *state, int screen) const {
        // Normalize state
        float x[NSTATE];
        for (int i = 0; i < NSTATE; ++i)
            x[i] = clampf((state[i] - stateMean[i]) * stateInv[i], -8.0f, 8.0f);

        float sOut[NHIDDEN2];
        encodeState(x, sOut);

        // Screen-selected value head: Linear(128,64) -> GELU -> Linear(64,1)
        const int h0 = clampi(screen - 1, 0, 7);
        float h[VALHID];
        for (int j = 0; j < VALHID; ++j) {
            float s = val0b[h0][j];
            for (int i = 0; i < NHIDDEN2; ++i) s += val0w[h0][j][i] * sOut[i];
            h[j] = gelu(s);
        }
        float out = val2b[h0];
        for (int i = 0; i < VALHID; ++i) out += val2w[h0][i] * h[i];
        return out;
    }

    float predictPolicyLogit(const float *state, std::uint32_t actionBits,
                             const int cats[6], int actionType, int screen) const {
        // Normalize state
        float x[NSTATE];
        for (int i = 0; i < NSTATE; ++i)
            x[i] = clampf((state[i] - stateMean[i]) * stateInv[i], -8.0f, 8.0f);

        float sOut[NHIDDEN2];
        encodeState(x, sOut);

        // Action bit encoder: Linear(32,32) -> GELU -> Linear(32,16)  (no final GELU)
        float bits[NBITS];
        for (int i = 0; i < NBITS; ++i) bits[i] = (float)((actionBits >> i) & 1u);
        float bOut[AHIDDEN2];
        {
            float h[AHIDDEN];
            for (int j = 0; j < AHIDDEN; ++j) {
                float s = a0b[j];
                for (int i = 0; i < NBITS; ++i) s += a0w[j][i] * bits[i];
                h[j] = gelu(s);
            }
            for (int j = 0; j < AHIDDEN2; ++j) {
                float s = a3b[j];
                for (int i = 0; i < AHIDDEN; ++i) s += a3w[j][i] * h[i];
                bOut[j] = s;
            }
        }

        // Action category encoder: cat embeddings + atype embedding, then Linear(32,32) -> GELU -> Linear(32,16)
        float catIn[CATIN];
        int p = 0;
        for (int c = 0; c < NCAT; ++c) {
            int idx = clampi(cats[c] + 1, 0, CATVOCAB - 1);
            for (int i = 0; i < CATDIM; ++i) catIn[p++] = cw[c][idx][i];
        }
        {
            int idx = clampi(actionType + 1, 0, ATYPEVOCAB - 1);
            for (int i = 0; i < ATYPEDIM; ++i) catIn[p++] = atypeW[idx][i];
        }
        float aOut[AHIDDEN2];
        {
            float h[AHIDDEN];
            for (int j = 0; j < AHIDDEN; ++j) {
                float s = cat0b[j];
                for (int i = 0; i < CATIN; ++i) s += cat0w[j][i] * catIn[i];
                h[j] = gelu(s);
            }
            for (int j = 0; j < AHIDDEN2; ++j) {
                float s = cat3b[j];
                for (int i = 0; i < AHIDDEN; ++i) s += cat3w[j][i] * h[i];
                aOut[j] = s;
            }
        }

        // Combined
        float z[POLIN];
        p = 0;
        for (int i = 0; i < NHIDDEN2; ++i) z[p++] = sOut[i];
        for (int i = 0; i < AHIDDEN2; ++i) z[p++] = bOut[i];
        for (int i = 0; i < AHIDDEN2; ++i) z[p++] = aOut[i];
        if (screen >= 0 && screen < NSCR)
            for (int i = 0; i < SCRDIM; ++i) z[p++] = screenW[screen][i];
        else
            for (int i = 0; i < SCRDIM; ++i) z[p++] = 0.0f;

        // Policy head: Linear(168,96) -> GELU -> Linear(96,1)
        float hh[POLHID];
        for (int j = 0; j < POLHID; ++j) {
            float s = pol0b[j];
            for (int i = 0; i < POLIN; ++i) s += pol0w[j][i] * z[i];
            hh[j] = gelu(s);
        }
        float out = pol2b;
        for (int i = 0; i < POLHID; ++i) out += pol2w[i] * hh[i];
        return out;
    }

    float predictActionValue(const float *state, std::uint32_t actionBits,
                             const int cats[6], int actionType, int screen) const {
        // Normalize state
        float x[NSTATE];
        for (int i = 0; i < NSTATE; ++i)
            x[i] = clampf((state[i] - stateMean[i]) * stateInv[i], -8.0f, 8.0f);

        float sOut[NHIDDEN2];
        encodeState(x, sOut);

        // Action bit encoder: Linear(32,32) -> GELU -> Linear(32,16)  (no final GELU)
        float bits[NBITS];
        for (int i = 0; i < NBITS; ++i) bits[i] = (float)((actionBits >> i) & 1u);
        float bOut[AHIDDEN2];
        {
            float h[AHIDDEN];
            for (int j = 0; j < AHIDDEN; ++j) {
                float s = a0b[j];
                for (int i = 0; i < NBITS; ++i) s += a0w[j][i] * bits[i];
                h[j] = gelu(s);
            }
            for (int j = 0; j < AHIDDEN2; ++j) {
                float s = a3b[j];
                for (int i = 0; i < AHIDDEN; ++i) s += a3w[j][i] * h[i];
                bOut[j] = s;
            }
        }

        // Action category encoder: cat embeddings + atype embedding, then Linear(32,32) -> GELU -> Linear(32,16)
        float catIn[CATIN];
        int p = 0;
        for (int c = 0; c < NCAT; ++c) {
            int idx = clampi(cats[c] + 1, 0, CATVOCAB - 1);
            for (int i = 0; i < CATDIM; ++i) catIn[p++] = cw[c][idx][i];
        }
        {
            int idx = clampi(actionType + 1, 0, ATYPEVOCAB - 1);
            for (int i = 0; i < ATYPEDIM; ++i) catIn[p++] = atypeW[idx][i];
        }
        float aOut[AHIDDEN2];
        {
            float h[AHIDDEN];
            for (int j = 0; j < AHIDDEN; ++j) {
                float s = cat0b[j];
                for (int i = 0; i < CATIN; ++i) s += cat0w[j][i] * catIn[i];
                h[j] = gelu(s);
            }
            for (int j = 0; j < AHIDDEN2; ++j) {
                float s = cat3b[j];
                for (int i = 0; i < AHIDDEN; ++i) s += cat3w[j][i] * h[i];
                aOut[j] = s;
            }
        }

        // Combined
        float z[POLIN];
        p = 0;
        for (int i = 0; i < NHIDDEN2; ++i) z[p++] = sOut[i];
        for (int i = 0; i < AHIDDEN2; ++i) z[p++] = bOut[i];
        for (int i = 0; i < AHIDDEN2; ++i) z[p++] = aOut[i];
        if (screen >= 0 && screen < NSCR)
            for (int i = 0; i < SCRDIM; ++i) z[p++] = screenW[screen][i];
        else
            for (int i = 0; i < SCRDIM; ++i) z[p++] = 0.0f;

        // Q head: Linear(168,96) -> GELU -> Linear(96,1)
        float hh[POLHID];
        for (int j = 0; j < POLHID; ++j) {
            float s = q0b[j];
            for (int i = 0; i < POLIN; ++i) s += q0w[j][i] * z[i];
            hh[j] = gelu(s);
        }
        float out = q2b;
        for (int i = 0; i < POLHID; ++i) out += q2w[i] * hh[i];
        if (probQ) out = 1.0f / (1.0f + std::exp(-out));   // Q_win: P(victory)
        return out;
    }

    // Route embedding for one legal child (V6 map-DAG encoder, 5.3.2): node =
    // room+row+col+burning embeddings; bottom-up reverse sweep rows 14 -> 0
    // with mean+max child messages and log1p degree; readout pools the chosen
    // child's subtree (row-0 roots when py < 0 = the act's first pick). Exact
    // mirror of train_strategic.py::FullMapGraphEncoder.
    void encodeMapGraph(const int rooms[105], const int edges[105],
                        const int special[105], int px, int py, int chosenX,
                        float out[MAPDOUT]) const {
        float base[15][7][MAPDN];
        for (int y = 0; y < 15; ++y)
            for (int x = 0; x < 7; ++x) {
                const int i = y * 7 + x;
                const int rid = clampi(rooms[i], 0, 9);
                for (int j = 0; j < MAPDN; ++j)
                    base[y][x][j] = mapRoomW[rid][j] + mapRowW[y][j]
                                  + mapColW[x][j] + mapBurnW[special[i] ? 1 : 0][j];
            }
        float graph[15][7][MAPDN];
        for (int x = 0; x < 7; ++x)
            for (int j = 0; j < MAPDN; ++j) graph[14][x][j] = base[14][x][j];
        for (int y = 13; y >= 0; --y) {
            for (int x = 0; x < 7; ++x) {
                const int em = edges[y * 7 + x];
                float mean[MAPDN] = {}, maxv[MAPDN] = {};
                int deg = 0;
                for (int cx = 0; cx < 7; ++cx)
                    if (em & (1 << cx)) {
                        ++deg;
                        for (int j = 0; j < MAPDN; ++j) {
                            const float v = graph[y + 1][cx][j];
                            mean[j] += v;
                            if (deg == 1 || v > maxv[j]) maxv[j] = v;
                        }
                    }
                if (deg) for (int j = 0; j < MAPDN; ++j) mean[j] /= (float)deg;
                float upIn[3 * MAPDN + 1];
                for (int j = 0; j < MAPDN; ++j) upIn[j] = base[y][x][j];
                for (int j = 0; j < MAPDN; ++j) upIn[MAPDN + j] = mean[j];
                for (int j = 0; j < MAPDN; ++j) upIn[2 * MAPDN + j] = maxv[j];
                upIn[3 * MAPDN] = std::log1p((float)deg);
                float h[MAPDU];
                for (int j = 0; j < MAPDU; ++j) {
                    float s = mapUp0b[j];
                    for (int i = 0; i < 3 * MAPDN + 1; ++i) s += mapUp0w[j][i] * upIn[i];
                    h[j] = s;
                }
                layerNormSiluInPlace(h, MAPDU, mapUp1w, mapUp1b);
                float upd[MAPDN];
                for (int j = 0; j < MAPDN; ++j) {
                    float s = mapUp3b[j];
                    for (int i = 0; i < MAPDU; ++i) s += mapUp3w[j][i] * h[i];
                    upd[j] = base[y][x][j] + s;
                }
                layerNormInPlace(upd, MAPDN, mapNormW, mapNormB);
                for (int j = 0; j < MAPDN; ++j) graph[y][x][j] = upd[j];
            }
        }
        // Readout: mean+max over the chosen child (roots when py < 0).
        float mean[MAPDN] = {}, maxv[MAPDN] = {};
        int deg = 0;
        const bool root = py < 0;
        const int row = root ? 0 : clampi(py + 1, 0, 14);
        for (int x = 0; x < 7; ++x) {
            if (chosenX >= 0 && x != chosenX) continue;
            const bool sel = root ? (edges[x] > 0)
                                  : (py < 14 && ((edges[clampi(py, 0, 14) * 7 + clampi(px, 0, 6)] >> x) & 1));
            if (!sel) continue;
            ++deg;
            for (int j = 0; j < MAPDN; ++j) {
                const float v = graph[row][x][j];
                mean[j] += v;
                if (deg == 1 || v > maxv[j]) maxv[j] = v;
            }
        }
        if (deg) for (int j = 0; j < MAPDN; ++j) mean[j] /= (float)deg;
        float roIn[2 * MAPDN];
        for (int j = 0; j < MAPDN; ++j) roIn[j] = mean[j];
        for (int j = 0; j < MAPDN; ++j) roIn[MAPDN + j] = maxv[j];
        float h[MAPDR];
        for (int j = 0; j < MAPDR; ++j) {
            float s = mapRo0b[j];
            for (int i = 0; i < 2 * MAPDN; ++i) s += mapRo0w[j][i] * roIn[i];
            h[j] = s;
        }
        layerNormSiluInPlace(h, MAPDR, mapRo1w, mapRo1b);
        for (int j = 0; j < MAPDOUT; ++j) {
            float s = mapRo3b[j];
            for (int i = 0; i < MAPDR; ++i) s += mapRo3w[j][i] * h[i];
            out[j] = silu(s);
        }
    }

    // Q(s,a) for a MAP-screen candidate with the V6 map-DAG route encoder: the
    // adapter output is added to the (z,b,a,screen) concat (zero at init, so
    // the base heads are untouched until the encoder is trained).
    float predictMapActionValue(const float *state, std::uint32_t actionBits,
                                const int cats[6], int actionType, int screen,
                                const int rooms[105], const int edges[105],
                                const int special[105], int px, int py, int chosenX) const {
        float x[NSTATE];
        for (int i = 0; i < NSTATE; ++i)
            x[i] = clampf((state[i] - stateMean[i]) * stateInv[i], -8.0f, 8.0f);

        float sOut[NHIDDEN2];
        encodeState(x, sOut);

        float bits[NBITS];
        for (int i = 0; i < NBITS; ++i) bits[i] = (float)((actionBits >> i) & 1u);
        float bOut[AHIDDEN2];
        {
            float h[AHIDDEN];
            for (int j = 0; j < AHIDDEN; ++j) {
                float s = a0b[j];
                for (int i = 0; i < NBITS; ++i) s += a0w[j][i] * bits[i];
                h[j] = gelu(s);
            }
            for (int j = 0; j < AHIDDEN2; ++j) {
                float s = a3b[j];
                for (int i = 0; i < AHIDDEN; ++i) s += a3w[j][i] * h[i];
                bOut[j] = s;
            }
        }

        float catIn[CATIN];
        int p = 0;
        for (int c = 0; c < NCAT; ++c) {
            int idx = clampi(cats[c] + 1, 0, CATVOCAB - 1);
            for (int i = 0; i < CATDIM; ++i) catIn[p++] = cw[c][idx][i];
        }
        {
            int idx = clampi(actionType + 1, 0, ATYPEVOCAB - 1);
            for (int i = 0; i < ATYPEDIM; ++i) catIn[p++] = atypeW[idx][i];
        }
        float aOut[AHIDDEN2];
        {
            float h[AHIDDEN];
            for (int j = 0; j < AHIDDEN; ++j) {
                float s = cat0b[j];
                for (int i = 0; i < CATIN; ++i) s += cat0w[j][i] * catIn[i];
                h[j] = gelu(s);
            }
            for (int j = 0; j < AHIDDEN2; ++j) {
                float s = cat3b[j];
                for (int i = 0; i < AHIDDEN; ++i) s += cat3w[j][i] * h[i];
                aOut[j] = s;
            }
        }

        float z[POLIN];
        p = 0;
        for (int i = 0; i < NHIDDEN2; ++i) z[p++] = sOut[i];
        for (int i = 0; i < AHIDDEN2; ++i) z[p++] = bOut[i];
        for (int i = 0; i < AHIDDEN2; ++i) z[p++] = aOut[i];
        if (screen >= 0 && screen < NSCR)
            for (int i = 0; i < SCRDIM; ++i) z[p++] = screenW[screen][i];
        else
            for (int i = 0; i < SCRDIM; ++i) z[p++] = 0.0f;

        float mapOut[MAPDOUT];
        encodeMapGraph(rooms, edges, special, px, py, chosenX, mapOut);
        float ad0[POLIN];
        for (int j = 0; j < POLIN; ++j) {
            float s = mapAd0b[j];
            for (int i = 0; i < MAPDOUT; ++i) s += mapAd0w[j][i] * mapOut[i];
            ad0[j] = gelu(s);
        }
        for (int j = 0; j < POLIN; ++j) {
            float s = mapAd2b[j];
            for (int i = 0; i < POLIN; ++i) s += mapAd2w[j][i] * ad0[i];
            z[j] += s;
        }

        float hh[POLHID];
        for (int j = 0; j < POLHID; ++j) {
            float s = q0b[j];
            for (int i = 0; i < POLIN; ++i) s += q0w[j][i] * z[i];
            hh[j] = gelu(s);
        }
        float out = q2b;
        for (int i = 0; i < POLHID; ++i) out += q2w[i] * hh[i];
        return probQ ? 1.0f / (1.0f + std::exp(-out)) : out;
    }

    // Q_HP / Q_floor auxiliary probability heads (V5 only; 0 for V3).
    float predictAuxValue(const float *state, std::uint32_t actionBits,
                          const int cats[6], int actionType, int screen,
                          float &qhp, float &qfloor) const {
        qhp = qfloor = 0.0f;
        if (!probQ) return predictActionValue(state, actionBits, cats, actionType, screen);
        // Normalize state
        float x[NSTATE];
        for (int i = 0; i < NSTATE; ++i)
            x[i] = clampf((state[i] - stateMean[i]) * stateInv[i], -8.0f, 8.0f);

        float sOut[NHIDDEN2];
        encodeState(x, sOut);

        float bits[NBITS];
        for (int i = 0; i < NBITS; ++i) bits[i] = (float)((actionBits >> i) & 1u);
        float bOut[AHIDDEN2];
        {
            float h[AHIDDEN];
            for (int j = 0; j < AHIDDEN; ++j) {
                float s = a0b[j];
                for (int i = 0; i < NBITS; ++i) s += a0w[j][i] * bits[i];
                h[j] = gelu(s);
            }
            for (int j = 0; j < AHIDDEN2; ++j) {
                float s = a3b[j];
                for (int i = 0; i < AHIDDEN; ++i) s += a3w[j][i] * h[i];
                bOut[j] = s;
            }
        }

        float catIn[CATIN];
        int p = 0;
        for (int c = 0; c < NCAT; ++c) {
            int idx = clampi(cats[c] + 1, 0, CATVOCAB - 1);
            for (int i = 0; i < CATDIM; ++i) catIn[p++] = cw[c][idx][i];
        }
        {
            int idx = clampi(actionType + 1, 0, ATYPEVOCAB - 1);
            for (int i = 0; i < ATYPEDIM; ++i) catIn[p++] = atypeW[idx][i];
        }
        float aOut[AHIDDEN2];
        {
            float h[AHIDDEN];
            for (int j = 0; j < AHIDDEN; ++j) {
                float s = cat0b[j];
                for (int i = 0; i < CATIN; ++i) s += cat0w[j][i] * catIn[i];
                h[j] = gelu(s);
            }
            for (int j = 0; j < AHIDDEN2; ++j) {
                float s = cat3b[j];
                for (int i = 0; i < AHIDDEN; ++i) s += cat3w[j][i] * h[i];
                aOut[j] = s;
            }
        }

        float z[POLIN];
        p = 0;
        for (int i = 0; i < NHIDDEN2; ++i) z[p++] = sOut[i];
        for (int i = 0; i < AHIDDEN2; ++i) z[p++] = bOut[i];
        for (int i = 0; i < AHIDDEN2; ++i) z[p++] = aOut[i];
        if (screen >= 0 && screen < NSCR)
            for (int i = 0; i < SCRDIM; ++i) z[p++] = screenW[screen][i];
        else
            for (int i = 0; i < SCRDIM; ++i) z[p++] = 0.0f;

        float hh[POLHID];
        for (int j = 0; j < POLHID; ++j) {
            float s = q0b[j];
            for (int i = 0; i < POLIN; ++i) s += q0w[j][i] * z[i];
            hh[j] = gelu(s);
        }
        float out = q2b;
        for (int i = 0; i < POLHID; ++i) out += q2w[i] * hh[i];
        out = 1.0f / (1.0f + std::exp(-out));
        for (int j = 0; j < POLHID; ++j) {
            float s = qhp0b[j];
            for (int i = 0; i < POLIN; ++i) s += qhp0w[j][i] * z[i];
            hh[j] = gelu(s);
        }
        float hp = qhp2b;
        for (int i = 0; i < POLHID; ++i) hp += qhp2w[i] * hh[i];
        qhp = 1.0f / (1.0f + std::exp(-hp));
        for (int j = 0; j < POLHID; ++j) {
            float s = qfl0b[j];
            for (int i = 0; i < POLIN; ++i) s += qfl0w[j][i] * z[i];
            hh[j] = gelu(s);
        }
        float fl = qfl2b;
        for (int i = 0; i < POLHID; ++i) fl += qfl2w[i] * hh[i];
        qfloor = 1.0f / (1.0f + std::exp(-fl));
        return out;
    }

    static float clampf(float v, float lo, float hi) {
        return v < lo ? lo : (v > hi ? hi : v);
    }
    static int clampi(int v, int lo, int hi) {
        return v < lo ? lo : (v > hi ? hi : v);
    }
    static float gelu(float x) {
        const float a = x * x * x * 0.044715f;
        return 0.5f * x * (1.0f + std::tanh(0.7978845608028654f * (x + a)));
    }
    static float silu(float x) {
        return x / (1.0f + std::exp(-x));
    }
    static void layerNormInPlace(float *h, int n, const float *w, const float *b) {
        float mu = 0; for (int j = 0; j < n; ++j) mu += h[j]; mu /= n;
        float var = 0; for (int j = 0; j < n; ++j) { float d = h[j] - mu; var += d * d; }
        var = var / n + 1e-5f; float invStd = 1.0f / std::sqrt(var);
        for (int j = 0; j < n; ++j) h[j] = (h[j] - mu) * invStd * w[j] + b[j];
    }
    static void layerNormSiluInPlace(float *h, int n, const float *w, const float *b) {
        layerNormInPlace(h, n, w, b);
        for (int j = 0; j < n; ++j) h[j] = silu(h[j]);
    }
};

static OocStrategicNet g_oocStrategicNet;
