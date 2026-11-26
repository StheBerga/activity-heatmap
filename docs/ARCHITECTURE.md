# Architecture and privacy model

## Repositories

| Repository | Visibility | Responsibility |
| --- | --- | --- |
| `StheBerga/activity-heatmap` | Public | R/Python source code, tests, workflows, documentation, rendered SVG |
| `StheBerga/running-heatmap-data` | Private | Historical activity CSV only |

The public workflow checks out only `data/historical_activities.csv` from the
private repository. Original FIT files are downloaded directly from
Intervals.icu to temporary runner storage for each production run; they are
not archived in either repository.

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
             Quilt Python API
             project palette registered
                        |
                        v
             activity-heatmap.svg
                        |
                        v
             public repository
```

## Palette ownership

The project-specific five-color palette is stored in
`python/activity_palette.py`. The renderer registers it in the current Python
process using Quilt's documented `habit_heatmap.colors.THEMES` dictionary,
then calls the public `load_events` and `render_svg` APIs.

No files in the Quilt repository are modified. Quilt retains its own independent
built-in themes; the custom theme exists only while this project renders its
heatmap. The workflow selects the `activity` theme explicitly.

## Secrets and permissions

Configure two repository Actions secrets in the public repository:

- `INTERVALS_API_KEY`: personal Intervals.icu API key.
- `HEATMAP_DATA_READ_TOKEN`: fine-grained GitHub token scoped to
  `StheBerga/running-heatmap-data`, with repository Contents read permission
  only.

The workflow's `GITHUB_TOKEN` has Contents write permission for the public
repository so it can commit the SVG. No personal publishing token is needed.

The separate CI workflow has read-only repository permissions, installs the
same Quilt dependency as production, uses synthetic fixtures, and does not
check out private data or access secrets.

## Privacy boundary

The historical CSV, downloaded FIT files, activity-level rows, and intermediate
daily CSV remain private. FIT files and temporary summaries exist only on the
ephemeral GitHub Actions runner during a production run. Only the rendered SVG
is committed publicly. FIT files can contain precise GPS traces, timestamps,
heart-rate records, and device metadata.

The SVG itself reveals dates with activity and relative daily moving-time
totals. This is the intentionally public output.

## Metric definition

The metric is timer-active moving duration, excluding paused time. FIT sessions
use `total_timer_time`, in seconds. Historical CSV rows use numeric seconds.
Durations are summed across all activities on each Europe/Rome calendar date.
The daily total is divided by 3600 to provide Quilt with decimal hours. The
rendered calendar covers 365 dates, including the current local date.
