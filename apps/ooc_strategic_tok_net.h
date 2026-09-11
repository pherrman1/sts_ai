// Native OOC strategic TOKEN model (V4).  Token-based run state with a single
// deck self-attention layer; loaded from the binary exported by
// export_strategic_tok.py (magic OOC_STRAT_V4).
#pragma once
#include <cstdio>
#include <cstring>
#include <cstdint>
#include <cmath>
#include <string>

struct OocStrategicTokNet {
    static constexpr int NGLB = 42, NHIDDEN = 256, NHIDDEN2 = 128, NBITS = 32;
    static constexpr int DECKDIM = 32, RELDIM = 16, POTDIM = 8;
    static constexpr int MAXDK = 96, MAXRL = 64, MAXPT = 8;
    static constexpr int DKTOKIN = 41, RLTOKIN = 17, PTTOKIN = 9;
    static constexpr int ENTIN = 37, ENTHID = 32, ENTOUT = 16, POLIN = 184;
    static constexpr int NCARD = 372, NREL = 181, NPOT = 48;
    static constexpr int NCAT = 6, CATVOCAB = 512, CATDIM = 4;
    static constexpr int ATYPEVOCAB = 16, ATYPEDIM = 8;
    static constexpr int NSCR = 16, SCRDIM = 8;
    static constexpr int AHIDDEN = 32, AHIDDEN2 = 16;
    static constexpr int POLHID = 96, VALHID = 64;
    static constexpr int QDIM = 3 * DECKDIM;             // 96
    static constexpr int FUSIN = NGLB + DECKDIM + RELDIM + POTDIM;  // 98
    static constexpr int CATIN = NCAT * CATDIM + ATYPEDIM;         // 32

    float globMean[NGLB], globInv[NGLB];

    // embeddings (shared between tokens and the candidate entity)
    float eCard[NCARD][DECKDIM];
    float eUp[2][8];
    float eRel[NREL][RELDIM];
    float ePot[NPOT][POTDIM];

    // deck token encoder + 1-head attention
    float deckTokW[DECKDIM][DKTOKIN], deckTokB[DECKDIM];
    float deckQkvW[QDIM][DECKDIM], deckQkvB[QDIM];
    float deckProjW[DECKDIM][DECKDIM], deckProjB[DECKDIM];
    float deckLnW[DECKDIM], deckLnB[DECKDIM];

    // relic/potion token encoders (mean-pool, no attention)
    float relTokW[RELDIM][RLTOKIN], relTokB[RELDIM];
    float potTokW[POTDIM][PTTOKIN], potTokB[POTDIM];

    // fusion: Linear(106,256) -> LayerNorm -> GELU -> Linear(256,128) -> GELU
    float f0w[NHIDDEN][FUSIN], f0b[NHIDDEN];
    float lnW[NHIDDEN], lnB[NHIDDEN];
    float f4w[NHIDDEN2][NHIDDEN], f4b[NHIDDEN2];

    // action bit encoder: Linear(32,32) -> GELU -> Linear(32,16)  (no final GELU)
    float a0w[AHIDDEN][NBITS], a0b[AHIDDEN];
    float a3w[AHIDDEN2][AHIDDEN], a3b[AHIDDEN2];

    // action category encoder: Linear(32,32) -> GELU -> Linear(32,16)  (no final GELU)
    float cat0w[AHIDDEN][CATIN], cat0b[AHIDDEN];
    float cat3w[AHIDDEN2][AHIDDEN], cat3b[AHIDDEN2];

    // embeddings
    float cw[NCAT][CATVOCAB][CATDIM];
    float atypeW[ATYPEVOCAB][ATYPEDIM];
    float screenW[NSCR][SCRDIM];

    // candidate entity encoder: Linear(37,32) -> GELU -> Linear(32,16)
    float ent0w[ENTHID][ENTIN], ent0b[ENTHID];
    float ent3w[ENTOUT][ENTHID], ent3b[ENTOUT];

    // policy head: Linear(184,96) -> GELU -> Linear(96,1)
    float pol0w[POLHID][POLIN], pol0b[POLHID];
    float pol2w[POLHID], pol2b;

    // one value head per screen (screens 1..8 -> index 0..7):
    // Linear(128,64) -> GELU -> Linear(64,1) on z_state
    float val0w[8][VALHID][NHIDDEN2], val0b[8][VALHID];
    float val2w[8][VALHID], val2b[8];

