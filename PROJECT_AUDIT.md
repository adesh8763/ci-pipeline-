# PROJECT AUDIT: Conditional Information Framework for True Convective Initiation (CI)

Audit date: 2026-10-10 (Asia/Calcutta). Auditor: Claude (research engineering assistant).
Scope of this audit: inspect only. Nothing was executed, downloaded, modified or deleted.

## 1. Headline finding

**The research proposal and the project repository are not present in this workspace.**
Nothing in this audit can be marked complete, failed or partially complete, because there is nothing to inspect.
No region, study period, data product, event definition or modelling decision has been established in any file I can reach, so none is stated here. I have not guessed them.

## 2. What was searched

| Location | Result |
|---|---|
| `/home/claude` (working directory) | Only tool caches and config: `.cache`, `.npm`, `.npm-global`, `.config`, `.ssh`, `.pki`, `.claude` (agent hooks), `.gitconfig`. No project files. |
| `/mnt/user-data/uploads` | Empty. No proposal attached. |
| `/mnt/user-data/working` | Empty. |
| `/mnt/user-data/outputs` (`/mnt/attach/outputs`) | Empty. |
| Filesystem-wide search (excluding system, cache and package paths) for `init.py`, `*proposal*`, `README*`, `*.ipynb`, `*.nc`, `*.grib*`, `*.parquet`, `PHASE*`, `*audit*`, `*convective*`, `CI_*` | Only unrelated system READMEs (`/etc`, rustup docs, a Nix TBB doc). |
| Git repositories | Only `/opt/rbenv` and `/opt/nvm` (system tooling, not this project). The working directory is not a git repository. |

Conclusion: no README, config, scripts, notebooks, datasets, logs, figures or phase/completion notes exist for this project in this session.

## 3. Items from the brief that could not be determined

| Item requested | Status |
|---|---|
| Geographical region | **Not established / unknown.** Not in any reachable file. |
| Study period | **Not established / unknown.** |
| Satellite, radar/precipitation and atmospheric data products | **Not established / unknown.** |
| True-CI and false-CI event definitions | **Not established / unknown.** |
| Existing modelling decisions | **Not established / unknown.** |
| Whether `init.py` (or similar) exists or was run | **No init script found, so no evidence of execution.** I cannot recommend running something I have not read. |
| Which tasks are complete, failed or unverified | **Cannot classify.** No artefacts exist. |

The only project facts available are the ones in your brief (scope, lead times 180/120/90/60/30 min, MI/CMI, models M1 to M6, evaluation themes). They are reproduced in `PHASE_STATUS.md` as the intended scope, not as evidence of progress.

## 4. Environment check (measured)

| Check | Result |
|---|---|
| Python | 3.13.16 |
| Present | numpy 2.5.3, pandas 3.0.5, scipy 1.18.1, scikit-learn 1.9.1, matplotlib 3.11.2, requests 2.34.2, pyyaml 6.0.3 |
| Missing | xarray, netCDF4, h5py, dask, zarr, cfgrib, pyproj, cartopy, metpy, rasterio, satpy, pyart, statsmodels, lightgbm, xgboost, boto3, s3fs |
| Disk | `df` reports about 31 GB available on `/` (14 GB used). Whether that suffices depends on the data volume the proposal implies, which I cannot see. |
| Memory / CPU | 7.8 GiB RAM, 2 cores, no swap |

Which missing packages matter depends on the data products the proposal chooses. Gridded satellite, radar and reanalysis data would very likely need at least xarray plus a NetCDF/GRIB reader. Do not install anything until the products are known.

## 5. Data source reachability (header-only checks, no downloads)

Shell egress goes through a policy-enforcing proxy. Results:

| Host | Result |
|---|---|
| `noaa-goes16.s3.amazonaws.com` | **Denied by policy** (proxy answered 403 to CONNECT). Per proxy guidance, not retried. |
| `cds.climate.copernicus.eu`, `www.ncei.noaa.gov`, `nomads.ncep.noaa.gov`, `data.hrrr.noaa.gov` | No HTTP response (code 000). Cause not confirmed from the portion of the proxy log I read. **Unverified.** |
| `github.com` | HTTP 400 to a HEAD request. Not informative. |
| `pypi.org` | No HTTP response to a HEAD request. Package installs were not tested. |

These checks used placeholder hosts commonly used for this kind of work, because the proposal's real sources are unknown. They show only that **this sandbox's outbound access is restricted and may block the proposal's actual data sources**. This must be re-tested against the real sources once they are known. If they are blocked, data would have to be supplied as uploads, or the data-acquisition phase run somewhere with access.

## 6. Risks and blockers

1. **Missing source of truth.** Without the proposal, any definition of CI events, region or period would be invented.
2. **Restricted network.** Large-scale data acquisition from this sandbox may not be possible.
3. **Limited resources.** 7.8 GiB RAM and 2 cores favour a small, subsampled workflow (consistent with "smallest practical workflow").
4. **Sandbox state.** The session may not persist your real repository. If your work lives on your own machine, it has not been linked here.

## 7. What I did not do

No scripts were run, no packages installed, no data downloaded, no files outside the three audit documents created, and nothing deleted or overwritten.

## 8. Recommended next step

See `PHASE_STATUS.md` (section "Next action") for the exact prompt to run after the proposal and repository are provided.
