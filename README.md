# Plan-Then-Compile: FHIR-to-SQL with Structured Reasoning Traces

Fine-tuning study translating natural-language hospital questions into DuckDB SQL against a FHIR-derived schema. Builds on [`adelelsayed/fhirsql`](https://github.com/adelelsayed/fhirsql) (DOI [10.5281/zenodo.21988210](https://doi.org/10.5281/zenodo.21988210)) by retargeting SFT and RL to produce a structured JSON query plan followed by the compiled SQL, in one continuous completion, so the RL stage has an actual reasoning trace to refine rather than a single flat SQL guess.

**Read `PAPER.md` first** — full method, results, and error analysis, with real numbers from a 3-seed SFT + DAPO/GRPO RL run.

## Headline results (mean across 3 seeds, held-out benchmark)

| | Frozen | SFT | SFT + RL |
|---|---:|---:|---:|
| Structural correctness (familiar concepts) | 0.0% | 99.6% | 99.6% |
| Structural correctness (unseen concepts) | 0.0% | 82.1% | 82.2% |
| Abstention precision / recall | 71-96% | 100% / 100% | 100% / 100% |
| Terminology-hardcoding rate | 3.0-3.4% | 0.0% | 0.0% |

RL does not measurably improve on SFT here — the same null result as the prior study, now replicated under a design built specifically to give RL a reasoning trace to work with. See `PAPER.md` Section 4.2 for why that strengthens rather than repeats the finding.

## Repository layout

- `PAPER.md` — the paper.
- `DESIGN.md` — design doc for the plan-JSON schema and the redesign's rationale (written during development, kept for the full reasoning trail).
- `METHODOLOGY_LOG.md` — dated methodology diary: schema/corpus decisions, bugs found and fixed (float non-determinism, ORDER BY tiebreaks), verification methodology.
- `sft_train.ipynb`, `rl_train.ipynb` — training notebooks (Colab/RunPod/local paths configurable).
- `scripts/` — corpus generation: `archetypes.py` (+ `operational_/quality_kpi_/regulatory_archetypes.py`) define question/plan/SQL templates; `generate_*_gold*.py`/`generate_*_backtranslations*.py` generate and verify gold data; `build_valuesets.py` builds the terminology lookup table; `plan_schema.py` documents the plan JSON schema.
- `schema/schema.sql` — the flattened FHIR-derived DuckDB schema.
- `data/training/` — assembled SFT and held-out benchmark JSONL files (`sft_final_plan.jsonl`, `heldout_benchmark_plan_{familiar,unseen}.jsonl`).
- `data/profile/` — corpus profiling (row counts, fill rates, concept bank) supporting the paper's data-quality claims.
- `results/` — training histories, held-out evaluation summaries, and failure logs for every seed and stage, backing every number in `PAPER.md`.
- `MODEL_CARD.md` — model card for the published adapter weights.

## Model weights

Best-checkpoint LoRA/DoRA adapters for all 3 seeds, both stages (SFT and SFT+RL), are published on Hugging Face — see `MODEL_CARD.md` for the repo link and loading instructions. Base model weights (`Qwen/Qwen2.5-Coder-14B-Instruct`, ~28GB) are not redistributed here; load them from Hugging Face directly.

## Reproducing

1. Generate the synthetic patient corpus and flatten it to DuckDB (`scripts/run_train_batches.ps1` / `run_heldout_batches.ps1`, `scripts/flatten_to_duckdb.py`) — regenerates `data/*.duckdb` and `data/parquet/`, excluded from this repo (multi-GB, regenerable).
2. Generate and verify gold data (`scripts/generate_gold_plan_sql.py` and category-specific variants) — regenerates `data/training/*.jsonl`.
3. Run `sft_train.ipynb`, then `rl_train.ipynb`.

## License

CC-BY-4.0 — see `LICENSE`. Citation metadata in `CITATION.cff`.
