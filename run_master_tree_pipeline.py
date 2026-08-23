#!/usr/bin/env python3
"""
run_master_tree_pipeline.py

Automatise le pipeline complet :
    how_many_attack_arbres_resolus/  -->  Final Conjunctive Attack Graph

Enchaîne les trois scripts :
    1. pv_json_simplify.py       (réduction des noeuds à io / pi_id / term)
    2. pv_json_merge_master.py   (fusion par but, relation ET/OU)
    3. pv_master_to_pdf.py       (rendu Graphviz, portes ET/OU, sous-arbres partagés)

Usage:
    python3 run_master_tree_pipeline.py [dossier_entree] [fichier_pdf_sortie]

Par défaut :
    dossier_entree     = how_many_attack_arbres_resolus
    fichier_pdf_sortie = final_conjunctive_attack_graph.pdf

Exemple:
    python3 run_master_tree_pipeline.py how_many_attack_arbres_resolus final_conjunctive_attack_graph.pdf
"""

import argparse
import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def run_step(step_num, total_steps, description, script_name, args):
    """Exécute un script du pipeline via subprocess et arrête tout en cas d'échec."""
    script_path = os.path.join(SCRIPT_DIR, script_name)
    if not os.path.isfile(script_path):
        sys.exit(f"Erreur : script introuvable : {script_path}")

    cmd = [sys.executable, script_path, *args]
    print(f"== {step_num}/{total_steps} : {description} ==")
    print(f"   $ {' '.join(cmd)}")

    result = subprocess.run(cmd)
    if result.returncode != 0:
        sys.exit(
            f"Erreur : '{script_name}' a échoué (code {result.returncode}). "
            "Pipeline interrompu."
        )
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Automatise le pipeline pv_json_simplify -> pv_json_merge_master "
        "-> pv_master_to_pdf sur un dossier d'arbres de dérivation résolus."
    )
    parser.add_argument(
        "input_dir",
        nargs="?",
        default="how_many_attack_arbres_resolus",
        help="Dossier d'entrée (arbres résolus, sortie de generate_cag.py). "
        "Défaut : how_many_attack_arbres_resolus",
    )
    parser.add_argument(
        "output_pdf",
        nargs="?",
        default="final_conjunctive_attack_graph.pdf",
        help="Fichier PDF final. Défaut : final_conjunctive_attack_graph.pdf",
    )
    args = parser.parse_args()

    if not os.path.isdir(args.input_dir):
        sys.exit(f"Erreur : dossier d'entrée introuvable : {args.input_dir}")

    simplified_dir = args.input_dir.rstrip("/\\") + "_simplified"
    master_json = "arbre_maitre.json"

    run_step(
        1, 3, "simplification des arbres",
        "pv_json_simplify.py", [args.input_dir, simplified_dir],
    )
    run_step(
        2, 3, "fusion par but (ET/OU)",
        "pv_json_merge_master.py", [simplified_dir, master_json],
    )
    run_step(
        3, 3, "génération du graphe final",
        "pv_master_to_pdf.py", [master_json, args.output_pdf],
    )

    print(f"Terminé : {args.output_pdf}")


if __name__ == "__main__":
    main()
