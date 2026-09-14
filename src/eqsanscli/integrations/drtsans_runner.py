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

DRTSANS_VERSIONS = {
    "default": ["drtsans"],
    "sans": ["drtsans"],
    "dev": ["drtsans", "--dev"],
    "qa": ["drtsans", "--qa"],
}


def get_drtsans_cmd(version: str = "default") -> list[str]:
    return list(DRTSANS_VERSIONS.get(version, DRTSANS_VERSIONS["default"]))


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
    note: str = ""   # non-fatal caveat on an otherwise-successful run


def run_reduction(
    json_path: str,
    cancel_event: threading.Event | None = None,
    proc_ref: list[subprocess.Popen] | None = None,
    drtsans_version: str = "default",
    progress_cb=None,
) -> ReductionResult:
    """Run a single reduction job.

    cancel_event: set it from another thread to kill the subprocess mid-run.
    proc_ref:     a single-element list; we store the Popen object here so the
                  caller can kill it independently if needed.
    progress_cb:  called with each stdout line as it arrives, so the caller can
                  surface live progress (a long time-slice run prints one
                  `SaveNexus to …_<slice>_processed.nxs` per slice).

    Output is streamed to the `.out`/`.err` files **as it arrives** (drtsans is
    run with PYTHONUNBUFFERED), not buffered until the end — so the files grow
    during the run and can be watched with `tail -f`, and cancellation stays
    responsive.
    """
    base = Path(json_path).stem
    output_dir = str(Path(json_path).parent)
    log_path = os.path.join(output_dir, f"{base}.out")
    err_path = os.path.join(output_dir, f"{base}.err")

    t0 = time.time()
    try:
        cmd = get_drtsans_cmd(drtsans_version) + [REDUCTION_SCRIPT, json_path]
        env = {**os.environ, "PYTHONUNBUFFERED": "1"}
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,          # line-buffered on our side
            env=env,
        )
        if proc_ref is not None:
            proc_ref.clear()
            proc_ref.append(proc)

        out_lines: list[str] = []
        err_lines: list[str] = []

        def _pump(stream, sink, path, is_stdout):
            # Own the file for the life of the stream; flush each line so the
            # on-disk log tracks the run in real time.
            with open(path, "w") as f:
                for line in stream:
                    sink.append(line)
                    f.write(line)
                    f.flush()
                    if is_stdout and progress_cb is not None:
                        try:
                            progress_cb(line)
                        except Exception:
                            pass   # a progress hook must never break a reduction
                stream.close()

        out_thread = threading.Thread(
            target=_pump, args=(proc.stdout, out_lines, log_path, True), daemon=True)
        err_thread = threading.Thread(
            target=_pump, args=(proc.stderr, err_lines, err_path, False), daemon=True)
        out_thread.start()
        err_thread.start()

        cancelled = False
        while proc.poll() is None:
            if cancel_event is not None and cancel_event.is_set():
                proc.kill()
                cancelled = True
                break
            time.sleep(0.2)
        proc.wait()
        out_thread.join(timeout=5)
        err_thread.join(timeout=5)

        elapsed = time.time() - t0
        stdout = "".join(out_lines)
        stderr = "".join(err_lines)

        if cancelled:
            # Threads are joined, so appending here doesn't race the pump.
            with open(err_path, "a") as f:
                f.write("\nCancelled by user.\n")
            return ReductionResult(
                success=False, json_path=json_path, output_file="",
                elapsed_seconds=elapsed, stdout=stdout, stderr="Cancelled by user.",
                return_code=-99, log_file=log_path, err_file=err_path, cancelled=True,
            )

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
        err_msg = f"'{' '.join(get_drtsans_cmd(drtsans_version))}' not found. Activate the drtsans conda environment first."
        with open(err_path, "w") as f:
            f.write(err_msg)
        return ReductionResult(
            success=False, json_path=json_path, output_file="",
            elapsed_seconds=elapsed, stdout="", stderr=err_msg,
            return_code=-1, log_file="", err_file=err_path,
        )
