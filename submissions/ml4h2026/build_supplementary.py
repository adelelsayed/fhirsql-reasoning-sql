"""Build an anonymized supplementary-material bundle for the ML4H 2026 submission.

The template is explicit: code supplied at review time must be anonymized, and
non-anonymized code is grounds for desk rejection. This script therefore:

  * includes only the reproducibility-relevant material (generation and analysis
    scripts, schema, notebooks, per-seed results),
  * excludes every document that carries the author's name, ORCID, employer, or
    the public GitHub/Zenodo/Hugging Face URLs (README, PAPER, LICENSE,
    CITATION.cff, CITATIONS.md, MODEL_CARD, and the submissions/ folder),
  * strips Colab's executionInfo user metadata from notebooks, which embeds the
    account display name and numeric user id invisibly in cell metadata,
  * rewrites absolute local paths to a neutral placeholder,
  * then re-scans every staged byte for identifying strings and refuses to
    produce the archive if any survive.
"""
import io, json, os, re, shutil, zipfile

SRC = r"C:\dev\fhirsql-phase2"
STAGE = r"C:\Users\adele\AppData\Local\Temp\claude\c--dev-fhirsql\db88938b-cd28-45d9-b6fa-d7086202a1a4\scratchpad\supp"
OUT = os.path.join(SRC, "submissions", "ml4h2026", "supplementary_anonymous.zip")

IDENTIFYING = [
    "elsayed", "adelelsayed", "intersystems", "adel ",
    "github.com", "zenodo", "huggingface", "0009-0009",
    "13956627940223451684",
]

if os.path.isdir(STAGE):
    shutil.rmtree(STAGE)
os.makedirs(STAGE)

# ---------------------------------------------------------------- copy code
for sub in ("scripts", "schema"):
    shutil.copytree(os.path.join(SRC, sub), os.path.join(STAGE, sub),
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

# results: JSON summaries + logs + failure logs (small, and they back every number)
shutil.copytree(os.path.join(SRC, "results"), os.path.join(STAGE, "results"))

# ---------------------------------------------------------------- notebooks, scrubbed
def scrub_notebook(src, dst):
    nb = json.load(io.open(src, encoding="utf-8"))
    nb.get("metadata", {}).pop("colab", None)
    removed = 0
    for c in nb.get("cells", []):
        md = c.get("metadata", {})
        for k in ("executionInfo", "outputId", "colab", "id"):
            if k in md:
                md.pop(k, None); removed += 1
        # outputs can contain rendered paths/usernames -- drop them entirely
        if c.get("cell_type") == "code":
            c["outputs"] = []
            c["execution_count"] = None
    json.dump(nb, io.open(dst, "w", encoding="utf-8"), indent=1)
    return removed

nb_removed = 0
for f in ("sft_train.ipynb", "rl_train.ipynb", "valuesets_ablation.ipynb"):
    nb_removed += scrub_notebook(os.path.join(SRC, f), os.path.join(STAGE, f))
print("notebook metadata keys removed:", nb_removed)

# ---------------------------------------------------------------- neutralize paths
PATH_RE = re.compile(r"[A-Za-z]:[\\/]+dev[\\/]+fhirsql[-A-Za-z0-9]*", re.I)
DRIVE_RE = re.compile(r"/content/drive/MyDrive/projects/[A-Za-z0-9_-]+", re.I)
rewrites = 0
for root, _, files in os.walk(STAGE):
    for fn in files:
        if not fn.endswith((".py", ".ipynb", ".sql", ".ps1", ".md", ".txt", ".json")):
            continue
        p = os.path.join(root, fn)
        try:
            t = io.open(p, encoding="utf-8").read()
        except (UnicodeDecodeError, PermissionError):
            continue
        n = t
        n = PATH_RE.sub("<PROJECT_ROOT>", n)
        n = DRIVE_RE.sub("<PROJECT_ROOT>", n)
        if n != t:
            io.open(p, "w", encoding="utf-8").write(n); rewrites += 1
print("files with paths rewritten:", rewrites)

# ---------------------------------------------------------------- readme
io.open(os.path.join(STAGE, "README.txt"), "w", encoding="utf-8").write(
"""Supplementary material -- anonymized for double-blind review
============================================================

Contents

  scripts/     corpus generation, execution-verification, and the two analysis
               scripts that reproduce the paper's tables:
                 analyze_unseen_failures.py           -> Section 6 failure table
                 analyze_unseen_discriminativeness.py -> the 53.9% collision bound
  schema/      the frozen benchmark schema injected into every prompt, plus the
               valuesets DDL fragment used only in the ablation
  results/     every per-seed training log, held-out evaluation summary, failure
               log, and ablation leg behind the numbers in the paper
  *.ipynb      the supervised fine-tuning, reinforcement learning, and ablation
               notebooks, configured as run

Not included, to preserve anonymity: the paper, README, license, citation
metadata, and model card, all of which name the author or link to public
repositories. The generated datasets (~86 MB) and the DuckDB databases are
omitted for size; they are regenerable from scripts/ and will be linked in the
camera-ready version.

Absolute paths have been replaced with <PROJECT_ROOT>.

Reproducing the analysis tables requires only the committed logs:
    cd scripts && python analyze_unseen_failures.py
    cd scripts && python analyze_unseen_discriminativeness.py   (needs heldout.duckdb)
""")

# ---------------------------------------------------------------- audit
print("\n=== anonymity audit over staged bytes ===")
hits = {}
for root, _, files in os.walk(STAGE):
    for fn in files:
        p = os.path.join(root, fn)
        try:
            t = io.open(p, encoding="utf-8", errors="ignore").read().lower()
        except PermissionError:
            continue
        for w in IDENTIFYING:
            if w in t:
                hits.setdefault(w, []).append(os.path.relpath(p, STAGE))
if hits:
    for w, fs in hits.items():
        print(f"  LEAK {w!r}: {fs[:6]}")
    raise SystemExit("REFUSING to build archive - identifying strings present")
print("  clean: no identifying strings in any staged file")

# ---------------------------------------------------------------- zip
if os.path.exists(OUT):
    os.remove(OUT)
n = 0
with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    for root, _, files in os.walk(STAGE):
        for fn in files:
            p = os.path.join(root, fn)
            z.write(p, os.path.relpath(p, STAGE))
            n += 1
print(f"\nwrote {OUT}")
print(f"  {n} files, {os.path.getsize(OUT)/1e6:.2f} MB")
