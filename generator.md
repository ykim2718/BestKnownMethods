# generator.py - Multi-Wafer BKM Version Assignment

## 1. Purpose

`generator.py` extends `bkm.py` from a **single-BKM tool** into a
**multi-BKM batch processor**.

While `bkm.py` defines and manipulates a single BKM DAG (see `bkm.md`),
`generator.py` adds three capabilities that `bkm.py` does not have:

| Capability                    | bkm.py               | generator.py              |
|-------------------------------|-----------------------|-------------------------------|
| Manage multiple BKM versions  | No (single instance)  | Yes (registry + index)        |
| Build loaf from raw columns   | No (expects `recipe`)  | Yes (combines equipment+chamber+sensor) |
| Batch-assign BKMs to wafers   | No (single wafer)     | Yes (all parquets in folder)  |
| Persist multi-BKM directory   | No (single JSON)      | Yes (directory JSON)          |
| Report & analytics            | No                    | Yes (summary, pareto)         |

---

## 2. How generator.py Uses bkm.py

### 2.1 BKM as a reader (edge inference)

A `BKM` instance with no `process_data` is used purely as a **reader**
to infer edges from a wafer DataFrame via `read_wafer_edges_from_df()`:

```python
from bkm import BKM

bkm_reader = BKM(
    wafer_id_label="wafer_id",
    tkout_label="tkout_time",
    loaf_label="loaf",
)

# Infer edges from a preprocessed 1-row DataFrame
wafer_id, edges, loaves = bkm_reader.read_wafer_edges_from_df(steps_df)
```

The reader does not hold any graph. It only uses the configured column labels
to parse the DataFrame and return edges.

### 2.2 BKM as a registered version (DAG holder)

When a new BKM version is created, the edges are converted into `process_data`
and a full BKM instance is constructed with a validated DAG:

```python
new_bkm = BKM(
    version="bkm0001",
    process_data={"in": ["a+b+c"], "a+b+c": ["out"]},
    wafer_id_label="wafer_id",
    tkout_label="tkout_time",
    loaf_label="loaf",
)
```

This BKM holds a complete graph with fingerprint, validation, and all
methods from `bkm.py` (matching, save/load, visualization).

### 2.3 BKM properties used by generator.py

| Property / Method             | Where used                           | Purpose                          |
|-------------------------------|--------------------------------------|----------------------------------|
| `BKM()`                       | Step [3] wafer loop                  | Create reader instance           |
| `BKM(process_data=...)`       | `find_or_create_bkm()`              | Register new BKM version         |
| `read_wafer_edges_from_df()`  | Step [3] wafer loop                  | Infer edges from DataFrame       |
| `.graph.number_of_nodes()`    | Step [5] summary                     | Count loaves per BKM             |
| `.fingerprint()`              | Steps [5], [9] summary/save         | Identify BKM structure           |
| `._nodes`                     | `save_bkm_directory()`              | Serialize node data to JSON      |

---

## 3. Key Extension: Loaf Construction from Raw Columns

`bkm.py` expects a single `recipe` (or `loaf`) column already present in the parquet.
`generator.py` creates the loaf on-the-fly from multiple raw columns.

### 3.1 The add_bkm_loaf() function

Given `bkm_columns = ['equipment', 'chamber', 'chamber_step', 'sensor']`, it:

1. Reads the parquet with only the needed columns
2. **Walks the columns in the order specified by `--bkm_columns`** (the user's
   order is preserved verbatim — no alphabetical sort), collecting sorted
   unique values from each column
3. Concatenates all values with `+` to form a single loaf string
4. Synthesizes `tkin_time` as `tkout_time - 60 minutes`

> **The order of `bkm_columns` is part of the BKM identity.** The same column
> set in a different order produces a different loaf string and therefore a
> different BKM (different fingerprint). Within a single column, however,
> values are always sorted — that's a canonical representation, not an order
> choice.

**Example**: A parquet file containing:

| wafer_id  | equipment | chamber | chamber_step | sensor | measured_value | tkout_time          |
|-----------|-----------|---------|--------------|--------|----------------|---------------------|
| LOT01_W01 | eq1       | ch1     | cs1          | se1    | 12.34          | 2025-08-01 09:00:00 |
| LOT01_W01 | eq2       | ch2     | cs2          | se2    | 13.45          | 2025-08-01 09:00:00 |

> `measured_value` is a real-life data column (sensor reading, etc.) that is
> **not part of the loaf composition** — only the columns listed in
> `--bkm_columns` (default: `equipment`, `chamber`, `chamber_step`, `sensor`)
> are used. Any extra columns in the parquet are simply ignored by
> `add_bkm_loaf()`.

Step-by-step (user order preserved → equipment → chamber → chamber_step → sensor):

```
columns (user order): equipment, chamber, chamber_step, sensor

equipment    unique sorted: ["eq1", "eq2"]
chamber      unique sorted: ["ch1", "ch2"]
chamber_step unique sorted: ["cs1", "cs2"]
sensor       unique sorted: ["se1", "se2"]

concatenated: ["eq1", "eq2", "ch1", "ch2", "cs1", "cs2", "se1", "se2"]
loaf = "eq1+eq2+ch1+ch2+cs1+cs2+se1+se2"
```

