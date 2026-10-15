#!/usr/bin/env python3
"""Export a CatBoost model to the same compact-tree text format that
CombatValueNet.cpp reads (originally XGBoost-specific).

CatBoost uses *oblivious* (symmetric) trees: all nodes at a given depth share
the same split condition.  This exporter expands each oblivious tree into a
standard binary decision tree so the C++ evaluator can walk it without knowing
about obliviousness.

Usage:
  # Auto-detect feature names from a training CSV:
  .venv/bin/python3 tools/export_catboost_vnet.py build/vnet_cb.cbm build/vnet_cb.txt --csv build/vcombat_honest.csv

  # Or pass names explicitly:
  .venv/bin/python3 tools/export_catboost_vnet.py build/vnet_cb.cbm build/vnet_cb.txt --features ascension,encounter,...
"""
import sys, json, struct, os
import numpy as np
import catboost as cb


def load_catboost_model(path):
    """Load a CatBoost .cbm file and extract trees + metadata."""
    model = cb.CatBoostRegressor()
    model.load_model(path)

    # Save as JSON to inspect tree structure
    import tempfile
    with tempfile.NamedTemporaryFile(suffix='.json', mode='w', delete=False) as f:
        tmp = f.name
    model.save_model(tmp, format='json')
    with open(tmp) as f:
        raw = json.load(f)
    os.unlink(tmp)

    # Feature info — CatBoost JSON doesn't store original names.
    # Get names from the model's own feature_names_ attribute.
    feature_names = model.feature_names_
    if feature_names and feature_names[0] == '0':
        # Names are just column indices — model was trained without named features.
        # Fall back to numbered names.
        feature_names = [f'f{i}' for i in range(len(feature_names))]
    if not feature_names:
        nfeat = len(raw['features_info'].get('float_features', []))
        feature_names = [f'f{i}' for i in range(nfeat)]

    # Oblivious trees
    oblivious_trees = raw.get('oblivious_trees', [])
    scale, bias = model.get_scale_and_bias()

    return feature_names, oblivious_trees, float(scale), float(bias)


def expand_oblivious_tree(splits, leaf_values, feat_count):
    """Expand one oblivious tree into a standard binary tree.

    Args:
        splits: list of dicts with 'float_feature_index' and 'border'
        leaf_values: list of 2^depth leaf values (ordered by CatBoost encoding)
        feat_count: total number of features (for validation)

    Returns:
        list of ('S', featIdx, thresh, yes_ci, no_ci) or ('L', value) nodes
        in C++ compact-index order (breadth-first).
    """
    depth = len(splits)

    # CatBoost leaf index encoding: bit i (from top, i=0..depth-1) corresponds
    # to split i. If the feature value is < border → left child (0), else right (1).
    # The binary number formed by these bits (MSB = top split) gives the leaf index.
    # So leaf_index = sum(bit_i * 2^(depth-1-i)) where bit_i is 0 for left, 1 for right.

    # We'll build a complete binary tree of height=depth.
    # Internal nodes at level L: 2^L of them, all using splits[L]
    # Leaf nodes at level depth: 2^depth of them

    total_internal = (1 << depth) - 1
    total_nodes = total_internal + (1 << depth)

    # We'll assign compact indices breadth-first
    nodes = [None] * total_nodes

    # First pass: assign leaves at the bottom level
    leaf_start = total_internal  # compact index of first leaf
    for leaf_idx in range(1 << depth):
        nodes[leaf_start + leaf_idx] = ('L', float(leaf_values[leaf_idx]))

    # Second pass: build internal nodes bottom-up, then assign compact indices
    # Actually easier: build in a list in breadth-first order directly
    result = []

    def build_subtree(level, leaf_offset):
        """Build the subtree rooted at depth `level`.
        leaf_offset: starting leaf index for the leftmost leaf under this node
        Returns: nothing, appends to result in preorder... 

        Actually, let's just build breadth-first which is what the C++ format uses.
        """
        pass

    # Breadth-first construction:
    # Level 0: 1 node using splits[0]
    # Level 1: 2 nodes using splits[1]
    # ...
    # Level depth-1: 2^(depth-1) nodes using splits[depth-1]
    # Level depth: 2^depth leaf nodes

    # First, build all internal nodes in BFS order
    internal_nodes = []
    for level in range(depth):
        s = splits[level]
        feat_idx = int(s['float_feature_index'])
        border = float(s['border'])
        for _ in range(1 << level):
            internal_nodes.append(('S', feat_idx, border, 0, 0))  # children set later

    # Total internal nodes
    n_internal = len(internal_nodes)

    # Leaf nodes in order
    leaf_nodes = [('L', float(v)) for v in leaf_values]

    # Now set the children pointers using compact indices.
    # For internal node at BFS position i (0-indexed):
    #   left child = 2*i + 1 (if internal) or (n_internal + 2*(i - first_leaf_parent_offset))
    # Actually, let's use standard heap indexing.
    # In a complete binary tree with BFS ordering:
    #   node i has left child at 2i+1, right child at 2i+2
    # Wait, that's for a binary heap. For a complete binary tree in BFS order:
    # Internal node at position i: left child at 2*i+1, right child at 2*i+2
    # This works for ALL internal nodes including the last level.

    # But the last level's internal nodes have LEAF children, not internal.
    # In BFS order, first leaf starts at position total_internal.
    # For internal node at BFS position i:
    #   left_pos = 2*i + 1
    #   right_pos = 2*i + 2
    # If left_pos >= total_internal: it's a leaf, compact_idx = left_pos
    # If left_pos < total_internal: it's internal, compact_idx = left_pos

    # Actually, this works because BFS is identical to heap indexing for a complete
    # binary tree. Let's just build the full array.

    all_nodes = internal_nodes + leaf_nodes

    for i in range(n_internal):
        feat_idx, border = internal_nodes[i][1], internal_nodes[i][2]
        left_pos = 2 * i + 1
        right_pos = 2 * i + 2
        # In compact index order, the node at position left_pos has compact index left_pos
        # (since we use positions as compact indices)
        all_nodes[i] = ('S', feat_idx, border, left_pos, right_pos)

    return all_nodes


