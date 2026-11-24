# Architecture and privacy model

## Repositories

| Repository | Visibility | Responsibility |
| --- | --- | --- |
| `StheBerga/running-heatmap` | Public | R/Python source code, tests, workflows, documentation, rendered SVG |
| `StheBerga/running-heatmap-data` | Private | Historical activity CSV and archived original FIT files |

The public workflow reads only `data/historical_activities.csv` from the private repository. The archive of FIT files remains private and is not checked out by the production workflow.

## Production pipeline

```text
Private data repository
  data/historical_activities.csv
              |
              | sparse checkout (single file)
              v
Public GitHub Actions runner
  Intervals.icu API ---> temporary FIT files
              |                  |
              v                  v
       latest historical   R FIT adapter
            date            total_timer_time
              |                  |
              +---------+--------+
                        v
             R daily aggregation
             Europe/Rome dates
             rolling 365-day window
             moving_time in seconds
                        |
                        v
             temporary daily CSV
             date,moving_time (hours)
                        |
                        v
             Quilt SVG renderer
                        |
                        v
             running-heatmap.svg
                        |
                        v
             public repository
```

The synchronization script queries from the later of the rolling 365-day start and the day after the latest historical date. This prevents overlap between the archived history and Intervals.icu. When the historical records age out of the rolling window, the API query naturally covers the entire window.

## Secrets and permissions

Configure two repository Actions secrets in the public repository:

- `INTERVALS_API_KEY`: personal Intervals.icu API key.
- `HEATMAP_DATA_READ_TOKEN`: fine-grained GitHub token scoped to `StheBerga/running-heatmap-data`, with repository Contents read permission only.

The workflow's `GITHUB_TOKEN` has Contents write permission for the public repository so it can commit the SVG. No personal publishing token is needed.

The production workflow is restricted to scheduled or manually dispatched runs on `main`. The separate CI workflow has read-only repository permissions, uses synthetic fixtures, and does not check out private data or access secrets.

## Privacy boundary

The private CSV, archived FIT files, downloaded FIT files, activity-level rows, and intermediate daily CSV remain private. Only the rendered SVG is committed publicly. FIT files can contain precise GPS traces, timestamps, heart-rate records, and device metadata.

The SVG itself reveals dates with activity and relative daily moving-time totals. This is the intentionally public output.

## Metric definition

The metric is timer-active moving duration, excluding paused time. FIT sessions use `total_timer_time`, in seconds. Historical CSV rows use numeric seconds. Durations are summed across all activities on each Europe/Rome calendar date. The daily total is divided by 3600 to provide Quilt with decimal hours. The rendered calendar covers 365 dates, including the current local date.
