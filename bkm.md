# BKM (Best Known Method) - Process Flow Graph

## 1. Definition

A **BKM** represents a semiconductor wafer process flow as a
**Directed Acyclic Graph (DAG)**.
Each node is a process step (called a **loaf**, e.g. a recipe name),
and each directed edge represents the temporal execution order between steps.

Every BKM contains two special virtual nodes:

| Node  | Role        | Constraint     |
|-------|-------------|----------------|
| `in`  | Entry point | in-degree = 0  |
| `out` | Exit point  | out-degree = 0 |

All node names are normalized to **lowercase** internally.

---

## 2. Directed Acyclic Graph (DAG)

### 2.1 What is a DAG?

A **Directed Acyclic Graph** is a graph where:

- Every edge has a **direction** (A -> B means "A leads to B", not the reverse).
- There are **no cycles** — you can never follow edges and return to a node
  you already visited.

These two properties make DAGs ideal for modeling process flows,
because manufacturing steps always move forward in time and never loop back.

### 2.2 DAG terminology

| Term            | Definition                                          | BKM example                   |
|-----------------|-----------------------------------------------------|-------------------------------|
| **Node**        | A vertex in the graph                               | A process step (`a`, `b`, `c`)|
| **Edge**        | A directed connection from one node to another       | `a -> b` (step a precedes b)  |
| **In-degree**   | Number of edges coming **into** a node               | `in` has in-degree 0          |
| **Out-degree**  | Number of edges going **out of** a node              | `out` has out-degree 0        |
| **Root**        | A node with in-degree 0 (no predecessors)            | The `in` node                 |
| **Leaf**        | A node with out-degree 0 (no successors)             | The `out` node                |
| **Branch node** | A node with out-degree > 1 (splits into parallels)   | `a` -> `[b, e, i]`           |
| **Merge node**  | A node with in-degree > 1 (multiple paths converge)  | `g` <- `[f, h, i]`           |
| **Path**        | A sequence of nodes connected by edges               | `in -> a -> b -> c -> out`    |

### 2.3 Understanding in-degree and out-degree

Every node in a DAG has two counts: **in-degree** (how many arrows point **into** it)
and **out-degree** (how many arrows go **out of** it).

Think of a node as a room with doors:
- **In-degree** = the number of **entrance** doors (arrows arriving from other nodes)
- **Out-degree** = the number of **exit** doors (arrows leaving to other nodes)

```
        ┌─── f
        │
  g  <──┼─── h       g has in-degree = 3  (three arrows come in)
        │
        └─── i


  a ───>─┬── b
         │
         ├── e       a has out-degree = 3  (three arrows go out)
         │
         └── i
```

**Why `in` must have in-degree 0:**
The `in` node is the very first step — nothing comes before it.
If something pointed into `in`, that would mean there is a step before
the start, which contradicts the definition of a starting point.

```
  (nothing) ──> in ──> a ──> b ──> ...
                ^
                no arrows come in (in-degree = 0)
```

**Why `out` must have out-degree 0:**
The `out` node is the very last step — nothing comes after it.
If `out` pointed to something, that would mean the process continues
after the end, which contradicts the definition of an ending point.

```
  ... ──> g ──> out ──> (nothing)
                    ^
                    no arrows go out (out-degree = 0)
```

**Full example from the sample BKM:**