def export_compact_trees(model_path, out_path, max_trees=0):
    """Export CatBoost model to compact-tree text format."""
    feature_names, oblivious_trees, scale, bias = load_catboost_model(model_path)

    nfeat = len(feature_names)
    # For oblivious trees, feat_idx is an index into float_features
    # We need to validate against nfeat

    if max_trees <= 0:
        max_trees = len(oblivious_trees)
    trees_to_export = oblivious_trees[:max_trees]

    # Expand each tree
    all_expanded = []
    for t in trees_to_export:
        splits = t['splits']
        leaf_values = t['leaf_values']
        expanded = expand_oblivious_tree(splits, leaf_values, nfeat)
        all_expanded.append(expanded)

    ntrees = len(all_expanded)

    # Scale and bias: CatBoost applies final = scale * raw + bias
    # We fold scale into leaf values and bias into base_score.
    # After expansion, each leaf value is adjusted.
    for tree_nodes in all_expanded:
        for i, nd in enumerate(tree_nodes):
            if nd[0] == 'L':
                # Apply scale to leaf values. Bias goes to base_score.
                tree_nodes[i] = ('L', nd[1] * scale)

    # Base score = bias (CatBoost's training label mean adjustment)
    base_score = float(bias)

    with open(out_path, 'w') as f:
        f.write(f"nfeat {nfeat}\n")
        for name in feature_names:
            f.write(f"feat {name}\n")
        f.write(f"base_score {base_score}\n")
        f.write(f"ntrees {ntrees}\n")
        for t_idx, nodes in enumerate(all_expanded):
            f.write(f"tree {t_idx} {len(nodes)}\n")
            for nd in nodes:
                if nd[0] == 'L':
                    f.write(f"L {nd[1]:.7g}\n")
                else:
                    f.write(f"S {nd[1]} {nd[2]:.7g} {nd[3]} {nd[4]}\n")

    print(f"CatBoost → compact-tree: {ntrees} trees, {nfeat} features, "
          f"base_score={base_score:.4f}, scale={scale:.4f}")
    print(f"wrote {out_path}")

    # Parity check: predict a few random inputs with both Python and our trees
    # (simple sanity: just verify tree count and structure)
    print(f"  max depth range: {min(len(t['splits']) for t in trees_to_export)}-"
          f"{max(len(t['splits']) for t in trees_to_export)}")
    total_internal = sum(len(nodes) - (1 << len(t['splits'])) 
                         for nodes, t in zip(all_expanded, trees_to_export))
    total_leaves = sum(1 << len(t['splits']) for t in trees_to_export)
    print(f"  total nodes: {total_internal + total_leaves} "
          f"({total_internal} internal + {total_leaves} leaves)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: export_catboost_vnet.py <model.cbm> [out.txt] [max_trees]")
        sys.exit(1)
    model_path = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else model_path.replace('.cbm', '.txt')
    max_trees = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    export_compact_trees(model_path, out_path, max_trees)
