"""
utils.py - Lightweight helpers used by wafer-bkm.
"""
from __future__ import annotations

import sys
import time
from datetime import timedelta
from pathlib import Path
from typing import Union


class TeeOutput:
    """Redirect stdout and stderr to both the terminal and a single log file.

    Examples
    --------
    >>> import sys
    >>> sys.stdout = sys.stderr = TeeOutput('app.log')
    """

    def __init__(self, filename: Union[str, Path]) -> None:
        self._orig_stdout = sys.stdout
        self._orig_stderr = sys.stderr
        self.log = open(filename, "w", encoding="utf-8")

    def write(self, message: str) -> None:
        self._orig_stdout.write(message)
        self.log.write(message)

    def flush(self) -> None:
        self._orig_stdout.flush()
        self._orig_stderr.flush()
        self.log.flush()

    def isatty(self) -> bool:
        return self._orig_stdout.isatty()


class MyTimer:
    """Simple wall-clock timer with a print-on-start/stop convenience."""

    def __init__(self, *, task_name: str = 'Task', verbose: bool = True) -> None:
        self.task_name = task_name
        self.verbose = verbose
        self.t_start: Union[float, None] = None
        self.t_stop: Union[float, None] = None
        self.elapsed: Union[float, None] = None

    def start(self) -> 'MyTimer':
        self.t_start = time.perf_counter()
        self.t_stop = None
        self.elapsed = None
        if self.verbose:
            now = time.strftime("%Y-%m-%d %H:%M:%S (%Z)")
            print(f"--- [{self.task_name}] Started at {now} ---\n")
        return self

    def stop(self, *, stop_message: str = 'Stopped') -> Union[float, None]:
        if self.t_start is None:
            if self.verbose:
                print(f"\n--- [{self.task_name}] Error: Timer was never started. ---")
            return None

        self.t_stop = time.perf_counter()
        self.elapsed = self.t_stop - self.t_start

        formatted_time = self.get_formatted_time()
        if self.verbose:
            print(f"\n--- [{self.task_name}] {stop_message} | Duration: {formatted_time} ---")
        return self.elapsed

    def end(self) -> None:
        self.stop(stop_message='Ended')

    def get_formatted_time(self) -> str:
        current_elapsed = self.elapsed
        if current_elapsed is None and self.t_start is not None:
            current_elapsed = time.perf_counter() - self.t_start
        if current_elapsed is None:
            return "00:00:00"
        return str(timedelta(seconds=current_elapsed)).split(".")[0]

    def __enter__(self) -> 'MyTimer':
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()

    def __str__(self) -> str:
        return self.get_formatted_time()


def my_script_stem() -> str:
    """Return the stem (no extension) of the running script's filename."""
    return Path(sys.argv[0]).stem


def my_script_name() -> str:
    """Return the running script's filename (with extension)."""
    return Path(sys.argv[0]).name