    // Q head: Linear(184,96) -> GELU -> Linear(96,1) on the same z concat
    float q0w[POLHID][POLIN], q0b[POLHID];
    float q2w[POLHID], q2b;

    bool ok = false;
    std::string path;

    bool load(const std::string &path) {
        FILE *f = std::fopen(path.c_str(), "rb");
        if (!f) { std::fprintf(stderr, "[ooc-strat-tok-net] cannot open %s\n", path.c_str()); return false; }
        auto readBlock = [f](void *dst, size_t count) -> bool {
            return std::fread(dst, 1, count, f) == count;
        };
        char hdr[13] = {};
        if (!readBlock(hdr, 12) || std::memcmp(hdr, "OOC_STRAT_V4", 12) != 0) {
            std::fprintf(stderr, "[ooc-strat-tok-net] truncated payload in %s\n", path.c_str());
            std::fclose(f); return false;
        }
        int dims[17];
        if (!readBlock(dims, sizeof(dims))
            || dims[0] != NGLB || dims[1] != NHIDDEN || dims[2] != NHIDDEN2 || dims[3] != NBITS
            || dims[4] != DECKDIM || dims[5] != RELDIM || dims[6] != POTDIM
            || dims[7] != MAXDK || dims[8] != MAXRL || dims[9] != MAXPT
            || dims[10] != DKTOKIN || dims[11] != RLTOKIN || dims[12] != PTTOKIN
            || dims[13] != ENTIN || dims[14] != ENTHID || dims[15] != ENTOUT
            || dims[16] != POLIN) {
            std::fprintf(stderr, "[ooc-strat-tok-net] truncated payload in %s\n", path.c_str());
            std::fclose(f); return false;
        }
        const bool complete =
               readBlock(globMean, sizeof(globMean))
            && readBlock(globInv, sizeof(globInv))
            && readBlock(eCard, sizeof(eCard))
            && readBlock(eUp, sizeof(eUp))
            && readBlock(deckTokW, sizeof(deckTokW))
            && readBlock(deckTokB, sizeof(deckTokB))
            && readBlock(deckQkvW, sizeof(deckQkvW))
            && readBlock(deckQkvB, sizeof(deckQkvB))
            && readBlock(deckProjW, sizeof(deckProjW))
            && readBlock(deckProjB, sizeof(deckProjB))
            && readBlock(deckLnW, sizeof(deckLnW))
            && readBlock(deckLnB, sizeof(deckLnB))
            && readBlock(eRel, sizeof(eRel))
            && readBlock(relTokW, sizeof(relTokW))
            && readBlock(relTokB, sizeof(relTokB))
            && readBlock(ePot, sizeof(ePot))
            && readBlock(potTokW, sizeof(potTokW))
            && readBlock(potTokB, sizeof(potTokB))
            && readBlock(f0w, sizeof(f0w))
            && readBlock(f0b, sizeof(f0b))
            && readBlock(lnW, sizeof(lnW))
            && readBlock(lnB, sizeof(lnB))
            && readBlock(f4w, sizeof(f4w))
            && readBlock(f4b, sizeof(f4b))
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
            && readBlock(ent0w, sizeof(ent0w))
            && readBlock(ent0b, sizeof(ent0b))
            && readBlock(ent3w, sizeof(ent3w))
            && readBlock(ent3b, sizeof(ent3b))
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
        std::fclose(f);
        if (!complete) {
            std::fprintf(stderr, "[ooc-strat-tok-net] truncated payload in %s\n", path.c_str());
            return false;
        }
        ok = true;
        this->path = path;
        std::printf("[ooc-strat-tok-net] loaded %s\n", path.c_str());
        return true;
    }

