"""
(copyLeft) yRocket, 202.4.10
bkm.py - BKM (Best Known Method) Process Flow DAG Manager

Manages semiconductor process flows as Directed Acyclic Graphs (DAGs).
Each process flow consists of named nodes connected by directed edges.
A BKM version is identified by its DAG structure fingerprint.
Any path from 'in' to 'out' within the same DAG belongs to the same BKM version.

Path-based matching: pre-computes fingerprints for all possible in->out paths
so that a wafer's observed recipe sequence can be quickly matched to a BKM version.

Edge inference from parquet data uses tkin/tkout timing to detect
both sequential and parallel (branching) process flows.

Dependencies: networkx, pandas, graphviz (optional)
Usage: python bkm.py --folder bkm_results
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# Fix Windows console encoding for box-drawing characters
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

import networkx as nx
import pandas as pd

try:
    from graphviz import Digraph as GvDigraph

    HAS_GRAPHVIZ = True
except ImportError:
    HAS_GRAPHVIZ = False


# ═══════════════════════════════════════════════════════════════════════════════
#  Data Structures
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ProcessNode:
    name: str
    next_steps: List[str] = field(default_factory=list)

    def get_normalized_next(self) -> Tuple[str, ...]:
        """Return sorted tuple of next steps for deterministic comparison."""
        return tuple(sorted(self.next_steps))


# ═══════════════════════════════════════════════════════════════════════════════
#  BKM Class
# ═══════════════════════════════════════════════════════════════════════════════

class BKM:
    """Manages a semiconductor process flow as a DAG.

    All node names are stored in lowercase internally.
    A BKM version is identified by its graph structure fingerprint.
    Any path from 'in' to 'out' within the same BKM belongs to the same version.

    Path fingerprints are pre-computed for fast wafer-to-BKM matching.
    """

    def __init__(self, version: str = "unnamed",
                 process_data: Optional[Dict[str, List[str]]] = None,
                 wafer_id_label: str = "wafer_id",
                 tkin_label: str = "tkin_time",
                 tkout_label: str = "tkout_time",
                 loaf_label: str = "loaf"):
        """
        Args:
            version: BKM version identifier string.
            process_data: Dict mapping node name -> list of successor node names.
                          Example: {"in": ["a"], "a": ["b", "c"], "b": ["out"], ...}
            wafer_id_label: Column name for wafer ID in parquet files.
            loaf_label: Column name for recipe/tool in parquet files.
            tkin_label: Column name for track-in time in parquet files.
            tkout_label: Column name for track-out time in parquet files.
        """
        self.version: str = version
        self.wafer_id_label: str = wafer_id_label
        self.loaf_label: str = loaf_label
        self.tkin_label: str = tkin_label
        self.tkout_label: str = tkout_label
        self._graph: nx.DiGraph = nx.DiGraph()
        self._nodes: Dict[str, ProcessNode] = {}
        self._fingerprint_cache: Optional[str] = None
        self._path_fingerprints_cache: Optional[Dict[str, List[str]]] = None
        if process_data is not None:
            self._build(process_data)

    # ── Build ──────────────────────────────────────────────────────────────

    def _build(self, process_data: Dict[str, List[str]]) -> None:
        """Build the internal DiGraph from process_data dict.
        All node names are normalized to lowercase.
        """
        self._graph.clear()
        self._nodes.clear()
        self._fingerprint_cache = None
        self._path_fingerprints_cache = None

        for name, next_steps in process_data.items():
            name_lower = name.lower()
            next_lower = [ns.lower() for ns in next_steps]
            node = ProcessNode(name=name_lower, next_steps=list(next_lower))
            self._nodes[name_lower] = node
            self._graph.add_node(name_lower)
            for ns in next_lower:
                self._graph.add_edge(name_lower, ns)

        # Add terminal nodes that only appear as edge targets (e.g. "out")
        for node_name in list(self._graph.nodes):
            if node_name not in self._nodes:
                self._nodes[node_name] = ProcessNode(name=node_name)

        self.validate()

    # ── Validation ─────────────────────────────────────────────────────────

    def validate(self) -> List[str]:
        """Validate the DAG structure. Raises ValueError on fatal errors.
        Returns a list of warning messages.
        """
        warnings: List[str] = []

        if not nx.is_directed_acyclic_graph(self._graph):
            cycle = nx.find_cycle(self._graph, orientation="original")
            raise ValueError(f"Graph has a cycle: {cycle}")

        if "in" not in self._graph:
            raise ValueError("Node 'in' is missing from the process flow")
        if self._graph.in_degree("in") != 0:
            raise ValueError(f"Node 'in' has in-degree {self._graph.in_degree('in')}, expected 0")

        if "out" not in self._graph:
            raise ValueError("Node 'out' is missing from the process flow")
        if self._graph.out_degree("out") != 0:
            raise ValueError(f"Node 'out' has out-degree {self._graph.out_degree('out')}, expected 0")

        for node in self._graph.nodes:
            if node != "out" and not nx.has_path(self._graph, node, "out"):
                raise ValueError(f"Node '{node}' cannot reach 'out'")

        for node in self._graph.nodes:
            if node != "in" and self._graph.in_degree(node) == 0:
                warnings.append(f"Node '{node}' has in-degree 0 (unreachable from in)")
            if node != "out" and self._graph.out_degree(node) == 0:
                warnings.append(f"Node '{node}' has out-degree 0 but is not out")

        return warnings

    # ── Fingerprint & Comparison ───────────────────────────────────────────

    def fingerprint(self) -> str:
        """Compute a deterministic SHA-256 fingerprint of the DAG structure.
        Based on sorted adjacency list (node names and edges only).
        """
        if self._fingerprint_cache is not None:
            return self._fingerprint_cache

        lines = []
        for name in sorted(self._graph.nodes):
            successors = sorted(self._graph.successors(name))
            lines.append(f"{name}|{','.join(successors)}")

        canonical = "\n".join(lines)
        self._fingerprint_cache = hashlib.sha256(canonical.encode()).hexdigest()
        return self._fingerprint_cache

    @staticmethod
    def compute_path_fingerprint(loaf_sequence: List[str]) -> str:
        """Compute SHA-256 fingerprint for a specific recipe sequence (path).

        Args:
            loaf_sequence: List of recipe names in order (excluding 'in' and 'out').
        """
        normalized = [t.lower() for t in loaf_sequence]
        canonical = ",".join(normalized)
        return hashlib.sha256(canonical.encode()).hexdigest()

    def all_path_fingerprints(self) -> Dict[str, List[str]]:
        """Pre-compute fingerprints for ALL possible in->out paths.

        Returns:
            Dict mapping path_fingerprint -> list of recipe names (excluding in/out).
            This allows O(1) lookup when matching a wafer to this BKM.
        """
        if self._path_fingerprints_cache is not None:
            return self._path_fingerprints_cache

        result: Dict[str, List[str]] = {}
        all_paths = list(nx.all_simple_paths(self._graph, "in", "out"))

        for path in all_paths:
            recipes = [n for n in path if n not in ("in", "out")]
            fp = self.compute_path_fingerprint(recipes)
            result[fp] = recipes

        self._path_fingerprints_cache = result
        return result

    def match_path(self, loaf_sequence: List[str]) -> bool:
        """Check if a wafer's recipe sequence matches any path in this BKM.

        Args:
            loaf_sequence: List of recipe names the wafer visited (excluding in/out).
        Returns:
            True if the sequence matches one of the BKM's in->out paths.
        """
        fp = self.compute_path_fingerprint(loaf_sequence)
        return fp in self.all_path_fingerprints()

    def match_edges(self, edges: Set[Tuple[str, str]]) -> bool:
        """Check if a wafer's inferred edges are all present in this BKM's DAG.

        Args:
            edges: Set of (src, dst) edges inferred from a wafer's timing data.
                   Should NOT include virtual 'in'/'out' edges.
        Returns:
            True if all wafer edges exist in this BKM's graph.
        """
        bkm_edges = set(self._graph.edges)
        return edges.issubset(bkm_edges)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, BKM):
            return NotImplemented
        return self.fingerprint() == other.fingerprint()

    def __hash__(self) -> int:
        return int(self.fingerprint()[:16], 16)

    def __repr__(self) -> str:
        return (f"BKM(version='{self.version}', nodes={self._graph.number_of_nodes()}, "
                f"edges={self._graph.number_of_edges()}, fp={self.fingerprint()[:12]}...)")

    # ── Save / Load (JSON) ─────────────────────────────────────────────────

    def save(self, path: str | Path) -> None:
        """Save the process flow to a JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "version": self.version,
            "fingerprint": self.fingerprint(),
            "labels": {
                "wafer_id": self.wafer_id_label,
                "recipe": self.loaf_label,
                "tkin_time": self.tkin_label,
                "tkout_time": self.tkout_label,
            },
            "nodes": {},
        }
        for name in sorted(self._nodes.keys()):
            node = self._nodes[name]
            data["nodes"][name] = {
                "next_steps": node.next_steps,
            }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"[BKM] Saved to {path}")

    @classmethod
    def load(cls, path: str | Path) -> BKM:
        """Load a process flow from a JSON file."""
        path = Path(path)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        bkm_version = data.get("version", "unnamed")
        labels = data.get("labels", {})

        process_data: Dict[str, List[str]] = {}
        for name, info in data["nodes"].items():
            next_steps = info["next_steps"]
            if next_steps or name == "in":
                process_data[name] = next_steps

        bkm = cls(version=bkm_version, process_data=process_data,
                   wafer_id_label=labels.get("wafer_id", "wafer_id"),
                   loaf_label=labels.get("recipe", "recipe"),
                   tkin_label=labels.get("tkin_time", "tkin_time"),
                   tkout_label=labels.get("tkout_time", "tkout_time"))

        stored_fp = data.get("fingerprint")
        if stored_fp and stored_fp != bkm.fingerprint():
            print(f"[BKM] WARNING: Stored fingerprint mismatch! "
                  f"stored={stored_fp[:16]}... computed={bkm.fingerprint()[:16]}...")

        print(f"[BKM] Loaded from {path}")
        return bkm

    # ══════════════════════════════════════════════════════════════════════════
    #  Timing-based Edge Inference from Parquet Data
    # ══════════════════════════════════════════════════════════════════════════
    #
    #  Predecessor Detection Rule (tkin/tkout timing)
    #  ───────────────────────────────────────────────
    #
    #  Given process steps with track-in (tkin) and track-out (tkout) times,
    #  we determine each step's predecessor by finding the step with the
    #  LATEST tkout_time that is <= this step's tkin_time.
    #
    #  Example 1: Sequential flow (A → B → C)
    #
    #    A: |====tkin====tkout====|
    #    B:                         |====tkin====tkout====|
    #    C:                                                 |====tkin====tkout====|
    #
    #    - B.tkin > A.tkout → A is predecessor of B  (edge: A→B)
    #    - C.tkin > B.tkout → B is predecessor of C  (edge: B→C)
    #
    #  Example 2: Branching flow (A → [B, C])
    #
    #    A: |====tkin====tkout====|
    #    B:                         |====tkin=========tkout=========|
    #    C:                              |====tkin====tkout====|
    #
    #    Timeline: A.tkout < B.tkin < C.tkin < B.tkout
    #
    #    - For B: latest tkout <= B.tkin → A.tkout ✓  → edge: A→B
    #    - For C: latest tkout <= C.tkin → A.tkout ✓  (B.tkout > C.tkin, B 아직 진행중)
    #                                                  → edge: A→C
    #    - Result: A has next_steps = [B, C]  (A에서 분기)
    #
    #    즉, B가 아직 진행중(B.tkout > C.tkin)이므로 B는 C의 predecessor가 될 수 없고,
    #    A가 B와 C 모두의 predecessor가 됨 → A에서 B, C로의 분기가 감지됨.
    #
    #  Terminal steps (no successor within the wafer) get edge → "out".
    #  Steps with no predecessor (first steps) get edge "in" →.
    # ══════════════════════════════════════════════════════════════════════════

    def read_wafer_edges(self, path: str | Path,
                         ) -> Tuple[str, List[Tuple[str, str]], List[str]]:
        """Read a single-wafer parquet and infer edges from tkin/tkout timing.

        Uses the predecessor detection rule described above:
        For each step X, predecessor = the step with the latest tkout <= X.tkin.
        This correctly detects both sequential and parallel (branching) flows.

        Uses column labels from self (wafer_id_label, loaf_label,
        tkin_label, tkout_label) set at __init__.

        Args:
            path: Path to parquet file (one wafer_id per file).

        Returns:
            (wafer_id, edges, loaf_sequence)
            - edges: List of (src, dst) tuples including virtual 'in'/'out'.
            - loaf_sequence: Flat list of recipes sorted by tkin_time (for display).
        """
        wid_col = self.wafer_id_label
        loaf_col = self.loaf_label
        tkin_col = self.tkin_label
        tkout_col = self.tkout_label

        path = Path(path)
        df = pd.read_parquet(path)

        required_cols = {wid_col, loaf_col, tkin_col, tkout_col}
        missing = required_cols - set(df.columns)
        if missing:
            raise ValueError(f"Missing columns in {path}: {missing}")

        df[loaf_col] = df[loaf_col].str.lower()
        df[tkin_col] = pd.to_datetime(df[tkin_col])
        df[tkout_col] = pd.to_datetime(df[tkout_col])
        df = df.sort_values(tkin_col).reset_index(drop=True)

        wafer_id = str(df[wid_col].iloc[0])
        loaf_sequence = df[loaf_col].tolist()

        # ── Step 1: Find each step's predecessor via timing ───────────
        #
        #   For step X at index idx:
        #     predecessor = argmax(steps[j].tkout) where steps[j].tkout <= X.tkin
        #                   (the step that finished most recently before X started)
        #
        #   If no such step exists → X is a start step → edge: "in" → X
        #
        steps = df[[loaf_col, tkin_col, tkout_col]].values.tolist()
        edges: List[Tuple[str, str]] = []
        has_successor: Set[str] = set()  # recipes that appear as a predecessor

        for idx, (recipe, tkin, tkout) in enumerate(steps):
            best_pred = None
            best_pred_tkout = None

            for j, (r2, tkin2, tkout2) in enumerate(steps):
                if j == idx:
                    continue
                # Candidate predecessor: finished before this step started
                if tkout2 <= tkin:
                    if best_pred_tkout is None or tkout2 > best_pred_tkout:
                        best_pred = r2
                        best_pred_tkout = tkout2

            if best_pred is None:
                # No predecessor → this is a start step
                edges.append(("in", recipe))
            else:
                edges.append((best_pred, recipe))
                has_successor.add(best_pred)

        # ── Step 2: Find terminal steps → edge to "out" ──────────────
        #
        #   A terminal step is one that does not appear as a predecessor
        #   of any other step within this wafer.
        #
        all_recipes_in_wafer = {recipe for recipe, _, _ in steps}
        terminal_recipes = all_recipes_in_wafer - has_successor
        for r in terminal_recipes:
            edges.append((r, "out"))

        return wafer_id, edges, loaf_sequence

    def read_wafer_edges_from_df(self, df: pd.DataFrame,
                                 ) -> Tuple[str, List[Tuple[str, str]], List[str]]:
        """Infer edges from an already-preprocessed DataFrame (no file I/O).

        Same logic as read_wafer_edges but operates on a DataFrame that
        already has the required columns (wafer_id_label, loaf_label,
        tkin_label, tkout_label).

        The DataFrame should contain only the unique process steps
        (use drop_duplicates on recipe/tkin/tkout before calling).

        Args:
            df: Preprocessed DataFrame with required columns.

        Returns:
            (wafer_id, edges, loaf_sequence)
        """
        wid_col = self.wafer_id_label
        tkin_col = self.tkin_label
        tkout_col = self.tkout_label
        loaf_col = self.loaf_label

        df = df.copy()
        df[tkin_col] = pd.to_datetime(df[tkin_col])
        df[tkout_col] = pd.to_datetime(df[tkout_col])
        df[loaf_col] = df[loaf_col].astype(str).str.lower()
        df = df.sort_values(tkin_col).reset_index(drop=True)

        wafer_id = str(df[wid_col].iloc[0])
        loaf_sequence = df[loaf_col].tolist()

        steps = df[[loaf_col, tkin_col, tkout_col]].values.tolist()
        edges: List[Tuple[str, str]] = []
        has_successor: Set[str] = set()

        for idx, (recipe, tkin, tkout) in enumerate(steps):
            best_pred = None
            best_pred_tkout = None

            for j, (r2, tkin2, tkout2) in enumerate(steps):
                if j == idx:
                    continue
                if tkout2 <= tkin:
                    if best_pred_tkout is None or tkout2 > best_pred_tkout:
                        best_pred = r2
                        best_pred_tkout = tkout2

            if best_pred is None:
                edges.append(("in", recipe))
            else:
                edges.append((best_pred, recipe))
                has_successor.add(best_pred)

        all_recipes_in_wafer = {recipe for recipe, _, _ in steps}
        terminal_recipes = all_recipes_in_wafer - has_successor
        for r in terminal_recipes:
            edges.append((r, "out"))

        return wafer_id, edges, loaf_sequence

    def read_wafer_path(self, path: str | Path,
                        ) -> Tuple[str, List[str]]:
        """Read a single-wafer parquet file and extract the recipe sequence.

        Uses column labels from self (wafer_id_label, loaf_label,
        tkin_label, tkout_label) set at __init__.

        Args:
            path: Path to parquet file (one wafer_id per file).
        Returns:
            (wafer_id, loaf_sequence) where loaf_sequence is sorted by tkin_time.
        """
        wid_col = self.wafer_id_label
        loaf_col = self.loaf_label
        tkin_col = self.tkin_label

        path = Path(path)
        df = pd.read_parquet(path)

        required_cols = {wid_col, loaf_col, tkin_col}
        missing = required_cols - set(df.columns)
        if missing:
            raise ValueError(f"Missing columns in {path}: {missing}")

        df[loaf_col] = df[loaf_col].str.lower()
        df[tkin_col] = pd.to_datetime(df[tkin_col])
        df = df.sort_values(tkin_col).reset_index(drop=True)

        wafer_id = str(df[wid_col].iloc[0])
        loaf_sequence = df[loaf_col].tolist()

        # Deduplicate consecutive duplicates (keep order)
        deduped: List[str] = []
        for r in loaf_sequence:
            if not deduped or deduped[-1] != r:
                deduped.append(r)

        return wafer_id, deduped

    # ── Infer BKM from multiple wafer parquets ─────────────────────────────

    @classmethod
    def infer_from_parquets(cls,
                            folder: str | Path,
                            version: str = "inferred",
                            wafer_id_label: str = "wafer_id",
                            loaf_label: str = "recipe",
                            tkin_label: str = "tkin_time",
                            tkout_label: str = "tkout_time",
                            ) -> BKM:
        """Infer a BKM process flow DAG from multiple single-wafer parquet files.

        Reads all .parquet files in the folder, infers edges from each wafer's
        tkin/tkout timing, then merges all edges into a single DAG.

        Args:
            folder: Folder containing .parquet files (one wafer per file).
            version: BKM version string to assign.
            wafer_id_label: Column name for wafer ID in parquet.
            loaf_label: Column name for recipe/tool in parquet.
            tkin_label: Column name for track-in time.
            tkout_label: Column name for track-out time.

        Returns:
            BKM instance with the inferred process flow.
        """
        import glob

        folder = Path(folder)
        files = sorted(glob.glob(str(folder / "*.parquet")))
        if not files:
            raise FileNotFoundError(f"No parquet files found in {folder}")

        print(f"[BKM] Inferring DAG from {len(files)} parquet files in {folder}/")

        # Create a temporary BKM to use its read_wafer_edges (needs label config)
        reader = cls(version=version,
                     wafer_id_label=wafer_id_label, loaf_label=loaf_label,
                     tkin_label=tkin_label, tkout_label=tkout_label)

        # Collect all edges from all wafers
        all_edges: Set[Tuple[str, str]] = set()

        for fpath in files:
            wf_id, edges, _ = reader.read_wafer_edges(fpath)
            for e in edges:
                all_edges.add(e)

        # Build process_data from merged edges
        successors: Dict[str, Set[str]] = {}
        for src, dst in all_edges:
            successors.setdefault(src, set()).add(dst)

        process_data: Dict[str, List[str]] = {
            node: sorted(succs) for node, succs in successors.items()
        }

        # Rebuild with inferred process_data
        reader._build(process_data)
        print(f"[BKM] Inferred: {reader._graph.number_of_nodes()} nodes, "
              f"{reader._graph.number_of_edges()} edges")
        return reader

    # ── Text Graph Printing ────────────────────────────────────────────────

    def print_graph(self) -> str:
        """Print the DAG as an indented tree with box-drawing characters.
        Collapses single-child chains into inline format (e.g. f -> g -> out).
        Returns the formatted string.
        """
        lines: List[str] = []
        visited: set = set()

        def _walk(name: str, prefix: str, is_last: bool, is_root: bool) -> None:
            if name in visited:
                if is_root:
                    lines.append(f"{name} (see above)")
                else:
                    connector = "\u2514\u2500 " if is_last else "\u251c\u2500 "
                    lines.append(f"{prefix}{connector}{name} (see above)")
                return

            chain_names: List[str] = []
            chain_labels: List[str] = []
            cur = name
            while True:
                chain_names.append(cur)
                chain_labels.append(cur)
                visited.add(cur)
                children = sorted(self._graph.successors(cur))
                if len(children) != 1:
                    break
                child = children[0]
                if child in visited:
                    chain_labels.append(f"{child} (see above)")
                    chain_names.append(child)
                    break
                cur = child

            chain_str = " -> ".join(chain_labels)

            if is_root:
                lines.append(chain_str)
            else:
                connector = "\u2514\u2500 " if is_last else "\u251c\u2500 "
                lines.append(f"{prefix}{connector}{chain_str}")

            tail = chain_names[-1]
            if tail in visited:
                children = sorted(self._graph.successors(tail))
            else:
                children = []

            if len(children) <= 1:
                return

            if is_root:
                child_prefix = prefix + "   "
            else:
                child_prefix = prefix + ("   " if is_last else "\u2502  ")

            for i, child in enumerate(children):
                _walk(child, child_prefix, i == len(children) - 1, False)

        _walk("in", "", True, True)

        result = "\n".join(lines)
        print(result)
        return result

    # ── Graphviz Rendering ─────────────────────────────────────────────────

    def render(self, filename: str = "process_flow", fmt: str = "png",
               view: bool = False) -> Optional[str]:
        """Render the DAG as an image using graphviz."""
        if not HAS_GRAPHVIZ:
            print("[BKM] graphviz Python package not installed. Skipping render.")
            return None

        dot = GvDigraph(format=fmt)
        dot.attr(rankdir="TB", fontname="Arial")
        dot.attr("node", shape="box", style="rounded,filled", fontname="Arial")

        for name in self._graph.nodes:
            n_children = self._graph.out_degree(name)
            if name == "in":
                dot.node(name, name, fillcolor="#90EE90", color="#228B22")
            elif name == "out":
                dot.node(name, name, fillcolor="#FFB6C1", color="#DC143C")
            elif n_children > 1:
                dot.node(name, name, fillcolor="#FFFACD", color="#DAA520")
            else:
                dot.node(name, name, fillcolor="#F5F5F5", color="#808080")

        for u, v in self._graph.edges:
            dot.edge(u, v)

        try:
            output_path = dot.render(filename, view=view, cleanup=True)
            print(f"[BKM] Rendered graph to {output_path}")
            return output_path
        except Exception as e:
            print(f"[BKM] Graphviz render failed: {e}")
            print("[BKM] Ensure Graphviz system binaries are installed and on PATH.")
            return None

    # ── Summary ────────────────────────────────────────────────────────────

    def summary(self) -> Dict[str, Any]:
        """Return a summary dict of the process flow."""
        all_paths = list(nx.all_simple_paths(self._graph, "in", "out"))
        branch_nodes = [n for n in self._graph.nodes
                        if self._graph.out_degree(n) > 1]
        merge_nodes = [n for n in self._graph.nodes
                       if self._graph.in_degree(n) > 1]

        return {
            "version": self.version,
            "node_count": self._graph.number_of_nodes(),
            "edge_count": self._graph.number_of_edges(),
            "paths_in_to_out": [" -> ".join(p) for p in all_paths],
            "path_count": len(all_paths),
            "branch_nodes": branch_nodes,
            "merge_nodes": merge_nodes,
            "fingerprint": self.fingerprint(),
            "path_fingerprints_count": len(self.all_path_fingerprints()),
        }

    # ── Properties ─────────────────────────────────────────────────────────

    @property
    def graph(self) -> nx.DiGraph:
        return self._graph

    @property
    def nodes(self) -> Dict[str, ProcessNode]:
        return self._nodes


