#!/usr/bin/env python3
"""
Test script to evaluate text matrix formatting and custom property parameter logic.
"""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from surfmap.lib.parameters import Parameters


def create_mock_matrix_file(matrix_path: str):
    """
    Creates a valid SurfMap matrix text file with header: absc, ord, value, residues
    """
    lines = ["absc\tord\tvalue\tresidues\n"]
    # Generate 5-degree grid cells (72 x 36)
    cellsize = 10
    for absc in range(cellsize, 360 + 1, cellsize):
        for ord_val in range(cellsize, 180 + 1, cellsize):
            val = round((absc * ord_val) / 100.0, 2)
            lines.append(f"{absc}\t{ord_val}\t{val}\tA_1_ALA\n")

    os.makedirs(os.path.dirname(matrix_path), exist_ok=True)
    with open(matrix_path, "w") as f:
        f.writelines(lines)


def test_matrix_input():
    matrix_path = "tests/mock_assay_matrix.txt"
    create_mock_matrix_file(matrix_path)

    out_dir = "logs/test_matrix_output"

    class DummyArgs:
        pdb = None
        mat = matrix_path
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
        docker = True
        pqr = None
        ff = "CHARMM"
        verbose = 1

    original_check_docker = Parameters._check_docker_install
    Parameters._check_docker_install = lambda self: None

    try:
        args = DummyArgs()
        params = Parameters(args)
        assert params.mat == matrix_path
        assert params.pdb_id == "mock_assay_matrix"
        print(f"SUCCESS: Matrix input test verified for {matrix_path}")
    finally:
        Parameters._check_docker_install = original_check_docker


if __name__ == "__main__":
    test_matrix_input()
