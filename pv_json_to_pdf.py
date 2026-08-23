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


import re

NL = "\\n"  # newline littéral pour les labels DOT (pas un vrai '\n')
WRAP_WIDTH = 45

# Motifs de faits qu'on ne veut pas afficher dans les labels
# (ex: "attacker(secretcondition[])", "attacker(hash(nonce[],seed[]))")
HIDDEN_FACT_PATTERNS = [
    re.compile(r"attacker\(secretcondition"),
    re.compile(r"attacker\(hash\("),
]


def is_hidden_fact(fact):
    """Renvoie True si le fait ne doit pas être affiché dans le PDF."""
    if not fact:
        return False
    return any(p.search(str(fact)) for p in HIDDEN_FACT_PATTERNS)


# Mots à retirer entièrement de tout texte affiché dans les labels
FORBIDDEN_WORDS_RE = re.compile(r"\b(attacker|input|premise)\b", re.IGNORECASE)


def remove_calls(s, keyword):
    """Retire toutes les occurrences de 'keyword(...)' d'une chaîne, en
    gérant correctement les parenthèses imbriquées (ex: 'attacker(hash(a,b))').
    """
    pattern = re.compile(r"\b" + keyword + r"\s*\(", re.IGNORECASE)
    out = []
    i = 0
    while True:
        m = pattern.search(s, i)
        if not m:
            out.append(s[i:])
            break
        out.append(s[i:m.start()])
        depth = 1
        j = m.end()
        while j < len(s) and depth > 0:
            if s[j] == "(":
                depth += 1
            elif s[j] == ")":
                depth -= 1
            j += 1
        i = j
    return "".join(out)


# Motifs d'annotations à retirer entièrement, quel que soit le noeud
# (ex: "[clause 3]", "[Clause #12]")
CLAUSE_TAG_RE = re.compile(r"\[\s*clause[^\]]*\]", re.IGNORECASE)


def clean_text(s):
    """Retire les mots interdits ('attacker', 'input', 'premise') et le
    symbole '=>' d'une chaîne, puis nettoie les espaces superflus.

    Certaines tournures récurrentes sont réécrites AVANT le retrait mot à
    mot, pour éviter des phrases bancales du style
    "received from the at {1}" (au lieu de "received at {1}")."""
    if not s:
        return s
    s = str(s)

    # --- Exceptions de phrase, à traiter avant le retrait générique ---
    # "... is received from the attacker at input {N}" -> "... is received at {N}"
    s = re.sub(r"\bfrom the attacker at input\b", "at", s, flags=re.IGNORECASE)
    # "... may be sent to the attacker at output {N}" -> "... may be sent at output {N}"
    s = re.sub(r"\bto the attacker at output\b", "at output", s, flags=re.IGNORECASE)
    # variantes plus génériques sans "at input"/"at output" juste après
    s = re.sub(r"\bfrom the attacker\b", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\bto the attacker\b", "", s, flags=re.IGNORECASE)

    # --- Retrait des annotations "[clause ...]" ---
    s = CLAUSE_TAG_RE.sub("", s)

    # --- Retrait des prédicats complets "attacker(...)" et "premise(...)" ---
    # (gère aussi les cas imbriqués comme "attacker(hash(...))")
    s = remove_calls(s, "attacker")
    s = remove_calls(s, "premise")

    # --- Retrait générique des mots interdits restants ---
    s = FORBIDDEN_WORDS_RE.sub("", s)
    s = s.replace("=>", "")

    # --- Nettoyage final ---
    s = re.sub(r",\s*,", ",", s)          # virgules doublées ("a, , b" -> "a, b")
    s = re.sub(r"\(\s*,\s*", "(", s)       # virgule juste après une parenthèse ouvrante
    s = re.sub(r",\s*\)", ")", s)          # virgule juste avant une parenthèse fermante
    s = re.sub(r"\s{2,}", " ", s)
    s = re.sub(r"\(\s*\)", "", s)  # parenthèses vides laissées par le nettoyage
    s = re.sub(r"\{\s*\}", "", s)  # accolades vides laissées par le nettoyage
    s = re.sub(r"^\s*,\s*", "", s)         # virgule résiduelle en tout début de chaîne
    s = re.sub(r"\s*,\s*$", "", s)         # virgule résiduelle en toute fin de chaîne
    return s.strip()

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
        fact = node.get("fact", "")
        if is_hidden_fact(fact):
            return "GOAL"
        return f"GOAL{NL}{wrap(clean_text(fact))}"

    if t == "step":
        description = node.get("description")
        fact = node.get("fact", "")
        if description:
            # La description contient déjà l'information du fait ;
            # on ne la répète pas en dessous.
            return wrap(clean_text(description))
        if not is_hidden_fact(fact):
            return wrap(clean_text(fact))
        return ""

    if t == "premise":
        parts = []
        if node.get("description"):
            parts.append(wrap(clean_text(node["description"])))
        fact = node.get("fact", "")
        if not is_hidden_fact(fact):
            parts.append(wrap(clean_text(fact)))
        return NL.join(p for p in parts if p)

    if t == "duplicate":
        fact = node.get("fact", "")
        if is_hidden_fact(fact):
            return "duplicate"
        return f"duplicate{NL}{wrap(clean_text(fact))}"

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