package stsmodelinspector;

import com.google.gson.*;

/** Response display contract: physical choices, ranked scores, and freshness. */
public final class OocOverlayTest {
    public static void main(String[] args) {
        JsonParser parser = new JsonParser();
        String observation = "{\"ooc\":{\"screen\":\"card_reward\",\"liveChoices\":["
                + "{\"liveAction\":{\"kind\":\"choose\",\"choiceIndex\":1},\"mcpLabel\":\"Bash\"},"
                + "{\"liveAction\":{\"kind\":\"choose\",\"choiceIndex\":2},\"mcpLabel\":\"Bash+\"}]}}";
        JsonObject response = parser.parse("{\"session\":\"s\",\"sequence\":7,\"observationHash\":\"h\",\"evaluators\":[{"
                + "\"id\":\"live_ooc_decision_v1\",\"policy\":\"v4_q\",\"status\":\"OK\","
                + "\"selectedSemanticKey\":\"second\",\"selectedLiveAction\":{\"kind\":\"choose\",\"choiceIndex\":2},"
                + "\"candidateSummaries\":["
                + "{\"semanticKey\":\"first\",\"q\":0.1,\"liveAction\":{\"kind\":\"choose\",\"choiceIndex\":1}},"
                + "{\"semanticKey\":\"skip\",\"q\":0.2,\"liveAction\":{\"kind\":\"skip\"}},"
                + "{\"semanticKey\":\"second\",\"q\":0.3,\"liveAction\":{\"kind\":\"choose\",\"choiceIndex\":2}}]}]}").getAsJsonObject();
        OocOverlay view = OocOverlay.parse(response.toString(), observation);
        if (!view.choices.get(0).selected || view.choices.get(0).index != 2
                || !view.choices.get(0).label.equals("Bash+") || !view.choices.get(1).label.equals("Skip")
                || !view.choices.get(2).label.equals("Bash")) throw new AssertionError("ranking or occurrence lost");
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
        JsonObject mapCandidate = parser.parse("{\"semanticKey\":\"node\",\"q\":2.5}").getAsJsonObject();
        mapCandidate.add("liveAction", mapAction); mapCandidates.add(mapCandidate);
        mapEvaluator.add("candidateSummaries", mapCandidates);
        OocOverlay mapView = OocOverlay.parse(mapResponse.toString(), "{\"ooc\":{\"screen\":\"map\",\"liveChoices\":[]}}");
        if (!mapView.forAction(InlineChoices.mapAction(2)).selected
                || mapView.forAction(InlineChoices.mapAction(1)) != null)
            throw new AssertionError("map physical choice binding lost");
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
