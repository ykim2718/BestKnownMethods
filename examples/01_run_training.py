"""
01_run_training.py - Build a BKM registry from synthetic wafers.

Equivalent CLI form:

    python -m bkm.generator --update \
        --data_folder examples/training_data \
        --bkm_folder  examples/bkm_results \
        --bkm_file    bkm_directory.json

(or simply `bkm-generator --update ...` if the console script is on PATH)

After training, also renders each BKM's DAG to a PNG and dumps the equivalent
Mermaid source (.mmd) under examples/bkm_results/diagrams/.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from bkm.generator import load_bkm_directory


HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "training_data"
BKM_DIR = HERE / "bkm_results"
BKM_FILE = "bkm_directory.json"
DIAGRAMS_DIR = BKM_DIR / "diagrams"


def render_bkm_to_png_and_mmd(bkm, out_stem: Path) -> None:
    """Render a BKM as both Graphviz PNG and a Mermaid .mmd source."""
    out_stem.parent.mkdir(parents=True, exist_ok=True)
    bkm.render(filename=str(out_stem), fmt="png", view=False)

    # Mermaid source: each edge (u, v) -> a line "u --> v".
    mmd_lines = ["flowchart LR"]
    for node in bkm.graph.nodes:
        if node == "in":
            mmd_lines.append(f"    {node}((in))")
        elif node == "out":
            mmd_lines.append(f"    {node}((out))")
        else:
            mmd_lines.append(f'    {_safe_id(node)}["{node}"]')
    for u, v in bkm.graph.edges:
        mmd_lines.append(f"    {_safe_id(u)} --> {_safe_id(v)}")
    out_stem.with_suffix(".mmd").write_text("\n".join(mmd_lines) + "\n", encoding="utf-8")


def _safe_id(node: str) -> str:
    """Mermaid node IDs can't contain '+' — alias to a safe form."""
    return node.replace("+", "_")


def main() -> None:
    if not DATA_DIR.is_dir() or not any(DATA_DIR.glob("*.parquet")):
        sys.exit(f"[ERROR] {DATA_DIR} is empty. Run 00_generate_sample_data.py first.")

    cmd = [
        sys.executable, "-m", "bkm.generator",
        "--update",
        "--data_folder", str(DATA_DIR),
        "--bkm_folder",  str(BKM_DIR),
        "--bkm_file",    BKM_FILE,
    ]
    print("[01] $ " + " ".join(cmd))
    subprocess.run(cmd, check=True)

    out_path = BKM_DIR / BKM_FILE
    wafers_path = BKM_DIR / "bkm_wafers.json"
    if not out_path.is_file():
        sys.exit(f"[ERROR] expected {out_path} to exist after training")

    with open(out_path, encoding="utf-8") as f:
        versions = json.load(f)
    with open(wafers_path, encoding="utf-8") as f:
        wafer_bkms = json.load(f)

    print("\n[01] Registry summary")
    print(f"  directory: {out_path}")
    print(f"  wafers:    {wafers_path}")
    print(f"  versions:  {len(versions)}")
    print(f"  wafers:    {len(wafer_bkms)}")
    for ver, entry in versions.items():
        n_wafers = sum(1 for v in wafer_bkms.values() if v == ver)
        loaf_set = entry.get("loaf_set", [])
        print(f"  - {ver}: {n_wafers} wafers, loaves={loaf_set}")

    print(f"\n[01] Rendering DAGs to {DIAGRAMS_DIR}")
    bkm_registry, _ = load_bkm_directory(
        bkm_folder=BKM_DIR, bkm_file=BKM_FILE,
        label_kwargs=dict(wafer_id_label="wafer_id",
                          tkout_label="tkout_time",
                          loaf_label="loaf"),
    )
    for ver, bkm in bkm_registry.items():
        render_bkm_to_png_and_mmd(bkm, DIAGRAMS_DIR / ver)


if __name__ == "__main__":
    main()
