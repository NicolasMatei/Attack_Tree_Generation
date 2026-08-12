#!/usr/bin/env python3
"""
proverif10times_annotate_derivation.py

Exécute proverif_annotate_derivation.py une ou plusieurs fois sur un
fichier .pv et agrège les arbres de dérivation uniques obtenus.

Comportement :
  - Si l'exécutable ProVerif utilisé est celui du PATH bash (option
    --proverif absente, ou --proverif proverif), le script ne l'exécute
    qu'UNE SEULE fois (le résultat est déterministe, inutile de répéter).
  - Si l'utilisateur choisit un exécutable local, par ex. ./proverif
    (--proverif ./proverif), le script l'exécute plusieurs fois afin de
    capter la variabilité de l'ordre des clauses / dérivations. Le
    nombre d'exécutions se règle avec -times n (défaut : 10).

Usage :
    python3 proverif10times_annotate_derivation.py fichier.pv
    python3 proverif10times_annotate_derivation.py fichier.pv --proverif ./proverif
    python3 proverif10times_annotate_derivation.py fichier.pv --proverif ./proverif -times 20
"""

import sys
import argparse
import subprocess
import re

SUBSCRIPT = "proverif_annotate_derivation.py"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Exécute proverif_annotate_derivation.py (1 ou N fois) et "
                    "agrège les arbres de dérivation uniques."
    )
    parser.add_argument("pv_file", help="Fichier .pv à analyser")
    parser.add_argument(
        "--proverif", default="proverif",
        help="Exécutable ProVerif à utiliser. Par défaut 'proverif' (celui du "
             "PATH bash) : dans ce cas une seule exécution est faite. "
             "Indiquez par ex. './proverif' pour utiliser un exécutable local, "
             "auquel cas plusieurs exécutions sont faites "
             "(voir -times)."
    )
    parser.add_argument(
        "-times", type=int, default=10, metavar="N",
        help="Nombre d'exécutions à effectuer lorsqu'un exécutable local "
             "(différent de 'proverif' du PATH) est utilisé. Ignoré (forcé à "
             "1) si --proverif vaut 'proverif'. Défaut : 10."
    )
    return parser.parse_args()


def main():
    args = parse_args()
    pv_file = args.pv_file
    proverif_path = args.proverif

    # "proverif" du PATH bash => résultat déterministe => une seule exécution.
    # Tout autre chemin (ex. "./proverif") => on respecte -times.
    use_bash_proverif = (proverif_path == "proverif")
    n_runs = 1 if use_bash_proverif else max(1, args.times)

    seen_trees = set()
    unique_blocks = []

    if use_bash_proverif:
        print(f"ProVerif du PATH bash détecté ('{proverif_path}') : "
              f"exécution unique pour le fichier '{pv_file}'...")
    else:
        print(f"Exécution de ProVerif ('{proverif_path}') {n_runs} fois pour "
              f"le fichier '{pv_file}', veuillez patienter...")

    for i in range(1, n_runs + 1):
        result = subprocess.run(
            ["python3", SUBSCRIPT, pv_file, "--proverif", proverif_path],
            capture_output=True,
            text=True
        )

        # En cas d'erreur bloquante de ProVerif ou du sous-script
        if result.returncode != 0:
            print(f"Erreur lors de l'itération {i} :\n{result.stderr}")
            continue

        # Découpage de l'output en blocs distincts (un bloc = une query + son arbre)
        blocks = re.split(r'(?m)^(?=-- Query )', result.stdout)

        for block in blocks:
            block_stripped = block.strip()
            if not block_stripped:
                continue

            # Ajout au résultat final si l'arbre n'a jamais été vu
            if block_stripped not in seen_trees:
                seen_trees.add(block_stripped)
                unique_blocks.append(block_stripped)

    for block in unique_blocks:
        print(block)
        print("\n")


if __name__ == "__main__":
    main()