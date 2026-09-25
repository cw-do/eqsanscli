"""Console entry point: one-time ONCat sign-in.

    eqsanscli-oncat-login

Runs the Device Authorization Grant in a plain terminal (prints a verification
URL to approve in a browser) and caches a per-user token in ~/.eqsanscli/, which
eqsanscli then reuses silently. Run once before first use, or again after the
session expires. Unattended services can set ONCAT_USERNAME/ONCAT_PASSWORD/
ONCAT_CLIENT_ID/ONCAT_CLIENT_SECRET instead of signing in here.
"""

from __future__ import annotations

import sys


def main() -> int:
    from eqsanscli.integrations import oncat

    try:
        me = oncat.login()
    except Exception as exc:  # noqa: BLE001 - top-level CLI boundary
        print(f"ONCat sign-in failed: {exc}", file=sys.stderr)
        return 1

    name = me.get("name") or me.get("id") or "you"
    n_exp = len(me.get("experiments") or [])
    instruments = ", ".join(me.get("instruments") or []) or "—"
    print(f"Signed in to ONCat as {name}.", file=sys.stderr)
    print(f"  instruments: {instruments}; direct experiment memberships: {n_exp}",
          file=sys.stderr)
    print(f"  token cached at {oncat._token_path()} (reused automatically).",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
