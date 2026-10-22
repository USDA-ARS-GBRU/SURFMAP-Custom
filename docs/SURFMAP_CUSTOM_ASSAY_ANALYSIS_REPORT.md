# Technical Analysis Report: SurfMap Adaptation for Custom Per-Residue Assay Values

**Trace ID:** `trace_surfmap_assay_analysis_20260330_01`
**Author:** Jules (Bioinformatics Software Engineer & Structural Data Specialist)
**Target Package:** SurfMap (v2.2.1)
**Domain:** Structural Bioinformatics & 2D Surface Feature Mapping

---

## 1. Executive Summary

This technical report provides a comprehensive analysis of adapting **SurfMap** to project custom per-residue numeric assay binding values (e.g., binding affinities $K_d$, $\Delta G$, IC50, or normalized binding signals) onto 2D protein surface projections.

### Key Conclusions:
1. **PDB B-Factor Injection Feasibility**: Custom per-residue assay binding values can be directly encoded into the temperature factor/B-factor field (columns 61–66, floating-point format `F6.2`) of a standard PDB structure. Running `surfmap -pdb <file.pdb> -tomap bfactor` natively reads and projects these scalar values without requiring modifications to underlying surface utilities (MSMS or FreeSASA).
2. **Color Scale & Smoothing Control**: SurfMap's built-in scaling options (`--bfactor-min-value`, `--bfactor-max-value`, and `--nosmooth`) apply seamlessly to assay binding data.
3. **Custom Property Key & External Matrix Support**:
   - Custom scalar keys (e.g., `-tomap assay_binding`) can be supported by expanding `Parameters.ALLOWED_PROPERTIES` and configuring default routing to B-factor parsing.
   - External text-based matrix overrides (`.txt` files formatted with `absc`, `ord`, `value`, `residues`) are natively supported via the `-mat` option (`surfmap -mat <matrix.txt> -tomap bfactor`), bypassing surface generation when pre-calculated 2D grid values are available.

---

## 2. PDB Temperature Factor Field Validation & Ingestion

### Standard PDB Format Specification
According to standard PDB ATOM record formatting:
* **Columns 61–66** (character indices `60:66` / string slice `line[60:67]` in Python): Temperature factor / B-factor field.
* **Format**: Floating-point number in `F6.2` format (e.g., ` 12.50`, `-10.20`, ` 99.99`).

### Python B-Factor Ingestion Mechanism
SurfMap's PDB parsing routines (`surfmap/tools/Structure.py` -> `parsePDBMultiChains`) extract B-factors as follows:
```python
# From surfmap/tools/Structure.py
if bfactor:
    try:
        dPDB[chain][curres][atomtype]["bfactor"] = float(line[60:67].strip())
    except ValueError:
        dPDB[chain][curres][atomtype]["bfactor"] = 0
```

### Ingestion Script Helper
To inject per-residue assay binding data into a PDB file prior to running SurfMap, each atom of a residue is assigned that residue's assay value in columns 61–66:

```python
def inject_assay_data_to_pdb(input_pdb: str, output_pdb: str, assay_dict: dict):
    """
    assay_dict mapping: { (chain_id, res_id): float_assay_value }
    """
    lines = []
    with open(input_pdb, "r") as f:
        for line in f:
            if line.startswith("ATOM") or line.startswith("HETATM"):
                chain = line[21]
                resnum = line[22:26].strip()
                key = (chain, resnum)
                assay_val = assay_dict.get(key, 0.0)

                # Reconstruct line preserving exact column layout with F6.2 bfactor
                new_line = f"{line[:60]}{assay_val:6.2f}{line[66:]}"
                lines.append(new_line)
            else:
                lines.append(line)

    with open(output_pdb, "w") as f:
        f.writelines(lines)
```

---

## 3. Codebase Pipeline & Surface Analysis

SurfMap processes custom B-factor encoded assay values through a 5-step pipeline:

```
[ Input PDB with Assay B-Factors ]
               │
               ▼
   1. MSMS Surface Generation (compute_shell.py)
      -> Generates Solvent Excluded Surface (SES) shell particles.
               │
               ▼
   2. Particle Property Assignment (SurfmapTools.py: run_particles_mapping)
      -> Assigns closest atom's B-factor (assay value) to each shell particle.
      -> Calculates spherical coordinates (phi, theta) relative to receptor CM.
               │
               ▼
   3. 2D Coordinate Projection (computeCoordList.R)
      -> Projects (phi, theta) to 2D Flamsteed/Mollweide/Lambert grid.
               │
               ▼
   4. Matrix Aggregation & Smoothing (computeMatrices.R)
      -> Averages or picks max value per grid cell.
      -> Applies spatial neighbor smoothing (disabled via --nosmooth).
               │
               ▼
   5. Map & Scale Rendering (computeMaps.R)
      -> Generates 2D map PDF/PNG with custom color scales (--bfactor-min-value / --bfactor-max-value).
```

### Compatibility with MSMS & FreeSASA
* **MSMS** calculates surface shell particles solely from atomic 3D coordinates $(x, y, z)$ and atomic radii.
* **FreeSASA** calculates solvent-accessible surface areas from coordinates and radii.
* Neither utility relies on or modifies the B-factor column. Therefore, injecting assay binding values into columns 61–66 causes **zero regressions or side effects** in surface shell computation.

---

## 4. Custom Field, Header & Matrix Feasibility

### Custom Property Key Extension (`-tomap assay`)
Currently, `Parameters.ALLOWED_PROPERTIES` in `surfmap/lib/parameters.py` contains:
`["all", "stickiness", "kyte_doolittle", "wimley_white", "electrostatics", "circular_variance", "circular_variance_atom", "bfactor", "binding_sites"]`

To enable custom scalar feature names directly on the CLI (e.g., `surfmap -pdb protein.pdb -tomap assay`):
1. **Extend `ALLOWED_PROPERTIES`** in `surfmap/lib/parameters.py` to allow custom keys or dynamically fall back to B-factor mapping.
2. **Route Property in `SurfmapTools.py`**: When an unknown or custom property key is specified, default `property = "bfactor"`.
3. **Configure Title/Labels in `computeMaps.R`**: Accept a `--title` or custom scale label parameter.

### Text Matrix File Format (`.txt`)
When pre-computed 2D grid matrix data is available, SurfMap can bypass surface generation entirely:
```bash
surfmap -mat custom_matrix.txt -tomap bfactor --bfactor-min-value 0 --bfactor-max-value 100 --png
```
Expected matrix text file format (`tab-separated`):
```tsv
absc	ord	value	residues
10	10	12.50	A_1_ALA
10	20	25.00	A_1_ALA
...
```

---

## 5. Verification & Test Execution Artifacts

The following test suites were created and executed in `tests/`:
* `tests/test_inject_assay_bfactor.py`: Verified PDB B-factor injection and `Structure.parsePDBMultiChains` parsing (Status: PASSED).
* `tests/test_surfmap_pipeline_bfactor.py`: Verified parameter initialization, particle mapping, and B-factor extraction (Status: PASSED).
* `tests/test_custom_feature_matrix.py`: Verified matrix input reading (`-mat`) and custom scaling configuration (Status: PASSED).

**Execution Logs Location:** `logs/`
**Transcript Location:** `docs/agent_transcripts/jules/jules_session_20260330.json`
**Checksum Location:** `docs/agent_transcripts/jules/jules_session_20260330.json.sha256`
