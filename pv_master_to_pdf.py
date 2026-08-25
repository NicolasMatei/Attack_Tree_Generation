#!/usr/bin/env python3
"""
pv_master_to_pdf.py

Takes as input the "master tree" JSON file produced by
pv_json_merge_master.py (one or more goals, each with a merged derivation
tree carrying a "relation" field ("and"/"or") on its input/output nodes)
and generates a SINGLE PDF with Graphviz.

The master tree can contain several goals (so several roots): it is not
a single tree but a forest. Rather than simply placing the trees side by
side (one page per goal), this script draws them all in the same graph
and MERGES identical subtrees: if the same node (same io/pi_id/term
triple, same AND/OR relation, and the same children recursively) appears
in several places -- whether in two branches of the same goal or in two
different goals -- it is only drawn once, with several incoming arrows.
In practice, this typically makes leaves and their direct parents
converge, since they are often shared across several derivations.

Visually:
    - red node    = goal (root, "GOAL")
    - blue node   = output ("output")
    - yellow node = input ("input")
    - green diamond  "AND" = conjunctive gate (all children required)
    - orange diamond "OR"  = disjunctive gate (one child is enough)

The AND/OR gate is only drawn when a node has at least 2 children (with
a single child, the AND/OR question doesn't arise).

Requirements:
    pip install graphviz
    + the Graphviz 'dot' binary installed on the system

Usage:
    python3 pv_master_to_pdf.py master_tree.json master_tree.pdf
"""

import argparse
import itertools
import json
import os
import re
import sys
import textwrap

try:
    import graphviz
except ImportError:
    sys.exit(
        "The python module 'graphviz' is required: pip install graphviz\n"
        "You also need the Graphviz 'dot' binary installed on your system "
        "(e.g. sudo dnf install graphviz / sudo apt install graphviz)."
    )

NL = "\\n"  # literal newline for DOT labels
WRAP_WIDTH = 40

ATTACKER_WRAPPER_RE = re.compile(r"^\s*attacker\s*\((.*)\)\s*$", re.IGNORECASE | re.DOTALL)

STYLE = {
    "goal": {
        "shape": "box",
        "style": "filled,bold",
        "fillcolor": "#f28b82",
        "fontname": "Helvetica-Bold",
        "fontsize": "11",
    },
    "output": {
        "shape": "box",
        "style": "filled,rounded",
        "fillcolor": "#aecbfa",
        "fontname": "Helvetica",
        "fontsize": "10",
    },
    "input": {
        "shape": "box",
        "style": "filled,rounded,dashed",
        "fillcolor": "#fdd663",
        "fontname": "Helvetica",
        "fontsize": "10",
    },
    "unknown": {
        "shape": "box",
        "style": "filled",
        "fillcolor": "#f1f3f4",
        "fontname": "Helvetica",
        "fontsize": "9",
    },
    "attacker_step": {
        "shape": "box",
        "style": "filled",
        "fillcolor": "#ccff90",
        "fontname": "Helvetica-Oblique",
        "fontsize": "10",
    },
    "attacker_reasoning": {
        "shape": "box",
        "style": "filled",
        "fillcolor": "#ccff90",
        "fontname": "Helvetica",
        "fontsize": "9",
    },
    "and_gate": {
        "shape": "diamond",
        "style": "filled",
        "fillcolor": "#a5d6a7",
        "fontname": "Helvetica-Bold",
        "fontsize": "9",
    },
    "or_gate": {
        "shape": "diamond",
        "style": "filled",
        "fillcolor": "#ffcc80",
        "fontname": "Helvetica-Bold",
        "fontsize": "9",
    },
    "no_derivation": {
        "shape": "box",
        "style": "filled",
        "fillcolor": "#ccff90",
        "fontname": "Helvetica",
        "fontsize": "10",
    },
}


def wrap(text, width=WRAP_WIDTH):
    if not text:
        return ""
    return NL.join(textwrap.wrap(str(text), width))


def extract_term(fact):
    """Strip the 'attacker(...)' wrapper off a fact for display in the goal node."""
    if not fact:
        return fact
    s = str(fact).strip()
    m = ATTACKER_WRAPPER_RE.match(s)
    return m.group(1).strip() if m else s


def goal_label(fact):
    return f"GOAL{NL}{wrap(extract_term(fact))}"


def leaf_label(node):
    io = node.get("io")
    pi_id = node.get("pi_id")
    term = node.get("term")

    if io == "output":
        header = f"Output {{{pi_id}}}" if pi_id is not None else "Output"
    elif io == "input":
        header = f"Input {{{pi_id}}}" if pi_id is not None else "Input"
    elif io in ("attacker_step", "attacker_reasoning"):
        # Raisonnement interne de l'attaquant (pas d'action réseau, pas de
        # pi-id) : le terme est déjà explicite, pas besoin de préfixer par
        # le nom brut de la catégorie ("attacker_step"/"attacker_reasoning"),
        # qui n'apporterait qu'un mot technique confus dans la figure.
        header = None
    else:
        header = str(io or "?")

    body = wrap(term) if term else ""
    if header is None:
        return body or "?"
    return f"{header}{NL}{body}" if body else header


