"""Functional tests for the `surfmap` CLI run through `--docker`.

These tests exercise the real, end-to-end SURFMAP pipeline (R/APBS/pdb2pqr/
freesasa) by running the `surfmap` console entry point as a subprocess against
a pre-built docker image, and checking exit codes plus produced/removed
output files.

They are skipped automatically if `docker` is not installed, or if the target
image is not available locally. Point them at a specific image with:

    DOCKER_REPOSITORY=surfmap SURFMAP_DOCKER_VERSION=ci-test \
        python -m unittest discover -s surfmap/tests -p "tests_functional_docker.py" -v

(these are the same env vars read by `surfmap/__init__.py`). Build a matching
image first, e.g.:

    docker build -t surfmap:ci-test .
"""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from surfmap import PATH_TO_EXAMPLES, DOCKER_REPOSITORY, SURFMAP_DOCKER_VERSION

PDB_1G3N_A = PATH_TO_EXAMPLES / "1g3n_A.pdb"
PDB_1G3N_BINDING_SITES = PATH_TO_EXAMPLES / "1g3n_ABC_chain-A_bs.pdb"
RESIDUES_FILE = PATH_TO_EXAMPLES / "residues_to_map.txt"

IMAGE = f"{DOCKER_REPOSITORY}:{SURFMAP_DOCKER_VERSION}"


def _docker_available():
    return shutil.which("docker") is not None


def _image_available():
    if not _docker_available():
        return False
    result = subprocess.run(
        ["docker", "image", "inspect", IMAGE],
        capture_output=True,
    )
    return result.returncode == 0


_SKIP_REASON = (
    f"docker CLI not found" if not _docker_available()
    else f"docker image '{IMAGE}' not found locally; build it first, e.g. "
         f"`docker build -t {IMAGE} .` (override with the DOCKER_REPOSITORY / "
         f"SURFMAP_DOCKER_VERSION env vars)"
)


@unittest.skipUnless(_image_available(), _SKIP_REASON)
class BaseFunctionalDockerTest(unittest.TestCase):

    def setUp(self):
        self.outdir = tempfile.mkdtemp(prefix="surfmap-tests-functional-")

    def tearDown(self):
        shutil.rmtree(self.outdir, ignore_errors=True)

    def run_surfmap(self, *extra_args, pdb=PDB_1G3N_A):
        cmd = ["surfmap", "-pdb", str(pdb), "-d", self.outdir, "--docker", *extra_args]
        return subprocess.run(cmd, capture_output=True, text=True, timeout=600)

    def maps_dir(self):
        return Path(self.outdir) / "maps"

    def assertNoIntermediaryFiles(self):
        for name in ("shells", "matrices", "coord_lists", "tmp-elec"):
            self.assertFalse(
                (Path(self.outdir) / name).exists(),
                f"'{name}' should have been removed (no --keep)",
            )
        self.assertEqual(
            list(Path(self.outdir).glob("*_partlist.out")), [],
            "*_partlist.out files should have been removed (no --keep)",
        )

    def assertIntermediaryFilesKept(self):
        for name in ("shells", "matrices", "coord_lists"):
            self.assertTrue(
                (Path(self.outdir) / name).is_dir(),
                f"'{name}' should have been kept (--keep)",
            )
        self.assertNotEqual(
            list(Path(self.outdir).glob("*_partlist.out")), [],
            "at least one *_partlist.out file should have been kept (--keep)",
        )


class TestTomapAll(BaseFunctionalDockerTest):

    def test_tomap_all(self):
        result = self.run_surfmap("-tomap", "all")
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)

        pdfs = list(self.maps_dir().glob("*.pdf"))
        self.assertEqual(len(pdfs), 4, msg=f"expected 4 maps, got: {pdfs}")

        smoothed = Path(self.outdir) / "smoothed_matrices"
        self.assertTrue(smoothed.is_dir())
        self.assertTrue(list(smoothed.iterdir()))

        self.assertNoIntermediaryFiles()


class TestTomapElectrostatics(BaseFunctionalDockerTest):

    def test_tomap_electrostatics(self):
        result = self.run_surfmap("-tomap", "electrostatics")
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)

        # --docker mounts the input pdb as "0_<basename>" to avoid collisions
        # (surfmap/lib/docker.py), which becomes part of the pdb_id-derived
        # output filename, so match by suffix rather than a hardcoded prefix.
        pdfs = list(self.maps_dir().glob("*_electrostatics_map.pdf"))
        self.assertEqual(len(pdfs), 1, msg=list(self.maps_dir().glob("*")))

        self.assertNoIntermediaryFiles()


class TestTomapStickinessKeep(BaseFunctionalDockerTest):

    def test_tomap_stickiness_keep(self):
        result = self.run_surfmap("-tomap", "stickiness", "--keep")
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)

        # see the note in test_tomap_electrostatics about the "0_" prefix
        pdfs = list(self.maps_dir().glob("*_stickiness_map.pdf"))
        self.assertEqual(len(pdfs), 1, msg=list(self.maps_dir().glob("*")))

        smoothed = Path(self.outdir) / "smoothed_matrices"
        self.assertTrue(smoothed.is_dir())
        self.assertTrue(list(smoothed.iterdir()))

        self.assertIntermediaryFilesKept()


class TestTomapWithResidues(BaseFunctionalDockerTest):

    def test_tomap_stickiness_with_residues(self):
        result = self.run_surfmap("-tomap", "stickiness", "-res", str(RESIDUES_FILE))
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)

        pdfs = list(self.maps_dir().glob("*.pdf"))
        self.assertEqual(len(pdfs), 1, msg=f"expected 1 map, got: {pdfs}")


class TestTomapBindingSites(BaseFunctionalDockerTest):

    def test_tomap_binding_sites(self):
        result = self.run_surfmap("-tomap", "binding_sites", pdb=PDB_1G3N_BINDING_SITES)
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)

        pdfs = list(self.maps_dir().glob("*.pdf"))
        self.assertEqual(len(pdfs), 1, msg=f"expected 1 map, got: {pdfs}")


class TestInvalidInput(BaseFunctionalDockerTest):

    def test_tomap_invalid_value(self):
        result = self.run_surfmap("-tomap", "not_a_real_property")
        self.assertEqual(result.returncode, 1, msg=result.stdout + result.stderr)
        self.assertIn("not accepted", result.stdout + result.stderr)

    def test_pdb_missing_file(self):
        result = self.run_surfmap("-tomap", "stickiness", pdb="/no/such/file.pdb")
        self.assertEqual(result.returncode, 1, msg=result.stdout + result.stderr)


@unittest.skipUnless(_docker_available(), "docker CLI not found")
class TestVersionAndHelp(unittest.TestCase):
    """These don't need the docker image itself: -v/-h exit before any
    container is launched (see surfmap/lib/parameters.py: get_args)."""

    def test_version_flag(self):
        result = subprocess.run(["surfmap", "-v"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("SURFMAP", result.stdout)

    def test_help_flag(self):
        result = subprocess.run(["surfmap", "-h"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("usage", result.stdout.lower())


if __name__ == '__main__':
    unittest.main()
