# Contributing to SURFMAP

This document describes the branching model, how to run the test suite
locally, what the CI workflows do, and the full release process (including
the manual Docker Hub step CI does **not** automate yet).

## Branching model

- `development`: integration branch. All feature/fix work targets this
  branch (directly or via PR).
- `master`: stable, released branch. README's install instructions point
  here (`@master`). Nothing should be pushed to `master` directly - it is
  updated automatically by CI (see [Release process](#release-process)
  below) whenever `development` is green and its version was bumped.

## Running tests locally

Two independent test suites live under `surfmap/tests/`.

### 1. Fast unit tests (no docker/R/APBS required)

Validates `surfmap.lib.parameters.Parameters`' input handling (bad
`-tomap`/`-ff`/`-proj`/`-rad`/`-s`/`-res`/`-pdb` values, docker/R requirement
checks). Hermetic: `shutil.which` is patched so these never depend on what's
actually installed on your machine.

```bash
pip install -e .
python -m unittest discover -s surfmap/tests -p "tests_parameters.py" -v
```

### 2. Functional docker tests (real, end-to-end)

Runs the actual `surfmap` CLI through `--docker` against a locally-built
image, and checks exit codes plus produced/removed output files (including
`--keep` vs. non-`--keep` behavior). These are the tests that actually
exercise R/APBS/pdb2pqr/freesasa - `--help`-only smoke tests are **not**
sufficient (they previously missed a broken Docker image, see the
[CHANGELOG](CHANGELOG.md)).

```bash
# build the image from your current working tree first
docker build -t surfmap:ci-test .

# then point the tests at it (same env vars read by surfmap/__init__.py)
DOCKER_REPOSITORY=surfmap SURFMAP_DOCKER_VERSION=ci-test \
    python -m unittest discover -s surfmap/tests -p "tests_functional_docker.py" -v
```

These tests skip themselves cleanly (with an explanatory message) if
`docker` isn't installed or if the target image can't be found locally.

## CI workflows

### `.github/workflows/development-ci.yml`

Triggers on every push to `development`, and on pull requests targeting
`development`/`master`. Two jobs:

1. **`test`**: installs surfmap, runs the fast unit tests, builds the
   Dockerfile from the current commit (cached via the GitHub Actions cache
   backend, so it's not pulled from Docker Hub), and runs the functional
   tests against that freshly-built image.
2. **`release`** (only runs on a push to `development`, after `test` passes):
   reads the current version from `surfmap/__init__.py: __VERSION__`. If a
   git tag `vX.Y.Z` for that version doesn't already exist, it:
   - fast-forward pushes `development` to `master` (no `--force` - fails
     loudly instead of clobbering history if the two have diverged)
   - tags the pushed commit `vX.Y.Z`
   - creates a GitHub Release from that tag

   If the version was **not** bumped since the last release, this job's
   steps are skipped cleanly - not every green push to `development` is
   meant to become a release.

### `.github/workflows/release-assets.yml`

Triggers whenever a GitHub Release is published (which the `release` job
above does automatically, or via manual `workflow_dispatch` for backfills).
Builds a Python sdist and uploads it as a release asset twice: with its
natural versioned name (`surfmap-X.Y.Z.tar.gz`) and as a fixed
`surfmap-latest.tar.gz`, which is what the README's install instructions
link to.

**This workflow does not build or push a Docker image** - see the manual
step below.

## Release process

1. On `development`: bump `__VERSION__` in `surfmap/__init__.py` and add a
   dated entry to [CHANGELOG.md](CHANGELOG.md) describing the change
   (do this for every user-facing or behavioral code change, not just at
   release time - it keeps the release entry accurate and easy to write).
2. Push (or merge a PR) to `development`. If CI is green, it automatically
   pushes to `master`, tags `vX.Y.Z`, and creates a GitHub Release, which in
   turn triggers `release-assets.yml` to publish the sdist assets.
3. **Manual step - build and push the Docker image to Docker Hub.**
   `surfmap --docker` runs pull `${DOCKER_REPOSITORY}:${SURFMAP_DOCKER_VERSION}`
   (`surfmap/__init__.py`), which default to `lopesi2bc/surfmap:<__VERSION__>`
   (**no** `v` prefix - the Docker tag is the bare version string, unlike the
   git tag). None of the CI workflows above build or push this image; until
   you do this step, users who install the new pip release and run
   `--docker` will fail to pull the matching image tag. After step 2
   completes:

   ```bash
   VERSION=$(python setup.py --version)
   docker build -t lopesi2bc/surfmap:$VERSION -t lopesi2bc/surfmap:latest .
   docker push lopesi2bc/surfmap:$VERSION
   docker push lopesi2bc/surfmap:latest
   ```

   Requires push access to the `lopesi2bc/surfmap` Docker Hub repository.

   > **Possible future improvement**: this could be automated as a third CI
   > job triggered on `release: published`, using `docker/login-action` +
   > `docker/build-push-action` with `DOCKERHUB_USERNAME`/`DOCKERHUB_TOKEN`
   > repository secrets. Not implemented yet - left as a deliberate manual
   > gate for now.
