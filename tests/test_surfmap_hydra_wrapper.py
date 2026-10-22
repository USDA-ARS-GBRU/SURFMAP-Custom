#!/usr/bin/env python3
"""
Unit and Integration Tests for SURFMAP Hydra Wrapper & RGB Multichannel Map Generator
"""

import os
import sys
import json
import numpy as np
import pandas as pd
import pytest
from pathlib import Path
from omegaconf import OmegaConf, DictConfig

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.surfmap_hydra_wrapper import (
    smooth_all_channels,
    extract_pdb_residues,
    parse_and_validate_microarray,
    compute_sasa_biopython,
    inject_bfactor_to_pdb,
    crop_surfmap_plot,
    crop_and_merge_multichannel_rgb,
    check_forbidden_path,
    run_pipeline,
    RefusalException,
)
from surfmap.tools import Structure


def test_smooth_all_channels():
    arr = np.array([1.0, 10.0, 1.0, 1.0, 1.0, 20.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0])
    smoothed = smooth_all_channels(arr, window_size=5)
    assert len(smoothed) == len(arr)
    # Confirm spike smoothing effect
    assert smoothed[1] < 10.0


def test_extract_pdb_residues():
    pdb_path = "surfmap/examples/1g3n_A.pdb"
    residues = extract_pdb_residues(pdb_path)
    assert len(residues) == 293
    assert residues[0] == ("A", "9")


def test_parse_and_validate_microarray(tmp_path):
    csv_path = "tests/mock_microarray.csv"
    residues = extract_pdb_residues("surfmap/examples/1g3n_A.pdb")
    trace_id = "test_trace_01"

    ratio_dict = parse_and_validate_microarray(csv_path, "1g3n_A", residues, trace_id)
    assert len(ratio_dict) == 293
    assert ("A", "9") in ratio_dict
    assert isinstance(ratio_dict[("A", "9")], float)

    # Test refusal on missing CSV
    with pytest.raises(RefusalException) as exc_info:
        parse_and_validate_microarray("non_existent.csv", "1g3n_A", residues, trace_id)
    assert exc_info.value.payload["reason_code"] == "INPUT_MISSING"

    # Test refusal on missing protein in CSV
    with pytest.raises(RefusalException) as exc_info:
        parse_and_validate_microarray(csv_path, "NON_EXISTENT_PROTEIN", residues, trace_id)
    assert exc_info.value.payload["reason_code"] == "INPUT_MISSING"

    # Test refusal on sequence shape mismatch
    short_residues = residues[:10]
    with pytest.raises(RefusalException) as exc_info:
        parse_and_validate_microarray(csv_path, "1g3n_A", short_residues, trace_id)
    assert exc_info.value.payload["reason_code"] == "UNSAFE_EXECUTION"


def test_compute_sasa_biopython():
    pdb_path = "surfmap/examples/1g3n_A.pdb"
    residues = extract_pdb_residues(pdb_path)
    trace_id = "test_trace_sasa"

    sasa_dict = compute_sasa_biopython(pdb_path, residues, trace_id)
    assert len(sasa_dict) == 293
    assert ("A", "9") in sasa_dict
    assert sasa_dict[("A", "9")] > 0.0


def test_inject_bfactor_to_pdb(tmp_path):
    input_pdb = "surfmap/examples/1g3n_A.pdb"
    output_pdb = str(tmp_path / "plots/test_inject.pdb")
    trace_id = "test_trace_inject"

    assay_data = {("A", "9"): 45.67, ("A", "10"): 12.34}
    inject_bfactor_to_pdb(input_pdb, output_pdb, assay_data, trace_id)

    assert os.path.exists(output_pdb)
    # Parse back with SurfMap Structure parser
    dPDB = Structure.parsePDBMultiChains(output_pdb, bfactor=True)
    val_9 = dPDB["A"]["9"]["N"]["bfactor"]
    assert abs(val_9 - 45.67) < 1e-2


def test_check_forbidden_path():
    trace_id = "test_trace_forbidden"
    with pytest.raises(RefusalException) as exc_info:
        check_forbidden_path("data/forbidden_output.pdb", trace_id)
    assert exc_info.value.payload["reason_code"] == "FORBIDDEN_MUTATION"


def test_end_to_end_pipeline(tmp_path):
    out_dir = str(tmp_path / "plots")
    temp_dir = str(tmp_path / "scratch")

    cfg = OmegaConf.create({
        "image_creation": {
            "protein": "1g3n_A",
            "pdb_path": "surfmap/examples/1g3n_A.pdb",
            "microarray": {
                "data_file": {
                    "file_path": "tests/mock_microarray.csv"
                }
            },
            "output_dir": out_dir,
            "temp_dir": temp_dir,
            "trace_id": "test_e2e_trace_2026"
        }
    })

    merged_img_path = run_pipeline(cfg)
    assert os.path.exists(merged_img_path)

    # Verify image properties
    import cv2
    img = cv2.imread(merged_img_path)
    assert img is not None
    assert img.shape == (256, 256, 3)