    // Deck tokens: GELU(Linear41->32), then 1-head self-attention (D=32) over
    // the valid tokens, LayerNorm(eps=1e-5) residual, mean-pool -> z_deck.
    void encodeDeck(int nDk, const int dk[][3], float *zDeck) const {
        if (nDk > MAXDK) nDk = MAXDK;
        float tok[MAXDK][DECKDIM];
        float tokIn[DKTOKIN];
        for (int i = 0; i < nDk; ++i) {
            const int id = clampi(dk[i][0], 0, NCARD - 1);
            const int up = clampi(dk[i][1], 0, 1);
            const float countF = (dk[i][2] > 9 ? 9 : dk[i][2]) / 9.0f;
            int p = 0;
            for (int d = 0; d < DECKDIM; ++d) tokIn[p++] = eCard[id][d];
            for (int d = 0; d < 8; ++d) tokIn[p++] = eUp[up][d];
            tokIn[p++] = countF;
            for (int j = 0; j < DECKDIM; ++j) {
                float s = deckTokB[j];
                for (int k = 0; k < DKTOKIN; ++k) s += deckTokW[j][k] * tokIn[k];
                tok[i][j] = gelu(s);
            }
        }
        if (nDk <= 0) {
            for (int d = 0; d < DECKDIM; ++d) zDeck[d] = 0.0f;
            return;
        }
        float qkv[MAXDK][QDIM];
        for (int i = 0; i < nDk; ++i)
            for (int j = 0; j < QDIM; ++j) {
                float s = deckQkvB[j];
                for (int d = 0; d < DECKDIM; ++d) s += deckQkvW[j][d] * tok[i][d];
                qkv[i][j] = s;
            }
        const float invSqrt = 1.0f / std::sqrt((float)DECKDIM);
        float scores[MAXDK][MAXDK], attn[MAXDK][DECKDIM];
        for (int i = 0; i < nDk; ++i) {
            float smax = -1e30f;
            for (int j = 0; j < nDk; ++j) {
                float s = 0;
                for (int d = 0; d < DECKDIM; ++d) s += qkv[i][d] * qkv[j][DECKDIM + d];
                scores[i][j] = s * invSqrt;
                if (scores[i][j] > smax) smax = scores[i][j];
            }
            float sum = 0;
            for (int j = 0; j < nDk; ++j) { scores[i][j] = std::exp(scores[i][j] - smax); sum += scores[i][j]; }
            const float inv = 1.0f / sum;
            for (int d = 0; d < DECKDIM; ++d) {
                float s = 0;
                for (int j = 0; j < nDk; ++j) s += scores[i][j] * inv * qkv[j][2 * DECKDIM + d];
                attn[i][d] = s;
            }
        }
        float mid[DECKDIM];
        for (int i = 0; i < nDk; ++i) {
            for (int d = 0; d < DECKDIM; ++d) {
                float s = deckProjB[d];
                for (int e = 0; e < DECKDIM; ++e) s += deckProjW[d][e] * attn[i][e];
                mid[d] = tok[i][d] + s;
            }
            float mu = 0; for (int d = 0; d < DECKDIM; ++d) mu += mid[d]; mu /= DECKDIM;
            float var = 0; for (int d = 0; d < DECKDIM; ++d) { float dd = mid[d] - mu; var += dd * dd; }
            var = var / DECKDIM + 1e-5f;
            const float invStd = 1.0f / std::sqrt(var);
            for (int d = 0; d < DECKDIM; ++d)
                tok[i][d] = (mid[d] - mu) * invStd * deckLnW[d] + deckLnB[d];
        }
        for (int d = 0; d < DECKDIM; ++d) {
            float s = 0;
            for (int i = 0; i < nDk; ++i) s += tok[i][d];
            zDeck[d] = s / nDk;
        }
    }

    // Relic tokens: GELU(Linear17->16), mean-pool -> z_rel.
    void encodeRel(int nRl, const int rl[][2], float *zRel) const {
        if (nRl > MAXRL) nRl = MAXRL;
        float tok[MAXRL][RELDIM];
        float tokIn[RLTOKIN];
        for (int i = 0; i < nRl; ++i) {
            const int id = clampi(rl[i][0], 0, NREL - 1);
            const float dataF = (rl[i][1] - 1 > 9 ? 9 : rl[i][1] - 1) / 9.0f;
            int p = 0;
            for (int d = 0; d < RELDIM; ++d) tokIn[p++] = eRel[id][d];
            tokIn[p++] = dataF;
            for (int j = 0; j < RELDIM; ++j) {
                float s = relTokB[j];
                for (int k = 0; k < RLTOKIN; ++k) s += relTokW[j][k] * tokIn[k];
                tok[i][j] = gelu(s);
            }
        }
        if (nRl <= 0) {
            for (int d = 0; d < RELDIM; ++d) zRel[d] = 0.0f;
            return;
        }
        for (int d = 0; d < RELDIM; ++d) {
            float s = 0;
            for (int i = 0; i < nRl; ++i) s += tok[i][d];
            zRel[d] = s / nRl;
        }
    }

