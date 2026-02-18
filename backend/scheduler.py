"""Compute time until the next street cleaning window."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from backend.parser import CleaningSchedule

NYC_TZ = ZoneInfo("America/New_York")


def hours_until_next_cleaning(schedule: CleaningSchedule, now: datetime | None = None) -> float:
    """Return hours from `now` until the start of the next cleaning window.

    If cleaning is currently happening, returns 0.
    """
    if now is None:
        now = datetime.now(NYC_TZ)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=NYC_TZ)

    current_weekday = now.weekday()
    current_minutes = now.hour * 60 + now.minute
    start_minutes = schedule.start_hour * 60 + schedule.start_minute
    end_minutes = schedule.end_hour * 60 + schedule.end_minute

    for day_offset in range(8):
        check_day = (current_weekday + day_offset) % 7
        if check_day not in schedule.days:
            continue

        if day_offset == 0:
            if start_minutes <= current_minutes < end_minutes:
                return 0.0
            if current_minutes < start_minutes:
                return (start_minutes - current_minutes) / 60.0
            # Already past today's window, keep looking
            continue

        minutes_until = (day_offset * 24 * 60) + start_minutes - current_minutes
        return minutes_until / 60.0

    return float("inf")
