// Native-style timing of generalized factorized policy MLPs (mirrors CombatValueNet::predictPolicyMlp loops).
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <string>
#include <vector>
#include <algorithm>
static const int S = 1766, A = 22, NCARD = 372, NT = 9, MON_OFF = 1766 - 8 - 5 - 44 - 5 * 9;
struct Net {
  int h1, h2, h3, tower, dot, enc;
  std::vector<float> encT, Wst, bt, Wtp, Wa, card, Wt, b1, W2T, b2, W3T, b3, wout, du, bdu, dvT;
  float bout;
};
static std::vector<float> rd(FILE *f, size_t n) { std::vector<float> v(n); if (fread(v.data(), 4, n, f) != n) { fprintf(stderr, "short\n"); exit(1);} return v; }
Net load(const char *p) {
  FILE *f = fopen(p, "rb"); Net n; int hd[6]; fread(hd, 4, 6, f);
  n.h1 = hd[0]; n.h2 = hd[1]; n.h3 = hd[2]; n.tower = hd[3]; n.dot = hd[4]; n.enc = hd[5];
  int T = n.tower ? n.tower : n.h1;
  n.Wst = rd(f, (size_t)S * T);
  if (n.tower) { n.bt = rd(f, T); n.Wtp = rd(f, (size_t)T * n.h1); }
  n.Wa = rd(f, (size_t)A * n.h1); n.card = rd(f, (size_t)NCARD * n.h1); n.Wt = rd(f, (size_t)NT * n.h1);
  n.b1 = rd(f, n.h1); n.W2T = rd(f, (size_t)n.h1 * n.h2); n.b2 = rd(f, n.h2);
  int last = n.h2;
  if (n.h3) { n.W3T = rd(f, (size_t)n.h2 * n.h3); n.b3 = rd(f, n.h3); last = n.h3; }
  n.wout = rd(f, last); n.bout = rd(f, 1)[0];
  if (n.dot) { n.du = rd(f, (size_t)n.h1 * n.dot); n.bdu = rd(f, n.dot); n.dvT = rd(f, (size_t)n.h1 * n.dot); }
  if (n.enc) n.encT = rd(f, (size_t)128 * (n.tower ? n.tower : n.h1));
  fclose(f); return n;
}
void predict(const Net &N, const float *st, const float *acts, const int *tg, int n, double *out) {
  const int H1 = N.h1, H2 = N.h2, H3 = N.h3, T = N.tower, D = N.dot;
  thread_local std::vector<float> hs, base, h, z, z3, t, u, ea;
  hs.assign(H1, 0.f);
  int encId = 0;
  if (N.enc) { encId = (int)(st[1] + 0.5f); if (encId < 0) encId = 0; if (encId > 127) encId = 127; }
  if (T) {
    t.assign(N.bt.begin(), N.bt.end());
    if (N.enc) { const float *w = &N.encT[(size_t)encId * T]; for (int j = 0; j < T; ++j) t[j] += w[j]; }
    for (int i = 0; i < S; ++i) { const float v = st[i]; if (v == 0.f) continue; const float *w = &N.Wst[(size_t)i * T]; for (int j = 0; j < T; ++j) t[j] += v * w[j]; }
    for (int k = 0; k < T; ++k) { const float v = t[k]; if (v <= 0.f) continue; const float *w = &N.Wtp[(size_t)k * H1]; for (int j = 0; j < H1; ++j) hs[j] += v * w[j]; }
  } else {
    if (N.enc) { const float *w = &N.encT[(size_t)encId * H1]; for (int j = 0; j < H1; ++j) hs[j] += w[j]; }
    for (int i = 0; i < S; ++i) { const float v = st[i]; if (v == 0.f) continue; const float *w = &N.Wst[(size_t)i * H1]; for (int j = 0; j < H1; ++j) hs[j] += v * w[j]; }
  }
  base.resize(H1); for (int j = 0; j < H1; ++j) base[j] = hs[j] + N.b1[j];
  if (D) { u.assign(N.bdu.begin(), N.bdu.end()); for (int j = 0; j < H1; ++j) { const float v = hs[j]; const float *w = &N.du[(size_t)j * D]; for (int d = 0; d < D; ++d) u[d] += v * w[d]; } ea.resize(H1); }
  h.resize(H1); z.resize(H2); z3.resize(H3 ? H3 : 1);
  for (int e = 0; e < n; ++e) {
    const float *a = acts + (size_t)e * A;
    for (int j = 0; j < H1; ++j) h[j] = base[j];
    for (int k = 0; k < A; ++k) { const float v = a[k]; if (v == 0.f) continue; const float *w = &N.Wa[(size_t)k * H1]; for (int j = 0; j < H1; ++j) h[j] += v * w[j]; }
    int c = (int)a[4] + 1; if (c < 0 || c >= NCARD) c = 0;
    const float *cw = &N.card[(size_t)c * H1]; for (int j = 0; j < H1; ++j) h[j] += cw[j];
    const int slot = tg[e];
    if (slot >= 0 && slot < 5) { const float *tv = st + MON_OFF + slot * NT; for (int k = 0; k < NT; ++k) { const float v = tv[k]; if (v == 0.f) continue; const float *w = &N.Wt[(size_t)k * H1]; for (int j = 0; j < H1; ++j) h[j] += v * w[j]; } }
    double extra = 0;
    if (D) { for (int j = 0; j < H1; ++j) ea[j] = h[j] - base[j] + N.b1[j]; float acc = 0; for (int d = 0; d < D; ++d) { float s = 0; for (int j = 0; j < H1; ++j) s += ea[j] * N.dvT[(size_t)j * D + d]; acc += s * u[d]; } extra = acc; }
    for (int i = 0; i < H2; ++i) z[i] = N.b2[i];
    for (int j = 0; j < H1; ++j) { const float v = h[j]; if (v <= 0.f) continue; const float *w = &N.W2T[(size_t)j * H2]; for (int i = 0; i < H2; ++i) z[i] += v * w[i]; }
    float o = N.bout;
    if (H3) {
      for (int i = 0; i < H3; ++i) z3[i] = N.b3[i];
      for (int j = 0; j < H2; ++j) { const float v = z[j]; if (v <= 0.f) continue; const float *w = &N.W3T[(size_t)j * H3]; for (int i = 0; i < H3; ++i) z3[i] += v * w[i]; }
      for (int i = 0; i < H3; ++i) if (z3[i] > 0.f) o += N.wout[i] * z3[i];
    } else {
      for (int i = 0; i < H2; ++i) if (z[i] > 0.f) o += N.wout[i] * z[i];
    }
    out[e] = o + extra;
  }
}
int main(int argc, char **argv) {
  // roots.bin: int nroots; per root: int n; float state[S]; float act[n*A]; int tgt[n]
  FILE *f = fopen(argv[2], "rb"); int R; fread(&R, 4, 1, f);
  struct Root { std::vector<float> s, a; std::vector<int> t; };
  std::vector<Root> roots(R);
  for (auto &r : roots) { int n; fread(&n, 4, 1, f); r.s.resize(S); fread(r.s.data(), 4, S, f); r.a.resize((size_t)n * A); fread(r.a.data(), 4, (size_t)n * A, f); r.t.resize(n); fread(r.t.data(), 4, n, f); }
  fclose(f);
  Net N = load(argv[1]);
  std::vector<double> out; double best = 1e300, sink = 0;
  FILE *dump = argc > 3 ? fopen(argv[3], "w") : nullptr;
  for (int rep = 0; rep < 5; ++rep) {
    auto t0 = std::chrono::steady_clock::now();
    for (auto &r : roots) { int n = r.t.size(); out.resize(n); predict(N, r.s.data(), r.a.data(), r.t.data(), n, out.data()); sink += out[0];
      if (rep == 0 && dump) for (double x : out) fprintf(dump, "%.9g\n", x); }
    double us = std::chrono::duration<double, std::micro>(std::chrono::steady_clock::now() - t0).count() / R;
    best = std::min(best, us);
  }
  if (dump) fclose(dump);
  printf("{\"roots\":%d,\"usPerRoot\":%.3f,\"sink\":%g}\n", R, best, sink);
}
