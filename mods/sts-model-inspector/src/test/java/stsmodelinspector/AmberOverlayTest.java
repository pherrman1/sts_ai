package stsmodelinspector;

import com.google.gson.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;

/** amber_explain_v1 display contract: physical choices, the pick, P(win) labels and the explanation lines. */
public final class AmberOverlayTest {
    private static JsonObject candidate(JsonObject action, boolean selected, long visits, double prior, double pWin) {
        JsonObject c = new JsonObject();
        if (action == null) c.add("liveAction", JsonNull.INSTANCE); else c.add("liveAction", action);
        c.addProperty("label", "encoder label");
        c.addProperty("selected", selected);
        c.addProperty("prior", prior);
        c.addProperty("visits", visits);
        c.addProperty("visitShare", visits / 64.0);
        c.addProperty("q", 0.3);
        c.addProperty("pWin", pWin);
        c.addProperty("hpFloorEnd", 28.0);
        c.addProperty("hpNextFloor", 74.4);
        JsonObject why = new JsonObject();
        why.addProperty("ref", "skip / leave rewards");
        why.addProperty("contrast", 2.089);
        JsonArray plus = new JsonArray();
        JsonObject item = new JsonObject();
        item.addProperty("item", "Shrug It Off"); item.addProperty("effect", 0.887); item.addProperty("z", 4.0);
        plus.add(item);
        why.add("for", plus);
        why.add("against", new JsonArray());
        c.add("why", why);
        return c;
    }
    private static JsonObject action(String kind, int index) {
        JsonObject a = new JsonObject();
        a.addProperty("kind", kind);
        if (index >= 0) a.addProperty("choiceIndex", index);
        return a;
    }
    public static void main(String[] args) throws Exception {
        String observation = "{\"ooc\":{\"screen\":\"card_reward\",\"liveChoices\":["
                + "{\"liveAction\":{\"kind\":\"choose\",\"choiceIndex\":1},\"mcpLabel\":\"Barricade\"},"
                + "{\"liveAction\":{\"kind\":\"skip\"},\"mcpLabel\":\"Skip\"}]}}";
        JsonObject ev = new JsonObject();
        ev.addProperty("id", "amber_explain_v1");
        ev.addProperty("status", "OK");
        JsonObject root = new JsonObject();
        root.addProperty("netPWin", 0.271); root.addProperty("searchPWin", 0.282); root.addProperty("visits", 64);
        ev.add("root", root);
        JsonArray cands = new JsonArray();
        cands.add(candidate(action("choose", 1), true, 30, 0.47, 0.346));
        cands.add(candidate(null, false, 4, 0.07, 0.25));            // no live action: left out
        cands.add(candidate(action("skip", -1), false, 22, 0.06, 0.254));
        cands.add(candidate(action("skip", -1), false, 8, 0.05, 0.2));  // same live control again: left out
        ev.add("candidates", cands);
        JsonObject pair = new JsonParser().parse("{\"pick\":\"take Barricade\",\"runner_up\":\"skip\","
                + "\"for\":[{\"item\":\"Shrug It Off\",\"effect\":0.89,\"z\":4.0}],\"against\":[],"
                + "\"shapley\":[{\"item\":\"Shrug It Off\",\"shapley\":0.91}],"
                + "\"minimal_flip\":{\"contrast\":2.0,\"set\":[\"Shrug It Off\",\"Ghostly Armor\"]},"
                + "\"hp\":{\"hp\":28,\"reverses_at\":21}}").getAsJsonObject();
        ev.add("pair", pair);
        JsonObject response = new JsonObject();
        response.addProperty("session", "s"); response.addProperty("sequence", 3);
        response.addProperty("observationHash", "h"); response.addProperty("status", "OK");
        JsonArray evs = new JsonArray();
        evs.add(ev);
        response.add("evaluators", evs);
        OocOverlay view = OocOverlay.parse(response.toString(), observation);
        if (!"OK".equals(view.status) || !OocOverlay.AMBER_POLICY.equals(view.policy) || view.choices.size() != 2)
            throw new AssertionError("Amber candidates not taken: " + view.choices.size());
        OocOverlay.Choice first = view.choices.get(0);
        if (!first.selected || first.index != 1 || !first.label.equals("Barricade") || first.visits != 30)
            throw new AssertionError("Amber pick lost");
        if (!first.scoreLabel(1).equals("#1 · P(win) 34.6% · N 30"))
            throw new AssertionError("Amber label: " + first.scoreLabel(1));
        if (view.forAction(action("skip", -1)).visits != 22) throw new AssertionError("duplicate live control kept");
        if (first.why.size() != 2 || !first.why.get(1).startsWith("+ Shrug It Off +0.89 (z 4.0)"))
            throw new AssertionError("option explanation: " + first.why);
        if (!view.amberRoot.startsWith("Net P(win) 27.1% · search 28.2%") || view.amberPair.size() != 5
                || !view.amberPair.get(3).equals("Prior reverses without: Shrug It Off, Ghostly Armor")
                || !view.amberPair.get(4).equals("Prior reverses at HP 21 (now 28)"))
            throw new AssertionError("pair explanation: " + view.amberRoot + " " + view.amberPair);
        // the legacy evaluator next to an Amber one: Amber wins unless turned off
        OocOverlay.preferAmber = false;
        try {
            OocOverlay legacy = OocOverlay.parse(response.toString(), observation);
            if (OocOverlay.AMBER_POLICY.equals(legacy.policy)) throw new AssertionError("oocSource=legacy ignored");
        } finally { OocOverlay.preferAmber = true; }
        // a forced decision
        JsonObject forced = new JsonParser().parse(response.toString()).getAsJsonObject();
        JsonObject fe = forced.getAsJsonArray("evaluators").get(0).getAsJsonObject();
        fe.addProperty("status", "FORCED"); fe.remove("candidates"); fe.add("selectedLiveAction", action("skip", -1));
        OocOverlay f = OocOverlay.parse(forced.toString(), observation);
        if (f.choices.size() != 1 || !f.choices.get(0).scoreLabel(1).equals("#1 · Forced"))
            throw new AssertionError("forced Amber choice");
        // a pick without a live action is no recommendation
        JsonObject broken = new JsonParser().parse(response.toString()).getAsJsonObject();
        broken.getAsJsonArray("evaluators").get(0).getAsJsonObject().getAsJsonArray("candidates")
                .get(0).getAsJsonObject().add("liveAction", JsonNull.INSTANCE);
        try { OocOverlay.parse(broken.toString(), observation); throw new AssertionError("unmapped pick shown"); }
        catch (IllegalArgumentException expected) { }
        // optional: a real advisor response line and its observation (tools/az_bench/amber_advisor.py output)
        if (args.length == 2) {
            String line = new String(Files.readAllBytes(Paths.get(args[0])), StandardCharsets.UTF_8).trim();
            String obs = new String(Files.readAllBytes(Paths.get(args[1])), StandardCharsets.UTF_8);
            OocOverlay real = OocOverlay.parse(line, obs);
            System.out.println(real.status + " " + real.amberRoot);
            for (OocOverlay.Choice c : real.choices) {
                System.out.println("  " + c.label + " | " + c.scoreLabel(real.choices.indexOf(c) + 1));
                for (String w : c.why) System.out.println("      " + w);
            }
            for (String w : real.amberPair) System.out.println("  " + w);
        }
        System.out.println("AmberOverlayTest OK");
    }
}
