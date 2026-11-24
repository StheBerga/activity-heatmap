"""Offline validation tests for the SVG rendering wrapper."""

import csv
import tempfile
import unittest
from argparse import Namespace
from datetime import date
from pathlib import Path

from render_heatmap import resolve_window, validate_input_csv


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


if __name__ == "__main__":
    unittest.main()
