# OpenReview submission — SUBMITTED

**Status: submitted to ML4H 2026, Findings track.**

| | |
|---|---|
| Forum | https://openreview.net/forum?id=EntkxH9paA |
| Submission ID | `EntkxH9paA` |
| Submission number | 41 |
| Track | Findings (non-archival) |

## Remaining action — reviewer waiver

File the exemption form, which requires the ID above:
https://docs.google.com/forms/d/e/1FAIpQLSe827colORXf495aAXCOgN8gjCD52dcL4-hiPAoygmfyMDkiw/viewform

- **Paper title:** Plan-Then-Compile: Resolving Clinical Terminology in the Database Enables FHIR-to-SQL Generalization to Unseen Concepts
- **Submission ID:** `EntkxH9paA` (Submission 41)
- **Grounds:** no prior archival peer-reviewed publication; prior work is self-archived only

An unregistered, unexempted submission is desk-rejectable, so this is not
optional. File it well before the deadline so it can be processed.

## Dates from here

| | |
|---|---|
| Reviews released | 5 Oct |
| Author response window | 5–12 Oct — keep this free |
| Decisions | 22 Oct |
| Camera-ready | 7 Nov (tentative) |
| Symposium | 6–7 Dec, Sydney |

On acceptance, de-anonymize for camera-ready: restore author name and
affiliation, add the public repository, DOI and Hugging Face links to the Data
and Code Availability statement, and add the acknowledgments (which the template
says must appear only in the camera-ready version).

---

# Prepared field answers (as submitted)

Submit at: https://openreview.net/group?id=ML4H/2026/Symposium
**Deadline: 10 September 2026, 11:59 PM AoE.**

---

## Track

**Findings**

Chosen deliberately over Proceedings: Findings is non-archival, so it does not
block a later journal submission, and it explicitly permits preprints and work
under review elsewhere. Proceedings is archival and would have foreclosed the
journal route.

## Title

> Plan-Then-Compile: Resolving Clinical Terminology in the Database Enables
> FHIR-to-SQL Generalization to Unseen Concepts

## Abstract

Plain-text form of the manuscript abstract, LaTeX markup unwrapped
(221 words, 1,358 characters). Contains no mathematics, so no `$...$` is
needed. Kept verbatim-identical in substance to `main.tex` — if you edit one,
edit both. Regenerate with the snippet in `make_abstract.txt`.

```
Text-to-SQL over clinical data conflates two skills: composing a query, and mapping a clinical concept to the code the database stores it under. When gold SQL embeds literal codes, the second is memorization, and no metric computed on that data can separate them. We rebuild a FHIR-derived benchmark so terminology is resolved through the database — every gold query looks the concept up in a valuesets table at runtime and never embeds a literal SNOMED CT, ICD-10 or RxNorm code — and pair each target with a structured JSON query plan compiled into SQL in one completion. On an earlier version of this pipeline that did embed literal codes, a fine-tuned model reached 98.4% execution match on familiar concepts but 20.7% on concepts absent from training. Under the lookup design, DoRA fine-tuning of a 14B open-weight coder model reaches 100% on familiar concepts and 89.1% on unseen ones (81.4% by the stricter text metric), from frozen baselines of 34.8% and 60.8%. An ablation isolates why this works: merely making the lookup table visible in the schema drives the untrained model's code-hardcoding from 3.4% to 0.0%, with no training signal at all — models bypass a resolution mechanism they cannot see. We additionally report that a DAPO/GRPO stage adds nothing on top of supervised fine-tuning, which already saturates the reward's correctness gate.
```

## TL;DR

```
Resolving clinical terminology through a database lookup rather than memorized codes lifts unseen-concept FHIR-to-SQL from 20.7% to 89.1%; merely making the lookup table visible drives an untrained model's code-hardcoding to zero.
```

230 characters. Leads with the mechanism and the headline number, and closes on
the ablation rather than the RL null, which should not be what a skim-reader
takes away.

Shorter alternative if the field is tighter (175 characters):

```
Resolving clinical terminology through a database lookup instead of memorized codes lifts FHIR-to-SQL accuracy on clinical concepts never seen in training from 20.7% to 89.1%.
```

## Subject area

**Applications and Practice**

Revised from an initial reading of "Models and Methods". The CFP's own bullets
under Applications and Practice are three direct hits:

- *"Datasets and simulation frameworks for addressing gaps in ML healthcare applications"* — the synthetic corpus
- *"Surveys, benchmarks, evaluations and best practices of using ML in healthcare"* — the two-arm benchmark
- *"electronic health records (EHR)"* — named as a traditional area

Models and Methods is for new learning algorithms; this work uses DoRA and DAPO
off the shelf and claims no algorithmic novelty, so reviewers in that area would
ask for something the paper does not offer. Applications reviewers are also
markedly more receptive to synthetic-data and benchmark contributions.

## Specific subject areas

Paste (all but the last are lifted from the CFP's own vocabulary, so they match
how reviewers self-declare expertise):

```
electronic health records (EHR), benchmarks and evaluation, datasets and simulation frameworks, domain adaptation and generalization, natural language processing, text-to-SQL
```

If the field takes only two or three: `electronic health records (EHR)`,
`benchmarks and evaluation`, `natural language processing`.

`domain adaptation and generalization` sits under a different top-level area but
is kept deliberately — it is the term that best describes what the unseen-concept
arm measures, and may attract a reviewer who scrutinises generalization claims.

## Keywords

Paste exactly (these drive reviewer matching, so they must pull a clinical
text-to-SQL reviewer rather than a generic ML one):

```
text-to-SQL, clinical natural language processing, electronic health records, FHIR, large language models, parameter-efficient fine-tuning, clinical terminology, synthetic health data
```

