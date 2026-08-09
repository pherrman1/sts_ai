# How the Slay the Spire AI Works

An explanation of the AI that plays Slay the Spire in this project. Assumes you know the game and have basic IT knowledge (algorithms, data, what "training a model" means). No machine learning background needed.

## Pages

| Page | Topic |
|------|-------|
| [How the AI fights](how-combat-works.md) | Monte Carlo Tree Search and the combat-value model |
| [How the AI makes run decisions](run-decisions.md) | Out-of-combat choices: card rewards, rest, shop, events, path |
| [How the models learned](how-models-learn.md) | Training pipeline: data generation, GBM training, neural network training |
| [A complete run](putting-it-together.md) | Walk through one run, decision point by decision point |
| [Glossary](glossary.md) | Definitions of all technical terms |

## In 30 seconds

The AI has two systems that don't directly talk to each other — they share the game state:

```mermaid
flowchart LR
    subgraph Combat["During fights"]
        MCTS["MCTS<br/>(simulates thousands of<br/>possible action sequences)"]
        VLeaf["Value predictor<br/>(GBM: estimates end-of-fight HP)"]
    end
    subgraph Map["On the map"]
        NN["Neural network<br/>(scores card picks, rest,<br/>shop, events, boss relics)"]
        Heuristics["Hand-coded rules<br/>(path finding, upgrade<br/>priorities, fallback)"]
    end
    MCTS -->|"uses"| VLeaf
    NN -->|"overrides"| Heuristics
```

**Combat:** Each turn, the AI runs 1,000–3,000 simulations of "what if I play these cards?" through a tree search. A GBM (gradient boosted machine — essentially a large decision flowchart) estimates how much HP remains at the end of the fight so the search doesn't have to simulate all the way to the end every time.

**Map:** Between fights, a small neural network scores each available choice. If its top pick beats the runner-up by enough margin, it overrides the hand-coded rules. Otherwise the heuristic handles it.

## Model summary

| Type | Analogy | Predicts | Size |
|------|---------|----------|------|
| **GBM** | Flowchart with ~1,000 branches, each checking conditions like "HP < 30?" or "has Corruption?" | Future HP, win chance, good next moves | ~1,000 trees, a few MB |
| **Neural network** | Formula with ~40+ inputs and hundreds of thousands of parameters | Q-values for run decisions | ~800 KB exported |

Both models load inline in the executable; the combined model files total a few megabytes.

## Current performance

Measured at 1,000 simulations/decision, 32 seeds. The A5–A20 numbers include the Heart fight (Act 4). Act-3-only was measured only at A0:

| Ascension | Full run (Act 3+4) | Act-3 only |
|-----------|---------------------|-------------|
| A0 | 22% | 31% |
| A5 | 13% | — |
| A10 | 13% | — |
| A15 | 9% | — |
| A20 | 0% | — |

At 3,000 simulations on larger seed blocks, earlier Searcher2/Searcher3 stacks reached roughly 44–47% A0 Act-3 (not yet measured on the current stack).

Top human players win roughly 40–60% of A20 Heart runs.

The AI sees only what a player sees — draw pile order and event RNG are hidden and sampled probabilistically.

---

**Start here:** [How the AI fights →](how-combat-works.md)