def leaf_style(node):
    io = node.get("io")
    return STYLE.get(io, STYLE["unknown"])


def node_signature(node, is_root=False):
    """Canonical, deterministic signature of a (sub)node, used to detect
    identical subtrees anywhere in the forest (same goal or different
    goals). Two nodes have the same signature if and only if everything
    displayed below them is identical: same type/values, same AND/OR
    relation, and the same children (recursively, order-independent)."""
    children_sigs = tuple(sorted(
        node_signature(c) for c in (node.get("children") or [])
    ))
    if is_root:
        return ("goal", node.get("fact"), children_sigs)
    return (
        node.get("io"),
        node.get("pi_id"),
        node.get("term"),
        node.get("relation", "and"),
        children_sigs,
    )


def add_gate(dot, counter, parent_id, relation):
    """Inserts an AND/OR diamond between a node and its children (used
    only when there are at least 2 children)."""
    gate_id = f"g{next(counter)}"
    if relation == "or":
        dot.node(gate_id, label="OR", **STYLE["or_gate"])
    else:
        dot.node(gate_id, label="AND", **STYLE["and_gate"])
    dot.edge(parent_id, gate_id, arrowhead="none")
    return gate_id


def build_node(dot, node, memo, counter, is_root=False):
    """Builds (or reuses) the Graphviz node corresponding to `node`.

    If a strictly identical node (same full signature, leaves included)
    has already been built elsewhere in the graph -- whether in another
    branch of the same goal or in another goal -- its existing id is
    returned without recreating anything: this is what merges the common
    parts of several derivations.
    """
    sig = node_signature(node, is_root)
    if sig in memo:
        return memo[sig]

    node_id = f"n{next(counter)}"
    if is_root:
        dot.node(node_id, label=goal_label(node.get("fact", "")), **STYLE["goal"])
    else:
        dot.node(node_id, label=leaf_label(node), **leaf_style(node))
    memo[sig] = node_id

    children = node.get("children") or []
    # The root never has a "relation" field (it is left untouched by the
    # merge script): it defaults to "and", consistent with the original
    # behavior (purely conjunctive).
    relation = "and" if is_root else node.get("relation", "and")

    if len(children) >= 2:
        gate_id = add_gate(dot, counter, node_id, relation)
        for child in children:
            child_id = build_node(dot, child, memo, counter)
            dot.edge(gate_id, child_id)
    else:
        for child in children:
            child_id = build_node(dot, child, memo, counter)
            dot.edge(node_id, child_id)

    return node_id


def build_master_graph(master):
    dot = graphviz.Digraph(comment="Master tree", format="pdf")
    dot.attr(rankdir="TB")
    dot.attr(
        label="Master tree -- all goals (shared subtrees merged)",
        labelloc="t",
        fontsize="14",
        fontname="Helvetica-Bold",
    )
    dot.attr("node", margin="0.15,0.1")

    counter = itertools.count()
    memo = {}

    for goal_entry in master.get("goals", []):
        derivation = goal_entry.get("derivation")
        if derivation is not None:
            build_node(dot, derivation, memo, counter, is_root=True)

    for entry in master.get("unresolved", []):
        node_id = f"nu{next(counter)}"
        label = f"GOAL{NL}{wrap(entry.get('query', ''))}{NL}(no derivation)"
        dot.node(node_id, label=label, **STYLE["no_derivation"])

    return dot


def main():
    parser = argparse.ArgumentParser(
        description="Generates a single PDF merging all goals of the master "
        "tree into one graph, sharing identical subtrees (typically leaves "
        "and their direct parents, common to several derivations)."
    )
    parser.add_argument("master_json", help="Master tree JSON file (from pv_json_merge_master.py)")
    parser.add_argument("output_file", help="Output PDF file")
    args = parser.parse_args()

    if not os.path.isfile(args.master_json):
        sys.exit(f"Error: input file not found: {args.master_json}")

    with open(args.master_json, "r", encoding="utf-8") as f:
        master = json.load(f)

    if not master.get("goals") and not master.get("unresolved"):
        sys.exit("No goal found in the master tree.")

    out_dir = os.path.dirname(os.path.abspath(args.output_file))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    stub, ext = os.path.splitext(args.output_file)
    fmt = ext.lstrip(".").lower() or "pdf"

    dot = build_master_graph(master)
    dot.format = fmt
    rendered_path = dot.render(filename=stub, cleanup=True)

    n_goals = len(master.get("goals", []))
    n_unresolved = len(master.get("unresolved", []))
    print(f"Goals with derivation: {n_goals}, without derivation: {n_unresolved}")
    print(f"Merged graph written to '{rendered_path}'.")


if __name__ == "__main__":
    main()