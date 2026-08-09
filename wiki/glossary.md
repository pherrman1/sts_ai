# Glossary

## A–F

### Backpropagation
MCTS step 4: a simulation's result (final HP) propagates back up the tree. Every visited node updates its visit count and average value.

### Combat value net (V_combat)
A GBM that predicts end-of-fight HP from the current combat state. Used as a leaf evaluator in MCTS to shortcut rollouts. 1,000 trees, 751 features, trained on ~1.58 million combat states.

### CSV
Comma-Separated Values. The spreadsheet format used throughout the training pipeline. Each row is one game state or decision; columns are features (HP, enemy HP, cards in hand, etc.).

### Determinization
One specific random outcome for all hidden variables — mainly the shuffled draw pile order. MCTS samples multiple determinizations (particles) to handle hidden information.

### Expansion
MCTS step 2: at a leaf node, add all legal next moves as children in the tree.

### Feature
A single number describing the game state: "player HP = 68," "has Vulnerable = 1," "Strike count = 3."

### Floor value (V_rich)
A GBM that scores run quality at any map floor. Used for card rewards, shop decisions, and path evaluation. Also called the "floor-value GBM" in the run-decisions page.

## G–M

### Gate (gating)
Two meanings in this project: (1) The mechanism where the neural network overrides the heuristic only when its top pick beats the runner-up by ≥ 1.0. (2) The paired statistical test: hundreds of identical seeds (adaptive gate up to 500) run with old and new models; the new model "passes the gate" if it wins significantly more.

### GBM (Gradient Boosted Machine)
A model made of many small decision trees, built sequentially. Each tree corrects errors from previous trees. At inference time, the input flows through all trees and their predictions are summed. Trained with XGBoost. See [How the models learned](how-models-learn.md).

### Heuristic
A hand-coded rule, not learned from data. Examples: "rest if HP < 40%," "pick the card with the highest floor value."

### Hyperparameter
A setting chosen before training (tree depth, learning rate, regularization strength). Not learned from data. The combat GBM's hyperparameters were tuned by an automated search (Optuna).

### IS-MCTS (Information Set MCTS)
MCTS that handles hidden information by sampling multiple possible worlds (particles). Each particle has a different draw order. Actions are evaluated by average outcome across all particles.

### Leaf node
A node in the MCTS tree with no children. When the search reaches a leaf, it either expands it (adds children) or evaluates it (rollout + GBM blend).

### Live-valid
A fix in MCTS: before following a stored tree edge, re-check that the action is legal in the current particle's draw order. Without this, edges added under different draw orders may be illegal. Adds ~5 percentage points to the win rate. Default on.

### MCTS (Monte Carlo Tree Search)
The combat decision algorithm. Iteratively selects, expands, simulates, and backpropagates to build and evaluate a tree of possible action sequences. See [How the AI fights](how-combat-works.md).

### Model artifact
A file containing a trained model. GBMs → `.txt`; neural networks → `.native`.

## N–Z

### Neural network (NN)
A parameterized function: input numbers → matrix multiplications → output predictions. The strategic NN takes run-state features and outputs Q-values per action. Several layers, tens of thousands of parameters. See [How the models learned](how-models-learn.md).

### OOC (Out Of Combat)
Everything between fights: card rewards, rest sites, shops, events, boss relics, path selection.

### One-ply
Evaluating one immediate action, not a sequence. "Ply" from chess: one half-move. The NN scores each action by "how good will the run be after taking this?" not by simulating follow-up decisions.

### Parity test
A check that the Python training code and C++ inference code produce identical outputs for the same input. Prevents silent model-loading bugs.

### Particle
One possible world in IS-MCTS — a specific shuffled draw order. 64 particles per combat decision.

### Policy prior
A GBM that predicts good next moves from past combat data. Used by PUCT to bias MCTS exploration toward promising branches.

### PUCT (Predictor + Upper Confidence bounds for Trees)
The formula MCTS uses to select which child to explore. Balances exploitation (good past results) with exploration (few visits) plus a policy prior bias.

### Q-value
"How good will the run be if I take this action?" Higher is better. Output by the neural network for each available action.

### Rollout
MCTS step 3: simulate the rest of the fight by playing weighted-random cards until it ends. Returns final HP (0 on loss).

### Searcher
The combat tree-search engine variant used by the AI. The current best results use Searcher3, which samples 64 particles (draw-order shuffles), blends the combat-value GBM, and has the live-valid fix enabled. An earlier, simpler Searcher2 variant runs faster but handles hidden information with a single determinization.

### Selection
MCTS step 1: descend the existing tree using PUCT to pick which child to visit at each level.

### Self-play
The automated improvement cycle: generate data with current AI → train new models → paired gate test → deploy if better → repeat.

### Simulation (sim)
One complete MCTS walk: select → expand → rollout → backpropagate. 1,000–3,000 sims per combat decision.

### Terminal node
A tree node where the fight has ended (win or loss). Value is exact (won HP or 0); no rollout or GBM prediction needed.

### Tree (decision tree, in a GBM)
A binary flowchart: "feature X < threshold? Yes → left, No → right." The leaf contains a prediction value.

### Win value (V_win)
A GBM that predicts the probability of winning the run. Used for rest/upgrade decisions. Also called the "win-chance GBM" in the run-decisions page.

### XGBoost
The library used to train GBMs. Handles large datasets efficiently and produces compact models.

---

**Previous:** [A complete run ←](putting-it-together.md)
