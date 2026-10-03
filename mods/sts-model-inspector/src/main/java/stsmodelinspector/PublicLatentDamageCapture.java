package stsmodelinspector;

import java.util.LinkedHashMap;
import java.util.Map;

/** Finite filtering from publicly visible hit outcomes; never accepts a private damage scalar. */
final class PublicLatentDamageCapture {
    private PublicLatentDamageCapture() {}
    static final class Observation {
        final int beforeHp,afterHp,beforeBlock,afterBlock,beforeBuffer,afterBuffer,maxHp,strength,reviveHp;
        final boolean weak,vulnerable,intangible,oddMushroom,paperKrane,torii,tungstenRod,wrath;
        Observation(int beforeHp,int afterHp,int beforeBlock,int afterBlock,int beforeBuffer,int afterBuffer,
                    int maxHp,int strength,int reviveHp,boolean weak,boolean vulnerable,boolean intangible,
                    boolean oddMushroom,boolean paperKrane,boolean torii,boolean tungstenRod,boolean wrath) {
            this.beforeHp=beforeHp;this.afterHp=afterHp;this.beforeBlock=beforeBlock;this.afterBlock=afterBlock;
            this.beforeBuffer=beforeBuffer;this.afterBuffer=afterBuffer;this.maxHp=maxHp;this.strength=strength;
            this.reviveHp=reviveHp;this.weak=weak;this.vulnerable=vulnerable;this.intangible=intangible;
            this.oddMushroom=oddMushroom;this.paperKrane=paperKrane;this.torii=torii;
            this.tungstenRod=tungstenRod;this.wrath=wrath;
        }
        int filterMask(int mask) {
            if(mask<=0 || mask>65535 || maxHp<1 || maxHp>32767 || beforeHp<1 || beforeHp>maxHp
                    || afterHp<0 || afterHp>maxHp || beforeBlock<0 || beforeBlock>999 || afterBlock<0 || afterBlock>999
                    || beforeBuffer<0 || beforeBuffer>999 || afterBuffer<0 || afterBuffer>999
                    || strength<-999 || strength>999 || reviveHp<0 || reviveHp>maxHp) return 0;
            int result=0;
            for(int base=0;base<16;++base) if((mask&(1<<base))!=0) {
                float damage=base+strength;
                if(weak)damage*=paperKrane?0.6f:0.75f;
                if(vulnerable)damage*=oddMushroom?1.25f:1.5f;
                if(wrath)damage*=2.0f;
                if(intangible)damage=Math.min(damage,1.0f);
                int hit=Math.max(0,(int)Math.floor(damage));
                int block=Math.max(0,beforeBlock-hit),loss=hit-beforeBlock,buffer=beforeBuffer;
                // Buffer reduction is queued after AbstractPlayer.damage returns.
                if(loss>0 && buffer>0)loss=0;
                if(loss>0 && loss<=5 && torii)loss=1;
                if(loss>0 && tungstenRod)--loss;
                int hp=Math.max(0,beforeHp-Math.max(0,loss));
                if(hp==0 && reviveHp>0)hp=reviveHp;
                if(hp==afterHp && block==afterBlock && buffer==afterBuffer)result|=1<<base;
            }
            return result;
        }
        Map<String,Object> toMap() {
            Map<String,Object> m=new LinkedHashMap<>();
            m.put("beforeHp",beforeHp);m.put("afterHp",afterHp);m.put("beforeBlock",beforeBlock);m.put("afterBlock",afterBlock);
            m.put("beforeBuffer",beforeBuffer);m.put("afterBuffer",afterBuffer);m.put("maxHp",maxHp);m.put("strength",strength);
            m.put("reviveHp",reviveHp);m.put("weak",weak);m.put("vulnerable",vulnerable);m.put("intangible",intangible);
            m.put("oddMushroom",oddMushroom);m.put("paperKrane",paperKrane);m.put("torii",torii);
            m.put("tungstenRod",tungstenRod);m.put("wrath",wrath);return m;
        }
    }
}
