# PHASE STATUS: True CI Conditional Information Framework

Audit date: 2026-10-10. Legend: **NOT STARTED** = no artefact found; **UNVERIFIED** = cannot be assessed; nothing here is marked complete.

> No proposal or repository was found in this workspace (see `PROJECT_AUDIT.md`). Every status below reflects absence of evidence, not a judgement of your actual progress. Phase names are taken from the scope in your brief; phase boundaries should be reconciled with the proposal.

## Phase table

| # | Phase | Status | Evidence | Blocked by |
|---|---|---|---|---|
| P0 | Source-of-truth capture (proposal, region, period, products, definitions) | **BLOCKED: proposal not available** | None found | Proposal and repo must be supplied |
| P1 | Environment and data-access readiness | **PARTIAL (measured)**: Python 3.13 + core stack present; geospatial/NetCDF stack missing; source access unverified/denied for the one host that was clear | See audit section 4, 5 | P0 (to know which products and packages) |
| P2 | Data acquisition (satellite, radar/precip, atmosphere) | **NOT STARTED / UNVERIFIED** | No data files found | P0, P1 |
| P3 | Event construction (true-CI, false-CI) | **NOT STARTED / UNVERIFIED** | No event table or labels found | P0, P2 |
| P4 | Predictor extraction at 180/120/90/60/30 min lead times | **NOT STARTED / UNVERIFIED** | None | P2, P3 |
| P5 | Dataset assembly, QC, train/validation/test split design | **NOT STARTED / UNVERIFIED** | None | P3, P4 |
| P6 | Information analysis: MI and CMI (atmosphere conditional on satellite+radar) | **NOT STARTED / UNVERIFIED** | None | P5 |
| P7 | Models M1 to M6 | **NOT STARTED / UNVERIFIED** | None | P5 (M6 also needs P6 for group selection) |
| P8 | Evaluation: detection skill, calibration, useful warning lead time | **NOT STARTED / UNVERIFIED** | None | P7 |
| P9 | Robustness checks (where data permit) | **NOT STARTED / UNVERIFIED** | None | P7, P8 |
| P10 | Reporting: figures, tables, write-up | **NOT STARTED / UNVERIFIED** | None | P6, P8, P9 |

## Model definitions to preserve (from brief; not yet implemented anywhere I can see)

- M1 satellite only
- M2 radar only
- M3 satellite + atmosphere
- M4 satellite + radar
- M5 satellite + radar + atmosphere
- M6 full model with selected atmospheric groups removed

Key comparisons: M4 vs M5 (unique atmospheric value beyond satellite+radar); M1 vs M3 and M2 vs M5 (atmosphere added to a single source); M5 vs M6 (which atmospheric groups carry the information).

## Dependency map

```
P0 proposal/definitions
 ├─> P1 environment + access checks
 │     └─> P2 data acquisition ──┐
 └───────────────────────────────┤
                                 ▼
                       P3 true/false CI events
                                 ▼
                 P4 predictors at 180/120/90/60/30 min
                                 ▼
                 P5 dataset assembly + QC + split design
                     ├─────────────────────┐
                     ▼                     ▼
              P6 MI / CMI            P7 models M1..M5
                     │                     │
                     └──> M6 group selection ──> P7 (M6)
                                           ▼
                           P8 detection / calibration / lead time
                                           ▼
                                   P9 robustness
                                           ▼
                                   P10 reporting
```

Critical path: P0 → P2 → P3 → P4 → P5 → P7 → P8 → P10. P6 (MI/CMI) is on the path only for M6's choice of removed groups.
Cross-cutting risks: event labels (P3) determine everything downstream; leakage controls (e.g. no predictor after lead time, spatial/temporal split in P5) must be fixed before P6/P7.

## Next action

The audit cannot proceed to a repository-specific recommendation until the proposal and repository are available here.

**Step 1.** Provide, in one of these ways:
- attach the proposal (PDF/DOCX/MD) and, if it exists, the repository (zip, or a GitHub `owner/repo` that this session can attach), or
- paste the proposal text into the chat and list the files in your repo (`ls -R` or `tree`) plus the contents of `README`, `init.py` and any phase notes.

**Step 2.** Then run this prompt:

```
Re-run the project audit. The proposal and repository are now attached. Read the proposal first, then inspect the repo (README, configs, init.py without executing it, scripts, notebooks, data, logs, figures, phase notes). Update PROJECT_AUDIT.md and PHASE_STATUS.md in place: replace the "unknown" entries with what the files establish (region, period, products, event definitions, modelling decisions), classify each task as complete / incomplete / failed / unverified with evidence, say whether init.py has been run and what it does, and give the exact next command. Do not execute the pipeline.
```
