#!/usr/bin/env python3
"""Render daily activity time as a vector SVG calendar heatmap with Quilt.

The input CSV contains exactly two columns:
    date,moving_time

`moving_time` is the sum of all activity moving durations for that local
calendar date, expressed in decimal hours. The renderer does not read FIT files
or activity-level records.
"""

from __future__ import annotations

import argparse
import csv
import math
import shutil
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

EXPECTED_COLUMNS = ["date", "moving_time"]
DEFAULT_TIMEZONE = "Europe/Rome"
INSTALL_HINT = (
    'Install Quilt with: python -m pip install '
    '"habit-heatmap @ git+https://github.com/StheBerga/quilt.git"'
)


def parse_args() -> argparse.Namespace:
    repository_root = Path(__file__).resolve().parents[1]

    parser = argparse.ArgumentParser(
        description="Render daily activity time as a vector SVG Quilt heatmap."
    )
    parser.add_argument(
        "input_csv",
        type=Path,
        help="R-generated daily CSV containing date and moving_time.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=repository_root / "running-heatmap.svg",
        help="SVG output path (default: running-heatmap.svg at the repo root).",
    )
    parser.add_argument(
        "--timezone",
        default=DEFAULT_TIMEZONE,
        help=f"IANA timezone used for the displayed calendar (default: {DEFAULT_TIMEZONE}).",
    )
    parser.add_argument(
        "--theme",
        default="dark",
        choices=("github", "blue", "purple", "mono", "dark"),
        help="Quilt colour theme (default: dark).",
    )
    parser.add_argument(
        "--label",
        default="Daily moving time (hours)",
        help="Heatmap title/label.",
    )
    parser.add_argument(
        "--month-label-font-size",
        type=float,
        default=9,
        help="Month-label font size in SVG units (default: 9).",
    )
    parser.add_argument(
        "--month-label-color",
        default=None,
        help="Month-label hex color (default: automatic from theme).",
    )
    parser.add_argument(
        "--weekday-label-font-size",
        type=float,
        default=9,
        help="Weekday-label font size in SVG units (default: 9).",
    )
    parser.add_argument(
        "--weekday-label-color",
        default=None,
        help="Weekday-label hex color (default: automatic from theme).",
    )
    parser.add_argument(
        "--title-font-size",
        type=float,
        default=14,
        help="Title font size in SVG units (default: 14).",
    )
    parser.add_argument(
        "--title-color",
        default=None,
        help="Title hex color (default: automatic from theme).",
    )
    parser.add_argument(
        "--legend-font-size",
        type=float,
        default=9,
        help="Legend-text font size in SVG units (default: 9).",
    )
    parser.add_argument(
        "--legend-color",
        default=None,
        help="Legend-text hex color (default: automatic from theme).",
    )
    parser.add_argument(
        "--week-start",
        choices=("sunday", "monday"),
        default="sunday",
        help="First weekday in each column (default: sunday).",
    )
    parser.add_argument(
        "--steps",
        default=None,
        metavar="WIDTH[,WIDTH,WIDTH,WIDTH]",
        help=(
            "optional fixed intensity step widths in hours: one positive width "
            "repeated four times, or four comma-separated positive widths; "
            "omit for automatic scaling"
        ),
    )
    parser.add_argument(
        "--start",
        type=date.fromisoformat,
        help="First displayed date (YYYY-MM-DD); defaults to today minus 364 days.",
    )
    parser.add_argument(
        "--end",
        type=date.fromisoformat,
        help="Last displayed date (YYYY-MM-DD); defaults to today in --timezone.",
    )
    return parser.parse_args()


def resolve_window(args: argparse.Namespace) -> tuple[date, date]:
    try:
        local_today = datetime.now(ZoneInfo(args.timezone)).date()
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown timezone: {args.timezone!r}") from exc

    if (args.start is None) != (args.end is None):
        raise ValueError("Pass both --start and --end, or neither.")

    if args.start is None:
        end = local_today
        start = end - timedelta(days=364)
    else:
        start, end = args.start, args.end

    if start > end:
        raise ValueError("--start must be on or before --end.")

    return start, end


