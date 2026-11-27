# Synthetic, privacy-safe regression test for daily aggregation and JSON export.
repo_root <- normalizePath(".", winslash = "/", mustWork = TRUE)
source(file.path(repo_root, "R", "fit_to_activity.R"))
source(file.path(repo_root, "R", "process_activities.R"))

fixture <- file.path(repo_root, "tests", "fixtures", "historical_activities.csv")
activities_dir <- tempfile("empty-fit-directory-")
dir.create(activities_dir)
output_file <- tempfile("daily-activities-", fileext = ".csv")
json_output_file <- tempfile("activity-data-", fileext = ".json")
test_as_of <- as.POSIXct("2026-11-24 12:00:00", tz = "UTC")
test_generated_at <- as.POSIXct("2026-11-24 12:34:56", tz = "UTC")

result <- process_activities(
  activities_dir = activities_dir,
  historical_csv = fixture,
  window_days = 365L,
  timezone = "Europe/Rome",
  output_file = output_file,
  as_of = test_as_of,
  quiet = TRUE,
  json_output_file = json_output_file,
  generated_at = test_generated_at
)

stopifnot(
  identical(names(result$summary), c("date", "moving_time")),
  nrow(result$summary) == 2L,
  identical(result$summary$date, c("2026-11-23", "2026-11-24")),
  isTRUE(all.equal(result$summary$moving_time, c(1.5, 0.25))),
  file.exists(output_file),
  identical(names(utils::read.csv(output_file)), c("date", "moving_time")),
  file.exists(json_output_file),
  identical(result$json_output_file, normalizePath(json_output_file))
)

payload <- jsonlite::fromJSON(json_output_file, simplifyVector = FALSE)
stopifnot(
  identical(
    names(payload),
    c("schema_version", "generated_at", "timezone", "window", "days")
  ),
  as.integer(payload$schema_version) == 1L,
  identical(payload$generated_at, "2026-11-24T12:34:56Z"),
  identical(payload$timezone, "Europe/Rome"),
  identical(payload$window$start, "2025-11-25"),
  identical(payload$window$end, "2026-11-24"),
  length(payload$days) == 365L
)

json_dates <- vapply(payload$days, function(day) day$date, character(1))
json_values <- vapply(payload$days, function(day) day$moving_time, numeric(1))
expected_dates <- format(
  seq.Date(as.Date("2025-11-25"), as.Date("2026-11-24"), by = "day"),
  "%Y-%m-%d"
)
stopifnot(
  identical(json_dates, expected_dates),
  !anyDuplicated(json_dates),
  isTRUE(all.equal(json_values[match("2026-11-23", json_dates)], 1.5)),
  isTRUE(all.equal(json_values[match("2026-11-24", json_dates)], 0.25)),
  isTRUE(all.equal(json_values[match("2026-11-22", json_dates)], 0))
)

# Reconstruct the complete calendar from the CSV and compare with the JSON.
csv_daily <- utils::read.csv(output_file, stringsAsFactors = FALSE)
expected_values <- numeric(length(json_dates))
csv_indices <- match(csv_daily$date, json_dates)
stopifnot(!anyNA(csv_indices))
expected_values[csv_indices] <- csv_daily$moving_time
stopifnot(isTRUE(all.equal(
  json_values,
  expected_values,
  tolerance = 1e-12,
  check.attributes = FALSE
)))

# The JSON writer must reject duplicate daily dates.
duplicate_summary <- rbind(result$summary, result$summary[1, , drop = FALSE])
duplicate_error <- tryCatch(
  write_activity_json(
    duplicate_summary,
    result$window,
    "Europe/Rome",
    tempfile(fileext = ".json"),
    generated_at = test_generated_at
  ),
  error = identity
)
stopifnot(inherits(duplicate_error, "error"))

unlink(c(activities_dir, output_file, json_output_file), recursive = TRUE)
cat("R activity aggregation and JSON export tests passed.\n")
