from argparse import Namespace
import unittest

from surfmap.lib.docker import DockerCLI


class BaseTest(unittest.TestCase):
    def setUp(self):
        self.namespace = Namespace(
            pdb='foo.pdb',
            mat=None,
            version=False,
            tomap='stickiness',
            proj='flamsteed',
            coords=None,
            res='',
            rad=3.0,
            d='output_SURFMAP_{}_{}',
            s=5,
            nosmooth=False,
            png=False,
            keep=False,
            docker=False,
            pqr=None,
            ff='CHARMM',
            verbose=1
        )


class TestDockerCLI(BaseTest):

    def test_create_fake_instance(self):
        self.assertTrue(self.namespace.pdb == "foo.pdb")

if __name__ == '__main__':
    unittest.main()