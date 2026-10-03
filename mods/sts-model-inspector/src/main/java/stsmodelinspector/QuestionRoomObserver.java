package stsmodelinspector;

import com.evacipated.cardcrawl.modthespire.lib.SpirePatch;
import com.evacipated.cardcrawl.modthespire.lib.SpireRawPatch;
import com.megacrit.cardcrawl.core.Settings;
import com.megacrit.cardcrawl.dungeons.AbstractDungeon;
import com.megacrit.cardcrawl.helpers.EventHelper;
import com.megacrit.cardcrawl.random.Random;
import com.megacrit.cardcrawl.relics.AbstractRelic;
import com.megacrit.cardcrawl.saveAndContinue.SaveFile;
import javassist.CannotCompileException;
import javassist.CtBehavior;
import javassist.expr.ExprEditor;
import javassist.expr.MethodCall;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

/** Observes Juzu's public flash; never inspects a rolled value or room-chance field. */
public final class QuestionRoomObserver {
    static final Ledger ledger=new Ledger();
    private static Frame frame;
    private static boolean captureFailed;
    private QuestionRoomObserver() {}
    static void clear() { ledger.clear();frame=null;captureFailed=false; }
    static void annotate(Object player,long seed,int floor,List<Map<String,Object>> outcomes) {
        if(captureFailed)throw new IllegalArgumentException("public question observer failed");
        ledger.annotate(player,seed,floor,outcomes);
    }
    static final class Frame {
        boolean enabled, rolling, flashed, owned;
        int rolls, floor;
        Object player;
        long seed;
    }
    static final class Ledger {
        private Object player;
        private long seed;
        private int lastFloor=-1;
        private final TreeMap<Integer,Map<String,Object>> entries=new TreeMap<>();
        void clear() { player=null;seed=0;lastFloor=-1;entries.clear(); }
        void record(Object currentPlayer,long currentSeed,int floor,String outcome,boolean owned,boolean converted) {
            if(player!=currentPlayer || seed!=currentSeed || floor<lastFloor) {
                clear();player=currentPlayer;seed=currentSeed;
            }
            if(floor<1 || floor>51 || !Arrays.asList("MONSTER","SHOP","TREASURE","EVENT").contains(outcome)
                    || (owned && "MONSTER".equals(outcome))
                    || (converted && (!owned || !"EVENT".equals(outcome))))
                throw new IllegalArgumentException("invalid public question transition");
            Map<String,Object> value=new LinkedHashMap<>();
            value.put("floor",floor);value.put("outcome",outcome);
            value.put("juzuOwnedAtEntry",owned);value.put("juzuConverted",converted);
            Map<String,Object> previous=entries.get(floor);
            if(previous!=null && !previous.equals(value))
                throw new IllegalArgumentException("conflicting public question transition");
            entries.put(floor,value);lastFloor=floor;
        }
        List<Map<String,Object>> snapshot() {
            List<Map<String,Object>> copy=new ArrayList<>();
            for(Map<String,Object> entry:entries.values())copy.add(new LinkedHashMap<>(entry));
            return copy;
        }
        boolean restore(Object currentPlayer,long currentSeed,int floor,List<Map<String,Object>> values) {
            clear();
            if(values==null || values.size()>51)return false;
            int previous=0;
            try {
                for(Map<String,Object> value:values) {
                    Integer f=value==null?null:PublicHistoryRecovery.floor(value.get("floor"),floor);
                    if(f==null || f<=previous || !(value.get("outcome") instanceof String)
                            || !(value.get("juzuOwnedAtEntry") instanceof Boolean)
                            || !(value.get("juzuConverted") instanceof Boolean))throw new IllegalArgumentException();
                    record(currentPlayer,currentSeed,f,(String)value.get("outcome"),
                            (Boolean)value.get("juzuOwnedAtEntry"),(Boolean)value.get("juzuConverted"));
                    previous=f;
                }
                player=currentPlayer;seed=currentSeed;lastFloor=floor;return true;
            } catch(IllegalArgumentException invalid) { clear();return false; }
        }
        void annotate(Object currentPlayer,long currentSeed,int floor,List<Map<String,Object>> outcomes) {
            if(player!=currentPlayer || seed!=currentSeed || floor<lastFloor)return;
            for(Map<String,Object> outcome:outcomes) {
                Map<String,Object> saved=entries.get(((Number)outcome.get("floor")).intValue());
                if(saved==null)continue;
                if(!saved.get("outcome").equals(outcome.get("outcome"))
                        || (outcome.containsKey("juzuOwnedAtEntry")
                            && !saved.get("juzuOwnedAtEntry").equals(outcome.get("juzuOwnedAtEntry"))))
                    throw new IllegalArgumentException("question checkpoint contradicts public metrics");
                outcome.put("juzuOwnedAtEntry",saved.get("juzuOwnedAtEntry"));
                outcome.put("juzuConverted",saved.get("juzuConverted"));
            }
        }
    }
    public static void beginTransition(boolean loading) {
        frame=new Frame();
        frame.enabled=!loading && !Settings.isDailyRun && !Settings.isEndless;
    }
    public static void endTransition() { frame=null; }
    public static void beginRoll() {
        if(frame==null || !frame.enabled)return;
        if(AbstractDungeon.player==null || Settings.seed==null || ++frame.rolls!=1) {
            frame.enabled=false;return;
        }
        try { RelicOfferRecorder.bind(); }
        catch(RuntimeException failure) { frame.enabled=false;captureFailed=true;return; }
        frame.player=AbstractDungeon.player;frame.seed=Settings.seed;frame.floor=AbstractDungeon.floorNum;
        frame.owned=AbstractDungeon.player.hasRelic("Juzu Bracelet");frame.rolling=true;
    }
    public static void endRoll() { if(frame!=null)frame.rolling=false; }
    public static void publicFlash(AbstractRelic relic) {
        if(frame!=null && frame.enabled && frame.rolling && "Juzu Bracelet".equals(relic.relicId))
            frame.flashed=true;
    }
    public static void commitTransition() {
        if(frame==null || !frame.enabled || frame.rolling || frame.rolls!=1
                || frame.player!=AbstractDungeon.player || frame.floor!=AbstractDungeon.floorNum
                || AbstractDungeon.getCurrRoom()==null)return;
        String outcome=QuestionRoomHistory.roomOutcome(AbstractDungeon.getCurrRoom().getClass().getSimpleName());
        try { ledger.record(frame.player,frame.seed,frame.floor,outcome,frame.owned,frame.flashed); }
        catch(RuntimeException failure) { captureFailed=true; }
        frame.enabled=false;
    }

