# Convert one Garmin FIT file into the minimal activity structure consumed by
# the activity-time heatmap pipeline.
#
# Output contract: one row per FIT session with start_time (UTC), sport,
# and moving_time_seconds.
# The adapter deliberately does not extract GPS coordinates, route polylines,
# heart-rate series, or device metadata.

.fit_first_value <- function(x) {
  if (is.null(x) || length(x) == 0L) {
    return(NULL)
  }

  valid <- !is.na(x)
  if (is.character(x)) {
    valid <- valid & nzchar(trimws(x))
  }

  if (!any(valid)) {
    return(NULL)
  }

  x[which(valid)[1L]]
}

.fit_column_value <- function(x, column, row = 1L) {
  if (is.null(x) || !column %in% names(x) || nrow(x) < row) {
    return(NULL)
  }

  .fit_first_value(x[[column]][row])
}

.fit_bind_messages <- function(x) {
  if (is.null(x)) {
    return(NULL)
  }

  if (is.data.frame(x)) {
    return(x)
  }

  # FITfileR may return a list of data frames when a message type has more
  # than one definition in the same file.
  if (is.list(x) && length(x) > 0L &&
      all(vapply(x, is.data.frame, logical(1)))) {
    return(dplyr::bind_rows(x))
  }

  stop("Unexpected message structure returned by FITfileR.", call. = FALSE)
}

.fit_get_messages <- function(fit, message_type) {
  available_types <- FITfileR::listMessageTypes(fit)

  if (!message_type %in% available_types) {
    return(NULL)
  }

  .fit_bind_messages(
    FITfileR::getMessagesByType(fit, message_type = message_type)
  )
}

.fit_parse_start_time <- function(x) {
  if (is.null(x) || length(x) == 0L || is.na(x[1L])) {
    stop("The FIT session does not contain a valid start_time.", call. = FALSE)
  }

  if (inherits(x, "POSIXt")) {
    return(as.POSIXct(x[1L], tz = "UTC"))
  }

  if (is.character(x)) {
    value <- trimws(x[1L])
    parsed <- suppressWarnings(
      as.POSIXct(
        value,
        tz = "UTC",
        tryFormats = c(
          "%Y-%m-%dT%H:%M:%OS%z",
          "%Y-%m-%dT%H:%M:%OSZ",
          "%Y-%m-%dT%H:%M:%OS",
          "%Y-%m-%d %H:%M:%OS"
        )
      )
    )

    if (!is.na(parsed)) {
      return(as.POSIXct(parsed, tz = "UTC"))
    }
  }

  stop(
    "Could not interpret the FIT session start_time as a date-time. ",
    "Expected a POSIXct value or ISO-8601 character string.",
    call. = FALSE
  )
}

.fit_normalise_sport <- function(sport, sub_sport = NULL) {
  if (is.null(sport) || length(sport) == 0L || all(is.na(sport))) {
    sport <- "unknown"
  }
  if (is.null(sub_sport) || length(sub_sport) == 0L ||
      all(is.na(sub_sport))) {
    sub_sport <- ""
  }

  sport <- tolower(trimws(as.character(sport[1L])))
  sub_sport <- tolower(trimws(as.character(sub_sport[1L])))

  sport <- gsub("[ -]+", "_", sport)
  sub_sport <- gsub("[ -]+", "_", sub_sport)

  if (sport %in% c("run", "running", "trail_running")) {
    if (sport == "trail_running" ||
        sub_sport %in% c("trail", "trail_running")) {
      return("trail_running")
    }
    return("running")
  }

  if (sport %in% c("ride", "cycling", "mountain_biking", "road_cycling")) {
    return("cycling")
  }

  if (sport %in% c("walk", "walking", "hiking")) {
    return("walking")
  }

  # Preserve other Garmin sport names. They are valid activities too and must
  # not be filtered out by the aggregation layer.
  if (!nzchar(sport)) "unknown" else sport
}

#' Parse one FIT file into a normalized activity record
#'
#' @param fit_file Path to a Garmin FIT file.
#'
#' @return A data.frame with one row per FIT session and columns
#'   `start_time`, `sport`, and `moving_time_seconds`. Timestamps represent the
#'   original instants in UTC; local calendar dates are assigned later by
#'   `process_activities()`.
#' @export
fit_to_activity <- function(fit_file) {
  if (!is.character(fit_file) || length(fit_file) != 1L ||
      is.na(fit_file) || !file.exists(fit_file)) {
    stop("`fit_file` must be a path to an existing FIT file.", call. = FALSE)
  }

  if (!requireNamespace("FITfileR", quietly = TRUE)) {
    stop(
      "Package `FITfileR` is required. Install it from ",
      "https://github.com/grimbough/FITfileR.",
      call. = FALSE
    )
  }

  if (!requireNamespace("dplyr", quietly = TRUE)) {
    stop("Package `dplyr` is required to combine FIT message tables.",
         call. = FALSE)
  }

  fit <- FITfileR::readFitFile(fit_file)
  session <- .fit_get_messages(fit, "session")

  if (is.null(session) || nrow(session) == 0L) {
    stop("No `session` message was found in the FIT file.", call. = FALSE)
  }

  # A normal activity often has one Session message. Multisport FIT files can
  # contain multiple Session messages (one per leg/transition), so retain all
  # of them rather than taking only the first one.
  sport_message <- .fit_get_messages(fit, "sport")

  session_records <- lapply(seq_len(nrow(session)), function(i) {
    start_time <- .fit_parse_start_time(
      .fit_column_value(session, "start_time", row = i)
    )

    # FIT session total_timer_time is expressed in seconds and excludes pauses.
    moving_time_seconds <- .fit_column_value(
      session, "total_timer_time", row = i
    )
    moving_time_seconds <- suppressWarnings(as.numeric(moving_time_seconds))

    if (length(moving_time_seconds) != 1L || !is.finite(moving_time_seconds) ||
        moving_time_seconds <= 0) {
      stop(
        "FIT session ", i,
        " does not contain a positive `total_timer_time` value (seconds).",
        call. = FALSE
      )
    }

    # Prefer the session fields. Use the corresponding sport-message row only
    # as a fallback when one exists for this session.
    sport_raw <- .fit_column_value(session, "sport", row = i)
    sub_sport_raw <- .fit_column_value(session, "sub_sport", row = i)

    if (is.null(sport_raw) && !is.null(sport_message) &&
        nrow(sport_message) >= i) {
      sport_raw <- .fit_column_value(sport_message, "sport", row = i)
    }
    if (is.null(sub_sport_raw) && !is.null(sport_message) &&
        nrow(sport_message) >= i) {
      sub_sport_raw <- .fit_column_value(sport_message, "sub_sport", row = i)
    }

    data.frame(
      start_time = start_time,
      sport = .fit_normalise_sport(sport_raw, sub_sport_raw),
      moving_time_seconds = moving_time_seconds,
      stringsAsFactors = FALSE
    )
  })

  do.call(rbind, session_records)
}
