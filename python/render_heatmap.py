#!/usr/bin/env python3
"""Render daily activity time as a vector SVG calendar heatmap with Quilt.

The input CSV contains exactly two columns:
    date,moving_time

`moving_time` is the sum of all activity moving durations for that local
calendar date, expressed in decimal hours. The renderer does not read FIT files
or activity-level records.

The activity palette is owned by this project (python/activity_palette.py).
It is registered through Quilt's documented Python API at runtime, leaving the
Quilt package and its built-in palettes untouched.
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from activity_palette import (
    ACTIVITY_DEFAULT_THEME,
    ACTIVITY_THEMES,
    register_activity_palettes,
)

EXPECTED_COLUMNS = ["date", "moving_time"]
DEFAULT_TIMEZONE = "Europe/Rome"
SUPPORTED_THEMES = (
    *ACTIVITY_THEMES,
    "github",
    "blue",
    "purple",
    "mono",
    "dark",
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
        default=repository_root / "activity-heatmap.svg",
        help="SVG output path (default: activity-heatmap.svg at the repo root).",
    )
    parser.add_argument(
        "--timezone",
        default=DEFAULT_TIMEZONE,
        help=f"IANA timezone used for the displayed calendar (default: {DEFAULT_TIMEZONE}).",
    )
    parser.add_argument(
    "--theme",
    default=ACTIVITY_DEFAULT_THEME,
    choices=SUPPORTED_THEMES,
    help="Color palette to use for the heatmap.",
    )
    parser.add_argument(
        "--label",
        default="Activity time (hours)",
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


def parse_steps(raw: str | None) -> float | tuple[float, float, float, float] | None:
    """Convert the CLI step notation to the format expected by Quilt's API."""
    if raw is None:
        return None

    try:
        values = tuple(float(part.strip()) for part in raw.split(","))
    except ValueError as exc:
        raise ValueError("--steps must be one positive number or four comma-separated numbers.") from exc

    if len(values) == 1:
        return values[0]
    if len(values) != 4:
        raise ValueError("--steps must be one positive number or exactly four comma-separated numbers.")
    return values


def render_activity_svg(
    input_csv: Path,
    start: date,
    end: date,
    *,
    theme: str = ACTIVITY_DEFAULT_THEME,
    label: str = "Activity time (hours)",
    week_start: str = "sunday",
    steps: str | None = None,
    month_label_font_size: float = 9,
    month_label_color: str | None = None,
    weekday_label_font_size: float = 9,
    weekday_label_color: str | None = None,
    title_font_size: float = 14,
    title_color: str | None = None,
    legend_font_size: float = 9,
    legend_color: str | None = None,
) -> str:
    """Render a daily CSV with Quilt's Python API and this project's palette."""
    try:
        from habit_heatmap import load_events, render_svg
    except ImportError as exc:
        raise RuntimeError(
            "Quilt is not installed. Install the project dependencies with "
            "'python -m pip install -r python/requirements.txt'."
        ) from exc

    register_activity_palettes()

    # The input contains date-only Europe/Rome calendar dates, so no timezone
    # conversion is needed when loading the already-aggregated daily records.
    counts = load_events(
        input_csv,
        date_col="date",
        value_col="moving_time",
    )

    return render_svg(
        counts,
        start=start,
        end=end,
        theme=theme,
        label=label,
        week_start=week_start,
        steps=parse_steps(steps),
        month_label_font_size=month_label_font_size,
        month_label_color=month_label_color,
        weekday_label_font_size=weekday_label_font_size,
        weekday_label_color=weekday_label_color,
        title_font_size=title_font_size,
        title_color=title_color,
        legend_font_size=legend_font_size,
        legend_color=legend_color,
    )


def main() -> int:
    args = parse_args()

    try:
        start, end = resolve_window(args)
        input_csv = args.input_csv.expanduser().resolve()
        output_svg = args.output.expanduser().resolve()

        if output_svg.suffix.lower() != ".svg":
            raise ValueError("The activity heatmap renderer currently supports SVG output only.")

        n_rows = validate_input_csv(input_csv, start, end)
        svg = render_activity_svg(
            input_csv,
            start,
            end,
            theme=args.theme,
            label=args.label,
            week_start=args.week_start,
            steps=args.steps,
            month_label_font_size=args.month_label_font_size,
            month_label_color=args.month_label_color,
            weekday_label_font_size=args.weekday_label_font_size,
            weekday_label_color=args.weekday_label_color,
            title_font_size=args.title_font_size,
            title_color=args.title_color,
            legend_font_size=args.legend_font_size,
            legend_color=args.legend_color,
        )

        output_svg.parent.mkdir(parents=True, exist_ok=True)
        output_svg.write_text(svg, encoding="utf-8")

        if not output_svg.is_file() or output_svg.stat().st_size == 0:
            raise RuntimeError(
                f"Quilt finished without producing a non-empty SVG at {output_svg}"
            )
        if "<svg" not in svg[:2048]:
            raise RuntimeError(f"Output does not look like an SVG document: {output_svg}")

        print(f"Validated daily records: {n_rows}")
        print(
            f"Displayed window: {start.isoformat()} to {end.isoformat()} "
            f"({args.timezone})"
        )
        print(f"Palette: {args.theme}")
        print(f"Heatmap: {output_svg}")
        return 0

    except (FileNotFoundError, ValueError, RuntimeError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
