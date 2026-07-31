"""Fast, hermetic unit tests for surfmap.lib.parameters.Parameters validation.

These tests do not require docker, R, APBS or any other external SURFMAP
requirement: `shutil.which` is patched so Parameters' own requirement checks
never actually depend on what is installed on the machine running the tests.
They only exercise Parameters' input-validation logic (and its exit codes).
"""
from argparse import Namespace
import shutil
import tempfile
import unittest
from unittest.mock import patch

from surfmap import PATH_TO_EXAMPLES
from surfmap.lib.parameters import Parameters

PDB_1G3N_A = str(PATH_TO_EXAMPLES / "1g3n_A.pdb")
RESIDUES_FILE = str(PATH_TO_EXAMPLES / "residues_to_map.txt")


def make_namespace(**overrides):
    base = dict(
        pdb=PDB_1G3N_A,
        mat=None,
        version=False,
        tomap='stickiness',
        proj='flamsteed',
        coords=None,
        res='',
        rad=3.0,
        s=5,
        elec_max_value=None,
        bfactor_min_value=None,
        bfactor_max_value=None,
        nosmooth=False,
        png=False,
        keep=False,
        docker=True,
        pqr=None,
        ff='CHARMM',
        verbose=1,
    )
    base.update(overrides)
    return Namespace(**base)


@patch('surfmap.lib.parameters.which', return_value='/usr/bin/true')
class TestParametersValidation(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="surfmap-tests-parameters-")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _namespace(self, **overrides):
        overrides.setdefault('d', self.tmpdir)
        return make_namespace(**overrides)

    def test_valid_args_do_not_raise(self, mock_which):
        Parameters(args=self._namespace())

    def test_invalid_tomap_exits_1(self, mock_which):
        with self.assertRaises(SystemExit) as ctx:
            Parameters(args=self._namespace(tomap='not_a_real_property'))
        self.assertEqual(ctx.exception.code, 1)

    def test_invalid_ff_exits_1(self, mock_which):
        with self.assertRaises(SystemExit) as ctx:
            Parameters(args=self._namespace(ff='NOT_A_FF'))
        self.assertEqual(ctx.exception.code, 1)

    def test_invalid_proj_exits_1(self, mock_which):
        with self.assertRaises(SystemExit) as ctx:
            Parameters(args=self._namespace(proj='not_a_proj'))
        self.assertEqual(ctx.exception.code, 1)

    def test_rad_too_low_exits_1(self, mock_which):
        with self.assertRaises(SystemExit) as ctx:
            Parameters(args=self._namespace(rad=0.1))
        self.assertEqual(ctx.exception.code, 1)

    def test_rad_too_high_exits_1(self, mock_which):
        with self.assertRaises(SystemExit) as ctx:
            Parameters(args=self._namespace(rad=20.0))
        self.assertEqual(ctx.exception.code, 1)

    def test_cellsize_not_multiple_of_180_exits_1(self, mock_which):
        with self.assertRaises(SystemExit) as ctx:
            Parameters(args=self._namespace(s=7))
        self.assertEqual(ctx.exception.code, 1)

    def test_cellsize_too_large_exits_1(self, mock_which):
        with self.assertRaises(SystemExit) as ctx:
            Parameters(args=self._namespace(s=180))
        self.assertEqual(ctx.exception.code, 1)

    def test_missing_res_file_exits_1(self, mock_which):
        with self.assertRaises(SystemExit) as ctx:
            Parameters(args=self._namespace(res='/no/such/residues.txt'))
        self.assertEqual(ctx.exception.code, 1)

    def test_valid_res_file_does_not_raise(self, mock_which):
        Parameters(args=self._namespace(res=RESIDUES_FILE))

    def test_missing_pdb_file_exits_1(self, mock_which):
        with self.assertRaises(SystemExit) as ctx:
            Parameters(args=self._namespace(pdb='/no/such/file.pdb'))
        self.assertEqual(ctx.exception.code, 1)

    def test_pdb_wrong_suffix_exits_1(self, mock_which):
        with self.assertRaises(SystemExit) as ctx:
            Parameters(args=self._namespace(pdb=RESIDUES_FILE))
        self.assertEqual(ctx.exception.code, 1)

    def test_docker_not_installed_exits_1(self, mock_which):
        mock_which.return_value = None
        with self.assertRaises(SystemExit) as ctx:
            Parameters(args=self._namespace())
        self.assertEqual(ctx.exception.code, 1)

    def test_local_requirement_not_installed_exits_1(self, mock_which):
        mock_which.return_value = None
        with self.assertRaises(SystemExit) as ctx:
            Parameters(args=self._namespace(docker=False))
        self.assertEqual(ctx.exception.code, 1)


if __name__ == '__main__':
    unittest.main()