Output (1-row DataFrame):

| wafer_id  | tkin_time           | tkout_time          | loaf                              |
|-----------|---------------------|---------------------|-----------------------------------|
| LOT01_W01 | 2025-08-01 08:00:00 | 2025-08-01 09:00:00 | eq1+eq2+ch1+ch2+cs1+cs2+se1+se2   |

If the user instead passes `--bkm_columns sensor,equipment,chamber_step,chamber`,
the same data yields a **different loaf** (and a different BKM):

```
loaf = "se1+se2+eq1+eq2+cs1+cs2+ch1+ch2"
```

This 1-row DataFrame is then fed to `bkm_reader.read_wafer_edges_from_df()`.

### 3.2 Why this extension matters

In `bkm.py`, the loaf is a single pre-existing column (e.g. `"recipe": "a"`).
In real production data, there is no single "recipe" column. Instead, the process
identity is determined by the **combination** of equipment, channel, channel step,
and sensor. `generator.py` bridges this gap by composing the loaf from
multiple columns before passing it to the BKM edge inference engine.

---

## 4. Key Extension: Multi-BKM Registry

### 4.1 Data structures

`bkm.py` handles one BKM at a time. `generator.py` manages an **entire
catalog** of BKM versions using two in-memory dictionaries:

```python
bkm_registry:   Dict[str, BKM]              # "bkm0001" -> BKM instance
loaf_set_index:  Dict[FrozenSet[str], str]   # frozenset({"loaf_a", "loaf_b"}) -> "bkm0001"
```

- `bkm_registry` stores the actual BKM objects (with full DAG, fingerprint, etc.)
- `loaf_set_index` is a **hash index** for O(1) wafer-to-BKM matching

### 4.2 Matching logic: extract_loaf_set()

To determine which BKM a wafer belongs to, the function extracts all
loaf names from the wafer's edges (excluding virtual `in`/`out` nodes)
and creates a `frozenset`:

```python
edges = [("in", "eq1+ch1+cs1+se1"), ("eq1+ch1+cs1+se1", "out")]

loaf_set = frozenset({"eq1+ch1+cs1+se1"})
```

This frozenset is looked up in `loaf_set_index`. Two wafers with the
**exact same set of loaf names** are assigned to the same BKM version.

### 4.3 Version creation: find_or_create_bkm()

```
wafer edges ──> extract_loaf_set() ──> frozenset
                                           │
                              ┌─────────────┴─────────────┐
                              │                           │
                        found in index              not found
                              │                           │
                      return existing ver      ┌──────────┴──────────┐
                                               │                    │
                                         allow_create=True    allow_create=False
                                               │                    │
                                        create new BKM       return "unknown"
                                        ("bkm0001", ...)
```

When `allow_create=True` (first run, or `--update`):
1. Assigns an auto-incremented version name (`bkm0001`, `bkm0002`, ...)
2. Converts edges into `process_data` dict
3. Creates a `BKM` instance (validated DAG)
4. Registers in both `bkm_registry` and `loaf_set_index`

When `allow_create=False` (using existing directory):
- Only matches against pre-loaded BKMs
- Unmatched wafers receive `"unknown"` label

### 4.4 Persistence: BKM directory + wafers JSON

`bkm.py` saves a single BKM to a JSON file. `generator.py` writes **two
sibling files** in the same `bkm_folder`:

**`bkm_directory.json`** — version entries at the top level (no wrapping key):

```json
{
  "bkm0001": {
    "version": "bkm0001",
    "fingerprint": "a1b2c3d4...",
    "labels": { "wafer_id": "wafer_id", "loaf": "loaf", ... },
    "nodes": {
      "in":                { "next_steps": ["4+5+s1+e2+se196"] },
      "4+5+s1+e2+se196":  { "next_steps": ["out"] },
      "out":               { "next_steps": [] }
    },
    "loaf_set": ["4+5+s1+e2+se196"]
  },
  "bkm0002": { ... },
  "bkm0003": { ... }
}
```

**`bkm_wafers.json`** — wafer→BKM-version mapping, sorted by `wafer_id`:

```json
{
  "LOT01_W001": "bkm0001",
  "LOT01_W002": "bkm0001",
  "LOT01_W003": "bkm0002"
}
```

The `loaf_set` field in `bkm_directory.json` stores the frozenset that was used
for matching, enabling the registry to be reloaded and `loaf_set_index`
to be reconstructed. `bkm_wafers.json` is informational output (not consumed by
`load_bkm_directory()` — inference mode rebuilds matchings from the directory
alone).

---

## 5. Two Operation Modes

### 5.1 First run (discovery mode)

No existing BKM directory file. The script discovers BKM versions from data:

```bash
python generator.py --data_folder training_data --update
```

- `allow_create = True`
- Every new loaf set creates a new BKM version
- At the end, saves the registry to `bkm_directory.json`

