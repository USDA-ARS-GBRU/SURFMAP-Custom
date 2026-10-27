#!/usr/bin/env python3
"""
Microarray Signal Data Smoothing & Feature Extraction Script

This script ingests extracted microarray CSV datasets (e.g., test.csv), validates input
columns, applies 15-mer convolution smoothing across signal channels (IgE & IgG4),
computes normalized antibody ratio profiles, and outputs a pickled data dictionary
for downstream SURFMAP 2D surface projection rendering.
"""

import argparse
import json
import logging
import os
import pickle
import sys
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("smooth_data")


class RefusalException(Exception):
    """Raised when a mandatory refusal condition is met."""
    def __init__(self, payload: Dict[str, Any]):
        super().__init__(json.dumps(payload))
        self.payload = payload


def emit_refusal(
    reason_code: str,
    trigger: str,
    trace_id: str = "trace_smooth_data_default",
    escalation_target: str = "Bio-ML Engineer",
    retry_boundary: str = "Correct input files or parameters and retry",
    handoff_payload: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Generates and emits a structured refusal payload."""
    payload = {
        "reason_code": reason_code,
        "trigger": trigger,
        "escalation_target": escalation_target,
        "retry_boundary": retry_boundary,
        "handoff_payload": handoff_payload or {},
        "trace_id": trace_id
    }
    logger.error("EMITTING REFUSAL: %s", json.dumps(payload, indent=2))
    raise RefusalException(payload)


def check_forbidden_path(file_path: str, trace_id: str = "trace_smooth_data_default"):
    """Ensures no write operation is directed toward data/ or unauthorized locations."""
    path = Path(file_path).resolve()
    for parent in [path] + list(path.parents):
        if parent.name == "data":
            emit_refusal(
                reason_code="FORBIDDEN_MUTATION",
                trigger=f"Write operation attempted inside forbidden directory: {file_path}",
                trace_id=trace_id,
                handoff_payload={"attempted_path": str(file_path)}
            )


def smooth_all_channels(data_array: np.ndarray, window_size: int = 15) -> np.ndarray:
    """
    Applies 1D convolution smoothing across peptide binding signals to eliminate spikes.
    Uses a 15-mer box window kernel with mode='same' to preserve array length.
    """
    if len(data_array) == 0:
        return data_array
    kernel = np.ones(window_size) / float(window_size)
    smoothed = np.convolve(data_array, kernel, mode="same")
    return smoothed


def load_and_preprocess_microarray(
    csv_path: str,
    trace_id: str = "trace_smooth_data_default"
) -> Tuple[str, str, np.ndarray, np.ndarray, np.ndarray]:
    """
    Loads microarray data from csv_path (handling files with or without header),
    extracts protein name, chip ID, peptide numbers, and raw IgE/IgG4 signal channels.
    """
    if not os.path.exists(csv_path):
        emit_refusal(
            reason_code="INPUT_MISSING",
            trigger=f"Microarray input dataset missing at path: {csv_path}",
            trace_id=trace_id,
            handoff_payload={"csv_path": csv_path}
        )

    try:
        # Check if file has header or raw grep output
        df = pd.read_csv(csv_path, header=None)
        if df.empty:
            emit_refusal(
                reason_code="INPUT_MISSING",
                trigger=f"Microarray dataset at {csv_path} is empty",
                trace_id=trace_id
            )

        # Check if first row contains column headers
        first_row_vals = [str(v).lower() for v in df.iloc[0].values]
        if "protein" in first_row_vals or "antibody_type" in first_row_vals:
            df = pd.read_csv(csv_path)
            protein_col = "protein" if "protein" in df.columns else "target_protein"
            ab_col = "antibody_type" if "antibody_type" in df.columns else "antibody"
            pep_col = "peptide_number"
            chip_col = "chip_number"
            val_col = "f_normexp"
        else:
            # Unheadered grep output format
            df.columns = ["protein", "peptide_number", "chip_number", "antibody_type", "f_normexp"]
            protein_col = "protein"
            ab_col = "antibody_type"
            pep_col = "peptide_number"
            chip_col = "chip_number"
            val_col = "f_normexp"

    except Exception as e:
        emit_refusal(
            reason_code="INPUT_MISSING",
            trigger=f"Failed to parse microarray CSV at {csv_path}: {str(e)}",
            trace_id=trace_id,
            handoff_payload={"csv_path": csv_path}
        )

    df[pep_col] = df[pep_col].astype(int)
    protein_name = str(df[protein_col].iloc[0])
    chip_id = str(df[chip_col].iloc[0])

    df_ige = df[df[ab_col] == "IgE"].sort_values(pep_col)
    df_igg4 = df[(df[ab_col] == "IgG4") | (df[ab_col] == "IgG")].sort_values(pep_col)

    if df_ige.empty or df_igg4.empty:
        emit_refusal(
            reason_code="INPUT_MISSING",
            trigger=f"Microarray dataset missing required IgE or IgG4 channels for protein {protein_name}",
            trace_id=trace_id,
            handoff_payload={"ige_rows": len(df_ige), "igg4_rows": len(df_igg4)}
        )

    if len(df_ige) != len(df_igg4):
        emit_refusal(
            reason_code="UNSAFE_EXECUTION",
            trigger=f"IgE and IgG4 row count mismatch: IgE={len(df_ige)}, IgG4={len(df_igg4)}",
            trace_id=trace_id
        )

    peptide_numbers = df_ige[pep_col].values
    ige_raw = df_ige[val_col].values.astype(float)
    igg4_raw = df_igg4[val_col].values.astype(float)

    return protein_name, chip_id, peptide_numbers, ige_raw, igg4_raw


def process_and_smooth_data(
    input_csv: str,
    output_pickle: str,
    window_size: int = 15,
    trace_id: str = "trace_smooth_data_default"
) -> Dict[str, Any]:
    """
    Ingests input_csv, applies 15-mer box window smoothing, computes ratio, and pickles result dictionary.
    """
    check_forbidden_path(output_pickle, trace_id)

    protein_name, chip_id, peptide_numbers, ige_raw, igg4_raw = load_and_preprocess_microarray(input_csv, trace_id)

    ige_smoothed = smooth_all_channels(ige_raw, window_size=window_size)
    igg4_smoothed = smooth_all_channels(igg4_raw, window_size=window_size)

    # Compute IgE / IgG4 ratio with small epsilon
    ratio_smoothed = ige_smoothed / (igg4_smoothed + 1e-6)

    data_dict = {
        "protein": protein_name,
        "chip_number": chip_id,
        "peptide_numbers": peptide_numbers,
        "ige_raw": ige_raw,
        "igg4_raw": igg4_raw,
        "ige_smoothed": ige_smoothed,
        "igg4_smoothed": igg4_smoothed,
        "ratio_smoothed": ratio_smoothed,
        "window_size": window_size,
        "trace_id": trace_id
    }

    os.makedirs(os.path.dirname(output_pickle), exist_ok=True)
    with open(output_pickle, "wb") as f:
        pickle.dump(data_dict, f)

    logger.info("Successfully created smoothed data pickle file at: %s", output_pickle)
    return data_dict


def main():
    parser = argparse.ArgumentParser(description="Smooth microarray signal data and output pickled dictionary")
    parser.add_argument("--input", "-i", default="test.csv", help="Input extracted CSV file")
    parser.add_argument("--output", "-o", default="plots/smoothed_data.pkl", help="Output pickled dictionary file")
    parser.add_argument("--window", "-w", type=int, default=15, help="Smoothing kernel window size")
    parser.add_argument("--trace_id", default="trace_smooth_data_2026", help="Unique trace identifier")

    args = parser.parse_args()

    try:
        process_and_smooth_data(args.input, args.output, args.window, args.trace_id)
    except RefusalException:
        logger.error("Data smoothing process terminated due to refusal.")
        sys.exit(1)


if __name__ == "__main__":
    main()
