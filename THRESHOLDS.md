# Where each threshold comes from (and which ones are NOT from the literature)

Prof. Messori asked: *are the usefulness thresholds based on ECMWF (or another centre), and if so cite the source of each choice.*
**Honest answer: the first version's POD/FAR/AUC levels were generic placeholders, not ECMWF or other-centre thresholds.**
v2 therefore (i) replaces them by criteria that have a stated rationale, (ii) keeps the old grid only as a clearly-labelled
sensitivity range, and (iii) tests whether the conclusions depend on any of it.

## What the literature actually provides (checked 2026-11-04)

| Source | What it says | Usable for us? |
|---|---|---|
| ECMWF, "headline scores" page (ecmwf.int/node/20991) | Headline scores are the lead time at which a score reaches a stated level (e.g. HRES Z500 anomaly correlation 80 %). The page states levels are "chosen to target the verification on the relevant forecast range"; it gives no reason why 80 %. | **No.** Gridded-field ACC; not a binary-event (CI) score. |
| ECMWF, "Landmark in forecast performance" (ecmwf.int/node/25701) | Uses "forecast range at which ACC drops to 60 %" as a key performance indicator; does not call it "useful" nor justify the level. | **No** (same reason). Do not write that 60 % is a "useful" threshold and cite ECMWF. |
| ECMWF e-library 8450, "forecast skill horizon" | Skill horizon = lead at which the forecast stops being more skilful than **climatology** (CRPS, significance test). | **Yes, the principle**: useful = better than climatology. Our tier 1. |
| SII-NowNet (AIES-D-25-0043.1; check author list before citing) | No usefulness threshold. Limits of capability = score falls below climatology, or reliability fails. Binary threshold for POD/FAR chosen at the ROC point maximising POD-POFD. Initiation AUC 0.82 (1 h) -> 0.64 (4 h) over Sumatra (Himawari, 10.4 um). Compares to persistence and climatology. | **Yes**: same principle (beat climatology / persistence) and a published AUC range to compare against. |
| Mecikalski et al. (2008), GOES CI interest fields (nsstc.uah.edu/uahci) | CI = first >= 35 dBZ echo; 0-1 h nowcasts validated 30-60 min ahead; pixel-based POD 0.88-0.998 but FAR 0.69-0.75, threat score 0.26, HSS 0.38. | **Yes**: supports the 35 dBZ definition and the 30-60 min verification window, and shows that published satellite-CI FARs are ~0.7, i.e. our "FAR <= 0.4-0.5" is *stricter* than published. Pixel scoring is not directly comparable. |
| Walker et al. (2012) / SATCAST AMS abstract | CI = transition from below to above 35 dBZ; 0-1 h. Numerical POD/FAR not available to me. | Definition only. Please read the paper and add its POD/FAR yourself. |
| FuXi-Nowcast (arXiv 2512.08974) | Cites Roberts & Rutledge (2003), Bai et al. (2020): 35-40 dBZ; Dixon & Wiener (1993, TITAN): 30-35 dBZ for CI/cell detection. Uses CSI only; no usefulness threshold. | **Yes**: supports our true-CI reflectivity grid 30/35/40 dBZ. |
| NetNCC (QJRMS e70284) | I could not retrieve this paper. | Please check how it defines skill / lead before citing. |

## Our choices, with status

| Choice | Value | Basis | Status |
|---|---|---|---|
| True-CI reflectivity | 30 / 35 / 40 dBZ grid, 35 primary | Mecikalski 2008; Walker 2012; Roberts & Rutledge 2003; Dixon & Wiener 1993 | literature-supported |
| Growth window | 30 / 45 / 60 min, 45 primary | Mecikalski 2008 validates 30-60 min | partly supported; 45 is ours |
| First-echo (candidate) | 25 dBZ (variants 20, 30) | none verified | **ours -> sensitivity** (`run_all.sh variants`) |
| Precursor radius / look-back | 15 km / 30 min (variants 10, 20 / 45) | none verified | **ours -> sensitivity** |
| Lead times | 30-180 min | proposal; literature uses 0-1 h (Mecikalski) and 1-6 h (SII-NowNet) | proposal |
| **Tier 1** usefulness: BSS > 0 (CI lower bound) | 0 | skill-score convention; ECMWF skill-horizon idea; SII-NowNet | **justified** |
| **Tier 2** usefulness: relative economic value | mean V over cost/loss 0.05-0.5 >= 0.02 / 0.05 / 0.10 | Murphy (1977, MWR 105); Richardson (2000, QJRMS 126, 649-667 - ECMWF EPS); please verify the citations | **justified method**; levels are a sensitivity range |
| Tier 3: AUC 0.60-0.80, BSS 0-0.20, POD/FAR pairs | grid | **not from any centre** | **sensitivity grid only** |
| Smallest meaningful difference | AUC 0.02, BSS 0.02, POD 0.03 | **placeholder**. Defensible alternatives: (a) the CV-partition noise in `cv_repeat_sd.csv`, (b) the score difference that changes value V by >= 0.01 at the relevant cost/loss ratios | **must be decided with the supervisor** |

## How to write it in the paper
"We do not adopt a single arbitrary usefulness threshold. A lead time is called *useful* if (1) the forecast beats
climatology (Brier skill score > 0; lower 95 % bound), the same principle ECMWF uses to define its skill horizon, and
(2) it has positive potential economic value for a range of user cost/loss ratios. Because no community-agreed POD/FAR
thresholds exist for CI nowcasting (published satellite CI FARs are ~0.7), we additionally report how the useful lead
time and model ranking change over a grid of POD/FAR/AUC levels."
