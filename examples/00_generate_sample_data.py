"""
00_generate_sample_data.py - synth wafer parquet files for the bkm examples.

Each output file = one wafer with multiple rows. All rows in a file share the
same `wafer_id` and `tkout_time`; the per-row equipment/chamber/chamber_step/sensor
values are combined into one loaf string by `bkm.generator.add_bkm_loaf()`.

Outputs (relative to project root):
    examples/training_data/  18 wafers across 3 distinct loaf patterns
    examples/inference_data/  5 wafers (3 known patterns + 2 novel)
"""
from __future__ import annotations

import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

import pandas as pd


HERE = Path(__file__).resolve().parent
TRAIN_DIR = HERE / "training_data"
INFER_DIR = HERE / "inference_data"

# Each pattern is a list of (equipment, chamber, chamber_step, sensor) rows that
# make up one wafer.
PATTERNS: Dict[str, List[tuple]] = {
    "A": [
        ("eq1", "ch1", "cs1", "se1"),
        ("eq2", "ch2", "cs2", "se2"),
    ],
    "B": [
        ("eq3", "ch3", "cs3", "se3"),
        ("eq4", "ch4", "cs4", "se4"),
        ("eq4", "ch4", "cs5", "se5"),
    ],
    "C": [
        ("eq5", "ch5", "cs6", "se6"),
        ("eq6", "ch6", "cs7", "se7"),
    ],
    # Novel patterns used only in inference_data (should be flagged as unknown).
    "X": [
        ("eq9", "ch9", "cs9", "se8"),
    ],
    "Y": [
        ("eq7", "ch7", "cs8", "se9"),
        ("eq8", "ch8", "cs9", "se10"),
    ],
}

T0 = datetime(2026, 1, 1, 9, 0, 0)


def make_wafer(wafer_id: str, pattern_key: str, tkout: datetime) -> pd.DataFrame:
    rows = [
        {"wafer_id": wafer_id, "tkout_time": tkout,
         "equipment": equipment, "chamber": chamber,
         "chamber_step": chamber_step, "sensor": sensor}
        for (equipment, chamber, chamber_step, sensor) in PATTERNS[pattern_key]
    ]
    return pd.DataFrame(rows)


def write_set(out_dir: Path, plan: List[tuple]) -> None:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    for i, (pattern_key, wafer_id) in enumerate(plan):
        tkout = T0 + timedelta(hours=i)
        df = make_wafer(wafer_id, pattern_key, tkout)
        df.to_parquet(out_dir / f"{wafer_id}.parquet", index=False)
        print(f"  wrote {out_dir.name}/{wafer_id}.parquet  pattern={pattern_key}  rows={len(df)}")


def main() -> None:
    train_plan = []
    for pattern_key in ("A", "B", "C"):
        for n in range(6):
            train_plan.append((pattern_key, f"LOT01_W{pattern_key}{n:02d}"))

    infer_plan = [
        ("A", "LOT02_WA00"),
        ("B", "LOT02_WB00"),
        ("C", "LOT02_WC00"),
        ("X", "LOT02_WX00"),
        ("Y", "LOT02_WY00"),
    ]

    print(f"[0] Generating training data -> {TRAIN_DIR}")
    write_set(TRAIN_DIR, train_plan)

    print(f"\n[0] Generating inference data -> {INFER_DIR}")
    write_set(INFER_DIR, infer_plan)

    print(f"\nDone. {len(train_plan)} training wafers, {len(infer_plan)} inference wafers.")


if __name__ == "__main__":
    main()
