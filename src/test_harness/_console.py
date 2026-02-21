from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from test_harness._schema import Outcome, TestFinished

_OUTCOME_STYLES: dict[Outcome, str] = {
    Outcome.PASSED: "green",
    Outcome.FAILED: "red bold",
    Outcome.SKIPPED: "yellow",
    Outcome.ERROR: "red bold",
    Outcome.XFAILED: "yellow",
    Outcome.XPASSED: "yellow bold",
}


def _make_summary_table(results: list[TestFinished]) -> Table:
    counts: dict[Outcome, int] = {}
    total_duration = 0.0
    for r in results:
        counts[r.outcome] = counts.get(r.outcome, 0) + 1
        total_duration += r.duration

    table = Table(title="Test Results Summary", show_edge=False)
    table.add_column("Outcome", style="bold")
    table.add_column("Count", justify="right")

    for outcome in Outcome:
        count = counts.get(outcome, 0)
        if count == 0:
            continue
        style = _OUTCOME_STYLES.get(outcome, "")
        table.add_row(
            Text(outcome.value, style=style),
            Text(str(count), style=style),
        )

    table.add_section()
    table.add_row("Total", str(len(results)))
    table.add_row("Duration", f"{total_duration:.2f}s")
    return table


def _make_failure_panels(results: list[TestFinished]) -> list[Panel]:
    panels: list[Panel] = []
    failed = [
        r
        for r in results
        if r.outcome in (Outcome.FAILED, Outcome.ERROR) and r.longrepr
    ]
    for r in failed:
        panels.append(
            Panel(
                r.longrepr or "",
                title=f"[red bold]{r.nodeid}[/red bold]",
                border_style="red",
                expand=True,
            )
        )
    return panels


def print_results(results: list[TestFinished]) -> None:
    """Print a rich-formatted summary of test results to stderr."""
    console = Console(stderr=True)

    if not results:
        console.print("[yellow]No test results collected.[/yellow]")
        return

    # Print failure details first.
    for panel in _make_failure_panels(results):
        console.print(panel)
        console.print()

    # Print summary table.
    console.print(_make_summary_table(results))
