# Plan-Then-Compile: Turning a General-Purpose Coder Model into a FHIR Data Analyst

**Adel Elsayed**

## Abstract

A frozen `Qwen2.5-Coder-14B-Instruct` is not a usable analyst over a FHIR-derived clinical database. Asked ordinary hospital questions — *"how many patients had a depression screening?"*, *"what's the average length of stay for inpatient encounters?"* — it answers roughly a third correctly on familiar clinical concepts and three-fifths on rarer ones **even when handed a complete schema description**, never once reproduces a correct query verbatim, refuses unanswerable questions unreliably in both directions, and writes queries 4.5–12× slower than gold. The model is a capable SQL writer; what it lacks is this schema, this clinical vocabulary, and any sense of where the boundary of the answerable lies.

This study takes that model to a working analyst. Fine-tuning with DoRA on 10,696 examples (9,680 execution-verified queries plus 1,016 unanswerable questions) raises end-to-end execution correctness on a **disjoint held-out patient population** to **100.0%**, and on clinical concepts appearing **nowhere in training** to **89.1%** (85.0–92.1% across three seeds) — from frozen baselines of 34.8% and 60.8% measured with that same complete schema description. Under the exact prompt used during training, which omitted the terminology table's DDL, the frozen baseline scores 10.2% and 31.3%; a dedicated ablation (Section 5.6) separates the two, and finds that simply making the lookup table visible drives the untrained model's terminology-hardcoding to zero.

The paper is deliberate about what each evaluation arm can show. The familiar arm's questions are 96.5% verbatim training rows and its abstention set is reused wholesale from training, so those results demonstrate *retention* — learned queries staying correct against a new patient population — not resistance to memorization. The unseen arm shares no question, no query, and no clinical concept with training, and is where transfer is actually established. Its 89.1% is an upper bound: unseen concepts are rare and their gold answers are small integers, so 53.9% of within-archetype concept pairs return identical results and a wrong concept can go undetected by execution match (Section 6); the text-match metrics, which cannot be satisfied that way, put a lower bound of 81.4%. Training and validation loss fall together with no divergence throughout.

The method rests on two design decisions. Each training target is a **structured JSON query plan followed by the compiled SQL** in one continuous completion, so the model commits to which clinical entities the question names, which query archetype it implies, and what aggregation it needs *before* writing SQL — making its reasoning inspectable rather than inferred from output. And the schema resolves clinical terminology **through the database**: gold SQL never embeds a literal SNOMED/ICD-10/RxNorm code, resolving concepts instead through a lookup against a `valuesets` table, so the model is never rewarded for memorizing codes and its competence transfers to concepts it has never seen. A reward penalty and detector for bypassing that lookup (Section 3.3) confirm the behavior holds: hardcoding falls from 3.0% in the frozen model to 0.0% in every fine-tuned run.

A subsequent DAPO/GRPO reinforcement-learning stage adds nothing measurable, and the training dynamics show why: all three seeds early-stop at step 40 of a 200-step budget having peaked at the *first* evaluation checkpoint, with mean reward pinned at or above the correct-answer floor on 37–38 of 40 steps. Supervised fine-tuning already saturates the reward's correctness gate.

The broader implication is that a mid-sized open-weight model can be converted, at modest cost, into a competent domain analyst for a specialized schema and vocabulary that no general-purpose model handles out of the box — a recipe that should transfer to other niche, normalized, terminology-heavy systems.

## 1. The task and what it actually requires

### 1.1 Four skills hiding inside one question

"How many patients with essential hypertension were prescribed a statin last year?" looks like a single translation step. It decomposes into at least four distinguishable skills:

1. **Clinical entity isolation** — recognizing that this question names *two* clinical concepts ("essential hypertension", "a statin"), one of which is the primary subject and one a companion condition, and that "last year" is a temporal constraint rather than a third entity.
2. **Query archetype identification** — recognizing the *shape* the question implies: a two-concept patient-cohort intersection with a temporal filter and a distinct-patient count, as opposed to a per-patient average, a top-N ranking, or a year-over-year trend.
3. **Query composition** — turning that shape into correct SQL over a specific normalized schema: which tables, which join keys, which aggregation, which grouping.
4. **Terminology resolution** — mapping each named concept to the code, in the coding system, that this database actually stores it under.

These fail differently and generalize differently. Skills 1–3 are reasoning that should transfer to unfamiliar subject matter. Skill 4, if performed from parametric memory, is recall: it degrades sharply for rare concepts, varies unpredictably across coding systems (SNOMED CT, ICD-10, RxNorm, LOINC, CDT all appear in this corpus), and cannot be audited.

Conventional text-to-SQL training collapses all four into one opaque mapping from question to query string. That is a problem for measurement as much as for capability: when a model gets an answer wrong, there is no way to tell whether it misread the clinical intent, picked the wrong query shape, wrote malformed SQL, or simply didn't know a code. And when it gets an answer *right*, there is no way to tell whether it reasoned or recognized.

This study's design separates these skills so that each can be trained and observed.

### 1.2 Design decision one: make the reasoning explicit and inspectable

Each training target is a structured JSON query plan followed by the compiled SQL, as one continuous completion:

```
{
  "entities": [{"role": "primary", "concept": "Depression screening (procedure)",
                "domain": "procedure", "terminology_lookup": true}],
  "joins": [],
  "constraints": [{"type": "status", "field": "status", "value": "completed"}],
  "aggregation": {"type": "list_distinct_patient", "group_by": null,
                  "order_by": null, "limit": null, "per_patient_metric": null},
  "abstain": false
}
```
```sql
WITH resolved AS (
    SELECT code, code_system FROM valuesets
    WHERE table_name = 'procedure' AND display ILIKE '%Depression screening (procedure)%'
)
SELECT DISTINCT patient_id
FROM procedure, resolved
WHERE procedure.code = resolved.code AND procedure.system = resolved.code_system
  AND status = 'completed'
```

(A real training target from `data/training/sft_final_plan.jsonl`, reformatted for the page; content unchanged.)

The `entities` array is skill 1 made explicit — which concepts the question names, which is primary versus companion, which clinical domain each belongs to, and whether each requires terminology lookup. The `aggregation` and `constraints` fields are skill 2 — the query archetype, drawn from a closed vocabulary where every value maps 1:1 to a clause shape some archetype's SQL template already needs. The SQL block is skills 3 and 4.

Because the plan precedes the SQL in a single autoregressive completion, the model must commit to its reading of the question before composing the query, and that commitment is recoverable from the output. Extending to a new query shape means deliberately extending the vocabulary (documented in `scripts/plan_schema.py`) rather than letting the model invent categories.

This also gives a reinforcement-learning stage a genuine reasoning trace to refine rather than a single opaque guess — the reasoning-then-answer shape GRPO and DAPO were designed around.

### 1.3 Design decision two: resolve terminology in the database

Every coded table carries a `code`/`system`/`display` triple, and a `valuesets` table indexes every `(table_name, code, code_system, display)` combination in the corpus. Gold SQL never contains a literal clinical code; it resolves the concept at query time, as in the example above.

This requires no retrieval infrastructure, no tool calls, and no prompt-format change — it is ordinary SQL against columns that already exist. What it buys: the model needs only to produce a plausible search phrase, DuckDB resolves it deterministically, and the capability transfers to concepts never encountered in training.

This is not a hypothetical benefit. An earlier iteration of this project's own pipeline embedded literal codes in gold SQL. Under that design a fine-tuned model reached 98.4% execution match on familiar concepts but **20.7%** on unseen ones, with 2.7% exact match (recorded in `METHODOLOGY_LOG.md`, 2026-08-16). The collapse was not a reasoning failure — the model could not know codes it had never been shown. Rebuilding the corpus around database-resolved terminology is the response to that measurement; the 89.1% reported here is the direct comparison.