| Node  | In-degree | Out-degree | Meaning                                          |
|-------|-----------|------------|--------------------------------------------------|
| `in`  | 0         | 1          | Start point: nothing before, leads to `a`        |
| `a`   | 1         | 3          | Branch: receives from `in`, splits to `b`, `e`, `i` |
| `b`   | 1         | 2          | Branch: receives from `a`, splits to `c`, `d`    |
| `c`   | 1         | 1          | Sequential: receives from `b`, leads to `out`    |
| `d`   | 1         | 1          | Sequential: receives from `b`, leads to `out`    |
| `e`   | 1         | 2          | Branch: receives from `a`, splits to `f`, `h`    |
| `f`   | 1         | 1          | Sequential: receives from `e`, leads to `g`      |
| `h`   | 1         | 1          | Sequential: receives from `e`, leads to `g`      |
| `i`   | 1         | 1          | Sequential: receives from `a`, leads to `g`      |
| `g`   | 3         | 1          | Merge: receives from `f`, `h`, `i`, leads to `out` |
| `out` | 3         | 0          | End point: receives from `c`, `d`, `g`, nothing after |

### 2.4 BKM DAG example (full)

The sample BKM defined in `bkm.py` has this structure:

```
in -> a
      ├── b
      │   ├── c -> out
      │   └── d -> out
      ├── e
      │   ├── f -> g -> out
      │   └── h -> g -> out
      └── i -> g -> out
```

This DAG contains:

- **10 nodes**: `in`, `a`, `b`, `c`, `d`, `e`, `f`, `g`, `h`, `i`, `out` (11 including `out`)
- **Branch nodes**: `a` (out-degree 3), `b` (out-degree 2), `e` (out-degree 2)
- **Merge node**: `g` (in-degree 3, reached from `f`, `h`, and `i`)
- **6 possible paths** from `in` to `out`:
  1. `in -> a -> b -> c -> out`
  2. `in -> a -> b -> d -> out`
  3. `in -> a -> e -> f -> g -> out`
  4. `in -> a -> e -> h -> g -> out`
  5. `in -> a -> i -> g -> out`

### 2.5 Why DAG for process flows?

| Property               | Benefit                                                |
|------------------------|--------------------------------------------------------|
| Directed edges         | Captures temporal order (which step comes before which)|
| No cycles              | Guarantees the process terminates (no infinite loops)  |
| Single `in` / `out`    | Every wafer starts and ends at well-defined points     |
| Branch nodes           | Models parallel or alternative process paths           |
| Merge nodes            | Models convergence (different paths rejoin)            |
| Path enumeration       | Lists all valid process routes through the factory     |
| Fingerprinting         | Deterministic hash enables fast BKM comparison         |

### 2.6 DAG validation rules

The `validate()` method enforces these invariants:

| Rule                              | Severity | Description                                |
|-----------------------------------|----------|--------------------------------------------|
| No cycles                         | Fatal    | Raises `ValueError` if a cycle is detected |
| `in` node exists                  | Fatal    | Must have exactly one entry point           |
| `in` has in-degree 0              | Fatal    | Nothing precedes the entry point            |
| `out` node exists                 | Fatal    | Must have exactly one exit point            |
| `out` has out-degree 0            | Fatal    | Nothing follows the exit point              |
| All nodes reach `out`             | Fatal    | No dead-end nodes allowed                   |
| Unreachable nodes (from `in`)     | Warning  | Nodes with in-degree 0 besides `in`         |

---

## 3. Data Structures

### 3.1 ProcessNode

```python
@dataclass
class ProcessNode:
    name: str                                        # node identifier (lowercase)
    next_steps: List[str] = field(default_factory=list)  # successor node names
```

- `name` — the process step identifier, stored in lowercase
- `next_steps` — list of successor node names (defines outgoing edges)
- `get_normalized_next()` — returns a sorted tuple for deterministic comparison

### 3.2 process_data (BKM registration dict)

The core data structure for defining a BKM is `Dict[str, List[str]]`,
mapping each node to its successor list.

The sample BKM in `bkm.py` is defined as:

```python
process_data = {
    "in": ["a"],
    "a":  ["b", "e", "i"],
    "b":  ["c", "d"],
    "c":  ["out"],
    "d":  ["out"],
    "e":  ["f", "h"],
    "f":  ["g"],
    "h":  ["g"],
    "i":  ["g"],
    "g":  ["out"],
}
```

