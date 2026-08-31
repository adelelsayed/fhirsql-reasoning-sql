# Plan-Then-Compile: Turning a General-Purpose Coder Model into a FHIR Data Analyst

A frozen `Qwen2.5-Coder-14B-Instruct` is effectively unusable as an analyst over a FHIR-derived clinical database: asked ordinary hospital questions, it returns the right answer about one time in ten, never reproduces a correct query verbatim, and refuses unanswerable questions barely better than chance. This study takes that model to a working analyst — 100% execution correctness on a disjoint held-out patient population, 89.1% on clinical concepts it was never trained on — with a single supervised fine-tuning pass on a synthetic (Synthea) corpus.

Two design decisions carry the result. Each training target is a **structured JSON query plan followed by the compiled SQL**, so the model commits to which clinical entities the question names and which query archetype it implies *before* writing SQL — making its reasoning inspectable. And clinical terminology is **resolved through the database**: gold SQL never embeds a literal SNOMED/ICD-10/RxNorm code, resolving concepts instead through a lookup against a `valuesets` table, so competence transfers to concepts never seen in training rather than depending on memorized codes.

**Read [`PAPER.md`](PAPER.md) first** — full method, complete results, error analysis, and limitations.

## Headline results

Three seeds, `Qwen2.5-Coder-14B-Instruct` + DoRA, evaluated on a held-out benchmark drawn from a **disjoint patient population**:

| | Frozen | SFT | SFT + RL |
|---|---:|---:|---:|
| Execution correctness — familiar concepts | 34.8% | **100.0%** | 100.0% |
| Execution correctness — unseen concepts | 60.8% | **89.1%** | 89.2% |
| Abstention precision / recall (familiar arm) | 68% / 72% | **100% / 100%** | 100% / 100% |
| Terminology-hardcoding rate | 0.0% | **0.0%** | 0.0% |

All four frozen figures are measured with a **complete** schema description, including the
`valuesets` terminology table DDL that the training-time prompt omitted — the fair comparison.
Under that exact training-time prompt the frozen model scores 10.2% / 31.3% execution match and
hardcodes terminology in 3.0% / 3.4% of correct completions; `PAPER.md` §5.6 isolates the difference
and shows that schema visibility alone drives hardcoding to zero. Even given full schema information
the frozen model never reproduces a gold query (0.0% exact match) and writes queries 4.5–12× slower
than gold. Frozen figures come from the 750-row ablation sample; SFT/RL from the main evaluation.

The 1,016 unanswerable questions are reused verbatim across training and both held-out arms, so the
fine-tuned 100%/100% abstention measures *retention* of trained refusal behavior, not held-out
refusal generalization (`PAPER.md` §2.7, §7).

The **unseen-concept** arm uses 84 clinical concepts appearing nowhere in training (verified disjoint by set intersection; zero shared question/query pairs) — the number that matters, and the one the database-resolved terminology design exists to make possible. Its 89.1% is an upper bound; the text-match metrics give a lower bound of 81.4% (`PAPER.md` §6 explains why execution match is weakly discriminative on this arm).

**No overfitting** (`PAPER.md` §5.2): training and validation loss fall together with no
divergence, learned queries stay correct against a disjoint patient population, and the model
transfers to clinical concepts absent from training. The paper is explicit about which arm shows
what — the familiar arm is 96.5% verbatim training rows and demonstrates *retention*; the unseen
arm shares no question, query, or concept with training and is where transfer is established.

The DAPO/GRPO reinforcement-learning stage adds nothing: all three seeds early-stopped at step 40 of a 200-step budget having peaked at the *first* evaluation checkpoint, with mean reward pinned at or above the correct-answer floor on 37–38 of 40 steps. SFT already saturates the reward's correctness gate. See `PAPER.md` Section 5.3 for the dynamics and the mechanism.

## Repository layout

- [`PAPER.md`](PAPER.md) — the paper.
- [`DESIGN.md`](DESIGN.md) — the plan-JSON schema, lookup-CTE mechanism, and anti-hardcoding detector in implementation detail.
- [`METHODOLOGY_LOG.md`](METHODOLOGY_LOG.md) — dated development diary: schema and corpus decisions, bugs found and fixed (DuckDB float non-determinism, `ORDER BY` tiebreaks), verification methodology.
- [`MODEL_CARD.md`](MODEL_CARD.md) — model card for the published adapter weights.
- `sft_train.ipynb`, `rl_train.ipynb` — training notebooks, configured exactly as run for the published results.
- `valuesets_ablation.ipynb` — frozen-baseline ablation measuring the effect of showing the model the `valuesets` table DDL, which the published runs' schema omitted (`PAPER.md` §5.6). Four evaluation legs; no training required.
- `scripts/` — corpus generation, verification, and analysis (`analyze_unseen_failures.py`, `analyze_unseen_discriminativeness.py`). `archetypes.py` (+ `operational_`/`quality_kpi_`/`regulatory_archetypes.py`) define the question/plan/SQL templates; `generate_*_plan_sql.py` and `generate_*_backtranslations_plan.py` instantiate, execution-verify, and back-translate them; `build_valuesets.py` builds the terminology lookup table; `plan_schema.py` documents the plan JSON schema; `analyze_unseen_failures.py` reproduces the paper's error-analysis table.
- `schema/schema.sql` — the frozen, benchmark-facing DuckDB schema (injected verbatim into every prompt), kept exactly as used for the published runs. `schema/valuesets_ddl.sql` is a separate ablation fragment, deliberately not merged in.
- `data/training/` — assembled datasets: `sft_final_plan.jsonl` (10,696 rows) and `heldout_benchmark_plan_{familiar,unseen}.jsonl`.
- `data/profile/` — corpus profiling (row counts, fill rates, concept bank).
- `results/` — every number in the paper: per-seed training logs and histories, held-out evaluation summaries for all three model states, failure logs, and the `valuesets` ablation legs.

## Environment

Trained and evaluated on Google Colab (G4 GPU instance, 96 GB RAM). SFT ran ~5.9 h/epoch/seed at 4-bit; RL ~7.3 min/step (median).

## Reproducing

1. Generate the synthetic corpus and flatten it to DuckDB — `scripts/run_train_batches.ps1` / `run_heldout_batches.ps1`, then `scripts/flatten_to_duckdb.py`, `profile_data.py`, `select_concepts.py`, `build_valuesets.py`. This regenerates `data/*.duckdb` and `data/parquet/`, which are excluded from git (multi-GB, fully regenerable).
2. Generate and execution-verify gold data — `scripts/generate_gold_plan_sql.py` and the category-specific variants, then the `generate_*_backtranslations_plan.py` scripts. Regenerates `data/training/*.jsonl`.
3. Run `sft_train.ipynb`, then `rl_train.ipynb`.

## Model weights

Best-checkpoint adapters for all three seeds and both stages are on Hugging Face — see [`MODEL_CARD.md`](MODEL_CARD.md). Base model weights (`Qwen/Qwen2.5-Coder-14B-Instruct`, ~28 GB) are not redistributed here.

## License

Dual-licensed: **Apache-2.0** for code (`scripts/`, notebooks, `schema/`) and **CC-BY-4.0** for the paper, documentation, and data. See [`LICENSE`](LICENSE); citation metadata in [`CITATION.cff`](CITATION.cff).
