# Daily activity JSON data contract

The workflow writes data/activity_data.json in the private
StheBerga/running-heatmap-data repository.

## Example

    {
      "schema_version": 1,
      "generated_at": "2026-11-27T03:17:00Z",
      "timezone": "Europe/Rome",
      "window": {
        "start": "2025-11-28",
        "end": "2026-11-27"
      },
      "days": [
        {
          "date": "2026-11-27",
          "moving_time": 1.5
        }
      ]
    }

The example shows one day for readability. A generated production file contains
exactly 365 entries in days.

## Fields

| Field | Type | Meaning |
| --- | --- | --- |
| schema_version | integer | JSON contract version; currently 1 |
| generated_at | string | UTC generation timestamp in ISO 8601 format |
| timezone | string | Calendar timezone used to assign activity dates; currently Europe/Rome |
| window.start | string | First date in the rolling window (YYYY-MM-DD) |
| window.end | string | Last date in the rolling window (YYYY-MM-DD) |
| days | array | One daily record for every date between window.start and window.end, inclusive |
| days[].date | string | Local calendar date (YYYY-MM-DD) |
| days[].moving_time | number | Total daily moving time in decimal hours |

## Data rules

- The source metric remains FIT session total_timer_time, in seconds.
- Historical CSV moving_time values are also read as seconds.
- R performs the only aggregation and converts daily totals to decimal hours once.
- The JSON is generated from the same R summary written to the temporary CSV used by Quilt.
- Every calendar date in the 365-day window is present, in ascending order.
- Inactive dates have moving_time: 0; active dates have a finite positive number.
- No activity-level records, FIT data, GPS tracks, heart-rate values, or additional metrics are included.
- The file is private and is not published to the public repository.

The workflow validates the JSON metadata, complete date sequence, non-negative
finite values, and exact agreement with the daily CSV before publishing it.
