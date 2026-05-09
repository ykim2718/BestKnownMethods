#!c:/Y/anaconda3/python.exe
"""
(copyLeft) yRocket, 2026.4.10 - 11, 4.14
generator.py - BKM Version Generator from Wafer Parquet Files

Reads wafer parquet files from a data_folder, preprocesses them to create
loaf and tkin_time columns, then assigns BKM versions by comparing
each wafer's process flow (set of loaves) against known BKM definitions.

Each wafer may have multiple loaves (equipment+chamber+sensor combinations).
Wafers with the same set of loaves belong to the same BKM version.

Usage:
    python -m bkm.generator --data_folder training_data
    bkm-generator --data_folder training_data        # console-script form
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
from pathlib import Path
from typing import Dict, FrozenSet, List, Tuple, Union

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import pandas as pd
from tqdm import tqdm

from .bkm import BKM
from . import utils as cu


# ═══════════════════════════════════════════════════════════════════════════════
#  Column label constants
# ═══════════════════════════════════════════════════════════════════════════════

# Wafer index DataFrame columns
col_wafer_id: str = "wafer_id"
col_parquet_file: str = "parquet_file"
col_tkin_time: str = "tkin_time"
col_tkout_time: str = "tkout_time"
col_bkm: str = "bkm"
col_n_loaves: str = "n_loaves"

# Generated column for BKM class compatibility
col_bkm_loaf: str = "loaf"


# ═══════════════════════════════════════════════════════════════════════════════
#  Functions
# ═══════════════════════════════════════════════════════════════════════════════

def build_wafers_index(*, folder: Path, max_file_count: int = 0) -> pd.DataFrame:
    """Scan all parquet files in folder and build a wafer index DataFrame.

    Args:
        folder: Folder containing parquet files.
        max_file_count: Max number of files to process. 0 means all.

    Returns:
        DataFrame sorted by tkout_time with columns:
        [col_wafer_id, col_parquet_file, col_tkout_time]
    """
    files: List[Path] = sorted(folder.glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"No parquet files found in {folder}")

    if max_file_count > 0:
        files = files[:max_file_count]

    rows: List[dict] = []
    pbar = tqdm(files, ncols=100, unit='parquet', desc="Indexing")
    for fpath in pbar:
        pbar.set_description(f"Indexing {fpath.stem}")
        df = pd.read_parquet(path=fpath, columns=[col_wafer_id, col_tkout_time])
        wafer_id: str = str(df[col_wafer_id].iloc[0])
        min_tkout = pd.to_datetime(df[col_tkout_time]).min()
        rows.append({
            col_wafer_id: wafer_id,
            col_parquet_file: fpath.name,
            col_tkout_time: min_tkout,
        })

    wafers: pd.DataFrame = pd.DataFrame(rows)
    wafers = wafers.sort_values(col_tkout_time).reset_index(drop=True)
    print(f"[generator] Built wafer index: {len(wafers)} wafers, "
          f"sorted by {col_tkout_time}")
    return wafers


def add_bkm_loaf(*, folder: Path, parquet_file: str, columns: List[str]) -> pd.DataFrame:
    """Read a wafer parquet and collapse it into a single 'loaf' row.

    Reads only the minimal columns needed, then constructs:
      - 'loaf' column: values from each column in ``columns`` (in the given
        order) joined by '+' — e.g. with ``columns=['equipment','chamber']``,
        loaf would be ``"eq1+eq2+ch1+ch2"`` (equipment values first, then
        chamber). The order of ``columns`` is preserved as the user specified
        it: a different ordering produces a different loaf string.
      - 'tkin_time' column: tkout_time - 60 minutes (synthesized).

    Args:
        folder: Folder containing the parquet file.
        parquet_file: Filename of the parquet (relative to ``folder``).
        columns: Source columns whose unique sorted values are concatenated
            to form the loaf. Order is preserved verbatim.

    Returns:
        Always a 1-row, 4-column DataFrame.

        Shape:   (1, 4)
        Index:   RangeIndex([0])  — single row, integer 0 (after reset_index)
        Columns: ['wafer_id', 'tkin_time', 'tkout_time', 'loaf']

        | Column      | dtype                        | Source                                          |
        |-------------|------------------------------|-------------------------------------------------|
        | wafer_id    | object (str)                 | First value of input wafer_id column            |
        | tkin_time   | object (str: YYYY-MM-DD ...) | tkout_time - 60 min, formatted via strftime     |
        | tkout_time  | datetime64[ns] (from parquet)| Single representative value from input          |
        | loaf        | object (str)                 | '+'.join(sorted_unique values, per column order)|

    Example:
        Input parquet ``LOT01_W01.parquet`` (2 rows):

            wafer_id   equipment  chamber  chamber_step  sensor  tkout_time
            LOT01_W01  eq1        ch1      cs1           se1     2025-08-01 09:00:00
            LOT01_W01  eq2        ch2      cs2           se2     2025-08-01 09:00:00

        Call:

            add_bkm_loaf(
                folder=Path("training_data"),
                parquet_file="LOT01_W01.parquet",
                columns=["equipment", "chamber", "chamber_step", "sensor"],
            )

        Returned DataFrame:

               wafer_id     tkin_time             tkout_time            loaf
            0  LOT01_W01    2025-08-01 08:00:00   2025-08-01 09:00:00   eq1+eq2+ch1+ch2+cs1+cs2+se1+se2

        How the loaf string was built (one bucket per column, order preserved):

            equipment    -> sorted unique: ['eq1', 'eq2']
            chamber      -> sorted unique: ['ch1', 'ch2']
            chamber_step -> sorted unique: ['cs1', 'cs2']
            sensor       -> sorted unique: ['se1', 'se2']

            loaf = '+'.join(['eq1','eq2','ch1','ch2','cs1','cs2','se1','se2'])
                 = 'eq1+eq2+ch1+ch2+cs1+cs2+se1+se2'

        Reordering ``columns=['sensor','equipment','chamber_step','chamber']``
        with the same input yields a *different* loaf and therefore a
        different BKM identity:

            loaf = 'se1+se2+eq1+eq2+cs1+cs2+ch1+ch2'

    Raises:
        AssertionError: If the parquet contains more than one distinct
            ``wafer_id``.
    """
    core_columns: List[str] = [col_wafer_id, col_tkout_time]
    fpath: Path = folder / parquet_file
    df: pd.DataFrame = pd.read_parquet(
        path=fpath, columns=sorted(set(columns + core_columns))
    )
    a: List = []
    for col in columns:
        a.extend(sorted(df[col].unique()))
    if df[col_wafer_id].unique().size != 1:
        raise AssertionError(
            f"  [ERROR] Multiple wafer_id in {parquet_file}: {df[col_wafer_id].unique()}"
        )
    if df[col_tkout_time].unique().size != 1:
        message: str = (
            f"  [ERROR] Multiple tkout_times in {parquet_file}: "
            f"{df[col_tkout_time].unique()}"
        )
        if False:
            raise AssertionError(message)
        else:
            a_counts = df[col_tkout_time].value_counts()
            message += f": {a_counts.to_dict()}"
            tkout_time = a_counts.idxmin()
            df[col_tkout_time] = tkout_time
            message += f"; take {tkout_time} as the representative"
            print(message)
    steps: pd.DataFrame = df.loc[[df.index[0]], [col_wafer_id, col_tkout_time]]
    steps[col_tkin_time] = (
        (pd.Timestamp(steps[col_tkout_time].iloc[0]) - pd.Timedelta(minutes=60))
        .strftime("%Y-%m-%d %H:%M:%S")
    )
    steps[col_bkm_loaf] = '+'.join(map(str, a))
    steps = steps[[col_wafer_id, col_tkin_time, col_tkout_time, col_bkm_loaf]]
    assert steps.shape == (1, 4)
    return steps.reset_index(drop=True)


def extract_loaf_set(*, edges: List[Tuple[str, str]]) -> FrozenSet[str]:
    """Extract the set of loaf names from edges (excluding 'in'/'out').

    For BKM comparison, two wafers match if they have the exact same
    set of loaves. Using frozenset enables O(1) hash-based lookup.
    """
    loaves: set = set()
    for src, dst in edges:
        if src != "in":
            loaves.add(src)
        if dst != "out":
            loaves.add(dst)
    return frozenset(loaves)


BKM_UNKNOWN: str = "unknown"


def find_or_create_bkm(
        *,
        bkm_registry: Dict[str, BKM],
        loaf_set_index: Dict[FrozenSet[str], str],
        wafer_edges: List[Tuple[str, str]],
        label_kwargs: dict,
        allow_create: bool = True,
) -> str:
    """Find a matching BKM version or create a new one.

    Uses a loaf-set hash index for O(1) lookup:
    Two wafers belong to the same BKM if they have the exact same set of loaves.

    Args:
        bkm_registry:   Dict mapping bkm_version_str -> BKM instance.
        loaf_set_index: Dict mapping frozenset(loaves) -> bkm_version_str.
        wafer_edges:    List of (src, dst) edge tuples from the wafer.
        label_kwargs:   Dict of label kwargs for BKM constructor.
        allow_create:   If True, create new BKM when no match found.
                        If False, return BKM_UNKNOWN instead.

    Returns:
        BKM version string, or BKM_UNKNOWN if not matched and creation disabled.
    """
    loaf_set: FrozenSet[str] = extract_loaf_set(edges=wafer_edges)

    # O(1) lookup by loaf set
    if loaf_set in loaf_set_index:
        return loaf_set_index[loaf_set]

    # No match found
    if not allow_create:
        tqdm.write(f"  [UNKNOWN] no matching BKM for {len(loaf_set)} loaves")
        return BKM_UNKNOWN

    # Create new BKM
    next_id: int = len(bkm_registry) + 1
    new_version: str = f"bkm{next_id:04d}"

    successors: dict = {}
    for src, dst in wafer_edges:
        successors.setdefault(src, set()).add(dst)

    process_data: dict = {node: sorted(succs) for node, succs in successors.items()}
    new_bkm: BKM = BKM(version=new_version, process_data=process_data, **label_kwargs)
    bkm_registry[new_version] = new_bkm
    loaf_set_index[loaf_set] = new_version

    tqdm.write(f"  [NEW] {new_version}: {len(loaf_set)} loaves, {new_bkm}")
    return new_version


# ═══════════════════════════════════════════════════════════════════════════════
#  BKM Directory (multi-BKM registry persistence)
# ═══════════════════════════════════════════════════════════════════════════════

BKM_WAFERS_FILE: str = "bkm_wafers.json"


def save_bkm_directory(
        *,
        bkm_registry: Dict[str, BKM],
        loaf_set_index: Dict[FrozenSet[str], str],
        wafer_bkms: Dict[str, str],
        bkm_folder: Path,
        bkm_file: str,
) -> Path:
    """Save the BKM registry to ``bkm_file`` and the wafer→BKM mappings to
    a sibling ``bkm_wafers.json``.

    The directory file holds version entries directly at the top level
    (no ``bkm_versions`` wrapping key)."""
    bkm_folder.mkdir(parents=True, exist_ok=True)
    fpath: Path = bkm_folder / bkm_file
    wafers_path: Path = bkm_folder / BKM_WAFERS_FILE

    # Invert loaf_set_index: version -> loaf_set
    ver_to_loaf_set: Dict[str, FrozenSet[str]] = {
        ver: ls for ls, ver in loaf_set_index.items()
    }

    directory: dict = {}
    for ver, bkm in sorted(bkm_registry.items()):
        entry: dict = {
            "version": bkm.version,
            "fingerprint": bkm.fingerprint(),
            "labels": {
                "wafer_id": bkm.wafer_id_label,
                "loaf": bkm.loaf_label,
                "tkin_time": bkm.tkin_label,
                "tkout_time": bkm.tkout_label,
            },
            "nodes": {},
            "loaf_set": sorted(ver_to_loaf_set.get(ver, [])),
        }
        for name in sorted(bkm._nodes.keys()):
            node = bkm._nodes[name]
            entry["nodes"][name] = {"next_steps": node.next_steps}
        directory[ver] = entry

    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(directory, f, indent=2, ensure_ascii=False)

    sorted_wafer_bkms: Dict[str, str] = dict(sorted(wafer_bkms.items()))
    with open(wafers_path, "w", encoding="utf-8") as f:
        json.dump(sorted_wafer_bkms, f, indent=2, ensure_ascii=False)

    print(f"[BKM Directory] Saved {len(bkm_registry)} BKM(s) to {fpath}")
    print(f"[BKM Directory] Saved {len(wafer_bkms)} wafer mapping(s) to {wafers_path}")
    return fpath


def load_bkm_directory(
        *,
        bkm_folder: Path,
        bkm_file: str,
        label_kwargs: dict,
) -> Tuple[Dict[str, BKM], Dict[FrozenSet[str], str]]:
    """Load BKM registry and loaf-set index from a directory JSON file.

    Expects each top-level key to be a version (no ``bkm_versions`` wrapper).
    Wafer→BKM mappings live in a sibling ``bkm_wafers.json`` and are not
    loaded here."""
    fpath: Path = bkm_folder / bkm_file
    with open(fpath, "r", encoding="utf-8") as f:
        directory: dict = json.load(f)

    bkm_registry: Dict[str, BKM] = {}
    loaf_set_index: Dict[FrozenSet[str], str] = {}

    for ver, entry in directory.items():
        process_data: Dict[str, List[str]] = {}
        for name, info in entry["nodes"].items():
            next_steps: List[str] = info["next_steps"]
            if next_steps or name == "in":
                process_data[name] = next_steps

        bkm: BKM = BKM(version=ver, process_data=process_data, **label_kwargs)

        stored_fp: Union[str, None] = entry.get("fingerprint")
        if stored_fp and stored_fp != bkm.fingerprint():
            print(f"  [WARN] Fingerprint mismatch for {ver}: "
                  f"stored={stored_fp[:16]}... computed={bkm.fingerprint()[:16]}...")

        bkm_registry[ver] = bkm

        loaf_set: FrozenSet[str] = frozenset(entry.get("loaf_set", []))
        if loaf_set:
            loaf_set_index[loaf_set] = ver

    print(f"[BKM Directory] Loaded {len(bkm_registry)} BKM(s) from {fpath}")
    return bkm_registry, loaf_set_index


# ═══════════════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════════════

def parse_args(*, verbose: bool = True) -> argparse.Namespace:
    """Parse command-line arguments for training."""
    ap = argparse.ArgumentParser(
        description="BKM Generator - Assign BKM versions to wafers from parquet files")
    ap.add_argument("--data_folder", default="training_data",
                    help="Folder containing wafer parquet files (default: training_data)")
    ap.add_argument("--max_file_count", type=int, default=0,
                    help="Max number of files to process (default=0 means all)")
    ap.add_argument("--bkm_file", default="bkm_directory.json",
                    help="BKM directory file name (default: bkm_directory.json)")
    ap.add_argument("--bkm_folder", default="bkm_results",
                    help="Folder to read/write BKM directory file (default: bkm_results)")
    BKM_COLUMNS_DEFAULT: List[str] = ['equipment', 'chamber', 'chamber_step', 'sensor']
    ap.add_argument("--bkm_columns",
                    type=lambda s: [c.strip() for c in s.split(',') if c.strip()],
                    default=BKM_COLUMNS_DEFAULT,
                    help=("Comma-separated column names for BKM loaf composition. "
                          "Order matters: the loaf string is built by walking columns "
                          "in this order, so the same column set in a different order "
                          "produces a different loaf and therefore a different BKM. "
                          f"Default: {','.join(BKM_COLUMNS_DEFAULT)}"))
    ap.add_argument("--update", action="store_true", default=False,
                    help="Ignore existing BKM directory and rebuild from scratch")
    args = ap.parse_args()

    if verbose:
        print('parsed_args=' + json.dumps(vars(args), indent=2))
    return args


def main() -> None:
    """CLI entry point for the `bkm-generator` console script."""
    # Tee stdout/stderr to a log file alongside terminal output
    sys.stdout = sys.stderr = cu.TeeOutput(cu.my_script_stem() + '.log')

    timer = cu.MyTimer(task_name=cu.my_script_name())
    timer.start()
    print()

    print(f"{'=' * 100}")
    print(f" BKM Generator")
    print(f"Python: {sys.executable}")
    print(f"Script: {sys.argv[0]}")
    print(f"Args:   {sys.argv[1:]}")
    print(f"{'=' * 100}\n")

    args = parse_args()
    data_folder: Path = Path(args.data_folder)

    # Label kwargs for BKM instances
    label_kwargs: dict = dict(
        wafer_id_label=col_wafer_id,
        tkout_label=col_tkout_time,
        loaf_label=col_bkm_loaf,
    )

    # -- 1. Build wafer index --------------------------------------------------
    print("[1] Building wafer index...")
    wafers: pd.DataFrame = build_wafers_index(
        folder=data_folder, max_file_count=args.max_file_count
    )
    wafers[col_bkm] = ""
    wafers[col_n_loaves] = 0
    print(f"  Wafers: {len(wafers)}")
    print(f"  Time range: {wafers[col_tkout_time].min()} ~ {wafers[col_tkout_time].max()}")
    print()

    # -- 2. Load existing BKM directory (if available) -------------------------
    bkm_folder: Path = Path(args.bkm_folder)
    bkm_file_path: Path = bkm_folder / args.bkm_file

    bkm_registry: Dict[str, BKM] = {}
    loaf_set_index: Dict[FrozenSet[str], str] = {}

    allow_create: bool = True  # allow creating new BKM versions

    if args.update:
        print(f"[2] --update: Rebuilding BKM directory from scratch")
        print(f"  Ignoring existing {bkm_file_path}")
    elif bkm_file_path.is_file():
        print(f"[2] Loading existing BKM directory: {bkm_file_path}")
        bkm_registry, loaf_set_index = load_bkm_directory(
            bkm_folder=bkm_folder, bkm_file=args.bkm_file, label_kwargs=label_kwargs
        )
        print(f"  Loaded {len(bkm_registry)} BKM version(s)")
        allow_create = False  # use existing BKMs only; unmatched -> unknown
    else:
        print(f"[2] No existing BKM directory found at {bkm_file_path}")
        print(f"  Starting with empty registry")
    print()

    # -- 3. Loop through wafers, assign BKM versions --------------------------
    print("[3] Assigning BKM versions...")
    print(f"  BKM columns : {args.bkm_columns}")
    bkm_reader: BKM = BKM(**label_kwargs)

    pbar = tqdm(wafers.index, desc="Processing", ncols=100, unit='parquet')
    for idx in pbar:
        parquet_file: str = wafers.at[idx, col_parquet_file]
        pbar.set_description(
            f"Processing {wafers.at[idx, col_wafer_id]} ({parquet_file})")

        steps_df: pd.DataFrame = add_bkm_loaf(
            folder=data_folder, parquet_file=parquet_file, columns=args.bkm_columns
        )
        wf_id, edges, loaves = bkm_reader.read_wafer_edges_from_df(steps_df)
        bkm_ver: str = find_or_create_bkm(
            bkm_registry=bkm_registry,
            loaf_set_index=loaf_set_index,
            wafer_edges=edges,
            label_kwargs=label_kwargs,
            allow_create=allow_create,
        )

        wafers.at[idx, col_bkm] = bkm_ver
        wafers.at[idx, col_n_loaves] = len(set(loaves))
    print()

    # -- 4. Show wafers result -------------------------------------------------
    print("[4] Wafers with BKM assignments:")
    pd.set_option("display.max_rows", None)
    pd.set_option("display.width", 120)
    print(wafers.to_string(index=True))
    print()

    # -- 5. BKM Summary -------------------------------------------------------
    n_unknown: int = int((wafers[col_bkm] == BKM_UNKNOWN).sum())
    n_known: int = len(wafers) - n_unknown

    print("[5] BKM Summary:")
    print(f"  Total wafers : {len(wafers)}")
    print(f"  Known BKM    : {n_known}")
    print(f"  Unknown BKM  : {n_unknown}" + (" (none)" if n_unknown == 0 else ""))
    print(f"  BKM versions : {len(bkm_registry)}")
    print()

    bkm_counts: pd.Series = wafers[col_bkm].value_counts().sort_index()
    print("  BKM distribution:")
    for ver, count in bkm_counts.items():
        if ver == BKM_UNKNOWN:
            print(f"    {ver}: {count:4d} wafers  (no matching BKM)")
        else:
            bkm = bkm_registry[ver]
            n_loaves: int = bkm.graph.number_of_nodes() - 2
            wafer_ids: List[str] = (
                wafers[wafers[col_bkm] == ver][col_wafer_id].sort_values().tolist()
            )
            print(f"    {ver}: {count:4d} wafers, {n_loaves:3d} loaves  "
                  f"(fp={bkm.fingerprint()[:16]}...) "
                  f"{','.join(wafer_ids[:10])}{'...' if len(wafer_ids) > 10 else ''}")
    print()

    # -- 6. Pareto chart -------------------------------------------------------
    print("[6] BKM Pareto Chart (wafer count, descending):")
    sorted_bkms: List[Tuple[str, int]] = sorted(
        bkm_counts.items(), key=lambda x: x[1], reverse=True
    )
    total_wafers: int = sum(c for _, c in sorted_bkms)
    cum: int = 0
    bar_max: int = 40
    max_count: int = sorted_bkms[0][1] if sorted_bkms else 1
    print(f"  {'BKM':<12s} {'Count':>5s} {'%':>6s} {'Cum%':>6s}  Bar")
    print(f"  {'-' * 12} {'-' * 5} {'-' * 6} {'-' * 6}  {'-' * bar_max}")
    for ver, count in sorted_bkms:
        cum += count
        pct: float = 100.0 * count / total_wafers if total_wafers else 0
        cum_pct: float = 100.0 * cum / total_wafers if total_wafers else 0
        bar_len: int = int(bar_max * count / max_count)
        bar: str = '\u2588' * bar_len
        print(f"  {ver:<12s} {count:>5d} {pct:>5.1f}% {cum_pct:>5.1f}%  {bar}")
    print()

    # -- 7. Unknown BKM Versions -----------------------------------------------
    print("[8] Unknown BKM Versions:")
    unknown_wafers: pd.DataFrame = (
        wafers[wafers[col_bkm] == BKM_UNKNOWN][[col_wafer_id, col_parquet_file]]
        .sort_values(by=col_wafer_id)
    )
    n_unknown_wafers: int = len(unknown_wafers)
    if n_unknown_wafers > 0:
        print(f"  {BKM_UNKNOWN} ({n_unknown_wafers} wafer{'s' if n_unknown_wafers != 1 else ''}):")
        for _, r in unknown_wafers.iterrows():
            print(f"    {r[col_wafer_id]:>20s}  {r[col_parquet_file]}")
    else:
        print("  (none)")
    print()

    # -- 8. Save BKM directory -------------------------------------------------
    if allow_create:
        print("[9] Saving BKM directory...")
        # Build wafer_id -> bkm_version mapping
        wafer_bkms: Dict[str, str] = dict(
            zip(wafers[col_wafer_id], wafers[col_bkm])
        )
        save_bkm_directory(
            bkm_registry=bkm_registry,
            loaf_set_index=loaf_set_index,
            wafer_bkms=wafer_bkms,
            bkm_folder=bkm_folder,
            bkm_file=args.bkm_file,
        )
    else:
        print("[9] Skipped saving (using existing BKM directory, no --update)")

    print()
    print(f"{'=' * 100}")
    print(f" Done!")
    print(f"{'=' * 100}")

    timer.end()


if __name__ == "__main__":
    main()
