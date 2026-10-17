// §494 rollout-target student as an OOC MCTS leaf value (research, default off).
//
// Native port of tools/heart_rollout_distill.py Net('attention') with the
// tools/heart_record_encoder.py encode_record features: a public heart1 leaf
// record (heart1::buildPublicLeafRecord) plus the leaf's X2-B anchor predicts the
// mean of Arm C rollout3 leaf values as sigmoid(net + logit(anchor)). Weights come
// from the §494 selected.pt via tools/rollout_student_export.py; they are not vendored.
#ifndef STS_ONE_COMBAT_ROLLOUT_STUDENT_H
#define STS_ONE_COMBAT_ROLLOUT_STUDENT_H

#include <optional>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

namespace one_combat {

class RolloutStudent {
public:
    // Throws on a malformed or incompatible weights file.
    explicit RolloutStudent(const std::string &path);
    // Predicted rollout value in [0, 1], or nullopt when encode_record would
    // reject the record (the caller falls back to its rollout).
    std::optional<double> predict(const nlohmann::json &record, double anchor) const;
    const std::string &path() const { return path_; }

private:
    struct Token { int kind, entity; float attrs[8]; };
    bool encode(const nlohmann::json &r, std::vector<std::pair<int, float>> &sparse,
                std::vector<Token> &tokens) const;

    std::string path_;
    int inputs_ = 0;  // vocabulary columns
    std::vector<int> denseCol_, countCol_, attrCol_;
    std::vector<float> cls_, kind_, entity_, attrs_;
    struct Layer {
        std::vector<float> inW, inB, outW, outB, l1W, l1B, l2W, l2B, n1W, n1B, n2W, n2B;
    };
    std::vector<Layer> layers_;
    std::vector<float> w0_, b0_, w2_, b2_, w4_, b4_;
};

// `one_combat rolloutstudentscore <weights.bin> <rows.jsonl> <out.jsonl>`: rows
// carry {"record", "x2b"}; prints {"value"} or {"unsupported": true} per row.
int rolloutStudentScoreCommand(int argc, char **argv);

}  // namespace one_combat

#endif