Identical to the `\begin{keywords}` block in `main.tex` — keep them in sync.

If the form caps the count, drop in this order: `synthetic health data`,
`clinical terminology`, `FHIR`. Never drop `text-to-SQL` or
`electronic health records`.

Deliberately omitted: `reinforcement learning` / `GRPO`. Including them would
match RL reviewers who would then judge the paper on its weakest section; the
null result is one scoped subsection and should not drive reviewer assignment.

## Data modality

**Structured electronic health records / tabular clinical data** — FHIR R4
resources flattened to a relational schema. Synthetic (Synthea), not real
patient data. Also involves natural-language questions and SQL, so if the form
allows multiple selections, add **text**.

## Ethics board approval

**Not applicable — no human subjects.** Suggested wording:

> This study uses only synthetic patient records generated by Synthea. No real
> patient data, human subjects, or identifiable information are involved, so
> institutional ethics approval is not required. Confirmation will be provided
> if requested on acceptance.

## Code and data availability

> All code, generated datasets, trained adapter weights, and the complete
> per-seed training logs, evaluation summaries, failure logs and ablation
> results are publicly released under open licenses (Apache-2.0 for code,
> CC-BY-4.0 for data and paper). Links are withheld from the submission to
> preserve anonymity and will be provided on acceptance.

## Supplemental material (anonymized code and data)

Upload `supplementary_anonymous.zip` (95 files, 0.61 MB). Built and audited by
`build_supplementary.py`; do NOT upload the public repository, which names the
author and would be grounds for desk rejection.

Field answer:

```
Yes. Anonymized code is included as supplementary material (supplementary_anonymous.zip): the corpus generation and execution-verification scripts, both analysis scripts that reproduce the paper's tables, the frozen benchmark schema, the three training and ablation notebooks configured as run, and every per-seed training log, held-out evaluation summary, failure log and ablation result behind the numbers reported.

All data in this study is synthetic, generated by Synthea. No real patient data, human subjects or identifiable information are involved, so no approvals, data-use agreements or access restrictions apply, and the data can be released without conditions.

The generated dataset files (~86 MB) and the flattened DuckDB databases are omitted from the supplement for size only; they are fully regenerable from the included scripts, and the analysis scripts run directly against the included logs. Author-identifying material - the paper, README, license, citation metadata and model card - is excluded to preserve anonymity, and all public repository links are withheld during review. Everything will be de-anonymized and linked in the camera-ready version.
```

Note the "with appropriate approval and guidelines" clause is aimed at
submissions constrained by DUAs, IRB conditions or PHI. This study has none of
those, so the answer states plainly that no approval is required and the data
carries no release conditions - a genuine advantage that reviewers will
otherwise assume away.

## Overlapping / prior work declaration — **required, do not skip**

The Findings track allows work that is preprinted or under review elsewhere,
*"if this is the case, authors should clearly state any overlapping published or
submitted work at the time of submission."* Suggested wording:

> A de-anonymized, longer version of this work has been publicly archived with a
> DOI as a self-published preprint and software release. It has not been
> published in, nor is it currently under review at, any peer-reviewed venue.
> The submitted 4-page manuscript is a condensed presentation of that work.

## Reciprocal reviewer

The CFP requires: *"Every submission must include at least one author registered
to review a minimum of three (3) papers"*, and *"if no author is registered as a
reviewer by the specified deadline, the submission may be desk rejected."*

**Likely route: request exemption.** The qualification bar is *"at least one
prior archival publication at a comparable peer-reviewed venue."* Prior output
here is self-archived (Zenodo) rather than peer-reviewed archival, so the
qualification is probably not met.

Exemption form:
https://docs.google.com/forms/d/e/1FAIpQLSe827colORXf495aAXCOgN8gjCD52dcL4-hiPAoygmfyMDkiw/viewform

**File the exemption before the deadline.** Do not leave this field blank — an
unregistered, unexempted submission is desk-rejectable. If you would rather
review than claim exemption, note that assignments are made by the organizers
and reviews are due before 5 October.

## Conflicts of interest

Declare current employer so the organizers can avoid conflicted reviewers.
Nothing about the employment funded or directed this work; state it as
independent research.

---

# Pre-submission checks

- [ ] Compiled in the official Overleaf template, `findings` track selected, anonymous mode on
- [ ] 4 pages or fewer, excluding references and appendices
- [ ] Data and Code Availability statement sits **directly after the abstract** (template requirement)
- [ ] Keywords block present
- [ ] No code links in the abstract (the template warns indexers redact them)
- [ ] No author name, affiliation, or GitHub/Zenodo/Hugging Face URL anywhere in the PDF
- [ ] PDF metadata carries no author name (Overleaf can embed it — check document properties)
- [ ] `fig1_unseen.pdf` uploaded alongside `main.tex` and `refs.bib`
- [ ] Only the auto-loaded packages used (amsmath, amssymb, natbib, graphicx, url, algorithm2e)
- [ ] Reciprocal reviewer registered **or** exemption form filed
- [ ] Overlapping-work declaration entered

# Dates

| | |
|---|---|
| Submission deadline | **10 Sep 2026**, 11:59 PM AoE |
| Reviews released | 5 Oct |
| Author response window | 5–12 Oct |
| Decisions | **22 Oct** |
| Camera-ready | 7 Nov (tentative) |
| Symposium | 6–7 Dec, Sydney — one author must register |

# Still open

**Sydney attendance.** The CFP says at least one presenting author must
*register*; no virtual option is stated and registration pricing is not yet
published. Worth emailing `ml4h@ahli.cc` to ask whether registration without
physical attendance is acceptable, before investing in the author-response
round.
