package stsmodelinspector;

import com.google.gson.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.zip.GZIPInputStream;

/** Exercise the UI anchor binding against actual recorded live map responses. */
public final class MapOverlayTest {
    public static void main(String[] args) throws Exception {
        JsonParser parser = new JsonParser();
        int screens = 0, choices = 0;
        try (BufferedReader input = new BufferedReader(new InputStreamReader(
                new GZIPInputStream(new FileInputStream(args[0])), StandardCharsets.UTF_8))) {
            String line;
            while ((line = input.readLine()) != null) {
                JsonObject row = parser.parse(line).getAsJsonObject();
                if (!row.has("screen_type") || !"MAP".equals(row.get("screen_type").getAsString())
                        || !row.has("ooc_evaluator")) continue;
                JsonObject evaluator = row.getAsJsonObject("ooc_evaluator");
                if (!"OK".equals(evaluator.get("status").getAsString())) continue;
                JsonObject response = new JsonObject();
                response.add("session", row.get("inspector_session"));
                response.add("sequence", row.get("inspector_sequence"));
                response.add("observationHash", row.get("inspector_observationHash"));
                JsonArray evaluators = new JsonArray(); evaluators.add(evaluator);
                response.add("evaluators", evaluators);
                OocOverlay view = OocOverlay.parse(response.toString(),
                        "{\"ooc\":{\"screen\":\"map\",\"liveChoices\":[]}}");
                for (OocOverlay.Choice choice : view.choices) {
                    if (!"choose".equals(choice.kind) || choice.index < 1
                            || view.forAction(InlineChoices.mapAction(choice.index)) != choice)
                        throw new AssertionError("live map candidate cannot attach to its physical node");
                    ++choices;
                }
                ++screens;
            }
        }
        if (screens == 0 || choices == 0) throw new AssertionError("no real map responses exercised");
        System.out.println("MapOverlayTest: " + screens + " recorded map screens, " + choices + " physical node bindings passed");
    }
}