Concepts whose display text ambiguously matches more than one `valuesets` row (computed by self-join, flagged `lookup_ambiguous`) are excluded from gold generation rather than resolved by an arbitrary tiebreak, so no gold query depends on a coin flip.

### 1.4 Related work

**Text-to-SQL benchmarks and models.** Cross-domain text-to-SQL is well established, from WikiSQL (Zhong et al., 2017) and Spider (Yu et al., 2018) to BIRD (Li et al., 2023), which added execution efficiency and dirty-value handling to the evaluation. Execution correctness as the primary metric, and the difficulty of schema linking, are inherited from that line rather than introduced here. Execution-guided decoding (Wang et al., 2018) and constrained decoding via PICARD (Scholak et al., 2021) are standard techniques for keeping generated SQL valid; this work uses neither, relying on supervised fine-tuning alone, which is a difference worth noting rather than an advantage claimed.

**Intermediate representations.** Emitting a structured plan before SQL is not new. IRNet's SemQL (Guo et al., 2019), RAT-SQL (Wang et al., 2020), and NatSQL (Gan et al., 2021) all interpose an abstraction between question and query to reduce the mismatch between natural-language intent and SQL syntax; in the LLM era, DIN-SQL (Pourreza & Rafiei, 2023) decomposes generation into explicit sub-steps and DAIL-SQL (Gao et al., 2024) systematizes prompt organization. This study's contribution on that axis is narrow and should be read as such: the plan is emitted *in the same completion* as the SQL so that a single autoregressive pass yields both an inspectable intermediate artifact and the executable answer, and the plan's vocabulary is closed and archetype-derived rather than a general-purpose query IR.

**Clinical text-to-SQL.** MIMICSQL/TREQS (Wang et al., 2020) and EHRSQL (Lee et al., 2022) established the clinical setting, and both already resolve clinical concepts by matching against dictionary tables rather than embedding memorized codes — the mechanism this paper calls database-resolved terminology is, in its essentials, established practice in that literature. EHRSQL further makes *unanswerable* questions a first-class part of the benchmark, and TrustSQL (Lee et al., 2024) formalizes reliability-aware evaluation where abstention is scored explicitly; the abstention design here follows that precedent rather than introducing it. Criteria2Query (Yuan et al., 2019) addresses the adjacent problem of turning eligibility criteria into executable cohort queries. What differs in this study is the substrate and the measurement: a FHIR-native flattened schema spanning six coding systems rather than MIMIC's relational tables, a two-arm benchmark that isolates concept generalization from population generalization, and a soundness-by-construction detector that verifies the lookup mechanism was actually used rather than bypassed.

**Reinforcement learning for SQL.** Seq2SQL (Zhong et al., 2017) applied execution-reward policy gradients to text-to-SQL well before current RLHF-style methods. This work applies DAPO (Yu et al., 2025), a GRPO-family method (Shao et al., 2024) from the reasoning-model literature, and reports a null result — which is a data point about a saturated objective, not a novel algorithm.

**Positioning.** Individually, most components here have precedent. The contribution is the combination and what it makes measurable: a FHIR-derived corpus where terminology resolution is a queryable operation rather than recall, an inspectable plan trained jointly with the SQL, a verifiable check that the lookup was not bypassed, and an evaluation that separates the arm which can only show retention from the arm which can show transfer.

### 1.5 Contributions

- A demonstration that a mid-sized open-weight coder model can be converted into a reliable analyst for a specialized clinical schema and vocabulary it initially cannot use at all, at roughly a day of single-GPU compute.
- A FHIR-native corpus and schema in which clinical terminology across six coding systems is resolved **through the database**, with an evaluation design that isolates generalization to clinical concepts absent from training.
- A soundness-by-construction detector and reward penalty for terminology-hardcoding, validated with zero false positives across all 9,680 gold-SQL-bearing training rows — plus the finding that schema *visibility* alone, with no training signal, eliminates hardcoding in the untrained model (Section 5.6).
- A plan-then-compile target format that emits an inspectable intermediate representation and its compiled SQL in one completion, instantiating a known idea (above) in a form where clinical-entity isolation and archetype identification are separately readable.
- A three-seed evaluation reporting the complete metric suite, with explicit accounting of how much of each held-out arm is genuinely novel, and a quantified bound on how discriminative execution match is on the harder arm.
- Evidence, with training dynamics, that DAPO/GRPO adds nothing once SFT saturates the task.

## 2. Building the corpus

Everything in this study is generated, verified, and measured by committed code; no step depends on manual curation that a reader cannot reproduce.

### 2.1 Synthetic patient populations

Patient data comes from **Synthea** (v3.4.0-18-ga07a65555), an open-source synthetic patient generator that simulates complete longitudinal medical histories — encounters, conditions, medications, procedures, observations, immunizations — with realistic clinical coding, without any real patient data.

Two populations were generated as independent sub-batches varied by age bracket and US state, all with a frozen reference date of 2026-08-02:

| Population | Patients | Seed family | Purpose |
|---|---:|---|---|
| Train | 18,999 | 10000–10399 | all training data |
| Held-out | 6,383 | 20000–20399 | all held-out evaluation |

Seed families are disjoint by construction, and zero `patient_id` overlap was verified by direct set intersection. Generation is reproducible via `scripts/run_train_batches.ps1` and `run_heldout_batches.ps1`.

### 2.2 Schema

FHIR NDJSON output is flattened into DuckDB (`scripts/flatten_to_duckdb.py`) in two layers: 11 benchmark-facing core clinical tables that models see in every prompt, and full-fidelity auxiliary tables retained but never shown. Column names follow FHIR element names directly (`onsetDateTime`, `clinicalStatus`, `vaccineCode`, `valueQuantity`, …) so a model's clinical-language understanding maps onto the schema with minimal translation. The complete DDL is `schema/schema.sql`, injected verbatim into every prompt.

Secondary (ART) indexes were added to the coding-triple columns on both databases identically, so any execution-time measurement means the same thing on both.

### 2.3 Concept selection

The corpus profiler (`scripts/profile_data.py`) computes a **concept bank**: every distinct `(table, code, system)` triple with its row count and distinct-patient coverage. The train population yields **2,595 distinct concepts**, of which **1,248** have ≥50-patient coverage.

Selection into the training factory (`scripts/select_concepts.py`) is deliberate rather than top-N:

- **Near-universal administrative and SDOH codes are excluded** — a "medication review due" boilerplate code present in 100% of patients, employment-status and education-level findings, dental-referral administrative procedures. These carry no differential clinical signal.
- **A 90%-of-population coverage ceiling** applies to condition, procedure, and encounter: a code nearly every patient has cannot discriminate for "which patients have X"-shaped questions. Observation and diagnostic_report are left unrestricted, since ubiquitous vitals like heart rate are legitimate subjects for "compute statistics of X"-shaped questions regardless of prevalence.
- **Selection spreads across the coverage range** per table rather than taking the most common, so both common and rare concepts appear.

**382 concepts were selected**, distributed: condition 90, observation 70, medication_request 60, procedure 45, encounter 45, diagnostic_report 30, allergy 21, immunization 21.

### 2.4 Archetypes

An **archetype** is a parameterized query shape: a SQL template plus a matching plan template, instantiated against one concept at a time. 82 archetypes appear in the assembled data — 64 answerable and 18 unanswerable — organized in tiers of increasing compositional difficulty:

