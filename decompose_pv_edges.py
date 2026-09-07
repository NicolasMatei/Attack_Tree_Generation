#!/usr/bin/env python3
"""
decompose_pv_edges.py

Prend en entrée le dossier de fichiers JSON produits par
pv_derivation_to_json.py et en recrée d'autres JSON dans lesquels les
noeuds "step" combinant plusieurs prémisses (texte du type
"If <premisse_1>, <premisse_2>, ..., then <conclusion>.") sont décomposés :

  - le noeud parent ne garde que le fragment de conclusion
  - un noeud intermédiaire "premise" est inséré par prémisse, chacun
    conservant en enfant le sous-arbre original qui prouvait cette prémisse.

Deux familles de prémisses/conclusions sont reconnues :

  - réseau  : "the message <m> is received from the attacker at input {N}"
              "the message <m> may be sent to the attacker at output {N}"
  - table   : "the entry <f> is in a table at get {N}"
              "the entry <f> may be inserted in a table at insert {N}"

Les noeuds de prémisse portent :
  - "input_index"  pour une prémisse réseau (input)
  - "get_index"    pour une prémisse table (get)
Le noeud parent conserve :
  - "output_index" si la conclusion est un envoi réseau
  - "insert_index" si la conclusion est une insertion en table

La structure globale de l'arbre (qui prouve quoi, combien de branches)
est conservée : on ne fait qu'expliciter chaque arête au lieu de tout
regrouper dans le texte du noeud parent.

Usage:
    python3 decompose_pv_edges.py dossier_json_entree dossier_json_sortie \
        [--premise-order reverse|forward]

Exemple:
    python3 decompose_pv_edges.py arbres/ arbres_decomposes/
"""

import argparse
import json
import os
import re
import sys


# Coupe juste après une accolade fermante suivie d'une virgule : ça isole
# chaque fragment "... input {N}" / "... output {N}" sans jamais couper à
# l'intérieur d'un terme comme enc(x_4,sk[]) (la virgule y est précédée
# d'un caractère quelconque, jamais d'un "}").
FRAGMENT_SPLIT_RE = re.compile(r'(?<=\})\s*,\s*')

# Préfixe de conjonction laissé par le découpage sur le tout premier
# fragment d'une description ("If the message ..."). On ne retire QUE ce
# "If " ; le "then " du fragment de conclusion est conservé tel quel, comme
# c'était déjà le cas dans les arbres produits jusqu'ici.
LEADING_IF_RE = re.compile(r'^\s*if\s+', re.IGNORECASE)

# --- prémisses réseau ---
PREMISE_INPUT_RE = re.compile(
    r'the message (?P<msg>.+) is received from the attacker at input \{(?P<idx>\d+)\}\s*$'
)
# --- prémisses table (get) ---
PREMISE_TABLE_RE = re.compile(
    r'the entry (?P<msg>.+) is in a table at get \{(?P<idx>\d+)\}\s*$'
)
# --- conclusions réseau ---
CONCLUSION_OUTPUT_RE = re.compile(
    r'the message (?P<msg>.+) may be sent to the attacker at output \{(?P<idx>\d+)\}\s*$'
)
# --- conclusions table (insert) ---
CONCLUSION_INSERT_RE = re.compile(
    r'the entry (?P<msg>.+) may be inserted in a table at insert \{(?P<idx>\d+)\}\s*$'
)

# Champ à utiliser sur le noeud "premise" selon le type de prémisse.
PREMISE_INDEX_FIELD = {
    "premise_input": "input_index",
    "premise_table": "get_index",
}
# Champ à utiliser sur le noeud parent selon le type de conclusion.
CONCLUSION_INDEX_FIELD = {
    "conclusion_output": "output_index",
    "conclusion_insert": "insert_index",
}


def split_description(desc):
    """Découpe une description de clause en fragments (prémisses + conclusion),
    en retirant le préfixe "If " résiduel laissé par le découpage."""
    desc = desc.strip()
    if desc.endswith('.'):
        desc = desc[:-1]
    fragments = FRAGMENT_SPLIT_RE.split(desc)
    cleaned = []
    for f in fragments:
        f = f.strip()
        if not f:
            continue
        f = LEADING_IF_RE.sub('', f).strip()
        cleaned.append(f)
    return cleaned


def classify_fragment(fragment):
    """Retourne (kind, msg, idx) où kind est l'un de :
    'premise_input', 'premise_table', 'conclusion_output', 'conclusion_insert',
    ou (None, None, None) si le fragment n'est reconnu dans aucune catégorie."""
    m = PREMISE_INPUT_RE.search(fragment)
    if m:
        return "premise_input", m.group("msg"), m.group("idx")
    m = PREMISE_TABLE_RE.search(fragment)
    if m:
        return "premise_table", m.group("msg"), m.group("idx")
    m = CONCLUSION_OUTPUT_RE.search(fragment)
    if m:
        return "conclusion_output", m.group("msg"), m.group("idx")
    m = CONCLUSION_INSERT_RE.search(fragment)
    if m:
        return "conclusion_insert", m.group("msg"), m.group("idx")
    return None, None, None


def is_premise_kind(kind):
    return kind in PREMISE_INDEX_FIELD


