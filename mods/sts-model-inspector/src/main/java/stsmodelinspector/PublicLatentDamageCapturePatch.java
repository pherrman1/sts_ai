package stsmodelinspector;

import com.evacipated.cardcrawl.modthespire.lib.SpirePatch;
import com.evacipated.cardcrawl.modthespire.lib.SpirePrefixPatch;
import com.evacipated.cardcrawl.modthespire.lib.SpirePostfixPatch;
import com.megacrit.cardcrawl.cards.DamageInfo;
import com.megacrit.cardcrawl.characters.AbstractPlayer;
import com.megacrit.cardcrawl.dungeons.AbstractDungeon;
import com.megacrit.cardcrawl.monsters.AbstractMonster;
import com.megacrit.cardcrawl.powers.AbstractPower;
import com.megacrit.cardcrawl.potions.AbstractPotion;
import com.megacrit.cardcrawl.relics.AbstractRelic;
import java.util.ArrayDeque;

@SpirePatch(clz=AbstractPlayer.class,method="damage")
public final class PublicLatentDamageCapturePatch {
    private static final class Pending {
        final AbstractMonster source;final PublicLatentDamageCapture.Observation before;
        Pending(AbstractMonster source,PublicLatentDamageCapture.Observation before){this.source=source;this.before=before;}
    }
    private static final ArrayDeque<Pending> stack=new ArrayDeque<>();
    private static int amount(AbstractPlayer p,String id){AbstractPower x=p.getPower(id);return x==null?0:x.amount;}
    private static int amount(AbstractMonster p,String id){AbstractPower x=p.getPower(id);return x==null?0:x.amount;}
    private static int reviveHp(AbstractPlayer p) {
        if(p.hasRelic("Mark of the Bloom"))return 0;
        int n=0;
        for(AbstractPotion x:p.potions)if(x!=null && "FairyPotion".equals(x.ID)) {
            n=Math.max(1,(int)(p.maxHealth*(p.hasRelic("SacredBark")?0.6f:0.3f)));break;
        }
        AbstractRelic tail=p.getRelic("Lizard Tail");
        if(n==0 && tail!=null && tail.counter==-1)n=Math.max(1,p.maxHealth/2);
        if(n>0 && p.hasRelic("Magic Flower"))n=(n*3+1)/2;
        return Math.min(p.maxHealth,n);
    }
    @SpirePrefixPatch public static void prefix(AbstractPlayer __instance,DamageInfo info) {
        Pending pending=new Pending(null,null);
        if(__instance==AbstractDungeon.player && RunicDomeCapture.active() && info!=null
                && info.getClass()==DamageInfo.class && info.type==DamageInfo.DamageType.NORMAL
                && info.owner instanceof AbstractMonster) {
            AbstractMonster source=(AbstractMonster)info.owner;
            if(RunicDomeCapture.publicLatentAttackActive(source)) {
                if(__instance.hasPower("Surrounded"))RunicDomeCapture.invalidate("latent_damage_modifier_domain");
                else pending=new Pending(source,new PublicLatentDamageCapture.Observation(
                    __instance.currentHealth,0,__instance.currentBlock,0,amount(__instance,"Buffer"),0,
                    __instance.maxHealth,amount(source,"Strength"),reviveHp(__instance),source.hasPower("Weakened"),
                    __instance.hasPower("Vulnerable"),__instance.hasPower("IntangiblePlayer"),__instance.hasRelic("Odd Mushroom"),
                    __instance.hasRelic("Paper Crane"),__instance.hasRelic("Torii"),__instance.hasRelic("TungstenRod"),
                    __instance.stance!=null && "Wrath".equals(__instance.stance.ID)));
            }
        }
        stack.push(pending);
    }
    @SpirePostfixPatch public static void postfix(AbstractPlayer __instance,DamageInfo info) {
        if(stack.isEmpty()){if(RunicDomeCapture.active())RunicDomeCapture.invalidate("latent_damage_boundary");return;}
        Pending pending=stack.pop();if(pending.source==null)return;
        PublicLatentDamageCapture.Observation b=pending.before;
        RunicDomeCapture.observePublicLatentDamage(pending.source,new PublicLatentDamageCapture.Observation(
            b.beforeHp,__instance.currentHealth,b.beforeBlock,__instance.currentBlock,b.beforeBuffer,amount(__instance,"Buffer"),
            b.maxHp,b.strength,b.reviveHp,b.weak,b.vulnerable,b.intangible,b.oddMushroom,b.paperKrane,b.torii,b.tungstenRod,b.wrath));
    }
}
