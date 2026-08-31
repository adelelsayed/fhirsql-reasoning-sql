# Model Card: fhirsql-reasoning-sql adapters

- **Model repo:** https://huggingface.co/adelelsayed1991/fhirsql-reasoning-sql-adapters
- **Dataset repo:** https://huggingface.co/datasets/adelelsayed1991/fhirsql-reasoning-sql
- **Code & paper:** https://github.com/adelelsayed/fhirsql-reasoning-sql

DoRA/LoRA adapters for `Qwen/Qwen2.5-Coder-14B-Instruct`, fine-tuned to translate natural-language hospital questions into a structured JSON query plan followed by DuckDB SQL, against a FHIR-derived schema. See `PAPER.md` for the full study.

## Repository contents

Six adapters: 3 random seeds (42, 43, 44) x 2 training stages. SFT checkpoints are selected by **validation loss**; RL checkpoints by **dev-set execution match** (each stage's own trainer criterion):

```
sft/seed_42/best/    sft/seed_43/best/    sft/seed_44/best/
rl/seed_42/best/     rl/seed_43/best/     rl/seed_44/best/
```

- `sft/` — supervised fine-tuning only (DoRA, rank 16, alpha 32). **Use these.**
- `rl/` — the corresponding `sft/` seed's checkpoint, continued with DAPO/GRPO reinforcement learning. Per `PAPER.md` Section 5.3, the RL stage does not improve on its SFT starting point on this task (and is marginally worse in-corpus); all three seeds early-stopped at step 40 of 200 having peaked at the first evaluation checkpoint. These adapters are published for completeness and reproducibility, not because they outperform `sft/`.

Each `best/` folder contains a standard PEFT adapter (`adapter_config.json`, `adapter_model.safetensors`, ~271MB).

## Intended use

Research artifact for reproducing or extending `PAPER.md`'s results. Generates a `{plan JSON}` + fenced ` ```sql ` completion for a natural-language question, given a prompt containing the DDL from `schema/schema.sql`. Not intended for use outside that schema/prompt format, and not validated on real (non-synthetic) patient data or real clinical schemas.

## How to load

```python
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import PeftModel
import torch

base_name = "Qwen/Qwen2.5-Coder-14B-Instruct"
tokenizer = AutoTokenizer.from_pretrained(base_name)
base_model = AutoModelForCausalLM.from_pretrained(
    base_name, dtype=torch.bfloat16,
    quantization_config=BitsAndBytesConfig(
        load_in_4bit=True, bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True, bnb_4bit_quant_type="nf4",
    ),
)
model = PeftModel.from_pretrained(
    base_model,
    "adelelsayed1991/fhirsql-reasoning-sql-adapters",
    subfolder="sft/seed_42/best",   # recommended; swap to "rl/..." to reproduce the RL arm
)
```

Prompting details (system prompt template, schema DDL extraction, plan-then-SQL output format) are in `sft_train.ipynb` and `rl_train.ipynb`'s `SYSTEM_PROMPT_TEMPLATE`/`build_messages` cells.

## Training data

`data/training/sft_final_plan.jsonl` (10,696 rows: 9,680 execution-verified gold SQL + 1,016 abstention examples, spanning 82 archetypes and 2,420 distinct executable gold SQL statements), generated from a synthetic (Synthea) patient corpus — no real patient data was used anywhere in this project. Trained on Google Colab (G4 GPU, 96 GB RAM), 2 epochs per seed. See `DESIGN.md` and `METHODOLOGY_LOG.md` for full corpus and training-data generation methodology.

## Evaluation summary

Mean across the 3 SFT seeds on a held-out benchmark drawn from a disjoint patient population. Full results in `PAPER.md` Section 5; underlying per-seed data in `results/`.

| | Frozen base | SFT adapter |
|---|---:|---:|
| Execution correctness, familiar concepts | 34.8% | 100.0% |
| Execution correctness, unseen concepts | 60.8% | 89.1% |
| Abstention precision / recall (familiar arm) | 68% / 72% | 100% / 100% |
| Terminology-hardcoding rate | 0.0% | 0.0% |

The frozen column uses a complete schema description including the `valuesets` DDL (the fair
comparison). Under the exact training-time prompt, which omitted it, the frozen model scores
10.2% / 31.3% — see `PAPER.md` §5.6.

"Unseen concepts" are 84 clinical concepts appearing nowhere in training (verified by set
intersection; zero shared question/query pairs) — the adapters compose correct
terminology-resolution queries for them without ever having been trained on their codes. That
89.1% is an upper bound; text-match metrics give 81.4% as a lower bound (`PAPER.md` §6).

Abstention figures measure *retention* of trained refusal categories: the unanswerable questions
are reused verbatim across training and evaluation, so this is not held-out refusal
generalization (`PAPER.md` §2.7).

## Limitations

- Trained and evaluated entirely on synthetic (Synthea) data against one specific flattened schema (`schema/schema.sql`) — not validated against real clinical data or a different schema design.
- All training and evaluation questions come from the same template-and-persona back-translation factory (`scripts/question_templates.py`, `scripts/personas.py`); robustness to free-form clinician phrasing outside that distribution is untested.
- Single base model and scale (`Qwen2.5-Coder-14B-Instruct`, 14B parameters, 4-bit). Behavior at other scales or with other base models is untested.
- The frozen-baseline column above is the *fair* comparison (complete schema description). The training-time prompt omitted the `valuesets` DDL, under which the frozen model scores lower; `PAPER.md` §5.6 quantifies both.
- The unseen-concept arm shows a real ~11-point accuracy gap relative to familiar concepts. 78% of those failures are one benign, well-characterized pattern (over-applying SNOMED CT's parenthetical qualifier convention to concepts coded in other systems) — see `PAPER.md` Section 6.

## License

Adapter weights are released under **CC-BY-4.0**, matching the repository's paper/data license; the repository's code is Apache-2.0. See `LICENSE` and `CITATION.cff`. The base model `Qwen/Qwen2.5-Coder-14B-Instruct` retains its own license.
