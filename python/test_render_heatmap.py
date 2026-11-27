"""Offline validation tests for the SVG rendering wrapper and project palette."""

import csv
import tempfile
import unittest
from argparse import Namespace
from datetime import date
from pathlib import Path
from unittest.mock import patch

from activity_palette import (
    ACTIVITY_DEFAULT_THEME,
    ACTIVITY_THEMES,
    validate_activity_palettes,
)
from render_heatmap import (
    parse_args,
    parse_steps,
    render_activity_svg,
    resolve_window,
    validate_input_csv,
)


class RenderValidationTests(unittest.TestCase):
    def test_accepts_daily_moving_time_csv(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "daily.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(["date", "moving_time"])
                writer.writerow(["2026-11-23", "1.5"])
                writer.writerow(["2026-11-24", "0.25"])
            count = validate_input_csv(path, date(2026, 11, 23), date(2026, 11, 24))
            self.assertEqual(count, 2)

    def test_rejects_duplicate_daily_dates(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "daily.csv"
            path.write_text(
                "date,moving_time\n2026-11-24,1\n2026-11-24,2\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "More than one daily record"):
                validate_input_csv(path, date(2026, 11, 24), date(2026, 11, 24))

    def test_rejects_rows_outside_display_window(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "daily.csv"
            path.write_text("date,moving_time\n2026-11-22,1\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "outside the render window"):
                validate_input_csv(path, date(2026, 11, 23), date(2026, 11, 24))

    def test_explicit_window_must_be_complete(self):
        args = Namespace(timezone="UTC", start=date(2026, 11, 24), end=None)
        with self.assertRaisesRegex(ValueError, "Pass both"):
            resolve_window(args)

def test_default_cli_theme_is_project_palette(self):
    with patch("sys.argv", ["render_heatmap.py", "daily.csv"]):
        args = parse_args()

    self.assertEqual(args.theme, ACTIVITY_DEFAULT_THEME)


def test_both_palettes_contain_five_valid_hex_colors(self):
    validate_activity_palettes()

    self.assertEqual(len(ACTIVITY_THEMES), 2)

    for theme_name, palette in ACTIVITY_THEMES.items():
        with self.subTest(theme=theme_name):
            self.assertEqual(len(palette), 5)

            for color in palette:
                self.assertRegex(color, r"^#[0-9a-fA-F]{6}$")
                
    def test_both_custom_palettes_are_used_in_rendered_svg(self):
        for theme_name, palette in ACTIVITY_THEMES.items():
            with self.subTest(theme=theme_name):
                with tempfile.TemporaryDirectory() as temp_dir:
                    path = Path(temp_dir) / "daily.csv"
                    path.write_text(
                    "date,moving_time\n"
                    "2026-11-23,0.25\n"
                    "2026-11-24,2.0\n",
                    encoding="utf-8",
                )

                svg = render_activity_svg(
                    path,
                    date(2026, 11, 23),
                    date(2026, 11, 24),
                    theme=theme_name,
                    steps="0.5",
                )

            for color in palette:
                self.assertIn(color, svg)

    def test_steps_are_converted_to_quilt_api_values(self):
        self.assertEqual(parse_steps("0.5"), 0.5)
        self.assertEqual(parse_steps("0.5,1,1.5,2"), (0.5, 1.0, 1.5, 2.0))
        self.assertIsNone(parse_steps(None))
        with self.assertRaisesRegex(ValueError, "exactly four"):
            parse_steps("1,2")


if __name__ == "__main__":
    unittest.main()
