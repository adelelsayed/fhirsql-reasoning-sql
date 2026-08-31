# Citations

Reference list for the paper, covering everything the study depends on: synthetic data generation, clinical terminology standards, domain-grounding sources for the regulatory/quality-KPI archetypes, infrastructure, and the fine-tuning method/libraries. Organized by category. Each entry notes what in this project it supports.

---

## Synthetic patient corpus

**Walonoski J, Kramer M, Nichols J, Quina A, Moesel C, Hall D, Duffett C, Dube K, Gallagher T, McLachlan S.** Synthea: An approach, method, and software mechanism for generating synthetic patients and the synthetic electronic health care record. *Journal of the American Medical Informatics Association*, 2018;25(3):230-238. DOI: [10.1093/jamia/ocx079](https://doi.org/10.1093/jamia/ocx079)
— The generator behind the entire corpus (train and held-out populations).

---

## Clinical data standards and terminology systems

Every coded field in the schema (`code`/`system`/`display` triples across condition, observation, medication_request, procedure, immunization) uses one of these standards; the FHIR structures themselves define the schema's shape.

- **HL7 International.** HL7 FHIR Release 4 (R4). [https://hl7.org/fhir/R4/](https://hl7.org/fhir/R4/)
  — The resource model the entire flattening/schema-design exercise is built on.
- **HL7 International.** US Core Implementation Guide. [https://hl7.org/fhir/us/core/](https://hl7.org/fhir/us/core/)
  — Source of the race/ethnicity extension structure parsed onto `patient`.
- **SNOMED International.** SNOMED CT. [https://www.snomed.org/](https://www.snomed.org/)
  — Coding system for condition and procedure concepts throughout the concept bank.
- **McDonald CJ, Huff SM, Suico JG, et al.** LOINC, a universal standard for identifying laboratory observations: a 5-year update. *Clinical Chemistry*, 2003;49(4):624-633. DOI: [10.1373/49.4.624](https://doi.org/10.1373/49.4.624)
  — Coding system for observation concepts.
- **Nelson SJ, Zeng K, Kilbourne J, Powell T, Moore R.** Normalized names for clinical drugs: RxNorm at 6 years. *Journal of the American Medical Informatics Association*, 2011;18(4):441-448. DOI: [10.1136/amiajnl-2011-000116](https://doi.org/10.1136/amiajnl-2011-000116)
  — Coding system for medication_request concepts, including the narcotic/controlled-substance list used in the regulatory archetypes.

---

## Text-to-SQL and clinical question answering

The task literature this study sits in. See PAPER.md Section 1.4 for how this work relates to each.

**General text-to-SQL**

- **Zhong V, Xiong C, Socher R.** Seq2SQL: Generating Structured Queries from Natural Language using Reinforcement Learning. *arXiv:1709.00103*, 2017. — WikiSQL, and the earliest execution-reward RL for text-to-SQL.
- **Yu T, Zhang R, Yang K, et al.** Spider: A Large-Scale Human-Labeled Dataset for Complex and Cross-Domain Semantic Parsing and Text-to-SQL Task. *EMNLP 2018*. arXiv:1809.08887. — The standard cross-domain benchmark.
- **Li J, Hui B, Qu G, et al.** Can LLM Already Serve as A Database Interface? A BIg Bench for Large-Scale Database Grounded Text-to-SQLs (BIRD). *NeurIPS 2023 Datasets & Benchmarks*. arXiv:2305.03111. — Adds execution efficiency and dirty values to evaluation.
- **Wang C, Huang P, Polozov A, Brockschmidt M, Singh R.** Execution-Guided Neural Program Decoding. *ICML 2018 Workshop (NAMPI)*. arXiv:1807.03100.
- **Scholak T, Schucher N, Bahdanau D.** PICARD: Parsing Incrementally for Constrained Auto-Regressive Decoding from Language Models. *EMNLP 2021*. arXiv:2109.05093. — Constrained decoding baseline; not used here.

**Intermediate representations and decomposition**

- **Guo J, Zhan Z, Gao Y, et al.** Towards Complex Text-to-SQL in Cross-Domain Database with Intermediate Representation (IRNet/SemQL). *ACL 2019*. arXiv:1905.08205.
- **Wang B, Shin R, Liu X, Polozov O, Richardson M.** RAT-SQL: Relation-Aware Schema Encoding and Linking for Text-to-SQL Parsers. *ACL 2020*. arXiv:1911.04942.
- **Gan Y, Chen X, Xie J, et al.** Natural SQL: Making SQL Easier to Infer from Natural Language Specifications. *Findings of EMNLP 2021*. arXiv:2109.05153.
- **Pourreza M, Rafiei D.** DIN-SQL: Decomposed In-Context Learning of Text-to-SQL with Self-Correction. *NeurIPS 2023*. arXiv:2304.11015.
- **Gao D, Wang H, Li Y, et al.** Text-to-SQL Empowered by Large Language Models: A Benchmark Evaluation (DAIL-SQL). *VLDB 2024*. arXiv:2308.15363.

**Clinical text-to-SQL and cohort querying**

- **Wang P, Shi T, Reddy CK.** Text-to-SQL Generation for Question Answering on Electronic Medical Records (MIMICSQL/TREQS). *WWW 2020*. arXiv:1908.01839. — Clinical text-to-SQL over MIMIC-III; gold SQL resolves concepts via dictionary-table matching.
- **Lee G, Hwang H, Bae S, et al.** EHRSQL: A Practical Text-to-SQL Benchmark for Electronic Health Records. *NeurIPS 2022 Datasets & Benchmarks*. — Establishes unanswerable questions as a first-class benchmark component.
- **Lee G, Kweon S, Bae S, Choi E.** TrustSQL: Benchmarking Text-to-SQL Reliability with Penalty-Based Scoring. *arXiv:2403.15879*, 2024. — Reliability-aware evaluation where abstention is scored explicitly.
- **Yuan C, Ryan PB, Ta C, et al.** Criteria2Query: a natural language interface to clinical databases for cohort definition. *JAMIA*, 2019;26(4):294-305. DOI: [10.1093/jamia/ocy178](https://doi.org/10.1093/jamia/ocy178)

---

## Infrastructure

**Raasveldt M, Mühleisen H.** DuckDB: an Embeddable Analytical Database. In *Proceedings of the 2019 International Conference on Management of Data* (SIGMOD '19), pp. 1981-1984. DOI: [10.1145/3299869.3320212](https://doi.org/10.1145/3299869.3320212)
— The embedded database every table is flattened into and every gold-SQL statement is execution-verified against.

---

## Base model and fine-tuning method

- **Hui B, Yang J, Cui Z, et al.** Qwen2.5-Coder Technical Report. *arXiv:2409.12186*, 2024. [https://arxiv.org/abs/2409.12186](https://arxiv.org/abs/2409.12186)
  — Base model for SFT (`Qwen/Qwen2.5-Coder-14B-Instruct`).
- **Hu EJ, Shen Y, Wallis P, Allen-Zhu Z, Li Y, Wang S, Wang L, Chen W.** LoRA: Low-Rank Adaptation of Large Language Models. *arXiv:2106.09685*, 2021. Also ICLR 2022. [https://arxiv.org/abs/2106.09685](https://arxiv.org/abs/2106.09685)
  — Method underlying the fine-tuning approach; motivates the all-linear-layer target-module choice discussed in METHODOLOGY_LOG.md.
- **Liu SY, Wang CY, Yin H, Molchanov P, Wang YCF, Cheng KT, Chen MH.** DoRA: Weight-Decomposed Low-Rank Adaptation. *ICML 2024 (Oral)*. arXiv:2402.09353. [https://arxiv.org/abs/2402.09353](https://arxiv.org/abs/2402.09353)
  — The adapter variant actually used for training (`use_dora=True`), decomposing each targeted weight matrix into magnitude and direction rather than plain LoRA's single low-rank update.
- **Dettmers T, Pagnoni A, Holtzman A, Zettlemoyer L.** QLoRA: Efficient Finetuning of Quantized LLMs. *Advances in Neural Information Processing Systems* 36 (NeurIPS 2023). arXiv:2305.14314. [https://arxiv.org/abs/2305.14314](https://arxiv.org/abs/2305.14314)
  — Source of the NF4 4-bit quantization scheme and the all-linear-layer LoRA target-module recipe actually used for training.
- **Wolf T, Debut L, Sanh V, et al.** Transformers: State-of-the-Art Natural Language Processing. In *Proceedings of EMNLP 2020: System Demonstrations*, pp. 38-45. [https://aclanthology.org/2020.emnlp-demos.6/](https://aclanthology.org/2020.emnlp-demos.6/)
  — Library used for model loading, tokenization, and generation.
- **Mangrulkar S, Gugger S, Debut L, Belkada Y, Paul S, Bossan B, Tietz M.** PEFT: State-of-the-art Parameter-Efficient Fine-Tuning methods. 2022. [https://github.com/huggingface/peft](https://github.com/huggingface/peft)
  — Library used for the LoRA adapter implementation.

---

## Reinforcement learning method

- **Shao Z, Wang P, Zhu Q, Xu R, Song J, Bi X, Zhang H, Zhang M, Li YK, Wu Y, Guo D.** DeepSeekMath: Pushing the Limits of Mathematical Reasoning in Open Language Models. *arXiv:2402.03300*, 2024. [https://arxiv.org/abs/2402.03300](https://arxiv.org/abs/2402.03300)
  — Origin of GRPO (Group Relative Policy Optimization): critic-free advantage estimation via within-group reward normalization across several sampled completions of the same prompt, which `group_advantages` implements directly.
- **Yu Q, Zhang Z, Zhu R, Yuan Y, Zuo X, Yue Y, Fan T, Liu G, Liu L, Liu X, et al.** DAPO: An Open-Source LLM Reinforcement Learning System at Scale. *arXiv:2503.14476*, 2025. [https://arxiv.org/abs/2503.14476](https://arxiv.org/abs/2503.14476)
  — The RL algorithm used in `rl_train.ipynb`: Clip-Higher (asymmetric PPO clipping), Dynamic Sampling (dropping zero-reward-variance groups), and token-level (rather than sequence-averaged) policy-gradient loss normalization. DAPO's fourth technique, Overlong Reward Shaping, is not used -- it targets runaway-length generation in long chain-of-thought reasoning, a failure mode that doesn't apply to length-capped SQL generation.
