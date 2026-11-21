package stsmodelinspector;

import com.google.gson.*;
import java.util.*;

/** Immutable display data from one identity-matched response; never controls the game. */
final class OocOverlay {
    static final class Distribution {
        private final long[] bins;
        final long count, deaths, victories;
        final Double mean;
        final double sumSquares;   // NaN when the producer did not report it
        Distribution(JsonObject value) {
            if (!"ooc_value_distribution_v1".equals(text(value, "schema"))
                    || !"share_of_own_samples".equals(text(value, "normalization")))
                throw new IllegalArgumentException("unknown value distribution semantics");
            JsonArray input = value.getAsJsonArray("bins");
            if (input.size() != 22) throw new IllegalArgumentException("wrong distribution buckets");
            bins = new long[22]; long sum = 0;
            for (int i = 0; i < bins.length; ++i) {
                bins[i] = input.get(i).getAsLong();
                if (bins[i] < 0 || input.get(i).getAsDouble() != bins[i])
                    throw new IllegalArgumentException("invalid distribution count");
                sum = Math.addExact(sum, bins[i]);
            }
            count = value.get("count").getAsLong();
            deaths = value.get("terminalDeaths").getAsLong();
            victories = value.get("terminalVictories").getAsLong();
            mean = value.get("mean").isJsonNull() ? null : value.get("mean").getAsDouble();
            sumSquares = value.has("sumSquares") ? value.get("sumSquares").getAsDouble() : Double.NaN;
            if (value.get("count").getAsDouble() != count
                    || value.get("terminalDeaths").getAsDouble() != deaths
                    || value.get("terminalVictories").getAsDouble() != victories
                    || sum != count || deaths != bins[0] || victories != bins[21]
                    || (count == 0 ? mean != null : mean == null || !Double.isFinite(mean) || mean < 0 || mean > 1))
                throw new IllegalArgumentException("inconsistent value distribution");
        }
        long bin(int index) { return bins[index]; }
        /** Standard error of the mean from the sample variance; NaN without two samples or sumSquares. */
        double standardError() {
            if (count < 2 || mean == null || !Double.isFinite(sumSquares)) return Double.NaN;
            double variance = Math.max(0, (sumSquares - count * mean * mean) / (count - 1));
            return Math.sqrt(variance / count);
        }
        double share(int index) { return count == 0 ? 0 : (double)bins[index] / count; }
        String summary(String label) {
            return count == 0 ? label + ": no search samples"
                    : String.format(Locale.ROOT, "%s · n %d · mean %.3f · sampled death %.1f%%",
                                    label, count, mean, 100.0 * deaths / count);
        }
    }
    static final class Choice {
        final String key, label, kind;
        final double q;
        final String valueSemantics;
        final Distribution distribution;
        final long visits;
        final double visitShare, prior;
        final int index;
        final boolean selected;
        final JsonObject action;
        final JsonObject followUp;
        final String followUpUuid;
        final CombatHpOverlay.Layer hp;   // endpoint HP samples, or null
        // amber_explain_v1 only (NaN / empty otherwise): the search-backed P(win) and expected HP at the end of
        // the current and of the next floor, and the explanation lines of this option.
        final double pWin, hpFloorEnd, hpNextFloor;
        final List<String> why;
        Choice(String key, String label, String kind, double q, long visits, double visitShare, double prior,
               int index, boolean selected, JsonObject action,
               JsonObject followUp, String followUpUuid, String valueSemantics, Distribution distribution,
               CombatHpOverlay.Layer hp) {
            this(key, label, kind, q, visits, visitShare, prior, index, selected, action, followUp, followUpUuid,
                 valueSemantics, distribution, hp, Double.NaN, Double.NaN, Double.NaN, Collections.<String>emptyList());
        }
        Choice(String key, String label, String kind, double q, long visits, double visitShare, double prior,
               int index, boolean selected, JsonObject action,
               JsonObject followUp, String followUpUuid, String valueSemantics, Distribution distribution,
               CombatHpOverlay.Layer hp, double pWin, double hpFloorEnd, double hpNextFloor, List<String> why) {
            this.key = key; this.label = label; this.kind = kind;
            this.q = q; this.visits = visits; this.visitShare = visitShare; this.prior = prior;
            this.index = index; this.selected = selected; this.action = action;
            this.followUp = followUp; this.followUpUuid = followUpUuid;
            this.valueSemantics = valueSemantics; this.distribution = distribution; this.hp = hp;
            this.pWin = pWin; this.hpFloorEnd = hpFloorEnd; this.hpNextFloor = hpNextFloor;
            this.why = Collections.unmodifiableList(new ArrayList<>(why));
        }
        String scoreLabel(int rank) {
            if ("forced_no_search".equals(valueSemantics)) return "#" + rank + " · Forced";
            if (AMBER_SEMANTICS.equals(valueSemantics))
                return visits == 0 || Double.isNaN(pWin)
                    ? String.format(Locale.ROOT, "#%d · prior %.0f%% · not searched", rank, 100 * prior)
                    : String.format(Locale.ROOT, "#%d · P(win) %.1f%% · N %d", rank, 100 * pWin, visits);
            if ("mean_backed_up_value_0_1".equals(valueSemantics))
                return visits == 0 ? "#" + rank + " · No samples"
                    : String.format(Locale.ROOT, "#%d · Mean %.3f · N %d", rank, q, visits);
            return String.format(Locale.ROOT, "#%d · V4 score %.3f", rank, q);
        }
    }
    static final String AMBER_EVALUATOR = "amber_explain_v1", AMBER_POLICY = "amber_search",
            AMBER_SEMANTICS = "amber_search_v1";
    /** Use the Amber evaluator when a response has one (config oocSource=legacy turns it off). */
    static volatile boolean preferAmber = true;
    final String session, hash, status, reason, policy, screen;
    final long sequence;
    // amber_explain_v1 only: the root line and the pick-vs-runner-up explanation lines (empty otherwise).
    String amberRoot = "";
    List<String> amberPair = Collections.emptyList();
    final List<Choice> choices;
    final Distribution distribution;
    // Player HP where each simulation was evaluated; null when not reported.
    CombatHpOverlay.Layer hpRoot;
    HpAxis hpAxis;
    String hpHorizon = "";
    private OocOverlay(JsonObject response, String status, String reason, String policy,
                       String screen, List<Choice> choices, Distribution distribution) {
        session = text(response, "session"); hash = text(response, "observationHash");
        sequence = response.get("sequence").getAsLong();
        this.status = status; this.reason = reason; this.policy = policy; this.screen = screen;
        this.choices = Collections.unmodifiableList(choices);
        this.distribution = distribution;
    }
    boolean matches(String session, long sequence, String hash) {
        return this.session.equals(session) && this.sequence == sequence && this.hash.equals(hash);
    }
    Choice forAction(JsonObject action) {
        Choice first = null;
        for (Choice choice : choices) if (choice.action.equals(action)) {
            if (choice.selected) return choice;
            if (first == null) first = choice;
        }
        return first;
    }
    List<Choice> panelChoices() {
        if (!"card_reward".equals(screen) || choices.size() <= 2)
            return choices.subList(0, Math.min(6, choices.size()));
        // Card scores also appear below each physical card. Keep this panel
        // above the reward cards, including four-card Question Card layouts.
        Choice first = choices.get(0), second = choices.get(1);
        for (Choice choice : choices)
            if ("skip".equals(choice.kind) && choice != first) second = choice;
        return Arrays.asList(first, second);
    }
    static OocOverlay parse(String responseJson, String observationJson) {
        JsonObject response = new JsonParser().parse(responseJson).getAsJsonObject();
        JsonObject ooc = new JsonParser().parse(observationJson).getAsJsonObject().getAsJsonObject("ooc");
        String screen = text(ooc, "screen");
        JsonObject evaluator = null, amber = null;
        if (response.has("evaluators")) for (JsonElement e : response.getAsJsonArray("evaluators")) {
            JsonObject candidate = e.getAsJsonObject();
            if ("live_ooc_decision_v1".equals(text(candidate, "id"))) {
                if (evaluator != null) throw new IllegalArgumentException("duplicate OOC evaluator");
                evaluator = candidate;
            }
            if (AMBER_EVALUATOR.equals(text(candidate, "id"))) {
                if (amber != null) throw new IllegalArgumentException("duplicate Amber evaluator");
                amber = candidate;
            }
        }
        if (amber != null && preferAmber && !"ERROR".equals(text(response, "status"))
                && (evaluator == null || "OK".equals(text(amber, "status")) || "FORCED".equals(text(amber, "status"))))
            return parseAmber(response, amber, ooc, screen);
        if ("ERROR".equals(text(response, "status")) || evaluator == null)
            return new OocOverlay(response, "ERROR", text(response, "message"), "", screen, new ArrayList<Choice>(), null);
        String status = text(evaluator, "status"), policy = text(evaluator, "policy");
        String semantics = text(evaluator, "valueSemantics");
        boolean forced = "forced_no_search".equals(semantics);
        boolean mcts = "mcts_ctm".equals(policy) && !forced;
        // Legacy V4 responses are still a raw score; MCTS distributions require
        // the explicit producer contract, so unknown scores cannot look like risk.
        if (semantics.isEmpty() && "v4_q".equals(policy)) semantics = "raw_v4_action_score";
        Distribution baseline = evaluator.has("valueDistribution")
                ? new Distribution(evaluator.getAsJsonObject("valueDistribution")) : null;
        if ("OK".equals(status) && ((mcts && (!"mean_backed_up_value_0_1".equals(semantics) || baseline == null))
                || (!mcts && !forced && !"raw_v4_action_score".equals(semantics))))
            throw new IllegalArgumentException("unknown OOC value semantics");
        List<Choice> choices = new ArrayList<>();
        JsonObject hpDistribution = "OK".equals(status) && evaluator.has("endpointHpDistribution")
                ? evaluator.getAsJsonObject("endpointHpDistribution") : null;
        int hpBins = 0;
        if (hpDistribution != null) {
            if (!"ooc_endpoint_hp_distribution_v1".equals(text(hpDistribution, "schema")))
                throw new IllegalArgumentException("unknown endpoint HP semantics");
            hpBins = hpDistribution.get("axisMaxHp").getAsInt() + 1;
            if (hpBins < 2) throw new IllegalArgumentException("invalid endpoint HP axis");
        }
        if ("OK".equals(status)) {
            String selected = text(evaluator, "selectedSemanticKey");
            Set<String> keys = new HashSet<>();
            int selectedCount = 0;
            long totalVisits = 0;
            double totalShare = 0.0;
            long selectedVisits = -1;
            long maximumVisits = 0;
            long[] combinedBins = new long[22];
            double backedUpSum = 0;
            for (JsonElement e : evaluator.getAsJsonArray("candidateSummaries")) {
                JsonObject c = e.getAsJsonObject(), action = c.getAsJsonObject("liveAction");
                String key = text(c, "semanticKey"), kind = text(action, "kind");
                double q = c.get("q").getAsDouble();
                boolean hasMctsStats = c.has("visits") && c.has("visitShare") && c.has("prior");
                long visits = hasMctsStats ? c.get("visits").getAsLong() : 0;
                double visitShare = hasMctsStats ? c.get("visitShare").getAsDouble() : 0.0;
                double prior = hasMctsStats ? c.get("prior").getAsDouble() : 0.0;
                if (("mcts_ctm".equals(policy) && !hasMctsStats) || !Double.isFinite(q) || visits < 0 || !Double.isFinite(visitShare)
                        || visitShare < 0 || visitShare > 1.0 || !Double.isFinite(prior) || prior < 0
                        || key.isEmpty() || !keys.add(key))
                    throw new IllegalArgumentException("invalid OOC ranking");
                totalVisits += visits;
                totalShare += visitShare;
                maximumVisits = Math.max(maximumVisits, visits);
                boolean best = key.equals(selected);
                if (best) {
                    ++selectedCount;
                    selectedVisits = visits;
                    if (!action.equals(evaluator.get("selectedLiveAction")))
                        throw new IllegalArgumentException("selected OOC action mismatch");
                }
                int index = action.has("choiceIndex") ? action.get("choiceIndex").getAsInt() : -1;
                JsonObject preview = c.has("followUpPreview") ? c.getAsJsonObject("followUpPreview") : null;
                String previewUuid = "";
                if (preview != null && "OK".equals(text(preview, "status"))) {
                    if (!"v4_q".equals(text(preview, "policy")) || !"selector_preview".equals(text(preview, "scope"))
                            || !"upgrade".equals(text(preview, "selectorType")) || !Double.isFinite(preview.get("q").getAsDouble()))
                        throw new IllegalArgumentException("invalid next-choice preview");
                    JsonObject target = preview.getAsJsonObject("card");
                    JsonObject card = ooc.getAsJsonObject("publicState").getAsJsonArray("deck")
                            .get(target.get("deckIndex").getAsInt()).getAsJsonObject();
                    for (String field : new String[]{"id", "upgraded", "misc"})
                        if (!Objects.equals(target.get(field), card.get(field)))
                            throw new IllegalArgumentException("preview physical card mismatch");
                    previewUuid = text(card, "uuid");
                    if (previewUuid.isEmpty()) throw new IllegalArgumentException("preview physical card missing");
                }
                CombatHpOverlay.Layer hp = hpBins > 0 && c.has("endpointHp")
                        ? new CombatHpOverlay.Layer(c.getAsJsonObject("endpointHp"), hpBins) : null;
                if (hpBins > 0 && hp == null) throw new IllegalArgumentException("missing candidate HP samples");
                Distribution distribution = c.has("valueDistribution")
                        ? new Distribution(c.getAsJsonObject("valueDistribution")) : null;
                if (mcts) {
                    if (q < 0 || q > 1 || distribution == null || distribution.count != visits
                            || (visits > 0 && Math.abs(distribution.mean - q) > 1e-9))
                        throw new IllegalArgumentException("candidate mean/distribution mismatch");
                    for (int bin = 0; bin < 22; ++bin) combinedBins[bin] += distribution.bin(bin);
                    backedUpSum += q * visits;
                }
                choices.add(new Choice(key, label(action, ooc), kind, q, visits, visitShare, prior,
                        index, best, action, preview, previewUuid, semantics, distribution, hp));
            }
            if (selectedCount != 1) throw new IllegalArgumentException("missing selected OOC choice");
            if (mcts) {
                if (Math.abs(totalShare - 1.0) > 1e-6 || selectedVisits != maximumVisits
                        || baseline.count != totalVisits
                        || (totalVisits == 0 && choices.size() != 1)
                        || (totalVisits > 0 && Math.abs(baseline.mean - backedUpSum / totalVisits) > 1e-9))
                    throw new IllegalArgumentException("invalid OOC visit distribution");
                for (int bin = 0; bin < 22; ++bin) if (combinedBins[bin] != baseline.bin(bin))
                    throw new IllegalArgumentException("root/candidate distribution mismatch");
                for (Choice choice : choices) if (totalVisits > 0
                        && Math.abs(choice.visitShare - (double)choice.visits / totalVisits) > 1e-6)
                    throw new IllegalArgumentException("candidate visit share mismatch");
            }
            choices.sort(Comparator.comparingLong((Choice c) -> -c.visits).thenComparing(c -> c.key));
        }
        OocOverlay view = new OocOverlay(response, status, text(evaluator, "reason"), policy, screen, choices, baseline);
        if (hpDistribution != null) attachHp(view, hpDistribution, hpBins);
        return view;
    }
    /**
     * The Amber net's search and explanation (tools/az_bench/amber_advisor.py). Candidates without a live action
     * (search actions the captured screen cannot express) are left out; exactly one remaining one is selected.
     */
    static OocOverlay parseAmber(JsonObject response, JsonObject evaluator, JsonObject ooc, String screen) {
        String status = text(evaluator, "status");
        List<Choice> choices = new ArrayList<>();
        if ("FORCED".equals(status)) {
            JsonElement only = evaluator.get("selectedLiveAction");
            if (only != null && only.isJsonObject()) {
                JsonObject action = only.getAsJsonObject();
                choices.add(new Choice("forced", label(action, ooc), text(action, "kind"), 0, 0, 0, 0,
                        action.has("choiceIndex") ? action.get("choiceIndex").getAsInt() : -1, true, action,
                        null, "", "forced_no_search", null, null));
            }
            OocOverlay view = new OocOverlay(response, choices.isEmpty() ? "UNSUPPORTED" : "OK",
                    text(evaluator, "reason"), AMBER_POLICY, screen, choices, null);
            view.amberRoot = "Forced: one legal choice";
            return view;
        }
        if (!"OK".equals(status))
            return new OocOverlay(response, "UNSUPPORTED", text(evaluator, "reason"), AMBER_POLICY, screen, choices, null);
        int selectedCount = 0, rank = 0;
        Set<String> keys = new HashSet<>();
        for (JsonElement e : evaluator.getAsJsonArray("candidates")) {
            JsonObject c = e.getAsJsonObject();
            ++rank;
            if (!c.has("liveAction") || !c.get("liveAction").isJsonObject()) continue;
            JsonObject action = c.getAsJsonObject("liveAction");
            String key = action.toString();
            if (!keys.add(key)) continue;   // two search actions on one live control: the first (better) one
            boolean selected = c.get("selected").getAsBoolean();
            if (selected) ++selectedCount;
            double prior = number(c, "prior"), share = number(c, "visitShare");
            long visits = c.get("visits").getAsLong();
            if (visits < 0 || !(prior >= 0 && prior <= 1.0 + 1e-9) || !(share >= 0 && share <= 1.0 + 1e-9))
                throw new IllegalArgumentException("invalid Amber candidate");
            String lbl = label(action, ooc);
            if (lbl.startsWith("Choice ") && !text(c, "label").isEmpty()) lbl = text(c, "label");
            choices.add(new Choice(key, lbl, text(action, "kind"), number(c, "q"), visits, share, prior,
                    action.has("choiceIndex") ? action.get("choiceIndex").getAsInt() : -1, selected, action,
                    null, "", AMBER_SEMANTICS, null, null, number(c, "pWin"), number(c, "hpFloorEnd"),
                    number(c, "hpNextFloor"), whyLines(c)));
        }
        if (selectedCount != 1) throw new IllegalArgumentException("Amber pick has no live action");
        OocOverlay view = new OocOverlay(response, "OK", "", AMBER_POLICY, screen, choices, null);
        JsonObject root = evaluator.getAsJsonObject("root");
        view.amberRoot = String.format(Locale.ROOT, "Net P(win) %.1f%% · search %.1f%% · %d sims",
                100 * number(root, "netPWin"), 100 * number(root, "searchPWin"), root.get("visits").getAsLong());
        view.amberPair = pairLines(evaluator.has("pair") && evaluator.get("pair").isJsonObject()
                ? evaluator.getAsJsonObject("pair") : null);
        return view;
    }
    private static double number(JsonObject o, String field) {
        JsonElement e = o == null ? null : o.get(field);
        return e == null || e.isJsonNull() ? Double.NaN : e.getAsDouble();
    }
    private static String items(JsonArray list, boolean z) {
        StringBuilder b = new StringBuilder();
        if (list != null) for (JsonElement e : list) {
            JsonObject x = e.getAsJsonObject();
            if (b.length() > 0) b.append(", ");
            b.append(text(x, "item")).append(String.format(Locale.ROOT, " %+.2f", number(x, z ? "effect" : "shapley")));
            if (z && x.has("z") && !x.get("z").isJsonNull())
                b.append(String.format(Locale.ROOT, " (z %.1f)", number(x, "z")));
        }
        return b.toString();
    }
    private static List<String> whyLines(JsonObject c) {
        List<String> out = new ArrayList<>();
        if (!c.has("why") || !c.get("why").isJsonObject()) return out;
        JsonObject why = c.getAsJsonObject("why");
        String plus = items(why.getAsJsonArray("for"), true), minus = items(why.getAsJsonArray("against"), true);
        out.add(String.format(Locale.ROOT, "Prior vs %s: %+.2f logits", text(why, "ref"), number(why, "contrast")));
        if (!plus.isEmpty()) out.add("+ " + plus);
        if (!minus.isEmpty()) out.add("- " + minus);
        return out;
    }
    private static List<String> pairLines(JsonObject pair) {
        List<String> out = new ArrayList<>();
        if (pair == null) return out;
        out.add("Why " + text(pair, "pick") + " over " + text(pair, "runner_up") + " (net prior):");
        String plus = items(pair.getAsJsonArray("for"), true), minus = items(pair.getAsJsonArray("against"), true);
        if (!plus.isEmpty()) out.add("+ " + plus);
        if (!minus.isEmpty()) out.add("- " + minus);
        if (pair.has("shapley")) {
            String sh = items(pair.getAsJsonArray("shapley"), false);
            if (!sh.isEmpty()) out.add("Shapley: " + sh);
        }
        JsonObject flip = pair.has("minimal_flip") ? pair.getAsJsonObject("minimal_flip") : null;
        if (flip != null) {
            JsonElement set = flip.get("set");
            if (set != null && set.isJsonArray()) {
                StringBuilder b = new StringBuilder();
                for (JsonElement e : set.getAsJsonArray()) b.append(b.length() > 0 ? ", " : "").append(e.getAsString());
                out.add("Prior reverses without: " + b);
            } else out.add("No small item set reverses the prior");
        }
        JsonObject hp = pair.has("hp") ? pair.getAsJsonObject("hp") : null;
        if (hp != null && hp.has("reverses_at") && !hp.get("reverses_at").isJsonNull())
            out.add("Prior reverses at HP " + hp.get("reverses_at").getAsInt() + " (now " + hp.get("hp").getAsInt() + ")");
        return out;
    }
    private static void attachHp(OocOverlay view, JsonObject distribution, int bins) {
        CombatHpOverlay.Layer root = new CombatHpOverlay.Layer(distribution.getAsJsonObject("root"), bins);
        List<CombatHpOverlay.Layer> layers = new ArrayList<>();
        layers.add(root);
        List<CombatHpOverlay.Layer> candidates = new ArrayList<>();
        for (Choice choice : view.choices) candidates.add(choice.hp);
        CombatHpOverlay.Layer sum = CombatHpOverlay.Layer.sum(candidates, bins);
        if (sum.count != root.count || sum.deaths != root.deaths || sum.unresolved != root.unresolved
                || !Arrays.equals(sum.counts(), root.counts()))
            throw new IllegalArgumentException("candidates do not partition the HP samples");
        layers.addAll(candidates);
        int currentHp = distribution.get("currentHp").getAsInt();
        if (currentHp < 0 || currentHp >= bins) throw new IllegalArgumentException("invalid current HP");
        int low = Integer.MAX_VALUE, high = Integer.MIN_VALUE;
        for (Map.Entry<String, JsonElement> entry : distribution.getAsJsonObject("root")
                .getAsJsonObject("floorOffsets").entrySet()) {
            int offset = Integer.parseInt(entry.getKey());
            low = Math.min(low, offset); high = Math.max(high, offset);
        }
        view.hpRoot = root;
        view.hpAxis = new HpAxis(currentHp, distribution.get("maxHp").getAsInt(), bins - 1, layers);
        view.hpHorizon = low > high ? "" : low == high ? "HP at floor +" + high : "HP at floor +" + low + "–" + high;
    }
    /** True when every resolved sample kept the current HP: nothing is at stake before the leaves. */
    boolean hpUnchanged() {
        return hpRoot != null && hpRoot.count > 0 && hpRoot.deaths == 0
                && hpRoot.share(hpAxis.currentHp, hpAxis.currentHp) == 1.0;
    }
    // Baseline is immutable and always first. Hover never replaces its samples.
    Distribution[] distributionLayers(Choice hovered) {
        return new Distribution[]{distribution, hovered == null ? null : hovered.distribution};
    }
    private static String label(JsonObject action, JsonObject ooc) {
        String kind = text(action, "kind");
        if (ooc.has("liveChoices")) for (JsonElement e : ooc.getAsJsonArray("liveChoices")) {
            JsonObject c = e.getAsJsonObject();
            boolean match = action.equals(c.get("liveAction"));
            if ("map".equals(kind)) match = Objects.equals(action.get("x"), c.get("x"))
                    && Objects.equals(action.get("y"), c.get("y"));
            if (match && !text(c, "mcpLabel").isEmpty()) return text(c, "mcpLabel");
        }
        if ("choose".equals(kind)) return "Choice " + text(action, "choiceIndex");
        if ("map".equals(kind)) return "Path (" + text(action, "x") + ", " + text(action, "y") + ")";
        return kind.isEmpty() ? "Choice" : Character.toUpperCase(kind.charAt(0)) + kind.substring(1).replace('_', ' ');
    }
    private static String text(JsonObject object, String field) {
        JsonElement e = object == null ? null : object.get(field);
        return e == null || e.isJsonNull() ? "" : e.getAsString();
    }
}
