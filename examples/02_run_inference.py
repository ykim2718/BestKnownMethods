"""
02_run_inference.py - Assign new wafers to known BKMs (or flag as unknown).

Equivalent CLI form:

    python -m bkm.generator \
        --data_folder examples/inference_data \
        --bkm_folder  examples/bkm_results \
        --bkm_file    bkm_directory.json

Without `--update`, the generator loads the registry written by 01_run_training.py
and assigns each wafer to a matching BKM. Wafers whose loaf-set has never been
seen are tagged "unknown".
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "inference_data"
BKM_DIR = HERE / "bkm_results"
BKM_FILE = "bkm_directory.json"


def main() -> None:
    if not DATA_DIR.is_dir() or not any(DATA_DIR.glob("*.parquet")):
        sys.exit(f"[ERROR] {DATA_DIR} is empty. Run 00_generate_sample_data.py first.")

    registry_path = BKM_DIR / BKM_FILE
    if not registry_path.is_file():
        sys.exit(
            f"[ERROR] {registry_path} not found.\n"
            f"        Run 01_run_training.py first to build the BKM registry."
        )

    cmd = [
        sys.executable, "-m", "bkm.generator",
        "--data_folder", str(DATA_DIR),
        "--bkm_folder",  str(BKM_DIR),
        "--bkm_file",    BKM_FILE,
    ]
    print("[02] $ " + " ".join(cmd))
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