| Tier | Shape | Examples |
|---|---|---|
| 1 | single table, single concept | count/list patients with a condition; average value of an observation |
| 2 | single table with filters or grouping | high-value observations; counts by year; status-filtered cohorts |
| 3 | multi-table joins, companion concepts | patients with condition X also prescribed Y; per-patient procedure counts; demographic breakdowns |
| 4 | windowed and temporal reasoning | most-recent observation per patient; time from diagnosis to treatment; year-over-year trend deltas |
| — | operational / regulatory / quality-KPI | physician attribution, bed occupancy and length of stay, notifiable-disease surveillance, controlled-substance reporting, readmission and mortality review |
| 5 | unanswerable | questions the schema genuinely cannot answer |

The operational, regulatory, and quality-KPI archetypes exist so the corpus reflects the questions hospitals actually ask, not only textbook clinical queries — physician-level attribution, occupancy, mandated reporting, and quality indicators.

**The unanswerable tier is a deliberate safety design.** ~9.5% of training rows reference data Synthea never generates or concepts outside the modeled scope (Section 2.7). Their gold target is a literal `UNANSWERABLE` token with `{"abstain": true}` as the plan. In a clinical setting a confidently wrong answer is worse than a refusal, so abstention is trained explicitly and scored as its own metric.

### 2.5 Gold generation and execution verification

For each archetype × eligible concept, the generator (`scripts/generate_gold_plan_sql.py` and category variants) instantiates the plan and SQL together from the same parameters, then **executes the SQL against the real database** and keeps the pair only if it runs without error *and* returns at least one row. Empty results are rejected outright: a query returning zero rows would be trivially "matched" by a broken query also returning zero rows, and RL would learn to exploit that.

Each surviving artifact is additionally checked for **repeated-execution stability** (the same query run five times must return identical results) — a guard added after discovering that DuckDB's parallel float aggregation and unpinned `ORDER BY` tiebreaks could make correctness measurement itself nondeterministic (see `METHODOLOGY_LOG.md`).

Verified yields: 2,051/2,346 main clinical + 175/199 operational + 167/189 quality-KPI + 27/31 regulatory, with zero execution errors throughout. Rejections are logged with reasons in `data/training/rejected_gold_plan*.jsonl`.

### 2.6 Natural-language questions

Gold SQL alone is not training data — each artifact needs a question a human would plausibly ask.

A roster of **eleven hospital roles** frames the phrasing: physician, nurse, pharmacist, admission/registration clerk, outpatient clerk, emergency department manager, ICU manager, finance reviewer, hospital CEO, population health analyst, and infection control officer. Roles are **mapped per archetype rather than assigned at random** — a hospital CEO asks trend and aggregate questions, a nurse asks patient-level care questions, a finance reviewer asks volume questions. A tier-1 single-patient lookup is never phrased as a CEO-level strategic question.

The question phrasings themselves were **authored with LLM assistance (Claude) under the author's direction**: 160 role-appropriate questions were composed and reviewed as a first batch, one per archetype × role pairing, specifically to validate that the phrasing read like a real hospital question rather than a SQL statement transliterated into English. Those 160 reviewed sentences were then parameterized — the specific concept name replaced by a `{concept}` placeholder — so the same vetted phrasing instantiates across every concept its archetype applies to (`scripts/question_templates.py`, `scripts/personas.py`). This keeps human-quality phrasing while scaling to thousands of examples, at the cost of template regularity that Section 7 discusses as a limitation.

A `clean_concept()` step strips FHIR-style trailing qualifiers (`(disorder)`, `(finding)`) that are unnatural in speech, collapses double-space artifacts present in some raw Synthea display strings, and handles acronym capitalization so questions read naturally.

Paraphrase quality is checked automatically: a filter verifies the question still references the concept the underlying SQL filters on, catching paraphrases that silently drop a filter. It flags for review rather than deleting, since valid synonyms and abbreviations would otherwise false-positive.

### 2.7 Final datasets

| Split | Rows | Answerable | Abstention |
|---|---:|---:|---:|
| Training (`sft_final_plan.jsonl`) | 10,696 | 9,680 | 1,016 |
| Held-out, familiar arm | 9,300 | 8,284 | 1,016 |
| Held-out, unseen arm | 2,156 | 1,140 | 1,016 |

**The 1,016 abstention rows are the same 1,016 rows in all three splits.** Unanswerable questions reference no patient data, so the factory emits an identical set for every population; they were reused rather than regenerated. Consequently the abstention metrics reported in Section 5 measure *retention of trained refusal behavior* on questions seen verbatim during training — not held-out refusal generalization — and the two arms' abstention figures are not independent measurements of each other. No result outside the abstention metrics is affected.

Training data spans 82 archetypes and **2,420 distinct executable gold SQL statements**, each back-translated into roughly four role-varied paraphrases. Tier distribution: tier 1 (1,332), tier 2 (2,244), tier 3 (3,808), tier 4 (2,296), unanswerable (1,016).

The train/dev/test split is **grouped by underlying SQL instance** (archetype + concept + gold SQL), not by row, so paraphrases of the same query never straddle the split — an ungrouped split would let dev accuracy partly reflect memorized phrasing. A fixed 84/8/8 split is shared across all seeds.

### 2.8 The two held-out arms

The held-out benchmark is built by the same factory against the **disjoint 6,383-patient population**, and deliberately separates two kinds of generalization:

- **Familiar arm** — concepts drawn from the same selection used for training, against entirely unfamiliar patients. Isolates **population generalization**. 382 concepts selected; **338 survive** execution-verification into the realized benchmark.
- **Unseen arm** — concepts that exist in the held-out corpus but appear **nowhere in training**. Isolates **concept generalization**. 87 selected; **84 survive**. All are low-prevalence (1–3 patients each), which restricts this arm to patient-level tier-1/2 archetypes on the three tables with unseen candidates (condition, procedure, medication_request) — population-aggregate shapes cannot be built from so few patients. **Disjointness verified directly**: zero of the 84 realized unseen concepts appear among the 345 concepts realized in training data.

Note that the unseen arm varies *two* things at once relative to training — novel concepts and a restricted archetype mix — which makes it a harder test than concept novelty alone, and means its accuracy should not be read as a pure concept-generalization figure.

**How much of each arm is genuinely new.** The distinction matters for reading Section 5, so it is stated numerically. In the familiar arm, 7,996 of 8,284 answerable rows (**96.5%**) are byte-identical `(question, gold SQL)` pairs from training, and 1,999 of its 2,071 distinct gold queries also appear in training. Only the underlying patient population differs — and because gold SQL contains no patient-specific literals, the *target string* for those rows is unchanged. The familiar arm therefore measures whether learned queries remain correct against new data; it cannot distinguish memorization from generalization. The unseen arm, by contrast, shares **zero** `(question, gold SQL)` pairs with training (0 of 1,140) and zero concepts, and is the arm on which any generalization claim rests.

Two further imperfections. First, 7 of the familiar arm's 338 concepts (160 answerable rows, 1.9%) were selected for training but their train-side instantiations failed verification, so they do not actually appear in training data; since the familiar arm scores 100%, all were answered correctly and the contamination runs in the conservative direction. Second, the unseen arm's 9 answerable archetypes are all archetypes that appear in training — the arm varies the *concept* and restricts the archetype *mix*, but introduces no query shape the model has not seen.

## 3. Method

### 3.1 Supervised fine-tuning

DoRA (Weight-Decomposed Low-Rank Adaptation) on `Qwen/Qwen2.5-Coder-14B-Instruct`, NF4 4-bit quantized (QLoRA): rank 16, alpha 32, dropout 0.05, all linear projection layers (`q/k/v/o_proj`, `gate/up/down_proj`), bias frozen. Learning rate 2e-4, no weight decay, 3% warmup, `max_seq_len` 4096, micro-batch 8, two epochs, three seeds (42, 43, 44).

