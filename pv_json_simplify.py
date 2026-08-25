#!/usr/bin/env python3
"""
pv_json_simplify.py

Prend en entrée un dossier de fichiers JSON (arbres de dérivation résolus,
typiquement la sortie de decompose_pv_edges.py) et génère, pour chaque
fichier, une version SIMPLIFIÉE de l'arbre :

    - La racine (noeud "goal") est conservée telle quelle.
    - Chaque autre noeud ("step"/bleu = output, "premise"/jaune = input,
      ainsi que "duplicate"/"unknown" le cas échéant) est réduit à
      3 informations :
        * "pi_id"  : le numéro entre accolades ({N}) de l'input/output
        * "io"     : "input" (jaune) ou "output" (bleu)
        * "term"   : le terme échangé, sans l'enrobage "attacker(...)"

Usage:
    python3 pv_json_simplify.py dossier_json_entree dossier_json_sortie

Exemple:
    python3 pv_json_simplify.py arbres_decomposes/ arbres_simplifies/
"""

import argparse
import json
import os
import re
import sys

# "attacker(...)" -> on ne garde que ce qu'il y a entre les parenthèses.
# Le fait est toujours de la forme "attacker(TERME)" dans les arbres traités
# ici, donc une extraction "premier ( ... dernier )" suffit.
ATTACKER_WRAPPER_RE = re.compile(r"^\s*attacker\s*\((.*)\)\s*$", re.IGNORECASE | re.DOTALL)

# Pour les noeuds "unknown" (pas de champ "fact", seulement "raw"), l'appel
# "attacker(...)" n'enrobe pas toute la chaîne (ex: "hypothesis attacker(nx)",
# "apply 2-proj-3-tuple attacker(pk(skB[]))"). On le repère par sa position
# de départ puis on compte les parenthèses pour trouver la fermante exacte
# (une regex ".*" gourmande casserait sur les termes imbriqués comme
# "attacker(pk(skB[]))").
ATTACKER_START_RE = re.compile(r"attacker\s*\(", re.IGNORECASE)


def unwrap_attacker_anywhere(s):
    """Déplie 'attacker(X)' en 'X' où qu'il apparaisse dans la chaîne,
    en conservant le texte autour (utile pour les raw des noeuds
    'unknown' : 'hypothesis attacker(nx)' -> 'hypothesis nx')."""
    m = ATTACKER_START_RE.search(s)
    if not m:
        return s.strip()
    depth = 1
    j = m.end()
    while j < len(s) and depth > 0:
        if s[j] == "(":
            depth += 1
        elif s[j] == ")":
            depth -= 1
        j += 1
    inner = s[m.end():j - 1]
    return (s[:m.start()] + inner + s[j:]).strip()


def extract_term(fact, raw=None):
    """Retire l'enrobage 'attacker(...)' d'un fait pour ne garder que le terme.

    - Si 'fact' est présent (noeuds step/premise/goal/duplicate), on suppose
      qu'il est intégralement de la forme 'attacker(TERME)' (cas d'origine).
    - Si 'fact' est absent mais 'raw' est fourni (noeuds "unknown"), on
      déplie 'attacker(...)' où qu'il apparaisse dans le texte brut, afin
      que chaque noeud garde une identité distincte (sinon tous les noeuds
      "unknown" collapsent sur le même terme None -> collision dans le
      merge des arbres, voir pv_json_merge_master.py).
    """
    if fact is not None:
        s = str(fact).strip()
        m = ATTACKER_WRAPPER_RE.match(s)
        if m:
            return m.group(1).strip()
        return s
    if raw is not None:
        return unwrap_attacker_anywhere(str(raw))
    return None


DESC_IO_RE = re.compile(r"at\s+(input|output)\s*\{\s*(-?\d+)\s*\}", re.IGNORECASE)


