from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

REDUCTION_SCRIPT = "/SNS/EQSANS/shared/script/eqsanstools/eqsans_reduction.py"
DRTSANS_CMD = "drtsans"


@dataclass
class ReductionResult:
    success: bool
    json_path: str
    output_file: str
    elapsed_seconds: float
    stdout: str
    stderr: str
    return_code: int
    log_file: str = ""
    err_file: str = ""
    cancelled: bool = False


def run_reduction(
    json_path: str,
    cancel_event: threading.Event | None = None,
    proc_ref: list[subprocess.Popen] | None = None,
) -> ReductionResult:
    """Run a single reduction job.

    cancel_event: set it from another thread to kill the subprocess mid-run.
    proc_ref:     a single-element list; we store the Popen object here so the
                  caller can kill it independently if needed.
    """
    base = Path(json_path).stem
    output_dir = str(Path(json_path).parent)
    log_path = os.path.join(output_dir, f"{base}.out")
    err_path = os.path.join(output_dir, f"{base}.err")

    t0 = time.time()
    try:
        proc = subprocess.Popen(
            [DRTSANS_CMD, REDUCTION_SCRIPT, json_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if proc_ref is not None:
            proc_ref.clear()
            proc_ref.append(proc)

        while True:
            try:
                stdout, stderr = proc.communicate(timeout=1.0)
                break
            except subprocess.TimeoutExpired:
                if cancel_event is not None and cancel_event.is_set():
                    proc.kill()
                    stdout, stderr = proc.communicate()
                    elapsed = time.time() - t0
                    with open(err_path, "w") as f:
                        f.write("Cancelled by user.\n" + stderr)
                    return ReductionResult(
                        success=False, json_path=json_path, output_file="",
                        elapsed_seconds=elapsed, stdout=stdout, stderr="Cancelled by user.",
                        return_code=-99, log_file="", err_file=err_path, cancelled=True,
                    )

        elapsed = time.time() - t0

        with open(log_path, "w") as f:
            f.write(stdout)
        with open(err_path, "w") as f:
            f.write(stderr)

        return ReductionResult(
            success=proc.returncode == 0,
            json_path=json_path,
            output_file="",
            elapsed_seconds=elapsed,
            stdout=stdout,
            stderr=stderr,
            return_code=proc.returncode,
            log_file=log_path,
            err_file=err_path,
        )
    except FileNotFoundError:
        elapsed = time.time() - t0
        err_msg = f"'{DRTSANS_CMD}' not found. Activate the drtsans conda environment first."
        with open(err_path, "w") as f:
            f.write(err_msg)
        return ReductionResult(
            success=False, json_path=json_path, output_file="",
            elapsed_seconds=elapsed, stdout="", stderr=err_msg,
            return_code=-1, log_file="", err_file=err_path,
        )
