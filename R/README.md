# R processing layer

The R layer has two responsibilities:

1. **FIT adapter** — read one FIT file and return a normalized activity record
   containing `start_time`, `sport`, and `moving_time_seconds`.
2. **Daily aggregation** — combine FIT records with historical CSV rows and
   sum moving time by Europe/Rome calendar date.

## FIT adapter contract

| Column | Type | Meaning |
| --- | --- | --- |
| `start_time` | POSIXct | Activity start instant, represented in UTC |
| `sport` | character | Normalized activity type; other Garmin sports are retained |
| `moving_time_seconds` | numeric | FIT session `total_timer_time`, in seconds |

The pipeline does not extract route coordinates, polylines, heart-rate series,
or device metadata. FIT files with multiple Session messages are expanded to
one normalized record per session, so multisport FIT files can contribute
each leg to the daily total.

## Historical CSV contract

`process_activities()` accepts `historical_csv`, an optional CSV containing
at least:

```csv
date,moving_time
2024-01-01,5130
2024-01-01,2700
```

Every row represents one activity. `moving_time` is numeric seconds. Dates
use `YYYY-MM-DD` and are already local calendar dates in Europe/Rome. Multiple
rows on a date are valid and are summed together with FIT activities.

## Daily output contract

The processing function combines both activity sources, applies the rolling
365-calendar-day window, then writes one row per active date:

```csv
date,moving_time
2026-11-19,2.175
```

`moving_time` is the daily sum expressed in decimal hours, solely to provide
a convenient numeric value to Quilt. The intermediate CSV is written to
`$RUNNER_TEMP` in GitHub Actions and must not be committed or published.
