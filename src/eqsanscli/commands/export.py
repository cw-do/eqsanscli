from __future__ import annotations

import glob
import os
import shutil
import subprocess
import tempfile
import zipfile
from datetime import datetime
from typing import TYPE_CHECKING

from eqsanscli.commands.router import CommandResult
from eqsanscli.services.script_exporter import export_reduction_script

if TYPE_CHECKING:
    from eqsanscli.models.session_state import SessionState


async def handle_export_script(args: list[str], state: SessionState) -> CommandResult:
    table = state.current_table
    if not table.rows:
        return CommandResult(success=False, message="Working table is empty. Use /matchruns first.")

    if args:
        output_path = args[0]
    else:
        output_path = os.path.join(
            state.output_directory,
            f"reduce_{state.ipts}_{table.name}.py",
        )

    path = export_reduction_script(
        table=table,
        user_configs=state.configurations,
        output_dir=state.output_directory,
        output_path=output_path,
        ipts=state.ipts,
    )

    n_configs = len(table.configurations)
    n_rows = len(table.rows)
    return CommandResult(
        success=True,
        message=f"Exported reduction script: {path}\n"
        f"  {n_rows} samples across {n_configs} configurations.\n"
        f"  Run with: drtsans {path}",
    )


async def handle_zipnsend(args: list[str], state: SessionState) -> CommandResult:
    """/zipnsend <email> [options] — zip files and email them.

    Examples:
        /zipnsend ccd@ornl.gov                              — merged*.txt from outputdir
        /zipnsend ccd@ornl.gov --pattern "*_Iq.dat"         — custom glob pattern
        /zipnsend ccd@ornl.gov --pattern "*.png"            — send plot images
        /zipnsend ccd@ornl.gov --dir /path/to/data          — from specific directory
        /zipnsend ccd@ornl.gov --subject "IPTS-35884 data"  — custom subject
    """
    if not args:
        return CommandResult(
            success=False,
            message="Usage: /zipnsend <email> [options]\n"
            "  --pattern <glob>    File pattern (default: merged*.txt)\n"
            "  --dir <path>        Source directory (default: outputdir)\n"
            "  --subject <text>    Email subject (default: auto-generated)\n\n"
            "Examples:\n"
            "  /zipnsend ccd@ornl.gov\n"
            '  /zipnsend ccd@ornl.gov --pattern "*_Iq.dat"\n'
            "  /zipnsend ccd@ornl.gov --pattern '*.png' --subject 'plots'",
        )

    # Parse arguments
    email = None
    pattern = "merged*.txt"
    source_dir = os.path.abspath(state.output_directory)
    subject = None

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--pattern" and i + 1 < len(args):
            pattern = args[i + 1]
            i += 2
            continue
        if a == "--dir" and i + 1 < len(args):
            source_dir = os.path.abspath(args[i + 1])
            i += 2
            continue
        if a == "--subject" and i + 1 < len(args):
            subject = args[i + 1]
            i += 2
            continue
        if email is None and "@" in a:
            email = a
        i += 1

    if not email:
        return CommandResult(success=False, message="No email address provided.")

    if not os.path.isdir(source_dir):
        return CommandResult(success=False, message=f"Directory not found: {source_dir}")

    # Find matching files
    matched_files = sorted(glob.glob(os.path.join(source_dir, pattern)))
    if not matched_files:
        return CommandResult(
            success=False,
            message=f"No files matching '{pattern}' in {source_dir}",
        )

    # Check mail command availability
    mail_cmd = None
    for cmd in ("mailx", "mail"):
        if shutil.which(cmd):
            mail_cmd = cmd
            break
    if not mail_cmd:
        return CommandResult(
            success=False,
            message="No mail command found (tried mailx, mail). Cannot send email.",
        )

    # Build zip file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    ipts_label = f"IPTS-{state.ipts}" if state.ipts else "eqsans"
    zip_name = f"{ipts_label}_{timestamp}.zip"

    try:
        tmp_dir = tempfile.mkdtemp(prefix="eqsanscli_")
        zip_path = os.path.join(tmp_dir, zip_name)

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for fpath in matched_files:
                zf.write(fpath, os.path.basename(fpath))

        zip_size = os.path.getsize(zip_path)
        if zip_size > 25 * 1024 * 1024:  # 25 MB
            os.unlink(zip_path)
            os.rmdir(tmp_dir)
            size_mb = zip_size / (1024 * 1024)
            return CommandResult(
                success=False,
                message=f"Zip file too large for email ({size_mb:.1f} MB). "
                "Consider using /share instead.",
            )

        # Build email
        if subject is None:
            subject = f"EQSANS data — {ipts_label} ({len(matched_files)} files)"

        file_list = "\n".join(f"  - {os.path.basename(f)}" for f in matched_files)
        body = (
            f"EQSANS CLI data export\n"
            f"{ipts_label}\n"
            f"Pattern: {pattern}\n"
            f"Files ({len(matched_files)}):\n{file_list}\n"
        )

        # Send via mail
        proc = subprocess.run(
            [mail_cmd, "-s", subject, "-a", zip_path, email],
            input=body,
            text=True,
            capture_output=True,
            timeout=30,
        )

        # Cleanup
        os.unlink(zip_path)
        os.rmdir(tmp_dir)

        if proc.returncode != 0:
            err = proc.stderr.strip() or "Unknown error"
            return CommandResult(
                success=False,
                message=f"Mail command failed: {err}",
            )

        size_kb = zip_size / 1024
        return CommandResult(
            success=True,
            message=f"Sent {len(matched_files)} file(s) to {email}\n"
            f"  Pattern: {pattern}\n"
            f"  Zip: {zip_name} ({size_kb:.0f} KB)\n"
            f"  Subject: {subject}",
        )

    except subprocess.TimeoutExpired:
        return CommandResult(success=False, message="Mail command timed out (30s).")
    except Exception as e:
        return CommandResult(success=False, message=f"Error: {e}")


