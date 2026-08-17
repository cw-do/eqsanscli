from __future__ import annotations

import os
import threading

from rich.table import Table
from rich.text import Text

from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import RichLog, Static
from textual import work

from eqsanscli.tui.widgets.completable_input import CommandSubmitted, CompletableInput, CompletionHint
from eqsanscli.tui.widgets.status_bar import FooterBar, HeaderBar

from eqsanscli import __version__
from eqsanscli.commands.registry import register_all
from eqsanscli.commands.router import CommandResult, CommandRouter
from eqsanscli.models.session_state import SessionState


class EQSANSApp(App):

    TITLE = "EQSANS CLI"
    SUB_TITLE = f"v{__version__}"

    CSS = """
    Screen {
        layout: vertical;
        padding: 0 1;
    }
    #main-area {
        height: 1fr;
        width: 100%;
    }
    #output-scroll {
        width: 1fr;
        height: 100%;
        overflow-y: auto;
        overflow-x: auto;
        scrollbar-gutter: stable;
    }
    #output {
        height: auto;
        min-height: 1;
        border: none;
        overflow-x: auto;
        overflow-y: hidden;
    }
    #guide-pane {
        width: 44;
        height: 100%;
        background: $surface;
        border-left: solid $accent;
        overflow-y: auto;
        scrollbar-gutter: stable;
        display: none;
    }
    #guide-pane.-visible {
        display: block;
    }
    #guide-content {
        height: auto;
        color: $text;
        padding: 1 2;
    }
    #cmd-input {
        dock: bottom;
        height: 5;
        border: round $accent;
        margin-bottom: 1;
    }
    """

    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("ctrl+l", "clear_log", "Clear"),
        ("ctrl+x", "cancel_job", "Cancel Job"),
        ("escape", "focus_input", "Focus Input"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.state = SessionState()
        self.state.output_directory = os.path.abspath(self.state.output_directory)
        self.router = CommandRouter()
        self._register_commands()
        self._cancel_event: threading.Event = threading.Event()
        self._job_running: bool = False
        self._prompt_event: threading.Event = threading.Event()
        self._prompt_response: str = ""
        self._prompt_pending: bool = False

    def cancel_job(self) -> None:
        if self._job_running:
            self._cancel_event.set()
            log = self.query_one("#output", RichLog)
            log.write(Text.from_markup("[bold yellow]⚠ Cancel requested — stopping after current run...[/bold yellow]"))

    def _set_job_running(self, running: bool) -> None:
        self._job_running = running
        if not running:
            self._cancel_event.clear()
        footer = self.query_one("#footer-bar", FooterBar)
        footer.set_job_running(running)

    def _register_commands(self) -> None:
        """Register command handlers with the router.

        Shared commands live in commands/registry.py (one place for both the TUI
        and headless mode). Only the TUI-specific ones are registered here.
        """
        register_all(self.router)

        self.router.register("list", self._handle_list)
        self.router.register("help", self._handle_help)
        self.router.register("guide", self._handle_guide)
        self.router.register("version", self._handle_version)
        self.router.register("exit", self._handle_exit)

    def compose(self) -> ComposeResult:
        yield HeaderBar(id="header-bar")
        with Horizontal(id="main-area"):
            with VerticalScroll(id="output-scroll"):
                yield RichLog(id="output", highlight=True, markup=True)
            with VerticalScroll(id="guide-pane"):
                yield Static("", id="guide-content", markup=True)
        yield CompletableInput(placeholder="eqsans> Type a command or ask in natural language...", id="cmd-input")
        yield FooterBar(id="footer-bar")

    def on_mount(self) -> None:
        log = self.query_one("#output", RichLog)
        logo = (
            "\n"
            "[bold cyan]"
            "  ███████╗ ██████╗ ███████╗ █████╗ ███╗   ██╗███████╗\n"
            "  ██╔════╝██╔═══██╗██╔════╝██╔══██╗████╗  ██║██╔════╝\n"
            "  █████╗  ██║   ██║███████╗███████║██╔██╗ ██║███████╗\n"
            "  ██╔══╝  ██║▄▄ ██║╚════██║██╔══██║██║╚██╗██║╚════██║\n"
            "  ███████╗╚██████╔╝███████║██║  ██║██║ ╚████║███████║\n"
            "  ╚══════╝ ╚══▀▀═╝ ╚══════╝╚═╝  ╚═╝╚═╝  ╚═══╝╚══════╝\n"
            "[/bold cyan]"
            f"  [dim]Extended Q-Range Small-Angle Neutron Scattering[/dim]  v{__version__}\n"
            "  [dim]SNS · ORNL · Oak Ridge, TN[/dim]\n"
            "\n"
            "  [bold]Getting Started:[/bold]\n"
            "    1. [cyan]/load ipts <number>[/cyan]     Load experiment catalog from ONCat\n"
            "    2. [cyan]/show catalog[/cyan]            Review catalog & run classes\n"
            "    3. [cyan]/reclass <runs> <class>[/cyan]  Fix misclassified runs (scatt/trans/bkg/empty)\n"
            "    4. [cyan]/matchruns[/cyan]              Auto-match trans/bkg/empty runs\n"
            "    5. [cyan]/show table[/cyan]             Review matched runs\n"
            "    6. [cyan]/show presets[/cyan]           Browse preset configurations\n"
            "    7. [cyan]/apply preset <name> <config>[/cyan]  Apply parameters\n"
            "    8. [cyan]/reduce all[/cyan]             Run data reduction\n"
            "\n"
            "  [dim]Type [bold]/help[/bold] for all commands, or just ask in natural language.[/dim]\n"
            "  [dim]Type [bold]/guide[/bold] to dock a quickstart side pane, or [bold]/help --simple[/bold] for an inline quickstart.[/dim]\n"
        )
        log.write(Text.from_markup(logo))

        autosave = SessionState.auto_save_path()
        if os.path.exists(autosave):
            log.write(Text.from_markup(
                "  [bold yellow]↩ Previous session found.[/bold yellow] "
                "Type [bold cyan]/continue[/bold cyan] to resume where you left off.\n"
            ))

        self.query_one("#cmd-input", CompletableInput).focus()
        self.query_one("#footer-bar", FooterBar).update_model()
        self._refresh_completions()
        self._update_status_bars()

    def _refresh_completions(self) -> None:
        completions: list[str] = []
        for cmd in self.router.commands:
            completions.append(f"/{cmd}")
        for cfg in self.state.current_table.configurations:
            completions.append(cfg)
        from eqsanscli.services.preset_service import list_presets
        for p in list_presets():
            completions.append(p["name"])
        self.query_one("#cmd-input", CompletableInput).update_completions(completions)

    def _update_status_bars(self) -> None:
        self.query_one("#header-bar", HeaderBar).update_from_state(self.state)
        version = self.state.drtsans_version
        if version == "default":
            label = "drtsans"
        else:
            label = f"drtsans --{version}"
        footer = self.query_one("#footer-bar", FooterBar)
        footer.drtsans_label = label
        footer.worker_count = self.state.max_workers

    async def on_command_submitted(self, event: CommandSubmitted) -> None:
        value = event.value.strip()
        if not value:
            return

        if self._prompt_pending:
            self._prompt_response = value
            self._prompt_pending = False
            self._prompt_event.set()
            log = self.query_one("#output", RichLog)
            log.write(Text.from_markup(f"\n[dim]>[/] [bold]{value}[/]"))
            return

        log = self.query_one("#output", RichLog)
        footer = self.query_one("#footer-bar", FooterBar)

        log.write(Text.from_markup(f"\n[dim]>[/] [bold]{value}[/]"))

        is_nl = not value.startswith("/")
        if is_nl:
            footer.set_llm_thinking()

        result = await self.router.dispatch(value, self.state)

        if is_nl:
            footer.set_llm_idle()

        if not result.success:
            log.write(Text.from_markup(f"[red]{result.message}[/]"))
        else:
            if result.message:
                log.write(Text.from_markup(f"[green]{result.message}[/]"))
            if result.data:
                self._render_data(log, result.data)

        try:
            self.state.save(SessionState.auto_save_path())
        except Exception:
            pass

        self.query_one("#output-scroll", VerticalScroll).scroll_end()
        self.query_one("#cmd-input", CompletableInput).focus()
        self._refresh_completions()
        self._update_status_bars()

    def on_completion_hint(self, event: CompletionHint) -> None:
        log = self.query_one("#output", RichLog)
        options = "  ".join(f"[cyan]{o}[/cyan]" for o in event.options)
        log.write(Text.from_markup(f"[dim]Tab options:[/dim] {options}"))
        self.query_one("#output-scroll", VerticalScroll).scroll_end()

    @work(thread=True)
    def run_reduction_batch(self, table, indices: list[int], state) -> None:
        import time
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from eqsanscli.services.reduction_service import reduce_row
        from eqsanscli.commands.reduction import _format_time, _summarize_error

        log = self.query_one("#output", RichLog)
        scroll = self.query_one("#output-scroll", VerticalScroll)

        def write(msg: str) -> None:
            self.call_from_thread(log.write, Text.from_markup(msg))
            self.call_from_thread(scroll.scroll_end)

        self.call_from_thread(self._set_job_running, True)
        self._cancel_event.clear()

        output_dir = state.output_directory
        total = len(indices)
        n_success = 0
        n_fail = 0
        n_cancelled = 0
        elapsed_times: list[float] = []
        batch_start = time.time()
        max_workers = state.max_workers

        parallel_label = f" ({max_workers} parallel)" if max_workers > 1 else ""
        write(f"[bold]Reducing {total} run(s) → {output_dir}{parallel_label}[/bold]")
        write(f"[dim]Running in background — press [bold]^X[/bold] or click [bold]✕ Cancel[/bold] to stop.[/dim]\n")

        if max_workers <= 1:
            for i, idx in enumerate(indices):
                if self._cancel_event.is_set():
                    write(f"[yellow]⚠ Cancelled — skipping remaining {total - i} run(s)[/yellow]")
                    n_cancelled = total - i
                    break

                row = table.get_row(idx)
                if row is None:
                    continue

                remaining = total - i
                eta_str = ""
                if elapsed_times:
                    avg = sum(elapsed_times) / len(elapsed_times)
                    eta_str = f"  ETA ~{_format_time(avg * remaining)}"

                output_name = row.output_stem
                row.status = "reducing"
                if row.background_scatt:
                    bkg_title = state.run_title(row.background_scatt)
                    bkg_info = f"  bkg={row.background_scatt}" + (f" [dim]({bkg_title})[/dim]" if bkg_title else "")
                else:
                    bkg_info = "  [yellow]no bkg[/yellow]"
                write(
                    f"  [dim][{i+1}/{total}][/dim] [yellow]⟳[/yellow] "
                    f"[bold]{row.sample_name}[/bold] ({row.configuration}){bkg_info} "
                    f"→ {output_name}.json  "
                    f"[dim]{remaining} left{eta_str}[/dim]"
                )

                result = reduce_row(
                    row=row, ipts=state.ipts,
                    user_configs=state.configurations, output_dir=output_dir,
                    cancel_event=self._cancel_event,
                    drtsans_version=state.drtsans_version,
                )

                elapsed_times.append(result.elapsed_seconds)

                if result.cancelled:
                    n_cancelled += 1
                    write(
                        f"  [dim][{i+1}/{total}][/dim] [yellow]⊘[/yellow] "
                        f"[bold]{row.sample_name}[/bold] ({row.configuration}) — cancelled"
                    )
                    break
                elif result.success:
                    n_success += 1
                    state.reduced_files.append(result.output_file)
                    write(
                        f"  [dim][{i+1}/{total}][/dim] [green]✓[/green] "
                        f"[bold]{row.sample_name}[/bold] ({row.configuration}) "
                        f"— {_format_time(result.elapsed_seconds)}  "
                        f"[dim]→ {output_name}_Iq.dat[/dim]"
                    )
                else:
                    n_fail += 1
                    error_summary = _summarize_error(result.log_file, result.err_file)
                    write(
                        f"  [dim][{i+1}/{total}][/dim] [red]✗[/red] "
                        f"[bold]{row.sample_name}[/bold] ({row.configuration}) "
                        f"— FAILED after {_format_time(result.elapsed_seconds)}"
                    )
                    write(f"      [red]{error_summary}[/red]")
                    if result.log_file:
                        write(f"      [dim]Logs: {result.log_file}[/dim]")
        else:
            rows_to_reduce = []
            for idx in indices:
                row = table.get_row(idx)
                if row is not None:
                    rows_to_reduce.append((idx, row))

            completed_count = 0

            def _do_reduce(idx_row):
                idx, row = idx_row
                return idx, row, reduce_row(
                    row=row, ipts=state.ipts,
                    user_configs=state.configurations, output_dir=output_dir,
                    cancel_event=self._cancel_event,
                    drtsans_version=state.drtsans_version,
                )

            for idx, row in rows_to_reduce:
                row.status = "reducing"

            write(f"  [dim]Submitting {len(rows_to_reduce)} jobs to {max_workers} workers...[/dim]")

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(_do_reduce, item): item
                    for item in rows_to_reduce
                }

                for future in as_completed(futures):
                    completed_count += 1
                    idx, row, result = future.result()
                    elapsed_times.append(result.elapsed_seconds)

                    if result.cancelled:
                        n_cancelled += 1
                        write(
                            f"  [dim][{completed_count}/{total}][/dim] [yellow]⊘[/yellow] "
                            f"[bold]{row.sample_name}[/bold] ({row.configuration}) — cancelled"
                        )
                    elif result.success:
                        n_success += 1
                        state.reduced_files.append(result.output_file)
                        remaining = total - completed_count
                        eta_str = ""
                        if elapsed_times:
                            avg = sum(elapsed_times) / len(elapsed_times)
                            eta_str = f"  ETA ~{_format_time(avg * remaining / max_workers)}"
                        write(
                            f"  [dim][{completed_count}/{total}][/dim] [green]✓[/green] "
                            f"[bold]{row.sample_name}[/bold] ({row.configuration}) "
                            f"— {_format_time(result.elapsed_seconds)}  "
                            f"[dim]{remaining} left{eta_str}[/dim]"
                        )
                    else:
                        n_fail += 1
                        error_summary = _summarize_error(result.log_file, result.err_file)
                        write(
                            f"  [dim][{completed_count}/{total}][/dim] [red]✗[/red] "
                            f"[bold]{row.sample_name}[/bold] ({row.configuration}) "
                            f"— FAILED after {_format_time(result.elapsed_seconds)}"
                        )
                        write(f"      [red]{error_summary}[/red]")
                        if result.log_file:
                            write(f"      [dim]Logs: {result.log_file}[/dim]")

        total_elapsed = time.time() - batch_start
        cancelled_str = f"  [yellow]{n_cancelled} cancelled[/yellow]  " if n_cancelled else ""
        write(
            f"\n[bold]━━━ Reduction complete ━━━[/bold]\n"
            f"  [green]{n_success} succeeded[/green]  [red]{n_fail} failed[/red]  "
            f"{cancelled_str}total {_format_time(total_elapsed)}\n"
            f"  Output: {output_dir}"
        )
        try:
            self.state.save(SessionState.auto_save_path())
        except Exception:
            pass
        self.call_from_thread(self._set_job_running, False)
        self.call_from_thread(self._update_status_bars)

    def _render_data(self, log: RichLog, data: dict) -> None:
        """Render structured command result data to the output log."""
        data_type = data.get("type")

        if data_type == "catalog":
            self._render_table(
                log,
                columns=["Run #", "Title", "Class", "Dist (m)", "λ (Å)", "Count", "Time(s)"],
                rows=data["rows"],
                title=f"IPTS-{data.get('ipts', '?')} Catalog",
            )

        elif data_type == "working_table":
            self._render_working_table(log, data["rows"])

        elif data_type == "config_table":
            self._render_config_table(log, data["rows"], data.get("config_id", ""))

        elif data_type == "preset_list":
            self._render_preset_list(log, data["rows"])

        elif data_type == "compare_table":
            self._render_compare_table(
                log, data["rows"], data.get("name_a", "A"), data.get("name_b", "B")
            )

        elif data_type == "image":
            log.write(Text.from_markup(f"[dim]Plot saved: {data.get('path', '')}[/dim]"))

        elif data_type == "stitch_table":
            self._render_stitch_table(log, data["groups"])

        elif data_type == "model_changed":
            footer = self.query_one("#footer-bar", FooterBar)
            footer.model_name = data["model"]

        elif data_type == "start_reduction":
            self.run_reduction_batch(
                self.state.current_table,
                data["indices"],
                self.state,
            )

        elif data_type == "start_autopilot":
            self.run_autopilot_worker(
                data["ipts"], data.get("samples"), data.get("excludes"),
                data.get("thickness"), data.get("bkg_sample"), data.get("config_filter"),
                data.get("force", False), data.get("continue_mode", False),
                data.get("standard_sample"), data.get("from_step", 1),
                data.get("fresh", False),
            )

    def action_cancel_job(self) -> None:
        self.cancel_job()

    @work(thread=True)
    def run_autopilot_worker(self, ipts: int, samples: list[str] | None = None, excludes: list[str] | None = None, thickness: float | None = None, bkg_sample: str | None = None, config_filter: str | None = None, force: bool = False, continue_mode: bool = False, standard_sample: str | None = None, from_step: int = 1, fresh: bool = False) -> None:
        import asyncio
        from eqsanscli.services.autopilot import run_autopilot_sync

        log = self.query_one("#output", RichLog)
        scroll = self.query_one("#output-scroll", VerticalScroll)

        def write(msg: str) -> None:
            self.call_from_thread(log.write, Text.from_markup(msg))
            self.call_from_thread(scroll.scroll_end)

        def prompt_user(question: str) -> str:
            self._prompt_event.clear()
            self._prompt_response = ""
            self._prompt_pending = True
            write(question)
            self._prompt_event.wait()
            return self._prompt_response.strip()

        self.call_from_thread(self._set_job_running, True)
        self._cancel_event.clear()
        loop = asyncio.new_event_loop()

        def dispatch_sync(cmd: str):
            return loop.run_until_complete(self.router.dispatch(cmd, self.state))

        try:
            run_autopilot_sync(
                ipts=ipts,
                state=self.state,
                dispatch_sync=dispatch_sync,
                write=write,
                cancel_event=self._cancel_event,
                prompt_user=prompt_user,
                sample_filter=samples,
                exclude_filter=excludes,
                thickness=thickness,
                bkg_sample=bkg_sample,
                config_filter=config_filter,
                force=force,
                continue_mode=continue_mode,
                standard_sample=standard_sample,
                from_step=from_step,
                fresh=fresh,
            )
        finally:
            loop.close()
            try:
                self.state.save(SessionState.auto_save_path())
            except Exception:
                pass
        self.call_from_thread(self._set_job_running, False)
        self.call_from_thread(self._update_status_bars)

    def _render_table(
        self, log: RichLog, columns: list[str], rows: list[dict], title: str = ""
    ) -> None:
        """Render a Rich table to the output log."""
        table = Table(title=title, show_lines=False, padding=(0, 1))
        for col in columns:
            justify = "right" if col in (
                "Run #", "Idx", "Count", "Time(s)"
            ) else "left"
            table.add_column(col, justify=justify)

        for row_data in rows:
            table.add_row(*[row_data.get(c, "") for c in columns])

        log.write(table, shrink=False)

    def _render_working_table(self, log: RichLog, rows: list[dict]) -> None:
        """Render working table with Config next to Sample and two-line run cells."""
        table = Table(
            title="Working Table",
            show_lines=True,
            padding=(0, 1),
            row_styles=["", ""],
        )

        # Column order: Idx, Sample, Config, then run numbers, Status
        table.add_column("Idx", justify="right", style="bold", width=4)
        table.add_column("Sample", justify="left", min_width=14)
        table.add_column("Config", justify="left", style="cyan", min_width=10)
        table.add_column("Scatt", justify="left", min_width=10)
        table.add_column("Trans", justify="left", min_width=10)
        table.add_column("Thick", justify="right", width=5)
        table.add_column("Bkg", justify="left", min_width=10)
        table.add_column("BkgTr", justify="left", min_width=10)
        table.add_column("Empty", justify="left", min_width=10)
        table.add_column("Status", justify="left", style="green", width=8)

        columns = ["Idx", "Sample", "Config", "Scatt", "Trans", "Thick", "Bkg", "BkgTr", "Empty", "Status"]
        for row_data in rows:
            table.add_row(*[row_data.get(c, "") for c in columns])

        log.write(table, shrink=False)

    def _render_preset_list(self, log: RichLog, rows: list[dict]) -> None:
        """Render preset list as a table."""
        table = Table(title="Available Presets", show_lines=False, padding=(0, 1))
        table.add_column("Name", justify="left", style="bold cyan", min_width=30)
        table.add_column("Description", justify="left", min_width=40)
        for row_data in rows:
            table.add_row(row_data["Name"], row_data["Description"])
        log.write(table, shrink=False)

    def _render_compare_table(
        self, log: RichLog, rows: list[dict], name_a: str, name_b: str,
    ) -> None:
        """Render side-by-side config comparison with diff highlighting."""
        table = Table(
            title=f"Compare: {name_a} vs {name_b}",
            show_lines=False,
            padding=(0, 1),
        )
        table.add_column("Parameter", justify="left", style="bold", min_width=35)
        table.add_column(name_a, justify="left", min_width=22)
        table.add_column(name_b, justify="left", min_width=22)

        for row_data in rows:
            diff = row_data["diff"]
            if diff == "same":
                continue  # Skip identical rows — only show differences
            param = row_data["param"]
            val_a = row_data["value_a"]
            val_b = row_data["value_b"]

            if diff == "diff":
                # Highlight differences in red/green
                table.add_row(
                    f"[bold]{param}[/bold]",
                    f"[red]{val_a}[/red]",
                    f"[green]{val_b}[/green]",
                )
            elif diff == "only_a":
                table.add_row(
                    f"[dim]{param}[/dim]",
                    f"[yellow]{val_a}[/yellow]",
                    "[dim]—[/dim]",
                )
            elif diff == "only_b":
                table.add_row(
                    f"[dim]{param}[/dim]",
                    "[dim]—[/dim]",
                    f"[yellow]{val_b}[/yellow]",
                )

        log.write(table, shrink=False)

    def _render_stitch_table(self, log: RichLog, groups: list[dict]) -> None:
        table = Table(title="Stitch Table", show_lines=True, padding=(0, 1))
        table.add_column("Idx", justify="right", style="bold", width=4)
        table.add_column("Sample", style="bold", min_width=16)
        table.add_column("Configs", min_width=20)
        table.add_column("Files", min_width=30)
        table.add_column("Overlap Q", min_width=20)
        table.add_column("Target", justify="center", width=6)
        table.add_column("Status", width=10)

        for idx, g in enumerate(groups):
            configs_str = "\n".join(g.get("configs", []))
            files_str = "\n".join(os.path.basename(f) for f in g.get("files", []))
            overlaps = g.get("overlaps", [])
            if overlaps:
                pairs = [f"[{overlaps[i]:.4f}, {overlaps[i+1]:.4f}]" for i in range(0, len(overlaps), 2)]
                overlap_str = "\n".join(pairs)
            else:
                overlap_str = "—"

            status = g.get("status", "ready")
            status_styled = {"done": "[green]done[/green]", "error": "[red]error[/red]", "1 config": "[dim]1 config[/dim]"}.get(status, status)

            table.add_row(
                str(idx),
                g.get("sample_name", ""),
                configs_str,
                files_str,
                overlap_str,
                str(g.get("target_profile_index", 0)),
                status_styled,
            )

        log.write(table, shrink=False)

    def _render_config_table(self, log: RichLog, rows: list[dict], config_id: str) -> None:
        """Render configuration parameters as a table."""
        table = Table(title=f"Config: {config_id}", show_lines=False, padding=(0, 1))
        table.add_column("Parameter", justify="left", style="bold", min_width=30)
        table.add_column("Value", justify="left", min_width=20)
        table.add_column("", justify="center", width=3)  # source marker

        for row_data in rows:
            table.add_row(row_data["Parameter"], row_data["Value"], row_data.get("Src", ""))

        log.write(table, shrink=False)

    async def _handle_help(self, args: list[str], state: SessionState) -> CommandResult:
        """Handle /help — show available commands.

        /help            — full command reference (long)
        /help --simple   — quickstart workflow with the 7 essential steps
        """
        if args and args[0].lower() in ("--simple", "-s", "simple", "quickstart"):
            simple_text = (
                "[bold]Quickstart — basic reduction workflow:[/]\n"
                "\n"
                "[bold cyan]1. Load the catalog[/]\n"
                "   [yellow]/load ipts <number>[/]              e.g. /load ipts 35884\n"
                "   Fetches all runs for that IPTS from ONCat.\n"
                "\n"
                "[bold cyan]2. Check run classes; reclass if needed[/]\n"
                "   [yellow]/show catalog[/]                    Look at the 'Class' column\n"
                "   [yellow]/reclass <runs> <class>[/]          e.g. /reclass 172804 scatt\n"
                "   [yellow]/reclass --sample BkgG sample[/]    Reclass by sample name (S-/T-aware)\n"
                "   [yellow]/reclass <runs> i[/]                'i' or 'n' → ignore (excluded from matching)\n"
                "   Classes: scatt, trans, bkg, bkgtrans, empty, sample, ignore\n"
                "\n"
                "[bold cyan]3. Build the working table[/]\n"
                "   [yellow]/matchruns[/]                       Auto-matches trans/bkg/empty per config\n"
                "\n"
                "[bold cyan]4. Inspect and edit the table[/]\n"
                "   [yellow]/show table[/]                      Look it over\n"
                "   [yellow]/set <row> <field> <value>[/]       e.g. /set 3 bkg 172810\n"
                "   [yellow]/assign bkg <sample>[/]             Bulk reassign background per config\n"
                "   [yellow]/apply preset auto[/]               Apply preset reduction params per config\n"
                "\n"
                "[bold cyan]5. Reduce[/]\n"
                "   [yellow]/reduce all[/]                      Reduce every row\n"
                "   [yellow]/reduce --new[/]                    Only rows whose status is not 'done'\n"
                "   [yellow]/reduce <row>[/]                    Single row or range (e.g. /reduce 1-4)\n"
                "\n"
                "[bold cyan]6. Stitch profiles across configurations[/]\n"
                "   [yellow]/stitch smart[/]                    Build stitch table + auto-detect overlap Q ranges\n"
                "   [yellow]/stitch run[/]                      Execute the merge (produces merged_*_Iq.txt)\n"
                "   [dim]/stitch smart prepares the table; /stitch run does the actual merging.\n"
                "    /stitch build is the manual alternative — use only if you want to set overlap\n"
                "    Q ranges by hand via /stitch set <sample> overlap <q1 q2 ...>.[/]\n"
                "\n"
                "[bold cyan]7. Save the session (optional but recommended)[/]\n"
                "   [yellow]/session save <name>[/]             Named save\n"
                "   [yellow]/session save[/]                    Save under the current session name\n"
                "   [dim]Session also autosaves after every command — /continue picks up the last one.[/]\n"
                "\n"
                "[bold cyan]8. Zip and email the results[/]\n"
                "   [yellow]/zipnsend <email>[/]               Default: merged*.txt from outputdir, capped at 25 MB\n"
                "   [yellow]/zipnsend <email> --pattern \"*_Iq.dat\"[/]   Custom file pattern\n"
                "   [yellow]/zipnsend <email> --subject \"IPTS-35884 results\"[/]   Custom subject\n"
                "   [yellow]/share <file|pattern>[/]            Anonymous 24h URL via here.now (alternative)\n"
                "\n"
                "[bold]Shortcut — let autopilot do it all:[/]\n"
                "   [yellow]/autopilot <ipts>[/]                Runs steps 1–6 (and calibration) automatically\n"
                "   [yellow]/autopilot --continue[/]            Mid-experiment: reduce only newly collected runs\n"
                "\n"
                "[dim]Tip: [bold]/guide[/bold] opens a side pane with these steps so you can follow along.\n"
                "Type /help for the full command reference.[/]"
            )
            return CommandResult(success=True, message=simple_text)

        help_text = (
            "[bold]Available Commands:[/]  [dim](use [bold]/help --simple[/bold] for the quickstart workflow, or [bold]/guide[/bold] to dock it as a side pane)[/]\n"
            "\n"
            "[bold cyan]Catalog & Data Loading:[/]\n"
            "  /load ipts <number>           — Fetch catalog from ONCat\n"
            "  /refresh catalog              — Re-fetch current IPTS catalog (preserves /reclass overrides; reports new runs)\n"
            "  /list ipts *                  — List all EQSANS experiments from ONCat\n"
            "  /list ipts <text>             — Search by title or team member name\n"
            "  /show catalog                 — Display loaded catalog\n"
            "  /show ipts                    — Show current IPTS number\n"
            "  /save catalog <file>          — Export catalog to CSV\n"
            "  /load catalog <file>          — Load catalog from CSV\n"
            "\n"
            "[bold cyan]Working Table:[/]\n"
            "  /show table                   — Show current working table\n"
            "  /show table --sample <name>   — Filter by sample name (read-only)\n"
            "  /reclass <runs> <class>       — Override run class (scatt/trans/bkg/bkgtrans/empty/sample/ignore)\n"
            "  /reclass --sample <name> <class> — Reclass all runs whose title contains <name>\n"
            "                                  Classes: scatt, trans, bkg, bkgtrans, empty, emptyscatt, sample, ignore (alias: i, n)\n"
            "                                  'sample' respects S-/T- prefix; 'ignore' excludes from /matchruns\n"
            "  /matchruns                    — Auto-match trans/bkg/empty runs (REBUILDS table, resets row status)\n"
            "  /matchruns --update           — Add new scattering runs only; preserves 'done' rows (use after /refresh catalog)\n"
            "  /assign bkg <sample>          — Reassign background for all rows (config-aware)\n"
            "  /set <row> <field> <value>    — Set field (row = index, run#, range, or all)\n"
            "  /set --sample <name> <field> <value> — Set field by sample name\n"
            "  /remove <row>                — Remove rows (index, run#, range, all --keep sample)\n"
            "  /remove --sample <name>       — Remove by sample name\n"
            "  /save table <name>            — Save working table\n"
            "  /load table <name>            — Load working table\n"
            "\n"
            "[bold cyan]Multi-Table:[/]\n"
            "  /table list                   — List all tables\n"
            "  /table new <name>             — Create and switch to new table\n"
            "  /table <name>                 — Switch active table\n"
            "  /table clone <src> <dst>      — Clone a table\n"
            "  /table rename <old> <new>     — Rename a table\n"
            "  /table delete <name>          — Delete a table\n"
            "  /move <row> <table>           — Move rows to another table\n"
            "\n"
            "[bold cyan]Configuration:[/]\n"
            "  /config list                  — List configs (table + stored extras like clones)\n"
            "  /config clone <src> <dst>     — Copy a config to a new name (then edit independently);\n"
            "                                  <dst> must contain <src>'s config ID: 4m10a → 4m10a_v2\n"
            "  /config rows <id>             — Show which rows reference <id>\n"
            "  /show config <id>             — Show reduction parameters for config\n"
            '  /set config <id> <param> <val> — Set config parameter\n'
            '  /set config all <param> <val> — Apply to every config; sticky default for future ones\n'
            "  /set <row> cfg <name>         — Reassign row to a (cloned) config; 'none' clears override (aliases: config, configuration)\n"
            "  /set --sample <name> cfg <new> — Bulk-reassign rows matching <name>\n"
            "\n[bold cyan]Instrument calibration files (machine physics):[/]\n"
            "  /instrument show              — Dark/flood/flux + detoffset/scalecomp per config, and their cycle\n"
            "  /instrument list [run]        — Cycle inventory and what a run resolves to\n"
            "  /instrument apply [--force]   — Re-resolve now (--force overrides your own /set config values)\n"
            "  /instrument pin <cycle>       — Freeze to one cycle (e.g. 2026A); /instrument unpin to release\n"
            "  /instrument off | on          — Disable/enable automatic resolution at /matchruns\n"
            "  /instrument check             — Verify referenced calibration files still exist\n"
            "  [dim]Resolved automatically at /matchruns and in autopilot, by run number.[/dim]\n"
            "\n[bold cyan]Output & misc:[/]\n"
            "  /show outputdir               — Show output directory\n"
            "  /set outputdir <path>         — Set output directory\n"
            "  /set ipts <number>            — Set IPTS number\n"
            "  /set drtsans <version>        — Set drtsans version (default, dev, qa)\n"
            "\n"
            "[bold cyan]Presets:[/]\n"
            "  /show presets                 — List available preset configurations\n"
            "  /show preset <name>           — Show preset parameters\n"
            '  /apply preset <name> <config_id> — Copy preset to active config\n'
            "  /apply preset auto            — Auto-match closest preset to each config\n"
            "  /compare <a> <b>              — Side-by-side diff of two configs/presets\n"
            "\n"
            "[bold cyan]Reduction:[/]\n"
            "  /reduce <row>                 — Run data reduction (index, run#, range, all)\n"
            "  /reduce --new                 — Reduce only rows whose status is not 'done'\n"
            "  /reduce --sample <name>       — Reduce rows matching sample name (substring/glob)\n"
            "  /export script [filename]     — Generate standalone .py script\n"
            "\n"
            "[bold cyan]Data & Plotting:[/]\n"
            "  /list iq                      — List reduced I(Q) files\n"
            "  /list iqxqy                   — List I(Qx,Qy) files\n"
            "  /plot <file|pattern> [flags]  — Plot I(Q) data\n"
            "    Axes:  --logx --logy --linx --liny --loglog --linlin\n"
            "    Types: --kratky --guinier --porod\n"
            "    Range: --xmin/xmax/ymin/ymax <val>\n"
            "    Style: --noerror --grid --offset <factor> --title <text>\n"
            "    Save:  --save <path> --dpi <val>\n"
            "  /calibrate <porsil_file> [--ref NG3|NG7] [--qmin 0.01] [--qmax 0.1]\n"
            "                                — Calculate absolute scale from porsil\n"
            "\n"
            "[bold cyan]Stitch/Merge:[/]\n"
            "  /stitch build                 — Auto-build stitch table from reduced files\n"
            "  /stitch smart                 — Smart stitch with overlap quality analysis\n"
            "  /stitch show                  — Display stitch table\n"
            "  /stitch set <sample> overlap <vals> — Set overlap Q range\n"
            "  /stitch set <sample> target <idx>   — Set normalization target\n"
            "  /stitch run [sample]          — Execute stitching\n"
            "  /stitch removerow <idx|all>   — Remove row(s)\n"
            "  /stitch removeconfig <idx|all> <config> — Remove config from row(s)\n"
            "  /stitch reorder <idx|all> <c1,c2,...> — Reorder configs (lower-Q first)\n"
            "  /stitch script [filename]     — Export stitch script\n"
            "  /stitch save <name>           — Save stitch table\n"
            "  /stitch load <name>           — Load stitch table\n"
            "\n"
            "[bold cyan]Autopilot:[/]\n"
            "  /autopilot <ipts>             — Full automated reduction pipeline\n"
            "  /autopilot current            — Use current session IPTS/catalog\n"
            "  /autopilot <ipts> --continue  — Reduce only NEW runs (reuse saved calibration)\n"
            "  /autopilot current --from <N> — Skip steps 1..(N-1) and start at step N (see /autopilot for step list)\n"
            "  Options: --standard <name>    — Custom calibration standard (default: porsil)\n"
            "           --samples <a,b>      — Only reduce specific samples\n"
            "           --exclude <a,b>      — Reduce all except named samples\n"
            "           --bkg <sample>       — Use sample as background (config-aware)\n"
            "           --config <id>        — Reduce only this configuration\n"
            "           --thickness <cm>     — Set sample thickness (default 0.1)\n"
            "           --force              — Re-reduce all (ignore 'done' status)\n"
            "\n"
            "[bold cyan]Note (per-outputdir log):[/]\n"
            '  /note add "<text>"            — Add a manual timestamped note to {outputdir}/NOTE.md\n'
            "  /note show [N]                — Show last N entries (default 30)\n"
            "  /note path                    — Show NOTE.md file path\n"
            "  /note clear --yes             — Delete NOTE.md\n"
            "  [dim]All state-changing commands are auto-logged to NOTE.md for reproducibility[/dim]\n"
            "\n"
            "[bold cyan]Share:[/]\n"
            "  /share <file|pattern>         — Share files via here.now (24h link)\n"
            "  /zipnsend <email> [options]   — Zip files and email (--pattern, --dir, --subject)\n"
            "  /confirm [ipts] [options]     — Update IPTS reduction status (--status, --comment)\n"
            "\n"
            "[bold cyan]LLM:[/]\n"
            "  /models                       — List available LLM models\n"
            "  /models <name>                — Switch LLM model\n"
            "\n"
            "[bold cyan]Settings:[/]\n"
            "  /settings                     — Show current settings\n"
            "  /settings textwrap <width>    — Set text wrap width (40-200)\n"
            "  /settings figsize <w> <h>     — Set default plot size (e.g. 8 6)\n"
            "  /settings dpi <value>         — Set default plot DPI (50-600)\n"
            "  /settings plotscale <scale>   — Default axis scale (loglog/linlin/loglin/linlog)\n"
            "  /settings errorbars <on|off>  — Toggle default error bars\n"
            "  /settings linestyle <style>   — Default style (line/marker/line+marker)\n"
            "  /settings multiprocessing <n> — Parallel reduction jobs (1-4, default 1)\n"
            "\n"
            "[bold cyan]Session:[/]\n"
            "  /continue                     — Resume most recent session (autosave or named)\n"
            "  /session list                 — List saved sessions\n"
            "  /session save [name]          — Save current session\n"
            "  /session load <name>          — Load a saved session\n"
            "  /help                         — This message\n"
            "  /quit                         — Exit\n"
            "\n"
            "[bold cyan]Shell Commands:[/]\n"
            "  /ls [path]                    — List directory contents\n"
            "  /cd <path>                    — Change directory\n"
            "  /pwd                          — Print working directory\n"
            "  /mkdir <path>                 — Create directory\n"
            "  /cat <file>                   — Display file contents\n"
            "  /head <file> [n]              — Show first n lines (default 10)\n"
            "  /tail <file> [n]              — Show last n lines (default 10)\n"
            "  /cp <src> <dst>               — Copy file or directory\n"
            "  /mv <src> <dst>               — Move/rename file\n"
            "  /rm <file> [file2...]         — Remove files or directories\n"
            "  /sh <command>                 — Run shell command\n"
            "\n"
            "[dim]Or type in natural language — e.g., 'show me runs from IPTS 35520'[/]\n"
            "[dim]Use ↑/↓ arrows to navigate command history[/]"
        )
        return CommandResult(success=True, message=help_text)

    _GUIDE_TEXT = (
        "[bold underline]EQSANS CLI — Quickstart[/]\n"
        "\n"
        "[bold cyan]1. Load catalog[/]\n"
        "   [yellow]/load ipts <N>[/]\n"
        "\n"
        "[bold cyan]2. Check / fix classes[/]\n"
        "   [yellow]/show catalog[/]\n"
        "   [yellow]/reclass <runs> <class>[/]\n"
        "   [yellow]/reclass --sample <name> <class>[/]\n"
        "   [dim]classes: scatt, trans, bkg,\n"
        "   bkgtrans, empty, sample, i (ignore)[/]\n"
        "\n"
        "[bold cyan]3. Build working table[/]\n"
        "   [yellow]/matchruns[/]\n"
        "\n"
        "[bold cyan]4. Inspect / edit[/]\n"
        "   [yellow]/show table[/]\n"
        "   [yellow]/set <row> <field> <val>[/]\n"
        "   [yellow]/assign bkg <sample>[/]\n"
        "   [yellow]/apply preset auto[/]\n"
        "\n"
        "[bold cyan]5. Reduce[/]\n"
        "   [yellow]/reduce all[/]\n"
        "   [yellow]/reduce --new[/]\n"
        "\n"
        "[bold cyan]6. Stitch configurations[/]\n"
        "   [yellow]/stitch smart[/]\n"
        "   [yellow]/stitch run[/]\n"
        "\n"
        "[bold cyan]7. Save session[/]\n"
        "   [yellow]/session save \\[name][/]\n"
        "\n"
        "[bold cyan]8. Zip & email results[/]\n"
        "   [yellow]/zipnsend <email>[/]\n"
        "   [dim]Default: merged*.txt from\n"
        "   outputdir, ≤25 MB[/]\n"
        "   [yellow]/zipnsend you@ornl.gov --pattern \"*_Iq.dat\"[/]\n"
        "   [yellow]/share <file>[/]   [dim](24h public link)[/]\n"
        "\n"
        "[bold]Shortcut[/]\n"
        "   [yellow]/autopilot <ipts>[/]\n"
        "   [yellow]/autopilot --continue[/]\n"
        "\n"
        "[bold]Mid-experiment update[/]\n"
        "   [yellow]/refresh catalog[/]\n"
        "   [yellow]/matchruns --update[/]\n"
        "   [yellow]/reduce --new[/]\n"
        "\n"
        "[dim]/guide off  — close this pane\n"
        "/help       — full reference[/]"
    )

    async def _handle_guide(self, args: list[str], state: SessionState) -> CommandResult:
        """Show/hide the right-side quickstart guide pane.

        /guide          — toggle pane
        /guide off      — close pane
        /guide on       — open pane
        """
        try:
            pane = self.query_one("#guide-pane", VerticalScroll)
            content = self.query_one("#guide-content", Static)
        except Exception:
            return CommandResult(
                success=False,
                message="Guide pane not available in this view.",
            )

        sub = args[0].lower() if args else ""
        if sub in ("off", "hide", "close"):
            pane.remove_class("-visible")
            return CommandResult(success=True, message="Guide closed.")

        if sub in ("on", "open", "show"):
            content.update(Text.from_markup(self._GUIDE_TEXT))
            pane.add_class("-visible")
            pane.scroll_home(animate=False)
            return CommandResult(success=True, message="Guide opened.")

        # bare /guide → toggle
        if pane.has_class("-visible"):
            pane.remove_class("-visible")
            return CommandResult(success=True, message="Guide closed.")
        content.update(Text.from_markup(self._GUIDE_TEXT))
        pane.add_class("-visible")
        pane.scroll_home(animate=False)
        return CommandResult(success=True, message="Guide opened. Type /guide off to close. Scroll with mouse wheel or arrow keys when focused.")

    async def _handle_version(self, args: list[str], state: SessionState) -> CommandResult:
        return CommandResult(success=True, message=f"eqsanscli v{__version__}")

    async def _handle_list(self, args: list[str], state: SessionState) -> CommandResult:
        return CommandResult(
            success=False,
            message="Usage: /list <target>\n"
            "  /list iq                   — List reduced I(Q) files\n"
            "  /list iqxqy                — List I(Qx,Qy) files\n"
            "  /list configs              — List configurations\n"
            "  /list tables               — List saved and active tables\n"
            "  /list ipts *               — List all EQSANS experiments\n"
            "  /list ipts <text>          — Search experiments by title or member\n"
            "  /list ipts refresh         — Re-fetch experiment list from ONCat",
        )

    async def _handle_exit(self, args: list[str], state: SessionState) -> CommandResult:
        """Handle /exit and /quit."""
        try:
            state.save(SessionState.auto_save_path())
        except Exception:
            pass
        self.exit()
        return CommandResult(success=True)

    def action_focus_input(self) -> None:
        """Refocus the command input."""
        self.query_one("#cmd-input", CompletableInput).focus()

    def action_clear_log(self) -> None:
        """Clear the output log."""
        self.query_one("#output", RichLog).clear()

    def action_quit(self) -> None:
        """Quit with auto-save."""
        try:
            self.state.save(SessionState.auto_save_path())
        except Exception:
            pass
        self.exit()
