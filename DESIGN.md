# Design: Structured Query-Plan Schema and Reasoning-Trace SFT/RL

## 1. The idea

Instead of training SFT to map `question -> SQL` directly, SFT is targeted to produce a **structured intermediate query plan followed by the compiled SQL, in one continuous completion**:

```
question -> { plan JSON } -> SQL
```

Both halves are learned together in SFT (not just the plan, with SQL bolted on separately) so RL — a later stage — inherits a strong, warm-started policy for the whole trace, not a cold start. RL then continues training this same combined completion, computing reward **only on the final SQL's** execution correctness + efficiency (a tiered reward, see `rl_train.ipynb`'s `CFG`) — the plan portion isn't separately rewarded, but rewriting the SQL well requires the plan preceding it to actually be useful, so gradient signal flows back through the whole trace.

Two reasons for this shape, expanded in `PAPER.md` Section 1.2. First, the plan is an **inspectable intermediate representation**: which concept the model believes the question names, whether it thinks a terminology lookup is required, which structural joins it intends, and what aggregation it will compute are all readable independently of whether the final SQL string matches gold. Second, it gives the RL stage a **reasoning trace to refine** rather than a single opaque guess — the reasoning-then-answer shape GRPO and DAPO were designed around.

## 2. The plan schema

Full schema and worked example: `scripts/plan_schema.py`. Summary:

```json
{
  "entities": [
    {"role": "primary", "concept": "Biopsy of breast (procedure)",
     "domain": "procedure", "terminology_lookup": true}
  ],
  "joins": [],
  "constraints": [
    {"type": "status", "field": "status", "value": "completed"}
  ],
  "aggregation": {"type": "list_distinct_patient", "group_by": null,
                  "order_by": null, "limit": null, "per_patient_metric": null},
  "abstain": false
}
```

Closed, enumerable vocabulary for `constraint.type` and `aggregation.type` by design -- not because the real space is small, but because every value maps 1:1 to a clause shape some archetype's `sql` template already needs. Extending to a new shape means deliberately extending the vocabulary (and `plan_schema.py`'s docstring), not letting the model invent categories.

Terminology resolution reuses a lookup-CTE mechanism: `WITH resolved AS (SELECT code, code_system FROM valuesets WHERE table_name = '...' AND display ILIKE '%{search_term}%') ...` -- the model's job is never to know a code, only to (a) name the concept correctly in the plan and (b) compile a syntactically correct lookup CTE around it. `build_valuesets.py` builds the lookup table (`lookup_ambiguous` computed via self-join; concepts flagged ambiguous are excluded from gold, never force-resolved with `LIMIT 1`).

## 3. Data generation and verification

All clinical archetypes (tiers 1-4) plus the operational, regulatory, and quality-KPI concept-parameterized archetypes carry both a `plan` template and lookup-based SQL -- 82 distinct archetypes in the assembled training set, yielding 2,420 distinct executable gold SQL statements. `plan_schema.py` documents the schema (`entities`/`joins`/`constraints`/`aggregation`/`abstain`), extended during implementation to add a `joins` field for structural table touches distinct from concept entities, and `having`/`point_in_time` constraint types plus `avg_per_patient`/`avg_age_at_event`/`avg_days_between_events`/`top_n_by_value` aggregation types for tier-3/4 and operational shapes.

- Train-side gold generation: 2,051/2,346 main + 175/199 operational + 167/189 quality-KPI + 27/31 regulatory verified (zero execution errors throughout), assembled into `sft_final_plan.jsonl` (10,696 rows, including 1,016 abstention rows).
- Heldout benchmark regenerated in the same format: familiar 2,071/2,346 verified -> 9,300 rows (incl. abstention), unseen 285/296 verified -> 2,156 rows.
- Target format: `json.dumps(plan, indent=2)` + `"\n\n```sql\n" + sql + "\n```"` -- a markdown-fenced code block, chosen for unambiguous regex extraction and because the base model is heavily pretrained on the convention. Verified against the entire assembled dataset: 10,696/10,696 rows round-trip through `extract_sql_from_completion()` back to the exact `gold_sql` they were built from.
- Every assembled row carries `gold_sql`/`gold_plan` directly (not just the compiled `target` string), so reward computation and evaluation never need to re-parse gold's own target.
- Both notebooks: prompt requests plan-then-SQL; `build_messages` targets `row['target']`; `instance_key`/stratified split keys on `gold_sql`; `compute_reward` (RL) and `evaluate_generation` (both notebooks) extract SQL via the fence before scoring -- a missing/unparseable fence scores `reward_non_executing` (same tier as broken SQL) and is logged separately as `malformed_completion` for diagnostics. The plan JSON itself is never separately rewarded, only the compiled SQL's correctness + efficiency.

## 4. Anti-hardcoding reward penalty

`compute_reward` detects whether a correct, executing prediction got there by hardcoding a literal terminology code/system instead of resolving it via the `valuesets` lookup CTE (`has_hardcoded_terminology`, `_HARDCODED_TERMINOLOGY_RE` -- a column-name-based regex matching `code`/`system`/`type_code`/`type_system`/`vaccineCode`/`vaccineCode_system` compared to a quoted literal, which can only match a bypassed lookup since every legitimate lookup CTE in this design filters exclusively on `table_name`/`display`, never on `code`/`system` themselves). A correct-but-hardcoded prediction scores `reward_hardcoded_value=-0.2` instead of the correct-answer tier, and never earns the efficiency bonus.

Validated with zero false positives across all 9,680 gold-SQL-bearing rows (2,420 distinct statements; gold is always properly lookup-based, and the remaining 1,016 rows are abstentions carrying no SQL), and confirmed to correctly ignore legitimate non-terminology literals (`class_code='IMP'`, `clinicalStatus='active'`). Also exposed as a diagnostic metric (`gen_hardcoded_rate`, fraction of exec-correct rows that hardcoded a value) in `evaluate_generation` in both notebooks, so this specific failure mode is directly visible in eval output over the course of training. See `PAPER.md` Section 5.4 for real-run results (0.0% hardcoding rate across every fine-tuned run).

## Results

See `PAPER.md` for the full experimental results, error analysis, and discussion. See `METHODOLOGY_LOG.md` for the dated development diary (schema decisions, bugs found and fixed, verification methodology) this design document draws on.
