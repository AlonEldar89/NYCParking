"""Parse NYC DOT sign descriptions to extract street cleaning schedules."""

import re
from dataclasses import dataclass

DAYS_OF_WEEK = {
    "MONDAY": 0,
    "TUESDAY": 1,
    "WEDNESDAY": 2,
    "THURSDAY": 3,
    "FRIDAY": 4,
    "SATURDAY": 5,
    "SUNDAY": 6,
}

TIME_RE = re.compile(
    r"(\d{1,2}(?::\d{2})?(?:AM|PM))\s*-\s*(\d{1,2}(?::\d{2})?(?:AM|PM))",
    re.IGNORECASE,
)

DAY_RE = re.compile(
    r"\b(" + "|".join(DAYS_OF_WEEK.keys()) + r")\b",
    re.IGNORECASE,
)


@dataclass
class CleaningSchedule:
    days: list[int]  # 0=Monday .. 6=Sunday
    start_hour: int
    start_minute: int
    end_hour: int
    end_minute: int


def _parse_time(t: str) -> tuple[int, int]:
    t = t.upper().strip()
    is_pm = t.endswith("PM")
    t = t.replace("AM", "").replace("PM", "")
    if ":" in t:
        h, m = t.split(":")
    else:
        h, m = t, "0"
    h, m = int(h), int(m)
    if is_pm and h != 12:
        h += 12
    if not is_pm and h == 12:
        h = 0
    return h, m


def parse_sign_description(desc: str) -> CleaningSchedule | None:
    """Return a CleaningSchedule if `desc` is a street-cleaning sign, else None."""
    if "SANITATION BROOM SYMBOL" not in desc.upper():
        return None

    upper = desc.upper()

    except_days = set()
    for day_name, day_num in DAYS_OF_WEEK.items():
        if f"EXCEPT {day_name}" in upper:
            except_days.add(day_num)

    # Strip "EXCEPT ..." clauses before matching explicit days
    cleaned = re.sub(r"EXCEPT\s+\w+", "", upper)
    day_matches = DAY_RE.findall(cleaned)

    if not day_matches and not except_days:
        return None

    if day_matches:
        days = sorted(set(DAYS_OF_WEEK[d.upper()] for d in day_matches) - except_days)
    else:
        # e.g. "EXCEPT SUNDAY" with no explicit days means every day except that one
        days = sorted(set(range(7)) - except_days)

    time_match = TIME_RE.search(desc)
    if not time_match:
        return None

    start_h, start_m = _parse_time(time_match.group(1))
    end_h, end_m = _parse_time(time_match.group(2))

    return CleaningSchedule(
        days=days,
        start_hour=start_h,
        start_minute=start_m,
        end_hour=end_h,
        end_minute=end_m,
    )
