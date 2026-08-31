# ML4H 2026 — Findings track submission checklist

**Deadline: 10 September 2026, 11:59 PM AoE.** Decisions 22 Oct · camera-ready 7 Nov (tentative) · symposium 6–7 Dec, Sydney (in person).

Verified against the [ML4H 2026 call for papers](https://ml4h.ahli.cc/submit/call-for-papers/).

---

## Why Findings rather than Proceedings

| | Findings | Proceedings |
|---|---|---|
| Length | 4 pages | 8 pages |
| Archival | **No** | Yes (PMLR) |
| Blocks a later journal submission | **No** | Yes |
| Preprints allowed | **Yes**, explicitly encouraged | Prohibited if already archival |

The Findings track explicitly solicits *"insightful negative results"* and permits synthetic data (*"authors may use synthetic datasets to demonstrate properties of their proposed algorithms"*) — the two features of this work most likely to be attacked elsewhere. Non-archival status means the full paper can still go to a journal afterwards.

## Steps

1. **Open the official template**
   https://www.overleaf.com/latex/templates/machine-learning-for-health-ml4h-2026-template/sqgwhtyswgcy
   It uses `\documentclass[pmlr,twocolumn,10pt]{jmlr}` and supplies `jmlr.cls`. **Select the `findings` track** using the template's own track macro, and enable its **anonymous** switch.

2. **Paste in `main.tex`** (everything from `\title` onward) and upload `refs.bib`. Keep the template's preamble — do not replace it with the one in `main.tex`, which is a stand-in so the file is readable on its own.

3. **Compile and check the page count.** Target is 4 pages **excluding references and appendices**. If it overruns, cut in this order: (a) the verbatim SQL block → prose, (b) the Discussion's outlook paragraph, (c) move "What each arm can and cannot show" detail into an appendix — but keep at least the 96.5% and 53.9% figures in the main text, since that honesty is a strength with this reviewer pool.

4. **Verify anonymization.** Review is double-blind and de-anonymization is grounds for desk rejection.
   - No author name or affiliation
   - No GitHub / Zenodo / Hugging Face URLs (the availability statement is already written around this)
   - Check the compiled PDF metadata (Overleaf can embed an author name — set `\hypersetup{pdfauthor={}}` if needed)

5. **Declare the overlapping public release.** Findings permits work that is preprinted or under review elsewhere, but *"authors should clearly state any overlapping published or submitted work at the time of submission."* The paper's availability statement does this; also state it in the OpenReview submission form.

6. **Submit** at https://openreview.net/group?id=ML4H/2026/Symposium

## Before submitting — decisions still open

- **Sydney attendance.** At least one presenting author must register for the in-person event. Don't submit intending to no-show; the asynchronous exception is narrow (political travel restrictions only).
- **Title.** The current one is long. A shorter alternative: *"Resolving Clinical Terminology in the Database Makes Concept Generalization Measurable."*
- **Figure.** There is currently no figure. A single two-arm evaluation-design diagram, or the frozen/SFT/RL bar chart, would help — reviewers skim figures first. Optional at 4 pages.

## Deliberately omitted

- **Frozen-API baseline.** Not run, by decision: for PHI-bearing clinical databases, sending records to a hosted third-party model is typically precluded by data-governance and residency rules regardless of accuracy, so it is not an available alternative. This is argued in the Discussion rather than left as a silent gap — expect at least one reviewer to raise it anyway.
- **Novel-abstention probe.** Not run; the paper instead states plainly that abstention results measure retention of trained refusal categories.

## After decisions (22 Oct)

Findings is non-archival, so the full paper proceeds to **JMIR AI** (Original Paper, US $1,985, PubMed-indexed) regardless of outcome. A medRxiv preprint in the Health Informatics category is the recommended companion step — note that arXiv tightened its endorsement policy in January 2026, which is a real obstacle for an author without an institutional email.
