# Process Garmin FIT exports and optional historical activity CSV records into
# one daily moving-time summary for the Quilt renderer.
#
# Canonical duration unit inside R: seconds.
# Quilt input contract: date,moving_time (decimal hours), one row per day.

.as_local_date <- function(x, timezone) {
  if (inherits(x, "Date")) {
    return(x)
  }

  if (!inherits(x, "POSIXt")) {
    x <- as.POSIXct(x, tz = "UTC")
  }

  as.Date(x, tz = timezone)
}

.relative_archive_path <- function(path, root) {
  root <- normalizePath(root, winslash = "/", mustWork = TRUE)
  path <- normalizePath(path, winslash = "/", mustWork = TRUE)
  prefix <- paste0(sub("/$", "", root), "/")

  if (startsWith(path, prefix)) {
    substring(path, nchar(prefix) + 1L)
  } else {
    basename(path)
  }
}

.read_historical_activities <- function(file) {
  if (is.null(file)) {
    return(data.frame(
      date = as.Date(character()),
      sport = character(),
      moving_time_seconds = numeric(),
      source = character(),
      stringsAsFactors = FALSE
    ))
  }

  if (!is.character(file) || length(file) != 1L || is.na(file) ||
      !file.exists(file)) {
    stop("Historical CSV does not exist: ", file, call. = FALSE)
  }

  # Read as character first so that values such as large integer seconds are
  # not accidentally converted through locale-dependent type guessing.
  historical <- utils::read.csv(
    file,
    stringsAsFactors = FALSE,
    check.names = FALSE,
    colClasses = "character",
    na.strings = c("", "NA")
  )

  required <- c("date", "moving_time")
  missing_columns <- setdiff(required, names(historical))
  if (length(missing_columns) > 0L) {
    stop(
      "Historical CSV is missing required column(s): ",
      paste(missing_columns, collapse = ", "),
      ". Expected at least: date,moving_time.",
      call. = FALSE
    )
  }

  # The CSV date is a local calendar date (Europe/Rome), not a UTC timestamp.
  # Taking the first ten characters also tolerates an ISO datetime column,
  # while preserving its explicitly supplied calendar date.
  date_text <- trimws(historical$date)
  activity_date <- as.Date(substr(date_text, 1L, 10L), format = "%Y-%m-%d")

  # Historical moving_time values are numeric seconds, one activity per row.
  moving_time_seconds <- suppressWarnings(
    as.numeric(trimws(historical$moving_time))
  )

  invalid_date <- is.na(activity_date)
  invalid_duration <- is.na(moving_time_seconds) |
    !is.finite(moving_time_seconds) |
    moving_time_seconds <= 0

  if (any(invalid_date)) {
    bad_rows <- which(invalid_date) + 1L
    stop(
      "Invalid historical date on CSV row(s): ",
      paste(bad_rows, collapse = ", "),
      ". Dates must use YYYY-MM-DD.",
      call. = FALSE
    )
  }

  if (any(invalid_duration)) {
    bad_rows <- which(invalid_duration) + 1L
    stop(
      "Invalid historical moving_time on CSV row(s): ",
      paste(bad_rows, collapse = ", "),
      ". Durations must be positive numeric seconds.",
      call. = FALSE
    )
  }

  data.frame(
    date = activity_date,
    sport = "historical",
    moving_time_seconds = moving_time_seconds,
    source = "historical_csv",
    stringsAsFactors = FALSE
  )
}


