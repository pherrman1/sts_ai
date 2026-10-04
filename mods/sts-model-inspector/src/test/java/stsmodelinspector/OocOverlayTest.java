package stsmodelinspector;

import com.google.gson.*;

/** Response display contract: physical choices, ranked scores, and freshness. */
public final class OocOverlayTest {
    private static JsonObject distribution(long death, long zero) {
        JsonObject d = new JsonObject();
        d.addProperty("schema", "ooc_value_distribution_v1");
        d.addProperty("normalization", "share_of_own_samples");
        JsonArray bins = new JsonArray();
        for (int i=0; i<22; ++i) bins.add(new JsonPrimitive(i == 0 ? death : i == 1 ? zero : 0));
        d.add("bins", bins); d.addProperty("count", death + zero);
        if (death + zero == 0) d.add("mean", JsonNull.INSTANCE); else d.addProperty("mean", 0);
        d.addProperty("terminalDeaths", death); d.addProperty("terminalVictories", 0);
        return d;
    }
    private static void rejects(JsonObject response, String observation) {
        try { OocOverlay.parse(response.toString(), observation); }
        catch (IllegalArgumentException expected) { return; }
        throw new AssertionError("malformed value distribution displayed");
    }
    public static void main(String[] args) {
        JsonParser parser = new JsonParser();
        String observation = "{\"ooc\":{\"screen\":\"card_reward\",\"liveChoices\":["
                + "{\"liveAction\":{\"kind\":\"choose\",\"choiceIndex\":1},\"mcpLabel\":\"Bash\"},"
                + "{\"liveAction\":{\"kind\":\"choose\",\"choiceIndex\":2},\"mcpLabel\":\"Bash+\"}]}}";
        JsonObject response = parser.parse("{\"session\":\"s\",\"sequence\":7,\"observationHash\":\"h\",\"evaluators\":[{"
                + "\"id\":\"live_ooc_decision_v1\",\"policy\":\"v4_q\",\"status\":\"OK\","
                + "\"selectedSemanticKey\":\"second\",\"selectedLiveAction\":{\"kind\":\"choose\",\"choiceIndex\":2},"
                + "\"candidateSummaries\":["
                + "{\"semanticKey\":\"first\",\"q\":0.1,\"visits\":10,\"visitShare\":0.2,\"prior\":0.3,\"liveAction\":{\"kind\":\"choose\",\"choiceIndex\":1}},"
                + "{\"semanticKey\":\"skip\",\"q\":0.2,\"visits\":20,\"visitShare\":0.4,\"prior\":0.3,\"liveAction\":{\"kind\":\"skip\"}},"
                + "{\"semanticKey\":\"second\",\"q\":0.3,\"visits\":20,\"visitShare\":0.4,\"prior\":0.4,\"liveAction\":{\"kind\":\"choose\",\"choiceIndex\":2}}]}]}").getAsJsonObject();
        OocOverlay view = OocOverlay.parse(response.toString(), observation);
        if (!view.choices.get(0).selected || view.choices.get(0).index != 2
                || !view.choices.get(0).label.equals("Bash+") || !view.choices.get(1).label.equals("Skip")
                || !view.choices.get(2).label.equals("Bash")) throw new AssertionError("ranking or occurrence lost");
        if (!view.choices.get(0).scoreLabel(1).equals("#1 · V4 score 0.300")
                || !view.choices.get(2).scoreLabel(3).equals("#3 · V4 score 0.100"))
            throw new AssertionError("raw V4 score mislabeled");
        if (view.panelChoices().size() != 2 || !view.panelChoices().get(0).selected
                || !view.panelChoices().get(1).kind.equals("skip"))
            throw new AssertionError("card panel must remain above the card row and retain skip");
        if (!view.matches("s", 7, "h") || view.matches("s", 8, "h") || view.matches("other", 7, "h")
                || view.matches("s", 7, "changed")) throw new AssertionError("stale ranking accepted");
        for (String screen : new String[]{"card_reward", "event", "neow", "shop"}) {
            OocOverlay inline = OocOverlay.parse(response.toString(), observation.replace("card_reward", screen));
            if (inline.forAction(InlineChoices.action("choose", 1)).index != 1
                    || !inline.forAction(InlineChoices.action("choose", 2)).selected
                    || !inline.forAction(InlineChoices.action("skip", 0)).kind.equals("skip")
                    || inline.forAction(InlineChoices.action("choose", 3)) != null)
                throw new AssertionError("inline action/physical occurrence binding lost: " + screen);
        }
        JsonObject mctsResponse = parser.parse(response.toString()).getAsJsonObject();
        JsonObject mcts = mctsResponse.getAsJsonArray("evaluators").get(0).getAsJsonObject();
        mcts.addProperty("policy", "mcts_ctm"); mcts.addProperty("valueSemantics", "mean_backed_up_value_0_1");
        mcts.add("valueDistribution", distribution(10,40));
        for (JsonElement e : mcts.getAsJsonArray("candidateSummaries")) {
            JsonObject c = e.getAsJsonObject(); c.addProperty("q",0);
            long n = c.get("visits").getAsLong();
            c.add("valueDistribution", distribution(n == 10 ? n : 0, n == 10 ? 0 : n));
        }
        OocOverlay mctsView = OocOverlay.parse(mctsResponse.toString(), observation);
        OocOverlay.Distribution baseline = mctsView.distribution;
        OocOverlay.Distribution[] hover = mctsView.distributionLayers(mctsView.choices.get(2));
        if (baseline.count != 50 || baseline.deaths != 10 || baseline.bin(1) != 40
                || baseline.share(0) != .2 || hover[0] != baseline || hover[1].share(0) != 1
                || mctsView.distributionLayers(null)[0] != baseline
                || mctsView.distributionLayers(null)[1] != null
                || !mctsView.choices.get(0).scoreLabel(1).equals("#1 · Mean 0.000 · N 20")
                || !baseline.summary("Baseline").contains("sampled death 20.0%"))
            throw new AssertionError("baseline, hover normalization, death/low-value separation or label changed");
        if (mctsView.hpRoot != null || !Double.isNaN(baseline.standardError()))
            throw new AssertionError("absent HP samples or value spread were invented");
        // Endpoint HP: one shared axis, candidates partition the root.
        JsonObject hpResponse = parser.parse(mctsResponse.toString()).getAsJsonObject();
        JsonObject hpEvaluator = hpResponse.getAsJsonArray("evaluators").get(0).getAsJsonObject();
        JsonObject hpDist = parser.parse("{\"schema\":\"ooc_endpoint_hp_distribution_v1\",\"currentHp\":3,"
                + "\"maxHp\":4,\"rootFloor\":7,\"axisMaxHp\":4,\"root\":{\"count\":50,\"deaths\":0,"
                + "\"unresolved\":0,\"hpCounts\":[0,0,10,40,0],\"floorOffsets\":{\"0\":10,\"1\":40}}}").getAsJsonObject();
        hpEvaluator.add("endpointHpDistribution", hpDist);
        for (JsonElement e : hpEvaluator.getAsJsonArray("candidateSummaries")) {
            JsonObject c = e.getAsJsonObject();
            long n = c.get("visits").getAsLong();
            c.add("endpointHp", parser.parse("{\"count\":" + n + ",\"deaths\":0,\"unresolved\":0,\"hpCounts\":"
                    + (n == 10 ? "[0,0,10,0,0]" : "[0,0,0," + n + ",0]") + ",\"floorOffsets\":{}}"));
        }
        OocOverlay hpView = OocOverlay.parse(hpResponse.toString(), observation);
        OocOverlay.Choice tenVisits = null;
        for (OocOverlay.Choice choice : hpView.choices) if (choice.visits == 10) tenVisits = choice;
        if (hpView.hpRoot.count != 50 || hpView.hpAxis.currentHp != 3 || hpView.hpAxis.axisMaxHp != 4
                || !hpView.hpHorizon.equals("HP at floor +0–1") || hpView.hpUnchanged()
                || tenVisits == null || tenVisits.hp.meanHp() != 2)
            throw new AssertionError("endpoint HP axis, horizon or candidate layer lost");
        hpEvaluator.getAsJsonArray("candidateSummaries").get(0).getAsJsonObject().getAsJsonObject("endpointHp")
                .addProperty("unresolved", 1);
        rejects(hpResponse, observation);
        JsonObject spread = distribution(0, 4);
        spread.addProperty("mean", .5); spread.addProperty("sumSquares", 1.16);
        // Samples with mean .5 and sum of squares 1.16: variance (1.16-1)/3, SE sqrt(variance/4).
        if (Math.abs(new OocOverlay.Distribution(spread).standardError() - Math.sqrt(0.16 / 3 / 4)) > 1e-12)
            throw new AssertionError("value standard error wrong");
        JsonObject mctsFirst = mcts.getAsJsonArray("candidateSummaries").get(0).getAsJsonObject();
        mctsFirst.addProperty("q",1.1); rejects(mctsResponse, observation); mctsFirst.addProperty("q",0);
        mcts.add("valueDistribution", distribution(9,41)); rejects(mctsResponse, observation);
        mcts.add("valueDistribution", distribution(10,40));
        mctsFirst.getAsJsonObject("valueDistribution").addProperty("count",9);
        rejects(mctsResponse, observation);
        JsonObject raw = parser.parse(response.toString()).getAsJsonObject();
        raw.getAsJsonArray("evaluators").get(0).getAsJsonObject().getAsJsonArray("candidateSummaries")
                .get(2).getAsJsonObject().addProperty("q",123.25);
        OocOverlay rawView = OocOverlay.parse(raw.toString(), observation);
        if (rawView.choices.get(0).q != 123.25 || !rawView.choices.get(0).scoreLabel(1).contains("V4 score 123.250"))
            throw new AssertionError("raw V4 scores above 100 were clamped or labeled as probabilities");
        JsonObject previewResponse = parser.parse(response.toString()).getAsJsonObject();
        JsonObject preview = parser.parse("{\"status\":\"OK\",\"policy\":\"v4_q\",\"scope\":\"selector_preview\","
                + "\"selectorType\":\"upgrade\",\"q\":7.5,\"card\":{\"id\":\"Bash\",\"upgraded\":false,\"misc\":0,\"deckIndex\":1}}")
                .getAsJsonObject();
        previewResponse.getAsJsonArray("evaluators").get(0).getAsJsonObject().getAsJsonArray("candidateSummaries")
                .get(2).getAsJsonObject().add("followUpPreview", preview);
        JsonObject previewObservation = parser.parse(observation).getAsJsonObject();
        previewObservation.getAsJsonObject("ooc").add("publicState", parser.parse("{\"deck\":["
                + "{\"id\":\"Bash\",\"upgraded\":false,\"misc\":0,\"uuid\":\"first\"},"
                + "{\"id\":\"Bash\",\"upgraded\":false,\"misc\":0,\"uuid\":\"second\"}]}"));
        OocOverlay withPreview = OocOverlay.parse(previewResponse.toString(), previewObservation.toString());
        if (!withPreview.choices.get(0).followUpUuid.equals("second") || withPreview.choices.get(0).q != .3
                || withPreview.choices.get(0).followUp.get("q").getAsDouble() != 7.5)
            throw new AssertionError("preview mixed parent Q or lost duplicate physical target");
        preview.getAsJsonObject("card").addProperty("id", "Strike_R");
        boolean invalidPreview = false;
        try { OocOverlay.parse(previewResponse.toString(), previewObservation.toString()); }
        catch (IllegalArgumentException expected) { invalidPreview = true; }
        if (!invalidPreview) throw new AssertionError("mismatched preview target displayed");

        JsonObject mapResponse = parser.parse(response.toString()).getAsJsonObject();
        JsonObject mapEvaluator = mapResponse.getAsJsonArray("evaluators").get(0).getAsJsonObject();
        JsonObject mapAction = parser.parse("{\"kind\":\"choose\",\"choiceIndex\":2}").getAsJsonObject();
        mapEvaluator.add("selectedLiveAction", mapAction);
        mapEvaluator.addProperty("selectedSemanticKey", "node");
        JsonArray mapCandidates = new JsonArray();
        JsonObject mapCandidate = parser.parse("{\"semanticKey\":\"node\",\"q\":2.5,\"visits\":1,\"visitShare\":1.0,\"prior\":1.0}").getAsJsonObject();
        mapCandidate.add("liveAction", mapAction); mapCandidates.add(mapCandidate);
        mapEvaluator.add("candidateSummaries", mapCandidates);
        OocOverlay mapView = OocOverlay.parse(mapResponse.toString(), "{\"ooc\":{\"screen\":\"map\",\"liveChoices\":[]}}");
        if (!mapView.forAction(InlineChoices.mapAction(2)).selected
                || mapView.forAction(InlineChoices.mapAction(1)) != null)
            throw new AssertionError("map physical choice binding lost");
        mapEvaluator.addProperty("policy","mcts_ctm");
        mapEvaluator.addProperty("valueSemantics","mean_backed_up_value_0_1");
        mapEvaluator.add("valueDistribution",distribution(0,0));
        mapCandidate.addProperty("visits",0); mapCandidate.addProperty("q",0);
        mapCandidate.add("valueDistribution",distribution(0,0));
        OocOverlay sole = OocOverlay.parse(mapResponse.toString(), observation);
        if (sole.distribution.count != 0 || !sole.choices.get(0).scoreLabel(1).contains("No samples"))
            throw new AssertionError("sole-choice shortcut invented samples");
        mapEvaluator.addProperty("valueSemantics","forced_no_search");
        mapCandidate.addProperty("visitShare",0);
        mapEvaluator.remove("valueDistribution"); mapCandidate.remove("valueDistribution");
        if (!OocOverlay.parse(mapResponse.toString(), observation).choices.get(0).scoreLabel(1).contains("Forced"))
            throw new AssertionError("pass-through placeholder displayed as score");
        JsonObject evaluator = response.getAsJsonArray("evaluators").get(0).getAsJsonObject();
        evaluator.addProperty("status", "UNSUPPORTED"); evaluator.addProperty("reason", "NATIVE_SCREEN_UNSUPPORTED");
        view = OocOverlay.parse(response.toString(), observation);
        if (!view.choices.isEmpty() || !view.reason.equals("NATIVE_SCREEN_UNSUPPORTED"))
            throw new AssertionError("unsupported displays a ranking");
        evaluator.addProperty("status", "OK");
        evaluator.addProperty("selectedSemanticKey", "missing");
        boolean rejected = false;
        try { OocOverlay.parse(response.toString(), observation); }
        catch (IllegalArgumentException expected) { rejected = true; }
        if (!rejected) throw new AssertionError("missing selected choice displayed");
        response.addProperty("status", "ERROR"); response.addProperty("message", "Bad observation");
        view = OocOverlay.parse(response.toString(), observation);
        if (!view.choices.isEmpty() || !view.status.equals("ERROR") || !view.reason.equals("Bad observation"))
            throw new AssertionError("error hidden by nested ranking");
        System.out.println("OocOverlayTest: ranking, occurrence, freshness, unsupported, malformed and error checks passed");
    }
}