    // Potion tokens: GELU(Linear9->8), mean-pool -> z_pot.
    void encodePot(int nPt, const int pt[][2], float *zPot) const {
        if (nPt > MAXPT) nPt = MAXPT;
        float tok[MAXPT][POTDIM];
        float tokIn[PTTOKIN];
        for (int i = 0; i < nPt; ++i) {
            const int id = clampi(pt[i][0], 0, NPOT - 1);
            const float countF = (pt[i][1] > 9 ? 9 : pt[i][1]) / 9.0f;
            int p = 0;
            for (int d = 0; d < POTDIM; ++d) tokIn[p++] = ePot[id][d];
            tokIn[p++] = countF;
            for (int j = 0; j < POTDIM; ++j) {
                float s = potTokB[j];
                for (int k = 0; k < PTTOKIN; ++k) s += potTokW[j][k] * tokIn[k];
                tok[i][j] = gelu(s);
            }
        }
        if (nPt <= 0) {
            for (int d = 0; d < POTDIM; ++d) zPot[d] = 0.0f;
            return;
        }
        for (int d = 0; d < POTDIM; ++d) {
            float s = 0;
            for (int i = 0; i < nPt; ++i) s += tok[i][d];
            zPot[d] = s / nPt;
        }
    }

    // Fusion encoder: globals normalized clamp((x-mean)*inv,-8,8), then
    // Linear(106,256) -> LayerNorm(eps=1e-5) -> GELU -> Linear(256,128) -> GELU.
    void encodeState(const float *glob, const float *zDeck, const float *zRel,
                     const float *zPot, float *zState) const {
        float x[NGLB];
        for (int i = 0; i < NGLB; ++i)
            x[i] = clampf((glob[i] - globMean[i]) * globInv[i], -8.0f, 8.0f);
        float fuse[FUSIN];
        int p = 0;
        for (int i = 0; i < NGLB; ++i) fuse[p++] = x[i];
        for (int i = 0; i < DECKDIM; ++i) fuse[p++] = zDeck[i];
        for (int i = 0; i < RELDIM; ++i) fuse[p++] = zRel[i];
        for (int i = 0; i < POTDIM; ++i) fuse[p++] = zPot[i];
        float h[NHIDDEN];
        for (int j = 0; j < NHIDDEN; ++j) {
            float s = f0b[j];
            for (int i = 0; i < FUSIN; ++i) s += f0w[j][i] * fuse[i];
            h[j] = s;
        }
        float mu = 0; for (int j = 0; j < NHIDDEN; ++j) mu += h[j]; mu /= NHIDDEN;
        float var = 0; for (int j = 0; j < NHIDDEN; ++j) { float dd = h[j] - mu; var += dd * dd; }
        var = var / NHIDDEN + 1e-5f;
        const float invStd = 1.0f / std::sqrt(var);
        for (int j = 0; j < NHIDDEN; ++j) h[j] = (h[j] - mu) * invStd * lnW[j] + lnB[j];
        for (int j = 0; j < NHIDDEN; ++j) h[j] = gelu(h[j]);
        for (int j = 0; j < NHIDDEN2; ++j) {
            float s = f4b[j];
            for (int i = 0; i < NHIDDEN; ++i) s += f4w[j][i] * h[i];
            zState[j] = gelu(s);
        }
    }

    // Action bit + category + screen encoders (as in V3).
    void encodeAction(std::uint32_t actionBits, const int cats[6], int actionType,
                      int screen, float *bOut, float *aOut, float *sOut) const {
        float bits[NBITS];
        for (int i = 0; i < NBITS; ++i) bits[i] = (float)((actionBits >> i) & 1u);
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
        if (screen >= 0 && screen < NSCR)
            for (int i = 0; i < SCRDIM; ++i) sOut[i] = screenW[screen][i];
        else
            for (int i = 0; i < SCRDIM; ++i) sOut[i] = 0.0f;
    }

