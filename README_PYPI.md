# bkm — Best Known Method DAG generator

Build, validate, fingerprint, and match Directed Acyclic Graphs that describe semiconductor wafer process flows. Auto-discover BKM versions from a folder of wafer parquet files, then route new wafers to a known BKM or flag them as `unknown`.

## Install

```bash
pip install bkm
pip install bkm[viz]   # adds graphviz for PNG rendering
```

Requires Python 3.9+. Dependencies: `pandas >= 1.5`, `networkx >= 2.8`, `tqdm >= 4.60`, `pyarrow >= 10.0`.

## Quick start (Python API)

```python
from bkm import BKM

# Build a single BKM DAG directly from a process_data dict
bkm = BKM(
    version="v1",
    process_data={
        "in": ["a"],
        "a":  ["b", "c"],   # branch
        "b":  ["out"],
        "c":  ["out"],
    },
)

print(bkm.fingerprint())     # canonical hash
print(bkm.print_graph())     # ASCII tree
bkm.save("v1.json")
bkm.render("v1", fmt="png")  # requires bkm[viz]
```

A **loaf** is the compressed identifier of one wafer's raw columns: `equipment + chamber + chamber_step + sensor` joined with `+` (e.g. `"eq1+eq2+ch1+ch2+cs1+cs2+se1+se2"`). Every node in the DAG is a loaf string.

## Public API

```python
from bkm import BKM, ProcessNode
```

| Symbol | Purpose |
|---|---|
| `BKM(version, process_data=...)` | Construct a single BKM DAG directly |
| `BKM.fingerprint()` | Canonical hash of the DAG (BKM identity) |
| `BKM.print_graph()` | ASCII tree dump |
| `BKM.render(filename, fmt='png')` | Graphviz PNG / SVG export |
| `BKM.save(path)` / `BKM.load(path)` | JSON round-trip |
| `BKM.read_wafer_edges_from_df(df, ...)` | Multi-row DataFrame → edges (timing-based branch inference) |
| `BKM.match_edges(edges)` / `match_path(seq)` | Test whether a wafer fits this BKM |
| `BKM.infer_from_parquets(folder, ...)` | Class method: discover a BKM from a folder |

CLI helpers from `bkm.generator`:

| Function | Purpose |
|---|---|
| `add_bkm_loaf(folder, parquet_file, columns)` | Build a 1-row loaf DataFrame from a wafer parquet |
| `find_or_create_bkm(...)` | Match a wafer's loaf-set against the BKM registry; create new if no match |
| `save_bkm_directory(...)` / `load_bkm_directory(...)` | Persist / load `bkm_directory.json` + `bkm_wafers.json` |

## CLI usage (`bkm-generator`)

Process every parquet in a folder and assign BKM versions:

```bash
# Training: discover new BKMs and add them to the registry
bkm-generator --data_folder ./training_data --update

# Inference: match wafers against existing BKMs (no --update)
bkm-generator --data_folder ./new_data
```

Outputs land in `./bkm_results/`:
- `bkm_directory.json` — BKM version registry (`bkm0001`, `bkm0002`, …)
- `bkm_wafers.json` — wafer → BKM mapping
- `diagrams/` — PNG (Graphviz) + Mermaid `.mmd` per BKM (when `bkm[viz]` is installed)

`python -m bkm.generator` works identically. The `bkm-generator` console command is registered by `pip install bkm`.

## Documentation

Full documentation — `BKM` class internals, edge inference algorithm, `bkm.generator` CLI options, examples walkthrough — lives on the GitHub README:

**https://github.com/ykim2718/BestKnownMethods**

The repo also ships a 4-script `examples/` demo.

## Links

- **Source / docs**: https://github.com/ykim2718/BestKnownMethods
- **Issues**: https://github.com/ykim2718/BestKnownMethods/issues
- **License**: MIT
