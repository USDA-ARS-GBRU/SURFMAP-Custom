#!/usr/bin/env python3
"""
SURFMAP Hydra Wrapper & RGB Multichannel Map Generator

This script integrates custom microarray binding assays (IgE/IgG4 ratio) and
Biopython ShrakeRupley SASA calculations into standard PDB B-factor fields,
executes SURFMAP projections for Red, Green, and Blue channels, crops plot
axes/legends, and merges the single-channel projections into a clean 256x256
RGB multichannel surface projection map.
"""

import hashlib
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any

import cv2
import hydra
from omegaconf import DictConfig, OmegaConf
import numpy as np
import pandas as pd
from Bio.PDB import PDBParser
from Bio.PDB.SASA import ShrakeRupley

# Ensure surfmap modules can be imported
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from surfmap.tools import Structure
from surfmap.lib.parameters import Parameters
from surfmap.lib.core import surfmap_from_pdb
from surfmap.lib.logs import addLoggingLevel

try:
    addLoggingLevel('TRACE', logging.DEBUG - 5)
except AttributeError:
    pass


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("surfmap_hydra_wrapper")


class RefusalException(Exception):
    """Exception raised when a mandatory refusal condition is met."""
    def __init__(self, payload: Dict[str, Any]):
        super().__init__(json.dumps(payload))
        self.payload = payload


