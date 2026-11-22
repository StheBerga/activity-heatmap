# Activity heatmap

A GitHub-style calendar visualizing my daily physical activity time.

![Activity heatmap](running-heatmap.svg)

The heatmap is automatically generated from Garmin FIT activities and
historical activity records. Only the rendered SVG is published here; original
activity files and intermediate datasets remain private.

## What does it show?

Each calendar square represents one day. Its intensity corresponds to the total
elapsed time spent exercising that day, aggregated across all activities.
Multiple activities performed on the same day are summed together.

## Data processing

- All supported Garmin activity types are included, not just running.
- Historical activity records are integrated with Garmin FIT exports.
- Activity durations are summed in seconds and expressed to Quilt as decimal
  hours.
- Dates are assigned using the Europe/Rome timezone.
- The heatmap covers a rolling 365-day window.

The image is automatically regenerated using GitHub Actions.
