"""ONCat API wrapper — per-user catalog access via pyoncat.

Authentication (see ORNL's ONCat docs, reviewed 2026-09-25):

  * **Device Authorization Grant** (recommended, the default here). A *public*
    client id, no secret. The user approves sign-in once in a browser; a per-user
    token is cached in their home and reused silently afterwards, so ONCat returns
    only the experiments THAT user may access. `login()` performs the sign-in;
    data calls never trigger a browser prompt themselves (token-first).
  * **Password Grant** (deprecated, browser-free fallback for services such as
    NDIP/Galaxy). Enabled only when the deployment sets `ONCAT_USERNAME`,
    `ONCAT_PASSWORD`, `ONCAT_CLIENT_ID`, `ONCAT_CLIENT_SECRET` in the environment —
    nothing secret is committed.

Precedence per call: a cached/refreshable token → env password-grant credentials →
(for `login()` only) an interactive device sign-in. A data call with none of these
raises `OncatAuthRequired`, which the front ends turn into "run sign-in first".
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable

import pandas as pd

logger = logging.getLogger(__name__)

ONCAT_URL = "https://oncat.ornl.gov"

# Public OAuth client id ONCat publishes for human users. Safe to commit — it is
# NOT a secret and carries no access on its own; each user authenticates as
# themselves. (Replaces the committed machine-to-machine client id + secret.)
PUBLIC_CLIENT_ID = "eaeb036a-2602-4bb9-8530-0bb5812da7a1"
SCOPES = ["api:read", "data:read", "openid"]


class OncatAuthRequired(RuntimeError):
    """No usable ONCat token and no way to get one without user interaction."""


def _token_path() -> str:
    """Per-user token cache. Override with EQSANSCLI_ONCAT_TOKEN for tests/NDIP."""
    return os.path.expanduser(
        os.environ.get("EQSANSCLI_ONCAT_TOKEN", "~/.eqsanscli/oncat_token.json")
    )


def _token_store():
    import pyoncat

    path = _token_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        os.chmod(os.path.dirname(path), 0o700)
    except OSError:
        pass
    return pyoncat.FileSystemTokenStore(path)


# A front end (the TUI) can register how the device-flow verification URL/code is
# shown; the default prints to stderr, which is right for a plain terminal and for
# the standalone login step, and stays out of the headless JSON on stdout.
_verification_handler: Callable[[Any], None] | None = None


def set_verification_handler(handler: Callable[[Any], None] | None) -> None:
    global _verification_handler
    _verification_handler = handler


def _default_verification_handler(challenge: Any) -> None:
    import sys

    link = getattr(challenge, "verification_uri_complete", None) or challenge.verification_uri
    print("\n" + "=" * 70, file=sys.stderr)
    print("  ONCat sign-in required — open this URL in a browser:", file=sys.stderr)
    print(f"    {link}", file=sys.stderr)
    if not getattr(challenge, "verification_uri_complete", None):
        print(f"  and enter the code: {challenge.user_code}", file=sys.stderr)
    print("  Sign in with your UCAMS/XCAMS and approve. Waiting...", file=sys.stderr)
    print("=" * 70 + "\n", file=sys.stderr)


def _env_password_credentials() -> tuple[str, str, str, str] | None:
    """(user, password, client_id, client_secret) if the deployment set all four,
    else None. Lets a browserless service (NDIP/Galaxy) use the Password Grant
    without any secret living in the code."""
    user = os.environ.get("ONCAT_USERNAME")
    pw = os.environ.get("ONCAT_PASSWORD")
    cid = os.environ.get("ONCAT_CLIENT_ID")
    secret = os.environ.get("ONCAT_CLIENT_SECRET")
    if user and pw and cid and secret:
        return user, pw, cid, secret
    return None


def _make_client(*, interactive: bool):
    """Build an ONCat client.

    interactive=False (data calls): token-first, never prompts. Uses the env
    password grant if configured; otherwise a device-flow client pinned to
    REAUTH_NEVER so an expired/absent token raises instead of popping a browser.
    interactive=True (`login()`): allows the device browser flow.
    """
    try:
        import pyoncat
    except ImportError as exc:
        raise ImportError(
            "pyoncat>=2.6 is required for ONCat access. Install it with: "
            "pip install 'pyoncat>=2.6'"
        ) from exc

    store = _token_store()
    creds = _env_password_credentials()
    if creds:
        user, pw, cid, secret = creds
        logger.info("ONCat: using env Password Grant for user %s (browserless).", user)
        return pyoncat.ONCat(
            ONCAT_URL,
            client_id=cid,
            client_secret=secret,
            token_getter=store.read_token,
            token_setter=store.write_token,
            login_prompt=lambda: (user, pw),
            flow=pyoncat.RESOURCE_OWNER_CREDENTIALS_FLOW,
        )

    if not interactive and not os.path.exists(_token_path()):
        raise OncatAuthRequired(
            "Not signed in to ONCat. Run the one-time sign-in "
            "(in the TUI: /oncat login; or the command line: eqsanscli-oncat-login), "
            "approve in your browser, then retry. Unattended services can instead set "
            "ONCAT_USERNAME/ONCAT_PASSWORD/ONCAT_CLIENT_ID/ONCAT_CLIENT_SECRET."
        )

    return pyoncat.ONCat(
        ONCAT_URL,
        client_id=PUBLIC_CLIENT_ID,
        scopes=SCOPES,
        token_getter=store.read_token,
        token_setter=store.write_token,
        flow=pyoncat.DEVICE_AUTHORIZATION_FLOW,
        verification_handler=_verification_handler or _default_verification_handler,
        reauth_on_expired=(pyoncat.REAUTH_PROMPT if interactive else pyoncat.REAUTH_NEVER),
    )


def login() -> dict:
    """Perform an interactive ONCat sign-in and cache the token. Returns the
    signed-in user's summary (id, name, entitlements). Safe to call when already
    signed in — it just refreshes/validates and returns the summary."""
    import getpass

    client = _make_client(interactive=True)
    client.login()
    try:
        me = client.User.retrieve(getpass.getuser()).to_dict()
    except Exception:  # noqa: BLE001 - identity is informational
        me = {"id": getpass.getuser()}
    logger.info("ONCat sign-in complete for %s.", me.get("id"))
    return me


def is_signed_in() -> bool:
    """True if a cached token exists or env credentials are configured. Does not
    hit the network (a stored token may still turn out to be expired)."""
    return _env_password_credentials() is not None or os.path.exists(_token_path())


def sign_out() -> bool:
    """Delete the cached token. Returns True if one was removed."""
    path = _token_path()
    if os.path.exists(path):
        os.remove(path)
        return True
    return False


def _translate_auth_error(exc: Exception) -> Exception:
    """Map pyoncat auth failures to OncatAuthRequired with actionable text."""
    import pyoncat

    if isinstance(exc, (
        getattr(pyoncat, "InvalidRefreshTokenError", ()),
        getattr(pyoncat, "LoginRequired", ()),
        getattr(pyoncat, "InteractionRequiredError", ()),
    )):
        return OncatAuthRequired(
            "ONCat session expired. Sign in again (/oncat login, or "
            "eqsanscli-oncat-login), then retry."
        )
    return exc


# Fields to fetch from ONCat
PROJECTION = [
    "experiment",
    "location",
    "indexed.run_number",
    "metadata.entry.title",
    "metadata.entry.run_number",
    "metadata.entry.total_counts",
    "metadata.entry.duration",
    "metadata.entry.daslogs.detectorz.average_value",
    "metadata.entry.daslogs.wavelength.average_value",
    "metadata.entry.daslogs.speed1.average_value",
    "metadata.entry.proton_charge",
]


def _round_frequency(raw_freq: float) -> int:
    """Round chopper frequency to nearest standard value (30 or 60 Hz)."""
    if raw_freq <= 0:
        return 60  # default
    if raw_freq < 45:
        return 30
    return 60


def _extract_field(record: Any, dotted_path: str) -> Any:
    """Safely extract a nested field from an ONCat record using dotted path.

    ONCat returns ONCatObject instances which support __getitem__ (bracket access)
    but nested objects may also be ONCatObject, not plain dicts.
    """
    obj = record
    for key in dotted_path.split("."):
        if obj is None:
            return None
        try:
            obj = obj[key]
        except (KeyError, TypeError, IndexError):
            try:
                obj = getattr(obj, key, None)
            except Exception:
                return None
    return obj


def fetch_catalog(ipts: int) -> pd.DataFrame:
    """Fetch all runs for an IPTS number from ONCat, as the signed-in user.

    Returns a DataFrame with columns:
        run_number, title, detector_distance, wavelength,
        total_counts, duration, proton_charge, experiment, location

    Raises OncatAuthRequired if there is no usable token (front ends prompt the
    user to sign in). Note: the user only sees IPTS they are entitled to, so an
    inaccessible IPTS comes back empty just like a nonexistent one.
    """
    oncat = _make_client(interactive=False)

    logger.info("Fetching catalog for IPTS-%d...", ipts)
    try:
        oncat.login()
        datafiles = oncat.Datafile.list(
            facility="SNS",
            instrument="EQSANS",
            experiment=f"IPTS-{ipts}",
            projection=PROJECTION,
            exts=[".nxs.h5"],
        )
    except Exception as exc:  # noqa: BLE001
        raise _translate_auth_error(exc) from exc

    if not datafiles:
        logger.warning("No datafiles found for IPTS-%d", ipts)
        return pd.DataFrame()

    rows = []
    for record in datafiles:
        run_number = (
            _extract_field(record, "metadata.entry.run_number")
            or _extract_field(record, "indexed.run_number")
        )
        if run_number is None:
            continue

        rows.append(
            {
                "run_number": int(run_number),
                "title": _extract_field(record, "metadata.entry.title") or "",
                "detector_distance": float(
                    _extract_field(record, "metadata.entry.daslogs.detectorz.average_value") or 0
                ) / 1000.0,  # ONCat returns mm, convert to meters
                "wavelength": float(
                    _extract_field(record, "metadata.entry.daslogs.wavelength.average_value") or 0
                ),
                "total_counts": int(
                    _extract_field(record, "metadata.entry.total_counts") or 0
                ),
                "duration": int(
                    _extract_field(record, "metadata.entry.duration") or 0
                ),
                "frequency": _round_frequency(
                    float(
                        _extract_field(record, "metadata.entry.daslogs.speed1.average_value") or 60
                    )
                ),
                "proton_charge": float(
                    _extract_field(record, "metadata.entry.proton_charge") or 0
                ),
                "experiment": _extract_field(record, "experiment") or f"IPTS-{ipts}",
                "location": _extract_field(record, "location") or "",
            }
        )

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("run_number").reset_index(drop=True)
    logger.info("Fetched %d runs for IPTS-%d", len(df), ipts)
    return df


_EXPERIMENT_PROJECTION = ["id", "title", "members", "rank", "size", "activity"]

# Module-level cache: stores the full list of experiment dicts fetched from ONCat.
# Persists for the lifetime of the process. Use list_experiments(refresh=True) to bust it.
_experiment_cache: list[dict] | None = None


def _fetch_all_experiments() -> list[dict]:
    oncat = _make_client(interactive=False)

    logger.info("Fetching EQSANS experiment list from ONCat...")
    try:
        oncat.login()
        experiments = oncat.Experiment.list(
            facility="SNS",
            instrument="EQSANS",
            projection=_EXPERIMENT_PROJECTION,
        )
    except Exception as exc:  # noqa: BLE001
        raise _translate_auth_error(exc) from exc

    results = []
    for exp in experiments:
        d = exp.to_dict()
        ipts_num = d.get("rank", 0)
        title = d.get("title", "") or ""
        members_list = d.get("members") or []
        member_names = [m.get("name", "") for m in members_list if isinstance(m, dict)]
        runs = d.get("size", 0)
        activity = d.get("activity") or {}
        dates = activity.get("acquisition") or []
        date_range = f"{dates[0]} — {dates[-1]}" if dates else ""
        results.append({
            "ipts": ipts_num,
            "title": title,
            "members": member_names,
            "runs": runs,
            "dates": date_range,
        })

    results.sort(key=lambda r: r["ipts"])
    logger.info("Fetched %d total EQSANS experiments from ONCat", len(results))
    return results


def list_experiments(search: str = "", refresh: bool = False) -> tuple[list[dict], bool]:
    """List EQSANS experiments the signed-in user can access, optionally filtered.

    Results are cached in memory after the first fetch. Subsequent calls with
    a different search term filter the cache without hitting the network.

    Args:
        search: Filter string. Use "*" or "" for all. Supports multi-term via
                "and" or "+" (e.g. "changwoo and sds"). Case-insensitive.
        refresh: If True, discard cache and re-fetch from ONCat.

    Returns:
        (results, from_cache) — matched experiment dicts, and whether cache was used.
    """
    global _experiment_cache

    if refresh or _experiment_cache is None:
        _experiment_cache = _fetch_all_experiments()
        was_cached = False
    else:
        was_cached = True

    import re as _re
    raw = search.strip().lower()
    terms = [t.strip() for t in _re.split(r"\+|\band\b", raw) if t.strip()]

    if not terms or terms == ["*"]:
        results = list(_experiment_cache)
    else:
        results = []
        for exp in _experiment_cache:
            searchable = (exp["title"] + " " + " ".join(exp["members"])).lower()
            if all(t in searchable for t in terms):
                results.append(exp)

    logger.info("Found %d experiments (filter=%r, cached=%s)", len(results), search, was_cached)
    return results, was_cached
