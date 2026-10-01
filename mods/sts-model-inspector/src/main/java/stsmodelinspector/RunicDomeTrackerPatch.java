package stsmodelinspector;

import com.evacipated.cardcrawl.modthespire.lib.*;
import com.megacrit.cardcrawl.monsters.AbstractMonster;
import com.megacrit.cardcrawl.monsters.MonsterGroup;
import com.megacrit.cardcrawl.monsters.exordium.*;
import com.megacrit.cardcrawl.monsters.city.*;
import com.megacrit.cardcrawl.monsters.beyond.*;

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
    @SpirePatch(clz=Centurion.class,method="takeTurn")
    public static class CenturionTurn {
        @SpirePrefixPatch public static void prefix(Centurion __instance) { RunicDomeCapture.execute(__instance); }
    }
    @SpirePatch(clz=Healer.class,method="takeTurn")
    public static class HealerTurn {
        @SpirePrefixPatch public static void prefix(Healer __instance) { RunicDomeCapture.execute(__instance); }
    }
    @SpirePatch(clz=Chosen.class,method="takeTurn")
    public static class ChosenTurn {
        @SpirePrefixPatch public static void prefix(Chosen __instance) { RunicDomeCapture.execute(__instance); }
    }
    @SpirePatch(clz=SnakePlant.class,method="takeTurn")
    public static class SnakePlantTurn {
        @SpirePrefixPatch public static void prefix(SnakePlant __instance) { RunicDomeCapture.execute(__instance); }
    }
    @SpirePatch(clz=Snecko.class,method="takeTurn")
    public static class SneckoTurn {
        @SpirePrefixPatch public static void prefix(Snecko __instance) { RunicDomeCapture.execute(__instance); }
    }
    @SpirePatch(clz=SphericGuardian.class,method="takeTurn")
    public static class SphericGuardianTurn {
        @SpirePrefixPatch public static void prefix(SphericGuardian __instance) { RunicDomeCapture.execute(__instance); }
    }
    @SpirePatch(clz=Exploder.class,method="takeTurn")
    public static class ExploderTurn {
        @SpirePrefixPatch public static void prefix(Exploder __instance) { RunicDomeCapture.execute(__instance); }
    }
    @SpirePatch(clz=Repulsor.class,method="takeTurn")
    public static class RepulsorTurn {
        @SpirePrefixPatch public static void prefix(Repulsor __instance) { RunicDomeCapture.execute(__instance); }
    }
    @SpirePatch(clz=Maw.class,method="takeTurn")
    public static class MawTurn {
        @SpirePrefixPatch public static void prefix(Maw __instance) { RunicDomeCapture.execute(__instance); }
    }
    @SpirePatch(clz=Nemesis.class,method="takeTurn")
    public static class NemesisTurn {
        @SpirePrefixPatch public static void prefix(Nemesis __instance) { RunicDomeCapture.execute(__instance); }
    }
    @SpirePatch(clz=OrbWalker.class,method="takeTurn")
    public static class OrbWalkerTurn {
        @SpirePrefixPatch public static void prefix(OrbWalker __instance) { RunicDomeCapture.execute(__instance); }
    }
    @SpirePatch(clz=GiantHead.class,method="takeTurn")
    public static class GiantHeadTurn {
        @SpirePrefixPatch public static void prefix(GiantHead __instance) { RunicDomeCapture.execute(__instance); }
    }
    @SpirePatch(clz=Donu.class,method="takeTurn")
    public static class DonuTurn {
        @SpirePrefixPatch public static void prefix(Donu __instance) { RunicDomeCapture.execute(__instance); }
    }
    @SpirePatch(clz=Deca.class,method="takeTurn")
    public static class DecaTurn {
        @SpirePrefixPatch public static void prefix(Deca __instance) { RunicDomeCapture.execute(__instance); }
    }
    @SpirePatch(clz=Spiker.class,method="takeTurn")
    public static class SpikerTurn {
        @SpirePrefixPatch public static void prefix(Spiker __instance) { RunicDomeCapture.execute(__instance); }
    }
    @SpirePatch(clz=SpireGrowth.class,method="takeTurn")
    public static class SpireGrowthTurn {
        @SpirePrefixPatch public static void prefix(SpireGrowth __instance) { RunicDomeCapture.execute(__instance); }
    }
    @SpirePatch(clz=Taskmaster.class,method="takeTurn")
    public static class TaskmasterTurn {
        @SpirePrefixPatch public static void prefix(Taskmaster __instance) { RunicDomeCapture.execute(__instance); }
    }
    @SpirePatch(clz=GremlinFat.class,method="takeTurn")
    public static class GremlinFatTurn {
        @SpirePrefixPatch public static void prefix(GremlinFat __instance) { RunicDomeCapture.execute(__instance); }
    }
    @SpirePatch(clz=BookOfStabbing.class,method="takeTurn")
    public static class BookOfStabbingTurn {
        @SpirePrefixPatch public static void prefix(BookOfStabbing __instance) { RunicDomeCapture.execute(__instance); }
    }
    @SpirePatch(clz=TimeEater.class,method="takeTurn")
    public static class TimeEaterTurn {
        @SpirePrefixPatch public static void prefix(TimeEater __instance) { RunicDomeCapture.execute(__instance); }
    }
    public static void finishPublicOverride(AbstractMonster monster) { RunicDomeCapture.finishKnownOverride(monster); }
    private static void instrumentKnownOverride(javassist.CtBehavior method,int expectedSites) throws javassist.CannotCompileException {
        final int[] sites={0};
        method.instrument(new javassist.expr.ExprEditor() {
            @Override public void edit(javassist.expr.MethodCall call) throws javassist.CannotCompileException {
                if(call.getMethodName().equals("setMove")) {
                    String signature=call.getSignature();
                    if(!signature.startsWith("(B") && !signature.startsWith("(Ljava/lang/String;B"))
                        throw new javassist.CannotCompileException("unqualified public setter signature");
                    ++sites[0];String arg=signature.startsWith("(B")?"$1":"$2";
                    call.replace("{ if(stsmodelinspector.RunicDomeTrackerPatch.beginHiddenSetter($0)) { $proceed($$); stsmodelinspector.RunicDomeTrackerPatch.endHiddenSetter($0); } else { stsmodelinspector.RunicDomeTrackerPatch.publicAcidOverride($0, "+arg+"); $proceed($$); stsmodelinspector.RunicDomeTrackerPatch.finishPublicOverride($0); } }");
                }
            }
        });
        if(sites[0]!=expectedSites) throw new javassist.CannotCompileException("unqualified public setter sites");
    }
    @SpirePatch(clz=com.megacrit.cardcrawl.actions.common.SetMoveAction.class,method="update")
    public static class PublicSetMoveAction {
        @SpireRawPatch public static void raw(javassist.CtBehavior method) throws javassist.CannotCompileException { instrumentKnownOverride(method,1); }
    }
    @SpirePatch(clz=GremlinThief.class,method="takeTurn")
    public static class GremlinThiefTurn {
        @SpirePrefixPatch public static void prefix(GremlinThief __instance) { RunicDomeCapture.beginKnownTurn(__instance); }
    }
    @SpirePatch(clz=GremlinWarrior.class,method="takeTurn")
    public static class GremlinWarriorTurn {
        @SpirePrefixPatch public static void prefix(GremlinWarrior __instance) { RunicDomeCapture.beginKnownTurn(__instance); }
    }
    @SpirePatch(clz=GremlinWizard.class,method="takeTurn")
    public static class GremlinWizardTurn {
        @SpirePrefixPatch public static void prefix(GremlinWizard __instance) { RunicDomeCapture.beginKnownTurn(__instance); }
        @SpireRawPatch public static void raw(javassist.CtBehavior method) throws javassist.CannotCompileException { instrumentKnownOverride(method,3); }
    }
    @SpirePatch(clz=GremlinTsundere.class,method="takeTurn")
    public static class GremlinTsundereTurn {
        @SpirePrefixPatch public static void prefix(GremlinTsundere __instance) { RunicDomeCapture.beginKnownTurn(__instance); }
        @SpireRawPatch public static void raw(javassist.CtBehavior method) throws javassist.CannotCompileException { instrumentKnownOverride(method,2); }
    }
    @SpirePatch(clz=BanditBear.class,method="takeTurn")
    public static class BanditBearTurn {
        @SpirePrefixPatch public static void prefix(BanditBear __instance) { RunicDomeCapture.beginKnownTurn(__instance); }
    }
    @SpirePatch(clz=BanditLeader.class,method="takeTurn")
    public static class BanditLeaderTurn {
        @SpirePrefixPatch public static void prefix(BanditLeader __instance) { RunicDomeCapture.beginKnownTurn(__instance); }
    }
    @SpirePatch(clz=BanditPointy.class,method="takeTurn")
    public static class BanditPointyTurn {
        @SpirePrefixPatch public static void prefix(BanditPointy __instance) { RunicDomeCapture.beginKnownTurn(__instance); }
    }
    @SpirePatch(clz=Transient.class,method="takeTurn")
    public static class TransientTurn {
        @SpirePrefixPatch public static void prefix(Transient __instance) { RunicDomeCapture.beginKnownTurn(__instance); }
        @SpireRawPatch public static void raw(javassist.CtBehavior method) throws javassist.CannotCompileException { instrumentKnownOverride(method,1); }
    }
    @SpirePatch(clz=WrithingMass.class,method="takeTurn")
    public static class WrithingMassTurn {
        @SpirePrefixPatch public static void prefix(WrithingMass __instance) { RunicDomeCapture.execute(__instance); }
    }
    @SpirePatch(clz=Champ.class,method="takeTurn")
    public static class ChampTurn {
        @SpirePrefixPatch public static void prefix(Champ __instance) { RunicDomeCapture.execute(__instance); }
    }
    public static void publicStun(AbstractMonster monster,int move) { RunicDomeCapture.publicStun(monster,move); }
    private static void instrumentPublicStun(javassist.CtBehavior method) throws javassist.CannotCompileException {
        final int[] sites={0};
        method.instrument(new javassist.expr.ExprEditor() {
            @Override public void edit(javassist.expr.MethodCall call) throws javassist.CannotCompileException {
                if(call.getMethodName().equals("setMove")) {
                    String signature=call.getSignature();
                    if(!signature.startsWith("(B") && !signature.startsWith("(Ljava/lang/String;B")) throw new javassist.CannotCompileException("unqualified stun signature");
                    String arg=signature.startsWith("(B")?"$1":"$2";
                    ++sites[0];call.replace("{ stsmodelinspector.RunicDomeTrackerPatch.publicStun($0,"+arg+"); $proceed($$); stsmodelinspector.RunicDomeTrackerPatch.finishPublicOverride($0); }");
                }
            }
        });
        if(sites[0]!=1) throw new javassist.CannotCompileException("unqualified stun sites");
    }
    @SpirePatch(clz=Byrd.class,method="takeTurn")
    public static class ByrdTurn {
        @SpirePrefixPatch public static void prefix(Byrd __instance) { RunicDomeCapture.beginDynamicTurn(__instance); }
        @SpireRawPatch public static void raw(javassist.CtBehavior method) throws javassist.CannotCompileException { instrumentKnownOverride(method,1); }
    }
    @SpirePatch(clz=Byrd.class,method="changeState")
    public static class ByrdGrounded {
        @SpireRawPatch public static void raw(javassist.CtBehavior method) throws javassist.CannotCompileException { instrumentPublicStun(method); }
    }
    @SpirePatch(clz=ShelledParasite.class,method="takeTurn")
    public static class ShelledParasiteTurn {
        @SpirePrefixPatch public static void prefix(ShelledParasite __instance) { RunicDomeCapture.beginDynamicTurn(__instance); }
        @SpireRawPatch public static void raw(javassist.CtBehavior method) throws javassist.CannotCompileException { instrumentKnownOverride(method,1); }
    }
    @SpirePatch(clz=ShelledParasite.class,method="changeState")
    public static class ShelledParasiteStun {
        @SpireRawPatch public static void raw(javassist.CtBehavior method) throws javassist.CannotCompileException { instrumentPublicStun(method); }
    }
    @SpirePatch(clz=TheGuardian.class,method="takeTurn")
    public static class GuardianTurn {
        @SpirePrefixPatch public static void prefix(TheGuardian __instance) { RunicDomeCapture.beginKnownTurn(__instance); }
    }
    @SpirePatch(clz=TheGuardian.class,method="changeState")
    public static class GuardianDefense {
        @SpireRawPatch public static void raw(javassist.CtBehavior method) throws javassist.CannotCompileException { instrumentPublicStun(method); }
    }
    @SpirePatch(clz=TheGuardian.class,method="useCloseUp")
    public static class Guardian_useCloseUp {
        @SpireRawPatch public static void raw(javassist.CtBehavior method) throws javassist.CannotCompileException { instrumentKnownOverride(method,1); }
    }
    @SpirePatch(clz=TheGuardian.class,method="useFierceBash")
    public static class Guardian_useFierceBash {
        @SpireRawPatch public static void raw(javassist.CtBehavior method) throws javassist.CannotCompileException { instrumentKnownOverride(method,1); }
    }
    @SpirePatch(clz=TheGuardian.class,method="useVentSteam")
    public static class Guardian_useVentSteam {
        @SpireRawPatch public static void raw(javassist.CtBehavior method) throws javassist.CannotCompileException { instrumentKnownOverride(method,1); }
    }
    @SpirePatch(clz=TheGuardian.class,method="useRollAttack")
    public static class Guardian_useRollAttack {
        @SpireRawPatch public static void raw(javassist.CtBehavior method) throws javassist.CannotCompileException { instrumentKnownOverride(method,1); }
    }
    @SpirePatch(clz=TheGuardian.class,method="useTwinSmash")
    public static class Guardian_useTwinSmash {
        @SpireRawPatch public static void raw(javassist.CtBehavior method) throws javassist.CannotCompileException { instrumentKnownOverride(method,1); }
    }
    @SpirePatch(clz=TheGuardian.class,method="useWhirlwind")
    public static class Guardian_useWhirlwind {
        @SpireRawPatch public static void raw(javassist.CtBehavior method) throws javassist.CannotCompileException { instrumentKnownOverride(method,1); }
    }
    @SpirePatch(clz=TheGuardian.class,method="useChargeUp")
    public static class Guardian_useChargeUp {
        @SpireRawPatch public static void raw(javassist.CtBehavior method) throws javassist.CannotCompileException { instrumentKnownOverride(method,1); }
    }
    @SpirePatch(clz=Hexaghost.class,method="takeTurn")
    public static class HexaghostTurn {
        @SpirePrefixPatch public static void prefix(Hexaghost __instance) { RunicDomeCapture.beginHexTurn(__instance); }
        @SpireRawPatch public static void raw(javassist.CtBehavior method) throws javassist.CannotCompileException { instrumentKnownOverride(method,1); }
    }
    public static void publicHexInferno(AbstractMonster monster,int move) { RunicDomeCapture.hexInferno(monster,move); }
    @SpirePatch(clz=Hexaghost.class,method="changeState")
    public static class HexaghostInferno {
        @SpireRawPatch public static void raw(javassist.CtBehavior method) throws javassist.CannotCompileException {
            final int[] sites={0};
            method.instrument(new javassist.expr.ExprEditor() {
                @Override public void edit(javassist.expr.MethodCall call) throws javassist.CannotCompileException {
                    if(call.getMethodName().equals("setMove")) {
                        if(!call.getSignature().startsWith("(Ljava/lang/String;B")) throw new javassist.CannotCompileException("unqualified Hex setter");
                        ++sites[0];call.replace("{ stsmodelinspector.RunicDomeTrackerPatch.publicHexInferno($0,$2); $proceed($$); stsmodelinspector.RunicDomeTrackerPatch.finishPublicOverride($0); }");
                    }
                }
            });
            if(sites[0]!=1) throw new javassist.CannotCompileException("unqualified Hex setter sites");
        }
    }
    @SpirePatch(clz=Lagavulin.class,method="takeTurn")
    public static class LagavulinTurn {
        @SpirePrefixPatch public static void prefix(Lagavulin __instance) {RunicDomeCapture.beginLagaTurn(__instance);}
        @SpireRawPatch public static void raw(javassist.CtBehavior method) throws javassist.CannotCompileException {instrumentKnownOverride(method,2);}
    }
    @SpirePatch(clz=Lagavulin.class,method="damage")
    public static class LagavulinWake {
        @SpireRawPatch public static void raw(javassist.CtBehavior method) throws javassist.CannotCompileException {instrumentPublicStun(method);}
    }
    public static void publicLagaPrebattle(AbstractMonster monster,int move) {RunicDomeCapture.lagaPrebattle(monster,move);}
    @SpirePatch(clz=Lagavulin.class,method="usePreBattleAction")
    public static class LagavulinPrebattle {
        @SpireRawPatch public static void raw(javassist.CtBehavior method) throws javassist.CannotCompileException {
            final int[] sites={0};method.instrument(new javassist.expr.ExprEditor() {
                @Override public void edit(javassist.expr.MethodCall call) throws javassist.CannotCompileException {
                    if(call.getMethodName().equals("setMove")) {
                        if(!call.getSignature().startsWith("(Ljava/lang/String;B")) throw new javassist.CannotCompileException("unqualified Laga prebattle");
                        ++sites[0];call.replace("{ stsmodelinspector.RunicDomeTrackerPatch.publicLagaPrebattle($0,$2);$proceed($$);stsmodelinspector.RunicDomeTrackerPatch.finishPublicOverride($0); }");
                    }
                }
            });if(sites[0]!=1) throw new javassist.CannotCompileException("unqualified Laga prebattle sites");
        }
    }
    public static boolean beginHiddenSetter(AbstractMonster monster) {return RunicDomeCapture.beginHiddenSetter(monster);}
    public static void endHiddenSetter(AbstractMonster monster) {RunicDomeCapture.endHiddenSetter(monster);}
    @SpirePatch(clz=Looter.class,method="takeTurn")
    public static class LooterTurn {
        @SpirePrefixPatch public static void prefix(Looter __instance) {RunicDomeCapture.beginThiefTurn(__instance);}
        @SpireRawPatch public static void raw(javassist.CtBehavior method) throws javassist.CannotCompileException {instrumentKnownOverride(method,2);}
    }
    @SpirePatch(clz=Mugger.class,method="takeTurn")
    public static class MuggerTurn {
        @SpirePrefixPatch public static void prefix(Mugger __instance) {RunicDomeCapture.beginThiefTurn(__instance);}
        @SpireRawPatch public static void raw(javassist.CtBehavior method) throws javassist.CannotCompileException {instrumentKnownOverride(method,2);}
    }
    public static void publicTheft(AbstractMonster monster) {RunicDomeCapture.publicTheft(monster);}
    private static void instrumentTheft(javassist.CtBehavior method) throws javassist.CannotCompileException {
        final int[] sites={0};method.instrument(new javassist.expr.ExprEditor() {
            @Override public void edit(javassist.expr.MethodCall call) throws javassist.CannotCompileException {
                if(call.getMethodName().equals("access$002")) {
                    ++sites[0];call.replace("{ stsmodelinspector.RunicDomeTrackerPatch.publicTheft($1); $_=$proceed($$); }");
                }
            }
        });if(sites[0]!=1)throw new javassist.CannotCompileException("unqualified public theft action");
    }
    @SpirePatch(cls="com.megacrit.cardcrawl.monsters.exordium.Looter$1",method="update")
    public static class LooterTheft1 {
        @SpireRawPatch public static void raw(javassist.CtBehavior method) throws javassist.CannotCompileException {instrumentTheft(method);}
    }
    @SpirePatch(cls="com.megacrit.cardcrawl.monsters.exordium.Looter$2",method="update")
    public static class LooterTheft2 {
        @SpireRawPatch public static void raw(javassist.CtBehavior method) throws javassist.CannotCompileException {instrumentTheft(method);}
    }
    @SpirePatch(cls="com.megacrit.cardcrawl.monsters.city.Mugger$1",method="update")
    public static class MuggerTheft1 {
        @SpireRawPatch public static void raw(javassist.CtBehavior method) throws javassist.CannotCompileException {instrumentTheft(method);}
    }
    @SpirePatch(cls="com.megacrit.cardcrawl.monsters.city.Mugger$2",method="update")
    public static class MuggerTheft2 {
        @SpireRawPatch public static void raw(javassist.CtBehavior method) throws javassist.CannotCompileException {instrumentTheft(method);}
    }
    @SpirePatch(clz=AwakenedOne.class,method="takeTurn")
    public static class AwakenedOneTurn {
        @SpirePrefixPatch public static void prefix(AwakenedOne __instance) {RunicDomeCapture.execute(__instance);}
    }
    public static void publicRebirth(AbstractMonster monster,int move) {RunicDomeCapture.beginRebirth(monster,move);}
    @SpirePatch(clz=AwakenedOne.class,method="damage")
    public static class AwakenedOneRebirth {
        @SpireRawPatch public static void raw(javassist.CtBehavior method) throws javassist.CannotCompileException {
            final int[] sites={0};method.instrument(new javassist.expr.ExprEditor() {
                @Override public void edit(javassist.expr.MethodCall call) throws javassist.CannotCompileException {
                    if(call.getMethodName().equals("setMove")) {
                        if(!call.getSignature().startsWith("(B"))throw new javassist.CannotCompileException("unqualified rebirth setter");
                        ++sites[0];call.replace("{ stsmodelinspector.RunicDomeTrackerPatch.publicRebirth($0,$1);$proceed($$);stsmodelinspector.RunicDomeTrackerPatch.finishPublicOverride($0); }");
                    }
                }
            });if(sites[0]!=1)throw new javassist.CannotCompileException("unqualified rebirth setter sites");
        }
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
    public static void registeredBirth(AbstractMonster m) {RunicDomeCapture.constructed(m);}
    public static void spawnInit(AbstractMonster m) {RunicDomeCapture.beforeSpawnInit(m);}
    public static void publicRemainingOverride(AbstractMonster m,int move) {RunicDomeCapture.publicOverride(m,move);}
    public static void torchConstructor(boolean before) {RunicDomeCapture.torchConstructor(before);}
    public static void torchConstructorResult(AbstractMonster m){RunicDomeCapture.torchConstructorResult(m);}
    static void instrumentSpawnInit(javassist.CtBehavior method) throws javassist.CannotCompileException {
        final int[] sites={0};method.instrument(new javassist.expr.ExprEditor(){
            @Override public void edit(javassist.expr.MethodCall c) throws javassist.CannotCompileException {
                if(c.getClassName().equals(AbstractMonster.class.getName()) && c.getMethodName().equals("init")) {
                    ++sites[0];c.replace("{stsmodelinspector.RunicDomeTrackerPatch.spawnInit($0);$proceed($$);}");
                }
            }
        });if(sites[0]!=1)throw new javassist.CannotCompileException("unqualified birth init sites");
    }
    static void instrumentRemainingOverride(javassist.CtBehavior method,int expected) throws javassist.CannotCompileException {
        final int[] sites={0};method.instrument(new javassist.expr.ExprEditor(){
            @Override public void edit(javassist.expr.MethodCall c) throws javassist.CannotCompileException {
                if(c.getMethodName().equals("setMove")) {
                    ++sites[0];String arg=c.getSignature().startsWith("(Ljava/lang/String;")?"$2":"$1";
                    c.replace("{stsmodelinspector.RunicDomeTrackerPatch.publicRemainingOverride($0,"+arg+");$proceed($$);stsmodelinspector.RunicDomeTrackerPatch.finishPublicOverride($0);}");
                }
            }
        });if(sites[0]!=expected)throw new javassist.CannotCompileException("unqualified remaining override sites");
    }
    @SpirePatch(clz=com.megacrit.cardcrawl.actions.common.SpawnMonsterAction.class,method=SpirePatch.CONSTRUCTOR,paramtypez={AbstractMonster.class,boolean.class,int.class})
    public static class SpawnConstructed {
        // SpirePatch binds positionally: the receiver precedes constructor arguments.
        @SpirePostfixPatch public static void postfix(com.megacrit.cardcrawl.actions.common.SpawnMonsterAction __instance,AbstractMonster m){registeredBirth(m);}
    }
    @SpirePatch(clz=com.megacrit.cardcrawl.actions.common.SpawnMonsterAction.class,method="update")
    public static class SpawnInit {
        @SpireRawPatch public static void raw(javassist.CtBehavior method)throws javassist.CannotCompileException{instrumentSpawnInit(method);}
    }
    @SpirePatch(clz=com.megacrit.cardcrawl.actions.unique.SummonGremlinAction.class,method=SpirePatch.CONSTRUCTOR)
    public static class GremlinConstructed {
        @SpireRawPatch public static void raw(javassist.CtBehavior method)throws javassist.CannotCompileException{
            final int[] sites={0};method.instrument(new javassist.expr.ExprEditor(){
                @Override public void edit(javassist.expr.FieldAccess f)throws javassist.CannotCompileException{
                    if(f.isWriter() && f.getFieldName().equals("m")){++sites[0];f.replace("{$proceed($$);stsmodelinspector.RunicDomeTrackerPatch.registeredBirth($1);}");}
                }
            });if(sites[0]!=1)throw new javassist.CannotCompileException("unqualified gremlin birth sites");
        }
    }
    @SpirePatch(clz=com.megacrit.cardcrawl.actions.unique.SummonGremlinAction.class,method="update")
    public static class GremlinInit {
        @SpireRawPatch public static void raw(javassist.CtBehavior method)throws javassist.CannotCompileException{instrumentSpawnInit(method);}
    }
    @SpirePatch(clz=TorchHead.class,method=SpirePatch.CONSTRUCTOR)
    public static class TorchConstructor {
        @SpireRawPatch public static void raw(javassist.CtBehavior method)throws javassist.CannotCompileException{
            final int[] sites={0};method.instrument(new javassist.expr.ExprEditor(){
                @Override public void edit(javassist.expr.MethodCall c)throws javassist.CannotCompileException{
                    if(c.getMethodName().equals("setMove")){++sites[0];c.replace("{stsmodelinspector.RunicDomeTrackerPatch.torchConstructor(true);$proceed($$);stsmodelinspector.RunicDomeTrackerPatch.torchConstructor(false);stsmodelinspector.RunicDomeTrackerPatch.torchConstructorResult($0);}");}
                }
            });if(sites[0]!=1)throw new javassist.CannotCompileException("unqualified torch constructor");
        }
    }
    @SpirePatch(clz=AcidSlime_L.class,method="takeTurn")
    public static class AcidSlime_LRemainingTurn {
        @SpirePrefixPatch public static void prefix(AcidSlime_L __instance){RunicDomeCapture.beginParentTurn(__instance);}
        @SpirePostfixPatch public static void postfix(AcidSlime_L __instance){RunicDomeCapture.endParentTurn(__instance);}
        @SpireRawPatch public static void raw(javassist.CtBehavior method)throws javassist.CannotCompileException{instrumentRemainingOverride(method,1);}
    }
    @SpirePatch(clz=SpikeSlime_L.class,method="takeTurn")
    public static class SpikeSlime_LRemainingTurn {
        @SpirePrefixPatch public static void prefix(SpikeSlime_L __instance){RunicDomeCapture.beginParentTurn(__instance);}
        @SpirePostfixPatch public static void postfix(SpikeSlime_L __instance){RunicDomeCapture.endParentTurn(__instance);}
        @SpireRawPatch public static void raw(javassist.CtBehavior method)throws javassist.CannotCompileException{instrumentRemainingOverride(method,1);}
    }
    @SpirePatch(clz=SlimeBoss.class,method="takeTurn")
    public static class SlimeBossRemainingTurn {
        @SpirePrefixPatch public static void prefix(SlimeBoss __instance){RunicDomeCapture.beginParentTurn(__instance);}
        @SpirePostfixPatch public static void postfix(SlimeBoss __instance){RunicDomeCapture.endParentTurn(__instance);}
        @SpireRawPatch public static void raw(javassist.CtBehavior method)throws javassist.CannotCompileException{instrumentKnownOverride(method,4);}
    }
    @SpirePatch(clz=BronzeAutomaton.class,method="takeTurn")
    public static class BronzeAutomatonRemainingTurn {
        @SpirePrefixPatch public static void prefix(BronzeAutomaton __instance){RunicDomeCapture.beginParentTurn(__instance);}
        @SpirePostfixPatch public static void postfix(BronzeAutomaton __instance){RunicDomeCapture.endParentTurn(__instance);}
    }
    @SpirePatch(clz=GremlinLeader.class,method="takeTurn")
    public static class GremlinLeaderRemainingTurn {
        @SpirePrefixPatch public static void prefix(GremlinLeader __instance){RunicDomeCapture.beginParentTurn(__instance);}
        @SpirePostfixPatch public static void postfix(GremlinLeader __instance){RunicDomeCapture.endParentTurn(__instance);}
    }
    @SpirePatch(clz=Reptomancer.class,method="takeTurn")
    public static class ReptomancerRemainingTurn {
        @SpirePrefixPatch public static void prefix(Reptomancer __instance){RunicDomeCapture.beginParentTurn(__instance);}
        @SpirePostfixPatch public static void postfix(Reptomancer __instance){RunicDomeCapture.endParentTurn(__instance);}
    }
    @SpirePatch(clz=TheCollector.class,method="takeTurn")
    public static class TheCollectorRemainingTurn {
        @SpirePrefixPatch public static void prefix(TheCollector __instance){RunicDomeCapture.beginParentTurn(__instance);}
        @SpirePostfixPatch public static void postfix(TheCollector __instance){RunicDomeCapture.endParentTurn(__instance);}
    }
    @SpirePatch(clz=BronzeOrb.class,method="takeTurn")
    public static class BronzeOrbRemainingTurn {
        @SpirePrefixPatch public static void prefix(BronzeOrb __instance){RunicDomeCapture.execute(__instance);}
    }
    @SpirePatch(clz=SnakeDagger.class,method="takeTurn")
    public static class SnakeDaggerRemainingTurn {
        @SpirePrefixPatch public static void prefix(SnakeDagger __instance){RunicDomeCapture.execute(__instance);}
    }
    @SpirePatch(clz=LouseNormal.class,method="takeTurn")
    public static class LouseNormalRemainingTurn {
        @SpirePrefixPatch public static void prefix(LouseNormal __instance){RunicDomeCapture.execute(__instance);}
    }
    @SpirePatch(clz=LouseDefensive.class,method="takeTurn")
    public static class LouseDefensiveRemainingTurn {
        @SpirePrefixPatch public static void prefix(LouseDefensive __instance){RunicDomeCapture.execute(__instance);}
    }
    @SpirePatch(clz=Darkling.class,method="takeTurn")
    public static class DarklingRemainingTurn {
        @SpirePrefixPatch public static void prefix(Darkling __instance){RunicDomeCapture.execute(__instance);}
    }
    @SpirePatch(clz=TorchHead.class,method="takeTurn")
    public static class TorchRemainingTurn {
        @SpirePrefixPatch public static void prefix(TorchHead __instance){RunicDomeCapture.beginKnownTurn(__instance);}
    }
    @SpirePatch(clz=AcidSlime_L.class,method="damage")
    public static class AcidSlime_LPublicOverride {
        @SpireRawPatch public static void raw(javassist.CtBehavior method)throws javassist.CannotCompileException{instrumentRemainingOverride(method,1);}
    }
    @SpirePatch(clz=SpikeSlime_L.class,method="damage")
    public static class SpikeSlime_LPublicOverride {
        @SpireRawPatch public static void raw(javassist.CtBehavior method)throws javassist.CannotCompileException{instrumentRemainingOverride(method,1);}
    }
    @SpirePatch(clz=SlimeBoss.class,method="damage")
    public static class SlimeBossPublicOverride {
        @SpireRawPatch public static void raw(javassist.CtBehavior method)throws javassist.CannotCompileException{instrumentRemainingOverride(method,1);}
    }
    @SpirePatch(clz=Darkling.class,method="damage")
    public static class DarklingPublicOverride {
        @SpireRawPatch public static void raw(javassist.CtBehavior method)throws javassist.CannotCompileException{instrumentRemainingOverride(method,1);}
    }

}