def validate_input_csv(path: Path, start: date, end: date) -> int:
    """Validate the minimal, daily-only data boundary before rendering."""
    if not path.is_file():
        raise FileNotFoundError(f"Input CSV does not exist: {path}")

    rows_seen = 0
    dates_seen: set[date] = set()

    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != EXPECTED_COLUMNS:
            raise ValueError(
                "The daily CSV must contain exactly these columns, in this order: "
                "date,moving_time. Found: "
                f"{reader.fieldnames!r}"
            )

        for line_number, row in enumerate(reader, start=2):
            try:
                day = date.fromisoformat(row["date"])
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid ISO date on CSV line {line_number}: {row['date']!r}"
                ) from exc

            try:
                moving_time = float(row["moving_time"])
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid moving_time on CSV line {line_number}: "
                    f"{row['moving_time']!r}"
                ) from exc

            if not math.isfinite(moving_time) or moving_time <= 0:
                raise ValueError(
                    f"moving_time on CSV line {line_number} must be finite and > 0."
                )
            if day in dates_seen:
                raise ValueError(
                    f"More than one daily record found for {day.isoformat()}. "
                    "The R aggregation should produce one row per date."
                )
            if not start <= day <= end:
                raise ValueError(
                    f"CSV date {day.isoformat()} is outside the render window "
                    f"{start.isoformat()} to {end.isoformat()}."
                )

            dates_seen.add(day)
            rows_seen += 1

    return rows_seen


def main() -> int:
    args = parse_args()

    try:
        start, end = resolve_window(args)
        input_csv = args.input_csv.expanduser().resolve()
        output_svg = args.output.expanduser().resolve()
        n_rows = validate_input_csv(input_csv, start, end)

        executable = shutil.which("habit-heatmap")
        if executable is None:
            raise RuntimeError(
                "Could not find the 'habit-heatmap' command on PATH. "
                + INSTALL_HINT
            )

        output_svg.parent.mkdir(parents=True, exist_ok=True)

        command = [
            executable,
            str(input_csv),
            "--date-col",
            "date",
            "--value-col",
            "moving_time",
            "--tz",
            args.timezone,
            "--start",
            start.isoformat(),
            "--end",
            end.isoformat(),
            "--theme",
            args.theme,
            "--label",
            args.label,
            "--week-start",
            args.week_start,
            "--month-label-font-size",
            str(args.month_label_font_size),
            "--weekday-label-font-size",
            str(args.weekday_label_font_size),
            "--title-font-size",
            str(args.title_font_size),
            "--legend-font-size",
            str(args.legend_font_size),
            "-o",
            str(output_svg),
            "--verbose",
        ]

        if args.month_label_color is not None:
            command.extend(["--month-label-color", args.month_label_color])
        if args.weekday_label_color is not None:
            command.extend(["--weekday-label-color", args.weekday_label_color])
        if args.title_color is not None:
            command.extend(["--title-color", args.title_color])
        if args.legend_color is not None:
            command.extend(["--legend-color", args.legend_color])

        if args.steps is not None:
            command.extend(["--steps", args.steps])

        subprocess.run(command, check=True)

        if not output_svg.is_file() or output_svg.stat().st_size == 0:
            raise RuntimeError(
                "Quilt finished without producing a non-empty SVG at "
                f"{output_svg}"
            )

        print(f"Validated daily records: {n_rows}")
        print(
            f"Displayed window: {start.isoformat()} to {end.isoformat()} "
            f"({args.timezone})"
        )

        with output_svg.open("r", encoding="utf-8") as svg_file:
            header = svg_file.read(2048)
        if "<svg" not in header:
            raise RuntimeError(
                f"Output does not look like an SVG document: {output_svg}"
            )

        print(f"Heatmap: {output_svg}")
        return 0

    except (
        FileNotFoundError,
        ValueError,
        RuntimeError,
        subprocess.CalledProcessError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
