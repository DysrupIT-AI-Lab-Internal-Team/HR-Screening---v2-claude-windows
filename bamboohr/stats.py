from datetime import datetime, timezone

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

from .tracker import STATUS_DOWNLOADED, STATUS_SKIPPED, STATUS_FAILED, STATUS_NO_RESUME

_console = Console()

BAR_WIDTH = 20
BAR_FILLED = "█"
BAR_EMPTY = "░"


def _bar(count: int, max_count: int) -> Text:
    if max_count == 0:
        filled = 0
    else:
        filled = round((count / max_count) * BAR_WIDTH)
    empty = BAR_WIDTH - filled
    bar = Text()
    bar.append(BAR_FILLED * filled, style="bold green")
    bar.append(BAR_EMPTY * empty, style="dim white")
    return bar


class StatsCollector:
    def __init__(self, job_id: int, job_title: str = ""):
        self.job_id = job_id
        self.job_title = job_title
        self.total = 0
        self.downloaded = 0
        self.skipped = 0
        self.moved = 0
        self.failed = 0
        self.no_resume = 0
        self.stage_counts: dict[str, int] = {}
        self.movements: list[tuple[str, int, str, str]] = []  # (name, app_id, old_stage, new_stage)

    def record_downloaded(self) -> None:
        self.total += 1
        self.downloaded += 1

    def record_skipped(self) -> None:
        self.total += 1
        self.skipped += 1

    def record_moved(self, applicant_name: str, app_id: int, old_stage: str, new_stage: str) -> None:
        self.total += 1
        self.moved += 1
        self.movements.append((applicant_name, app_id, old_stage, new_stage))

    def record_failed(self) -> None:
        self.total += 1
        self.failed += 1

    def record_no_resume(self) -> None:
        self.total += 1
        self.no_resume += 1

    def record_stage(self, stage: str) -> None:
        label = stage.strip() or "Unknown"
        self.stage_counts[label] = self.stage_counts.get(label, 0) + 1

    def as_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "job_title": self.job_title,
            "total": self.total,
            STATUS_DOWNLOADED: self.downloaded,
            "moved": self.moved,
            STATUS_SKIPPED: self.skipped,
            STATUS_FAILED: self.failed,
            STATUS_NO_RESUME: self.no_resume,
        }

    def print_summary(self) -> None:
        now = datetime.now(timezone.utc).astimezone()
        run_time = now.strftime("%Y-%m-%d %H:%M %Z")

        # ── Header ────────────────────────────────────────────────────────────
        title_line = f"Job ID: [bold]{self.job_id}[/bold]"
        if self.job_title:
            title_line += f"  │  [bold]{self.job_title}[/bold]"

        header = Text(justify="center")
        header.append("BAMBOOHR RESUME DOWNLOAD REPORT\n", style="bold white")
        header.append(f"Job ID: {self.job_id}", style="bold yellow")
        if self.job_title:
            header.append(f"  │  {self.job_title}", style="bold white")
        header.append(f"\nRun: {run_time}", style="dim white")

        _console.print()
        _console.print(Panel(header, style="bold white on dark_blue", padding=(1, 4)))

        # ── Overall Summary ───────────────────────────────────────────────────
        summary_table = Table(
            box=box.ROUNDED,
            show_header=False,
            padding=(0, 2),
            min_width=42,
        )
        summary_table.add_column("Metric", style="white")
        summary_table.add_column("Count", justify="right", min_width=6)

        summary_table.add_row(
            Text("Total Applicants", style="bold white"),
            Text(str(self.total), style="bold white"),
        )
        summary_table.add_row(
            Text("✔  New Downloads", style="bold green"),
            Text(str(self.downloaded), style="bold green"),
        )
        summary_table.add_row(
            Text("➜  Stage Movements", style="bold yellow"),
            Text(str(self.moved), style="bold yellow"),
        )
        summary_table.add_row(
            Text("–  Skipped (no change)", style="dim white"),
            Text(str(self.skipped), style="dim white"),
        )
        summary_table.add_row(
            Text("✘  No Resume", style="bold red"),
            Text(str(self.no_resume), style="bold red"),
        )
        summary_table.add_row(
            Text("⚠  Failed", style="bold red"),
            Text(str(self.failed), style="bold red"),
        )

        _console.print(Panel(summary_table, title="[bold cyan]OVERALL SUMMARY[/bold cyan]", box=box.ROUNDED))

        # ── Applicants by Stage ───────────────────────────────────────────────
        if self.stage_counts:
            stage_table = Table(
                box=box.ROUNDED,
                padding=(0, 2),
                min_width=60,
            )
            stage_table.add_column("Stage", style="white", min_width=30)
            stage_table.add_column("Count", justify="right", style="bold white", min_width=6)
            stage_table.add_column("Distribution", min_width=BAR_WIDTH + 2)

            max_count = max(self.stage_counts.values()) if self.stage_counts else 1
            sorted_stages = sorted(self.stage_counts.items(), key=lambda x: x[1], reverse=True)

            for stage, count in sorted_stages:
                stage_table.add_row(stage, str(count), _bar(count, max_count))

            _console.print(Panel(
                stage_table,
                title="[bold cyan]APPLICANTS BY STAGE[/bold cyan]",
                box=box.ROUNDED,
            ))

        # ── Stage Movements ───────────────────────────────────────────────────
        if self.movements:
            move_table = Table(
                box=box.ROUNDED,
                padding=(0, 2),
                min_width=70,
            )
            move_table.add_column("Applicant", style="white", min_width=28)
            move_table.add_column("From Stage", style="bold yellow", min_width=22)
            move_table.add_column("To Stage", style="bold green", min_width=18)

            for name, app_id, old_stage, new_stage in self.movements:
                move_table.add_row(f"{name} ({app_id})", old_stage, new_stage)

            _console.print(Panel(
                move_table,
                title="[bold cyan]STAGE MOVEMENTS THIS RUN[/bold cyan]",
                box=box.ROUNDED,
            ))

        # ── Footer note ───────────────────────────────────────────────────────
        if self.failed > 0:
            _console.print(
                Panel(
                    Text("⚠  Check the log file for details on failed downloads.", style="bold red"),
                    box=box.ROUNDED,
                    style="red",
                )
            )

        _console.print()