One procedural irregularity: seed 42 was launched under an earlier configuration allowing up to 3 epochs, gated by a rule that attempts a third epoch only if the second improved dev loss by ≥5%. That rule fired (epoch 2 improved 78%), a third epoch began, but it was abandoned before completing and never recorded. The configuration was then fixed at 2 epochs for seeds 43/44, which is what the shipped notebook contains. **Every published checkpoint is an epoch-2 checkpoint selected by dev loss**, so all three seeds are comparable — but seeds did not differ *only* in initialization and batch order. Logs: `results/sft_outputs/seed_*/train.log`.

### 3.2 Reinforcement learning

Each seed's best SFT checkpoint is continued with DAPO (Yu et al., 2025), a GRPO-family (Shao et al., 2024) critic-free method where advantage is the within-group reward z-score across `group_size=4` completions per prompt. Three of DAPO's four techniques are used: **Clip-Higher** (`eps_low=0.20`/`eps_high=0.28`), **Dynamic Sampling** (zero-reward-variance groups carry no signal and are dropped, resampling until 8 usable groups accumulate), and **token-level loss normalization**. Overlong Reward Shaping is omitted — it targets runaway-length chain-of-thought, which does not apply to length-capped SQL. Learning rate 1e-5, 200-step budget, evaluated every 10 steps, early stopping after 3 checks without improvement.

Reward is computed **only on the final SQL** extracted from the completion's fenced block; the plan is never separately scored. Correctness is a strict gate and efficiency only ever adds a bonus on top of a correct answer, so a faster wrong query can never outscore a correct one (asserted in code):

| Outcome | Reward |
|---|---:|
| Correct result | 1.0 + up to 0.1 efficiency bonus |
| SQL executes, wrong result | 0.0 |
| SQL doesn't execute | −0.2 |
| Correct result, but terminology hardcoded | −0.2 |
| Abstained on an answerable question | −0.1 |
| Answered a genuinely unanswerable question | −0.3 |

Wrong answers are **tiered rather than flat** so a group failing in different ways carries real variance for Dynamic Sampling to exploit. Confidently answering an unanswerable question is the worst tier, reflecting clinical-safety asymmetry.

### 3.3 Preventing terminology memorization

The database-resolved design (Section 1.3) removes the *incentive* to memorize codes, but not the *possibility*: a model could still embed a literal code (`WHERE code = '271737000'`) and produce a correct, executing query. Under an execution-correctness-only reward this is invisible, yet it bypasses the capability the design exists to build and would not transfer.

`has_hardcoded_terminology()` flags any of `code`/`system`/`type_code`/`type_system`/`vaccineCode`/`vaccineCode_system` compared against a quoted literal. This is **sound by construction**: every legitimate lookup CTE filters exclusively on `table_name` and `display`, and joins compare these columns to *identifiers* (`resolved.code`), never literals. A match can therefore only mean the lookup was bypassed. Validated against all 9,680 gold-SQL-bearing rows (2,420 distinct statements) with zero false positives, and confirmed to ignore legitimate non-terminology literals such as `class_code = 'IMP'` or `clinicalStatus = 'active'`.

A correct-but-hardcoded completion scores `−0.2` instead of the correct-answer tier and forfeits the efficiency bonus. The same detector is reported as a diagnostic metric (`gen_hardcoded_rate`) at evaluation time.

## 4. Experimental setup

**Hardware.** All training and evaluation ran on Google Colab with a G4 GPU instance (96 GB RAM). SFT took ≈5.9 hours per epoch per seed (≈11.7 h/seed); RL steps took a median of 7.3 minutes (440 s); typical non-evaluation steps ran 344–455 s, with dynamic-sampling resampling pushing a minority as high as ~2,900 s.

**Evaluation scope.** Two metric classes with different coverage:

- **Teacher-forced metrics** (`val_loss`, `val_perplexity`, `val_token_acc`) — computed over the **complete** arm: all 9,300 familiar and all 2,156 unseen rows.
- **Generation metrics** (`gen_*`) — require autoregressive decoding, computed over a fixed random sample capped at 3,000 rows per arm (`heldout_eval_gen_sample_size=3000`, drawn once with a fixed seed so every model state is scored on identical rows). This covers the **unseen arm in full** (2,156 rows: 1,140 answerable + 1,016 abstention) and samples the familiar arm at **3,000 of 9,300** (2,682 answerable + 318 abstention).

**Metrics.**

| Metric | What it measures |
|---|---|
| `val_loss`, `val_perplexity`, `val_token_acc` | teacher-forced fit to the gold completion |
| `gen_exec_match` | **primary correctness**: does the generated SQL execute to the same result set as gold (order-insensitive, float-tolerant) |
| | *denominator note:* exec-match is computed over answerable questions the model actually attempted — rows it falsely refused are counted against abstention recall instead. The text-match metrics below divide by all answerable rows, so the two are not row-for-row comparable. This affects only the frozen baseline (fine-tuned models never falsely refuse): counted over all answerable rows, frozen familiar exec-match is 9.8% rather than 10.2%. |
| `gen_exact_match` | literal text identity with gold SQL |
| `gen_structure_match` | text identity after whitespace collapse and masking of `code`/`system` literal values |
| `gen_abstention_precision` / `recall` | correctly declining unanswerable questions |
| `gen_hardcoded_rate` | fraction of correct completions that bypassed the lookup |
| `gen_efficiency_speedup` | median gold-time / predicted-time among correct completions, measured cache-fair |

**Which metric is primary.** `gen_exec_match` — it measures whether the query returns the right answer. `gen_exact_match` and `gen_structure_match` are strict text-similarity diagnostics, reported for completeness; both are *stricter* than execution correctness and can penalize a semantically correct query for phrasing a search term differently than gold. `gen_structure_match`'s code-literal masking was designed for a data regime where gold SQL embedded literal codes and one needed to avoid conflating SQL skill with code recall; under this study's lookup design that confound does not exist — there are no code literals to mask — so the masking is inert and the metric collapses to near-exact text match (identical to `gen_exact_match` on the familiar arm, within 0.7 pp on the unseen arm). It is retained for transparency, not relied upon.

## 5. Results

### 5.1 Held-out benchmark, complete metric suite

Frozen baseline is deterministic under greedy decoding and computed once. SFT and RL columns are means across seeds 42/43/44, per-seed ranges in brackets. Per-seed files: `results/heldout_eval/*.json`.

**Familiar arm** (population generalization — trained concepts, unfamiliar patients):

| Metric | Frozen | SFT (mean) | SFT range | RL (mean) | RL range |
|---|---:|---:|---|---:|---|
| `val_loss` | 0.8787 | 0.0001 | [0.0000–0.0001] | 0.0001 | [0.0000–0.0001] |
| `val_perplexity` | 2.4077 | 1.0001 | [1.0000–1.0001] | 1.0001 | [1.0000–1.0001] |
| `val_token_acc` | 0.8141 | 1.0000 | [1.0000–1.0000] | 1.0000 | [1.0000–1.0000] |
| **`gen_exec_match`** | **0.1020** | **1.0000** | [1.0000–1.0000] | **1.0000** | [1.0000–1.0000] |
| `gen_exact_match` | 0.0000 | 0.9960 | [0.9952–0.9970] | 0.9959 | [0.9948–0.9970] |
| `gen_structure_match` | 0.0000 | 0.9960 | [0.9952–0.9970] | 0.9959 | [0.9948–0.9970] |
| `gen_abstention_precision` | 0.7134 | 1.0000 | [1.0000–1.0000] | 1.0000 | [1.0000–1.0000] |
| `gen_abstention_recall` | 0.7358 | 1.0000 | [1.0000–1.0000] | 1.0000 | [1.0000–1.0000] |
| `gen_efficiency_speedup` | 1.6902 | 1.0009 | [1.0003–1.0017] | 1.0001 | [0.9986–1.0011] |
| `gen_hardcoded_rate` | 0.0303 | 0.0000 | [0.0000–0.0000] | 0.0000 | [0.0000–0.0000] |