Note: terminal nodes like `out` do not need to be listed as keys.
The `_build()` method automatically creates `ProcessNode` entries
for nodes that only appear as edge targets.

### 3.3 Internal representation

When `_build(process_data)` is called, it creates:

| Attribute                | Type                       | Description                               |
|--------------------------|----------------------------|-------------------------------------------|
| `_nodes`                 | `Dict[str, ProcessNode]`   | All node objects keyed by name            |
| `_graph`                 | `nx.DiGraph`               | NetworkX directed graph with edges        |
| `_fingerprint_cache`     | `Optional[str]`            | Cached SHA-256 hash (invalidated on rebuild) |
| `_path_fingerprints_cache` | `Optional[Dict]`         | Cached path fingerprints (invalidated on rebuild) |

---

## 4. How to Create a BKM

### 4.1 Manual construction (from process_data)

```python
from bkm import BKM

bkm = BKM(
    version="sample",
    process_data={
        "in": ["a"],
        "a":  ["b", "e", "i"],
        "b":  ["c", "d"],
        "c":  ["out"],
        "d":  ["out"],
        "e":  ["f", "h"],
        "f":  ["g"],
        "h":  ["g"],
        "i":  ["g"],
        "g":  ["out"],
    },
    wafer_id_label="wafer_id",
    loaf_label="recipe",
    tkin_label="tkin_time",
    tkout_label="tkout_time",
)
```

### 4.2 Automatic inference from parquet files

```python
bkm = BKM.infer_from_parquets(
    folder="bkm_results/parquets",
    version="inferred",
    wafer_id_label="wafer_id",
    loaf_label="recipe",
    tkin_label="tkin_time",
    tkout_label="tkout_time",
)
```

This reads all `.parquet` files in the folder, infers edges from each wafer
using the predecessor detection algorithm (see Section 5), merges all edges
into a single unified DAG, and calls `_build()`.

### 4.3 Load from JSON file

```python
bkm = BKM.load(path="bkm_results/sample.json")
```

---

## 5. Edge Inference Algorithm (Predecessor Detection)

When reading a wafer's process steps from a parquet file, `read_wafer_edges()`
infers the DAG edges from timestamps.

**Rule**: For each step X, the **predecessor** is the step whose `tkout` is the
**latest** value that is still `<= X.tkin`.

### 5.1 Sequential Flow Example

Using sample wafers from `generate_sample_parquets()`:

**W01**: steps `a -> b -> c` (each step: 60 min, gap: 5 min)

```
 a: |===tkin========tkout===|
    08:00              09:00
                              b: |===tkin========tkout===|
                                 09:05              10:05
                                                           c: |===tkin========tkout===|
                                                              10:10              11:10
```

| Step | tkin  | tkout | Predecessor logic                     | Edge     |
|------|-------|-------|---------------------------------------|----------|
| `a`  | 08:00 | 09:00 | No prior step -> start node           | `in -> a`|
| `b`  | 09:05 | 10:05 | Latest tkout <= 09:05 = a(09:00)      | `a -> b` |
| `c`  | 10:10 | 11:10 | Latest tkout <= 10:10 = b(10:05)      | `b -> c` |

Terminal detection: `c` has no successor -> `c -> out`

**Inferred edges**: `[("in","a"), ("a","b"), ("b","c"), ("c","out")]`

**Resulting DAG**:
```
in -> a -> b -> c -> out
```

Other sequential wafer examples from the sample data:

| Wafer | Recipe sequence       | Inferred path                    |
|-------|----------------------|----------------------------------|
| W01   | a, b, c              | `in -> a -> b -> c -> out`       |
| W02   | a, b, d              | `in -> a -> b -> d -> out`       |
| W04   | a, e, f, g           | `in -> a -> e -> f -> g -> out`  |
| W06   | a, e, h, g           | `in -> a -> e -> h -> g -> out`  |
| W08   | a, i, g              | `in -> a -> i -> g -> out`       |

