package stsmodelinspector;

/** Independent literal public outcomes, including cases where several bases remain indistinguishable. */
public final class PublicLatentDamageCaptureTest {
    private static final int PRIOR=(1<<5)|(1<<6)|(1<<7);
    private static PublicLatentDamageCapture.Observation hit(int hp,int afterHp,int block,int afterBlock,int buffer,int afterBuffer,
            int strength,int revive,boolean weak,boolean vuln,boolean intangible,boolean mushroom,boolean crane,
            boolean torii,boolean tungsten,boolean wrath) {
        return new PublicLatentDamageCapture.Observation(hp,afterHp,block,afterBlock,buffer,afterBuffer,100,strength,revive,
                weak,vuln,intangible,mushroom,crane,torii,tungsten,wrath);
    }
    private static void expect(String label,int wanted,PublicLatentDamageCapture.Observation o) {
        int got=o.filterMask(PRIOR);if(got!=wanted)throw new AssertionError(label+": "+got+" != "+wanted);
        if(o.toMap().containsKey("damage") || o.toMap().containsKey("base") || o.toMap().containsKey("output"))
            throw new AssertionError("Private damage field serialized");
    }
    public static void main(String[] args) {
        expect("ordinary six",1<<6,hit(100,94,0,0,0,0,0,0,false,false,false,false,false,false,false,false));
        expect("visible block consumption",1<<6,hit(100,100,10,4,0,0,0,0,false,false,false,false,false,false,false,false));
        expect("exact block boundary",1<<6,hit(100,100,6,0,0,0,0,0,false,false,false,false,false,false,false,false));
        expect("buffer censor",PRIOR,hit(100,100,0,0,1,1,0,0,false,false,false,false,false,false,false,false));
        expect("intangible censor",PRIOR,hit(100,99,0,0,0,0,0,0,false,false,true,false,false,false,false,false));
        expect("overkill censor",PRIOR,hit(2,0,0,0,0,0,0,0,false,false,false,false,false,false,false,false));
        expect("revival censor",PRIOR,hit(2,44,0,0,0,0,0,44,false,false,false,false,false,false,false,false));
        expect("torii censor",PRIOR,hit(100,99,3,0,0,0,0,0,false,false,false,false,false,true,false,false));
        expect("tungsten",1<<6,hit(100,95,0,0,0,0,0,0,false,false,false,false,false,false,true,false));
        expect("weak floor",1<<6,hit(100,96,0,0,0,0,0,0,true,false,false,false,false,false,false,false));
        expect("weak vuln strength order",1<<5,hit(100,94,0,0,0,0,1,0,true,true,false,false,false,false,false,false));
        expect("crane mushroom",1<<6,hit(100,95,0,0,0,0,1,0,true,true,false,true,true,false,false,false));
        expect("wrath",1<<6,hit(100,88,0,0,0,0,0,0,false,false,false,false,false,false,false,true));
        expect("zero damage censor",PRIOR,hit(100,100,0,0,0,0,-9,0,false,false,false,false,false,false,false,false));
        expect("impossible output",0,hit(100,1,0,0,0,0,0,0,false,false,false,false,false,false,false,false));
        expect("invalid before hp",0,hit(0,0,0,0,0,0,0,0,false,false,false,false,false,false,false,false));
        PublicLatentDamageCapture.Observation narrowed=hit(100,94,0,0,0,0,0,0,false,false,false,false,false,false,false,false);
        if(narrowed.filterMask(1<<5)!=0 || narrowed.filterMask(65536)!=0)
            throw new AssertionError("Posterior expanded or accepted invalid mask");
        System.out.println("PublicLatentDamageCaptureTest: public hit filtering, censoring, modifiers, revival and malformed outcomes passed");
    }
}
