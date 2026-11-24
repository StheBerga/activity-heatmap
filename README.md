# Activity heatmap

A GitHub-style calendar showing daily timer-active physical activity time.

![Activity heatmap](running-heatmap.svg)

The SVG is generated automatically from Garmin FIT files and a private historical activity dataset. This repository contains the complete, reproducible processing pipeline; personal activity records remain in a separate private repository.

## What the heatmap shows

Each square represents one calendar day. Its intensity reflects the sum of activity moving time on that day. Multiple activities are aggregated together.

- The metric is FIT session `total_timer_time` (seconds), excluding paused time.
- All supported Garmin activity types are included, not only running.
- Historical records and FIT activities are summed by Europe/Rome calendar date.
- The displayed range is a rolling 365-calendar-day window.
- The SVG is rendered with [Quilt](https://github.com/StheBerga/quilt), using the dark theme and fixed 0.5-hour intensity steps.

## Architecture

The public repository contains the R processing code, Python Intervals.icu client, SVG renderer, tests, and GitHub Actions workflows.

At production time, GitHub Actions checks out only `data/historical_activities.csv` from the private [running-heatmap-data](https://github.com/StheBerga/running-heatmap-data) repository. It downloads the required original FIT files from Intervals.icu to temporary runner storage, builds a daily summary, renders the SVG, and publishes only `running-heatmap.svg`.

See [the architecture and privacy notes](docs/ARCHITECTURE.md) for details.

## Repository secrets

Configure these Actions secrets in this public repository:

| Secret | Purpose |
| --- | --- |
| `INTERVALS_API_KEY` | Personal Intervals.icu API key with access to activity files |
| `HEATMAP_DATA_READ_TOKEN` | Fine-grained GitHub token with **Contents: read** access to `StheBerga/running-heatmap-data` only |

The workflow uses its automatically provided `GITHUB_TOKEN` to update the SVG in this repository. No separate publishing token is required.

## Local development

Python helper tests:

```bash
python -m unittest discover -s python -p 'test_*.py' -v
```

R aggregation test (requires R):

```bash
Rscript tests/test_process_activities.R
```

The full production pipeline additionally requires the R package `FITfileR`, Python dependencies in `python/requirements.txt`, and a private historical CSV plus an Intervals.icu API key. Never commit FIT files, personal activity-level records, API keys, or generated intermediate CSVs to this repository.

## Privacy

The public SVG reveals the dates on which activity occurred and the relative daily moving-time totals. Raw FIT files can contain GPS tracks, timestamps, heart-rate data, and device information; they are not published here. The historical CSV and all intermediate activity data remain private.