def node_io_and_pi_id(node):
    """Détermine (io, pi_id) pour un noeud.

    On cherche en priorité le motif "at input {N}" / "at output {N}" dans
    la description : c'est la source la plus fiable, car certains noeuds
    (notamment les feuilles) n'ont pas de champ input_index/output_index
    même quand leur description mentionne un output/input.
    À défaut, on se rabat sur les champs input_index / output_index.

    Si aucun des deux ne s'applique et que le noeud est de type "step",
    ce n'est PAS un vrai input/output du protocole mais un calcul interne
    de l'attaquant (ex: "The attacker applies function encrypt.", clause
    sans référence à un canal) : on l'étiquette "attacker_step" plutôt que
    "step" tout court, pour rester cohérent avec le classement fait côté
    rendu PDF (pv_json_to_pdf.py::effective_type) et ne pas laisser croire
    qu'il s'agit d'un vrai échange réseau.

    En tout dernier recours, on se rabat sur le type du noeud lui-même
    (ex: "unknown", "duplicate").
    """
    description = node.get("description")
    if description:
        m = DESC_IO_RE.search(str(description))
        if m:
            return m.group(1).lower(), int(m.group(2))

    if "input_index" in node and node["input_index"] is not None:
        return "input", node["input_index"]
    if "output_index" in node and node["output_index"] is not None:
        return "output", node["output_index"]

    if node.get("type") == "step":
        return "attacker_step", None

    node_type = node.get("type")
    if node_type == "unknown":
        # Raisonnement interne de l'attaquant sans clause dédiée
        # (hypothesis / any / initial knowledge / apply ...). On évite le
        # mot "unknown" dans l'io : il ne veut pas dire "non pris en
        # compte" mais fuiterait tel quel dans le label du noeud lors du
        # rendu du master tree.
        return "attacker_reasoning", None

    return node_type or "attacker_reasoning", None


def simplify_node(node, is_root=False):
    """Transforme récursivement un noeud d'arbre de dérivation.

    - is_root=True : le noeud est renvoyé inchangé (mêmes clés que dans
      l'arbre d'origine), seuls ses enfants sont simplifiés.
    - is_root=False : le noeud est réduit à {pi_id, io, term, children}.
    """
    children = [simplify_node(c) for c in (node.get("children") or [])]

    if is_root:
        simplified = dict(node)
        simplified["children"] = children
        return simplified

    io, pi_id = node_io_and_pi_id(node)
    term = extract_term(node.get("fact"), node.get("raw"))

    return {
        "pi_id": pi_id,
        "io": io,
        "term": term,
        "children": children,
    }


def simplify_entry(entry):
    """Transforme une entrée complète (un fichier JSON) en gardant ses
    métadonnées (index, query, has_derivation) et en simplifiant l'arbre."""
    result = dict(entry)
    if entry.get("has_derivation") and entry.get("derivation") is not None:
        result["derivation"] = simplify_node(entry["derivation"], is_root=True)
    return result


def safe_stub(filename):
    return os.path.splitext(filename)[0]


def main():
    parser = argparse.ArgumentParser(
        description="Simplifie chaque arbre de dérivation JSON d'un dossier "
        "(pi-id / input-ou-output / terme uniquement pour les noeuds non racine)."
    )
    parser.add_argument("input_dir", help="Dossier contenant les JSON d'entrée")
    parser.add_argument("output_dir", help="Dossier où écrire les JSON simplifiés")
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

            simplified = simplify_entry(entry)

            stub = safe_stub(fname)
            out_path = os.path.join(args.output_dir, f"{stub}.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(simplified, f, ensure_ascii=False, indent=2)

            print(f"  - {fname} -> {out_path}")
            ok += 1
        except Exception as e:
            print(f"  - {fname} : ÉCHEC ({e})", file=sys.stderr)
            failed += 1

    print(f"\nTerminé : {ok} fichier(s) simplifié(s), {failed} échec(s). Sortie dans '{args.output_dir}'.")


if __name__ == "__main__":
    main()