#' Write the daily moving-time summary as a versioned JSON document
#'
#' The JSON is expanded to every calendar date in the requested window.
#' Dates without activity receive a moving_time value of zero.
#'
#' @param summary Daily active-date summary with exactly date and moving_time
#'   columns. Moving time is expressed in decimal hours.
#' @param window Named character vector with start and end ISO dates.
#' @param timezone Timezone associated with the calendar dates.
#' @param output_file Destination JSON file.
#' @param generated_at Timestamp used for the generated_at field.
#'
#' @return The normalized path to the written JSON file.
#' @export
write_activity_json <- function(
    summary,
    window,
    timezone,
    output_file,
    generated_at = Sys.time()) {

  if (!requireNamespace("jsonlite", quietly = TRUE)) {
    stop("Package jsonlite is required to write the activity JSON.", call. = FALSE)
  }

  if (!is.data.frame(summary) ||
      !identical(names(summary), c("date", "moving_time"))) {
    stop(
      "summary must be a data frame with exactly date and moving_time columns.",
      call. = FALSE
    )
  }

  if (!is.character(window) || is.null(names(window)) ||
      !all(c("start", "end") %in% names(window))) {
    stop("window must contain named start and end dates.", call. = FALSE)
  }

  parse_window_date <- function(value, label) {
    if (length(value) != 1L || is.na(value)) {
      stop("Window ", label, " date must be one YYYY-MM-DD value.", call. = FALSE)
    }
    parsed <- as.Date(value, format = "%Y-%m-%d")
    if (is.na(parsed) || format(parsed, "%Y-%m-%d") != value) {
      stop("Window ", label, " date must use YYYY-MM-DD.", call. = FALSE)
    }
    parsed
  }

  start_date <- parse_window_date(window[["start"]], "start")
  end_date <- parse_window_date(window[["end"]], "end")
  if (start_date > end_date) {
    stop("Window start date must be on or before its end date.", call. = FALSE)
  }

  if (!is.character(timezone) || length(timezone) != 1L ||
      is.na(timezone) || !timezone %in% OlsonNames()) {
    stop("Unknown timezone: ", timezone, call. = FALSE)
  }

  if (!is.character(output_file) || length(output_file) != 1L ||
      is.na(output_file) || !nzchar(output_file)) {
    stop("output_file must be one non-empty path.", call. = FALSE)
  }

  if (!is.character(summary$date)) {
    stop("Summary dates must be character values in YYYY-MM-DD format.", call. = FALSE)
  }
  activity_dates <- as.Date(summary$date, format = "%Y-%m-%d")
  invalid_date <- is.na(activity_dates)
  if (any(!invalid_date)) {
    invalid_date[!invalid_date] <-
      format(activity_dates[!invalid_date], "%Y-%m-%d") != summary$date[!invalid_date]
  }
  if (any(invalid_date)) {
    stop("Summary contains an invalid date; expected YYYY-MM-DD.", call. = FALSE)
  }

  if (!is.numeric(summary$moving_time)) {
    stop("Summary moving_time values must be numeric hours.", call. = FALSE)
  }
  moving_time <- as.numeric(summary$moving_time)
  invalid_duration <- !is.finite(moving_time) | moving_time <= 0
  if (any(invalid_duration)) {
    stop("Summary moving_time values must be finite and greater than zero.", call. = FALSE)
  }

  if (anyDuplicated(activity_dates)) {
    stop("Summary contains duplicate daily dates.", call. = FALSE)
  }
  if (any(activity_dates < start_date | activity_dates > end_date)) {
    stop("Summary contains dates outside the requested window.", call. = FALSE)
  }

  generated_at <- tryCatch(
    as.POSIXct(generated_at, tz = "UTC"),
    error = function(e) as.POSIXct(NA, tz = "UTC")
  )
  if (length(generated_at) != 1L || is.na(generated_at)) {
    stop("generated_at must resolve to one valid timestamp.", call. = FALSE)
  }
  generated_at_text <- format(
    generated_at,
    format = "%Y-%m-%dT%H:%M:%SZ",
    tz = "UTC",
    usetz = FALSE
  )

  all_dates <- seq.Date(start_date, end_date, by = "day")
  all_date_text <- format(all_dates, "%Y-%m-%d")
  all_moving_time <- numeric(length(all_dates))
  if (length(activity_dates) > 0L) {
    date_indices <- match(format(activity_dates, "%Y-%m-%d"), all_date_text)
    all_moving_time[date_indices] <- moving_time
  }

  days <- lapply(seq_along(all_dates), function(i) {
    list(
      date = all_date_text[[i]],
      moving_time = as.numeric(all_moving_time[[i]])
    )
  })

  payload <- list(
    schema_version = 1L,
    generated_at = generated_at_text,
    timezone = timezone,
    window = list(
      start = format(start_date, "%Y-%m-%d"),
      end = format(end_date, "%Y-%m-%d")
    ),
    days = days
  )

  dir.create(dirname(output_file), recursive = TRUE, showWarnings = FALSE)
  jsonlite::write_json(
    payload,
    path = output_file,
    auto_unbox = TRUE,
    pretty = TRUE,
    digits = NA
  )

  if (!file.exists(output_file) || file.info(output_file)$size == 0L) {
    stop("Activity JSON was not written successfully.", call. = FALSE)
  }

  normalizePath(output_file, mustWork = TRUE)
}

