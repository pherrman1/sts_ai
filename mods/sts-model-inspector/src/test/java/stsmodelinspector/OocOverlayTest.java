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
        if (!view.matches("s", 7, "h") || view.matches("s", 8, "h") || view.matches("other", 7, "h")
                || view.matches("s", 7, "changed")) throw new AssertionError("stale ranking accepted");
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