**Unseen arm** (concept generalization — clinical concepts absent from all training data):

| Metric | Frozen | SFT (mean) | SFT range | RL (mean) | RL range |
|---|---:|---:|---|---:|---|
| `val_loss` | 0.6280 | 0.0028 | [0.0024–0.0031] | 0.0028 | [0.0024–0.0031] |
| `val_perplexity` | 1.8739 | 1.0028 | [1.0024–1.0031] | 1.0028 | [1.0024–1.0031] |
| `val_token_acc` | 0.8180 | 0.9992 | [0.9989–0.9993] | 0.9992 | [0.9990–0.9993] |
| **`gen_exec_match`** | **0.3129** | **0.8912** | [0.8500–0.9211] | **0.8915** | [0.8509–0.9211] |
| `gen_exact_match` | 0.0000 | 0.8137 | [0.7667–0.8579] | 0.8149 | [0.7667–0.8605] |
| `gen_structure_match` | 0.0000 | 0.8208 | [0.7737–0.8649] | 0.8219 | [0.7737–0.8675] |
| `gen_abstention_precision` | 0.9629 | 1.0000 | [1.0000–1.0000] | 1.0000 | [1.0000–1.0000] |
| `gen_abstention_recall` | 0.7156 | 1.0000 | [1.0000–1.0000] | 1.0000 | [1.0000–1.0000] |
| `gen_efficiency_speedup` | 2.3169 | 1.0011 | [0.9985–1.0035] | 1.0034 | [1.0024–1.0047] |
| `gen_hardcoded_rate` | 0.0345 | 0.0000 | [0.0000–0.0000] | 0.0000 | [0.0000–0.0000] |

