package stsmodelinspector;

import java.util.*;

public final class RunicDomeTrackerTest {
    private static void complete(Map<String,Object> snapshot) {
        if(!Boolean.TRUE.equals(snapshot.get("complete"))) throw new AssertionError(snapshot);
    }
    private static void rejected(Map<String,Object> snapshot) {
        if(!Boolean.FALSE.equals(snapshot.get("complete"))) throw new AssertionError("unproven Dome accepted: "+snapshot);
    }
    public static void main(String[] args) throws Exception {
        Object monster=new Object();
        for(String id:Arrays.asList("JawWorm","Cultist")) {
            RunicDomeTracker a=new RunicDomeTracker(monster,id,1,1,1);
            RunicDomeTracker b=new RunicDomeTracker(monster,id,1,1,1);
            for(RunicDomeTracker tracker:Arrays.asList(a,b)) {
                tracker.beginRoll(monster,42,42); tracker.setMove(monster); tracker.endRoll(monster);
            }
            Map<String,Object> first=a.snapshot(monster,1); complete(first);
            // No API accepts a private roll result, history, damage, or RNG.
            // Different unexecuted realizations cannot change the projection.
            if(!first.equals(b.snapshot(monster,1)) || first.containsKey("nextMove") || first.containsKey("miscInfo"))
                throw new AssertionError("hidden result leaked");
            a.execute(monster,id.equals("JawWorm")?1:3);
            a.beginRoll(monster,30,42); a.setMove(monster); a.endRoll(monster);
            Map<String,Object> second=a.snapshot(monster,2); complete(second);
            if(!second.get("completedTurns").equals(1) || !second.get("generation").equals(3L)
                    || !second.get("rollHp").equals(30) || second.equals(first)) throw new AssertionError("executed public history lost");
            a.execute(monster,id.equals("JawWorm")?2:1);
            a.beginRoll(monster,20,42); a.setMove(monster); a.endRoll(monster);
            complete(a.snapshot(monster,3));
            a.execute(monster,id.equals("JawWorm")?3:1);
            a.beginRoll(monster,18,42); a.setMove(monster); a.endRoll(monster);
            Map<String,Object> fourth=a.snapshot(monster,4); complete(fourth);
            if(!fourth.get("executedMoves").equals(Arrays.asList(id.equals("JawWorm")?2:1,id.equals("JawWorm")?3:1)))
                throw new AssertionError("executed history order");
        }
        RunicDomeTracker t=new RunicDomeTracker(monster,"JawWorm",1,1,1);
        rejected(t.snapshot(monster,1)); // never rolled / hot attachment
        t=new RunicDomeTracker(monster,"JawWorm",1,1,1); t.beginRoll(monster,42,42);
        rejected(t.snapshot(monster,1)); // hook exception / unresolved scope
        t.endRoll(monster); t.beginRoll(monster,42,42); rejected(t.snapshot(monster,1)); // hidden reroll
        t=new RunicDomeTracker(monster,"JawWorm",1,1,1); t.setMove(monster); rejected(t.snapshot(monster,1));
        t=new RunicDomeTracker(monster,"JawWorm",1,1,1); t.beginRoll(monster,42,42);t.endRoll(monster);
        rejected(t.snapshot(new Object(),1)); // spawn/replacement cannot inherit history
        t=new RunicDomeTracker(monster,"JawWorm",1,1,1);t.beginRoll(monster,42,42);t.endRoll(monster);
        rejected(t.snapshot(monster,2)); // missing public turn hook
        for(String id:Arrays.asList("BookOfStabbing","Looter","WrithingMass"))
            rejected(new RunicDomeTracker(monster,id,1,1,1).snapshot(monster,1));
        rejected(new RunicDomeTracker(monster,"JawWorm",1,3,1).snapshot(monster,1));
        rejected(new RunicDomeTracker(monster,"JawWorm",1,1,6).snapshot(monster,1));
        // Every audited concrete takeTurn has one trailing RollMoveAction.
        for(String id:Arrays.asList("FungiBeast","SlaverBlue","SlaverRed","AcidSlime_M","SpikeSlime_M","GremlinNob")) {
            RunicDomeTracker multi=new RunicDomeTracker(monster,id,7,1,2);
            multi.beginRoll(monster,35,35,44,44,true,2);multi.endRoll(monster);
            complete(multi.snapshot(monster,1,1,false));
            multi.execute(monster,"GremlinNob".equals(id)?3:1);
            multi.beginRoll(monster,30,35,0,44,false,1);multi.endRoll(monster);
            Map<String,Object> state=multi.snapshot(monster,2,1,false);complete(state);
            if(!state.get("slot").equals(1) || !state.get("firstHp").equals(0)
                    || !state.get("aliveCount").equals(1)) throw new AssertionError("roll group inputs lost");
            Map<String,Object> corpse=multi.snapshot(monster,3,1,true);complete(corpse);
            if(!corpse.get("pendingMoveRolls").equals(0)) throw new AssertionError("dead slot retained private move");
        }
        for(int slot=0;slot<3;++slot) {
            RunicDomeTracker sentry=new RunicDomeTracker(monster,"Sentry",11,1,3);
            for(int completed=0;completed<4;++completed) {
                sentry.beginRoll(monster,35,40,35,40,true,3);sentry.endRoll(monster);
                complete(sentry.snapshot(monster,completed+1,slot,false));
                sentry.execute(monster,(slot+completed)%2==0?3:4);
            }
        }
        RunicDomeTracker spike=new RunicDomeTracker(monster,"SpikeSlime_S",12,1,5);
        spike.beginRoll(monster,10,10);spike.endRoll(monster);spike.execute(monster,1);
        spike.beginRoll(monster,8,10);spike.endRoll(monster);complete(spike.snapshot(monster,2,4,false));
        RunicDomeTracker red=new RunicDomeTracker(monster,"SlaverRed",9,1,2);
        int turn=1;
        red.beginRoll(monster,40,40);red.endRoll(monster);
        for(int move:new int[]{1,2,3,1,3}) {
            red.execute(monster,move);red.beginRoll(monster,30,40);red.endRoll(monster);++turn;
        }
        Map<String,Object> redState=red.snapshot(monster,turn);complete(redState);
        if(!redState.get("publicMisc").equals(1) || !redState.get("executedMoves").equals(Arrays.asList(1,3)))
            throw new AssertionError("public Entangle lost after history rolled over");
        red.execute(monster,2);rejected(red.snapshot(monster,turn+1));
        if(!RunicDomeTracker.cardAllowed("Spot Weakness") || RunicDomeTracker.cardAllowed("Discovery")
                || RunicDomeTracker.relicAllowed("Dead Branch") || RunicDomeTracker.relicAllowed("Nilry's Codex")
                || RunicDomeTracker.potionAllowed("SkillPotion") || RunicDomeTracker.potionAllowed("EntropicBrew"))
            throw new AssertionError("intent-query/generator domain accepted");
        for(String power:Arrays.asList("Magnetism","Mayhem","Creative AI","Hello World","Discovery"))
            if(RunicDomeTracker.playerPowerAllowed(power)) throw new AssertionError("consumed potion generator power accepted");
        if(RunicDomeTracker.monsterPowerAllowed("Ritual","JawWorm")
                || RunicDomeTracker.monsterPowerAllowed("Compulsive","JawWorm"))
            throw new AssertionError("unaudited monster power accepted");
        for(boolean attacking:new boolean[]{false,true}) {
            RunicDomeTracker predicate=new RunicDomeTracker(monster,"JawWorm",1,1,1);
            predicate.beginRoll(monster,40,40);predicate.endRoll(monster);
            predicate.observeAttack(monster,attacking);predicate.observeAttack(monster,attacking);
            Map<String,Object> state=predicate.snapshot(monster,1);complete(state);
            if(!state.get("pendingAttackPredicates").equals(Arrays.asList(Arrays.asList(1,attacking))))
                throw new AssertionError("public Spot result missing");
            predicate.execute(monster,1);predicate.beginRoll(monster,30,40);predicate.endRoll(monster);
            if(!predicate.snapshot(monster,2).get("pendingAttackPredicates").equals(Collections.emptyList())) throw new AssertionError("stale predicate reused");
            predicate.observeAttack(monster,attacking);predicate.observeAttack(monster,!attacking);
            rejected(predicate.snapshot(monster,2));
        }
        javassist.ClassPool pool=new javassist.ClassPool(true);
        pool.appendClassPath(new javassist.LoaderClassPath(RunicDomeTrackerTest.class.getClassLoader()));
        javassist.CtClass action=pool.get("com.megacrit.cardcrawl.actions.unique.SpotWeaknessAction");
        RunicDomeTrackerPatch.SpotResult.raw(action.getDeclaredMethod("update"));
        if(action.toBytecode().length==0) throw new AssertionError("Spot instrumentation missing");
        action.detach();
        if(!RunicDomeTracker.cardAllowed("Strike_R") || !RunicDomeTracker.relicAllowed("Runic Dome"))
            throw new AssertionError("audited domain rejected");
        // Hook signatures are verified against the installed JAR without
        // initializing game graphics. Pure lifecycle tests cannot prove hook
        // delivery; installed-mod smoke remains separate evidence.
        ClassLoader loader=RunicDomeTrackerTest.class.getClassLoader();
        Class<?> base=Class.forName("com.megacrit.cardcrawl.monsters.AbstractMonster",false,loader);
        base.getDeclaredMethod("rollMove");
        Class<?> intent=Class.forName("com.megacrit.cardcrawl.monsters.AbstractMonster$Intent",false,loader);
        base.getDeclaredMethod("setMove",String.class,byte.class,intent,int.class,int.class,boolean.class);
        for(String cls:Arrays.asList("JawWorm","Cultist","FungiBeast","SlaverBlue","SlaverRed","AcidSlime_M","SpikeSlime_M","SpikeSlime_S","Sentry","GremlinNob"))
            Class.forName("com.megacrit.cardcrawl.monsters.exordium."+cls,false,loader).getDeclaredMethod("takeTurn");
        Class.forName("com.megacrit.cardcrawl.monsters.MonsterGroup",false,loader).getDeclaredMethod("init");
        System.out.println("RunicDomeTrackerTest PASS");
    }
}
