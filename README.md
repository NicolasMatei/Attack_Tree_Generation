# Conjunctive Attack Graph (CAG) — ProVerif Pipeline

Automated pipeline that takes a ProVerif specification file (`.pv`) as input and outputs:

- **resolved** attack derivation trees, in JSON format (`<prefix>_arbres_resolus/`);
- a **PDF** rendering of each tree (`<prefix>_pdf/`).

## Prerequisites

- Python 3
- [ProVerif](https://prosecco.gforge.inria.fr/personal/bblanche/proverif/) installed, either:
  - accessible in the `PATH` bash (`proverif` command), **or**
  - a local binary in the project folder (`./proverif`)
- The Python module `graphviz` + the system binary `dot` (for the PDFs):

  ```bash
  pip install graphviz
  sudo apt install graphviz   # or: sudo dnf install graphviz
  ```

## Quick Start

The entire pipeline can be launched with a single script, **`generate_cag.py`**, from the project folder:

```bash
python3 generate_cag.py how_many_attack.pv --classical
```

or

```bash
python3 generate_cag.py how_many_attack.pv --randomized 10
```

That's it: the JSON and PDF files will appear in `how_many_attack_arbres_resolus/` and `how_many_attack_pdf/`.

## Choice of ProVerif Mode (Required)

`generate_cag.py` requires **one** of the two following options:

| Option             | Behavior                                                                                                                                      |
|----------------------|-----------------------------------------------------------------------------------------------------------------------------------------------|
| `--classical`         | Uses the `proverif` from the bash `PATH`. Deterministic result → **1 single execution**. |
| `--randomized N`      | Uses the local executable `./proverif`, executed **N times** to capture the variability of the derivation order (useful for finding multiple distinct attack trees). |

```bash
# Classical mode
python3 generate_cag.py NS-PK.pv --classical

# Randomized mode, 15 executions
python3 generate_cag.py NS-PK.pv --randomized 15
```

## Other Useful Options

| Option                    | Effect |
|----------------------------|-------|
| `--skip-pdf`               | Skips PDF generation (step 4), keeping only the resolved JSONs. |
| `--scripts-dir PATH`       | Folder containing the pipeline scripts, if different from the current directory. |
| `-v` / `--verbose`         | Displays each exact command executed. |

```bash
python3 generate_cag.py how_many_attack.pv --classical --skip-pdf -v
```

## What the Pipeline Does (4 Steps)

For a `<prefix>.pv` file (e.g., `how_many_attack.pv`):

1. **`pv_derivation_to_json.py`** — executes ProVerif (via `proverif10times_annotate_derivation.py`), parses the derivation trees (Horn Derivation Proof Trees) and exports them to JSON in `<prefix>_arbres/`.
2. **`decompose_pv_edges.py`** — decomposes long edges into a succession of simpler nodes/edges → `<prefix>_arbres_decomposes/`.
3. **`resolve_pv_duplicates.py`** — replaces "duplicate" nodes with the corresponding human-readable description → `<prefix>_arbres_resolus/`.
4. **`pv_json_to_pdf.py`** *(optional, `--skip-pdf` to skip)* — generates one PDF per tree with Graphviz → `<prefix>_pdf/`.

**Automatic cleanup:** before starting, outputs from a previous execution (`<prefix>_arbres*`, `<prefix>_pdf`) are deleted. Once step 3 is completed, the intermediate directories `<prefix>_arbres/` and `<prefix>_arbres_decomposes/` are also deleted: **only `<prefix>_arbres_resolus/` and `<prefix>_pdf/` are kept in the end.**

## Example Output

For `how_many_attack.pv --classical`:

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

Each number corresponds to a ProVerif query (`-- Query ...`); the associated PDF is the graphical rendering of the JSON derivation tree of the same name.

## Using the Scripts Individually

Each step can also be run alone, for example, to debug:

```bash
# Step 1 only, randomized mode
python3 pv_derivation_to_json.py how_many_attack.pv how_many_attack_arbres/ \
    --proverif ./proverif -times 10

# Step 2 only
python3 decompose_pv_edges.py how_many_attack_arbres/ how_many_attack_arbres_decomposes/

# Step 3 only
python3 resolve_pv_duplicates.py how_many_attack_arbres_decomposes/ how_many_attack_arbres_resolus/

# Step 4 only
python3 pv_json_to_pdf.py how_many_attack_arbres_resolus/ how_many_attack_pdf/
```

`proverif_annotate_derivation.py` and `proverif10times_annotate_derivation.py` are low-level building blocks used internally by `pv_derivation_to_json.py` to launch ProVerif and annotate the derivations with the description of each clause; it is rare to need to call them directly.

## Repository Structure

```
generate_cag.py                          # main script (complete pipeline)
pv_derivation_to_json.py                 # step 1
decompose_pv_edges.py                    # step 2
resolve_pv_duplicates.py                 # step 3
pv_json_to_pdf.py                        # step 4 (PDF)
proverif_annotate_derivation.py          # executes proverif 1 time + annotates
proverif10times_annotate_derivation.py   # executes proverif 1 or N times (--proverif / -times)
<prefix>.pv                              # input ProVerif specification
<prefix>_arbres_resolus/                 # final output: resolved JSON trees
<prefix>_pdf/                            # final output: PDF rendering of the trees
```
