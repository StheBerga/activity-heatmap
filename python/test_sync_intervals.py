"""Offline tests for the Intervals.icu full-refresh downloader."""

import csv
import gzip
import tempfile
import unittest
from datetime import date
from pathlib import Path

from sync_intervals import (
    decode_fit_payload,
    read_latest_historical_date,
    resolve_date_window,
    select_fit_activities,
)


class DateWindowTests(unittest.TestCase):
    def test_initial_window_starts_after_historical_csv(self):
        oldest, newest = resolve_date_window(
            date(2026, 11, 24),
            date(2026, 9, 27),
            window_days=365,
        )
        self.assertEqual(oldest, date(2026, 9, 28))
        self.assertEqual(newest, date(2026, 11, 24))

    def test_window_becomes_full_rolling_year_after_history_expires(self):
        oldest, newest = resolve_date_window(
            date(2027, 10, 1),
            date(2026, 9, 27),
            window_days=365,
        )
        self.assertEqual(oldest, date(2026, 10, 2))
        self.assertEqual(newest, date(2027, 10, 1))

    def test_window_uses_latest_date_found_in_csv(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "historical.csv"
            with csv_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(["date", "moving_time"])
                writer.writerow(["2026-09-26", "1200"])
                writer.writerow(["2026-09-27", "1800"])

            self.assertEqual(
                read_latest_historical_date(csv_path),
                date(2026, 9, 27),
            )


class FitPayloadTests(unittest.TestCase):
    def setUp(self):
        # Minimal byte sequence with the standard FIT signature at offset 8.
        self.fit_payload = b"\x0e\x10\x00\x00\x00\x00\x00\x00.FIT"

    def test_accepts_uncompressed_fit_file(self):
        self.assertEqual(
            decode_fit_payload(self.fit_payload),
            self.fit_payload,
        )

    def test_decompresses_gzip_fit_file(self):
        self.assertEqual(
            decode_fit_payload(gzip.compress(self.fit_payload)),
            self.fit_payload,
        )

    def test_rejects_non_fit_download(self):
        with self.assertRaises(ValueError):
            decode_fit_payload(b"not a FIT file")

    def test_selects_only_unique_fit_activities(self):
        activities = [
            {"id": "i100", "file_type": "fit"},
            {"id": "i101", "file_type": "tcx"},
            {"id": "i100", "file_type": "fit"},
            {"id": "i102", "file_type": "FIT"},
        ]
        selected, skipped = select_fit_activities(activities)
        self.assertEqual([item["id"] for item in selected], ["i100", "i102"])
        self.assertEqual(skipped, 1)


if __name__ == "__main__":
    unittest.main()
