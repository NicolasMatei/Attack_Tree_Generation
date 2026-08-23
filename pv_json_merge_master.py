#!/usr/bin/env python3
"""
pv_json_merge_master.py

Prend en entrée un dossier de fichiers JSON "simplifiés" (sortie de
pv_json_simplify.py : chaque noeud non-racine a juste pi_id / io / term /
children, la racine garde type "goal" + fact) et fusionne, pour chaque
but (query / fact) rencontré, TOUTES les dérivations disponibles en un
seul arbre "maître".

Principe de la fusion
----------------------
Chaque arbre d'entrée est purement conjonctif : pour satisfaire un noeud,
il faut satisfaire TOUS ses enfants. En fusionnant plusieurs dérivations
d'un même but, on peut découvrir qu'un même noeud (même triplet
(io, pi_id, term)) est atteint via des ensembles d'enfants différents
selon la dérivation : cela signifie qu'il existe plusieurs façons
alternatives de le satisfaire.

Pour chaque noeud "avec input/output" (donc chaque noeud non-racine) de
l'arbre fusionné, on ajoute un champ "relation" qui vaut :
    - "and" : toutes les dérivations connues qui atteignent ce noeud
      utilisent exactement le même ensemble d'enfants -> il faut
      satisfaire tous les enfants (comme avant, cas conjonctif).
    - "or"  : des dérivations différentes atteignent ce noeud avec des
      ensembles d'enfants différents -> il suffit de satisfaire l'un des
      groupes d'enfants (cas disjonctif : plusieurs preuves alternatives).

La racine ("goal") garde exactement la même forme qu'avant (type, fact,
children), sans champ "relation" : ce champ n'est ajouté qu'aux noeuds
qui portent une donnée input/output (pi_id / io / term).

Usage:
    python3 pv_json_merge_master.py dossier_json_simplifies/ arbre_maitre.json

Exemple:
    python3 pv_json_merge_master.py arbres_simplifies/ arbre_maitre.json
"""

import argparse
import json
import os
import sys
from collections import defaultdict


def node_key(node):
    """Clé d'identité d'un noeud non-racine : (io, pi_id, term)."""
    return (node.get("io"), node.get("pi_id"), node.get("term"))


def merge_node_occurrences(occurrences):
    """Fusionne plusieurs occurrences d'UN MÊME noeud (même clé (io, pi_id,
    term), rencontrées dans différentes dérivations) en un seul noeud.

    Ajoute le champ "relation" ("and" ou "or") décrivant comment les
    enfants DE CE NOEUD doivent être combinés.
    """
    base = occurrences[0]
    child_lists = [occ.get("children") or [] for occ in occurrences]
    merged_children, relation = merge_child_lists(child_lists)
    return {
        "io": base.get("io"),
        "pi_id": base.get("pi_id"),
        "term": base.get("term"),
        "relation": relation,
        "children": merged_children,
    }


def merge_child_lists(child_lists):
    """Fusionne les listes d'enfants provenant de plusieurs dérivations
    atteignant le même noeud parent.

    Retourne (children_fusionnés, relation) où relation vaut :
        - "and" si toutes les dérivations utilisent le même ensemble
          d'enfants (ou s'il n'y a qu'une seule dérivation connue) ;
        - "or"  si au moins deux dérivations utilisent des ensembles
          d'enfants différents.
    """
    # Aucune dérivation, ou une seule -> conjonctif par défaut (cas d'origine).
    if len(child_lists) <= 1:
        children = child_lists[0] if child_lists else []
        by_key = defaultdict(list)
        order = []
        for c in children:
            k = node_key(c)
            if k not in by_key:
                order.append(k)
            by_key[k].append(c)
        merged = [merge_node_occurrences(by_key[k]) for k in order]
        return merged, "and"

    # Signature (ensemble des clés d'enfants) de chaque dérivation, pour
    # savoir si toutes les dérivations utilisent le même ensemble d'enfants.
    signatures = [frozenset(node_key(c) for c in lst) for lst in child_lists]
    relation = "and" if len(set(signatures)) == 1 else "or"

    # Regroupe toutes les occurrences (toutes dérivations confondues) par
    # clé de noeud, pour fusionner récursivement chaque enfant partagé.
    by_key = defaultdict(list)
    order = []
    for lst in child_lists:
        for c in lst:
            k = node_key(c)
            if k not in by_key:
                order.append(k)
            by_key[k].append(c)

    merged_children = [merge_node_occurrences(by_key[k]) for k in order]
    return merged_children, relation


