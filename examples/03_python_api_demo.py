"""
03_python_api_demo.py - Use bkm without the CLI.

Two parts:
  (1) Build a BRANCHED BKM ("demo_v1") in pure Python — shape:
      in -> loafA -> {loafB, loafC} -> out
      The CLI flow only ever produces linear DAGs (one loaf per wafer),
      so this script is the canonical way to demonstrate non-trivial DAGs.
  (2) Load the registry produced by 01_run_training.py and inspect it
      programmatically.
"""
from __future__ import annotations

from pathlib import Path

from bkm import BKM
from bkm.generator import load_bkm_directory


HERE = Path(__file__).resolve().parent
BKM_DIR = HERE / "bkm_results"
BKM_FILE = "bkm_directory.json"

LABEL_KWARGS = dict(
    wafer_id_label="wafer_id",
    tkout_label="tkout_time",
    loaf_label="loaf",
)


def part1_build_branched() -> BKM:
    print("=" * 60)
    print(" Part 1: build branched BKM in-memory")
    print("=" * 60)

    bkm = BKM(
        version="demo_v1",
        process_data={
            "in":    ["loafA"],
            "loafA": ["loafB", "loafC"],
            "loafB": ["out"],
            "loafC": ["out"],
        },
    )
    print(bkm)
    print(bkm.print_graph())
    print(f"fingerprint: {bkm.fingerprint()}")
    return bkm


def part2_inspect_registry() -> None:
    print("\n" + "=" * 60)
    print(" Part 2: inspect bkm_directory.json")
    print("=" * 60)

    registry_path = BKM_DIR / BKM_FILE
    if not registry_path.is_file():
        print(f"  [skip] {registry_path} not found. Run 01_run_training.py first.")
        return

    registry, loaf_set_index = load_bkm_directory(
        bkm_folder=BKM_DIR, bkm_file=BKM_FILE, label_kwargs=LABEL_KWARGS,
    )
    print(f"  {len(registry)} BKM version(s) loaded")
    for ver, bkm in registry.items():
        print(f"  - {ver}: {bkm} nodes={list(bkm.nodes.keys())}")

    print(f"\n  loaf-set index has {len(loaf_set_index)} entries:")
    for loaf_set, ver in loaf_set_index.items():
        print(f"  - {ver}: {sorted(loaf_set)}")


def main() -> None:
    part1_build_branched()
    part2_inspect_registry()


if __name__ == "__main__":
    main()