### 5.2 Branching Flow Example

**W11**: steps `a -> b -> [c AND d]` (c and d run in parallel after b)

```
 a: |===tkin========tkout===|
    08:00              09:00
                              b: |===tkin========tkout===|
                                 09:05              10:05
                                                           c: |===tkin========tkout===|
                                                              10:10              11:10
                                                           d: |===tkin========tkout===|
                                                              10:10              11:10
```

Both `c` and `d` share the **same tkin_time** (10:10), starting simultaneously after `b`.

| Step | tkin  | tkout | Predecessor logic                          | Edge     |
|------|-------|-------|--------------------------------------------|----------|
| `a`  | 08:00 | 09:00 | No prior step -> start node                | `in -> a`|
| `b`  | 09:05 | 10:05 | Latest tkout <= 09:05 = a(09:00)           | `a -> b` |
| `c`  | 10:10 | 11:10 | Latest tkout <= 10:10 = b(10:05)           | `b -> c` |
| `d`  | 10:10 | 11:10 | Latest tkout <= 10:10 = b(10:05)           | `b -> d` |

Both `c` and `d` find `b` as their predecessor because `b.tkout (10:05) <= 10:10`.
Neither `c` nor `d` can be predecessor of the other since they start at the same time.

Terminal detection: both `c` and `d` have no successor -> `c -> out`, `d -> out`

**Inferred edges**: `[("in","a"), ("a","b"), ("b","c"), ("b","d"), ("c","out"), ("d","out")]`

**Resulting DAG**:
```
in -> a -> b -> c -> out
               └── d -> out
```

Here `b` becomes a **branch node** (out-degree 2) because two steps follow it simultaneously.

### 5.3 Overlap-based branching detection

The key insight: when step B is still running (`B.tkout > C.tkin`), step C
cannot have B as its predecessor. Instead, C finds an earlier step as predecessor,
which reveals that a **branch** occurred.

```
 A: |===tkin========tkout===|
                               B: |===tkin=================tkout=================|
                                    C: |===tkin========tkout===|

 For B: latest tkout <= B.tkin = A.tkout  -> edge A -> B
 For C: latest tkout <= C.tkin = A.tkout  -> edge A -> C  (B is NOT finished yet)
 Result: A branches into [B, C]
```

---

## 6. Input / Output

### 6.1 Input: Wafer parquet file

Each parquet file represents **one wafer** and must contain these columns:

| Column        | Type     | Description                               |
|---------------|----------|-------------------------------------------|
| `wafer_id`    | str      | Wafer identifier (e.g. `"W01"`)          |
| `recipe`      | str      | Process step name (e.g. `"a"`, `"b"`)    |
| `tkin_time`   | datetime | Track-in timestamp (step start)           |
| `tkout_time`  | datetime | Track-out timestamp (step end)            |

Column names are configurable via the constructor's label parameters.

### 6.2 Input example: Sequential wafer (W01)

| wafer_id | recipe | tkin_time           | tkout_time          |
|----------|--------|---------------------|---------------------|
| W01      | a      | 2025-08-01 08:00:00 | 2025-08-01 09:00:00 |
| W01      | b      | 2025-08-01 09:05:00 | 2025-08-01 10:05:00 |
| W01      | c      | 2025-08-01 10:10:00 | 2025-08-01 11:10:00 |

Three sequential steps with 5-minute gaps. Each step lasts 60 minutes.

### 6.3 Input example: Branching wafer (W11)

| wafer_id | recipe | tkin_time           | tkout_time          |
|----------|--------|---------------------|---------------------|
| W11      | a      | 2025-08-01 08:00:00 | 2025-08-01 09:00:00 |
| W11      | b      | 2025-08-01 09:05:00 | 2025-08-01 10:05:00 |
| W11      | c      | 2025-08-01 10:10:00 | 2025-08-01 11:10:00 |
| W11      | d      | 2025-08-01 10:10:00 | 2025-08-01 11:10:00 |