**Reading these numbers.** The frozen column is measured under the identical prompt the fine-tuned models saw — a like-for-like prompt comparison, but one that understates the frozen model, because that prompt omitted the DDL for the `valuesets` terminology table. Section 5.6 quantifies the effect: given the table description, frozen execution match rises to 34.8% (familiar) and 60.8% (unseen). **The fair reading of what fine-tuning contributed is therefore 34.8% → 100.0% on familiar concepts and 60.8% → 89.1% on unseen ones**, and that is the comparison to cite. Two provenance caveats on that pairing: the with-DDL frozen figures come from the 750-row ablation sample rather than this table's full-arm evaluation, and within the ablation's own paired sample the without-DDL frozen scores are 8.7% and 31.2% (tracking this table's 10.2% and 31.3% within sampling noise). The fine-tuned side of the comparison is unchanged either way, since fine-tuned models gain nothing from the DDL (Section 5.6).

What does *not* change with the extra schema information is more telling than what does. The frozen model never produces a query matching gold text under either prompt (0.0% exact match throughout); its refusal behavior stays unreliable in both directions, failing to refuse 26.4% of unanswerable familiar questions and 28.4% of unseen ones while falsely abstaining on 3.5% and 2.5% of *answerable* ones; and Section 5.6 shows its correct queries run 4.5–12× slower than gold. It can sometimes reach the right answer; it is not a dependable analyst.

After fine-tuning, familiar-arm execution correctness is perfect on all three seeds and teacher-forced token accuracy is 1.0000: the model reproduces gold completions essentially exactly on trained clinical vocabulary, against patients it has never seen. The unseen arm reaches 89.1% — a real gap, but a demonstration that the design does what it was built for: the model composes correct terminology-resolution queries for clinical concepts it was never trained on. That number is only meaningful *because* gold SQL contains no memorizable codes, and it should be read as the upper end of a range: Section 6 shows execution match is weakly discriminative on this arm, with the text-match metrics putting the lower end at 81.4%.

Refusal is perfect on both arms, every seed — but see Section 2.7: the abstention rows are reused verbatim from training, so this measures retention of trained refusal behavior, not held-out refusal. `gen_efficiency_speedup` near 1.0 means fine-tuned queries run at essentially gold speed; the frozen model's higher apparent speedup is an artifact of being computed only over its rare correct completions, which skew simple.

### 5.2 No overfitting: three independent lines of evidence

Given a 100% result, the first question a reader should ask is whether the model memorized the corpus. Three separate observations say it did not.

**(a) Training and validation loss fall together.** Validation loss never rises while training loss drops by two orders of magnitude:

| Seed | Train loss (ep1 → ep2) | Val loss (ep1 → ep2) | Val token acc (ep2) |
|---|---|---|---:|
| 42 | 0.0160 → 0.00019 | 0.00157 → 0.00034 | 0.9999 |
| 43 | 0.0144 → 0.00008 | 0.00057 → 0.00037 | 0.9999 |
| 44 | 0.0143 → 0.00005 | 0.00037 → 0.00024 | 1.0000 |

The classic overfitting signature — training loss falling while validation loss turns upward — is absent in all three seeds.

**(b) Learned queries stay correct against a new patient population.** The in-corpus test split (same patient population, held out during training, grouped so no paraphrase leaks) and the familiar held-out arm (**entirely different patients**) both score 100% execution match. Note precisely what this does and does not show: 96.5% of familiar-arm rows are verbatim training pairs (Section 2.8), so a purely memorizing model would also score 100% here — this line of evidence establishes that the learned query mapping is not patient-specific and does not degrade on new data, which is necessary but not sufficient for generalization. The weight of the no-overfitting argument is carried by (c).

| | Frozen | SFT (mean) | RL (mean) |
|---|---:|---:|---:|
| `val_loss` | 0.8799 | 0.0002 | 0.0002 |
| `val_token_acc` | 0.8148 | 0.9999 | 0.9999 |
| `gen_exec_match` | 0.1600 | 1.0000 | 0.9970 |
| `gen_exact_match` | 0.0000 | 1.0000 | 0.9848 |
| `gen_abstention_precision` | 0.4444 | 1.0000 | 0.9710 |
| `gen_abstention_recall` | 0.8000 | 1.0000 | 1.0000 |

(Frozen and SFT columns come from `sft_train.ipynb`'s 60-row test sample, RL from `rl_train.ipynb`'s 240-row sample; the SFT and RL columns are therefore **not** computed on the same rows, and small differences between them are not meaningful. Both stages sit at or within one or two rows of ceiling, and neither can be separated from the other in-corpus.)

Moving from patients the model trained on to a disjoint 6,383-patient population costs **nothing**. A memorizing model would degrade here; this one does not.

**(c) The model transfers to clinical concepts it never saw.** This is the load-bearing evidence. On the unseen arm every clinical concept is novel — verified by set intersection over primary and companion entities, question text, and gold SQL — and **no** `(question, gold SQL)` pair is shared with training (0 of 1,140). The model executes correctly 89.1% of the time there, with teacher-forced token accuracy 0.9992 and validation loss 0.0028 on data built from vocabulary it has no exposure to. Memorization of training targets cannot produce that.

Two honest bounds on how much this shows. The unseen arm's archetypes are all trained archetypes, so what transfers is concept identification, domain/table assignment, and lookup composition — not novel query composition. And its 89.1% is an upper bound for the reasons in Section 6; the text-match metrics bound the same quantity from below at 81.4%.

Taken together — no loss divergence, learned queries holding on a new population, and 81–89% correctness on genuinely novel clinical concepts — the results reflect a learned mapping from clinical question to query structure rather than corpus recall. All three lines share one question-generation distribution (Section 7).

### 5.3 Why RL adds nothing

The RL result is not a marginal null — the stage had almost no room to operate.

| Seed | Steps run (budget 200) | Best dev exec-match | Reached at | Mean reward (mean / min / max) | Steps with reward ≥ 1.0 | Groups kept (mean) |
|---|---:|---:|---:|---|---:|---:|
| 42 | 40 | 1.000 | step 10 | 1.0035 / 0.9772 / 1.0088 | 38/40 | 87.1% |
| 43 | 40 | 0.995 | step 10 | 1.0016 / 0.9404 / 1.0130 | 37/40 | 86.7% |
| 44 | 40 | 1.000 | step 10 | 1.0033 / 0.9756 / 1.0090 | 38/40 | 88.2% |

All three seeds peaked at the **first** evaluation checkpoint and never improved, early-stopping at step 40 — one fifth of the budget. Dev exec-match never rose after step 10 in any seed; seeds 43 and 44 held flat across all four checkpoints, and seed 42 slipped from 1.000 to 0.991 and stayed there.

Mean reward (over retained groups) sat at or above 1.0 — the correct-answer floor — on 37–38 of 40 steps, meaning sampled completions were already overwhelmingly correct before any update. With the correctness tier this close to saturation, the reward differences Dynamic Sampling retained (it still kept ~87% of groups) must have come largely from the small efficiency bonus, derived from wall-clock timing. This is an inference from reward statistics, not a direct measurement: the committed histories log per-step mean reward but do not decompose within-group variance, and the few steps below 1.0 confirm some retained variance came from genuinely wrong completions. Establishing the mechanism conclusively would require logging per-group reward components, which this run did not do.

The practical conclusion is scoped, not general: **when SFT already saturates the reward's correctness gate, a GRPO/DAPO stage on the same objective has nothing left to optimize.** Extracting value from RL here would need a reward with headroom above SFT's ceiling — a harder task distribution, or a correctness criterion SFT does not already satisfy.

### 5.4 Terminology hardcoding

The frozen model bypasses the lookup in 3.0% (familiar) and 3.4% (unseen) of its rare correct-looking completions. **Every fine-tuned model — both stages, three seeds, both arms, and the in-corpus test split — hardcodes in exactly 0.0% of completions.**

Read precisely: the 0.0% rate is achieved by SFT alone, before the RL penalty is ever applied. Gold SFT data is uniformly lookup-based and supervised learning reproduces that pattern, so the penalty was never needed to correct an observed tendency. What the result establishes is that (a) the behavior holds on genuinely unseen concepts, where a memorized code would have been the tempting shortcut, and (b) the detector, validated on gold data, produces no false positives on real model output either.

### 5.5 Efficiency

`gen_efficiency_speedup` sits within ±0.5% of 1.0 for every fine-tuned state on both arms — fine-tuned queries execute at gold speed. Since the reward's efficiency term only ever operated on already-correct answers and correctness was saturated (Section 5.3), this run provides no evidence about whether that term can shape behavior when there is headroom.

### 5.6 Ablation: how much of the frozen baseline's failure was a missing `valuesets` DDL?

During the published runs, `schema/schema.sql` did **not** contain a `CREATE TABLE valuesets` block. The table existed in both databases and every gold query resolved through it, but the model was never shown its columns. Fine-tuned models learned the table's shape from thousands of training targets; the frozen baseline had only the table name. That asymmetry could inflate the apparent contribution of fine-tuning, so it was measured directly.

`valuesets_ablation.ipynb` re-runs the held-out generation evaluation on the frozen model twice — once with the exact published DDL, once with `schema/valuesets_ddl.sql` prepended — holding the evaluation sample, metric code, database, and in-memory model fixed. The ablation is frozen-first by design: the frozen model is seed-independent (no adapter, greedy decoding), and the fine-tuned states have no open question and no familiar-arm headroom. One fine-tuned checkpoint (SFT seed 42) was included as a control. Sample: 750 rows per arm per condition, paired.

**Frozen baseline** (same 750 rows in both conditions):

| Metric | Arm | without DDL | with DDL | Δ |
|---|---|---:|---:|---:|
| `gen_exec_match` | familiar | 0.0866 | **0.3484** | **+0.2618** (4.0×) |
| `gen_exec_match` | unseen | 0.3115 | **0.6078** | **+0.2963** (1.95×) |
| `gen_exact_match` | familiar | 0.0000 | 0.0000 | 0.0000 |
| `gen_exact_match` | unseen | 0.0000 | 0.0000 | 0.0000 |
| `gen_abstention_precision` | familiar | 0.6447 | 0.6812 | +0.0364 |
| `gen_abstention_recall` | familiar | 0.7538 | 0.7231 | −0.0308 |
| `gen_abstention_precision` | unseen | 0.9556 | 0.9654 | +0.0098 |
| `gen_abstention_recall` | unseen | 0.7247 | 0.7051 | −0.0197 |
| `gen_hardcoded_rate` | familiar | 0.0175 | **0.0000** | −0.0175 |
| `gen_hardcoded_rate` | unseen | 0.0420 | **0.0000** | −0.0420 |
| `gen_efficiency_speedup` | familiar | 1.5918 | 0.2197 | −1.3721 |
| `gen_efficiency_speedup` | unseen | 2.3277 | 0.0841 | −2.2437 |

**SFT seed 42 control** (unseen arm): execution match 0.8503 → 0.8579 (**+0.0076**), exact match 0.7690 → 0.7817, abstention and hardcoding unchanged. The familiar-arm `with` leg was not completed; the `without` leg is already at ceiling (1.0000), leaving no headroom for the DDL to add.

**Harness validity.** The `without` legs track the published frozen evaluation closely despite the smaller sample — unseen execution match 0.3115 versus published 0.3129, a 0.14 pp difference; familiar 0.0866 versus 0.1020, within sampling noise at n=750. No systematic divergence, so the paired contrast is trustworthy.

**Four findings.**

1. **The frozen baseline was substantially handicapped.** Showing it the lookup table's columns quadruples familiar-arm execution match and roughly doubles unseen-arm. The published frozen figures remain a valid same-prompt comparison but are a poor estimate of the model's underlying capability; Section 5.1's fair reading (34.8% → 100.0%, 60.8% → 89.1%) is what fine-tuning actually contributed.

2. **Fine-tuned models had already internalized the table.** A +0.8 pp change on the unseen arm — well inside seed-to-seed variation — confirms they learned the schema implicitly from training targets and gain nothing from being told explicitly.

3. **Making the lookup discoverable appears to eliminate hardcoding with no reward pressure at all.** The frozen model's terminology-hardcoding rate falls to 0.0% on both arms once it can see the table's columns (familiar 1/57 correct completions → 0/261; unseen 5/119 → 0/456). The event counts are small, so the familiar-arm contrast alone is not significant; the pooled contrast and the larger same-prompt figures from the published evaluation (8/264 familiar, 12/348 unseen, Section 5.4) support the same direction. This is consistent with the model embedding literal codes because the lookup route was undiscoverable rather than dispreferred — support for the design thesis of Section 1.3, obtained from a model that received no training signal whatsoever, though from a modest number of events.

4. **Access is not competence.** Even with full schema information the frozen model never once reproduces a gold query (0.0% exact match), its refusal behavior barely moves and its recall slightly worsens, and its correct queries run 4.5–12× slower than gold. The efficiency collapse from 1.59×/2.33× to 0.22×/0.08× indicates it is now attempting terminology lookups but composing them badly. It reaches right answers more often without becoming a system anyone would deploy.

Because these results settle the question, `schema/schema.sql` is deliberately left in its published state and `valuesets_ddl.sql` remains a separate fragment, so the contrast stays reproducible. Raw per-leg results: `results/valuesets_ablation/`.

## 6. Error analysis: the unseen-concept gap

The unseen arm's 89.1% leaves a 10.9-point gap below the familiar arm. Across all six fine-tuned runs (3 seeds × 2 stages, 1,140 answerable rows each) there are 743 execution failures; the familiar arm produced **zero** in any run. Categorizing all 743 by comparing the `ILIKE` search term in the predicted lookup CTE against gold's (reproducible via `scripts/analyze_unseen_failures.py`):

| Failure category | Count | Share |
|---|---:|---:|
| Added a qualifier suffix not present in gold | 580 | 78.1% |
| Substantively different search phrase | 113 | 15.2% |
| Wrong qualifier suffix | 28 | 3.8% |
| Same search term, other SQL difference | 18 | 2.4% |
| Missing a qualifier suffix present in gold | 2 | 0.3% |
| Same base phrase, other minor difference | 2 | 0.3% |

**78.1% of failures are one benign pattern.** SNOMED CT display text conventionally carries a parenthetical semantic tag — `(disorder)`, `(finding)`, `(procedure)`, `(situation)`. The model learned this from training data, where SNOMED concepts dominate, and over-applies it to concepts coded in systems that don't use it. Verified against `valuesets` contents in the held-out database: "Chronic sialoadenitis" is ICD-10 `K11.23` with no parenthetical tag; several CDT dental codes such as `D2663` contain literal double-spaces no convention would predict. Because the lookup uses `ILIKE '%…%'` containment, a suffix the stored text doesn't contain matches nothing, so the query returns empty rather than wrong.

This is a **data-formatting mismatch, not a reasoning failure**: the model identified the right concept, chose the right table, and built a structurally correct lookup — it guessed the wrong surface form of a display string it had never seen. It is also directly fixable (normalizing display text, or matching on a suffix-stripped column) without retraining, which suggests the ceiling here is meaningfully above 89%.

Only the 15.2% "substantively different search phrase" category represents genuine concept-identification error.

**Caveat on the text metrics.** On `gen_structure_match`, unseen mismatches total 1,222 rather than 743 — the extra 479 rows execute to the *correct result* while differing from gold's SQL text (typically an equivalent search phrase matching the same `valuesets` rows). Those are correct under the primary metric and are not errors, but they explain why text-similarity metrics sit below execution correctness. Measured against structure mismatches instead, the SNOMED-suffix pattern accounts for 47.5% rather than 78.1%.

**How discriminative is execution match on this arm?** Less than one would like, and this bounds the headline number. Unseen concepts are deliberately rare (1–3 patients each), so their gold answers are small: of the 285 distinct unseen gold queries, 265 return a single row, and the most common answers are the integers 1 (94 queries), 0 (56) and 2 (16). A prediction that resolves the *wrong* unseen concept can therefore return gold's exact result by coincidence. Executing every gold query and comparing concepts pairwise within each archetype (`scripts/analyze_unseen_discriminativeness.py`) quantifies it: **3,594 of 6,662 within-archetype concept pairs (53.9%) return identical gold answers.** The risk is concentrated in the three condition-count archetypes — `t2_active_condition_count` 93.0%, `t1_count_patients_with_condition` 72.0%, `t2_resolved_condition_count` 66.2% — and is negligible for the list- and year-grouped shapes (0–2.2%), whose result sets carry far more information.

The consequence is a bracket rather than a point estimate. `gen_exec_match` (89.1%) is an **upper bound** on true concept-resolution accuracy, since some correct-scoring rows may be coincidental agreement. `gen_exact_match` (81.4%) and `gen_structure_match` (82.1%) compare query text and cannot be satisfied by a collision, so they are **lower bounds** — conservative, because they also penalize genuinely equivalent phrasings. True unseen-arm performance lies between roughly **81% and 89%**. Distinguishing the two would require re-running evaluation with predicted lookup phrases logged for correct rows, which this run did not record.

## 7. Limitations

- **Synthetic data only.** One Synthea corpus. Its terminology distribution, code density, and clinical realism differ from real EHR data in ways that could change both difficulty and failure modes.
- **Abstention results are retention, not generalization.** The 1,016 unanswerable questions are identical across training and both held-out arms (Section 2.7), so 100% precision and recall measures reproduction of trained refusals on verbatim-seen questions. Refusal of *novel* unanswerable categories is untested, and the 18 refusal archetypes occupy topic domains disjoint from the answerable questions, so the task may be solvable by topic recognition alone. Note also that several "unanswerable" categories are unanswerable relative to the curated 11-table schema, not to Synthea's full output — the corresponding data exists in auxiliary tables that were never promoted.
- **The familiar arm cannot detect memorization** (Section 2.8): 96.5% of its rows are verbatim training pairs, so a memorizing model would also score 100%. Only the unseen arm speaks to generalization.
- **Execution match is weakly discriminative on the unseen arm** (Section 6): 53.9% of within-archetype concept pairs share gold answers, so 89.1% is an upper bound and 81.4% a lower bound on true performance.
- **One question distribution.** All training and evaluation questions derive from the same 160 reviewed phrasings, parameterized by concept and role. The results demonstrate generalization to new patients and new clinical concepts *within* that phrasing distribution; robustness to unconstrained clinician phrasing, typos, ambiguity, or multi-turn clarification is untested, and template regularity is the most likely reason the familiar arm reaches exactly 100%.
- **The familiar arm has no headroom.** At 100% execution match and 1.0000 token accuracy, it cannot discriminate between two good models. Only the unseen arm carries that signal, and only 84 concepts back it.
- **The unseen arm confounds two variables.** Novel concepts *and* a restricted archetype mix (tier-1/2, three tables). Its 89.1% is not a pure concept-generalization figure.
- **One model, one scale, one schema.** `Qwen2.5-Coder-14B-Instruct` at 14B, 4-bit, against one flattened schema. Scaling and transfer are untested.
- **Execution match is database-instance-specific.** Two queries can agree on this corpus without being semantically equivalent in general — a predicted `ILIKE` phrase broader than gold's may match extra `valuesets` rows that happen to return the same result. The 479 correct-but-textually-different rows in Section 6 were not individually audited for this.
- **The frozen baseline's headline numbers understate it.** The published prompt omitted the `valuesets` DDL; given it, frozen execution match rises to 34.8%/60.8% (Section 5.6). The fair fine-tuning contribution is 34.8% → 100.0% and 60.8% → 89.1%, not the larger same-prompt deltas. The ablation used a 750-row sample per arm and a single fine-tuned control seed, with one control leg (SFT familiar, `with`) not completed.
- **RL scope.** The null result applies to this reward, this task, at this SFT ceiling — it is evidence about a saturated objective, not about GRPO/DAPO generally. The efficiency reward term was never meaningfully exercised.
- **Seed 42's SFT configuration differed** (Section 3.1). All published checkpoints are epoch-2 and comparable, but exact reproduction of seed 42's launch state is not possible from the committed notebook alone.
- **Terminology resolution here is substring matching, not value-set expansion.** Concepts resolve by `display ILIKE '%…%'` against a corpus-derived dictionary with one display string per code, and concepts whose text matches more than one row are *excluded from gold* (Section 1.3) — so the benchmark omits synonymy, hierarchical subsumption, and genuine ambiguity, which is most of what clinical terminology work involves in practice. The table is named `valuesets` for historical reasons but is a code dictionary, not a FHIR ValueSet resource. Section 8's extrapolation to large controlled vocabularies should be read with this gap in mind.
- **Some regulatory questions say "dispensed" but are answered from prescription orders.** `MedicationRequest` records orders, not dispensing or administration events; Synthea's administration data was not promoted into the benchmark schema. The affected archetypes' gold SQL counts prescriptions, so the phrasing overstates what the answer represents.
- **Role phrasing occasionally implies a cohort restriction the gold SQL ignores.** Templates such as "how many of *my* patients…" read as panel-restricted, while gold SQL counts the whole population; the model learns the population-wide reading.
- **The `valuesets` ablation was run at a reduced sample** (750 rows/arm rather than the 3,000 used for the main evaluation), which forfeits the exact-reproduction check the notebook was designed to support, and one control leg (SFT, familiar arm, with-DDL) was not completed.

## 8. Conclusion and outlook

A general-purpose coder model that cannot usefully query a FHIR-derived database — roughly a third of answers correct on familiar concepts and three-fifths on unseen ones even when handed the full schema, zero exact matches, unreliable refusal, and queries 4.5–12× slower than gold — becomes a dependable analyst over it after a single supervised fine-tuning pass: 100% on familiar clinical concepts against an unseen patient population, 81–89% on concepts it was never trained on, reliable abstention on trained refusal categories, and no measurable overfitting. The reinforcement-learning stage proves unnecessary, and the training dynamics show why: SFT already saturates the correctness objective.

Two design decisions carry that result. Making the model emit an explicit query plan — clinical entities, query archetype, aggregation — before the SQL turns latent reasoning into an inspectable artifact. Resolving clinical terminology through a database lookup rather than model memory converts an unverifiable recall problem into a checkable composition problem, and is what makes generalization to unseen clinical vocabulary both possible and measurable. The ablation in Section 5.6 sharpens that second point in a way the main results could not: simply making the lookup table visible in the schema drove the *untrained* model's terminology-hardcoding to zero. Models bypass a resolution mechanism they cannot see — the fix is as much schema design as it is training.

**The wider point is about where fine-tuning pays.** Frontier general-purpose models are strong at common, well-represented tasks and weak at narrow, idiosyncratic, standards-heavy ones — precisely the systems that dominate real enterprise and clinical data work: normalized schemas nobody outside the organization has seen, controlled vocabularies with millions of codes, domain conventions that never appear in pretraining corpora. This study is one instance of a repeatable recipe for that setting: express the domain's structure in the schema so it can be *queried* rather than recalled; generate training data by execution-verified construction rather than annotation; make the model's intermediate reasoning an explicit, checkable artifact; and train abstention as a first-class behavior so the system declines rather than fabricates. Applied here, that recipe turned a 14B open-weight model into a subject-matter analyst for FHIR-over-DuckDB at a cost of roughly a day of single-GPU compute.

Nothing about the recipe is specific to FHIR. Any domain with a normalized schema, a controlled vocabulary, and a supply of verifiable queries — claims and billing, laboratory information systems, regulatory reporting, industrial telemetry, financial reference data — presents the same structure. The most promising extension is not a larger model but a harder benchmark: real clinician phrasing, deeper compositional queries, and a correctness criterion with genuine headroom left above the supervised ceiling, which is where a reinforcement-learning stage might finally earn its cost.

## Reproducing

Everything needed is committed: corpus generation and verification scripts (`scripts/`), the frozen schema (`schema/schema.sql`), assembled datasets (`data/training/`), both training notebooks configured exactly as run, the `valuesets` ablation notebook, and all per-seed training logs, evaluation summaries, and failure logs (`results/`). Adapter weights are on Hugging Face (`MODEL_CARD.md`). `METHODOLOGY_LOG.md` records the dated development history, including bugs found and fixed — notably floating-point non-determinism in DuckDB's parallel `AVG()` aggregation and non-deterministic `ORDER BY` tiebreaks, both of which silently corrupted correctness measurement until traced and eliminated.

## Data and code availability

- **Code, paper, and results:** https://github.com/adelelsayed/fhirsql-reasoning-sql
- **Archived release (DOI):** [10.5281/zenodo.22194576](https://doi.org/10.5281/zenodo.22194576) (concept DOI [10.5281/zenodo.22194575](https://doi.org/10.5281/zenodo.22194575) resolves to the latest version)
- **Fine-tuned adapters:** https://huggingface.co/adelelsayed1991/fhirsql-reasoning-sql-adapters
- **Datasets:** https://huggingface.co/datasets/adelelsayed1991/fhirsql-reasoning-sql

All data is synthetic (Synthea); no real patient data was used at any stage.

## Acknowledgments

The research design, pipeline architecture, and all experimental and interpretive decisions are the author's. Core components — including the trainer structure and checkpoint/resume pattern, the `FHIRSQLLLM` model-wrapper design, the evaluation and reward architecture, the two-arm benchmark design, and the corpus and schema design — were specified by the author and, in several cases, written by the author directly. Claude Code (Anthropic) was used as an implementation assistant under the author's direction: filling in parts of the pipeline to the author's specification, drafting the 160 seed question phrasings (reviewed by the author), assisting with data analysis, and helping draft this paper. All results, interpretations, and conclusions are the author's own.

## References

Full reference list, including data standards and terminology systems: `CITATIONS.md`.

- Yu T, Zhang R, Yang K, et al. Spider: A Large-Scale Human-Labeled Dataset for Complex and Cross-Domain Semantic Parsing and Text-to-SQL Task. EMNLP 2018. arXiv:1809.08887.
- Li J, Hui B, Qu G, et al. Can LLM Already Serve as A Database Interface? (BIRD). NeurIPS 2023 D&B. arXiv:2305.03111.
- Guo J, Zhan Z, Gao Y, et al. Towards Complex Text-to-SQL … with Intermediate Representation (IRNet). ACL 2019. arXiv:1905.08205.
- Wang B, Shin R, Liu X, Polozov O, Richardson M. RAT-SQL. ACL 2020. arXiv:1911.04942.
- Gan Y, Chen X, Xie J, et al. Natural SQL. Findings of EMNLP 2021. arXiv:2109.05153.
- Pourreza M, Rafiei D. DIN-SQL. NeurIPS 2023. arXiv:2304.11015.
- Gao D, Wang H, Li Y, et al. DAIL-SQL. VLDB 2024. arXiv:2308.15363.
- Scholak T, Schucher N, Bahdanau D. PICARD. EMNLP 2021. arXiv:2109.05093.
- Zhong V, Xiong C, Socher R. Seq2SQL. arXiv:1709.00103, 2017.
- Wang P, Shi T, Reddy CK. Text-to-SQL Generation for Question Answering on Electronic Medical Records (MIMICSQL/TREQS). WWW 2020. arXiv:1908.01839.
- Lee G, Hwang H, Bae S, et al. EHRSQL: A Practical Text-to-SQL Benchmark for Electronic Health Records. NeurIPS 2022 D&B.
- Lee G, Kweon S, Bae S, Choi E. TrustSQL: Benchmarking Text-to-SQL Reliability with Penalty-Based Scoring. arXiv:2403.15879, 2024.
- Yuan C, Ryan PB, Ta C, et al. Criteria2Query. JAMIA 2019. DOI: 10.1093/jamia/ocy178.
- Hui B, Yang J, Cui Z, et al. Qwen2.5-Coder Technical Report. arXiv:2409.12186, 2024.
- Liu SY, Wang CY, Yin H, Molchanov P, Wang YCF, Cheng KT, Chen MH. DoRA: Weight-Decomposed Low-Rank Adaptation. ICML 2024. arXiv:2402.09353.
- Dettmers T, Pagnoni A, Holtzman A, Zettlemoyer L. QLoRA: Efficient Finetuning of Quantized LLMs. NeurIPS 2023. arXiv:2305.14314.
- Yu Q, Zhang Z, Zhu R, et al. DAPO: An Open-Source LLM Reinforcement Learning System at Scale. arXiv:2503.14476, 2025.
- Shao Z, Wang P, Zhu Q, et al. DeepSeekMath: Pushing the Limits of Mathematical Reasoning in Open Language Models. arXiv:2402.03300, 2024. (Origin of GRPO.)
- Walonoski J, Kramer M, Nichols J, et al. Synthea: An approach, method, and software mechanism for generating synthetic patients and the synthetic electronic health care record. JAMIA, 2018. DOI: 10.1093/jamia/ocx079.
- Raasveldt M, Mühleisen H. DuckDB: an Embeddable Analytical Database. SIGMOD 2019. DOI: 10.1145/3299869.3320212.
