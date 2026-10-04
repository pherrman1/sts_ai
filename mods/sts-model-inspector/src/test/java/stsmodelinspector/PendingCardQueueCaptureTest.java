package stsmodelinspector;

import java.util.*;
import com.google.gson.*;

public final class PendingCardQueueCaptureTest {
    private static PendingCardQueueCapture.Item copy(String uuid, String id, int target) {
        PendingCardQueueCapture.Item item = new PendingCardQueueCapture.Item();
        item.identity = new Object(); item.uuid = uuid;
        item.cardJson = "{\"id\":\""+id+"\",\"uuid\":\""+uuid+"\",\"upgraded\":false,\"misc\":0,"
                +"\"cost\":1,\"costForTurn\":0,\"freeToPlayOnce\":true,\"retain\":false}";
        item.hasMonster = true; item.requiresTarget = true; item.target = target;
        item.autoplay = true; item.ignoreEnergyTotal = true; item.purgeOnUse = true;
        item.energyOnUse = 2; item.freeToPlay = true;
        return item;
    }
    private static void reject(List<PendingCardQueueCapture.Item> items, Object current, String reason) {
        PendingCardQueueCapture.Result result = PendingCardQueueCapture.capture(items, current);
        if (!reason.equals(result.error) || result.json != null) throw new AssertionError("expected " + reason);
    }
    public static void main(String[] args) throws Exception {
        Object processed = new Object();
        // All three vanilla repeat mechanisms use makeSameInstanceOf(): the
        // copy retains UUID but is a distinct physical queue item.
        for (String source : Arrays.asList("DoubleTap", "Duplication", "Necronomicon")) {
            PendingCardQueueCapture.Item a = copy("played-uuid", "Headbutt", 2);
            PendingCardQueueCapture.Item b = copy("played-uuid", "Headbutt", 0);
            PendingCardQueueCapture.Item generated = copy("new-uuid", "Strike_R", 1);
            generated.exhaustOnUse = true;
            PendingCardQueueCapture.Result result = PendingCardQueueCapture.capture(Arrays.asList(a,b,generated), processed);
            if (result.error != null) throw new AssertionError(source+": "+result.error);
            JsonArray array = new Gson().fromJson(result.json, JsonArray.class);
            JsonObject first = array.get(0).getAsJsonObject();
            if (array.size()!=3 || first.get("target").getAsInt()!=2
                    || array.get(1).getAsJsonObject().get("target").getAsInt()!=0
                    || !array.get(2).getAsJsonObject().getAsJsonObject("card").get("uuid").getAsString().equals("new-uuid")
                    || first.get("isEndTurn").getAsBoolean() || !first.get("triggerOnUse").getAsBoolean()
                    || !first.get("freeToPlay").getAsBoolean() || !first.get("ignoreEnergyTotal").getAsBoolean()
                    || !first.get("autoplay").getAsBoolean() || !first.get("purgeOnUse").getAsBoolean()
                    || first.get("energyOnUse").getAsInt()!=2 || first.get("regretCardCount").getAsInt()!=0
                    || !array.get(2).getAsJsonObject().get("exhaustOnUse").getAsBoolean())
                throw new AssertionError("queue order, flags or identity changed");
            reject(Arrays.asList(a), a.identity, "queue_not_settled");
            reject(Arrays.asList(a,a), processed, "queue_not_settled");
        }
        if (!"[]".equals(PendingCardQueueCapture.capture(Collections.emptyList(),processed).json))
            throw new AssertionError("observed empty is not explicit");
        reject(null, processed, "queue_unavailable");
        reject(Arrays.asList((PendingCardQueueCapture.Item)null), processed, "unknown_queue_item");
        PendingCardQueueCapture.Item item = copy("q", "Headbutt", 0);
        item.vanilla=false; reject(Arrays.asList(item),processed,"unknown_queue_item"); item.vanilla=true;
        item.uuid=null; reject(Arrays.asList(item),processed,"card_identity"); item.uuid="q";
        item.target=null; reject(Arrays.asList(item),processed,"queue_target"); item.target=0;
        item.hasMonster=false; reject(Arrays.asList(item),processed,"queue_target");
        item.randomTarget=true;
        if(PendingCardQueueCapture.capture(Arrays.asList(item),processed).error!=null) throw new AssertionError("public random-target rule rejected");
        item.endTurnAutoPlay=true; reject(Arrays.asList(item),processed,"end_turn_card_continuation");
        item.endTurnAutoPlay=false; item.triggerOnUse=false;
        reject(Arrays.asList(item),processed,"end_turn_card_continuation"); item.triggerOnUse=true;
        item.energyOnUse=-1; reject(Arrays.asList(item),processed,"queue_energy");
        List<PendingCardQueueCapture.Item> many = new ArrayList<>();
        for(int i=0;i<11;i++) many.add(copy("q"+i,"Headbutt",0));
        reject(many,processed,"queue_capacity");
        PendingCardQueueCapture.Item marker = new PendingCardQueueCapture.Item(); marker.identity=new Object();
        JsonObject end = new Gson().fromJson(PendingCardQueueCapture.capture(Arrays.asList(marker),processed).json,JsonArray.class).get(0).getAsJsonObject();
        if(!end.get("card").isJsonNull() || !end.get("isEndTurn").getAsBoolean()) throw new AssertionError("null-card marker mapping");
        marker.autoplay=true; reject(Arrays.asList(marker),processed,"end_turn_marker");
        // Source-shaped Burn/Decay end-turn items: same physical hand cards,
        // no target, no normal play, Java end-turn autoplay flag is distinct.
        for(String id:Arrays.asList("Burn","Decay","Doubt","Shame","Regret")) {
            PendingCardQueueCapture.Item status=new PendingCardQueueCapture.Item();
            status.identity=new Object();status.uuid="status-"+id;status.cardId=id;
            status.cardJson="{\"id\":\""+id+"\",\"uuid\":\""+status.uuid+"\"}";
            status.inHand=true;status.vanillaEndTurnCard=true;status.triggerOnUse=false;
            status.endTurnAutoPlay=true;status.energyOnUse=2;
            if ("Regret".equals(id)) status.regretCardCount=7;
            PendingCardQueueCapture.Result accepted=PendingCardQueueCapture.capture(Arrays.asList(status),processed,true,false);
            if(accepted.error!=null)throw new AssertionError(id+" Codex queue rejected: "+accepted.error);
            JsonObject row=new Gson().fromJson(accepted.json,JsonArray.class).get(0).getAsJsonObject();
            if(row.get("isEndTurn").getAsBoolean() || row.get("triggerOnUse").getAsBoolean()
                    || !row.get("endTurnAutoPlay").getAsBoolean()
                    || !"codex_end_turn".equals(row.get("noTriggerOwner").getAsString()))
                throw new AssertionError("Codex no-trigger proof lost");
            if(PendingCardQueueCapture.capture(Arrays.asList(status),processed,false,false).error==null
                    || PendingCardQueueCapture.capture(Arrays.asList(status),processed,true,true).error!=null)
                throw new AssertionError("owner proof or Unceasing Top continuation mismatch");
            if (row.get("regretCardCount").getAsInt() != ("Regret".equals(id)?7:0))
                throw new AssertionError("Regret captured trigger-time hand count lost");
            status.inHand=false;
            if(PendingCardQueueCapture.capture(Arrays.asList(status),processed,true,false).error==null)
                throw new AssertionError("non-hand status queue accepted");
            status.inHand=true;status.cardId="Regret";status.regretCardCount=null;
            if(PendingCardQueueCapture.capture(Arrays.asList(status),processed,true,false).error==null)
                throw new AssertionError("unqualified no-trigger payload accepted");
        }
        // Installed JAR shape: missing or changed public fields cannot quietly
        // fall back to false; production reads them directly at compile time.
        Class<?> cls=Class.forName("com.megacrit.cardcrawl.cards.CardQueueItem",false,PendingCardQueueCaptureTest.class.getClassLoader());
        for(String flag:Arrays.asList("ignoreEnergyTotal","autoplayCard","randomTarget","isEndTurnAutoPlay"))
            if(cls.getField(flag).getType()!=boolean.class) throw new AssertionError("JAR queue flag changed");
        System.out.println("PendingCardQueueCaptureTest PASS");
    }
}
