package stsmodelinspector;

import com.evacipated.cardcrawl.modthespire.lib.*;
import com.megacrit.cardcrawl.monsters.AbstractMonster;
import com.megacrit.cardcrawl.monsters.MonsterGroup;
import com.megacrit.cardcrawl.monsters.exordium.*;
import com.megacrit.cardcrawl.monsters.exordium.JawWorm;

/** Hooks precede initial RNG and publish only actually executing audited moves. */
public final class RunicDomeTrackerPatch {
    @SpirePatch(clz=MonsterGroup.class,method="init")
    public static class GroupInit {
        @SpirePrefixPatch public static void prefix(MonsterGroup __instance) { RunicDomeCapture.begin(__instance); }
    }
    @SpirePatch(clz=AbstractMonster.class,method="rollMove")
    public static class Roll {
        @SpirePrefixPatch public static void prefix(AbstractMonster __instance) { RunicDomeCapture.beginRoll(__instance); }
        @SpirePostfixPatch public static void postfix(AbstractMonster __instance) { RunicDomeCapture.endRoll(__instance); }
    }
    @SpirePatch(clz=AbstractMonster.class,method="setMove",paramtypez={String.class,byte.class,
            AbstractMonster.Intent.class,int.class,int.class,boolean.class})
    public static class Move {
        @SpirePrefixPatch public static void prefix(AbstractMonster __instance) { RunicDomeCapture.setMove(__instance); }
    }
    @SpirePatch(clz=JawWorm.class,method="takeTurn")
    public static class JawTurn {
        @SpirePrefixPatch public static void prefix(JawWorm __instance) { RunicDomeCapture.execute(__instance); }
    }
    @SpirePatch(clz=Cultist.class,method="takeTurn")
    public static class CultistTurn {
        @SpirePrefixPatch public static void prefix(Cultist __instance) { RunicDomeCapture.execute(__instance); }
    }
    @SpirePatch(clz=FungiBeast.class,method="takeTurn")
    public static class FungiBeastTurn {
        @SpirePrefixPatch public static void prefix(FungiBeast __instance) { RunicDomeCapture.execute(__instance); }
    }
    @SpirePatch(clz=SlaverBlue.class,method="takeTurn")
    public static class SlaverBlueTurn {
        @SpirePrefixPatch public static void prefix(SlaverBlue __instance) { RunicDomeCapture.execute(__instance); }
    }
    @SpirePatch(clz=SlaverRed.class,method="takeTurn")
    public static class SlaverRedTurn {
        @SpirePrefixPatch public static void prefix(SlaverRed __instance) { RunicDomeCapture.execute(__instance); }
    }
    public static void publicAcidOverride(AbstractMonster monster,int proposed) {
        RunicDomeCapture.acidOverride(monster,proposed);
    }
    @SpirePatch(clz=AcidSlime_S.class,method="takeTurn")
    public static class AcidSlime_STurn {
        @SpirePrefixPatch public static void prefix(AcidSlime_S __instance) { RunicDomeCapture.beginAcidTurn(__instance); }
        @SpirePostfixPatch public static void postfix(AcidSlime_S __instance) { RunicDomeCapture.endAcidTurn(__instance); }
        @SpireRawPatch public static void raw(javassist.CtBehavior method) throws javassist.CannotCompileException {
            final int[] sites={0};
            method.instrument(new javassist.expr.ExprEditor() {
                @Override public void edit(javassist.expr.MethodCall call) throws javassist.CannotCompileException {
                    if(call.getClassName().equals(AcidSlime_S.class.getName()) && call.getMethodName().equals("setMove")) {
                        String signature=call.getSignature();
                        if(!signature.equals("(BLcom/megacrit/cardcrawl/monsters/AbstractMonster$Intent;)V")
                                && !signature.equals("(BLcom/megacrit/cardcrawl/monsters/AbstractMonster$Intent;I)V"))
                            throw new javassist.CannotCompileException("unqualified Acid Slime override signature");
                        ++sites[0];
                        call.replace("{ stsmodelinspector.RunicDomeTrackerPatch.publicAcidOverride($0, $1); $proceed($$); }");
                    }
                }
            });
            if(sites[0]!=2) throw new javassist.CannotCompileException("unqualified Acid Slime override sites");
        }
    }
    @SpirePatch(clz=AcidSlime_M.class,method="takeTurn")
    public static class AcidSlime_MTurn {
        @SpirePrefixPatch public static void prefix(AcidSlime_M __instance) { RunicDomeCapture.execute(__instance); }
    }
    @SpirePatch(clz=SpikeSlime_M.class,method="takeTurn")
    public static class SpikeSlime_MTurn {
        @SpirePrefixPatch public static void prefix(SpikeSlime_M __instance) { RunicDomeCapture.execute(__instance); }
    }
    @SpirePatch(clz=GremlinNob.class,method="takeTurn")
    public static class GremlinNobTurn {
        @SpirePrefixPatch public static void prefix(GremlinNob __instance) { RunicDomeCapture.execute(__instance); }
    }
    @SpirePatch(clz=SpikeSlime_S.class,method="takeTurn")
    public static class SpikeSlime_STurn {
        @SpirePrefixPatch public static void prefix(SpikeSlime_S __instance) { RunicDomeCapture.execute(__instance); }
    }
    @SpirePatch(clz=Sentry.class,method="takeTurn")
    public static class SentryTurn {
        @SpirePrefixPatch public static void prefix(Sentry __instance) { RunicDomeCapture.execute(__instance); }
    }
    public static void publicSpotResult(AbstractMonster monster,boolean attacking) {
        RunicDomeCapture.observeAttack(monster,attacking);
    }
    @SpirePatch(clz=com.megacrit.cardcrawl.actions.unique.SpotWeaknessAction.class,method="update")
    public static class SpotResult {
        @SpireRawPatch public static void raw(javassist.CtBehavior method) throws javassist.CannotCompileException {
            final int[] sites={0};
            method.instrument(new javassist.expr.ExprEditor() {
                @Override public void edit(javassist.expr.MethodCall call) throws javassist.CannotCompileException {
                    if(call.getClassName().equals(AbstractMonster.class.getName()) && call.getMethodName().equals("getIntentBaseDmg")) {
                        ++sites[0];
                        call.replace("{ $_ = $proceed($$); stsmodelinspector.RunicDomeTrackerPatch.publicSpotResult($0, $_ >= 0); }");
                    }
                }
            });
            if(sites[0]!=1) throw new javassist.CannotCompileException("unqualified Spot Weakness predicate hook");
        }
    }
}
