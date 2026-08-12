import sys
import subprocess

def extract_pi_calculus(pv_file):
    print(f"Exécution de ProVerif sur '{pv_file}'...\n")
    
    try:
        # On exécute ProVerif (adapte la commande si tu utilises un exécutable spécifique comme ./proverif)
        result = subprocess.run(['proverif', pv_file], capture_output=True, text=True)
        output = result.stdout
    except FileNotFoundError:
        print("Erreur : La commande 'proverif' est introuvable.")
        print("Si ton exécutable est dans le dossier courant, remplace 'proverif' par './proverif' dans le script.")
        return

    in_process = False
    pi_calculus_lines = []

    for line in output.splitlines():
        # Détection du début du bloc
        if line.startswith("Process:") or line.startswith("Process 0"):
            in_process = True
            
        if in_process:
            # Détection de la fin du bloc
            if line.startswith("-- Query") or line.startswith("Translation") or line.startswith("Resolving"):
                break
            pi_calculus_lines.append(line)

    if pi_calculus_lines:
        print("--- Système en pi-calcul appliqué ---")
        print("\n".join(pi_calculus_lines))
    else:
        print("Aucun bloc de processus n'a été détecté.")
        print("Voici le début de l'output pour vérifier ce que ProVerif renvoie réellement :\n")
        print("\n".join(output.splitlines()[:15]))

if __name__ == "__main__":
    if len(sys.argv) > 1:
        extract_pi_calculus(sys.argv[1])
    else:
        print("Usage: python3 extract_pi.py <fichier.pv>")
