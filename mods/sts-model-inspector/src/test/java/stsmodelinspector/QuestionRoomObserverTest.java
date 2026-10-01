package stsmodelinspector;

import com.google.gson.Gson;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import javassist.ClassPool;
import javassist.CtClass;
import javassist.CtMethod;
import javassist.expr.ExprEditor;
import javassist.expr.MethodCall;

public final class QuestionRoomObserverTest {
    private static Map<String,Object> outcome(int floor,String name) {
        Map<String,Object> value=new LinkedHashMap<>();value.put("floor",floor);value.put("outcome",name);return value;
    }
    private static void require(boolean ok,String why) { if(!ok)throw new AssertionError(why); }
    private static void realHookSites() throws Exception {
        // Apply the actual raw patches to the installed vanilla bytecode,
        // without initializing any game class or driving a game seed.
        ClassPool pool=new ClassPool(true);
        pool.appendPathList(System.getProperty("java.class.path"));
        CtClass dungeon=pool.get("com.megacrit.cardcrawl.dungeons.AbstractDungeon");
        CtMethod transition=dungeon.getDeclaredMethod("nextRoomTransition",
                new CtClass[]{pool.get("com.megacrit.cardcrawl.saveAndContinue.SaveFile")});
        QuestionRoomObserver.TransitionPatch.raw(transition);
        final Map<String,Integer> calls=new LinkedHashMap<>();
        transition.instrument(new ExprEditor() {
            @Override public void edit(MethodCall call) {
                if(call.getClassName().equals(QuestionRoomObserver.class.getName()))
                    calls.put(call.getMethodName(),calls.getOrDefault(call.getMethodName(),0)+1);
            }
        });
        require(calls.getOrDefault("beginTransition",0)==1 && calls.getOrDefault("beginRoll",0)==1
                && calls.getOrDefault("commitTransition",0)==1
                && calls.getOrDefault("endRoll",0)>=1 && calls.getOrDefault("endTransition",0)>=1,
                "actual transition hook coverage");
        require(dungeon.toBytecode().length>0,"patched transition bytecode");
        CtClass helper=pool.get("com.megacrit.cardcrawl.helpers.EventHelper");
        CtMethod roll=helper.getDeclaredMethod("roll",new CtClass[]{pool.get("com.megacrit.cardcrawl.random.Random")});
        QuestionRoomObserver.FlashPatch.raw(roll);
        final int[] flashes={0};
        roll.instrument(new ExprEditor() {
            @Override public void edit(MethodCall call) {
                if(call.getClassName().equals(QuestionRoomObserver.class.getName())
                        && call.getMethodName().equals("publicFlash"))++flashes[0];
            }
        });
        require(flashes[0]==3 && helper.toBytecode().length>0,"actual public flash hook coverage");
    }
    public static void main(String[] args) throws Exception {
        realHookSites();
        Object player=new Object();
        QuestionRoomObserver.Ledger ledger=new QuestionRoomObserver.Ledger();
        ledger.record(player,12,2,"EVENT",true,true);
        ledger.record(player,12,4,"EVENT",true,false);
        ledger.record(player,12,4,"EVENT",true,false);
        require(ledger.snapshot().size()==2,"duplicate accepted transition added twice");
        List<Map<String,Object>> outcomes=new ArrayList<>(Arrays.asList(outcome(2,"EVENT"),outcome(3,"EVENT"),outcome(4,"EVENT")));
        ledger.annotate(player,12,4,outcomes);
        require(Boolean.TRUE.equals(outcomes.get(0).get("juzuConverted"))
                && !outcomes.get(1).containsKey("juzuConverted")
                && Boolean.FALSE.equals(outcomes.get(2).get("juzuConverted")),"missing observation became false");
        List<Map<String,Object>> detached=Arrays.asList(outcome(2,"EVENT"));
        ledger.annotate(new Object(),12,4,detached);
        require(!detached.get(0).containsKey("juzuConverted"),"different player inherited observations");
        boolean conflict=false;
        try { ledger.record(player,12,4,"EVENT",true,true); } catch(IllegalArgumentException expected){conflict=true;}
        require(conflict,"conflicting repeat transition accepted");
        conflict=false;
        try { ledger.annotate(player,12,4,Arrays.asList(outcome(2,"SHOP"))); }
        catch(IllegalArgumentException expected){conflict=true;}
        require(conflict,"saved observer contradicted room metrics");
        RelicOfferRecorder.SaveData save=new RelicOfferRecorder.SaveData();
        save.version=1;save.seed=12L;save.floor=4;save.character="IRONCLAD";save.ascension=0;
        save.complete=false;save.currentShopRevealed=false;save.offers=new ArrayList<>();
        save.questionVersion=1;save.questionEntries=ledger.snapshot();
        RelicOfferRecorder.SaveData decoded=RelicOfferRecorder.decodeCheckpoint(new Gson().toJsonTree(save));
        require(decoded!=null,"question JSON checkpoint");
        new RelicOfferRecorder().onLoadRaw(new Gson().toJsonTree(save));
        RelicOfferRecorder.restorePending(player,12,4,"IRONCLAD",0,1,new ArrayList<Integer>());
        List<Map<String,Object>> restored=Arrays.asList(outcome(2,"EVENT"));
        QuestionRoomObserver.annotate(player,12,4,restored);
        require(Boolean.TRUE.equals(restored.get(0).get("juzuConverted")),"saved flash provenance lost");
        for(int bad=0;bad<5;++bad) {
            save.questionEntries=ledger.snapshot();save.questionVersion=1;
            if(bad==0)save.questionVersion=2;
            if(bad==1)save.questionEntries.get(0).put("floor",2.5);
            if(bad==2)save.questionEntries.get(0).put("juzuConverted","true");
            if(bad==3)save.questionEntries.get(0).put("juzuOwnedAtEntry",false);
            if(bad==4)save.questionEntries.get(0).put("outcome","TREASURE");
            require(RelicOfferRecorder.decodeCheckpoint(new Gson().toJsonTree(save))==null,"malformed question checkpoint "+bad);
        }
        require(!new QuestionRoomObserver.Ledger().restore(player,12,3,ledger.snapshot()),"future checkpoint leaked into rollback");
        System.out.println("QuestionRoomObserverTest passed (real vanilla bytecode hooks, persistence and provenance)");
    }
}
