#!/usr/bin/env python3
"""
Test script for injecting custom per-residue assay binding values into the
B-factor column (columns 61-66) of a standard PDB structure and validating
parsing by SurfMap's Structure routines.
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from surfmap.tools import Structure


def create_mock_pdb_with_assay_data(output_pdb_path: str, assay_data: dict):
    """
    Creates a mock PDB file with custom assay values injected into the B-factor column.
    assay_data structure: { (chain_id, res_id): float_value }
    """
    residues = [
        ("A", "1", "ALA", [("N", 0.0, 0.0, 0.0), ("CA", 1.458, 0.0, 0.0), ("C", 2.009, 1.42, 0.0), ("O", 1.371, 2.378, 0.0)]),
        ("A", "2", "GLY", [("N", 3.327, 1.542, 0.0), ("CA", 3.992, 2.839, 0.0), ("C", 5.488, 2.715, 0.0), ("O", 6.096, 1.644, 0.0)]),
        ("A", "3", "VAL", [("N", 6.082, 3.822, 0.0), ("CA", 7.502, 3.854, 0.0), ("C", 8.084, 5.244, 0.0), ("O", 7.373, 6.241, 0.0)]),
    ]

    lines = []
    atom_id = 1
    for chain, resnum, resname, atoms in residues:
        key = (chain, resnum)
        assay_val = assay_data.get(key, 0.0)

        for atomname, x, y, z in atoms:
            # Standard PDB format (F6.2 across cols 61-66):
            line = f"ATOM  {atom_id:5d} {atomname:^4s} {resname:3s} {chain:1s}{int(resnum):4d}    {x:8.3f}{y:8.3f}{z:8.3f}  1.00{assay_val:6.2f}\n"
            lines.append(line)
            atom_id += 1

    os.makedirs(os.path.dirname(output_pdb_path), exist_ok=True)
    with open(output_pdb_path, "w") as f:
        f.writelines(lines)


def test_b_factor_injection():
    assay_data = {
        ("A", "1"): 12.50,
        ("A", "2"): -3.75,
        ("A", "3"): 88.10,
    }

    test_pdb_path = "tests/mock_assay_protein.pdb"
    create_mock_pdb_with_assay_data(test_pdb_path, assay_data)

    # Parse PDB using SurfMap's internal parser
    dPDB = Structure.parsePDBMultiChains(test_pdb_path, bfactor=True)

    # Verify extracted B-factor values match injected assay data
    for (chain, resnum), expected_val in assay_data.items():
        res_dict = dPDB[chain][resnum]
        for atomname in res_dict["atomlist"]:
            parsed_bfactor = res_dict[atomname][atomname]["bfactor"] if atomname in res_dict[atomname] else res_dict[atomname]["bfactor"]
            assert abs(parsed_bfactor - expected_val) < 1e-2, f"Mismatch for {chain}-{resnum}-{atomname}: expected {expected_val}, got {parsed_bfactor}"

    print(f"SUCCESS: Injecting and parsing assay values via B-factor column verified successfully for {test_pdb_path}.")


if __name__ == "__main__":
    test_b_factor_injection()