Steps `c` and `d` share the same `tkin_time`, indicating they run in parallel after `b`.

### 6.4 Output: BKM JSON file

```json
{
  "version": "sample",
  "fingerprint": "a1b2c3d4...",
  "labels": {
    "wafer_id": "wafer_id",
    "recipe": "recipe",
    "tkin_time": "tkin_time",
    "tkout_time": "tkout_time"
  },
  "nodes": {
    "in": { "next_steps": ["a"] },
    "a":  { "next_steps": ["b", "e", "i"] },
    "b":  { "next_steps": ["c", "d"] },
    "c":  { "next_steps": ["out"] },
    "d":  { "next_steps": ["out"] },
    "e":  { "next_steps": ["f", "h"] },
    "f":  { "next_steps": ["g"] },
    "g":  { "next_steps": ["out"] },
    "h":  { "next_steps": ["g"] },
    "i":  { "next_steps": ["g"] },
    "out": { "next_steps": [] }
  }
}
```

### 6.5 Output: print_graph()

```
in
└── a
    ├── b
    │   ├── c -> out
    │   └── d -> out
    ├── e
    │   ├── f -> g -> out
    │   └── h -> g -> out
    └── i -> g -> out
```

### 6.6 Output: summary()

```python
{
    "version": "sample",
    "node_count": 11,
    "edge_count": 12,
    "paths_in_to_out": [
        "in -> a -> b -> c -> out",
        "in -> a -> b -> d -> out",
        "in -> a -> e -> f -> g -> out",
        "in -> a -> e -> h -> g -> out",
        "in -> a -> i -> g -> out",
    ],
    "path_count": 5,
    "branch_nodes": ["a", "b", "e"],
    "merge_nodes": ["g", "out"],
    "fingerprint": "a1b2c3d4...",
    "path_fingerprints_count": 5,
}
```

---

## 7. Usage

### 7.1 Matching a wafer to a BKM

**Path-based matching** (for sequential wafers):

```python
# W01: a -> b -> c
matched = bkm.match_path(loaf_sequence=["a", "b", "c"])   # True

# Non-existent path
matched = bkm.match_path(loaf_sequence=["a", "c", "b"])   # False
```

**Edge-based matching** (for branching wafers):

```python
# W11: a -> b -> [c, d] (parallel)
matched = bkm.match_edges(edges={("a","b"), ("b","c"), ("b","d")})  # True
```

### 7.2 Fingerprinting

```python
fp = bkm.fingerprint()   # SHA-256 hex string
```

The fingerprint is computed from the canonical DAG structure:
1. Sort all node names alphabetically
2. For each node, list sorted successors: `"a|b,e,i\nb|c,d\nc|out\n..."`
3. Compute SHA-256 of that canonical string

Two BKMs with identical graph structure produce identical fingerprints,
regardless of version name or label configuration.

### 7.3 Save and load

```python
bkm.save(path="bkm_results/sample.json")
loaded = BKM.load(path="bkm_results/sample.json")

assert bkm == loaded                                  # True (fingerprint comparison)
assert bkm.fingerprint() == loaded.fingerprint()       # True
```

### 7.4 Visualization

**Text-based tree** (box-drawing characters):

```python
print(bkm.print_graph())
```

**Graphviz image** (requires `graphviz` package and system binaries):

```python
bkm.render(filename="process_flow", fmt="png", view=True)
```

Node colors in the rendered image:

| Color        | Hex       | Meaning                          |
|--------------|-----------|----------------------------------|
| Green        | `#90EE90` | `in` node (entry point)          |
| Pink         | `#FFB6C1` | `out` node (exit point)          |
| Yellow       | `#FFFACD` | Branch node (out-degree > 1)     |
| Light gray   | `#F5F5F5` | Sequential node (out-degree <= 1)|

