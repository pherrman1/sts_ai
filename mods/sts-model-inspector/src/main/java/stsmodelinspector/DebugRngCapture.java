package stsmodelinspector;

import com.badlogic.gdx.math.RandomXS128;
import com.google.gson.Gson;
import com.megacrit.cardcrawl.dungeons.AbstractDungeon;
import com.megacrit.cardcrawl.random.Random;
import com.evacipated.cardcrawl.modthespire.Loader;
import com.evacipated.cardcrawl.modthespire.ModInfo;

import java.util.LinkedHashMap;
import java.util.Map;

/** Read-only, opt-in hidden RNG diagnostics for differential testing only. */
final class DebugRngCapture {
    private static final boolean ENABLED = "1".equals(System.getenv("STS_DIFFERENTIAL_DEBUG_RNG"));
    private static final Gson JSON = new Gson();

    private DebugRngCapture() {}

    private static Map<String, Object> tuple(Random rng) {
        Map<String, Object> out = new LinkedHashMap<>();
        if (rng == null || rng.random == null) {
            out.put("available", false);
            out.put("reason", "stream_uninitialized");
            return out;
        }
        RandomXS128 raw = rng.random;
        out.put("counter", rng.counter);
        out.put("seed0", Long.toUnsignedString(raw.getState(0)));
        out.put("seed1", Long.toUnsignedString(raw.getState(1)));
        return out;
    }

    static boolean enabled() {
        return ENABLED || "1".equals(System.getenv("STS_DIFFERENTIAL_TRACE"));
    }

    static String json() {
        if (!ENABLED) return "";
        try {
            Map<String, Object> streams = new LinkedHashMap<>();
            streams.put("aiRng", tuple(AbstractDungeon.aiRng));
            streams.put("cardRandomRng", tuple(AbstractDungeon.cardRandomRng));
            streams.put("cardRng", tuple(AbstractDungeon.cardRng));
            streams.put("eventRng", tuple(AbstractDungeon.eventRng));
            streams.put("merchantRng", tuple(AbstractDungeon.merchantRng));
            streams.put("miscRng", tuple(AbstractDungeon.miscRng));
            streams.put("monsterHpRng", tuple(AbstractDungeon.monsterHpRng));
            streams.put("monsterRng", tuple(AbstractDungeon.monsterRng));
            streams.put("potionRng", tuple(AbstractDungeon.potionRng));
            streams.put("relicRng", tuple(AbstractDungeon.relicRng));
            streams.put("shuffleRng", tuple(AbstractDungeon.shuffleRng));
            streams.put("treasureRng", tuple(AbstractDungeon.treasureRng));
            Map<String, Object> envelope = new LinkedHashMap<>();
            envelope.put("schema", "sts_java_rng_v1");
            envelope.put("available", true);
            envelope.put("streams", streams);
            return JSON.toJson(envelope);
        } catch (Throwable error) {
            Map<String, Object> envelope = new LinkedHashMap<>();
            envelope.put("schema", "sts_java_rng_v1");
            envelope.put("available", false);
            envelope.put("reason", error.getClass().getName());
            return JSON.toJson(envelope);
        }
    }

    static String runtimeJson() {
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("gameVersion", Loader.STS_VERSION);
        out.put("modTheSpireVersion", String.valueOf(Loader.MTS_VERSION));
        out.put("javaVersion", System.getProperty("java.version", "unknown"));
        Map<String, Object> mods = new LinkedHashMap<>();
        boolean superFast = false;
        if (Loader.MODINFOS != null) for (ModInfo info : Loader.MODINFOS) {
            if (info == null || info.ID == null) continue;
            mods.put(info.ID, String.valueOf(info.ModVersion));
            if (info.ID.toLowerCase().contains("superfast")
                    || (info.Name != null && info.Name.toLowerCase().contains("super fast")))
                superFast = true;
        }
        out.put("mods", mods);
        out.put("superFastMode", superFast);
        return JSON.toJson(out);
    }
}
