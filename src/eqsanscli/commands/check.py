"""/check — run the protocol checks decidable from session state (knowledge/protocol.md).

Gathers in one place what is otherwise spread over /matchruns, /reduce and
/show config: the registered protocol validators (`services/protocol.py`), each
row's reducibility (EMP-01, TBL-02/03/05), the absolute scale's origin and range
(SCL-03, SCL-04), and transmission runs nothing uses (TBL-02). Read-only.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from eqsanscli.commands.router import CommandResult

if TYPE_CHECKING:
    from eqsanscli.models.session_state import SessionState

_ORDER = {"blocking": 0, "warning": 1, "info": 2}


def collect_findings(state: SessionState) -> list[dict]:
    """Every finding as {"rule", "severity", "message", "rows"}; blocking first."""
    from eqsanscli.services import protocol, scale_service
    from eqsanscli.services.reduction_service import advisory_problems, blocking_problems

    out: list[dict] = []
    for f in protocol.check(state):
        out.append({"rule": f.rule, "severity": f.severity, "message": f.message, "rows": []})

    table = state.current_table
    no_empty = [r.index for r in table.rows if any("empty beam" in p for p in blocking_problems(r))]
    if no_empty:
        out.append({"rule": "EMP-01", "severity": "blocking", "rows": no_empty,
                    "message": f"{len(no_empty)} row(s) have no empty beam (beam centre) — "
                               f"/reduce refuses them"})
    by_kind: dict[str, list[int]] = {}
    for r in table.rows:
        for p in advisory_problems(r):
            by_kind.setdefault(p.split("=")[0], []).append(r.index)
    rules = {"no transmission": "TBL-02", "no background": "TBL-03", "thickness": "TBL-05"}
    for kind, rows in by_kind.items():
        out.append({"rule": rules.get(kind, "TBL"), "severity": "warning", "rows": rows,
                    "message": f"{len(rows)} row(s): {kind}"})

    if state.catalog is not None and not state.catalog.empty and table.rows:
        from eqsanscli.services.matching_service import transmission_report
        for u in transmission_report(state.catalog, table)["unused"]:
            near = f" — closest rows {u['closest_rows'][:6]}" if u["closest_rows"] else ""
            out.append({"rule": "TBL-02", "severity": "warning", "rows": u["closest_rows"],
                        "message": f"transmission {u['run']} ({u['title']}, {u['config']}) "
                                   f"is not used by any row{near}"})

    for cfg in table.configurations:
        if scale_service.is_relative(state, cfg) is None:
            out.append({"rule": "SCL-04", "severity": "warning", "rows": [],
                        "message": f"{cfg}: {scale_service.describe(state, cfg)}"})
        warn = scale_service.plausibility(scale_service.current_scale(state, cfg))
        if warn:
            out.append({"rule": "SCL-03", "severity": "warning", "rows": [],
                        "message": f"{cfg}: scale {scale_service.current_scale(state, cfg):.4g} is {warn}"})
    return sorted(out, key=lambda f: (_ORDER.get(f["severity"], 9), f["rule"]))


async def handle_check(args: list[str], state: SessionState) -> CommandResult:
    from eqsanscli.services import protocol
    findings = collect_findings(state)
    unenforced = [r.id for r in protocol.unenforced_rules()]
    if not findings:
        msg = "[green]✓ No protocol findings.[/green]"
    else:
        marks = {"blocking": "[red]✗[/red]", "warning": "[yellow]⚠[/yellow]", "info": "·"}
        n_block = sum(f["severity"] == "blocking" for f in findings)
        lines = [f"{len(findings)} finding(s), {n_block} blocking:"]
        for f in findings:
            lines.append(f"  {marks.get(f['severity'], '·')} {f['rule']} ({f['severity']}): {f['message']}")
        if n_block:
            lines.append("  [dim]/reduce refuses while blocking findings stand (--force overrides).[/dim]")
        msg = "\n".join(lines)
    msg += f"\n  [dim]{len(unenforced)} rule(s) not yet checked by code: {', '.join(unenforced)}[/dim]"
    return CommandResult(success=True, message=msg,
                         data={"type": "check", "findings": findings, "unenforced": unenforced})
