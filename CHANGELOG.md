# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [2.2.1] - 2026-07-29

PATCH release of SURFMAP - contains breaking changes for local (non-Docker) users, see below

### Added
- functional CLI test suite: `surfmap/tests/tests_parameters.py` (fast, hermetic `Parameters` input-validation unit tests) and `surfmap/tests/tests_functional_docker.py` (real end-to-end `--docker` tests covering `-tomap all/electrostatics/stickiness --keep`, `-res`, `binding_sites`, invalid input, `-v`/`-h`, checking exit codes and produced/removed output files)
- `.github/workflows/development-ci.yml`: runs both test suites on every push to `development` (and PRs targeting `development`/`master`), building the Dockerfile fresh with GitHub Actions layer caching; if green and `__VERSION__` was bumped, automatically fast-forwards `development` to `master`, tags `vX.Y.Z`, and creates a GitHub Release (which in turn triggers `release-assets.yml`)
- `CONTRIBUTING.md`: development process documentation (branching model, running tests locally, what each CI workflow does, and the full release process - including the manual Docker Hub image push step needed for `lopesi2bc/surfmap`, which no CI workflow automates yet)


### Changed
- `setup.py` now reads the package version directly from `surfmap.__VERSION__` instead of hardcoding it, avoiding version drift
- `freesasa` dependency is now resolved per Python version: `2.1.0` for `python_version < '3.12'`, `2.2.1` for `python_version >= '3.12'` (tested up to Python 3.14)
- input file mounts for `--docker` runs are now mounted read-only (`:ro`) instead of the implicit read-write default, since surfmap never writes to its inputs
- Python dependencies needed only for local execution (`freesasa`, `numpy`, `pdb2pqr`, `requests`) are no longer installed by default; `pip install surfmap` alone is now enough to use `--docker` (only the `docker` CLI is required), use `pip install surfmap[local]` to run the computation pipeline locally [BREAKING CHANGE for local users: run `pip install surfmap[local]` instead of `pip install surfmap`]
- `surfmap.lib.core` (and its `numpy` dependency chain), and the `freesasa`-dependent imports in `extract_interface.py`/`write_pdb_interface.py`, are now imported lazily, only when actually running locally, so they are no longer required just to launch `--docker`
- README's install instructions now use a stable GitHub Releases URL (`.../releases/latest/download/surfmap-latest.tar.gz`), backed by a new `.github/workflows/release-assets.yml` CI workflow that publishes it on every release; installing no longer requires manually downloading an archive first or updating a version number in the docs
- README's "How to install SURFMAP" section is simplified: the recommended `pip install` command (with an inlined, optional `venv` isolated-environment setup) is now shown directly instead of behind a collapsed "Option 1" section, the previous "Option 2" (git-based install) is folded into the source/development install as a one-line alternative using `@master` (fixing the previously stale `@main`/`@v2.1.0` references), and the separate "Recommendation" section on third-party `virtualenv` usage is removed in favor of the inlined `venv` steps

### Fixed
- `parsePDBParticule()` in `Structure.py` no longer truncates shell particle serial numbers above 9999, which could make distinct shell points collide on the same identifier and overwrite each other's coordinates, leading to incorrect closest-atom assignments during map generation
- `DockerCLI` (`docker.py`) no longer forces `-it`, which made `--docker` fail with "the input device is not a TTY" when run non-interactively (scripts, CI, some editor terminals); a pseudo-tty is now only requested when stdin is actually a TTY
- `DockerCLI.run()` now returns the container's exit code, and `main()` in `surfmap.py`, `extract_interface.py` and `write_pdb_interface.py` propagates it via `sys.exit()`, instead of always exiting `0` regardless of failures inside the container
- `_check_docker_install()` in `parameters.py` now actually exits when docker is not found on the system, instead of printing a warning and continuing anyway
- input files mounted for `--docker` runs (e.g. `-pdb` and `-res`) no longer collide when they share the same basename from different host directories, by index-prefixing their container mount paths
- `surfmap/lib/parameters.py`: several validation error paths (missing/wrong-suffix `-pdb`, missing `-res` file, out-of-range `-rad`, invalid `-s` cellsize, missing local R/APBS/awk requirements) called bare `exit()`, which exits with code `0` even on error, making failures look like successes to scripts/CI. Now consistently `exit(1)`.
- `--docker` runs failed with a `PermissionError` on the bind-mounted input/output directories on any host whose invoking user isn't uid `1000` (e.g. CI runners, shared servers, secondary accounts) - the image's `surfmap` home directory (`/home/surfmap`) was created with the default `750` mode, which blocks *any* other uid from even traversing into it, independently of the mounted paths' own permissions. `Dockerfile` now opens up traversal (`chmod o+rx /home/surfmap`), and `DockerCLI` (`docker.py`) additionally ensures the output directory it creates is world-writable, so `--docker` works regardless of the invoking host user.
- Dockerfile's runtime stage requires APBS's binary distribution (`softwares/APBS-3.4.1.Linux`), which is intentionally untracked (see `.gitignore`) and wasn't available on a fresh CI checkout, breaking `development-ci.yml`'s Docker build. It now downloads the official APBS 3.4.1 Linux release archive before building (cached across runs via `actions/cache`), and applies the known `psize.py` `nsmall`/list-indexing fix (see i2bc/SURFMAP#18) so the CI-built image matches a correctly patched local build.


## [2.2.0] - 2024-05-14

MINOR release of SURFMAP - minor breaking changes

### Added
- command line option to set min/max values for the bfactor color scale (`--bfactor-min-value`, `--bfactor-max-value`)

### Changed
- change command line option to set max absolute value for electrostatics color scale [BREAKING CHANGE]
  - from `--color-max-val` to  `--elec-max-value`


## [2.1.0] - 2023-12-27

MINOR release of SURFMAP - no breaking changes

### Added
- command line option to set min/max values for the electrostatics color scale

### Patched
- change the Proline value in the Kyte and Doolittle scale (from 1.6 to -1.6)


## [2.0.0] - 2023-02-27

MAJOR release where SURFMAP has been completely restructured as a python package.

### Added
-  a new docker CLI handler
-  surfmap options `-pqr` and `-ff`
- `surfmap` executable command
- `extract_interface` utility script
- `write_pdb_bs` utility script
- MANIFEST.in
- examples for new utility scripts
- setup.py
- Dockerfile
- check for surfmap requirements (apbs, r)
- optional environment variable for surfmap image version
- logging with 3 verbose levels
- surfmap.log file as output
- multival_csv2pdb as binary

### Changed
- README
- LICENCE from GPL to MIT
- install process
- docker repository name
- pdb_to_xyzr from awk to python3
- copyright notices
- path-related instructions in R scripts
- `compute_shell.sh` from bash to a python function
- electrostatics computation as a python function
- version format

### Removed
- use of `surfmap.py`
- use of `run_surfmap.py`
- electrostatics computation from shell computation
- awk/nawk dependency
- unused JS scripts/packages

### Deprecated
- everything included in lower versions is now deprecated


## [1.5] - 2023-02-27