def merge_goal_group(entries):
    """Fusionne les dérivations de plusieurs entrées partageant le même
    but (même fait racine). La racine garde sa forme d'origine, sans
    champ 'relation'."""
    base_derivation = entries[0]["derivation"]
    child_lists = [e["derivation"].get("children") or [] for e in entries]
    merged_children, _root_relation = merge_child_lists(child_lists)
    # La relation calculée pour la racine n'est volontairement pas stockée :
    # seuls les noeuds "avec input/output" reçoivent le champ 'relation'.

    return {
        "type": base_derivation.get("type", "goal"),
        "fact": base_derivation.get("fact"),
        "children": merged_children,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Fusionne un dossier d'arbres de dérivation simplifiés en "
        "un arbre maître conjonctif/disjonctif (champ 'relation' and/or)."
    )
    parser.add_argument("input_dir", help="Dossier contenant les JSON simplifiés")
    parser.add_argument("output_file", help="Fichier JSON de sortie (arbre maître)")
    args = parser.parse_args()

    if not os.path.isdir(args.input_dir):
        sys.exit(f"Erreur : dossier d'entrée introuvable : {args.input_dir}")

    json_files = sorted(f for f in os.listdir(args.input_dir) if f.endswith(".json"))
    if not json_files:
        print(f"Aucun fichier .json trouvé dans '{args.input_dir}'.")
        return

    # Regroupe les entrées par but : on utilise le fait racine de la
    # dérivation comme clé (deux fichiers qui prouvent le même fait sont
    # considérés comme deux dérivations alternatives du même but), avec la
    # requête ("query") gardée à titre indicatif.
    groups = defaultdict(list)
    without_derivation = []
    load_errors = []

    for fname in json_files:
        in_path = os.path.join(args.input_dir, fname)
        try:
            with open(in_path, "r", encoding="utf-8") as f:
                entry = json.load(f)
        except Exception as e:
            load_errors.append((fname, str(e)))
            continue

        if entry.get("has_derivation") and entry.get("derivation") is not None:
            root_fact = entry["derivation"].get("fact")
            entry["_source_file"] = fname
            groups[root_fact].append(entry)
        else:
            entry["_source_file"] = fname
            without_derivation.append(entry)

    goals = []
    for root_fact, entries in groups.items():
        merged_derivation = merge_goal_group(entries)
        goals.append({
            "fact": root_fact,
            "query": entries[0].get("query"),
            "source_indices": [e.get("index") for e in entries],
            "source_files": [e["_source_file"] for e in entries],
            "derivation": merged_derivation,
        })

    master = {
        "goals": goals,
        "unresolved": [
            {
                "index": e.get("index"),
                "query": e.get("query"),
                "source_file": e["_source_file"],
            }
            for e in without_derivation
        ],
    }

    with open(args.output_file, "w", encoding="utf-8") as f:
        json.dump(master, f, ensure_ascii=False, indent=2)

    print(f"Buts fusionnés : {len(goals)}")
    for g in goals:
        print(f"  - {g['query']!r} <- {g['source_files']}")
    if without_derivation:
        print(f"Sans dérivation (repris tels quels) : {len(without_derivation)}")
    if load_errors:
        for fname, err in load_errors:
            print(f"  - {fname} : ÉCHEC ({err})", file=sys.stderr)
    print(f"\nArbre maître écrit dans '{args.output_file}'.")


if __name__ == "__main__":
    main()
