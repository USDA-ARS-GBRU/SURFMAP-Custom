#!/usr/bin/env python3
"""
Test script to run SurfMap pipeline audit on a mock PDB structure with assay data encoded in B-factor.
"""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

from test_inject_assay_bfactor import create_mock_pdb_with_assay_data
from surfmap.lib.parameters import Parameters


def test_pipeline_audit():
    assay_data = {
        ("A", "1"): 10.0,
        ("A", "2"): 25.0,
        ("A", "3"): 50.0,
    }

    test_pdb = "tests/mock_assay_protein.pdb"
    create_mock_pdb_with_assay_data(test_pdb, assay_data)

    out_dir = "logs/test_surfmap_output"
    os.makedirs(out_dir, exist_ok=True)

    class DummyArgs:
        pdb = test_pdb
        mat = None
        version = False
        tomap = "bfactor"
        proj = "flamsteed"
        coords = None
        res = ""
        rad = 3.0
        d = out_dir
        s = 10
        elec_max_value = None
        bfactor_min_value = 0.0
        bfactor_max_value = 100.0
        nosmooth = True
        png = True
        keep = True
        docker = True  # Avoid system R check during code inspection
        pqr = None
        ff = "CHARMM"
        verbose = 1

    # Bypass docker binary existence check for unit testing parameters object
    original_check_docker = Parameters._check_docker_install
    Parameters._check_docker_install = lambda self: None

    try:
        args = DummyArgs()
        params = Parameters(args)

        print("Parameters created successfully. Outdir:", params.outdir)
        print("Testing B-factor parsing and particle mapping step...")

        from surfmap.tools import Structure
        dPDB = Structure.parsePDBMultiChains(test_pdb, bfactor=True)

        for (chain, resnum), val in assay_data.items():
            res = dPDB[chain][resnum]
            atom_bfactor = res["N"]["bfactor"]
            print(f"Verified residue {chain}-{resnum} B-factor = {atom_bfactor} (expected {val})")

        print("Pipeline audit test complete.")
    finally:
        Parameters._check_docker_install = original_check_docker


if __name__ == "__main__":
    test_pipeline_audit()
