#!/usr/bin/env python3
"""
proverif_annotate_derivation.py

Exécute ProVerif sur un fichier .pv avec les options :
    -set explainDerivation false -set verboseClauses explained
récupère la sortie, puis pour chaque requête ("-- Query ...") :
  1. construit un dictionnaire {numéro de clause -> description}
     à partir du bloc "Initial clauses:" (le texte entre parenthèses
     qui suit chaque "Clause N: ...") ;
  2. repère le bloc "Derivation:" ;
  3. remplace chaque occurrence de "clause N" par la description
     correspondante (son "sous-titre").

Usage :
    python3 proverif_annotate_derivation.py fichier.pv
    python3 proverif_annotate_derivation.py fichier.pv --proverif ./proverif --out resultat.txt
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path


def run_proverif(proverif_path: str, pv_file: str) -> str:
    """Lance ProVerif et retourne stdout (+ stderr en cas d'erreur)."""
    cmd = [
        proverif_path,
        "-set", "explainDerivation", "false",
        "-set", "verboseClauses", "explained",
        pv_file,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        sys.exit(f"Erreur : exécutable ProVerif introuvable ('{proverif_path}'). "
                  f"Utilisez --proverif pour préciser le chemin.")

    output = result.stdout
    if result.returncode not in (0, 1, 2) and result.stderr:
        output += "\n[stderr]\n" + result.stderr
    return output


def split_query_sections(output: str):
    """
    Découpe la sortie complète en morceaux, un par bloc "-- Query ...".
    Retourne (en_tete, [section1, section2, ...]).
    """
    pattern = re.compile(r'(?=^-- Query )', re.MULTILINE)
    parts = pattern.split(output)
    if parts and not parts[0].lstrip().startswith('-- Query'):
        header, sections = parts[0], parts[1:]
    else:
        header, sections = "", parts
    return header, sections


def parse_clause_table(section_text: str) -> dict:
    """
    Extrait, depuis le bloc "Initial clauses:" d'une section, le
    dictionnaire {numéro de clause (int): description (str)}.
    La description est le texte entre parenthèses qui suit
    immédiatement la ligne "Clause N: ...".
    """
    clauses = {}

    m = re.search(
        r'Initial clauses:(.*?)(?:\n0 rules inserted|\nCompleting\.\.\.)',
        section_text, re.DOTALL
    )
    block = m.group(1) if m else section_text

    lines = block.splitlines()
    i, n = 0, len(lines)
    while i < n:
        header_match = re.match(r'^Clause (\d+):\s*(.*)$', lines[i])
        if not header_match:
            i += 1
            continue

        clause_num = int(header_match.group(1))
        i += 1

        # La description commence sur la ligne suivante par "(" et se
        # termine sur la première ligne dont le dernier caractère est ")".
        desc_lines = []
        while i < n:
            stripped = lines[i].rstrip()
            if not desc_lines and not stripped.lstrip().startswith('('):
                break  # pas de description pour cette clause (cas rare)
            desc_lines.append(lines[i])
            i += 1
            if stripped.endswith(')'):
                break

        if desc_lines:
            desc = " ".join(l.strip() for l in desc_lines).strip()
            if desc.startswith('(') and desc.endswith(')'):
                desc = desc[1:-1].strip()
            clauses[clause_num] = desc

    return clauses


def extract_derivation_span(section_text: str):
    """Retourne (start, end, texte) du bloc 'Derivation: ...' dans la section, ou None."""
    m = re.search(
        r'Derivation:\n.*?(?=\nA more detailed output|\nRESULT|\Z)',
        section_text, re.DOTALL
    )
    if not m:
        return None
    return m.start(), m.end(), m.group(0)


def annotate_derivation(derivation_text: str, clause_map: dict) -> str:
    """Remplace chaque 'clause N' par sa description (sous-titre)."""

    def repl(match):
        num = int(match.group(1))
        desc = clause_map.get(num)
        if desc:
            return f'"{desc}" [clause {num}]'
        return match.group(0)  # pas de description trouvée : on laisse tel quel

    return re.sub(r'\bclause (\d+)\b', repl, derivation_text)


def process_output(raw_output: str) -> str:
    header, sections = split_query_sections(raw_output)
    annotated_sections = []

    for sec in sections:
        clause_map = parse_clause_table(sec)
        span = extract_derivation_span(sec)
        if span is None:
            annotated_sections.append(sec)
            continue
        start, end, deriv_text = span
        annotated = annotate_derivation(deriv_text, clause_map)
        annotated_sections.append(sec[:start] + annotated + sec[end:])

    return header + "".join(annotated_sections)


def print_derivation_summary(annotated_output: str) -> None:
    """Affiche uniquement les arbres de dérivation annotés, par requête."""
    for m in re.finditer(r'^-- Query.*?(?=^-- Query |\Z)', annotated_output,
                          re.DOTALL | re.MULTILINE):
        section = m.group(0)
        title = section.splitlines()[0]
        print(title)
        deriv_m = re.search(
            r'Derivation:\n.*?(?=\nA more detailed output|\nRESULT|\Z)',
            section, re.DOTALL
        )
        if deriv_m:
            print(deriv_m.group(0))
        else:
            print("(pas d'arbre de dérivation — la requête est probablement vraie)")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Exécute ProVerif et annote les arbres de dérivation avec "
                    "la description ('sous-titre') de chaque clause référencée."
    )
    parser.add_argument("pv_file", help="Fichier .pv à analyser")
    parser.add_argument("--proverif", default="proverif",
                        help="Chemin vers l'exécutable proverif (défaut : proverif)")
    parser.add_argument("--out", default=None,
                        help="Fichier de sortie (défaut : <pv_file>_annotated.txt)")
    args = parser.parse_args()

    pv_path = Path(args.pv_file)
    if not pv_path.exists():
        sys.exit(f"Erreur : fichier introuvable : {pv_path}")

#    print(f"[*] Exécution de ProVerif sur {pv_path} ...")
    raw_output = run_proverif(args.proverif, str(pv_path))

 #   print("[*] Analyse des clauses et annotation des dérivations ...")
    annotated = process_output(raw_output)

    out_path = Path(args.out) if args.out else pv_path.with_name(pv_path.stem + "_annotated.txt")
    out_path.write_text(annotated, encoding="utf-8")
  #  print(f"[*] Sortie complète (annotée) écrite dans : {out_path}\n")

    print_derivation_summary(annotated)


if __name__ == "__main__":
    main()