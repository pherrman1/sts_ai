package stsmodelinspector;

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Exercises actual JSON save/load callbacks without initializing a game. */
public final class RelicOfferRecorderTest {
    private static final Gson JSON = new Gson();
    private static final Object PLAYER = new Object();
    private static void require(boolean ok, String reason) {
        if (!ok) throw new AssertionError(reason);
    }
    private static Map<String,Object> combat(int floor, String kind, String encounter) {
        Map<String,Object> value = new LinkedHashMap<>();
        value.put("floor", floor); value.put("kind", kind); value.put("encounter", encounter);
        return value;
    }
    private static RelicOfferRecorder.SaveData checkpoint() {
        RelicOfferRecorder.SaveData data = new RelicOfferRecorder.SaveData();
        data.version = 1; data.seed = 12345L; data.floor = 8; data.ascension = 0;
        data.character = "IRONCLAD"; data.complete = true; data.currentShopRevealed = false;
        data.offers = new ArrayList<>(Arrays.asList("Anchor", "Vajra"));
        data.combatAct = 1; data.combatComplete = true;
        data.combatEntries = new ArrayList<>(Arrays.asList(combat(3,"FIXED_EVENT","MUSHROOMS_EVENT"),
                combat(5,"NORMAL_QUEUE","JAW_WORM"), combat(8,"ELITE_QUEUE","GREMLIN_NOB")));
        return data;
    }
    private static void load(RelicOfferRecorder.SaveData data, long seed, int floor,
            String character, int ascension, List<Integer> completed) {
        new RelicOfferRecorder().onLoadRaw(JSON.toJsonTree(data));
        RelicOfferRecorder.restorePending(PLAYER, seed, floor, character, ascension, 1, completed);
    }
    private static void load(RelicOfferRecorder.SaveData data) {
        load(data, 12345, 8, "IRONCLAD", 0, Arrays.asList(3,5,8));
    }
    private static void rejected(JsonObject raw, String label) {
        require(RelicOfferRecorder.decodeCheckpoint(raw) == null, label);
        new RelicOfferRecorder().onLoadRaw(raw);
        RelicOfferRecorder.restorePending(PLAYER, 12345, 8, "IRONCLAD", 0, 1, Arrays.asList(3,5,8));
        require(!LiveOocCapture.seenRelicOffers.complete()
                && !LiveOocCapture.combatClassHistory.complete(), "malformed save retained qualified history: " + label);
    }
    private static void colosseumCheckpoints() {
        LiveOocCapture.CombatClassHistory history = new LiveOocCapture.CombatClassHistory();
        Object first = new Object(), second = new Object();
        history.observe(PLAYER,12345,2,25,true,true,first,"FIXED_EVENT","COLOSSEUM_EVENT_SLAVERS","Colosseum");
        history.observe(PLAYER,12345,2,25,false,false,null,null,"","Colosseum");
        require(history.completeFor(Arrays.asList(25)),"Colosseum first victory lost history");
        for(int stage=0;stage<3;++stage) {
            if(stage==1) {
                history.observe(PLAYER,12345,2,25,false,true,second,"FIXED_EVENT","COLOSSEUM_EVENT_NOBS","Colosseum");
                history.observe(PLAYER,12345,2,25,false,true,second,"FIXED_EVENT","COLOSSEUM_EVENT_NOBS","Colosseum");
            }
            RelicOfferRecorder.SaveData saved=checkpoint();saved.floor=25;saved.combatAct=2;saved.combatEntries=history.snapshot();
            List<Integer> metrics=stage==2?Arrays.asList(25,25):Arrays.asList(25);
            new RelicOfferRecorder().onLoadRaw(JSON.toJsonTree(saved));
            RelicOfferRecorder.restorePending(PLAYER,12345,25,"IRONCLAD",0,2,metrics);
            LiveOocCapture.CombatClassHistory restored=LiveOocCapture.combatClassHistory;
            require(restored.complete() && restored.snapshot().size()==(stage==0?1:2),"Colosseum save phase "+stage);
            require(restored.completeFor(metrics)==(stage!=1),"pending second fight claimed completed metric");
            restored.observe(PLAYER,12345,2,25,false,true,new Object(),"FIXED_EVENT",
                    stage==0?"COLOSSEUM_EVENT_SLAVERS":"COLOSSEUM_EVENT_NOBS",null);
            require(restored.complete(),"bound current fight lost on group/event reconstruction");
            restored.observe(PLAYER,12345,2,25,false,true,new Object(),"FIXED_EVENT","COLOSSEUM_EVENT_NOBS","Colosseum");
            require(restored.completeFor(Arrays.asList(25,25)) && restored.snapshot().size()==2,
                    "Colosseum reload repeated or lost second fight "+stage);
        }
        for(int defect=0;defect<6;++defect) {
            RelicOfferRecorder.SaveData saved=checkpoint();saved.floor=25;saved.combatAct=defect==3?1:2;
            saved.combatEntries=new ArrayList<>(Arrays.asList(combat(25,"FIXED_EVENT","COLOSSEUM_EVENT_SLAVERS"),
                    combat(25,"FIXED_EVENT","COLOSSEUM_EVENT_NOBS")));
            if(defect==0)Collections.reverse(saved.combatEntries);
            if(defect==1)saved.combatEntries.get(0).put("encounter","MUSHROOMS_EVENT");
            if(defect==2)saved.combatEntries.get(1).put("kind","ELITE_QUEUE");
            if(defect==4)saved.combatEntries.add(combat(25,"FIXED_EVENT","COLOSSEUM_EVENT_NOBS"));
            if(defect==5)saved.combatEntries.remove(0);
            List<Integer> metrics=new ArrayList<>(Collections.nCopies(saved.combatEntries.size(),25));
            new RelicOfferRecorder().onLoadRaw(JSON.toJsonTree(saved));
            RelicOfferRecorder.restorePending(PLAYER,12345,25,"IRONCLAD",0,saved.combatAct,metrics);
            require(!LiveOocCapture.combatClassHistory.complete(),"malformed same-floor history accepted "+defect);
        }
        for(String owner:Arrays.asList("OtherEvent",null)) {
            history=new LiveOocCapture.CombatClassHistory();
            history.observe(PLAYER,12345,2,25,true,true,new Object(),"FIXED_EVENT","COLOSSEUM_EVENT_SLAVERS",owner);
            history.observe(PLAYER,12345,2,25,false,true,new Object(),"FIXED_EVENT","COLOSSEUM_EVENT_NOBS",owner);
            require(!history.complete(),"unverified event source qualified Colosseum sequence");
        }
    }
    public static void main(String[] args) {
        colosseumCheckpoints();
        load(checkpoint());
        require(LiveOocCapture.seenRelicOffers.complete()
                && LiveOocCapture.seenRelicOffers.snapshot().equals(Arrays.asList("Anchor","Vajra")),
                "JSON roundtrip must restore exact observed offers");
        require(LiveOocCapture.combatClassHistory.completeFor(Arrays.asList(3,5,8)),
                "matching saved combat ledger must restore");
        RelicOfferRecorder.observeRoom(new Object(),8,true);
        require(!RelicOfferRecorder.projectionComplete() && LiveOocCapture.seenRelicOffers.complete(),
                "same-floor hidden shop must block projection while retaining repairable ledger");
        RelicOfferRecorder.shopRevealed(8);
        require(RelicOfferRecorder.projectionComplete(),"revealing current shop repairs temporary public gap");
        RelicOfferRecorder.observeRoom(new Object(),9,true);
        RelicOfferRecorder.observeRoom(new Object(),10,false);
        require(!RelicOfferRecorder.projectionComplete() && !LiveOocCapture.seenRelicOffers.complete(),
                "leaving an unseen shop permanently invalidates offer completeness");
        RelicOfferRecorder.SaveData revealed=checkpoint();revealed.currentShopRevealed=true;load(revealed);
        RelicOfferRecorder.observeRoom(new Object(),8,true);
        require(RelicOfferRecorder.projectionComplete(),"reload of an already revealed shop preserves public completeness");
        load(checkpoint());
        RelicOfferRecorder.observeRoom(new Object(),8,true);
        require(!RelicOfferRecorder.projectionComplete(),"reload of an unseen shop retains its public gap");
        load(checkpoint());
        LiveOocCapture.combatClassHistory.observe(PLAYER,12345,1,8,false,true,new Object(),"ELITE_QUEUE","GREMLIN_NOB");
        require(LiveOocCapture.combatClassHistory.completeFor(Arrays.asList(3,5,8)),
                "reload during same fight must not duplicate current floor");
        LiveOocCapture.seenRelicOffers.add("Anchor");
        LiveOocCapture.seenRelicOffers.add("Lantern");
        require(LiveOocCapture.seenRelicOffers.snapshot().equals(Arrays.asList("Anchor","Vajra","Lantern")),
                "later observed offers append without duplicates");
        load(checkpoint());
        require(!LiveOocCapture.seenRelicOffers.snapshot().contains("Lantern"),
                "checkpoint rollback must discard offers from abandoned future");
        for (int mismatch=0; mismatch<5; ++mismatch) {
            load(checkpoint(), mismatch==0 ? 54321 : 12345, mismatch==1 ? 7 : mismatch==2 ? 9 : 8,
                    mismatch==3 ? "THE_SILENT" : "IRONCLAD", mismatch==4 ? 1 : 0, Arrays.asList(3,5,8));
            require(!LiveOocCapture.seenRelicOffers.complete()
                    && !LiveOocCapture.combatClassHistory.complete(), "identity mismatch qualified save " + mismatch);
        }
        load(null);
        require(!LiveOocCapture.seenRelicOffers.complete() && LiveOocCapture.seenRelicOffers.snapshot().isEmpty(),
                "old save without history must remain incomplete");
        LiveOocCapture.seenRelicOffers.observe(PLAYER,12345,8,false,"",Collections.emptyMap());
        require(!LiveOocCapture.seenRelicOffers.complete(), "observation must not promote missing legacy history");
        RelicOfferRecorder.SaveData old = checkpoint(); old.combatEntries=null;old.combatComplete=null;old.combatAct=null;
        load(old);
        require(LiveOocCapture.seenRelicOffers.complete() && !LiveOocCapture.combatClassHistory.complete(),
                "legacy offer checkpoint cannot invent missing combat history");
        RelicOfferRecorder.SaveData incomplete = checkpoint(); incomplete.complete=false; incomplete.combatComplete=false;
        load(incomplete);
        require(!LiveOocCapture.seenRelicOffers.complete() && !LiveOocCapture.combatClassHistory.complete(),
                "incomplete save must remain incomplete after reload");
        for (String missing : Arrays.asList("version","seed","floor","character","ascension","offers","complete","currentShopRevealed")) {
            JsonObject raw=JSON.toJsonTree(checkpoint()).getAsJsonObject();raw.remove(missing);rejected(raw,"missing "+missing);
        }
        JsonObject raw=JSON.toJsonTree(checkpoint()).getAsJsonObject();raw.addProperty("version",2);rejected(raw,"unknown version");
        raw=JSON.toJsonTree(checkpoint()).getAsJsonObject();raw.addProperty("floor",8.5);rejected(raw,"fractional floor");
        raw=JSON.toJsonTree(checkpoint()).getAsJsonObject();raw.addProperty("seed","12345");rejected(raw,"string seed");
        raw=JSON.toJsonTree(checkpoint()).getAsJsonObject();raw.addProperty("complete","true");rejected(raw,"string boolean");
        raw=JSON.toJsonTree(checkpoint()).getAsJsonObject();raw.addProperty("combatAct","1");rejected(raw,"string combat act");
        raw=JSON.toJsonTree(checkpoint()).getAsJsonObject();raw.addProperty("combatAct",1.9);rejected(raw,"fractional combat act");
        raw=JSON.toJsonTree(checkpoint()).getAsJsonObject();raw.addProperty("combatComplete","true");rejected(raw,"string combat completeness");
        raw=JSON.toJsonTree(checkpoint()).getAsJsonObject();raw.remove("combatEntries");rejected(raw,"partial combat checkpoint");
        for (List<String> offers : Arrays.asList(Arrays.asList("Anchor","Anchor"),Arrays.asList("Anchor",null),
                Arrays.asList(""),new ArrayList<>(Collections.nCopies(182,"Anchor")))) {
            RelicOfferRecorder.SaveData invalid=checkpoint();invalid.offers=offers;load(invalid);
            require(!LiveOocCapture.seenRelicOffers.complete() && LiveOocCapture.seenRelicOffers.snapshot().isEmpty(),
                    "invalid offer list qualified history");
        }
        for(int invalid=0; invalid<7; ++invalid) {
            RelicOfferRecorder.SaveData data=checkpoint();
            if(invalid==0)data.combatAct=2;
            if(invalid==1)data.combatEntries.get(0).put("kind","UNKNOWN");
            if(invalid==2)data.combatEntries.get(1).put("encounter","");
            if(invalid==3)data.combatEntries.get(2).put("floor",9);
            if(invalid==4)data.combatEntries.get(1).put("floor",3);
            if(invalid==5)data.combatEntries.get(1).put("floor",5.5);
            if(invalid==6)data.combatEntries.remove(1);
            load(data);
            require(!LiveOocCapture.combatClassHistory.complete(),"invalid combat ledger accepted " + invalid);
        }
        load(checkpoint(),12345,8,"IRONCLAD",0,Arrays.asList(3,5));
        require(LiveOocCapture.combatClassHistory.complete(),"pending current combat may precede damage metric");
        load(checkpoint(),12345,8,"IRONCLAD",0,Arrays.asList(3,6));
        require(!LiveOocCapture.combatClassHistory.complete(),"contradictory public metric accepted");
        load(checkpoint());
        new RelicOfferRecorder().receivePreStartGame();
        LiveOocCapture.seenRelicOffers.observe(PLAYER,12345,0,true,"",Collections.emptyMap());
        LiveOocCapture.combatClassHistory.resetForFreshRun(PLAYER,12345,1);
        require(LiveOocCapture.seenRelicOffers.complete() && LiveOocCapture.seenRelicOffers.snapshot().isEmpty()
                && LiveOocCapture.combatClassHistory.completeFor(Collections.emptyList()),
                "fresh same-seed run must not inherit the prior save");
        System.out.println("RelicOfferRecorderTest: JSON roundtrip, identity, schema, rollback, legacy, combat and fresh-run checks passed");
    }
}