    // Candidate entity: concat(entityVec(32), entityType(4), goldGePrice(1))
    // -> Linear(37,32) -> GELU -> Linear(32,16).
    void encodeEntity(int entType, int entId, const float *entityType,
                      float goldGePrice, float *eOut) const {
        float vec[DECKDIM];
        if (entType == 1) {
            const int id = clampi(entId, 0, NCARD - 1);
            for (int d = 0; d < DECKDIM; ++d) vec[d] = eCard[id][d];
        } else if (entType == 2) {
            const int id = clampi(entId, 0, NREL - 1);
            for (int d = 0; d < RELDIM; ++d) vec[d] = eRel[id][d];
            for (int d = RELDIM; d < DECKDIM; ++d) vec[d] = 0.0f;
        } else if (entType == 3) {
            const int id = clampi(entId, 0, NPOT - 1);
            for (int d = 0; d < POTDIM; ++d) vec[d] = ePot[id][d];
            for (int d = POTDIM; d < DECKDIM; ++d) vec[d] = 0.0f;
        } else {
            for (int d = 0; d < DECKDIM; ++d) vec[d] = 0.0f;
        }
        float entIn[ENTIN];
        int p = 0;
        for (int d = 0; d < DECKDIM; ++d) entIn[p++] = vec[d];
        for (int d = 0; d < 4; ++d) entIn[p++] = entityType[d];
        entIn[p++] = goldGePrice;
        float h[ENTHID];
        for (int j = 0; j < ENTHID; ++j) {
            float s = ent0b[j];
            for (int i = 0; i < ENTIN; ++i) s += ent0w[j][i] * entIn[i];
            h[j] = gelu(s);
        }
        for (int j = 0; j < ENTOUT; ++j) {
            float s = ent3b[j];
            for (int i = 0; i < ENTHID; ++i) s += ent3w[j][i] * h[i];
            eOut[j] = s;
        }
    }

    // Per-screen value head on z_state (token groups empty: z_deck/z_rel/z_pot = 0).
    float predictValue(const float glob[NGLB], int screen) const {
        const float zDeck[DECKDIM] = {}, zRel[RELDIM] = {}, zPot[POTDIM] = {};
        float sOut[NHIDDEN2];
        encodeState(glob, zDeck, zRel, zPot, sOut);
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

    // Q logit on z = concat(z_state(128), b(16), a(16), s8(8), e(16)) = 184.
    float predictActionValue(const float glob[NGLB], int nDk, const int dk[96][3],
                             int nRl, const int rl[64][2], int nPt, const int pt[8][2],
                             std::uint32_t actionBits, const int cats[6], int actionType,
                             int screen, const float entityType[4], int entityId,
                             float goldGePrice) const {
        float zDeck[DECKDIM], zRel[RELDIM], zPot[POTDIM];
        encodeDeck(nDk, dk, zDeck);
        encodeRel(nRl, rl, zRel);
        encodePot(nPt, pt, zPot);

        float zState[NHIDDEN2];
        encodeState(glob, zDeck, zRel, zPot, zState);

        float bOut[AHIDDEN2], aOut[AHIDDEN2], sOut[SCRDIM];
        encodeAction(actionBits, cats, actionType, screen, bOut, aOut, sOut);

        float eOut[ENTOUT];
        encodeEntity(entityType[1] ? 1 : (entityType[2] ? 2 : (entityType[3] ? 3 : 0)),
                     entityId, entityType, goldGePrice, eOut);

        float z[POLIN];
        int p = 0;
        for (int i = 0; i < NHIDDEN2; ++i) z[p++] = zState[i];
        for (int i = 0; i < AHIDDEN2; ++i) z[p++] = bOut[i];
        for (int i = 0; i < AHIDDEN2; ++i) z[p++] = aOut[i];
        for (int i = 0; i < SCRDIM; ++i) z[p++] = sOut[i];
        for (int i = 0; i < ENTOUT; ++i) z[p++] = eOut[i];

        // Q head: Linear(184,96) -> GELU -> Linear(96,1)
        float hh[POLHID];
        for (int j = 0; j < POLHID; ++j) {
            float s = q0b[j];
            for (int i = 0; i < POLIN; ++i) s += q0w[j][i] * z[i];
            hh[j] = gelu(s);
        }
        float out = q2b;
        for (int i = 0; i < POLHID; ++i) out += q2w[i] * hh[i];
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
};

extern OocStrategicTokNet g_oocStrategicTokNet;
