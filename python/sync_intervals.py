#!/usr/bin/env python3
"""Fetch the current FIT activity window from Intervals.icu.

Downloaded FIT files are written to a caller-supplied temporary directory. The
script never writes activity files or API credentials into the repository.
"""

from __future__ import annotations

import argparse
import base64
import csv
import gzip
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

API_BASE_URL = "https://intervals.icu/api/v1"
DEFAULT_TIMEZONE = "Europe/Rome"
DEFAULT_WINDOW_DAYS = 365
MAX_ACTIVITY_RESULTS = 1000
MIN_REQUEST_INTERVAL_SECONDS = 0.25
REQUEST_TIMEOUT_SECONDS = 60
MAX_RETRIES = 5
USER_AGENT = "running-heatmap-sync/1.0"
FIT_SIGNATURE = b".FIT"


def read_latest_historical_date(csv_path: Path) -> date | None:
    """Return the latest activity date in the historical CSV."""
    if not csv_path.is_file():
        raise FileNotFoundError(f"Historical CSV does not exist: {csv_path}")

    latest: date | None = None
    with csv_path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "date" not in reader.fieldnames:
            raise ValueError(
                f"{csv_path} must contain a 'date' column."
            )

        for line_number, row in enumerate(reader, start=2):
            value = (row.get("date") or "").strip()
            try:
                activity_date = date.fromisoformat(value[:10])
            except ValueError as exc:
                raise ValueError(
                    f"Invalid date in {csv_path}, line {line_number}: {value!r}"
                ) from exc

            if latest is None or activity_date > latest:
                latest = activity_date

    return latest