    @SpirePatch(clz=AbstractDungeon.class,method="nextRoomTransition",paramtypez={SaveFile.class})
    public static class TransitionPatch {
        @SpireRawPatch public static void raw(CtBehavior method) throws CannotCompileException {
            final int[] sites={0,0};
            method.instrument(new ExprEditor() {
                @Override public void edit(MethodCall call) throws CannotCompileException {
                    if(call.getClassName().equals(EventHelper.class.getName()) && call.getMethodName().equals("roll")) {
                        ++sites[0];
                        call.replace("{ stsmodelinspector.QuestionRoomObserver.beginRoll(); "
                                + "try { $_ = $proceed($$); } finally { stsmodelinspector.QuestionRoomObserver.endRoll(); } }");
                    } else if(call.getClassName().equals(AbstractDungeon.class.getName())
                            && call.getMethodName().equals("setCurrMapNode")) {
                        ++sites[1];call.replace("{ $proceed($$); stsmodelinspector.QuestionRoomObserver.commitTransition(); }");
                    }
                }
            });
            if(sites[0]!=1 || sites[1]!=1)throw new CannotCompileException("unqualified question transition hook sites");
            method.insertBefore("{ stsmodelinspector.QuestionRoomObserver.beginTransition($1 != null); }");
            method.insertAfter("{ stsmodelinspector.QuestionRoomObserver.endTransition(); }",true);
        }
    }
    @SpirePatch(clz=EventHelper.class,method="roll",paramtypez={Random.class})
    public static class FlashPatch {
        @SpireRawPatch public static void raw(CtBehavior method) throws CannotCompileException {
            final int[] sites={0};
            method.instrument(new ExprEditor() {
                @Override public void edit(MethodCall call) throws CannotCompileException {
                    if(call.getClassName().equals(AbstractRelic.class.getName()) && call.getMethodName().equals("flash")) {
                        ++sites[0];call.replace("{ $proceed($$); stsmodelinspector.QuestionRoomObserver.publicFlash($0); }");
                    }
                }
            });
            // Tiny Chest, ordinary Juzu, and Endless Mimic Juzu. The observer
            // itself is disabled for Endless/Daily runs.
            if(sites[0]!=3)throw new CannotCompileException("unqualified question public flash sites");
        }
    }
}
