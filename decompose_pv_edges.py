#!/usr/bin/env python3
"""
decompose_pv_edges.py

Prend en entrée le dossier de fichiers JSON produits par
pv_derivation_to_json.py et en recrée d'autres JSON dans lesquels les
noeuds "step" combinant plusieurs prémisses (texte du type
"If <premisse_1>, <premisse_2>, ..., then <conclusion>.") sont décomposés :

  - le noeud parent ne garde que le fragment de conclusion
    ("then the message ... may be sent to the attacker at output {N}")
  - un noeud intermédiaire "premise" est inséré par prémisse
    ("the message ... is received from the attacker at input {N}"),
    chacun conservant en enfant le sous-arbre original qui prouvait
    cette prémisse.

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

PREMISE_RE = re.compile(
    r'the message (?P<msg>.+) is received from the attacker at input \{(?P<idx>\d+)\}\s*$'
)
CONCLUSION_RE = re.compile(
    r'the message (?P<msg>.+) may be sent to the attacker at output \{(?P<idx>\d+)\}\s*$'
)


def split_description(desc):
    """Découpe une description de clause en fragments (prémisses + conclusion)."""
    desc = desc.strip()
    if desc.endswith('.'):
        desc = desc[:-1]
    fragments = FRAGMENT_SPLIT_RE.split(desc)
    return [f.strip() for f in fragments if f.strip()]


def classify_fragment(fragment):
    """Retourne ('premise', msg, idx) ou ('conclusion', msg, idx) ou (None, None, None)."""
    m = PREMISE_RE.search(fragment)
    if m:
        return "premise", m.group("msg"), m.group("idx")
    m = CONCLUSION_RE.search(fragment)
    if m:
        return "conclusion", m.group("msg"), m.group("idx")
    return None, None, None


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
            (frag, msg, idx)
            for frag, (kind, msg, idx) in zip(fragments, classified)
            if kind == "premise"
        ]
        conclusions = [
            (frag, msg, idx)
            for frag, (kind, msg, idx) in zip(fragments, classified)
            if kind == "conclusion"
        ]

        if len(conclusions) == 1 and len(premises) > 0 and len(premises) == len(children):
            concl_frag, concl_msg, concl_idx = conclusions[0]

            ordered_premises = (
                list(reversed(premises)) if premise_order == "reverse" else premises
            )

            new_children = []
            for (prem_frag, prem_msg, prem_idx), child in zip(ordered_premises, children):
                decomposed_child = decompose_node(child, premise_order, stats)
                premise_node = {
                    "type": "premise",
                    "description": prem_frag,
                    "input_index": int(prem_idx),
                    "fact": child.get("fact"),
                    "clause": node.get("clause"),
                    "children": [decomposed_child],
                }
                new_children.append(premise_node)

            stats["decomposed"] += 1
            new_node = dict(node)
            new_node["description"] = concl_frag
            new_node["output_index"] = int(concl_idx)
            new_node["children"] = new_children
            return new_node

        # Motif non reconnu ou nombre de prémisses != nombre d'enfants :
        # on laisse le noeud tel quel mais on continue à décomposer en dessous.
        if premises or len(conclusions) != 1:
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