CONFIRM_DATA_BIN = "/SNS/software/nses/bin/confirm-data"

VALID_STATUSES = ["Unknown", "No", "Yes", "Partially", "None Expected"]
VALID_TYPES = ["Auto", "CIS", "Scripts"]


def run_confirm_data(
    ipts: int,
    submission: int = 1,
    reduction_type: str = "Scripts",
    status: str = "Yes",
    comment: str = "",
) -> tuple[bool, str]:
    """Call confirm-data to update IPTS reduction status.

    Returns (success, message).
    """
    if not os.path.exists(CONFIRM_DATA_BIN):
        return False, f"confirm-data not found: {CONFIRM_DATA_BIN}"

    cmd = [CONFIRM_DATA_BIN, "EQSANS", str(ipts), str(submission), reduction_type,
           "-s", status]
    if comment:
        cmd.extend(["-c", comment])

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if proc.returncode != 0:
            err = proc.stderr.strip() or proc.stdout.strip() or "Unknown error"
            return False, f"confirm-data failed: {err}"
        return True, f"Data reduction status updated for IPTS-{ipts} (type={reduction_type}, status={status})"
    except subprocess.TimeoutExpired:
        return False, "confirm-data timed out (30s)"
    except Exception as e:
        return False, f"Error running confirm-data: {e}"


async def handle_confirm(args: list[str], state: SessionState) -> CommandResult:
    """/confirm [ipts] [--comment <text>] — confirm IPTS data reduction is complete.

    Examples:
        /confirm                                — Confirm current IPTS
        /confirm 38397                          — Confirm specific IPTS
        /confirm --comment "reduced with eqsanscli"
    """
    if args and args[0] in ("--help", "-h", "help"):
        return CommandResult(
            success=False,
            message="Usage: /confirm [ipts] [--comment <text>]\n"
            "  Confirms data reduction is complete (status=Yes, type=Scripts).\n\n"
            "Examples:\n"
            "  /confirm\n"
            "  /confirm 38397\n"
            '  /confirm --comment "reduced with eqsanscli"',
        )

    ipts = None
    comment = ""

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--comment" and i + 1 < len(args):
            comment = args[i + 1]
            i += 2
            continue
        if ipts is None:
            try:
                ipts = int(a)
            except ValueError:
                pass
        i += 1

    if ipts is None:
        ipts = state.ipts
    if not ipts:
        return CommandResult(success=False, message="No IPTS specified and none in session. Usage: /confirm [ipts]")

    success, message = run_confirm_data(ipts, comment=comment)
    return CommandResult(success=success, message=message)
