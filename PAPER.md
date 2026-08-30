# Plan-Then-Compile: Structured Reasoning Traces for FHIR-to-SQL Fine-Tuning

**Adel Elsayed**

## Abstract

A prior study (Elsayed, 2026a — *From Frozen to Fluent*, DOI [10.5281/zenodo.21988210](https://doi.org/10.5281/zenodo.21988210)) fine-tuned Qwen2.5-Coder-14B-Instruct with DoRA SFT to translate natural-language hospital questions directly into DuckDB SQL against a FHIR-derived schema, and found that a follow-up DAPO/GRPO reinforcement-learning stage did not measurably improve on the SFT baseline. That study's RL stage had a flat `question -> SQL` target to refine: a single guess with no intermediate reasoning trace, even though DAPO/GRPO were designed around exactly the reasoning-trace-then-answer shape that setup lacked. This work retargets the same pipeline to produce a **structured JSON query plan followed by the compiled SQL, in one continuous completion**, so both SFT and RL have an inspectable reasoning artifact to learn over and refine. It also adds a reward penalty for a specific failure mode the flat-SQL design could not detect: a model hardcoding a terminology literal (a SNOMED/ICD/RxNorm code) into the query instead of resolving it through the schema's lookup mechanism.

Across three seeds, SFT lifts structural query-plan correctness from 0% (frozen base model) to 99.6% on familiar clinical concepts and 82.1% on clinical concepts never seen in training, while eliminating terminology-hardcoding entirely (0.0% vs. the frozen model's 3.0-3.4%) and reaching perfect abstention precision and recall (100%/100% vs. the frozen model's 71-96%). A subsequent DAPO/GRPO RL stage again does not move any of these numbers beyond what SFT alone achieves — the same finding as the prior study, now replicated under a materially different completion format, which is evidence the finding reflects something about the task and reward surface rather than an artifact of the flat-SQL setup. A database-verified analysis of the residual unseen-concept failures finds that 78% are a single, benign, identifiable surface-form pattern — the model appending a SNOMED-style qualifier suffix (e.g. "(disorder)") to concepts coded in systems that don't use that convention — rather than genuine compositional-reasoning errors.

## 1. Motivation: what the reasoning-trace redesign responds to

The prior study's RL stage trained on a direct `question -> SQL` mapping. Two limitations followed directly from that shape:

1. **RL had nothing to refine.** DAPO and GRPO (Yu et al., 2025; Shao et al., 2024) were motivated by long chain-of-thought math and code reasoning, where a model samples multiple *reasoning-then-answer* trajectories per prompt and reward comparisons across the group teach it to reason better before answering. A flat SQL target gives RL a single guess to nudge token-by-token, not a reasoning process to improve.
2. **No way to inspect compositional understanding separately from surface pattern-matching.** With only a final SQL string to look at, there was no artifact that separated "the model understood which clinical concept, constraint, and aggregation the question required" from "the model pattern-matched the question to a memorized archetype shape."

This study's redesign asks the model to produce, in a single completion:

```
{
  "entities": [{"role": "primary", "concept": "Biopsy of breast (procedure)",
                "domain": "procedure", "terminology_lookup": true}],
  "constraints": [{"type": "status", "field": "status", "value": "completed"}],
  "aggregation": {"type": "list_distinct_patient", "group_by": null,
                  "order_by": null, "limit": null},
  "abstain": false
}
```
```sql
WITH resolved AS (
  SELECT code, code_system FROM valuesets
  WHERE table_name = 'procedure' AND display ILIKE '%Biopsy of breast (procedure)%'
)
SELECT DISTINCT p.patient_id FROM procedure p
JOIN resolved r ON p.code = r.code AND p.code_system = r.code_system
WHERE p.status = 'completed'
```

The plan's vocabulary (`entities`/`joins`/`constraints`/`aggregation`) is closed and enumerable by design — every value maps 1:1 to a clause shape an archetype's SQL template already needs — so the model's job is compositional selection from a fixed inventory, not free-form generation of an unbounded schema. Terminology resolution is unchanged from the prior study's design: the model never needs to know a code, only to name the concept and compile a syntactically correct lookup CTE (`WITH resolved AS (SELECT code, code_system FROM valuesets WHERE table_name = '...' AND display ILIKE '%{concept}%')`) around it — codes are resolved against the `valuesets` table at query time, not memorized.

SFT is trained on `question -> plan + SQL` as one continuous target, so RL inherits a warm-started policy for the whole trace rather than a cold start on a totally new task. RL's reward is computed **only on the final SQL's** execution correctness and efficiency — the plan is never separately rewarded — but producing a correct SQL compilation requires the preceding plan to actually be right, so gradient signal flows back through the whole completion. Full schema and design rationale: `scripts/plan_schema.py`, `DESIGN.md`.

## 2. Anti-hardcoding reward penalty

A model can produce an executing, even correct-looking, query by hardcoding a literal terminology code (`WHERE code = '271737000'`) instead of resolving it through the lookup CTE. This is silently invisible to an execution-correctness-only reward: the query still runs and returns the right rows in-sample, but the underlying capability being tested — composing a resolution query against a coding system, the actual point of the schema design — is being bypassed rather than demonstrated. Because the base model would need to have memorized real SNOMED/ICD/RxNorm codes to do this, the schema and reward specifically make bypassing the lookup mechanism a distinct failure mode worth detecting and penalizing.

`has_hardcoded_terminology()` flags any of `code`/`system`/`type_code`/`type_system`/`vaccineCode`/`vaccineCode_system` compared to a quoted literal via regex. This is sound by construction under this schema: every legitimate lookup CTE filters exclusively on `table_name`/`display`, never on those columns directly, so a match can only occur when the lookup has been bypassed. A correct-but-hardcoded completion scores `reward_hardcoded_value = -0.2` (instead of the correct-answer tier) and never earns the efficiency bonus. The detector was validated against all 10,696 real gold-SQL statements in the training set with zero false positives, and confirmed to correctly ignore legitimate non-terminology literals such as `class_code = 'IMP'` or `clinicalStatus = 'active'`.

## 3. Experimental setup

- **Base model:** `Qwen/Qwen2.5-Coder-14B-Instruct`, NF4 4-bit quantized (QLoRA).
- **SFT:** DoRA (Liu et al., 2024), rank 16, alpha 32, all-linear-layer target modules. Up to 3 epochs with early stopping (skip epoch 3 if epoch 2's relative validation-loss improvement over epoch 1 is below 5%).
- **RL:** DAPO/GRPO (Yu et al., 2025; Shao et al., 2024) — Clip-Higher asymmetric clipping, Dynamic Sampling (dropping zero-reward-variance groups), token-level loss normalization, group-relative advantage.
- **Data:** 10,696 SFT training rows (main clinical archetypes + operational/regulatory/quality-KPI archetypes + abstention examples), all with execution-verified gold SQL against a synthetic (Synthea) patient corpus.
- **Evaluation:** a two-arm held-out benchmark from a disjoint patient population — **familiar** (clinical concepts seen during training, different patients) and **unseen** (clinical concepts never seen during training) — run against the model's full held-out arms (not a subsample). Three independent seeds (42, 43, 44) for both SFT and RL.
- **Metrics:** `gen_structure_match` (does the generated plan's structure match gold — the primary correctness metric, robust to superficial SQL-text variation), `gen_exec_match` (does the generated SQL execute to the same result set as gold), `gen_exact_match` (reported alongside structure_match as a secondary check; the two track each other closely in this run — see Section 4 — unlike the prior study, where exact-match text comparison was affected by floating-point non-determinism in `AVG()` aggregates and was excluded from headline reporting for that reason), `gen_abstention_precision/recall` (correctly declining unanswerable questions), `gen_hardcoded_rate` (diagnostic: fraction of correct completions that bypassed the lookup mechanism), `gen_efficiency_speedup` (gold-query-time / predicted-query-time, cache-fair, among execution-correct completions).

## 4. Results

### 4.1 Frozen baseline vs. fine-tuned (mean across 3 seeds)

| Metric | Frozen (familiar) | Frozen (unseen) | SFT (familiar) | SFT (unseen) | RL (familiar) | RL (unseen) |
|---|---:|---:|---:|---:|---:|---:|
| `gen_structure_match` | 0.0% | 0.0% | 99.6% | 82.1% | 99.6% | 82.2% |
| `gen_exact_match` | 0.0% | 0.0% | 99.6% | 81.4% | 99.6% | 82.1% |
| `gen_exec_match` | 10.2% | 31.3% | 100.0% | 89.1% | 100.0% | 89.2% |
| `gen_abstention_precision` | 71.3% | 96.3% | 100.0% | 100.0% | 100.0% | 100.0% |
| `gen_abstention_recall` | 73.6% | 71.6% | 100.0% | 100.0% | 100.0% | 100.0% |
| `gen_hardcoded_rate` | 3.0% | 3.4% | 0.0% | 0.0% | 0.0% | 0.0% |

Per-seed numbers: `results/heldout_eval/*.json`. A frozen instruction-tuned coder model cannot compose a correct query against this schema at all (0% structural correctness on either arm) — it can occasionally stumble into an executing query by chance or by hardcoding a value it happens to know, but it does not reliably produce the plan-and-lookup structure the schema requires. A single round of SFT changes this completely, and does so for concepts the model never saw a training example of, not only for concepts it memorized a template for.

### 4.2 SFT vs. RL: no measurable RL gain, replicated under a new completion format

RL does not move any headline metric beyond SFT's baseline, within seed-to-seed noise (e.g. familiar `gen_structure_match`: SFT 99.51-99.70% vs. RL 99.48-99.70%; unseen: SFT 77.4-86.5% vs. RL 77.4-86.8%). RL's own training-time `mean_reward` stayed essentially flat across all 40 logged steps for every seed (seed 42: 1.002 -> 1.005, min 0.977; seed 43: 1.005 -> 1.005, min 0.940; seed 44: 1.005 -> 0.980, min 0.976) — consistent with RL starting from an already near-ceiling SFT policy and finding little room to improve a reward it can already mostly satisfy.

This null result for RL is the same finding as the prior flat-SQL study, but it no longer rests on the concern raised in Section 1 — that RL had nothing but a single guess to refine. Here RL is training over a genuine reasoning-trace-then-answer completion, the shape DAPO/GRPO were designed for, and reward is computed end-to-end through that trace. The fact that RL still does not improve on SFT under this design is stronger evidence that **SFT alone reaches this task's achievable ceiling on this schema and data distribution** — not that the flat-SQL format was suppressing RL's ability to help.

### 4.3 Anti-hardcoding penalty: fully effective post-training

The frozen base model hardcodes a terminology literal in 3.0-3.4% of its (rare) correct-looking completions. Every fine-tuned model — SFT and RL, all three seeds, both arms — hardcodes in exactly 0.0% of completions. The training data's gold SQL is always properly lookup-based, so this reflects the model learning the intended query-composition pattern rather than the reward penalty being needed to correct against a real observed tendency to hardcode during training; it is reported here as a clean confirmation that the detector generalizes correctly to real model output at eval time, not just to gold data (Section 2).

### 4.4 Training stability: no divergence between train and validation loss

SFT training and validation loss decrease together across both epochs (early stopping triggered after epoch 2 for all three seeds, per the 5%-relative-improvement threshold) with no divergence: e.g. seed 42's train loss falls from 0.0160 to 0.00019 while validation loss falls from 0.0016 to 0.00034 — both moving in the same direction, validation never rising as training continues. Per-seed curves: `results/sft_outputs/seed_*/history.json`.

## 5. Error analysis: what's actually left on the unseen arm

Unseen-concept structural correctness (82.1%) sits well below familiar-concept correctness (99.6%) — a real, non-trivial generalization gap the aggregate numbers alone don't explain. A database-verified analysis of all 743 unseen-arm failures across all six fine-tuned runs (SFT x3 seeds, RL x3 seeds; the familiar arm produced **zero** failures across all six runs) attributes them to:

| Failure category | Count | Share |
|---|---:|---:|
| Added an extra qualifier suffix not present in gold | 580 | 78.1% |
| Substantively different search phrase | 113 | 15.2% |
| Wrong qualifier suffix | 28 | 3.8% |
| Same search term, other SQL difference | 18 | 2.4% |
| Missing a qualifier suffix present in gold | 2 | 0.3% |
| Same base phrase, other minor difference | 2 | 0.3% |

The dominant category (78.1%) is a single, identifiable, benign pattern: the model appends a SNOMED CT-style qualifier suffix — `(disorder)`, `(finding)`, `(situation)`, `(procedure)`, etc. — to a concept's display text even when that concept is coded in a system that doesn't use the convention (e.g. an ICD-10 diagnosis or a CDT dental procedure code). This is over-generalization of a real, frequent SNOMED CT naming pattern onto concepts from other terminology systems, verified directly against `valuesets` table contents in the held-out database (e.g. "Chronic sialoadenitis" is coded ICD-10 `K11.23` and has no parenthetical suffix in its actual display text; several CDT dental codes such as `D2663` contain literal double-spaces in their display text that a model reproducing the SNOMED convention would not anticipate). Because the lookup CTE uses `ILIKE '%...%'` containment matching, an extra suffix the gold display text doesn't contain simply fails to match any row, which is why this surfaces as an execution/structure mismatch rather than a silent wrong answer.

Only the second category — 15.2%, substantively different search phrases — looks like a genuine concept-identification error rather than a surface-form artifact. Combined with the zero-failure familiar arm, this suggests the model's underlying compositional-reasoning skill (choosing the right entities, constraints, and aggregation shape) transfers cleanly to unseen concepts; what does not fully transfer is knowing, for an unfamiliar concept, which terminology system's display-text convention applies before that concept has been seen resolved during training.

## 6. What this run supports as a finding, and what it doesn't

**Supported:**
- Fine-tuning (SFT) is necessary and sufficient to take this schema from unusable (0% structural correctness on a frozen instruction-tuned coder model) to reliable (99.6% familiar, 82.1% unseen), replicated across 3 seeds.
- The reasoning-trace-then-answer redesign is a fair, and if anything more favorable, setup for the RL stage than the prior study's flat-SQL format, and RL still shows no measurable gain over SFT under it — strengthening (not merely repeating) the prior null result for RL on this task.
- An explicit reward penalty against terminology-hardcoding is implementable with zero false positives against real gold data and generalizes correctly to real model output (0% hardcoding rate post-training, across every fine-tuned run).
- Fine-tuning drives abstention precision and recall from a frozen model's 71-96% range to a perfect 100%/100%, across every fine-tuned run and arm.
- The residual gap between familiar- and unseen-concept correctness is mostly explained (78% of failures) by one specific, benign, well-understood surface-form pattern, not a diffuse or mysterious reasoning failure.

**Not supported / left open:**
- This does not show RL is never useful for this class of task — only that, on this reward surface, data distribution, and model scale, RL does not improve on a strong SFT baseline that already reaches a high ceiling.
- The 15.2% of unseen failures that are substantively different search phrases are not further explained here; whether they reflect a genuinely harder subset of concepts or a fixable data/prompting gap is open.
- Efficiency-speedup numbers (`gen_efficiency_speedup`, hovering near 1.0x for SFT/RL) indicate the fine-tuned models' query plans are about as efficient as gold, not that either training stage specifically improved efficiency beyond what correct lookup-CTE composition already implies.

## Model weights and data

Best-checkpoint LoRA/DoRA adapters for all 3 seeds, both training stages (6 adapters total), are published on Hugging Face: see `MODEL_CARD.md`. Full training/evaluation artifacts (loss histories, held-out evaluation summaries, failure logs) are in `results/`.

## Acknowledgments

Claude Code (Anthropic) was used as an engineering assistant throughout this project: implementing the plan-JSON schema and archetype conversions, drafting and iterating on the training notebooks, and assisting with data analysis and this paper's drafting. All experimental design decisions, result interpretation, and conclusions are the author's own.

## References

See `CITATIONS.md` for the full reference list (data standards, infrastructure, base model, fine-tuning method). Directly relevant to this paper's framing:

- Elsayed A. From Frozen to Fluent: DoRA Fine-Tuning for Reliable, Generalizing FHIR-to-SQL Generation. 2026a. DOI: [10.5281/zenodo.21988210](https://doi.org/10.5281/zenodo.21988210) — the prior, flat-`question->SQL` study this work responds to and builds on.
- Liu SY, Wang CY, Yin H, Molchanov P, Wang YCF, Cheng KT, Chen MH. DoRA: Weight-Decomposed Low-Rank Adaptation. ICML 2024 (Oral). arXiv:2402.09353.
- Yu Q, Zhang Z, Zhu R, et al. DAPO: An Open-Source LLM Reinforcement Learning System at Scale. arXiv:2503.14476, 2025.
- Shao Z, Wang P, Zhu Q, et al. DeepSeekMath: Pushing the Limits of Mathematical Reasoning in Open Language Models. arXiv:2402.03300, 2024. (Origin of GRPO.)
- Walonoski J, Kramer M, Nichols J, et al. Synthea: An approach, method, and software mechanism for generating synthetic patients and the synthetic electronic health care record. JAMIA, 2018. DOI: 10.1093/jamia/ocx079.