def is_conclusion_kind(kind):
    return kind in CONCLUSION_INDEX_FIELD


def decompose_node(node, premise_order="reverse", stats=None):
    """
    Transforme récursivement un noeud de l'arbre. Retourne un nouveau noeud
    (ne modifie pas l'original en place).
    """
    if stats is None:
        stats = {"decomposed": 0, "unchanged_step": 0}

    if not isinstance(node, dict):
        return node

    node_type = node.get("type")
    children = node.get("children", [])

    if node_type == "step" and "description" in node:
        fragments = split_description(node["description"])
        classified = [classify_fragment(f) for f in fragments]

        premises = [
            (frag, kind, msg, idx)
            for frag, (kind, msg, idx) in zip(fragments, classified)
            if is_premise_kind(kind)
        ]
        conclusions = [
            (frag, kind, msg, idx)
            for frag, (kind, msg, idx) in zip(fragments, classified)
            if is_conclusion_kind(kind)
        ]

        if len(conclusions) == 1 and len(premises) > 0 and len(premises) == len(children):
            concl_frag, concl_kind, concl_msg, concl_idx = conclusions[0]

            ordered_premises = (
                list(reversed(premises)) if premise_order == "reverse" else premises
            )

            new_children = []
            for (prem_frag, prem_kind, prem_msg, prem_idx), child in zip(ordered_premises, children):
                decomposed_child = decompose_node(child, premise_order, stats)
                premise_node = {
                    "type": "premise",
                    "description": prem_frag,
                    PREMISE_INDEX_FIELD[prem_kind]: int(prem_idx),
                    "fact": child.get("fact"),
                    "clause": node.get("clause"),
                    "children": [decomposed_child],
                }
                new_children.append(premise_node)

            stats["decomposed"] += 1
            new_node = dict(node)
            new_node["description"] = concl_frag
            new_node[CONCLUSION_INDEX_FIELD[concl_kind]] = int(concl_idx)
            new_node["children"] = new_children
            return new_node

        # Motif non reconnu ou nombre de prémisses != nombre d'enfants :
        # on laisse le noeud tel quel mais on continue à décomposer en dessous.
        # (un step "may be inserted" en feuille, sans prémisse et sans enfant,
        # n'est pas un échec de décomposition : on ne le compte pas comme tel)
        if children and (premises or len(conclusions) != 1):
            stats["unchanged_step"] += 1
        new_node = dict(node)
        new_node["children"] = [decompose_node(c, premise_order, stats) for c in children]
        return new_node

    # goal / duplicate / unknown -> on ne touche pas au noeud, on descend juste
    new_node = dict(node)
    new_node["children"] = [decompose_node(c, premise_order, stats) for c in children]
    return new_node


def process_file(in_path, out_path, premise_order):
    with open(in_path, "r", encoding="utf-8") as f:
        entry = json.load(f)

    stats = {"decomposed": 0, "unchanged_step": 0}

    if entry.get("has_derivation") and entry.get("derivation") is not None:
        entry["derivation"] = decompose_node(entry["derivation"], premise_order, stats)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(entry, f, indent=2, ensure_ascii=False)

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Décompose les noeuds 'step' à prémisses multiples des arbres JSON "
                    "produits par pv_derivation_to_json.py en une chaîne de noeuds."
    )
    parser.add_argument("input_dir", help="Dossier contenant les JSON d'entrée")
    parser.add_argument("output_dir", help="Dossier où écrire les JSON décomposés")
    parser.add_argument(
        "--premise-order",
        choices=["reverse", "forward"],
        default="reverse",
        help="Correspondance entre l'ordre des prémisses dans le texte et l'ordre des "
             "enfants imprimés par ProVerif. 'reverse' (défaut) correspond à ce qui a été "
             "observé dans les exemples fournis ; utilisez 'forward' si ça ne correspond pas.",
    )
    args = parser.parse_args()

    if not os.path.isdir(args.input_dir):
        sys.exit(f"Erreur : dossier d'entrée introuvable : {args.input_dir}")

    os.makedirs(args.output_dir, exist_ok=True)

    json_files = sorted(f for f in os.listdir(args.input_dir) if f.endswith(".json"))
    if not json_files:
        print(f"Aucun fichier .json trouvé dans '{args.input_dir}'.")
        return

    total_decomposed = 0
    total_unchanged = 0

    for fname in json_files:
        in_path = os.path.join(args.input_dir, fname)
        out_path = os.path.join(args.output_dir, fname)
        stats = process_file(in_path, out_path, args.premise_order)
        total_decomposed += stats["decomposed"]
        total_unchanged += stats["unchanged_step"]
        print(
            f"  - {fname}: {stats['decomposed']} noeud(s) décomposé(s), "
            f"{stats['unchanged_step']} laissé(s) tel quel (motif non reconnu ou "
            f"nombre de prémisses différent du nombre d'enfants)"
        )

    print(
        f"\nTerminé : {len(json_files)} fichier(s) traité(s), "
        f"{total_decomposed} noeud(s) décomposé(s) au total, "
        f"{total_unchanged} laissé(s) inchangé(s). Sortie dans '{args.output_dir}'."
    )


if __name__ == "__main__":
    main()