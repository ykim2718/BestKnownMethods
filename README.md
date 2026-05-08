# bkm

**BKM (Best Known Method) DAG generator for wafer process flows.**

Build, validate, fingerprint, and match Directed Acyclic Graphs that describe
semiconductor wafer process flows from parquet data.

## Installation

```bash
pip install bkm
pip install bkm[viz]   # with graphviz rendering
```

## Quick start (Python API)

```python
from bkm import BKM

bkm = BKM(
    version="v1",
    process_data={
        "in": ["a"],
        "a":  ["b", "c"],
        "b":  ["out"],
        "c":  ["out"],
    },
)

print(bkm.fingerprint())
print(bkm.print_graph())
bkm.save("v1.json")
```

## CLI usage (`bkm-generator`)

Process all parquet files in a folder and assign BKM versions:

```bash
bkm-generator --data_folder ./training_data --update
```

Subsequent runs assign wafers to existing BKMs and flag unmatched as `unknown`:

```bash
bkm-generator --data_folder ./new_data
```

## Documentation

- `bkm.md` — `BKM` class API, DAG concepts, edge inference algorithm
- `generator.md` — multi-BKM registry, loaf composition, CLI pipeline

## License

MIT © 2026 yRocket