# ═══════════════════════════════════════════════════════════════════════════════
#  Sample Data Generation (standalone function)
# ═══════════════════════════════════════════════════════════════════════════════

def generate_sample_parquets(
        folder: str | Path,
        wafer_id_label: str = "wafer_id",
        loaf_label: str = "recipe",
        tkin_label: str = "tkin_time",
        tkout_label: str = "tkout_time",
        base_time: Optional[Any] = None,
        step_duration: Optional[Any] = None,
        gap: Optional[Any] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Generate sample single-wafer parquet files representing the example flow.

    in -> a
       ├─ b
       │  ├─ c -> out
       │  └─ d -> out
       ├─ e
       │  ├─ f -> g -> out
       │  └─ h -> g -> out
       └─ i -> g -> out

    Creates one parquet file per wafer in the given folder.
    Columns: wafer_id, {loaf_label}, {tkin_label}, {tkout_label}
    Each recipe step: tkout = tkin + step_duration.

    Some wafers include parallel steps (e.g. W11: a -> b -> [c AND d])
    to demonstrate branching detection from timing overlap.

    Args:
        folder: Output folder for parquet files.
        wafer_id_label: Column name for wafer ID in parquet.
        loaf_label: Column name for recipe in parquet.
        tkin_label: Column name for track-in time.
        tkout_label: Column name for track-out time.
        base_time: Start datetime for the first wafer (default: 2025-08-01 08:00).
        step_duration: Duration of each recipe step (default: 60 min).
        gap: Gap between consecutive steps (default: 5 min).

    Returns:
        (file_summary_df, all_data_df)
    """
    from datetime import datetime, timedelta

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)

    # Apply defaults for optional timing parameters
    if base_time is None:
        base_time = datetime(2025, 8, 1, 8, 0, 0)
    if step_duration is None:
        step_duration = timedelta(minutes=60)   # tkout = tkin + 60 min
    if gap is None:
        gap = timedelta(minutes=5)              # gap between consecutive steps

    # wafer_paths: list of step specs.
    #   "recipe"              → sequential step
    #   ("recipe1", "recipe2") → parallel steps (same tkin, both follow previous)
    #
    # W01~W10: sequential-only paths (one path per wafer)
    # W11~W12: parallel steps demonstrating branch detection
    wafer_paths = {
        "W01": ["a", "b", "c"],             # in->a->b->c->out
        "W02": ["a", "b", "d"],             # in->a->b->d->out
        "W03": ["a", "b", "c"],             # same as W01
        "W04": ["a", "e", "f", "g"],        # in->a->e->f->g->out
        "W05": ["a", "e", "f", "g"],        # same as W04
        "W06": ["a", "e", "h", "g"],        # in->a->e->h->g->out
        "W07": ["a", "e", "h", "g"],        # same as W06
        "W08": ["a", "i", "g"],             # in->a->i->g->out
        "W09": ["a", "i", "g"],             # same as W08
        "W10": ["a", "b", "d"],             # same as W02
        "W11": ["a", "b", ("c", "d")],      # PARALLEL: b -> [c AND d]
        "W12": ["a", "b", ("c", "d")],      # same parallel path
    }

    all_rows = []
    file_list = []

    for wf_idx, (wf_id, steps) in enumerate(wafer_paths.items()):
        wf_start = base_time + timedelta(hours=wf_idx * 2)
        tkin = wf_start
        rows = []
        recipe_names = []

        for step in steps:
            if isinstance(step, tuple):
                # Parallel steps: all share the same tkin_time
                #   A.tkout < B.tkin = C.tkin → A is predecessor of both B and C
                #   B and C overlap in time (C.tkin < B.tkout)
                parallel_tkin = tkin
                max_tkout = parallel_tkin
                for recipe in step:
                    tkout = parallel_tkin + step_duration
                    rows.append({
                        wafer_id_label: wf_id,
                        loaf_label: recipe,
                        tkin_label: parallel_tkin.strftime("%Y-%m-%d %H:%M:%S"),
                        tkout_label: tkout.strftime("%Y-%m-%d %H:%M:%S"),
                    })
                    recipe_names.append(recipe)
                    if tkout > max_tkout:
                        max_tkout = tkout
                tkin = max_tkout + gap
            else:
                tkout = tkin + step_duration
                rows.append({
                    "wafer_id": wf_id,
                    loaf_label: step,
                    tkin_label: tkin.strftime("%Y-%m-%d %H:%M:%S"),
                    tkout_label: tkout.strftime("%Y-%m-%d %H:%M:%S"),
                })
                recipe_names.append(step)
                tkin = tkout + gap

        df = pd.DataFrame(rows)
        fname = f"{wf_id}.parquet"
        fpath = folder / fname
        df.to_parquet(fpath, index=False)
        file_list.append({
            "file": fname,
            "wafer_id": wf_id,
            "recipes": " -> ".join(recipe_names),
            "n_steps": len(recipe_names),
        })
        all_rows.extend(rows)

    summary_df = pd.DataFrame(file_list)
    print(f"[BKM] Generated {len(wafer_paths)} parquet files in {folder}/")
    return summary_df, pd.DataFrame(all_rows)


# ═══════════════════════════════════════════════════════════════════════════════
#  Argument Parsing
# ═══════════════════════════════════════════════════════════════════════════════

def parse_args(verbose=True) -> argparse.Namespace:
    """Parse command-line arguments for training."""
    ap = argparse.ArgumentParser(
        description="BKM - Semiconductor process flow DAG manager")
    ap.add_argument("--folder", default="bkm_results",
                    help="Folder for saving/loading BKM files (default: bkm_results)")
    ap.add_argument("--wafer_id_label", default="wafer_id",
                    help="Column name for wafer ID in parquet (default: wafer_id)")
    ap.add_argument("--loaf_label", default="recipe",
                    help="Column name for recipe/tool in parquet (default: recipe)")
    ap.add_argument("--tkin_time_label", default="tkin_time",
                    help="Column name for track-in time in parquet (default: tkin_time)")
    ap.add_argument("--tkout_time_label", default="tkout_time",
                    help="Column name for track-out time in parquet (default: tkout_time)")

    args = ap.parse_args()
    if verbose:
        print('parsed_args=' + json.dumps(vars(args), indent=2))
    return args


# ═══════════════════════════════════════════════════════════════════════════════
#  Main (Demo)
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print(f"{'=' * 100}")
    print(f" BKM Process Flow DAG Manager - Demo")
    print(f"Python: {sys.executable}")
    print(f" Args:   {sys.argv[1:]}")
    print(f"{'=' * 100}\n")

    args = parse_args()
    folder = Path(args.folder)
    folder.mkdir(parents=True, exist_ok=True)
    wid_lbl = args.wafer_id_label
    recipe_lbl = args.loaf_label
    tkin_lbl = args.tkin_time_label
    tkout_lbl = args.tkout_time_label
    # Common label kwargs for BKM constructor
    label_kwargs = dict(wafer_id_label=wid_lbl, loaf_label=recipe_lbl,
                        tkin_label=tkin_lbl, tkout_label=tkout_lbl)
    print(f"  wafer_id_label   = '{wid_lbl}'")
    print(f"  loaf_label     = '{recipe_lbl}'")
    print(f"  tkin_time_label  = '{tkin_lbl}'")
    print(f"  tkout_time_label = '{tkout_lbl}'\n")

    # ── 1. Define BKM process flow (manual) ───────────────────────────
    print("[1] Defining BKM process flow (version='v1.0')...")
    process_data = {
        "in": ["a"],
        "a": ["b", "e", "i"],
        "b": ["c", "d"],
        "c": ["out"],
        "d": ["out"],
        "e": ["f", "h"],
        "f": ["g"],
        "h": ["g"],
        "i": ["g"],
        "g": ["out"],
    }
    bkm_manual = BKM(version="v1.0", process_data=process_data, **label_kwargs)
    print(f"  {bkm_manual}")
    print("-" * 50)
    bkm_manual.print_graph()
    print("-" * 50)
    print()

    # ── 2. Generate sample parquet files ──────────────────────────────
    parquet_folder = folder / "wafers"
    print(f"[2] Generating sample parquet files in {parquet_folder}/")
    from datetime import datetime, timedelta
    file_summary_df, all_data_df = generate_sample_parquets(
        parquet_folder,
        wafer_id_label=wid_lbl, loaf_label=recipe_lbl,
        tkin_label=tkin_lbl, tkout_label=tkout_lbl,
        base_time=datetime(2025, 8, 1, 8, 0, 0),
        step_duration=timedelta(minutes=60),
        gap=timedelta(minutes=5),
    )
    print()

    print("  Generated files:")
    print(file_summary_df.to_string(index=False))
    print()

    # Show one sequential wafer (W01)
    print("  Example (sequential): W01.parquet")
    df_w01 = pd.read_parquet(parquet_folder / "W01.parquet")
    print(df_w01.to_string(index=True))
    print()

    # Show one parallel wafer (W11)
    print("  Example (parallel branch): W11.parquet")
    df_w11 = pd.read_parquet(parquet_folder / "W11.parquet")
    print(df_w11.to_string(index=True))
    print("  ^ Note: c and d share the same tkin_time (parallel after b)")
    print()

    # ── 3. Edge inference demo on individual wafers ───────────────────
    print("[3] Edge inference from timing (read_wafer_edges):")
    for fname in ["W01.parquet", "W04.parquet", "W11.parquet"]:
        wf_id, edges, recipes = bkm_manual.read_wafer_edges(
            parquet_folder / fname)
        edges_str = ", ".join(f"{s}->{d}" for s, d in edges)
        print(f"  {fname}: {wf_id}  recipes={recipes}")
        print(f"    edges: [{edges_str}]")
    print()

    # ── 4. Infer BKM DAG from all wafer files ─────────────────────────
    print("[4] Inferring BKM from all wafer parquet files...")
    bkm_inferred = BKM.infer_from_parquets(
        parquet_folder, version="v1.0-inferred", **label_kwargs)
    print(f"  {bkm_inferred}")
    print("-" * 50)
    bkm_inferred.print_graph()
    print("-" * 50)
    print()

    # ── 5. Compare manual vs inferred ─────────────────────────────────
    print("[5] Comparison: manual vs inferred:")
    print(f"  manual   fp: {bkm_manual.fingerprint()[:32]}...")
    print(f"  inferred fp: {bkm_inferred.fingerprint()[:32]}...")
    print(f"  Same DAG? {bkm_manual == bkm_inferred}")
    print()

    # ── 6. Match wafers using path fingerprints ───────────────────────
    print("[6] Path-based matching (all paths -> same BKM version):")
    path_fps = bkm_manual.all_path_fingerprints()
    for fp, recipes in path_fps.items():
        print(f"  {fp[:16]}...  {' -> '.join(recipes)}")
    print()

    import glob
    wafer_files = sorted(glob.glob(str(parquet_folder / "*.parquet")))
    for wf_path in wafer_files:
        wf_id, recipe_seq = bkm_manual.read_wafer_path(wf_path)
        matched = bkm_manual.match_path(recipe_seq)
        status = f"MATCH (v={bkm_manual.version})" if matched else "NO MATCH"
        print(f"  {Path(wf_path).name}: {wf_id} [{' -> '.join(recipe_seq)}] => {status}")
    print()

    # ── 7. Edge-based matching for parallel wafers ────────────────────
    print("[7] Edge-based matching (for wafers with parallel steps):")
    for fname in ["W01.parquet", "W11.parquet"]:
        wf_id, edges, recipes = bkm_manual.read_wafer_edges(
            parquet_folder / fname)
        # Convert to set, exclude in/out for comparison
        inner_edges = {(s, d) for s, d in edges if s != "in" and d != "out"}
        matched = bkm_manual.match_edges(inner_edges)
        print(f"  {fname}: {wf_id}  inner_edges={inner_edges}")
        print(f"    match_edges={matched}")
    print()

    # ── 8. Non-matching test ──────────────────────────────────────────
    print("[8] Non-matching tests:")
    print(f"  Unknown path ['a','x','z']: match={bkm_manual.match_path(['a', 'x', 'z'])}")
    fake_edges = {("a", "x"), ("x", "z")}
    print(f"  Unknown edges {fake_edges}: match={bkm_manual.match_edges(fake_edges)}")
    print()

    # ── 9. Summary ────────────────────────────────────────────────────
    print("[9] Summary:")
    summary = bkm_manual.summary()
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print()

    # ── 10. Save & reload ─────────────────────────────────────────────
    json_path = folder / "bkm_v1.json"
    print(f"[10] Save & reload test:")
    bkm_manual.save(json_path)
    bkm_reloaded = BKM.load(json_path)
    print(f"  Same? {bkm_manual == bkm_reloaded}")
    print()

    # ── 11. Render graphviz ───────────────────────────────────────────
    print("[11] Rendering graphviz image...")
    img_path = bkm_inferred.render(str(folder / "bkm_v1"), fmt="png", view=False)
    if img_path:
        print(f"  Image saved to: {img_path}")
    print()

    print(f"{'=' * 100}")
    print(" Demo complete!")
    print(f"{'=' * 100}")

