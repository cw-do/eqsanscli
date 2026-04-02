"""Share files via here.now — zero-dependency file sharing using only stdlib."""

from __future__ import annotations

import json
import logging
import mimetypes
import os
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

_API_URL = "https://here.now/api/v1/publish"
_CLIENT_HEADER = "eqsanscli/share"


def share_files(paths: list[str]) -> tuple[bool, str, str]:
    """Upload files to here.now and return (success, url, message).

    Uses the anonymous API — links expire in 24 hours.
    No external dependencies; uses only urllib from stdlib.
    """
    files_meta = []
    for p in paths:
        if not os.path.exists(p):
            return False, "", f"File not found: {p}"
        size = os.path.getsize(p)
        ct = mimetypes.guess_type(p)[0] or "application/octet-stream"
        files_meta.append({
            "path": os.path.basename(p),
            "size": size,
            "contentType": ct,
        })

    # Step 1: Create site
    create_body = json.dumps({"files": files_meta}).encode()
    req = urllib.request.Request(
        _API_URL,
        data=create_body,
        headers={
            "Content-Type": "application/json",
            "X-HereNow-Client": _CLIENT_HEADER,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            create_data = json.loads(resp.read())
    except Exception as e:
        return False, "", f"Failed to create share: {e}"

    site_url = create_data.get("siteUrl", "")
    upload_block = create_data.get("upload", {})
    version_id = upload_block.get("versionId", "")
    finalize_url = upload_block.get("finalizeUrl", "")
    uploads = upload_block.get("uploads", [])

    if not site_url or not finalize_url or len(uploads) != len(paths):
        return False, "", f"Unexpected API response: {json.dumps(create_data)[:200]}"

    # Step 2: Upload each file
    for i, p in enumerate(paths):
        upload_url = uploads[i].get("url", "")
        if not upload_url:
            return False, "", f"No upload URL for {os.path.basename(p)}"

        ct = files_meta[i]["contentType"]
        with open(p, "rb") as f:
            file_data = f.read()

        put_req = urllib.request.Request(
            upload_url,
            data=file_data,
            headers={"Content-Type": ct},
            method="PUT",
        )
        try:
            with urllib.request.urlopen(put_req, timeout=120) as resp:
                if resp.status not in (200, 201):
                    return False, "", f"Upload failed for {os.path.basename(p)}: HTTP {resp.status}"
        except Exception as e:
            return False, "", f"Upload failed for {os.path.basename(p)}: {e}"

    # Step 3: Finalize
    finalize_body = json.dumps({"versionId": version_id}).encode()
    fin_req = urllib.request.Request(
        finalize_url,
        data=finalize_body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(fin_req, timeout=30) as resp:
            fin_data = json.loads(resp.read())
    except Exception as e:
        return False, "", f"Finalize failed: {e}"

    final_url = fin_data.get("siteUrl", site_url)
    return True, final_url, ""
