#!/usr/bin/env python3
"""
pv_json_to_pdf.py

Prend en entrée un dossier de fichiers JSON (typiquement la sortie de
decompose_pv_edges.py) et génère, pour chaque fichier, un PDF de l'arbre
de dérivation avec Graphviz.

Prérequis :
    pip install graphviz
    + le binaire Graphviz 'dot' installé sur le système
      (ex : sudo dnf install graphviz   /   sudo apt install graphviz)

Usage:
    python3 pv_json_to_pdf.py dossier_json_entree dossier_pdf_sortie

Exemple:
    python3 pv_json_to_pdf.py arbres_decomposes/ pdf/
"""

import argparse
import itertools
import json
import os
import sys
import textwrap

try:
    import graphviz
except ImportError:
    sys.exit(
        "Le module python 'graphviz' est requis : pip install graphviz\n"
        "Il faut aussi que le binaire Graphviz 'dot' soit installé sur le système "
        "(ex : sudo dnf install graphviz / sudo apt install graphviz)."
    )


NL = "\\n"  # newline littéral pour les labels DOT (pas un vrai '\n')
WRAP_WIDTH = 45

# Style graphique par type de noeud
STYLE = {
    "goal": {
        "shape": "box",
        "style": "filled,bold",
        "fillcolor": "#f28b82",
        "fontname": "Helvetica-Bold",
        "fontsize": "11",
    },
    "step": {
        "shape": "box",
        "style": "filled,rounded",
        "fillcolor": "#aecbfa",
        "fontname": "Helvetica",
        "fontsize": "10",
    },
    "premise": {
        "shape": "box",
        "style": "filled,rounded,dashed",
        "fillcolor": "#fdd663",
        "fontname": "Helvetica",
        "fontsize": "10",
    },
    "duplicate": {
        "shape": "box",
        "style": "filled,dotted",
        "fillcolor": "#e8eaed",
        "fontcolor": "#5f6368",
        "fontname": "Helvetica-Oblique",
        "fontsize": "9",
    },
    "unknown": {
        "shape": "box",
        "style": "filled",
        "fillcolor": "white",
        "fontname": "Helvetica",
        "fontsize": "9",
    },
}


def wrap(text, width=WRAP_WIDTH):
    if not text:
        return ""
    return NL.join(textwrap.wrap(str(text), width))


def node_label(node):
    t = node.get("type")

    if t == "goal":
        return f"GOAL{NL}{wrap(node.get('fact', ''))}"

    if t == "step":
        parts = []
        if node.get("clause") is not None:
            parts.append(f"[clause {node['clause']}]")
        if node.get("description"):
            parts.append(wrap(node["description"]))
        parts.append("=> " + wrap(node.get("fact", "")))
        return NL.join(parts)

    if t == "premise":
        parts = [f"premise (input {{{node.get('input_index', '?')}}})"]
        if node.get("description"):
            parts.append(wrap(node["description"]))
        parts.append(wrap(node.get("fact", "")))
        return NL.join(parts)

    if t == "duplicate":
        return f"duplicate{NL}{wrap(node.get('fact', ''))}"

    # type inconnu / fallback
    raw = node.get("raw") or json.dumps(node, ensure_ascii=False)
    return wrap(raw)


def add_node_recursive(dot, node, counter, parent_id=None):
    node_id = f"n{next(counter)}"
    node_type = node.get("type", "unknown")
    style = STYLE.get(node_type, STYLE["unknown"])

    dot.node(node_id, label=node_label(node), **style)

    if parent_id is not None:
        dot.edge(parent_id, node_id)

    for child in node.get("children", []) or []:
        add_node_recursive(dot, child, counter, node_id)

    return node_id


def build_graph(entry, fmt="pdf"):
    dot = graphviz.Digraph(
        comment=entry.get("query", ""),
        format=fmt,
    )
    dot.attr(rankdir="TB")
    dot.attr(
        label=wrap(entry.get("query", ""), width=90),
        labelloc="t",
        fontsize="12",
        fontname="Helvetica-Bold",
    )
    dot.attr("node", margin="0.15,0.1")

    counter = itertools.count()

    if entry.get("has_derivation") and entry.get("derivation") is not None:
        add_node_recursive(dot, entry["derivation"], counter)
    else:
        # Pas de dérivation (requête prouvée, pas d'attaque trouvée)
        dot.node(
            "n0",
            label=f"Pas de dérivation{NL}(requête prouvée / pas d'attaque trouvée)",
            shape="box",
            style="filled",
            fillcolor="#ccff90",
            fontname="Helvetica",
            fontsize="10",
        )

    return dot


def safe_stub(filename):
    return os.path.splitext(filename)[0]


def main():
    parser = argparse.ArgumentParser(
        description="Génère un PDF par arbre de dérivation JSON, avec Graphviz."
    )
    parser.add_argument("input_dir", help="Dossier contenant les JSON d'entrée")
    parser.add_argument("output_dir", help="Dossier où écrire les PDF")
    parser.add_argument(
        "--format",
        default="pdf",
        help="Format de sortie Graphviz (défaut : pdf ; ex. png, svg)",
    )
    args = parser.parse_args()

    if not os.path.isdir(args.input_dir):
        sys.exit(f"Erreur : dossier d'entrée introuvable : {args.input_dir}")

    os.makedirs(args.output_dir, exist_ok=True)

    json_files = sorted(f for f in os.listdir(args.input_dir) if f.endswith(".json"))
    if not json_files:
        print(f"Aucun fichier .json trouvé dans '{args.input_dir}'.")
        return

    ok, failed = 0, 0
    for fname in json_files:
        in_path = os.path.join(args.input_dir, fname)
        try:
            with open(in_path, "r", encoding="utf-8") as f:
                entry = json.load(f)

            dot = build_graph(entry, fmt=args.format)

            stub = safe_stub(fname)
            out_path_no_ext = os.path.join(args.output_dir, stub)

            # graphviz.render() écrit un fichier source .gv puis produit le
            # fichier de sortie (.pdf) ; on nettoie le fichier source ensuite.
            rendered_path = dot.render(filename=out_path_no_ext, cleanup=True)
            print(f"  - {fname} -> {rendered_path}")
            ok += 1
        except Exception as e:
            print(f"  - {fname} : ÉCHEC ({e})", file=sys.stderr)
            failed += 1

    print(f"\nTerminé : {ok} PDF généré(s), {failed} échec(s). Sortie dans '{args.output_dir}'.")


if __name__ == "__main__":
    main()
