#!/usr/bin/env python3
"""
Unit tests for src/smooth_data.py
"""

import os
import pickle
import sys
import numpy as np
import pandas as pd
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.smooth_data import (
    smooth_all_channels,
    check_forbidden_path,
    load_and_preprocess_microarray,
    process_and_smooth_data,
    RefusalException,
)


def test_smooth_all_channels():
    arr = np.array([1.0, 20.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0])
    smoothed = smooth_all_channels(arr, window_size=5)
    assert len(smoothed) == len(arr)
    # Peak at index 1 should be smoothed down significantly
    assert smoothed[1] < 20.0


def test_check_forbidden_path():
    trace_id = "test_trace_forbidden"
    with pytest.raises(RefusalException) as exc_info:
        check_forbidden_path("data/forbidden_output.pkl", trace_id)
    assert exc_info.value.payload["reason_code"] == "FORBIDDEN_MUTATION"


def test_process_and_smooth_data(tmp_path):
    # Create test CSV fixture
    csv_file = str(tmp_path / "test_fixture.csv")
    out_pkl = str(tmp_path / "plots/smoothed_out.pkl")

    peptides = np.arange(1, 16)
    ige_vals = np.ones(15) * 10.0
    igg4_vals = np.ones(15) * 2.0

    lines = []
    for p, v in zip(peptides, ige_vals):
        lines.append(f"ARA_H_2,{p},3490-109,IgE,{v}\n")
    for p, v in zip(peptides, igg4_vals):
        lines.append(f"ARA_H_2,{p},3490-109,IgG4,{v}\n")

    with open(csv_file, "w") as f:
        f.writelines(lines)

    res_dict = process_and_smooth_data(csv_file, out_pkl, window_size=5, trace_id="test_smooth_trace")

    assert os.path.exists(out_pkl)
    assert res_dict["protein"] == "ARA_H_2"
    assert res_dict["chip_number"] == "3490-109"
    assert len(res_dict["ige_smoothed"]) == 15
    assert len(res_dict["igg4_smoothed"]) == 15
    assert len(res_dict["ratio_smoothed"]) == 15

    # Check unpickling
    with open(out_pkl, "rb") as f:
        loaded = pickle.load(f)
    assert loaded["protein"] == "ARA_H_2"


def test_missing_csv_refusal():
    with pytest.raises(RefusalException) as exc_info:
        process_and_smooth_data("non_existent_file.csv", "plots/out.pkl")
    assert exc_info.value.payload["reason_code"] == "INPUT_MISSING"
