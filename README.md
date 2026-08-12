# Conjonctive Attack Graph (CAG) — Pipeline ProVerif

Pipeline automatisé qui prend en entrée un fichier de spécification
ProVerif (`.pv`) et produit :

- des arbres de dérivation d'attaque **résolus**, au format JSON
  (`<prefix>_arbres_resolus/`) ;
- un rendu **PDF** de chaque arbre (`<prefix>_pdf/`).

## Prérequis

- Python 3
- [ProVerif](https://prosecco.gforge.inria.fr/personal/bblanche/proverif/)
  installé, soit :
  - accessible dans le `PATH` bash (commande `proverif`), **ou**
  - un binaire local dans le dossier du projet (`./proverif`)
- Le module Python `graphviz` + le binaire système `dot` (pour les PDF) :

  ```bash
  pip install graphviz
  sudo apt install graphviz   # ou : sudo dnf install graphviz
  ```

## Démarrage rapide

Tout le pipeline se lance avec un seul script, **`generate_cag.py`**,
depuis le dossier du projet :

```bash
python3 generate_cag.py how_many_attack.pv --classical
```

ou

```bash
python3 generate_cag.py how_many_attack.pv --randomized 10
```

C'est tout : les JSON et PDF apparaissent dans
`how_many_attack_arbres_resolus/` et `how_many_attack_pdf/`.

## Choix du mode ProVerif (obligatoire)

`generate_cag.py` exige **une** des deux options suivantes :

| Option              | Comportement                                                                 |
|----------------------|-------------------------------------------------------------------------------|
| `--classical`         | Utilise le `proverif` du `PATH` bash. Résultat déterministe → **1 seule exécution**. |
| `--randomized N`      | Utilise l'exécutable local `./proverif`, exécuté **N fois** pour capter la variabilité de l'ordre des dérivations (utile pour trouver plusieurs arbres d'attaque distincts). |

```bash
# Mode classique
python3 generate_cag.py NS-PK.pv --classical

# Mode randomisé, 15 exécutions
python3 generate_cag.py NS-PK.pv --randomized 15
```

## Autres options utiles

| Option                    | Effet |
|----------------------------|-------|
| `--skip-pdf`               | Saute la génération des PDF (étape 4), ne garde que les JSON résolus. |
| `--scripts-dir CHEMIN`      | Dossier contenant les scripts du pipeline, si différent du dossier courant. |
| `-v` / `--verbose`          | Affiche chaque commande exacte exécutée. |

```bash
python3 generate_cag.py how_many_attack.pv --classical --skip-pdf -v
```

## Ce que fait le pipeline (4 étapes)

Pour un fichier `<prefix>.pv` (ex. `how_many_attack.pv`) :

1. **`pv_derivation_to_json.py`** — exécute ProVerif (via
   `proverif10times_annotate_derivation.py`), parse les arbres de
   dérivation (Horn Derivation Proof Trees) et les exporte en JSON
   dans `<prefix>_arbres/`.
2. **`decompose_pv_edges.py`** — décompose les arêtes longues en une
   succession de noeuds/arêtes plus simples →
   `<prefix>_arbres_decomposes/`.
3. **`resolve_pv_duplicates.py`** — remplace les noeuds `"duplicate"`
   par la description humainement lisible correspondante →
   `<prefix>_arbres_resolus/`.
4. **`pv_json_to_pdf.py`** *(optionnelle, `--skip-pdf` pour la sauter)*
   — génère un PDF par arbre avec Graphviz → `<prefix>_pdf/`.

**Nettoyage automatique :** avant de démarrer, les sorties d'une
exécution précédente (`<prefix>_arbres*`, `<prefix>_pdf`) sont
supprimées. Une fois l'étape 3 terminée, les répertoires intermédiaires
`<prefix>_arbres/` et `<prefix>_arbres_decomposes/` sont eux aussi
supprimés : **seuls `<prefix>_arbres_resolus/` et `<prefix>_pdf/` sont
conservés au final.**

## Exemple de résultat

Pour `how_many_attack.pv --classical` :

```
how_many_attack_arbres_resolus/
├── 01_not_attacker_success_in_process_0.json
├── 02_not_attacker_success2_in_process_0.json
└── 03_not_attacker_success_in_process_0.json
how_many_attack_pdf/
├── 01_not_attacker_success_in_process_0.pdf
├── 02_not_attacker_success2_in_process_0.pdf
└── 03_not_attacker_success_in_process_0.pdf
```

Chaque numéro correspond à une requête ProVerif (`-- Query ...`) ;
le PDF associé est le rendu graphique de l'arbre de dérivation JSON du
même nom.

## Utiliser les scripts individuellement

Chaque étape peut aussi être lancée seule, par exemple pour déboguer :

```bash
# Étape 1 seule, mode randomisé
python3 pv_derivation_to_json.py how_many_attack.pv how_many_attack_arbres/ \
    --proverif ./proverif -times 10

# Étape 2 seule
python3 decompose_pv_edges.py how_many_attack_arbres/ how_many_attack_arbres_decomposes/

# Étape 3 seule
python3 resolve_pv_duplicates.py how_many_attack_arbres_decomposes/ how_many_attack_arbres_resolus/

# Étape 4 seule
python3 pv_json_to_pdf.py how_many_attack_arbres_resolus/ how_many_attack_pdf/
```

`proverif_annotate_derivation.py` et
`proverif10times_annotate_derivation.py` sont les briques de bas
niveau utilisées en interne par `pv_derivation_to_json.py` pour lancer
ProVerif et annoter les dérivations avec la description de chaque
clause ; il est rare d'avoir besoin de les appeler directement.

## Structure du dépôt

```
generate_cag.py                          # script principal (pipeline complet)
pv_derivation_to_json.py                 # étape 1
decompose_pv_edges.py                    # étape 2
resolve_pv_duplicates.py                 # étape 3
pv_json_to_pdf.py                        # étape 4 (PDF)
proverif_annotate_derivation.py          # exécute proverif 1 fois + annote
proverif10times_annotate_derivation.py   # exécute proverif 1 ou N fois (--proverif / -times)
<prefix>.pv                              # spécification ProVerif d'entrée
<prefix>_arbres_resolus/                 # sortie finale : arbres JSON résolus
<prefix>_pdf/                            # sortie finale : rendu PDF des arbres
```