#' Process FIT and historical records into a daily activity-time summary
#'
#' @param activities_dir Directory containing FIT files. Discovery is
#'   recursive, so year subdirectories are supported.
#' @param historical_csv Optional CSV with at least two columns:
#'   `date` (YYYY-MM-DD) and `moving_time` (numeric seconds). Each row must
#'   represent one activity. Multiple activities on the same date are allowed.
#' @param window_days Number of local calendar dates to retain. The default is
#'   365 dates, including `as_of`.
#' @param timezone Timezone used to assign FIT activities to local calendar
#'   dates. Defaults to `Europe/Rome`. Historical CSV dates are already local
#'   calendar dates and are not timezone-shifted.
#' @param output_file CSV destination. When `NULL`, writes
#'   `daily-activities.csv` to `$RUNNER_TEMP` or, locally, `tempdir()`.
#' @param json_output_file Optional JSON destination. When supplied, the JSON
#'   is generated from the same daily summary as the CSV and includes every
#'   date in the rolling window, with zero for inactive dates.
#' @param generated_at Timestamp used in the JSON generated_at field.
#' @param as_of Reference date/time for the rolling window. Defaults to the
#'   current instant. Exposed to make local tests reproducible.
#' @param quiet Suppress progress messages and warnings about individual files.
#'
#' @return An invisible list containing the daily summary, included activity
#'   records, FIT file and duplicate counts, parse errors, window limits, and
#'   CSV and optional JSON paths. The daily summary contains only `date` and
#'   `moving_time`.
#' @export
process_activities <- function(
    activities_dir = "activities",
    historical_csv = NULL,
    window_days = 365L,
    timezone = "Europe/Rome",
    output_file = NULL,
    as_of = Sys.time(),
    quiet = FALSE,
    json_output_file = NULL,
    generated_at = Sys.time()) {

  if (!dir.exists(activities_dir)) {
    stop("Activities directory does not exist: ", activities_dir,
         call. = FALSE)
  }

  if (length(window_days) != 1L || is.na(window_days) ||
      !is.finite(window_days) || window_days < 1L ||
      window_days != as.integer(window_days)) {
    stop("`window_days` must be a positive whole number.", call. = FALSE)
  }

  if (!is.character(timezone) || length(timezone) != 1L ||
      is.na(timezone) || !timezone %in% OlsonNames()) {
    stop("Unknown timezone: ", timezone, call. = FALSE)
  }

  if (!exists("fit_to_activity", mode = "function", inherits = TRUE)) {
    stop(
      "`fit_to_activity()` is not loaded. Run `source('R/fit_to_activity.R')` ",
      "before calling `process_activities()`.",
      call. = FALSE
    )
  }

  end_date <- .as_local_date(as_of, timezone)
  if (length(end_date) != 1L || is.na(end_date)) {
    stop("`as_of` must resolve to one valid date/time.", call. = FALSE)
  }
  start_date <- end_date - (as.integer(window_days) - 1L)

  fit_files <- sort(list.files(
    path = activities_dir,
    pattern = "\\.fit$",
    recursive = TRUE,
    full.names = TRUE,
    ignore.case = TRUE
  ))

  n_files_found <- length(fit_files)
  duplicate_file_paths <- character()
  duplicate_activity_count <- 0L
  parse_errors <- data.frame(
    file = character(),
    error = character(),
    stringsAsFactors = FALSE
  )

  # Remove byte-for-byte duplicate FIT exports before parsing.
  if (length(fit_files) > 0L) {
    file_hashes <- unname(tools::md5sum(fit_files))
    is_duplicate_file <- !is.na(file_hashes) & duplicated(file_hashes)
    duplicate_file_paths <- fit_files[is_duplicate_file]
    fit_files <- fit_files[!is_duplicate_file]
  }

  parsed <- vector("list", length(fit_files))
  parse_error_rows <- list()

  for (i in seq_along(fit_files)) {
    parse_result <- tryCatch(
      list(activity = fit_to_activity(fit_files[[i]]), error = NULL),
      error = function(e) list(activity = NULL, error = conditionMessage(e))
    )

    parsed[[i]] <- parse_result$activity

    if (!is.null(parse_result$error)) {
      parse_error_rows[[length(parse_error_rows) + 1L]] <- data.frame(
        file = .relative_archive_path(fit_files[[i]], activities_dir),
        error = parse_result$error,
        stringsAsFactors = FALSE
      )
    }
  }

  if (length(parse_error_rows) > 0L) {
    parse_errors <- do.call(rbind, parse_error_rows)
    rownames(parse_errors) <- NULL
  }

  parsed <- Filter(Negate(is.null), parsed)

  if (length(parsed) > 0L) {
    fit_activities <- do.call(rbind, parsed)
    rownames(fit_activities) <- NULL
  } else {
    fit_activities <- data.frame(
      start_time = as.POSIXct(character(), tz = "UTC"),
      sport = character(),
      moving_time_seconds = numeric(),
      stringsAsFactors = FALSE
    )
  }

  # Deduplicate FIT records that were re-exported with different file bytes.
  # Historical rows are not deduplicated because each CSV row is an activity;
  # the user has confirmed that the two sources do not overlap.
  if (nrow(fit_activities) > 0L) {
    activity_key <- paste(
      format(fit_activities$start_time,
             "%Y-%m-%dT%H:%M:%OS6", tz = "UTC"),
      fit_activities$sport,
      sprintf("%.3f", fit_activities$moving_time_seconds),
      sep = "|"
    )
    is_duplicate_activity <- duplicated(activity_key)
    duplicate_activity_count <- sum(is_duplicate_activity)
    fit_activities <- fit_activities[!is_duplicate_activity, , drop = FALSE]
  }

  if (nrow(fit_activities) > 0L) {
    fit_activities$date <- as.Date(fit_activities$start_time, tz = timezone)
    fit_activities$source <- "fit"
    fit_activities <- fit_activities[
      !is.na(fit_activities$date) &
        fit_activities$date >= start_date &
        fit_activities$date <= end_date,
      ,
      drop = FALSE
    ]
  } else {
    fit_activities$date <- as.Date(character())
    fit_activities$source <- character()
  }

  historical_activities <- .read_historical_activities(historical_csv)
  if (nrow(historical_activities) > 0L) {
    historical_activities <- historical_activities[
      historical_activities$date >= start_date &
        historical_activities$date <= end_date,
      ,
      drop = FALSE
    ]
  }

  fit_records <- if (nrow(fit_activities) > 0L) {
    fit_activities[, c("date", "sport", "moving_time_seconds", "source"),
                   drop = FALSE]
  } else {
    data.frame(
      date = as.Date(character()),
      sport = character(),
      moving_time_seconds = numeric(),
      source = character(),
      stringsAsFactors = FALSE
    )
  }

  all_activities <- rbind(fit_records, historical_activities)
  rownames(all_activities) <- NULL

  # Aggregate every activity type and both sources by local calendar date.
  if (nrow(all_activities) > 0L) {
    daily <- stats::aggregate(
      moving_time_seconds ~ date,
      data = all_activities,
      FUN = sum
    )
    daily <- daily[order(daily$date), , drop = FALSE]

    daily_summary <- data.frame(
      date = format(daily$date, "%Y-%m-%d"),
      moving_time = as.numeric(daily$moving_time_seconds) / 3600,
      stringsAsFactors = FALSE
    )
  } else {
    daily_summary <- data.frame(
      date = character(),
      moving_time = numeric(),
      stringsAsFactors = FALSE
    )
  }

  # Intermediate data stays outside the repository by default.
  if (is.null(output_file)) {
    output_dir <- Sys.getenv("RUNNER_TEMP", unset = tempdir())
    output_file <- file.path(output_dir, "daily-activities.csv")
  }

  dir.create(dirname(output_file), recursive = TRUE, showWarnings = FALSE)
  utils::write.csv(
    daily_summary,
    file = output_file,
    row.names = FALSE,
    na = ""
  )

  json_output_path <- NULL
  if (!is.null(json_output_file)) {
    json_output_path <- write_activity_json(
      summary = daily_summary,
      window = c(start = as.character(start_date), end = as.character(end_date)),
      timezone = timezone,
      output_file = json_output_file,
      generated_at = generated_at
    )
  }

  n_fit_in_window <- sum(all_activities$source == "fit")
  n_historical_in_window <- sum(all_activities$source == "historical_csv")

  if (!quiet) {
    message("FIT files found: ", n_files_found)
    message("Identical FIT file copies skipped: ", length(duplicate_file_paths))
    message("Duplicate FIT activity records skipped: ", duplicate_activity_count)
    message("FIT activities in window: ", n_fit_in_window)
    message("Historical activities in window: ", n_historical_in_window)
    message("Total activities in window: ", nrow(all_activities))
    message("Active days: ", nrow(daily_summary))
    message("Window: ", format(start_date), " to ", format(end_date),
            " (", timezone, ")")
    message("Daily CSV: ", normalizePath(output_file, mustWork = TRUE))

    if (nrow(parse_errors) > 0L) {
      warning(
        nrow(parse_errors),
        " FIT file(s) could not be parsed. See the returned `parse_errors` table.",
        call. = FALSE
      )
    }
  }

  invisible(list(
    summary = daily_summary,
    activities = all_activities,
    fit_activities = fit_activities,
    historical_activities = historical_activities,
    files_found = n_files_found,
    files_parsed = length(fit_files) - nrow(parse_errors),
    identical_files_skipped = length(duplicate_file_paths),
    duplicate_activities_skipped = duplicate_activity_count,
    parse_errors = parse_errors,
    window = c(start = as.character(start_date), end = as.character(end_date)),
    output_file = normalizePath(output_file, mustWork = TRUE),
    json_output_file = json_output_path
  ))
}

# Command-line entry point: `Rscript R/process_activities.R` from any working
# directory. Sourcing the file defines the function but does not run it.
if (sys.nframe() == 0L) {
  script_arg <- grep("^--file=", commandArgs(trailingOnly = FALSE), value = TRUE)

  if (length(script_arg) != 1L) {
    stop("Could not determine the path to process_activities.R.", call. = FALSE)
  }

  script_path <- normalizePath(sub("^--file=", "", script_arg), mustWork = TRUE)
  script_dir <- dirname(script_path)
  repository_root <- dirname(script_dir)

  source(file.path(script_dir, "fit_to_activity.R"), local = FALSE)

  activity_dir <- Sys.getenv(
    "ACTIVITIES_DIR",
    unset = file.path(repository_root, "activities")
  )
  historical_file <- Sys.getenv(
    "HISTORICAL_CSV",
    unset = file.path(repository_root, "data", "historical_activities.csv")
  )

  result <- process_activities(
    activities_dir = activity_dir,
    historical_csv = historical_file
  )

  if (nrow(result$parse_errors) > 0L) {
    message("Some FIT files were skipped because they could not be parsed.")
    print(result$parse_errors, row.names = FALSE)
  }
}