def resolve_date_window(
    today: date,
    latest_historical_date: date | None,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> tuple[date, date]:
    """Avoid overlap with historical data while retaining a rolling window.

    The API starts one day after the last date in the historical CSV, unless
    the rolling window starts later. Once the historical records expire from
    the 365-day window, this naturally becomes a complete rolling-year fetch.
    """
    if window_days < 1:
        raise ValueError("window_days must be a positive integer.")

    rolling_start = today - timedelta(days=window_days - 1)
    if latest_historical_date is None:
        oldest = rolling_start
    else:
        oldest = max(rolling_start, latest_historical_date + timedelta(days=1))

    if oldest > today:
        raise ValueError(
            "The latest historical CSV date is later than the current date; "
            "the Intervals.icu query window would be empty."
        )

    return oldest, today


def decode_fit_payload(payload: bytes) -> bytes:
    """Accept either a gzip-compressed or an already-uncompressed FIT file."""
    if payload.startswith(b"\x1f\x8b"):
        try:
            fit_data = gzip.decompress(payload)
        except OSError as exc:
            raise ValueError("Intervals.icu returned an invalid gzip file.") from exc
    else:
        fit_data = payload

    if len(fit_data) < 12 or fit_data[8:12] != FIT_SIGNATURE:
        raise ValueError(
            "The downloaded activity does not have a valid FIT file signature."
        )

    return fit_data


def select_fit_activities(payload: Any) -> tuple[list[dict[str, Any]], int]:
    """Return unique activities with an available original FIT file."""
    if not isinstance(payload, list):
        raise ValueError("Unexpected Intervals.icu response: expected a JSON array.")

    selected: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    skipped = 0

    for index, activity in enumerate(payload):
        if not isinstance(activity, dict):
            raise ValueError(
                f"Unexpected activity item at response position {index}."
            )

        if str(activity.get("file_type") or "").strip().lower().lstrip(".") != "fit":
            skipped += 1
            continue

        activity_id = str(activity.get("id") or "").strip()
        if not activity_id:
            raise ValueError(
                f"FIT activity at response position {index} has no activity ID."
            )
        if not re.fullmatch(r"[A-Za-z0-9_-]+", activity_id):
            raise ValueError(f"Unexpected activity ID format: {activity_id!r}")

        if activity_id in seen_ids:
            continue

        seen_ids.add(activity_id)
        selected.append(activity)

    return selected, skipped


class IntervalsClient:
    """Small standard-library client for the personal Intervals.icu API."""

    def __init__(self, api_key: str) -> None:
        if not api_key.strip():
            raise ValueError(
                "INTERVALS_API_KEY is empty. Add it as a repository Actions secret."
            )

        credentials = base64.b64encode(
            f"API_KEY:{api_key.strip()}".encode("utf-8")
        ).decode("ascii")

        self._authorization = f"Basic {credentials}"
        self._last_request_started = 0.0

    def get(self, path: str, accept: str) -> bytes:
        url = f"{API_BASE_URL}{path}"

        for attempt in range(MAX_RETRIES):
            elapsed = time.monotonic() - self._last_request_started
            delay = MIN_REQUEST_INTERVAL_SECONDS - elapsed
            if delay > 0:
                time.sleep(delay)

            request = Request(
                url,
                headers={
                    "Authorization": self._authorization,
                    "Accept": accept,
                    # Intervals.icu's Cloudflare protection can block Python's
                    # default urllib User-Agent. This value was tested locally.
                    "User-Agent": USER_AGENT,
                },
                method="GET",
            )
            self._last_request_started = time.monotonic()

            try:
                with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                    return response.read()

            except HTTPError as exc:
                detail = exc.read(500).decode("utf-8", errors="replace")
                retry_after = exc.headers.get("Retry-After")

                if exc.code == 429 and attempt < MAX_RETRIES - 1:
                    try:
                        wait_seconds = max(1.0, float(retry_after or "5"))
                    except ValueError:
                        wait_seconds = 5.0
                    print(
                        f"Intervals.icu rate limit reached; retrying in "
                        f"{wait_seconds:g} seconds.",
                        file=sys.stderr,
                    )
                    time.sleep(wait_seconds)
                    continue

                if exc.code in (500, 502, 503, 504) and attempt < MAX_RETRIES - 1:
                    wait_seconds = 2 ** (attempt + 1)
                    print(
                        f"Intervals.icu returned HTTP {exc.code}; retrying in "
                        f"{wait_seconds} seconds.",
                        file=sys.stderr,
                    )
                    time.sleep(wait_seconds)
                    continue

                raise RuntimeError(
                    f"Intervals.icu returned HTTP {exc.code} for {path}: {detail}"
                ) from exc

            except (URLError, TimeoutError) as exc:
                if attempt >= MAX_RETRIES - 1:
                    raise RuntimeError(
                        f"Could not contact Intervals.icu for {path}: {exc}"
                    ) from exc

                wait_seconds = 2 ** (attempt + 1)
                print(
                    f"Intervals.icu request failed; retrying in "
                    f"{wait_seconds} seconds.",
                    file=sys.stderr,
                )
                time.sleep(wait_seconds)

        raise RuntimeError(f"Intervals.icu request failed after {MAX_RETRIES} attempts.")


def download_fit_activities(
    client: IntervalsClient,
    oldest: date,
    newest: date,
    output_dir: Path,
) -> tuple[int, int, int]:
    """List the date window and download every available original FIT file."""
    query = urlencode(
        {
            "oldest": oldest.isoformat(),
            "newest": newest.isoformat(),
            "limit": str(MAX_ACTIVITY_RESULTS),
        }
    )
    raw_listing = client.get(
        f"/athlete/0/activities?{query}",
        "application/json",
    )

    try:
        activities = json.loads(raw_listing.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Intervals.icu returned invalid activity-list JSON.") from exc

    if not isinstance(activities, list):
        raise RuntimeError("Intervals.icu activity response is not a JSON array.")

    if len(activities) >= MAX_ACTIVITY_RESULTS:
        raise RuntimeError(
            f"Intervals.icu returned {len(activities)} activities, reaching the "
            f"configured limit ({MAX_ACTIVITY_RESULTS}). Refusing to continue "
            "because the response may be truncated."
        )

    fit_activities, skipped_non_fit = select_fit_activities(activities)

    output_dir = output_dir.expanduser().resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        raise RuntimeError(
            f"Output directory is not empty: {output_dir}. "
            "Use a fresh temporary directory for each full refresh."
        )
    output_dir.mkdir(parents=True, exist_ok=True)

    for index, activity in enumerate(fit_activities, start=1):
        activity_id = str(activity["id"])
        escaped_id = quote(activity_id, safe="")
        payload = client.get(
            f"/activity/{escaped_id}/file",
            "application/octet-stream",
        )

        try:
            fit_data = decode_fit_payload(payload)
        except ValueError as exc:
            raise RuntimeError(
                f"Could not validate the FIT file for activity {activity_id}: {exc}"
            ) from exc

        destination = output_dir / f"{activity_id}.fit"
        destination.write_bytes(fit_data)

        if index == 1 or index == len(fit_activities) or index % 25 == 0:
            print(f"Downloaded {index}/{len(fit_activities)} FIT files.")

    return len(activities), len(fit_activities), skipped_non_fit


def parse_args() -> argparse.Namespace:
    repository_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description=(
            "Download the rolling 365-day FIT activity window from Intervals.icu "
            "to temporary storage for the private heatmap pipeline."
        )
    )
    parser.add_argument(
        "--historical-csv",
        type=Path,
        default=repository_root / "private-data" / "data" / "historical_activities.csv",
        help="Historical CSV used to avoid overlap with API activities.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="New temporary directory where FIT files will be written.",
    )
    parser.add_argument(
        "--timezone",
        default=DEFAULT_TIMEZONE,
        help=f"Timezone used to resolve today's date (default: {DEFAULT_TIMEZONE}).",
    )
    parser.add_argument(
        "--window-days",
        type=int,
        default=DEFAULT_WINDOW_DAYS,
        help=f"Number of rolling calendar days (default: {DEFAULT_WINDOW_DAYS}).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        try:
            today = datetime.now(ZoneInfo(args.timezone)).date()
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown timezone: {args.timezone!r}") from exc

        latest_historical_date = read_latest_historical_date(
            args.historical_csv.expanduser().resolve()
        )
        oldest, newest = resolve_date_window(
            today,
            latest_historical_date,
            args.window_days,
        )

        api_key = os.environ.get("INTERVALS_API_KEY", "")
        client = IntervalsClient(api_key)

        print(f"Intervals.icu full refresh: {oldest} to {newest} ({args.timezone})")
        if latest_historical_date is not None:
            print(
                "Latest historical CSV date:",
                latest_historical_date,
            )

        n_listed, n_downloaded, n_skipped = download_fit_activities(
            client,
            oldest,
            newest,
            args.output_dir,
        )

        print(f"Activities returned by API: {n_listed}")
        print(f"FIT files downloaded: {n_downloaded}")
        print(f"Activities skipped (no original FIT file): {n_skipped}")
        print(f"Temporary FIT directory: {args.output_dir.expanduser().resolve()}")
        return 0

    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