### 7.5 Reading wafer edges from a parquet file

```python
bkm_reader = BKM(wafer_id_label="wafer_id", loaf_label="recipe",
                  tkin_label="tkin_time", tkout_label="tkout_time")

wafer_id, edges, loaf_sequence = bkm_reader.read_wafer_edges(
    path="bkm_results/parquets/W01.parquet"
)
# wafer_id      = "W01"
# edges         = [("in","a"), ("a","b"), ("b","c"), ("c","out")]
# loaf_sequence = ["a", "b", "c"]
```

### 7.6 Generating sample parquet files

```python
summary_df, all_data_df = BKM.generate_sample_parquets(folder="bkm_results/parquets")
```

Generates 12 wafer parquet files (W01-W12):

| Wafer | Recipe steps          | Flow type  |
|-------|-----------------------|------------|
| W01   | a -> b -> c           | Sequential |
| W02   | a -> b -> d           | Sequential |
| W03   | a -> b -> c           | Sequential |
| W04   | a -> e -> f -> g      | Sequential |
| W05   | a -> e -> f -> g      | Sequential |
| W06   | a -> e -> h -> g      | Sequential |
| W07   | a -> e -> h -> g      | Sequential |
| W08   | a -> i -> g           | Sequential |
| W09   | a -> i -> g           | Sequential |
| W10   | a -> b -> d           | Sequential |
| W11   | a -> b -> (c AND d)   | Branching  |
| W12   | a -> b -> (c AND d)   | Branching  |

---

## 8. BKM Class API Reference

### 8.1 Constructor

```python
BKM(
    version: str = "unnamed",
    process_data: Optional[Dict[str, List[str]]] = None,
    wafer_id_label: str = "wafer_id",
    tkin_label: str = "tkin_time",
    tkout_label: str = "tkout_time",
    loaf_label: str = "loaf",
)
```

### 8.2 Methods and properties

| Method / Property              | Returns                         | Description                                      |
|--------------------------------|---------------------------------|--------------------------------------------------|
| `fingerprint()`               | `str`                           | SHA-256 hash of canonical DAG structure           |
| `validate()`                  | `List[str]`                     | Check DAG integrity; returns warnings             |
| `save(path)`                  | `None`                          | Serialize BKM to JSON file                        |
| `BKM.load(path)`              | `BKM`                           | Deserialize BKM from JSON file (classmethod)      |
| `read_wafer_edges(path)`      | `(str, List[edge], List[str])`  | Infer edges from a wafer parquet file             |
| `read_wafer_edges_from_df(df)`| `(str, List[edge], List[str])`  | Infer edges from a preprocessed DataFrame         |
| `read_wafer_path(path)`       | `(str, List[str])`              | Extract recipe sequence from a wafer parquet      |
| `match_path(loaf_sequence)`   | `bool`                          | Check if sequence matches any in-to-out path      |
| `match_edges(edges)`          | `bool`                          | Check if edge set is a subset of BKM edges        |
| `infer_from_parquets(folder)` | `BKM`                           | Infer BKM DAG from multiple parquets (classmethod)|
| `print_graph()`               | `str`                           | Text-based DAG tree with box-drawing characters   |
| `render(filename, fmt)`       | `Optional[str]`                 | Graphviz visualization (PNG/SVG/PDF)              |
| `summary()`                   | `Dict[str, Any]`                | Node/edge counts, paths, branch/merge nodes       |
| `all_path_fingerprints()`     | `Dict[str, List[str]]`          | All in-to-out path fingerprints                   |
| `compute_path_fingerprint()`  | `str`                           | SHA-256 of a recipe sequence (staticmethod)       |
| `.graph`                      | `nx.DiGraph`                    | Property: internal NetworkX directed graph        |
| `.nodes`                      | `Dict[str, ProcessNode]`        | Property: all ProcessNode objects                 |