### 5.2 Subsequent runs (assignment mode)

An existing BKM directory is loaded. The script assigns wafers to known versions:

```bash
python generator.py --data_folder new_data
```

- `allow_create = False`
- Wafers matching a known loaf set get the existing BKM version
- Wafers with no match get `"unknown"`
- The directory file is not modified

---

## 6. Execution Pipeline (9 Steps)

```
[1] Build wafer index
 │  Scan parquet files, extract wafer_id + tkout_time, sort by time
 │
[2] Load or initialize BKM directory
 │  Load existing JSON, or start empty (--update)
 │
[3] Assign BKM versions
 │  For each wafer:
 │    add_bkm_loaf()  -->  read_wafer_edges_from_df()  -->  find_or_create_bkm()
 │
[4] Show wafer results table
 │  Full DataFrame: wafer_id, parquet_file, tkout_time, bkm, n_loaves
 │
[5] BKM summary
 │  Total/known/unknown counts, per-version distribution with fingerprints
 │
[6] Pareto chart
 │  BKM versions sorted by wafer count, with percentage bars
 │
[8] Unknown BKM versions
 │  Wafers that did not match any known BKM (sorted by wafer_id)
 │
[9] Save BKM directory
    Write registry to JSON (only in discovery mode)
```

---

## 7. CLI Arguments

| Argument               | Default                          | Description                                |
|------------------------|----------------------------------|--------------------------------------------|
| `--data_folder`        | `training_data`                  | Folder containing wafer parquet files       |
| `--max_file_count`     | `0` (all)                        | Limit number of files to process            |
| `--bkm_file`           | `bkm_directory.json`             | BKM directory file name                     |
| `--bkm_folder`         | `bkm_results`                       | Folder to read/write BKM directory          |
| `--bkm_columns`        | `['equipment','chamber','chamber_step','sensor']`| Columns used to compose loaf string         |
| `--update`             | `False`                          | Rebuild BKM directory from scratch          |

---

## 8. Input / Output

### 8.1 Input: Wafer parquet files

Each parquet file represents one wafer. Required columns depend on `--bkm_columns`:

| Column        | Type     | Description                              |
|---------------|----------|------------------------------------------|
| `wafer_id`      | str      | Wafer identifier                         |
| `tkout_time`  | datetime | Track-out timestamp                      |
| `equipment`         | str      | Equipment name (part of loaf)            |
| `chamber`          | str      | Channel (part of loaf)                   |
| `chamber_step`     | str      | Channel step (part of loaf)              |
| `sensor`      | str      | Sensor name (part of loaf)               |

### 8.2 Output: Wafer assignment table (Step [4])

| wafer_id    | parquet_file      | tkout_time          | bkm      | n_loaves |
|-----------|-------------------|---------------------|----------|----------|
| LOT01_W01 | LOT01_W01.parquet | 2025-08-01 09:00:00 | bkm0001  | 1        |
| LOT02_W01 | LOT02_W01.parquet | 2025-08-02 10:00:00 | bkm0001  | 1        |
| LOT03_W01 | LOT03_W01.parquet | 2025-08-03 11:00:00 | bkm0002  | 3        |
| LOT04_W01 | LOT04_W01.parquet | 2025-08-04 12:00:00 | unknown  | 2        |

### 8.3 Output: BKM directory JSON (Step [9])

Multi-version directory file saved to `bkm_folder/bkm_file`.
Structure is described in Section 4.4.

### 8.4 Output: Log file

All console output is also written to `generator.log` via `TeeOutput`.

---

## 9. Function Reference

| Function                | Parameters (keyword-only)                                            | Returns                                          | Description                                |
|-------------------------|----------------------------------------------------------------------|--------------------------------------------------|--------------------------------------------|
| `build_wafers_index()`  | `folder`, `max_file_count`                                           | `pd.DataFrame`                                   | Scan parquets, build wafer index sorted by time |
| `add_bkm_loaf()`       | `folder`, `parquet_file`, `columns`                                  | `pd.DataFrame` (1 row)                           | Read parquet, compose loaf from raw columns     |
| `extract_loaf_set()`   | `edges`                                                              | `FrozenSet[str]`                                 | Extract loaf names from edges (exclude in/out)  |
| `find_or_create_bkm()` | `bkm_registry`, `loaf_set_index`, `wafer_edges`, `label_kwargs`, `allow_create` | `str` (version or "unknown")         | Match wafer to BKM or create new version        |
| `save_bkm_directory()`  | `bkm_registry`, `loaf_set_index`, `bkm_folder`, `bkm_file`          | `Path`                                           | Serialize all BKMs + loaf index to JSON         |
| `load_bkm_directory()`  | `bkm_folder`, `bkm_file`, `label_kwargs`                            | `(Dict[str,BKM], Dict[FrozenSet,str])`           | Deserialize registry + index from JSON          |
| `parse_args()`          | `verbose`                                                            | `argparse.Namespace`                             | Parse and validate CLI arguments                |
