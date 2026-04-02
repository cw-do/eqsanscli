from __future__ import annotations

import glob
import os
from typing import TYPE_CHECKING

from eqsanscli.commands.router import CommandResult

if TYPE_CHECKING:
    from eqsanscli.models.session_state import SessionState


async def handle_share(args: list[str], state: SessionState) -> CommandResult:
    if not args:
        return CommandResult(
            success=False,
            message="Usage: /share <file|pattern> [file2 ...]\n"
            "  /share *_4m10a_Iq.dat            — Share matching files\n"
            "  /share merged_porsil_Iq.txt       — Share a single file\n"
            "  /share plot.png                    — Share an image\n"
            "  /share *.png                       — Share all PNG files\n\n"
            "Files are uploaded to here.now (anonymous, 24h expiry).\n"
            "Returns a shareable URL.",
        )

    output_dir = state.output_directory
    resolved: list[str] = []

    for pattern in args:
        matches = glob.glob(pattern)
        if not matches and not os.path.isabs(pattern):
            matches = glob.glob(os.path.join(output_dir, pattern))
        if not matches and os.path.exists(pattern):
            matches = [pattern]

        resolved.extend(os.path.abspath(m) for m in sorted(matches))

    if not resolved:
        return CommandResult(
            success=False,
            message=f"No files matched: {' '.join(args)}\n"
            f"  Searched in: {output_dir} and current directory",
        )

    resolved = list(dict.fromkeys(resolved))

    total_size = sum(os.path.getsize(f) for f in resolved)
    if total_size > 50 * 1024 * 1024:
        mb = total_size / (1024 * 1024)
        return CommandResult(
            success=False,
            message=f"Total size {mb:.1f} MB exceeds 50 MB limit. Share fewer files.",
        )

    file_list = "\n".join(f"  {os.path.basename(f)} ({os.path.getsize(f) / 1024:.1f} KB)" for f in resolved)

    from eqsanscli.services.share_service import share_files
    success, url, error = share_files(resolved)

    if not success:
        return CommandResult(success=False, message=f"Share failed: {error}")

    return CommandResult(
        success=True,
        message=f"Shared {len(resolved)} file(s) → [bold cyan]{url}[/bold cyan]\n"
        f"  (anonymous, expires in 24 hours)\n\n"
        f"Files:\n{file_list}",
    )
