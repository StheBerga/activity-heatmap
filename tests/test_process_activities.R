# Synthetic, privacy-safe regression test for the daily aggregation layer.
repo_root <- normalizePath(".", winslash = "/", mustWork = TRUE)
source(file.path(repo_root, "R", "fit_to_activity.R"))
source(file.path(repo_root, "R", "process_activities.R"))

fixture <- file.path(
  repo_root, "tests", "fixtures", "historical_activities.csv"
)
activities_dir <- tempfile("empty-fit-directory-")
dir.create(activities_dir)
output_file <- tempfile("daily-activities-", fileext = ".csv")

result <- process_activities(
  activities_dir = activities_dir,
  historical_csv = fixture,
  window_days = 365L,
  timezone = "Europe/Rome",
  output_file = output_file,
  as_of = as.POSIXct("2026-11-24 12:00:00", tz = "UTC"),
  quiet = TRUE
)

stopifnot(
  identical(names(result$summary), c("date", "moving_time")),
  nrow(result$summary) == 2L,
  identical(result$summary$date, c("2026-11-23", "2026-11-24")),
  isTRUE(all.equal(result$summary$moving_time, c(1.5, 0.25))),
  file.exists(output_file),
  identical(names(utils::read.csv(output_file)), c("date", "moving_time"))
)

unlink(c(activities_dir, output_file), recursive = TRUE)
cat("R activity aggregation tests passed.\n")
