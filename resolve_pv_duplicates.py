#!/usr/bin/env python3
"""
resolve_pv_duplicates.py

Prend en entrée un dossier de JSON (typiquement la sortie de
decompose_pv_edges.py) et remplace chaque noeud "duplicate" par une copie
du vrai sous-arbre qui prouve le même fait ("fact"), trouvé ailleurs dans
le même arbre de dérivation.

Un noeud "duplicate attacker(X)" apparaît quand ProVerif a déjà prouvé
attacker(X) plus tôt dans la dérivation et ne réimprime pas le sous-arbre
une deuxième fois. Ce script retrouve ce sous-arbre (un noeud "step" avec
le même "fact", ailleurs dans l'arbre) et le recopie à la place du
"duplicate", pour avoir un arbre complet, sans feuille tronquée.

À utiliser dans la chaîne :
    pv_derivation_to_json.py -> decompose_pv_edges.py
        -> resolve_pv_duplicates.py -> pv_json_to_pdf.py

Usage:
    python3 resolve_pv_duplicates.py dossier_json_entree dossier_json_sortie

Exemple:
    python3 resolve_pv_duplicates.py arbres_decomposes/ arbres_resolus/
"""

import argparse
import copy
import json
import os
import re
import sys

# Motif d'un appel "attacker(" pour le repérer où qu'il apparaisse dans un
# texte brut (noeuds "unknown" : "initial knowledge  attacker(I[])",
# "apply 2-proj-3-tuple attacker(pk(skB[]))", ...).
ATTACKER_CALL_RE = re.compile(r"attacker\s*\(", re.IGNORECASE)


def find_fact_string(node):
    """Retourne le fait canonique 'attacker(X)' prouvé par ce noeud.

    - Pour un noeud 'step' (ou tout noeud portant un champ 'fact'), on
      renvoie directement ce champ (comportement d'origine).
    - Pour un noeud 'unknown' (pas de champ 'fact', seulement 'raw'), on
      extrait le premier 'attacker(...)' rencontré dans le texte brut, en
      comptant les parenthèses pour trouver la fermante exacte (les
      termes peuvent être imbriqués, ex: 'attacker(pk(skB[]))').

    Sans cette extraction depuis 'raw', les faits prouvés uniquement par
    un raisonnement interne de l'attaquant (connaissance initiale,
    hypothèse, application/projection de constructeur) ne sont jamais
    indexés, et les 'duplicate' qui les référencent restent non résolus.
    """
    fact = node.get("fact")
    if fact is not None:
        return fact

    raw = node.get("raw")
    if raw:
        m = ATTACKER_CALL_RE.search(raw)
        if m:
            depth = 1
            j = m.end()
            while j < len(raw) and depth > 0:
                if raw[j] == "(":
                    depth += 1
                elif raw[j] == ")":
                    depth -= 1
                j += 1
            return raw[m.start():j]

    return None


def collect_fact_index(node, index):
    """
    Parcourt l'arbre et indexe, pour chaque fait, le premier noeud
    ("step" ou "unknown") qui le prouve. Les noeuds "unknown" (raisonnement
    interne de l'attaquant : connaissance initiale, hypothèse, application
    de constructeur ou de projection) sont inclus car ce sont souvent eux
    qui prouvent les faits référencés par les "duplicate" — pas seulement
    les "step".
    """
    if not isinstance(node, dict):
        return

    if node.get("type") in ("step", "unknown"):
        fact = find_fact_string(node)
        if fact is not None and fact not in index:
            index[fact] = node

    for child in node.get("children", []) or []:
        collect_fact_index(child, index)


def resolve_duplicates(node, index, expanding=None, stats=None):
    """
    Retourne une copie de l'arbre où chaque noeud "duplicate" est remplacé
    par une copie complète du sous-arbre trouvé dans l'index pour le même
    fait. 'expanding' sert de garde-fou contre une éventuelle boucle.
    """
    if expanding is None:
        expanding = frozenset()
    if stats is None:
        stats = {"replaced": 0, "unresolved": 0}

    if not isinstance(node, dict):
        return node

    if node.get("type") == "duplicate":
        fact = node.get("fact")
        target = index.get(fact)

        if target is not None and fact not in expanding:
            replacement = copy.deepcopy(target)
            replacement = resolve_duplicates(
                replacement, index, expanding | {fact}, stats
            )
            stats["replaced"] += 1
            return replacement

        stats["unresolved"] += 1
        return dict(node)  # laissé tel quel : pas trouvé, ou cycle détecté

    new_node = dict(node)
    new_node["children"] = [
        resolve_duplicates(c, index, expanding, stats) for c in node.get("children", []) or []
    ]
    return new_node


def process_entry(entry):
    stats = {"replaced": 0, "unresolved": 0}

    if entry.get("has_derivation") and entry.get("derivation") is not None:
        index = {}
        collect_fact_index(entry["derivation"], index)
        entry["derivation"] = resolve_duplicates(entry["derivation"], index, stats=stats)

    return entry, stats


def main():
    parser = argparse.ArgumentParser(
        description="Remplace les noeuds 'duplicate' par une copie du vrai sous-arbre "
                    "trouvé ailleurs dans le même arbre de dérivation."
    )
    parser.add_argument("input_dir", help="Dossier contenant les JSON d'entrée")
    parser.add_argument("output_dir", help="Dossier où écrire les JSON avec duplicates résolus")
    args = parser.parse_args()

    if not os.path.isdir(args.input_dir):
        sys.exit(f"Erreur : dossier d'entrée introuvable : {args.input_dir}")

    os.makedirs(args.output_dir, exist_ok=True)

    json_files = sorted(f for f in os.listdir(args.input_dir) if f.endswith(".json"))
    if not json_files:
        print(f"Aucun fichier .json trouvé dans '{args.input_dir}'.")
        return

    total_replaced = 0
    total_unresolved = 0

    for fname in json_files:
        in_path = os.path.join(args.input_dir, fname)
        out_path = os.path.join(args.output_dir, fname)

        with open(in_path, "r", encoding="utf-8") as f:
            entry = json.load(f)

        entry, stats = process_entry(entry)

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(entry, f, indent=2, ensure_ascii=False)

        total_replaced += stats["replaced"]
        total_unresolved += stats["unresolved"]

        msg = f"  - {fname}: {stats['replaced']} duplicate(s) remplacé(s)"
        if stats["unresolved"]:
            msg += f", {stats['unresolved']} non résolu(s) (pas trouvé ailleurs, ou cycle)"
        print(msg)

    print(
        f"\nTerminé : {len(json_files)} fichier(s) traité(s), "
        f"{total_replaced} duplicate(s) remplacé(s) au total, "
        f"{total_unresolved} non résolu(s). Sortie dans '{args.output_dir}'."
    )


if __name__ == "__main__":
    main()