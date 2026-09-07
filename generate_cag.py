#!/usr/bin/env python3
"""
generate_cag.py

Pipeline automatisé pour la génération du Conjonctive Attack Graph (CAG)
à partir d'un fichier de spécification ProVerif (.pv).

Ce script enchaîne les quatre étapes décrites dans la sous-section
"Generation of Conjonctive Attack Graphs" du framework :

    1. pv_derivation_to_json.py   -- extraction et parsing des Horn
                                     Derivation Proof Trees produits par
                                     ProVerif (avec nommage des clauses)
    2. decompose_pv_edges.py      -- décomposition des arêtes longues en
                                     une succession de noeuds/arêtes
    3. resolve_pv_duplicates.py   -- remplacement des noeuds "duplicate"
                                     par la description humainement
                                     lisible correspondante
    4. pv_json_to_pdf.py          -- (optionnel) génération d'un rendu PDF
                                     des arbres finaux

Avant toute exécution, les répertoires de sortie d'une exécution
précédente sont supprimés (équivalent de la série de `rm -rf` donnée
dans le document). Après l'étape 3, les répertoires intermédiaires
(arbres bruts et arbres décomposés) sont eux aussi supprimés : seuls
les arbres résolus (<prefix>_arbres_resolus) et les PDF (<prefix>_pdf)
sont conservés au final dans le dossier de sortie.

Le script ProVerif utilisé (et le nombre d'exécutions) doit être choisi
explicitement via l'une de ces deux options mutuellement exclusives,
OBLIGATOIRES :

    --classical        Utilise le proverif du PATH bash (une seule
                       exécution, résultat déterministe).
    --randomized N     Utilise l'exécutable local ./proverif, exécuté
                       N fois (variabilité de l'ordre des dérivations).

Usage
-----
    python3 generate_cag.py how_many_attack.pv --classical
    python3 generate_cag.py how_many_attack.pv --randomized 10
    python3 generate_cag.py how_many_attack.pv --randomized 10 --skip-pdf
    python3 generate_cag.py how_many_attack.pv --classical --scripts-dir /chemin/vers/scripts
    python3 generate_cag.py how_many_attack.pv --classical --output-dir /chemin/vers/resultats
    python3 generate_cag.py how_many_attack.pv --randomized 10 -v
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

# Les scripts requis par le pipeline, dans l'ordre d'exécution.
PIPELINE_SCRIPTS = [
    "pv_derivation_to_json.py",
    "decompose_pv_edges.py",
    "resolve_pv_duplicates.py",
    "pv_json_to_pdf.py",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Génère le Conjonctive Attack Graph (CAG) pour une spécification "
            "ProVerif donnée."
        )
    )
    parser.add_argument(
        "pv_file",
        type=Path,
        help="Chemin vers le fichier ProVerif (.pv), ex : how_many_attack.pv",
    )
    parser.add_argument(
        "--scripts-dir",
        type=Path,
        default=Path(__file__).resolve().parent,
        help=(
            "Répertoire contenant pv_derivation_to_json.py, "
            "decompose_pv_edges.py, resolve_pv_duplicates.py et "
            "pv_json_to_pdf.py (par défaut : le répertoire de generate_cag.py)"
        ),
    )
    parser.add_argument(
        "-o", "--output-dir",
        type=Path,
        default=Path("."),
        help=(
            "Dossier de destination pour les résultats. Les dossiers finaux "
            "y seront créés. (Par défaut : le répertoire courant)"
        ),
    )
    parser.add_argument(
        "--skip-pdf",
        action="store_true",
        help="Ignore la 4ème étape, optionnelle, de génération des PDF.",
    )
    parser.add_argument(
        "--lib",
        type=Path,
        default=None,
        metavar="LIB.pvl",
        help=(
            "Bibliothèque ProVerif (.pvl) à charger via l'option -lib de "
            "proverif, transmise à l'étape 1 (--classical ou --randomized). "
            "Optionnel."
        ),
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Affiche les commandes exactes exécutées à chaque étape.",
    )

    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--classical",
        action="store_true",
        help=(
            "Utilise le proverif du PATH bash : une seule exécution "
            "(résultat déterministe)."
        ),
    )
    mode_group.add_argument(
        "--randomized",
        type=int,
        metavar="N",
        help=(
            "Utilise l'exécutable local ./proverif, exécuté N fois pour "
            "capter la variabilité de l'ordre des dérivations."
        ),
    )

    args = parser.parse_args()
    if args.randomized is not None and args.randomized < 1:
        parser.error("--randomized N nécessite un entier N >= 1.")
    if args.lib is not None and not args.lib.is_file():
        parser.error(f"--lib : fichier introuvable : {args.lib}")
    return args


def clean_previous_outputs(dirs: list[Path], files: list[Path], verbose: bool) -> None:
    """Équivalent de : rm -rf <dir1> <dir2> ... && rm -f <file1> <file2> ..."""
    print("[generate_cag] Nettoyage des sorties d'une exécution précédente...")
    for d in dirs:
        if d.exists():
            if verbose:
                print(f"    rm -rf {d}")
            shutil.rmtree(d)
    for f in files:
        if f.exists():
            if verbose:
                print(f"    rm -f {f}")
            f.unlink()


def run_step(step_name: str, cmd: list[str], verbose: bool) -> None:
    print(f"[generate_cag] {step_name} ...")
    if verbose:
        print("    $ " + " ".join(str(c) for c in cmd))
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(
            f"[generate_cag] ERREUR : '{cmd[0]} {cmd[1]}' a échoué "
            f"(code de sortie {result.returncode}). Arrêt du pipeline.",
            file=sys.stderr,
        )
        sys.exit(result.returncode)


def main() -> None:
    args = parse_args()

    pv_file: Path = args.pv_file
    if not pv_file.is_file():
        print(f"[generate_cag] ERREUR : '{pv_file}' est introuvable.", file=sys.stderr)
        sys.exit(1)

    # Création du dossier de sortie s'il n'existe pas
    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    # Préfixe utilisé pour tous les répertoires générés, ex : "how_many_attack"
    prefix = pv_file.stem

    # Les dossiers sont maintenant rattachés au dossier de sortie
    arbres_dir = output_dir / f"{prefix}_arbres"
    decomposes_dir = output_dir / f"{prefix}_arbres_decomposes"
    resolus_dir = output_dir / f"{prefix}_arbres_resolus"
    pdf_dir = output_dir / f"{prefix}_pdf"

    # On vérifie la présence de tous les scripts requis avant de commencer.
    missing = [
        s for s in PIPELINE_SCRIPTS if not (args.scripts_dir / s).is_file()
    ]
    if missing:
        print(
            "[generate_cag] ERREUR : script(s) requis introuvable(s) dans "
            f"'{args.scripts_dir}' : {', '.join(missing)}",
            file=sys.stderr,
        )
        sys.exit(1)

    def script(name: str) -> str:
        return str(args.scripts_dir / name)

    # Options ProVerif à propager à l'étape 1
    if args.classical:
        proverif_mode_desc = "classique (proverif du PATH bash, 1 exécution)"
        proverif_opts = ["--proverif", "proverif"]
    else:
        proverif_mode_desc = f"randomisé (./proverif, {args.randomized} exécutions)"
        proverif_opts = ["--proverif", "./proverif", "-times", str(args.randomized)]

    if args.lib is not None:
        proverif_opts += ["--lib", str(args.lib)]
        proverif_mode_desc += f", lib={args.lib}"

    print(f"[generate_cag] Mode ProVerif : {proverif_mode_desc}")

    # --- Étape 0 : nettoyage ---
    clean_previous_outputs(
        [arbres_dir, decomposes_dir, resolus_dir, pdf_dir],
        [],
        args.verbose,
    )

    # --- Étape 1 : extraction et parsing des Horn Derivation Proof Trees ---
    run_step(
        "Étape 1/4 - Extraction et parsing des Horn Derivation Proof Trees",
        ["python3", script("pv_derivation_to_json.py"), str(pv_file), str(arbres_dir)]
        + proverif_opts,
        args.verbose,
    )

    # --- Étape 2 : décomposition des arêtes longues ---
    run_step(
        "Étape 2/4 - Décomposition des arêtes",
        ["python3", script("decompose_pv_edges.py"), str(arbres_dir), str(decomposes_dir)],
        args.verbose,
    )

    # --- Étape 3 : résolution des noeuds "duplicate" ---
    run_step(
        "Étape 3/4 - Résolution des noeuds dupliqués",
        ["python3", script("resolve_pv_duplicates.py"), str(decomposes_dir), str(resolus_dir)],
        args.verbose,
    )

    # Nettoyage des répertoires intermédiaires
    print("[generate_cag] Nettoyage des répertoires intermédiaires (arbres, arbres_decomposes)...")
    for d in (arbres_dir, decomposes_dir):
        if d.exists():
            if args.verbose:
                print(f"    rm -rf {d}")
            shutil.rmtree(d)

    # --- Étape 4 (optionnelle) : génération des PDF ---
    if args.skip_pdf:
        print("[generate_cag] Étape 4/4 - Ignorée (--skip-pdf).")
    else:
        run_step(
            "Étape 4/4 - Génération des PDF (optionnelle)",
            ["python3", script("pv_json_to_pdf.py"), str(resolus_dir), str(pdf_dir)],
            args.verbose,
        )

    print(
        f"[generate_cag] Terminé. Conjonctive Attack Graph final disponible dans : "
        f"{resolus_dir}"
    )


if __name__ == "__main__":
    main()
