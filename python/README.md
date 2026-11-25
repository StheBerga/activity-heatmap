# Python processing layer

The Python layer synchronizes original FIT files from Intervals.icu and renders
the daily R summary with [StheBerga/Quilt](https://github.com/StheBerga/quilt).

## Intervals.icu synchronization

The workflow calls `sync_intervals.py` once per production run:

```bash
export INTERVALS_API_KEY="your-personal-api-key"

python python/sync_intervals.py \
  --historical-csv private-data/data/historical_activities.csv \
  --output-dir "$RUNNER_TEMP/intervals-fit" \
  --timezone Europe/Rome \
  --window-days 365
```

The script:

- Reads the latest date in the historical CSV.
- Queries Intervals.icu from the later of the rolling-window start or the day
  after the historical CSV ends.
- Downloads only activities whose original file type is FIT.
- Handles both gzip-compressed and uncompressed FIT responses.
- Checks the FIT signature before writing each temporary file.
- Uses a descriptive User-Agent, request pacing, and retries for transient
  server errors and rate limiting.

FIT files are written only to the supplied temporary directory. The workflow
deletes that directory after R processing, including when processing fails.
The API key is read from the environment and is never written to disk.

## Tests

The synchronization helpers have offline unit tests covering date-window
selection, the historical CSV boundary, duplicate activity IDs, and compressed
or uncompressed FIT payloads:

```bash
python -m unittest discover -s python -p 'test_*.py' -v
```

## Rendering

The R processing layer writes a daily CSV with exactly two columns:
`date,moving_time`. The Python renderer validates it, resolves the local
365-day display window, and invokes Quilt:

```bash
python python/render_heatmap.py /path/to/daily-activities.csv \
  --timezone Europe/Rome \
  --theme dark \
  --label "Activity time (hours)" \
  --week-start sunday \
  --steps 0.5 \
  --output activity-heatmap.svg
```

The output is a vector SVG. Only this SVG is copied to the public repository.