def emit_refusal(
    reason_code: str,
    trigger: str,
    trace_id: str,
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


def check_forbidden_path(file_path: str, trace_id: str):
    """Ensures no write operation is directed toward data/ or unauthorized locations."""
    path = Path(file_path).resolve()
    # Check if target path is inside data/
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


def extract_pdb_residues(pdb_path: str) -> List[Tuple[str, str]]:
    """
    Extracts ordered list of (chain_id, res_id) tuples for standard amino acid residues.
    """
    if not os.path.exists(pdb_path):
        return []
    parser = PDBParser(QUIET=True)
    structure = parser.get_structure("protein", pdb_path)
    residues = []
    for model in structure:
        for chain in model:
            for res in chain:
                if res.id[0] == " ":  # Standard residue
                    residues.append((chain.id, str(res.id[1])))
    return residues


def parse_and_validate_microarray(
    csv_path: str,
    target_protein: str,
    residue_list: List[Tuple[str, str]],
    trace_id: str
) -> Dict[Tuple[str, str], float]:
    """
    Reads and filters microarray CSV data for target_protein, parses peptide_number and chip_number,
    extracts f_normexp for IgE and IgG4, validates shape consistency, applies 15-mer convolution smoothing,
    and returns a dictionary mapping (chain, resnum) to the smoothed IgE/IgG4 ratio.
    """
    if not os.path.exists(csv_path):
        emit_refusal(
            reason_code="INPUT_MISSING",
            trigger=f"Microarray CSV dataset missing at path: {csv_path}",
            trace_id=trace_id,
            handoff_payload={"csv_path": csv_path}
        )

    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        emit_refusal(
            reason_code="INPUT_MISSING",
            trigger=f"Failed to read microarray CSV at {csv_path}: {str(e)}",
            trace_id=trace_id,
            handoff_payload={"csv_path": csv_path}
        )

    protein_col = "protein" if "protein" in df.columns else ("target_protein" if "target_protein" in df.columns else None)
    if protein_col is None:
        emit_refusal(
            reason_code="INPUT_MISSING",
            trigger="Microarray CSV missing protein identifier column ('protein' or 'target_protein')",
            trace_id=trace_id
        )

    df_filtered = df[df[protein_col] == target_protein]
    if df_filtered.empty:
        emit_refusal(
            reason_code="INPUT_MISSING",
            trigger=f"Microarray CSV contains no data for target protein '{target_protein}'",
            trace_id=trace_id,
            handoff_payload={"target_protein": target_protein, "available_proteins": list(df[protein_col].unique())}
        )

    # Validate numeric types
    df_filtered = df_filtered.copy()
    df_filtered["peptide_number"] = df_filtered["peptide_number"].astype(int)
    df_filtered["chip_number"] = df_filtered["chip_number"].astype(str)

    # Separate IgE and IgG4
    ab_col = "antibody_type" if "antibody_type" in df_filtered.columns else "antibody"
    df_ige = df_filtered[df_filtered[ab_col] == "IgE"].sort_values("peptide_number")
    df_igg4 = df_filtered[df_filtered[ab_col] == "IgG4"].sort_values("peptide_number")

    ige_values = df_ige["f_normexp"].values.astype(float)
    igg4_values = df_igg4["f_normexp"].values.astype(float)

    seq_len = len(residue_list)
    if len(ige_values) != seq_len or len(igg4_values) != seq_len:
        emit_refusal(
            reason_code="UNSAFE_EXECUTION",
            trigger=f"Microarray shape mismatch: IgE len={len(ige_values)}, IgG4 len={len(igg4_values)}, expected PDB sequence len={seq_len}",
            trace_id=trace_id,
            handoff_payload={"ige_len": len(ige_values), "igg4_len": len(igg4_values), "seq_len": seq_len}
        )

    # Apply 15-mer convolution smoothing
    smoothed_ige = smooth_all_channels(ige_values, window_size=15)
    smoothed_igg4 = smooth_all_channels(igg4_values, window_size=15)

    # Compute IgE/IgG4 ratio with epsilon to avoid division by zero
    ratio_values = smoothed_ige / (smoothed_igg4 + 1e-6)

    # Map ratio to PDB residues
    ratio_dict = {}
    for idx, key in enumerate(residue_list):
        ratio_dict[key] = float(ratio_values[idx])

    return ratio_dict


def compute_sasa_biopython(
    pdb_path: str,
    residue_list: List[Tuple[str, str]],
    trace_id: str
) -> Dict[Tuple[str, str], float]:
    """
    Computes residue Solvent Accessible Surface Area (SASA) using Biopython ShrakeRupley.
    Validates output shape against structure residue count.
    """
    if not os.path.exists(pdb_path):
        emit_refusal(
            reason_code="INPUT_MISSING",
            trigger=f"PDB structure file missing at path: {pdb_path}",
            trace_id=trace_id,
            handoff_payload={"pdb_path": pdb_path}
        )

    try:
        parser = PDBParser(QUIET=True)
        structure = parser.get_structure("protein", pdb_path)
        sr = ShrakeRupley()
        sr.compute(structure, level="R")
    except Exception as e:
        emit_refusal(
            reason_code="UNSAFE_EXECUTION",
            trigger=f"Biopython ShrakeRupley SASA calculation failed: {str(e)}",
            trace_id=trace_id
        )

    sasa_dict = {}
    for model in structure:
        for chain in model:
            for res in chain:
                if res.id[0] == " ":
                    key = (chain.id, str(res.id[1]))
                    sasa_dict[key] = float(res.sasa) if hasattr(res, "sasa") else 0.0

    if len(sasa_dict) != len(residue_list):
        emit_refusal(
            reason_code="UNSAFE_EXECUTION",
            trigger=f"SASA calculation returned invalid array length: got {len(sasa_dict)}, expected {len(residue_list)}",
            trace_id=trace_id,
            handoff_payload={"sasa_len": len(sasa_dict), "seq_len": len(residue_list)}
        )

    return sasa_dict


def inject_bfactor_to_pdb(
    input_pdb: str,
    output_pdb: str,
    bfactor_dict: Dict[Tuple[str, str], float],
    trace_id: str
):
    """
    Injects custom floating point scalar values into the B-factor column (cols 61-66, F6.2 format)
    of a PDB file.
    """
    check_forbidden_path(output_pdb, trace_id)
    os.makedirs(os.path.dirname(output_pdb), exist_ok=True)

    lines = []
    with open(input_pdb, "r") as f:
        for line in f:
            if line.startswith("ATOM") or line.startswith("HETATM"):
                chain = line[21]
                resnum = line[22:26].strip()
                key = (chain, resnum)
                val = bfactor_dict.get(key, 0.0)

                # Format in F6.2 format for columns 61-66 (line[60:66])
                val_str = f"{val:6.2f}"
                if len(val_str) > 6:
                    val_str = " 99.99" if val > 0 else "-99.99"

                new_line = f"{line[:60]}{val_str}{line[66:]}"
                lines.append(new_line)
            else:
                lines.append(line)

    with open(output_pdb, "w") as f:
        f.writelines(lines)


def run_surfmap_cmd(
    pdb_path: str,
    tomap: str,
    out_dir: str,
    trace_id: str,
    bfactor_min: Optional[float] = None,
    bfactor_max: Optional[float] = None
) -> str:
    """
    Executes SURFMAP computation pipeline for a specified PDB structure and feature target.
    """
    check_forbidden_path(out_dir, trace_id)
    os.makedirs(out_dir, exist_ok=True)

    class CLIArgs:
        def __init__(self):
            self.pdb = pdb_path
            self.mat = None
            self.version = False
            self.tomap = tomap
            self.proj = "flamsteed"
            self.coords = None
            self.res = ""
            self.rad = 3.0
            self.d = out_dir
            self.s = 5
            self.elec_max_value = None
            self.bfactor_min_value = bfactor_min
            self.bfactor_max_value = bfactor_max
            self.nosmooth = False
            self.png = True
            self.keep = False
            self.docker = False
            self.pqr = None
            self.ff = "CHARMM"
            self.verbose = 1

    try:
        args = CLIArgs()
        params = Parameters(args)
        surfmap_from_pdb(params, with_copyright=False)
    except Exception as e:
        emit_refusal(
            reason_code="UNSAFE_EXECUTION",
            trigger=f"SURFMAP execution failed for target '{tomap}': {str(e)}",
            trace_id=trace_id,
            handoff_payload={"pdb_path": pdb_path, "tomap": tomap}
        )

    pdb_stem = Path(pdb_path).stem
    map_png = Path(out_dir) / "maps" / f"{pdb_stem}_{tomap}_map.png"
    if not map_png.exists():
        emit_refusal(
            reason_code="UNSAFE_EXECUTION",
            trigger=f"SURFMAP failed to produce output PNG map at expected path: {map_png}",
            trace_id=trace_id
        )

    return str(map_png)


def crop_surfmap_plot(image_path: str) -> np.ndarray:
    """
    Reads a SURFMAP output PNG image, detects the main projection map bounding box,
    crops it (excluding axes, titles, and legends), and returns the cropped BGR image array.
    """
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Could not load image file: {image_path}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 250, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    candidates = []
    img_h, img_w = gray.shape
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if w > img_w * 0.3 and h > img_h * 0.2:
            aspect = w / float(h)
            if 1.4 <= aspect <= 2.5:
                candidates.append((x, y, w, h))

    if candidates:
        candidates.sort(key=lambda b: b[2] * b[3], reverse=True)
        x, y, w, h = candidates[0]
    else:
        x, y, w, h = int(img_w * 0.127), int(img_h * 0.264), int(img_w * 0.639), int(img_h * 0.339)

    cropped = img[y:y+h, x:x+w]
    return cropped


def crop_and_merge_multichannel_rgb(
    red_map_path: str,
    green_map_path: str,
    blue_map_path: str,
    output_path: str,
    trace_id: str,
    target_size: Tuple[int, int] = (256, 256)
) -> str:
    """
    Crops individual single-channel maps, converts them to single-channel intensity,
    resizes to target_size (256x256), and merges into a 3-channel RGB image.
    """
    check_forbidden_path(output_path, trace_id)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    try:
        crop_r = crop_surfmap_plot(red_map_path)
        crop_g = crop_surfmap_plot(green_map_path)
        crop_b = crop_surfmap_plot(blue_map_path)

        gray_r = cv2.cvtColor(crop_r, cv2.COLOR_BGR2GRAY)
        gray_g = cv2.cvtColor(crop_g, cv2.COLOR_BGR2GRAY)
        gray_b = cv2.cvtColor(crop_b, cv2.COLOR_BGR2GRAY)

        res_r = cv2.resize(gray_r, target_size, interpolation=cv2.INTER_AREA)
        res_g = cv2.resize(gray_g, target_size, interpolation=cv2.INTER_AREA)
        res_b = cv2.resize(gray_b, target_size, interpolation=cv2.INTER_AREA)

        # Merge Red (Ch0), Green (Ch1), Blue (Ch2) into RGB
        rgb_img = np.dstack([res_r, res_g, res_b])

        # Write image using OpenCV (OpenCV expects BGR format)
        bgr_img = cv2.cvtColor(rgb_img, cv2.COLOR_RGB2BGR)
        cv2.imwrite(output_path, bgr_img)
    except Exception as e:
        emit_refusal(
            reason_code="UNSAFE_EXECUTION",
            trigger=f"Failed to crop or merge single-channel maps into RGB image: {str(e)}",
            trace_id=trace_id
        )

    if not os.path.exists(output_path):
        emit_refusal(
            reason_code="UNSAFE_EXECUTION",
            trigger=f"Merged multichannel RGB image not found at path: {output_path}",
            trace_id=trace_id
        )

    return output_path


def create_evidence_transcript(
    session_id: str,
    trace_id: str,
    events: List[Dict[str, Any]]
) -> Tuple[str, str]:
    """
    Saves JSONL session transcript to docs/agent_transcripts/jules/jules_{session_id}.json
    and SHA256 checksum to docs/agent_transcripts/jules/jules_{session_id}.json.sha256.
    """
    transcript_dir = Path("docs/agent_transcripts/jules")
    check_forbidden_path(str(transcript_dir), trace_id)
    transcript_dir.mkdir(parents=True, exist_ok=True)

    transcript_path = transcript_dir / f"jules_{session_id}.json"
    checksum_path = transcript_dir / f"jules_{session_id}.json.sha256"

    with open(transcript_path, "w") as f:
        for ev in events:
            ev_with_trace = {"trace_id": trace_id, "timestamp": time.time(), **ev}
            f.write(json.dumps(ev_with_trace) + "\n")

    hasher = hashlib.sha256()
    with open(transcript_path, "rb") as f:
        hasher.update(f.read())
    sha256_hash = hasher.hexdigest()

    with open(checksum_path, "w") as f:
        f.write(f"{sha256_hash}  {transcript_path.name}\n")

    return str(transcript_path), str(checksum_path)


def run_pipeline(cfg: DictConfig) -> str:
    """Runs the complete SURFMAP Hydra wrapper pipeline."""
    c = cfg.image_creation
    trace_id = c.get("trace_id", "trace_surfmap_hydra_default")
    session_id = f"session_{int(time.time())}"
    events = []

    events.append({"event": "pipeline_start", "protein": c.protein, "pdb_path": c.pdb_path})

    # Step 1: Extract PDB residue sequence
    residues = extract_pdb_residues(c.pdb_path)
    if not residues:
        emit_refusal(
            reason_code="INPUT_MISSING",
            trigger=f"Could not parse standard residues from PDB structure at {c.pdb_path}",
            trace_id=trace_id
        )

    # Step 2: Parse Microarray & compute IgE/IgG4 ratio
    csv_path = c.microarray.data_file.file_path
    ratio_dict = parse_and_validate_microarray(csv_path, c.protein, residues, trace_id)
    events.append({"event": "microarray_ratio_computed", "residue_count": len(ratio_dict)})

    # Step 3: Compute Biopython SASA
    sasa_dict = compute_sasa_biopython(c.pdb_path, residues, trace_id)
    events.append({"event": "sasa_computed", "residue_count": len(sasa_dict)})

    # Step 4: Inject B-factors into temporary scratch PDBs
    scratch_dir = Path(c.temp_dir)
    check_forbidden_path(str(scratch_dir), trace_id)
    scratch_dir.mkdir(parents=True, exist_ok=True)

    ratio_pdb = str(scratch_dir / "temp_ratio.pdb")
    sasa_pdb = str(scratch_dir / "temp_sasa.pdb")

    inject_bfactor_to_pdb(c.pdb_path, ratio_pdb, ratio_dict, trace_id)
    inject_bfactor_to_pdb(c.pdb_path, sasa_pdb, sasa_dict, trace_id)
    events.append({"event": "temp_pdbs_injected", "ratio_pdb": ratio_pdb, "sasa_pdb": sasa_pdb})

    # Step 5: Execute SURFMAP projections for Channels 0, 1, 2
    out_dir = Path(c.output_dir)
    red_dir = str(out_dir / "red_channel")
    green_dir = str(out_dir / "green_channel")
    blue_dir = str(out_dir / "blue_channel")

    red_map = run_surfmap_cmd(ratio_pdb, "bfactor", red_dir, trace_id)
    green_map = run_surfmap_cmd(c.pdb_path, "stickiness", green_dir, trace_id)
    blue_map = run_surfmap_cmd(sasa_pdb, "bfactor", blue_dir, trace_id)
    events.append({"event": "surfmap_projections_completed", "red_map": red_map, "green_map": green_map, "blue_map": blue_map})

    # Step 6: Crop & merge channels into 256x256 RGB image
    merged_output_path = str(out_dir / "merged_multichannel_256x256.png")
    final_rgb = crop_and_merge_multichannel_rgb(red_map, green_map, blue_map, merged_output_path, trace_id, target_size=(256, 256))
    events.append({"event": "rgb_merging_completed", "output_path": final_rgb})

    # Step 7: Create evidence transcript & SHA256 checksum
    t_path, c_path = create_evidence_transcript(session_id, trace_id, events)
    logger.info(f"Successfully generated merged 256x256 RGB image: {final_rgb}")
    logger.info(f"Saved transcript: {t_path}")
    logger.info(f"Saved SHA256 checksum: {c_path}")

    return final_rgb


@hydra.main(config_path="../config", config_name="config", version_base=None)
def main(cfg: DictConfig):
    try:
        run_pipeline(cfg)
    except RefusalException as re_err:
        logger.error("Pipeline terminated due to refusal condition.")
        sys.exit(1)


if __name__ == "__main__":
    main()
