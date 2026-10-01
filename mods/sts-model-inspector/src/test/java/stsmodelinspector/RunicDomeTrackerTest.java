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
        rejected(new RunicDomeTracker(monster,"JawWorm",1,1,3).snapshot(monster,1));
        if(RunicDomeTracker.cardAllowed("Spot Weakness") || RunicDomeTracker.cardAllowed("Discovery")
                || RunicDomeTracker.relicAllowed("Dead Branch") || RunicDomeTracker.relicAllowed("Nilry's Codex")
                || RunicDomeTracker.potionAllowed("SkillPotion") || RunicDomeTracker.potionAllowed("EntropicBrew"))
            throw new AssertionError("intent-query/generator domain accepted");
        for(String power:Arrays.asList("Magnetism","Mayhem","Creative AI","Hello World","Discovery"))
            if(RunicDomeTracker.playerPowerAllowed(power)) throw new AssertionError("consumed potion generator power accepted");
        if(RunicDomeTracker.monsterPowerAllowed("Ritual","JawWorm")
                || RunicDomeTracker.monsterPowerAllowed("Compulsive","JawWorm"))
            throw new AssertionError("unaudited monster power accepted");
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
        for(String cls:Arrays.asList("JawWorm","Cultist"))
            Class.forName("com.megacrit.cardcrawl.monsters.exordium."+cls,false,loader).getDeclaredMethod("takeTurn");
        Class.forName("com.megacrit.cardcrawl.monsters.MonsterGroup",false,loader).getDeclaredMethod("init");
        System.out.println("RunicDomeTrackerTest PASS");
    }
}
