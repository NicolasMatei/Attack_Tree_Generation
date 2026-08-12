#!/usr/bin/env python3
"""
pv_derivation_to_json.py

Exécute proverif10times_annotate_derivation.py sur un fichier .pv, parse les
arbres de dérivation affichés sur stdout, et sauvegarde chacun d'eux comme
fichier JSON dans un dossier de sortie.

Usage:
    python3 pv_derivation_to_json.py fichier.pv dossier_sortie \
        [--script chemin_vers_proverif10times_annotate_derivation.py] \
        [--python python3] [--raw-output sortie_brute.txt]

Exemple:
    python3 pv_derivation_to_json.py how_many_attack.pv arbres/
"""

import argparse
import json
import os
import re
import subprocess
import sys


QUERY_RE = re.compile(r'^--\s*Query\s+(.*)$')
GOAL_RE = re.compile(r'^goal\s+(.*)$')
DUP_RE = re.compile(r'^duplicate\s+(.*)$')
STEP_RE = re.compile(r'^"(?P<desc>.*)"\s+\[clause\s+(?P<clause>\d+)\]\s+(?P<fact>.*)$')


def run_proverif(script_path, pv_file, python_bin="python3", proverif=None, times=None):
    """Lance le script d'annotation et renvoie sa sortie (stdout + stderr)."""
    cmd = [python_bin, script_path, pv_file]
    if proverif is not None:
        cmd += ["--proverif", proverif]
    if times is not None:
        cmd += ["-times", str(times)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 and not result.stdout.strip():
        sys.stderr.write(result.stderr)
        raise RuntimeError(
            f"'{' '.join(cmd)}' a échoué (code {result.returncode}) et n'a produit aucune sortie."
        )
    output = result.stdout
    if result.stderr.strip():
        output += "\n" + result.stderr
    return output


def indent_of(line):
    return len(line) - len(line.lstrip(' '))


def parse_line(stripped):
    """Transforme une ligne (déjà strip()) d'un arbre de dérivation en noeud dict."""
    m = GOAL_RE.match(stripped)
    if m:
        return {"type": "goal", "fact": m.group(1).strip(), "children": []}

    m = DUP_RE.match(stripped)
    if m:
        return {"type": "duplicate", "fact": m.group(1).strip(), "children": []}

    m = STEP_RE.match(stripped)
    if m:
        return {
            "type": "step",
            "description": m.group("desc").strip(),
            "clause": int(m.group("clause")),
            "fact": m.group("fact").strip(),
            "children": [],
        }

    # Filet de sécurité : on ne perd jamais de contenu silencieusement
    return {"type": "unknown", "raw": stripped, "children": []}


def parse_derivation_tree(lines):
    """
    lines : lignes brutes (non strip) d'un arbre de dérivation, en commençant
            par la ligne 'goal ...'.
    Retourne le noeud racine (dict).
    """
    stack = []  # liste de (indentation, noeud)
    root = None

    for raw_line in lines:
        if not raw_line.strip():
            continue
        indent = indent_of(raw_line)
        node = parse_line(raw_line.strip())

        # On dépile tant que le sommet a une indentation >= à la ligne courante
        while stack and stack[-1][0] >= indent:
            stack.pop()

        if not stack:
            root = node
        else:
            stack[-1][1]["children"].append(node)

        stack.append((indent, node))

    return root


def split_into_query_blocks(output_text):
    """
    Découpe la sortie complète en blocs, un par ligne '-- Query ...'.
    Retourne une liste de (texte_requete, lignes_suivantes_jusqu_a_la_prochaine_query).
    """
    lines = output_text.splitlines()
    blocks = []
    current_query = None
    current_lines = []

    for line in lines:
        m = QUERY_RE.match(line.strip())
        if m:
            if current_query is not None:
                blocks.append((current_query, current_lines))
            current_query = m.group(1).strip()
            current_lines = []
        else:
            if current_query is not None:
                current_lines.append(line)

    if current_query is not None:
        blocks.append((current_query, current_lines))

    return blocks


def extract_derivation_lines(block_lines):
    """
    Cherche le marqueur 'Derivation:' dans les lignes suivant une entête
    '-- Query' et retourne les lignes de l'arbre qui suivent (ou None s'il
    n'y a pas de dérivation, par ex. requête prouvée).
    """
    for i, line in enumerate(block_lines):
        if line.strip() == "Derivation:":
            return block_lines[i + 1:]
    return None


def safe_filename(text, max_len=60):
    text = re.sub(r'[^A-Za-z0-9_\-]+', '_', text)
    text = text.strip('_')
    if not text:
        text = "query"
    return text[:max_len]


def main():
    parser = argparse.ArgumentParser(
        description="Exécute proverif10times_annotate_derivation.py sur un fichier .pv "
                    "et exporte les arbres de dérivation trouvés dans sa sortie en JSON."
    )
    parser.add_argument("pv_file", help="Chemin vers le fichier .pv à analyser")
    parser.add_argument("output_dir", help="Dossier où écrire les arbres JSON")
    parser.add_argument(
        "--script",
        default="proverif10times_annotate_derivation.py",
        help="Chemin vers proverif10times_annotate_derivation.py "
             "(par défaut : dans le dossier courant)",
    )
    parser.add_argument(
        "--python",
        default="python3",
        help="Interpréteur Python utilisé pour lancer le script (défaut : python3)",
    )
    parser.add_argument(
        "--raw-output",
        default=None,
        help="Chemin optionnel pour sauvegarder aussi la sortie brute du run",
    )
    parser.add_argument(
        "--proverif",
        default="proverif",
        help="Exécutable ProVerif à transmettre à "
             "proverif10times_annotate_derivation.py via son option "
             "--proverif (défaut : 'proverif', celui du PATH bash).",
    )
    parser.add_argument(
        "-times",
        type=int,
        default=None,
        metavar="N",
        help="Nombre d'exécutions à transmettre à "
             "proverif10times_annotate_derivation.py via son option -times "
             "(ignoré par ce dernier si --proverif vaut 'proverif').",
    )
    args = parser.parse_args()

    if not os.path.isfile(args.pv_file):
        sys.exit(f"Erreur : fichier .pv introuvable : {args.pv_file}")
    if not os.path.isfile(args.script):
        sys.exit(f"Erreur : script introuvable : {args.script}")

    os.makedirs(args.output_dir, exist_ok=True)

    cmd_desc = f"{args.python} {args.script} {args.pv_file} --proverif {args.proverif}"
    if args.times is not None:
        cmd_desc += f" -times {args.times}"
    print(f"Exécution : {cmd_desc}")
    output_text = run_proverif(
        args.script, args.pv_file, args.python,
        proverif=args.proverif, times=args.times,
    )

    if args.raw_output:
        with open(args.raw_output, "w", encoding="utf-8") as f:
            f.write(output_text)

    blocks = split_into_query_blocks(output_text)

    if not blocks:
        print("Aucun bloc '-- Query' trouvé dans la sortie. Rien à exporter.")
        return

    summary = []
    for idx, (query_text, block_lines) in enumerate(blocks, start=1):
        derivation_lines = extract_derivation_lines(block_lines)

        entry = {
            "index": idx,
            "query": query_text,
        }

        if derivation_lines is not None:
            tree = parse_derivation_tree(derivation_lines)
            entry["has_derivation"] = True
            entry["derivation"] = tree
        else:
            entry["has_derivation"] = False
            entry["raw"] = "\n".join(block_lines).strip()

        fname = f"{idx:02d}_{safe_filename(query_text)}.json"
        fpath = os.path.join(args.output_dir, fname)
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(entry, f, indent=2, ensure_ascii=False)

        summary.append((fname, query_text, entry["has_derivation"]))

    print(f"\n{len(blocks)} bloc(s) de requête trouvé(s), JSON écrits dans '{args.output_dir}':")
    for fname, query_text, has_deriv in summary:
        tag = "dérivation" if has_deriv else "pas de dérivation"
        print(f"  - {fname}  [{tag}]  {query_text}")


if __name__ == "__main__":
    main()